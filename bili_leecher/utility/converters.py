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

    from bili_leecher import colab_bot
    is_prem = hasattr(colab_bot, "me") and getattr(colab_bot.me, "is_premium", False)
    max_allowed_mb = 3900 if is_prem else 1950

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
            max_size_mb = 3900
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
            logging.warning("Video splitting produced no parts or failed, falling back to 7z split archive...")
            await archive(file_path, is_split=True, remove=remove, split_size_mb=max_size_mb, target_dir=temp_zpath, task_ctx=task_ctx)
    elif any(filename.lower().endswith(ext) for ext in [".zip", ".rar", ".7z", ".tar", ".gz"]):
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


async def archive(path: str, is_split: bool = False, remove: bool = False, split_size_mb: int = 1950, target_dir: str = None, task_ctx=None):
    target_dir = target_dir or (task_ctx.temp_zpath if task_ctx else Paths.temp_zpath)
    makedirs(target_dir, exist_ok=True)

    name = (task_ctx.task_title if task_ctx else None) or ospath.basename(path)
    zip_pswd = (task_ctx.options.get("zip_pswd") if task_ctx else None) or BOT.Options.zip_pswd
    split_flag = f"-v{split_size_mb}m" if is_split else ""
    pswd_flag = f"-p{zip_pswd}" if zip_pswd else ""

    out_file = ospath.join(target_dir, f"{name}.7z")
    cmd = f'7z a -mx=0 {split_flag} {pswd_flag} "{out_file}" "{path}"'

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


async def extract(archive_path: str, target_dir: str = None, password: str = "", task_ctx=None) -> str:
    target_dir = target_dir or (task_ctx.temp_unzip_path if task_ctx else Paths.temp_unzip_path)
    makedirs(target_dir, exist_ok=True)
    pswd_flag = f"-p{password}" if password else "-p-"
    cmd = f'7z x -y {pswd_flag} -o"{target_dir}" "{archive_path}"'

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while proc.poll() is None:
        await sleep(2)

    return target_dir

