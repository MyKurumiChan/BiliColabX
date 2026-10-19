# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import os
import re
import json
import math
import psutil
import logging
import subprocess
import urllib.request
from time import time
from PIL import Image
from os import path as ospath
from datetime import datetime
from urllib.parse import urlparse
from asyncio import get_event_loop
from pyrogram.errors import BadRequest, FloodWait

try:
    from pyrogram.types import LinkPreviewOptions
    link_preview = LinkPreviewOptions(is_disabled=True)
except ImportError:
    link_preview = None

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bili_leecher.utility.variables import (
    BOT,
    MSG,
    BotTimes,
    Messages,
    Paths,
)


def isLink(_, __, update):
    if update.text:
        text = update.text.strip()
        if "/content/" in text or "/home" in text:
            return True
        elif "magnet:?xt=" in text.lower() or text.lower().endswith(".torrent"):
            return True
        url_match = re.search(r"https?://[^\s]+", text)
        if url_match:
            return True
    return False


def is_bilibili_url(link: str) -> bool:
    """Checks if the URL is a Bilibili video, audio, collection, series, or short link."""
    low = str(link).lower().strip()
    return any(domain in low for domain in [
        "bilibili.com",
        "b23.tv",
        "bili2233.cn",
        "bilivideo.com",
    ])


def is_google_drive(link):
    return "drive.google.com" in str(link)


def is_ytdl_link(link):
    return "bilibili.com" in str(link).lower() or "b23.tv" in str(link).lower()


def is_telegram(link):
    return "t.me" in str(link) or "telegram.me" in str(link)


def is_torrent_or_magnet(link):
    low = str(link).lower().strip()
    return "magnet:?xt=" in low or low.endswith(".torrent") or "torrent" in low


def getTime(seconds):
    seconds = int(seconds)
    days = seconds // (24 * 3600)
    seconds = seconds % (24 * 3600)
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


def speedETA(start, done, total):
    percentage = (done / total) * 100 if total > 0 else 0
    percentage = min(100.0, max(0.0, percentage))
    elapsed_time = (datetime.now() - start).seconds
    if done > 0 and elapsed_time != 0:
        raw_speed = done / elapsed_time
        speed = f"{sizeUnit(raw_speed)}/s"
        eta = (total - done) / raw_speed
    else:
        speed, eta = "N/A", 0
    return speed, eta, percentage


def sizeUnit(size):
    try:
        size = float(size)
    except Exception:
        return "0 B"
    if size > 1024 * 1024 * 1024 * 1024 * 1024:
        siz = f"{size/(1024**5):.2f} PiB"
    elif size > 1024 * 1024 * 1024 * 1024:
        siz = f"{size/(1024**4):.2f} TiB"
    elif size > 1024 * 1024 * 1024:
        siz = f"{size/(1024**3):.2f} GiB"
    elif size > 1024 * 1024:
        siz = f"{size/(1024**2):.2f} MiB"
    elif size > 1024:
        siz = f"{size/1024:.2f} KiB"
    else:
        siz = f"{size:.2f} B"
    return siz


def fileType(file_path: str):
    extensions_dict = {
        ".mp4": "video",
        ".avi": "video",
        ".mkv": "video",
        ".flv": "video",
        ".webm": "video",
        ".mov": "video",
        ".ts": "video",
        ".mp3": "audio",
        ".flac": "audio",
        ".aac": "audio",
        ".m4a": "audio",
        ".wav": "audio",
        ".ogg": "audio",
        ".jpg": "photo",
        ".png": "photo",
        ".webp": "photo",
        ".zip": "archive",
        ".rar": "archive",
        ".7z": "archive",
        ".tar": "archive",
        ".gz": "archive",
    }
    _, ext = ospath.splitext(file_path)
    return extensions_dict.get(ext.lower(), "document")


def getSize(path: str) -> int:
    total_size = 0
    if ospath.isfile(path):
        return os.path.getsize(path)
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


def shortFileName(name: str, max_len: int = 35) -> str:
    if len(name) <= max_len:
        return name
    base, ext = ospath.splitext(name)
    rem = max_len - len(ext) - 3
    if rem <= 5:
        return name[:max_len]
    return f"{base[:rem]}...{ext}"


def sysINFO():
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    ram_free = sizeUnit(vm.available)
    disk_free = sizeUnit(du.free)
    return (
        f"\n\n╭─ <b>[🖥 Colab Server Metrics]</b>\n"
        f"├ <b>CPU:</b> <code>{cpu}%</code> | <b>RAM:</b> <code>{vm.percent}%</code> (Free: <code>{ram_free}</code>)\n"
        f"╰ <b>Disk:</b> <code>{du.percent}%</code> (Free: <code>{disk_free}</code>)"
    )


def circular_progress(percentage: float) -> str:
    try:
        pct = float(percentage or 0.0)
    except Exception:
        pct = 0.0
    if pct <= 0.0:
        return "○" * 10
    elif pct >= 100.0:
        return "●" * 10
    filled = min(10, max(1, int(round(pct / 10.0))))
    empty = 10 - filled
    return "●" * filled + "○" * empty


def keyboard(task_ctx=None):
    t_id = task_ctx.task_id if task_ctx else ""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("♻️ Refresh", callback_data="ref"),
            InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_{t_id}" if t_id else "cancel"),
        ]
    ])


def quality_buttons(url: str, user_id: int = 0):
    """Inline quality buttons for interactive download."""
    clean_url = url.split()[0]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📺 1080P Full HD", callback_data=f"bili_dl_{user_id}_1080P"),
            InlineKeyboardButton("✨ 1080P+ High Bitrate", callback_data=f"bili_dl_{user_id}_1080P+"),
        ],
        [
            InlineKeyboardButton("🌟 4K Dolby/HDR", callback_data=f"bili_dl_{user_id}_4K"),
            InlineKeyboardButton("🎬 720P HD", callback_data=f"bili_dl_{user_id}_720P"),
        ],
        [
            InlineKeyboardButton("📱 480P SD", callback_data=f"bili_dl_{user_id}_480P"),
            InlineKeyboardButton("🎵 Audio Only (FLAC/320K)", callback_data=f"bili_dl_{user_id}_Audio"),
        ],
        [
            InlineKeyboardButton("💬 Download Danmaku (.ass)", callback_data=f"bili_dl_{user_id}_Danmaku"),
            InlineKeyboardButton("❌ Cancel", callback_data="uset_close"),
        ]
    ])


def render_multi_status(active_tasks: dict, chat_id: int = None) -> str:
    """Unified single-window live dashboard for all parallel Bilibili tasks."""
    if not active_tasks:
        return "<b>✅ All Bilibili tasks have finished! System is idle.</b>"

    target_tasks = {tid: ctx for tid, ctx in active_tasks.items() if (chat_id is None or ctx.chat_id == chat_id)}
    if not target_tasks:
        target_tasks = active_tasks

    lines = [
        f"<b>⚡ BiliColabX — Live Dashboard 📺</b>",
        f"<i>Active Parallel Tasks: {len(target_tasks)}</i>\n",
    ]

    for t_id, ctx in target_tasks.items():
        title = shortFileName(ctx.task_title, 36)
        pct = float(ctx.percentage or 0.0)
        prog_bar = circular_progress(pct)
        speed = ctx.speed or "0 B/s"
        done = ctx.done or "0 B"
        left = ctx.left or "N/A"
        eta = ctx.eta or "N/A"
        engine = ctx.engine or "BBDown 📺"
        state = ctx.status_state or "Downloading"

        task_block = (
            f"╭⌬ <b>[{state}]</b> <code>{title}</code>\n"
            f"├⌬ <code>[{prog_bar}]</code> <b>{pct:.1f}%</b>\n"
            f"├⌬ <b>Speed :</b> <code>{speed}</code> | <b>ETA :</b> <code>{eta}</code>\n"
            f"├⌬ <b>Done  :</b> <code>{done}</code> / <code>{left}</code>\n"
            f"├⌬ <b>User  :</b> <b>{ctx.user_name}</b> | <b>Engine:</b> <i>{engine}</i>\n"
            f"╰⌬ <b>Stop  :</b> /cancel_{t_id}\n"
        )
        lines.append(task_block)

    lines.append(sysINFO())
    return "\n".join(lines)


async def status_bar(
    down_msg: str,
    speed: str,
    percentage: float,
    eta: str,
    done: str,
    left: str,
    engine: str = "BBDown 📺",
    task_title: str = "",
    task_ctx=None,
):
    from bili_leecher import colab_bot
    target_msg = task_ctx.status_msg if (task_ctx and task_ctx.status_msg) else MSG.status_msg
    if not target_msg and task_ctx and task_ctx.chat_id:
        from bili_leecher.utility.task_manager import CHAT_STATUS_MSGS
        target_msg = CHAT_STATUS_MSGS.get(task_ctx.chat_id)
        if target_msg:
            task_ctx.status_msg = target_msg
    if not target_msg:
        return

    now = time()
    if task_ctx:
        if now - getattr(task_ctx, "last_update", 0) < 1.8:
            return
        task_ctx.last_update = now

    from bili_leecher.utility.task_manager import ACTIVE_TASKS
    if ACTIVE_TASKS:
        c_id = task_ctx.chat_id if task_ctx else None
        text = render_multi_status(ACTIVE_TASKS, chat_id=c_id)
    else:
        pct_bar = circular_progress(percentage)
        title = shortFileName(task_title or Messages.download_name, 35)
        text = (
            f"<b>⚡ BiliColabX — Media Stream</b>\n\n"
            f"╭⌬ <b>File  :</b> <code>{title}</code>\n"
            f"├⌬ <code>[{pct_bar}]</code> <b>{percentage:.1f}%</b>\n"
            f"├⌬ <b>Speed :</b> <code>{speed}</code> | <b>ETA :</b> <code>{eta}</code>\n"
            f"├⌬ <b>Done  :</b> <code>{done}</code> / <code>{left}</code>\n"
            f"╰⌬ <b>Engine:</b> <i>{engine}</i>\n"
            f"{sysINFO()}"
        )

    try:
        await target_msg.edit_text(text, reply_markup=keyboard(task_ctx), disable_web_page_preview=True)
    except FloodWait as fw:
        await sleep(fw.value)
    except Exception:
        pass


def download_thumbnail_from_url(url: str, user_id: int) -> str:
    try:
        from bili_leecher.utility.settings_manager import SettingsManager
        tmp_dst = os.path.join(Paths.WORK_PATH, f"temp_thumb_{user_id}.jpg")
        urllib.request.urlretrieve(url, tmp_dst)
        SettingsManager.save_user_thumb(user_id, tmp_dst)
        try:
            os.remove(tmp_dst)
        except Exception:
            pass
        return SettingsManager.get_user_thumb_path(user_id)
    except Exception as e:
        logging.error(f"Error downloading thumbnail: {e}")
        return ""


def setThumbnail(file_path: str):
    try:
        image = Image.open(file_path)
        image.thumbnail((320, 320))
        image.save(Paths.THMB_PATH, "JPEG")
        return True
    except Exception:
        return False


def thumbMaintainer(video_path: str, task_ctx=None, user_id: int = 0):
    from bili_leecher.utility.settings_manager import SettingsManager

    duration = 0
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True,
            text=True,
        )
        if res.stdout.strip():
            duration = float(res.stdout.strip())
    except Exception:
        duration = 0

    # 1. Custom User thumbnail
    if user_id:
        u_thumb = SettingsManager.get_user_thumb_path(user_id)
        if os.path.exists(u_thumb):
            return u_thumb, duration

    # 2. Check if a downloaded Bilibili video cover / thumbnail exists in task folder
    down_dir = task_ctx.down_path if task_ctx else Paths.down_path
    if ospath.exists(down_dir):
        for f in os.listdir(down_dir):
            if f.lower().endswith((".jpg", ".png", ".webp")) and not f.startswith("temp"):
                cover_p = os.path.join(down_dir, f)
                try:
                    img = Image.open(cover_p)
                    out_thumb = os.path.join(down_dir, "bili_cover.jpg")
                    img.convert("RGB").save(out_thumb, "JPEG", quality=90)
                    return out_thumb, duration
                except Exception:
                    pass

    # 3. Generate thumbnail frame from video using ffmpeg
    frame_path = os.path.join(Paths.WORK_PATH, f"frame_{int(time())}.jpg")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "00:00:05", "-i", video_path, "-vframes", "1", "-q:v", "2", frame_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
            return frame_path, duration
    except Exception:
        pass

    return None, duration


def videoExtFix(file_path: str) -> str:
    if file_path.endswith(".m4v") or file_path.endswith(".flv"):
        new_p = ospath.splitext(file_path)[0] + ".mp4"
        try:
            os.rename(file_path, new_p)
            return new_p
        except Exception:
            return file_path
    return file_path


def generate_sample_video(file_path: str, duration: int = 30) -> str:
    try:
        sample_out = os.path.join(Paths.samples_dir, f"sample_{ospath.basename(file_path)}")
        os.makedirs(Paths.samples_dir, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-ss", "00:01:00", "-i", file_path,
            "-t", str(duration), "-c", "copy", sample_out,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(sample_out) and os.path.getsize(sample_out) > 0:
            return sample_out
    except Exception as e:
        logging.error(f"Sample video error: {e}")
    return ""


def generate_screenshots(file_path: str, count: int = 5) -> list:
    shots = []
    try:
        os.makedirs(Paths.screenshots_dir, exist_ok=True)
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True,
            text=True,
        )
        total_sec = float(res.stdout.strip()) if res.stdout.strip() else 60.0
        step = max(5.0, total_sec / (count + 1))

        for idx in range(1, count + 1):
            ss_time = int(idx * step)
            out_img = os.path.join(Paths.screenshots_dir, f"shot_{idx}_{int(time())}.jpg")
            cmd = ["ffmpeg", "-y", "-ss", str(ss_time), "-i", file_path, "-vframes", "1", "-q:v", "2", out_img]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(out_img) and os.path.getsize(out_img) > 0:
                shots.append(out_img)
    except Exception as e:
        logging.error(f"Screenshots error: {e}")
    return shots


def automated_video_merge(folder_path: str) -> str:
    """Merges all video parts inside folder into a single unified video."""
    video_files = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            if fileType(os.path.join(root, f)) == "video":
                video_files.append(os.path.join(root, f))
    if len(video_files) <= 1:
        return video_files[0] if video_files else ""

    from natsort import natsorted
    video_files = natsorted(video_files)
    list_file = os.path.join(folder_path, "merge_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for vf in video_files:
            f.write(f"file '{vf}'\n")

    out_merged = os.path.join(folder_path, "Merged_Video.mp4")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_merged]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if os.path.exists(out_merged) and os.path.getsize(out_merged) > 0:
        for vf in video_files:
            try:
                os.remove(vf)
            except Exception:
                pass
        try:
            os.remove(list_file)
        except Exception:
            pass
        return out_merged
    return ""

