# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Dedicated Bilibili Download Pipeline

import logging
from datetime import datetime
from bili_leecher.downloader.bbdown import bbdown_download
from bili_leecher.downloader.bilibili_helper import (
    is_bilibili_url,
    fetch_bilibili_info,
    normalize_bilibili_url,
)
from bili_leecher.downloader.ytdl import YTDL_Status, get_YT_Name
from bili_leecher.downloader.telegram import TelegramDownload
from bili_leecher.downloader.cloud_downloader import is_cloud_download_url, download_cloud_url
from bili_leecher.utility.settings_manager import SettingsManager
from bili_leecher.utility.variables import (
    BOT,
    Transfer,
    MSG,
    Messages,
    BotTimes,
)
from bili_leecher.utility.helper import (
    keyboard,
    sysINFO,
    is_telegram,
    is_torrent_or_magnet,
)
from bili_leecher.utility.handler import cancelTask


async def downloadManager(source, is_ytdl: bool, task_ctx=None):
    BotTimes.task_start = datetime.now()
    logging.info(f"downloadManager starting with {len(source)} Bilibili items.")

    for i, link in enumerate(source):
        if task_ctx and task_ctx.is_cancelled:
            logging.info(f"Task {task_ctx.task_id} cancelled.")
            return

        BOT.CurrentTaskIndex = i + 1
        BOT.ActiveTasks = source[i:]
        if task_ctx:
            task_ctx.batch_index = i + 1
            task_ctx.batch_total = len(source)
        logging.info(f"[Download {i+1}/{len(source)}] Starting Bilibili download: {link}")

        try:
            if is_torrent_or_magnet(link):
                err = "Torrent / Magnet links are strictly prohibited by Google Colab policies."
                await cancelTask(err, task_id=(task_ctx.task_id if task_ctx else None))
                return

            if is_telegram(link):
                await TelegramDownload(link, i + 1, task_ctx)
            elif is_bilibili_url(link):
                await bbdown_download(link, task_ctx)
            elif is_cloud_download_url(link):
                await download_cloud_url(link, task_ctx)
            else:
                # Fallback to yt-dlp if it's another streaming URL
                await YTDL_Status(link, i + 1, task_ctx)

        except Exception as Error:
            logging.error(f"Error while downloading: {Error}")
            await cancelTask(f"Download Error: {str(Error)}", task_id=(task_ctx.task_id if task_ctx else None))
            return


async def calDownSize(sources, task_ctx=None):
    if task_ctx:
        task_ctx.total_size = 0


async def get_d_name(link, task_ctx=None):
    user_id = task_ctx.chat_id if task_ctx else None
    sessdata = SettingsManager.get_sessdata(user_id)
    try:
        if is_bilibili_url(link):
            info = await fetch_bilibili_info(link, sessdata=sessdata)
            name = info.get("title", "Bilibili_Video")
        else:
            name = await get_YT_Name(link)
    except Exception:
        name = "Bilibili_Video"

    Messages.download_name = name
    if task_ctx:
        task_ctx.task_title = name
    return name
