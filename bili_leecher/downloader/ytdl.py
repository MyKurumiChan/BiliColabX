# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import os
import logging
import yt_dlp
from asyncio import sleep, get_event_loop
from threading import Thread
from os import makedirs, path as ospath
from bili_leecher.utility.variables import BOT, YTDL, MSG, Messages, Paths
from bili_leecher.utility.settings_manager import SettingsManager
from bili_leecher.utility.helper import getTime, sizeUnit, status_bar


class MyLogger:
    def __init__(self):
        pass

    def debug(self, msg):
        pass

    @staticmethod
    def warning(msg):
        logging.warning(f"[yt-dlp warning] {msg}")

    @staticmethod
    def error(msg):
        if "ERROR: Cancelling..." not in str(msg):
            logging.error(f"[yt-dlp error] {msg}")


async def YTDL_Status(link, num, task_ctx=None):
    global Messages, YTDL

    user_id = task_ctx.chat_id if task_ctx else None
    cookie_path = SettingsManager.get_cookie_path(user_id)
    has_cookies = bool(cookie_path)
    engine_name = "yt-dlp 🏮 (🍪 Cookies)" if has_cookies else "yt-dlp 🏮"

    name = await get_YT_Name(link, cookie_path=cookie_path)
    custom_name = (task_ctx.options.get("custom_name") if task_ctx else None) or BOT.Options.custom_name
    if custom_name:
        name = custom_name

    if task_ctx:
        task_ctx.task_title = name
        task_ctx.engine = engine_name
        task_ctx.status_state = "Download"
    else:
        Messages.download_name = name

    # Reset metrics
    if task_ctx:
        task_ctx.speed = "0 B/s"
        task_ctx.percentage = 0.0
        task_ctx.eta = "N/A"
        task_ctx.done = "0 B"
        task_ctx.left = "N/A"
        task_ctx.error = None

    ytdl_thread = Thread(target=YouTubeDL, name="YouTubeDL", args=(link, task_ctx, cookie_path), daemon=True)
    ytdl_thread.start()

    while ytdl_thread.is_alive():
        try:
            if task_ctx and task_ctx.is_cancelled:
                break

            speed = task_ctx.speed if task_ctx else (YTDL.speed or "0 B/s")
            pct = task_ctx.percentage if task_ctx else float(YTDL.percentage or 0.0)
            eta = task_ctx.eta if task_ctx else (YTDL.eta or "N/A")
            done = task_ctx.done if task_ctx else (YTDL.done or "0 B")
            left = task_ctx.left if task_ctx else (YTDL.left or "N/A")

            await status_bar(
                down_msg=f"<b>📥 DOWNLOADING » </b><code>{name}</code>\n",
                speed=speed,
                percentage=pct,
                eta=eta,
                done=done,
                left=left,
                engine=engine_name,
                task_title=name,
                task_ctx=task_ctx,
            )
        except Exception as e:
            logging.error(f"Error in YTDL status update: {e}")

        await sleep(2.0)

    ytdl_thread.join(timeout=2.0)


def YouTubeDL(url, task_ctx=None, cookie_path: str = ""):
    global YTDL

    user_id = task_ctx.chat_id if task_ctx else None
    if not cookie_path:
        cookie_path = SettingsManager.get_cookie_path(user_id)

    def my_hook(d):
        nonlocal task_ctx
        if d.get("status") == "downloading":
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            dl_bytes = d.get("downloaded_bytes") or 0
            percent = 0.0
            if total_bytes > 0:
                percent = round((float(dl_bytes) * 100 / float(total_bytes)), 2)

            speed = d.get("speed")
            eta = d.get("eta")

            speed_str = f"{sizeUnit(speed)}/s" if (isinstance(speed, (int, float)) and speed > 0) else "0 B/s"
            eta_str = getTime(eta) if (isinstance(eta, (int, float)) and eta > 0) else "N/A"
            done_str = sizeUnit(dl_bytes)
            left_str = sizeUnit(total_bytes) if total_bytes > 0 else "N/A"

            if task_ctx:
                task_ctx.speed = speed_str
                task_ctx.percentage = percent
                task_ctx.eta = eta_str
                task_ctx.done = done_str
                task_ctx.left = left_str
                if total_bytes > 0:
                    task_ctx.total_size = total_bytes

    down_dir = task_ctx.down_path if task_ctx else Paths.down_path
    thumb_dir = task_ctx.thumbnail_ytdl if task_ctx else Paths.thumbnail_ytdl
    makedirs(down_dir, exist_ok=True)
    makedirs(thumb_dir, exist_ok=True)

    format_choice = "bv*+ba/b"
    if task_ctx and task_ctx.options.get("ytdl_format"):
        format_choice = task_ctx.options["ytdl_format"]

    custom_name = (task_ctx.options.get("custom_name") if task_ctx else None) or BOT.Options.custom_name

    if custom_name:
        base_name = ospath.splitext(custom_name)[0]
        default_tmpl = f"{down_dir}/{base_name}.%(ext)s"
    else:
        default_tmpl = f"{down_dir}/%(title).180s.%(ext)s"

    thumb_tmpl = f"{thumb_dir}/%(title).180s.%(ext)s"

    base_ydl_opts = {
        "outtmpl": {"default": default_tmpl, "thumbnail": thumb_tmpl},
        "writethumbnail": True,
        "overwrites": True,
        "ignoreerrors": False,
        "allow_multiple_video_streams": True,
        "allow_multiple_audio_streams": True,
        "allow_playlist_files": True,
        "trim_file_name": 180,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "merge_output_format": "mp4",
        "retries": 10,
        "fragment_retries": 10,
        "progress_hooks": [my_hook],
        "logger": MyLogger(),
        "quiet": False,
        "concurrent_fragment_downloads": 8,
        "buffersize": 1048576,
        "http_chunk_size": 10485760,
        "socket_timeout": 30,
    }

    if cookie_path and ospath.exists(cookie_path):
        base_ydl_opts["cookiefile"] = cookie_path

    ydl_opts = dict(base_ydl_opts)
    if format_choice == "mp3":
        ydl_opts.update({
            "format": "ba/b/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}],
        })
    else:
        ydl_opts["format"] = f"{format_choice}/bv*+ba/b/best"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logging.error(f"yt-dlp download failed: {e}")
        if task_ctx:
            task_ctx.error = str(e)


async def get_YT_Name(link, cookie_path: str = ""):
    loop = get_event_loop()

    def _extract():
        opts = {
            "logger": MyLogger(),
            "quiet": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "skip_download": True,
        }
        if cookie_path and ospath.exists(cookie_path):
            opts["cookiefile"] = cookie_path
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(link, download=False)

    try:
        info = await loop.run_in_executor(None, _extract)
        if info and "title" in info and info["title"]:
            return info["title"]
        return "Bilibili_Media"
    except Exception:
        return "Bilibili_Media"

