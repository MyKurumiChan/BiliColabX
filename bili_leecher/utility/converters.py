# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import os
import json
import shutil
import logging
import subprocess
from asyncio import sleep
from datetime import datetime
from os import makedirs, path as ospath

try:
    import GPUtil
except ImportError:
    GPUtil = None

import math
from bili_leecher.utility.settings_manager import SettingsManager
from bili_leecher.utility.variables import BOT, MSG, BotTimes, Paths, Messages
from bili_leecher.utility.helper import (
    getSize,
    fileType,
    keyboard,
    sizeUnit,
    status_bar,
    sysINFO,
    getTime,
)


async def videoConverter(file: str):
    name, ext = ospath.splitext(file)
    if ext.lower() in [".mkv", ".mp4"]:
        return file

    out_file = f"{name}.{BOT.Options.video_out}"
    quality = "-preset fast -crf 23" if BOT.Options.convert_quality else ""

    cmd = f"ffmpeg -y -i \"{file}\" {quality} -c:v libx264 -c:a aac -strict -2 \"{out_file}\""
    proc = subprocess.Popen(cmd, shell=True)
    while proc.poll() is None:
        await sleep(3)

    if ospath.exists(out_file) and getSize(out_file) > 0:
        try:
            os.remove(file)
        except Exception:
            pass
        return out_file
    return file


async def sizeChecker(file_path: str, remove: bool = False, task_ctx=None) -> bool:
    if not ospath.exists(file_path):
        return False
    file_size = os.stat(file_path).st_size

    user_id = getattr(task_ctx, "user_id", None) or (task_ctx.chat_id if task_ctx else 0)
    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}

    # TG Tier: automatically determined by whether the active Telegram account is Premium
    from bili_leecher import colab_bot
    bot_has_prem = hasattr(colab_bot, "me") and getattr(colab_bot.me, "is_premium", False)

    task_prem_opt = task_ctx.options.get("is_prem") if task_ctx else None
    if task_prem_opt is not None:
        is_prem = bool(task_prem_opt)
    else:
        is_prem = bot_has_prem

    # Telegram hard upload ceiling: 3950 MB for Premium, 1950 MB for Free
    max_allowed_mb = 3950 if is_prem else 1950

    task_split_mb = task_ctx.options.get("split_size_mb") if task_ctx else 0
    if task_split_mb and int(task_split_mb) > 0:
        max_size_mb = min(int(task_split_mb), max_allowed_mb)
    else:
        custom_mb = u_conf.get("split_size_mb", 0)
        if custom_mb and int(custom_mb) > 50:
            max_size_mb = min(int(custom_mb), max_allowed_mb)
        else:
            user_split = str(u_conf.get("split_video", "2.0GB")).upper().strip()
            if "500" in user_split:
                max_size_mb = 500
            elif "1.5" in user_split or "1500" in user_split:
                max_size_mb = 1500
            elif "1" in user_split or "1000" in user_split:
                max_size_mb = 1000
            elif "4" in user_split and is_prem:
                max_size_mb = 3950
            else:
                max_size_mb = 1950

    max_size_bytes = max_size_mb * 1024 * 1024
    if file_size <= max_size_bytes:
        return False

    temp_zpath = task_ctx.temp_zpath if task_ctx else Paths.temp_zpath
    makedirs(temp_zpath, exist_ok=True)
    _, filename = ospath.split(file_path)

    logging.info(f"File {filename} ({sizeUnit(file_size)}) exceeds split target ({max_size_mb} MB). Splitting...")

    f_type = fileType(file_path)
    if f_type == "video":
        success = await splitVideo(file_path, max_size_mb, remove, target_dir=temp_zpath, task_ctx=task_ctx)
        if not success or not os.listdir(temp_zpath):
            logging.warning("Video splitting produced no parts or failed, falling back to multi-volume split archive...")
            await archive(file_path, is_split=True, remove=remove, split_size_mb=max_size_mb, target_dir=temp_zpath, task_ctx=task_ctx)
    elif any(filename.lower().endswith(ext) for ext in [".zip", ".rar", ".7z", ".tar", ".gz", ".tgz"]):
        await splitArchive(file_path, max_size_bytes, target_dir=temp_zpath, task_ctx=task_ctx)
    else:
        await archive(file_path, is_split=True, remove=remove, split_size_mb=max_size_mb, target_dir=temp_zpath, task_ctx=task_ctx)

    await sleep(1)
    return True


async def splitVideo(video_path: str, max_size_mb: int, remove: bool = False, target_dir: str = None, task_ctx=None) -> bool:
    """Clean video splitting via FFmpeg stream copy (-c copy)."""
    target_dir = target_dir or (task_ctx.temp_zpath if task_ctx else Paths.temp_zpath)
    makedirs(target_dir, exist_ok=True)

    file_size = os.path.getsize(video_path)
    max_size_bytes = max_size_mb * 1024 * 1024
    total_parts = int(math.ceil(file_size / max_size_bytes))

    # Probe duration
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True,
            text=True,
        )
        total_duration = float(res.stdout.strip())
    except Exception:
        total_duration = 0

    if total_duration <= 0:
        return False

    segment_time = total_duration / total_parts
    base_name, ext = ospath.splitext(ospath.basename(video_path))
    out_pattern = ospath.join(target_dir, f"{base_name}.part%03d{ext}")

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-c", "copy", "-map", "0",
        "-segment_time", str(int(segment_time)),
        "-f", "segment",
        "-reset_timestamps", "1",
        out_pattern
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        await sleep(2)

    parts_created = [f for f in os.listdir(target_dir) if f.startswith(base_name) and ".part" in f]
    if parts_created:
        if remove:
            try:
                os.remove(video_path)
            except Exception:
                pass
        return True
    return False


async def splitArchive(archive_path: str, max_size_bytes: int, target_dir: str = None, task_ctx=None):
    target_dir = target_dir or (task_ctx.temp_zpath if task_ctx else Paths.temp_zpath)
    split_size_mb = int(max_size_bytes / (1024 * 1024))
    await archive(archive_path, is_split=True, remove=True, split_size_mb=split_size_mb, target_dir=target_dir, task_ctx=task_ctx)


async def archive(
    path: str,
    is_split: bool = False,
    remove: bool = False,
    split_size_mb: int = 1950,
    target_dir: str = None,
    task_ctx=None,
    archive_format: str = None,
    password: str = None,
):
    """
    Creates archives with multi-format support (zip, 7z, rar, tar, tar.gz) and optional multi-volume splitting.
    """
    target_dir = target_dir or (task_ctx.temp_zpath if task_ctx else Paths.temp_zpath)
    makedirs(target_dir, exist_ok=True)

    user_id = getattr(task_ctx, "user_id", None) or (task_ctx.chat_id if task_ctx else 0)
    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}

    # Format resolution: direct param > task option > user setting > default "zip"
    fmt = (
        archive_format
        or (task_ctx.options.get("archive_format") if task_ctx else None)
        or u_conf.get("archive_format")
        or "zip"
    ).lower().strip()

    name = (task_ctx.task_title if task_ctx else None) or ospath.basename(path)
    zip_pswd = password or (task_ctx.options.get("zip_pswd") if task_ctx else None) or BOT.Options.zip_pswd

    split_flag_7z = f"-v{split_size_mb}m" if is_split else ""
    split_flag_rar = f"-v{split_size_mb}m" if is_split else ""
    pswd_flag_7z = f"-p{zip_pswd}" if zip_pswd else ""
    pswd_flag_rar = f"-p{zip_pswd} -hp{zip_pswd}" if zip_pswd else ""

    # Sanitize name
    name_clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip() or "Bilibili_Archive"

    cmd = None
    if fmt == "rar":
        # Check if rar CLI is available
        rar_available = shutil.which("rar") is not None
        if rar_available:
            out_file = ospath.join(target_dir, f"{name_clean}.rar")
            cmd = f'rar a -m1 {split_flag_rar} {pswd_flag_rar} "{out_file}" "{path}"'
        else:
            # Fallback to 7z format if rar binary is absent
            fmt = "7z"

    if fmt in ["7z", "7zip"]:
        out_file = ospath.join(target_dir, f"{name_clean}.7z")
        cmd = f'7z a -t7z -mx=1 -mhe=on {split_flag_7z} {pswd_flag_7z} "{out_file}" "{path}"'
    elif fmt == "tar":
        out_file = ospath.join(target_dir, f"{name_clean}.tar")
        if is_split:
            # Split tar into multi-volume parts via 7z
            cmd = f'7z a -ttar {split_flag_7z} "{out_file}" "{path}"'
        else:
            cmd = f'7z a -ttar "{out_file}" "{path}"'
    elif fmt in ["tar.gz", "tgz"]:
        out_file = ospath.join(target_dir, f"{name_clean}.tar.gz")
        if is_split:
            # Multi-volume gzip archive via 7z
            cmd = f'7z a -t7z -mx=1 {split_flag_7z} {pswd_flag_7z} "{out_file}" "{path}"'
        else:
            tar_temp = ospath.join(target_dir, f"{name_clean}.tar")
            cmd = f'7z a -ttar "{tar_temp}" "{path}" && 7z a -tgzip -mx=3 "{out_file}" "{tar_temp}" && rm -f "{tar_temp}"'
    elif not cmd:  # Default to zip
        out_file = ospath.join(target_dir, f"{name_clean}.zip")
        cmd = f'7z a -tzip -mx=1 {split_flag_7z} {pswd_flag_7z} "{out_file}" "{path}"'

    logging.info(f"Executing archive command: {cmd}")
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        await sleep(2)

    if remove:
        if ospath.isfile(path):
            try:
                os.remove(path)
            except Exception:
                pass
        elif ospath.isdir(path):
            try:
                shutil.rmtree(path)
            except Exception:
                pass


async def extract(archive_path: str, remove: bool = False, temp_unzip_path: str = None, task_ctx=None, password: str = "") -> str:
    target_dir = temp_unzip_path or (task_ctx.temp_unzip_path if task_ctx else Paths.temp_unzip_path)
    makedirs(target_dir, exist_ok=True)
    pswd = password or (task_ctx.options.get("unzip_pswd") if task_ctx else "")
    pswd_flag = f"-p{pswd}" if pswd else "-p-"
    cmd = f'7z x -y {pswd_flag} -o"{target_dir}" "{archive_path}"'

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        await sleep(2)

    if remove and ospath.exists(archive_path):
        try:
            os.remove(archive_path)
        except Exception:
            pass

    return target_dir


