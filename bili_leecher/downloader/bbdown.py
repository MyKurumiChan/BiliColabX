# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import os
import re
import sys
import shutil
import logging
import asyncio
import platform
import subprocess
from typing import Tuple, List, Dict, Any, Optional
from asyncio import sleep, get_event_loop
from time import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from bili_leecher.utility.variables import BOT, BBDOWN, Paths
from bili_leecher.utility.settings_manager import SettingsManager
from bili_leecher.utility.helper import (
    status_bar,
    sizeUnit,
    getTime,
    fileType,
    getSize,
)
from bili_leecher.downloader.bilibili_helper import (
    normalize_bilibili_url,
    fetch_bilibili_info,
    parse_range_spec,
)

BBDOWN_BIN_PATH = None


def find_or_install_bbdown() -> str:
    """Finds existing BBDown executable or installs latest release if on Linux / Google Colab."""
    global BBDOWN_BIN_PATH
    if BBDOWN_BIN_PATH and os.path.exists(BBDOWN_BIN_PATH):
        return BBDOWN_BIN_PATH

    # 1. System PATH
    found = shutil.which("BBDown") or shutil.which("bbdown") or shutil.which("BBDown.exe")
    if found:
        BBDOWN_BIN_PATH = found
        return found

    # 2. Common Colab / Linux paths
    candidates = [
        "/usr/local/bin/BBDown",
        "/usr/bin/BBDown",
        os.path.join(Paths.BASE_DIR, "BBDown"),
        os.path.join(Paths.BASE_DIR, "BBDown.exe"),
        os.path.join(os.getcwd(), "BBDown"),
        os.path.join(os.getcwd(), "BBDown.exe"),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isfile(c):
            BBDOWN_BIN_PATH = c
            return c

    # 3. Auto-install on Linux / Google Colab
    if platform.system() == "Linux":
        try:
            logging.info("⬇️ Fetching latest BBDown release for Linux x64...")
            cmd = (
                "LATEST_RELEASE=$(curl -s https://api.github.com/repos/nilaoda/BBDown/releases/latest "
                "| grep 'browser_download_url.*linux-x64.zip' | cut -d '\"' -f 4) && "
                "wget -qO /tmp/BBDown.zip \"$LATEST_RELEASE\" && "
                "unzip -q -o /tmp/BBDown.zip -d /usr/local/bin/ && "
                "chmod +x /usr/local/bin/BBDown && "
                "rm -f /tmp/BBDown.zip"
            )
            subprocess.run(cmd, shell=True, check=True)
            if os.path.exists("/usr/local/bin/BBDown"):
                BBDOWN_BIN_PATH = "/usr/local/bin/BBDown"
                logging.info("✅ BBDown installed successfully into /usr/local/bin/BBDown")
                return BBDOWN_BIN_PATH
        except Exception as e:
            logging.error(f"Failed to auto-install BBDown: {e}")

    return "BBDown"


def map_resolution_to_bbdown(quality_str: str):
    """
    Maps friendly quality names into BBDown flags:
    Returns (quality_flag, is_audio_only)
    """
    q = (quality_str or "1080P").upper().strip()
    if q in ["AUDIO", "MP3", "FLAC", "SOUND"]:
        return "", True
    elif "8K" in q:
        return "8K", False
    elif "4K" in q:
        return "4K", False
    elif "1080P+" in q or "高码率" in q or "60" in q:
        return "1080P 高码率", False
    elif "1080P" in q or "1080" in q:
        return "1080P", False
    elif "720P" in q or "720" in q:
        return "720P", False
    elif "480P" in q or "480" in q:
        return "480P", False
    elif "360P" in q or "360" in q:
        return "360P", False
    return "1080P", False


async def bbdown_download(url: str, task_ctx=None):
    """
    Main entry point for downloading Bilibili media via BBDown:
    - Auto-detects Single vs Multi-part (分P) / Series / Collections
    - Dispatches to Aria2c accelerated downloading
    - Employs anti-rate-limit staggered delays
    - Feeds live progress into Telegram status card
    """
    clean_url = normalize_bilibili_url(url)
    bbdown_bin = find_or_install_bbdown()

    user_id = getattr(task_ctx, "user_id", None) or (task_ctx.chat_id if task_ctx else 0)
    sessdata = SettingsManager.get_sessdata(user_id)
    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}

    # Quality setting
    custom_q = (task_ctx.options.get("bili_quality") if task_ctx else None) or u_conf.get("bili_quality", "1080P")
    quality_flag, is_audio_only = map_resolution_to_bbdown(custom_q)
    if task_ctx and task_ctx.options.get("audio_only"):
        is_audio_only = True

    # Engine Selection & Concurrency Limits from User Settings
    engine_choice = str(
        (task_ctx.options.get("engine") if task_ctx else None)
        or u_conf.get("engine", "BBDown - WEB")
    )
    concurrent_videos = int(
        (task_ctx.options.get("concurrent_videos") if task_ctx else None)
        or u_conf.get("concurrent_videos", 4)
    )
    concurrent_videos = max(1, min(8, concurrent_videos))
    upos_host = str(
        (task_ctx.options.get("upos_host") if task_ctx else None)
        or u_conf.get("upos_host", "upos-sz-mirrorhw.bilivideo.com")
    )

    # If yt-dlp was chosen as engine
    if "yt-dlp" in engine_choice.lower() or "ytdl" in engine_choice.lower():
        logging.info("Routing download to yt-dlp engine as selected...")
        from bili_leecher.downloader.ytdl import YTDL_Status
        if task_ctx:
            task_ctx.engine = "yt-dlp 🎬"
        await YTDL_Status(clean_url, 1, task_ctx)
        return

    # Danmaku & Subtitles
    dl_danmaku = (task_ctx.options.get("download_danmaku") if task_ctx else None) or u_conf.get("download_danmaku", False)
    dl_sub = (task_ctx.options.get("download_sub") if task_ctx else None) or u_conf.get("download_sub", True)

    down_dir = task_ctx.down_path if task_ctx else Paths.down_path
    os.makedirs(down_dir, exist_ok=True)

    # 1. Probe video metadata
    eng_tag = "BBDown TV 📺" if "TV" in engine_choice.upper() else ("BBDown APP 📱" if "APP" in engine_choice.upper() else "BBDown 📺")
    if task_ctx:
        task_ctx.status_state = "Probing"
        task_ctx.engine = f"{eng_tag} (🍪 VIP)" if sessdata else eng_tag

    info = await fetch_bilibili_info(clean_url, sessdata=sessdata)
    video_title = info.get("title", "Bilibili_Video")
    if task_ctx and not task_ctx.options.get("custom_name"):
        task_ctx.task_title = video_title

    part_count = info.get("part_count", 1)
    is_multi_part = part_count > 1

    # Check range options from task context or URL parameter
    range_opt = task_ctx.options.get("range") if task_ctx else None
    if not range_opt:
        p_m = re.search(r"[?&]p=(\d+)", clean_url)
        if p_m:
            range_opt = p_m.group(1)

    start_p, end_p = 1, part_count
    if range_opt:
        start_p, end_p = parse_range_spec(str(range_opt))
        start_p = max(1, start_p)
        end_p = min(part_count, end_p) if part_count > 1 else max(1, end_p)

    logging.info(f"BBDown target: '{video_title}' | Parts: {part_count} | Range: {start_p}-{end_p} | Engine: {engine_choice} | Concurrency: {concurrent_videos} | VIP: {bool(sessdata)}")

    # 2. Single Video execution
    if not is_multi_part or (start_p == 1 and end_p == 1 and part_count <= 1):
        await run_bbdown_single(
            bbdown_bin=bbdown_bin,
            url=clean_url,
            down_dir=down_dir,
            quality_flag=quality_flag,
            is_audio_only=is_audio_only,
            sessdata=sessdata,
            dl_danmaku=dl_danmaku,
            dl_sub=dl_sub,
            engine_choice=engine_choice,
            upos_host=upos_host,
            task_ctx=task_ctx,
        )
    else:
        # 3. Multi-part / Collection Concurrent Runner with anti-rate-limit delay
        await run_bbdown_multipart(
            bbdown_bin=bbdown_bin,
            url=clean_url,
            down_dir=down_dir,
            start_part=start_p,
            end_part=end_p,
            total_parts=part_count,
            quality_flag=quality_flag,
            is_audio_only=is_audio_only,
            sessdata=sessdata,
            dl_danmaku=dl_danmaku,
            dl_sub=dl_sub,
            engine_choice=engine_choice,
            upos_host=upos_host,
            concurrency_limit=concurrent_videos,
            task_ctx=task_ctx,
        )

    # 4. Verify downloaded media
    valid_media = []
    for root, _, files in os.walk(down_dir):
        for f in files:
            f_low = f.lower()
            if not f_low.endswith((".aria2", ".part", ".tmp", ".log")):
                if fileType(os.path.join(root, f)) in ["video", "audio"]:
                    valid_media.append(os.path.join(root, f))

    if not valid_media:
        # If BBDown couldn't get the file, try fallback to yt-dlp
        logging.warning("BBDown produced 0 media files. Attempting yt-dlp fallback...")
        from bili_leecher.downloader.ytdl import YTDL_Status
        await YTDL_Status(clean_url, 1, task_ctx)


ANSI_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Strips all ANSI color codes and escape sequences produced by BBDown and Aria2c."""
    if not text:
        return ""
    return ANSI_REGEX.sub("", text)


async def read_stream_lines(stream):
    """
    Asynchronously yields lines from a StreamReader, splitting on BOTH \r and \n,
    with ANSI escape codes cleanly stripped.
    Required for aria2c / BBDown which flush live progress with \r and Spectre.Console sequences.
    """
    buffer = bytearray()
    while True:
        try:
            chunk = await stream.read(512)
        except Exception:
            break
        if not chunk:
            if buffer:
                line = strip_ansi(buffer.decode("utf-8", errors="ignore")).strip()
                if line:
                    yield line
            break

        buffer.extend(chunk)
        while b"\r" in buffer or b"\n" in buffer:
            idx_r = buffer.find(b"\r")
            idx_n = buffer.find(b"\n")
            if idx_r != -1 and (idx_n == -1 or idx_r < idx_n):
                split_idx = idx_r
            else:
                split_idx = idx_n

            raw = buffer[:split_idx]
            buffer = buffer[split_idx + 1 :]
            line = strip_ansi(raw.decode("utf-8", errors="ignore")).strip()
            if line:
                yield line


def parse_size_to_bytes(size_str: str) -> int:
    """Parses strings like '15.5MiB', '1.2GiB', '850KiB' into bytes."""
    if not size_str:
        return 0
    m = re.match(r"^([0-9.]+)\s*([KMGT]?i?B)$", size_str.strip(), re.IGNORECASE)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2).upper()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "KIB": 1024,
        "MB": 1024 ** 2,
        "MIB": 1024 ** 2,
        "GB": 1024 ** 3,
        "GIB": 1024 ** 3,
        "TB": 1024 ** 4,
        "TIB": 1024 ** 4,
    }
    return int(val * multipliers.get(unit, 1))


async def monitor_download_progress(down_dir: str, task_ctx, stop_event: asyncio.Event):
    """
    Background progress monitor that computes real-time download speed
    and ETA directly from disk bytes growth every 1.5 seconds.
    Ensures the Telegram status window ALWAYS shows live speed and ETA.
    """
    last_bytes = 0
    last_time = time()

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=1.5)
            break
        except asyncio.TimeoutError:
            pass

        if not task_ctx:
            continue

        now = time()
        dt = max(0.1, now - last_time)

        curr_bytes = 0
        try:
            for root, _, files in os.walk(down_dir):
                for f in files:
                    try:
                        curr_bytes += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass
        except Exception:
            pass

        is_merging = "Merging" in getattr(task_ctx, "status_state", "") or "混流" in getattr(task_ctx, "status_state", "")
        if is_merging:
            task_ctx.speed = "FFmpeg Mux ⚡"
            task_ctx.eta = "Processing..."
            if curr_bytes > 0:
                task_ctx.done = sizeUnit(curr_bytes)
                task_ctx.left = sizeUnit(curr_bytes)
            task_ctx.percentage = 99.5
        elif curr_bytes > last_bytes and last_bytes > 0:
            speed_bps = (curr_bytes - last_bytes) / dt
            if not task_ctx.speed or task_ctx.speed == "0 B/s" or "FFmpeg" in task_ctx.speed:
                task_ctx.speed = f"{sizeUnit(speed_bps)}/s"

            task_ctx.done = sizeUnit(curr_bytes)

            tot = getattr(task_ctx, "total_size", 0)
            if tot > curr_bytes:
                rem_bytes = tot - curr_bytes
                eta_sec = rem_bytes / speed_bps if speed_bps > 0 else 0
                if not task_ctx.eta or task_ctx.eta in ["N/A", "Processing..."]:
                    task_ctx.eta = getTime(eta_sec)
                task_ctx.left = sizeUnit(tot)
                if not getattr(task_ctx, "is_multipart_custom_pct", False) and (not task_ctx.percentage or task_ctx.percentage == 0.0):
                    task_ctx.percentage = min(99.0, max(0.5, round((curr_bytes / tot) * 100, 1)))
            else:
                task_ctx.left = sizeUnit(curr_bytes)
        elif curr_bytes > 0 and (not task_ctx.done or task_ctx.done == "0 B"):
            task_ctx.done = sizeUnit(curr_bytes)

        last_bytes = curr_bytes
        last_time = now

        try:
            await status_bar(
                down_msg=f"<b>📥 DOWNLOADING » </b><code>{task_ctx.task_title}</code>\n",
                speed=task_ctx.speed,
                percentage=task_ctx.percentage,
                eta=task_ctx.eta,
                done=task_ctx.done,
                left=task_ctx.left,
                engine=task_ctx.engine,
                task_title=task_ctx.task_title,
                task_ctx=task_ctx,
            )
        except Exception:
            pass


async def run_bbdown_single(
    bbdown_bin: str,
    url: str,
    down_dir: str,
    quality_flag: str,
    is_audio_only: bool,
    sessdata: str,
    dl_danmaku: bool,
    dl_sub: bool,
    engine_choice: str = "BBDown - WEB",
    upos_host: str = "upos-sz-mirrorhw.bilivideo.com",
    task_ctx=None,
):
    """Downloads a single Bilibili video using BBDown with aria2c acceleration."""
    if task_ctx:
        task_ctx.status_state = "Downloading"

    cmd = [
        bbdown_bin,
        url,
        "--work-dir", down_dir,
        "--use-aria2c",
        "--aria2c-args", "--console-log-level=warn --summary-interval=1 -x 16 -s 16 -j 16 -k 1M --min-split-size=1M --max-connection-per-server=16 --split=16 --file-allocation=falloc --disk-cache=64M --optimize-concurrent-downloads=true --conditional-get=true --stream-piece-selector=geom",
    ]

    if "TV" in engine_choice.upper():
        cmd.append("-tv")
    elif "APP" in engine_choice.upper():
        cmd.append("-app")

    if upos_host:
        cmd.extend(["--upos-host", upos_host])

    if is_audio_only:
        cmd.append("--audio-only")
    elif quality_flag:
        cmd.extend(["-q", quality_flag])

    if sessdata:
        cmd.extend(["-c", f"SESSDATA={sessdata}"])

    if dl_danmaku:
        cmd.append("--dd")

    if not dl_sub:
        cmd.append("--skip-subtitle")

    logging.info(f"Running BBDown single command: {' '.join(cmd)}")

    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_download_progress(down_dir, task_ctx, stop_event))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    pattern_aria2 = re.compile(
        r"\[#\w+\s+([0-9.]+\s*[KMGT]?i?B)\s*/\s*([0-9.]+\s*[KMGT]?i?B)\s*\(?([0-9.]+)%\)?.*?DL:\s*([0-9.]+\s*[KMGT]?i?B)(?:.*?ETA:\s*([0-9a-zA-Z:]+))?",
        re.IGNORECASE,
    )
    pattern_progress = re.compile(r"\(?(\d+(?:\.\d+)?)%\)?")
    pattern_speed = re.compile(r"(\d+(?:\.\d+)?\s*(?:K|M|G|T)?i?B/s)", re.IGNORECASE)
    pattern_aria_dl = re.compile(r"DL:\s*([0-9.]+\s*[KMGT]?i?B)", re.IGNORECASE)
    pattern_eta = re.compile(r"ETA:\s*([0-9a-zA-Z:]+)", re.IGNORECASE)
    pattern_done_total = re.compile(r"([0-9.]+\s*[KMGT]?i?B)\s*/\s*([0-9.]+\s*[KMGT]?i?B)", re.IGNORECASE)

    try:
        async for line in read_stream_lines(process.stdout):
            l_low = line.lower()

            # Lifecycle Stage Transitions
            if any(k in l_low for k in ["混流", "合并", "mux", "merge", "封装", "ffmpeg"]):
                if task_ctx:
                    task_ctx.status_state = "Merging Audio & Video 🎬"
                    task_ctx.speed = "FFmpeg Mux ⚡"
                    task_ctx.eta = "Processing..."
                    task_ctx.percentage = 99.5
                    tot_s = getattr(task_ctx, "total_size", 0)
                    if tot_s > 0:
                        task_ctx.done = sizeUnit(tot_s)
                        task_ctx.left = sizeUnit(tot_s)
                    await status_bar(
                        down_msg=f"<b>🎬 MERGING AUDIO & VIDEO » </b><code>{task_ctx.task_title}</code>\n",
                        speed=task_ctx.speed,
                        percentage=task_ctx.percentage,
                        eta=task_ctx.eta,
                        done=task_ctx.done,
                        left=task_ctx.left,
                        engine=task_ctx.engine,
                        task_title=task_ctx.task_title,
                        task_ctx=task_ctx,
                    )
                continue
            elif any(k in l_low for k in ["下载音频", "audio"]) and "merging" not in getattr(task_ctx, "status_state", "").lower():
                if task_ctx:
                    task_ctx.status_state = "Downloading Audio 🎵"
            elif any(k in l_low for k in ["下载视频", "video"]) and "merging" not in getattr(task_ctx, "status_state", "").lower():
                if task_ctx:
                    task_ctx.status_state = "Downloading Video 🎬"
            elif any(k in l_low for k in ["弹幕", "danmaku"]):
                if task_ctx:
                    task_ctx.status_state = "Downloading Danmaku 💬"
            elif any(k in l_low for k in ["字幕", "subtitle"]):
                if task_ctx:
                    task_ctx.status_state = "Downloading Subtitles 📑"
            elif any(k in l_low for k in ["清理", "clean"]):
                if task_ctx:
                    task_ctx.status_state = "Finishing & Cleaning 🧹"
                    task_ctx.speed = "Cleaning 🧹"
                    task_ctx.eta = "Almost done"
                    task_ctx.percentage = 99.9
            elif any(k in l_low for k in ["下载完成", "任务完成", "succeed"]):
                if task_ctx:
                    task_ctx.status_state = "Download Complete ✅"
                    task_ctx.percentage = 100.0
                    task_ctx.speed = "Done"
                    task_ctx.eta = "0s"

            # Fast-path: Complete Aria2c single-line progress update
            m_a2 = pattern_aria2.search(line)
            if m_a2 and task_ctx:
                p_done, p_tot, p_pct, p_spd, p_eta = m_a2.groups()
                p_tot_bytes = parse_size_to_bytes(p_tot)
                
                # Never let smaller audio stream overwrite previously learned larger total size
                current_max_tot = max(getattr(task_ctx, "total_size", 0), p_tot_bytes)
                task_ctx.total_size = current_max_tot
                task_ctx.left = sizeUnit(current_max_tot)

                task_ctx.percentage = float(p_pct)
                task_ctx.done = p_done.strip()
                task_ctx.speed = f"{p_spd.strip()}/s"
                if p_eta:
                    task_ctx.eta = p_eta.strip()
            else:
                # Fallback parsers
                m_pct = pattern_progress.search(line)
                if m_pct and task_ctx:
                    try:
                        task_ctx.percentage = float(m_pct.group(1))
                    except Exception:
                        pass

                m_spd = pattern_speed.search(line)
                if m_spd and task_ctx:
                    task_ctx.speed = m_spd.group(1).strip()
                else:
                    m_adl = pattern_aria_dl.search(line)
                    if m_adl and task_ctx:
                        task_ctx.speed = f"{m_adl.group(1).strip()}/s"

                m_eta = pattern_eta.search(line)
                if m_eta and task_ctx:
                    task_ctx.eta = m_eta.group(1).strip()

                m_dt = pattern_done_total.search(line)
                if m_dt and task_ctx:
                    p_tot_bytes = parse_size_to_bytes(m_dt.group(2))
                    current_max_tot = max(getattr(task_ctx, "total_size", 0), p_tot_bytes)
                    task_ctx.total_size = current_max_tot
                    task_ctx.left = sizeUnit(current_max_tot)
                    task_ctx.done = m_dt.group(1).strip()

            if task_ctx:
                await status_bar(
                    down_msg=f"<b>📥 DOWNLOADING » </b><code>{task_ctx.task_title}</code>\n",
                    speed=task_ctx.speed,
                    percentage=task_ctx.percentage,
                    eta=task_ctx.eta,
                    done=task_ctx.done,
                    left=task_ctx.left,
                    engine=task_ctx.engine,
                    task_title=task_ctx.task_title,
                    task_ctx=task_ctx,
                )

        await process.wait()
    finally:
        stop_event.set()
        try:
            await monitor_task
        except Exception:
            pass


async def run_bbdown_multipart(
    bbdown_bin: str,
    url: str,
    down_dir: str,
    start_part: int,
    end_part: int,
    total_parts: int,
    quality_flag: str,
    is_audio_only: bool,
    sessdata: str,
    dl_danmaku: bool,
    dl_sub: bool,
    engine_choice: str = "BBDown - WEB",
    upos_host: str = "upos-sz-mirrorhw.bilivideo.com",
    concurrency_limit: int = 4,
    task_ctx=None,
):
    """
    Concurrent multi-part engine with anti-rate-limit delays:
    Matches Downloader_Zone.txt mechanism:
    DELAY = (PART - START_PART) * 2
    """
    total_to_download = max(1, end_part - start_part + 1)
    completed_parts = 0
    part_progress = {}

    if task_ctx:
        task_ctx.is_multipart_custom_pct = True

    sem = asyncio.Semaphore(max(1, concurrency_limit))

    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_download_progress(down_dir, task_ctx, stop_event))

    async def download_one_part(part_num: int):
        nonlocal completed_parts, part_progress
        async with sem:
            if task_ctx and task_ctx.is_cancelled:
                return

            # Stagger delay to prevent Bilibili 412/429 anti-bot rate-limiting
            delay = (part_num - start_part) * 2
            if 0 < delay < 20:
                await sleep(delay)

            cmd = [
                bbdown_bin,
                url,
                "-p", str(part_num),
                "--work-dir", down_dir,
                "--use-aria2c",
                "--aria2c-args", "--console-log-level=warn --summary-interval=1 -x 16 -s 16 -j 16 -k 1M --min-split-size=1M --max-connection-per-server=16 --split=16 --file-allocation=falloc --disk-cache=64M --optimize-concurrent-downloads=true --conditional-get=true --stream-piece-selector=geom",
            ]

            if "TV" in engine_choice.upper():
                cmd.append("-tv")
            elif "APP" in engine_choice.upper():
                cmd.append("-app")

            if upos_host:
                cmd.extend(["--upos-host", upos_host])

            if is_audio_only:
                cmd.append("--audio-only")
            elif quality_flag:
                cmd.extend(["-q", quality_flag])

            if sessdata:
                cmd.extend(["-c", f"SESSDATA={sessdata}"])

            if dl_danmaku:
                cmd.append("--dd")

            logging.info(f"Starting BBDown Part {part_num}/{end_part}...")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            pattern_aria2 = re.compile(
                r"\[#\w+\s+([0-9.]+\s*[KMGT]?i?B)\s*/\s*([0-9.]+\s*[KMGT]?i?B)\s*\(?([0-9.]+)%\)?.*?DL:\s*([0-9.]+\s*[KMGT]?i?B)(?:.*?ETA:\s*([0-9a-zA-Z:]+))?",
                re.IGNORECASE,
            )
            pattern_aria_dl = re.compile(r"DL:\s*([0-9.]+\s*[KMGT]?i?B)", re.IGNORECASE)
            pattern_spd = re.compile(r"(\d+(?:\.\d+)?\s*(?:K|M|G|T)?i?B/s)", re.IGNORECASE)
            pattern_prog = re.compile(r"\(?(\d+(?:\.\d+)?)%\)?")

            async for l_str in read_stream_lines(proc.stdout):
                if task_ctx:
                    part_pct = part_progress.get(part_num, 0.0)
                    m_a2 = pattern_aria2.search(l_str)
                    if m_a2:
                        p_done, p_tot, p_pct, p_spd, p_eta = m_a2.groups()
                        part_pct = float(p_pct)
                        task_ctx.speed = f"{p_spd.strip()}/s"
                        task_ctx.done = f"{p_done.strip()} (P{part_num})"
                        task_ctx.left = p_tot.strip()
                        if p_eta:
                            task_ctx.eta = p_eta.strip()
                    else:
                        m_spd = pattern_spd.search(l_str)
                        if m_spd:
                            task_ctx.speed = m_spd.group(1).strip()
                        else:
                            m_adl = pattern_aria_dl.search(l_str)
                            if m_adl:
                                task_ctx.speed = f"{m_adl.group(1).strip()}/s"

                        m_pr = pattern_prog.search(l_str)
                        if m_pr:
                            try:
                                part_pct = float(m_pr.group(1))
                            except Exception:
                                pass

                    l_low = l_str.lower()
                    if any(k in l_low for k in ["混流", "合并", "mux", "merge", "封装", "ffmpeg"]):
                        task_ctx.status_state = f"Merging P{part_num} 🎬"
                        task_ctx.speed = "FFmpeg Mux ⚡"
                        task_ctx.eta = "Processing..."
                        part_pct = 99.5
                    elif any(k in l_low for k in ["下载音频", "audio"]) and "merging" not in getattr(task_ctx, "status_state", "").lower():
                        task_ctx.status_state = f"Downloading Audio P{part_num} 🎵"
                    elif any(k in l_low for k in ["下载视频", "video"]) and "merging" not in getattr(task_ctx, "status_state", "").lower():
                        task_ctx.status_state = f"Downloading Video P{part_num} 🎬"
                    elif any(k in l_low for k in ["清理", "clean"]):
                        task_ctx.status_state = f"Cleaning P{part_num} 🧹"
                        task_ctx.speed = "Cleaning 🧹"
                        task_ctx.eta = "Almost done"
                        part_pct = 99.9
                    elif any(k in l_low for k in ["下载完成", "任务完成", "succeed"]):
                        part_pct = 100.0

                    part_progress[part_num] = part_pct
                    in_progress_sum = sum(p for p in part_progress.values())
                    overall_pct = ((completed_parts * 100.0 + in_progress_sum) / (total_to_download * 100.0)) * 100.0
                    task_ctx.percentage = round(min(99.5, max(0.5, overall_pct)), 1)
                    if "merging" not in getattr(task_ctx, "status_state", "").lower() and "cleaning" not in getattr(task_ctx, "status_state", "").lower():
                        task_ctx.status_state = f"Downloading P{part_num} ({part_pct:.0f}%)"

                    await status_bar(
                        down_msg=f"<b>📥 DOWNLOADING » </b><code>{task_ctx.task_title}</code>\n",
                        speed=task_ctx.speed,
                        percentage=task_ctx.percentage,
                        eta=task_ctx.eta,
                        done=task_ctx.done,
                        left=task_ctx.left,
                        engine=task_ctx.engine,
                        task_title=task_ctx.task_title,
                        task_ctx=task_ctx,
                    )

            await proc.wait()
            completed_parts += 1
            if part_num in part_progress:
                del part_progress[part_num]

            if task_ctx:
                task_ctx.percentage = round((completed_parts / total_to_download) * 100, 1)
                task_ctx.done = f"{completed_parts}/{total_to_download} parts"
                task_ctx.status_state = f"Completed P{part_num}"
                await status_bar(
                    down_msg=f"<b>📥 DOWNLOADING » </b><code>{task_ctx.task_title}</code>\n",
                    speed=task_ctx.speed,
                    percentage=task_ctx.percentage,
                    eta=task_ctx.eta,
                    done=task_ctx.done,
                    left=task_ctx.left,
                    engine=task_ctx.engine,
                    task_title=task_ctx.task_title,
                    task_ctx=task_ctx,
                )

    try:
        tasks = [download_one_part(p) for p in range(start_part, end_part + 1)]
        await asyncio.gather(*tasks)
    finally:
        stop_event.set()
        try:
            await monitor_task
        except Exception:
            pass

