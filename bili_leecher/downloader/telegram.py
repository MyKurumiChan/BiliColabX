# TGColabX - Based on WZML-X & XronTrix10
# Copyright (c) 2024-2026 TGColabX

import os
import logging
from datetime import datetime
from os import path as ospath
from bili_leecher import colab_bot
from bili_leecher.utility.handler import cancelTask
from bili_leecher.utility.variables import Transfer, Paths, Messages, BOT, BotTimes
from bili_leecher.utility.helper import speedETA, getTime, sizeUnit, status_bar


def parse_telegram_link(link: str):
    """
    Parses a Telegram message link to extract (chat_id, message_id).
    Supports:
      - Private supergroups/channels: https://t.me/c/1234567890/123
      - Private topics/threads:       https://t.me/c/1234567890/45/123
      - Public channels:              https://t.me/channel_name/123
      - Public topics/threads:        https://t.me/channel_name/45/123
      - Links with query parameters:  ?single, ?comment=..., etc.
      - Domains: t.me, telegram.me
    """
    clean_link = link.split("?")[0].rstrip("/")
    parts = clean_link.split("/")

    if len(parts) < 5:
        raise ValueError(f"Invalid Telegram link format: {link}")

    try:
        message_id = int(parts[-1])
    except ValueError:
        raise ValueError(f"Unable to extract message ID from link: {link}")

    if "c" in parts:
        c_index = parts.index("c")
        raw_chat_id = parts[c_index + 1]
        chat_id = int(f"-100{raw_chat_id}")
    else:
        chat_id = parts[3]

    return chat_id, message_id


def get_media_info(media, message):
    """
    Safely retrieves the file name and file size for any Telegram media type.
    """
    file_name = getattr(media, "file_name", None)
    file_size = getattr(media, "file_size", 0)

    if not file_name:
        msg_id = getattr(message, "id", "media")
        if getattr(message, "photo", None):
            file_name = f"photo_{msg_id}.jpg"
        elif getattr(message, "video", None):
            file_name = f"video_{msg_id}.mp4"
        elif getattr(message, "audio", None):
            mime = getattr(media, "mime_type", "") or ""
            ext = mime.split("/")[-1] if "/" in mime else "mp3"
            file_name = f"audio_{msg_id}.{ext}"
        elif getattr(message, "voice", None):
            file_name = f"voice_{msg_id}.ogg"
        elif getattr(message, "video_note", None):
            file_name = f"video_note_{msg_id}.mp4"
        elif getattr(message, "animation", None):
            file_name = f"animation_{msg_id}.mp4"
        elif getattr(message, "sticker", None):
            file_name = f"sticker_{msg_id}.webp"
        else:
            file_name = f"file_{msg_id}"

    return file_name, file_size


async def media_Identifier(link):
    """
    Locates the message and extracts the media object from a Telegram link.
    Returns (media, message) on success, or (None, None) on failure.
    """
    try:
        chat_id, message_id = parse_telegram_link(link)
    except Exception as e:
        err = f"Failed to parse Telegram link: {e}"
        logging.error(err)
        return None, None

    message = None
    try:
        message = await colab_bot.get_messages(chat_id, message_id)
    except Exception as e:
        err = f"Error getting Telegram message: {e}. Check if bot has access to chat {chat_id}."
        logging.error(err)
        return None, None

    if message is None or getattr(message, "empty", False):
        err = f"Telegram message {message_id} in {chat_id} not found or inaccessible."
        logging.error(err)
        return None, None

    media = (
        getattr(message, "document", None)
        or getattr(message, "video", None)
        or getattr(message, "audio", None)
        or getattr(message, "photo", None)
        or getattr(message, "voice", None)
        or getattr(message, "video_note", None)
        or getattr(message, "sticker", None)
        or getattr(message, "animation", None)
    )

    if media is None:
        err = f"Telegram message {message_id} does not contain any downloadable media."
        logging.error(err)
        return None, None

    return media, message


async def TelegramDownload(link, num, task_ctx=None):
    media, message = await media_Identifier(link)
    if media is None or message is None:
        return

    name, file_size = get_media_info(media, message)
    custom_name = (task_ctx.options.get("custom_name") if task_ctx else None) or BOT.Options.custom_name
    if custom_name:
        name = custom_name

    down_dir = task_ctx.down_path if task_ctx else Paths.down_path
    os.makedirs(down_dir, exist_ok=True)
    file_path = ospath.join(down_dir, name)

    if task_ctx:
        task_ctx.task_title = name
        task_ctx.engine = "Pyrofork 💥"
        task_ctx.status_state = "Download"
    else:
        Messages.download_name = name
        Messages.status_head = (
            f"<b>📥 DOWNLOADING FROM » </b><i>🔗Link {str(num).zfill(2)}</i>\n\n<code>{name}</code>\n"
        )
        BotTimes.task_start = datetime.now()

    start_t = datetime.now()

    async def download_progress(current, total):
        speed_string, eta, percentage = speedETA(start_t, current, total)
        total_target = (task_ctx.total_size if (task_ctx and task_ctx.total_size > 0) else (Transfer.total_down_size if Transfer.total_down_size > 0 else total))

        if task_ctx:
            task_ctx.speed = speed_string
            task_ctx.percentage = percentage
            task_ctx.eta = getTime(eta)
            task_ctx.done = sizeUnit(current)
            task_ctx.left = sizeUnit(total_target)

        await status_bar(
            down_msg=f"<b>📥 DOWNLOADING » </b><code>{name}</code>\n",
            speed=speed_string,
            percentage=percentage,
            eta=getTime(eta),
            done=sizeUnit(current),
            left=sizeUnit(total_target),
            engine="Pyrofork 💥",
            task_title=name,
            task_ctx=task_ctx,
        )

    await message.download(progress=download_progress, in_memory=False, file_name=file_path)
    actual_size = file_size or (ospath.getsize(file_path) if ospath.exists(file_path) else 0)
    Transfer.down_bytes.append(actual_size)
