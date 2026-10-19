# TGColabX - Based on WZML-X & XronTrix10
# Copyright (c) 2024-2026 TGColabX

import re
import html
import logging
from PIL import Image
from asyncio import sleep
from os import path as ospath
from datetime import datetime
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaPhoto
from bili_leecher import colab_bot
from bili_leecher.utility.variables import BOT, Transfer, BotTimes, Messages, MSG, Paths
from bili_leecher.utility.settings_manager import SettingsManager
from bili_leecher.utility.helper import (
    sizeUnit,
    fileType,
    getTime,
    status_bar,
    thumbMaintainer,
    videoExtFix,
    generate_sample_video,
    generate_screenshots,
)


def format_caption(real_name: str, task_ctx=None) -> str:
    user_id = task_ctx.chat_id if task_ctx else 0
    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}

    # Check custom caption
    custom_cap = (task_ctx.options.get("custom_caption") if task_ctx else None) or u_conf.get("custom_caption") or BOT.Options.custom_caption
    if custom_cap:
        return custom_cap

    safe_name = html.escape(real_name)
    prefix_val = u_conf.get("prefix") if u_conf else BOT.Setting.prefix
    suffix_val = u_conf.get("suffix") if u_conf else BOT.Setting.suffix

    prefix = html.escape(prefix_val).strip() if prefix_val else ""
    suffix = html.escape(suffix_val).strip() if suffix_val else ""

    parts = [p for p in (prefix, safe_name, suffix) if p]
    caption_text = " ".join(parts)

    style = (u_conf.get("caption_style") if u_conf else BOT.Setting.caption or "Monospace").lower()
    if style in ["b", "bold"]:
        return f"<b>{caption_text}</b>"
    elif style in ["i", "italic"]:
        return f"<i>{caption_text}</i>"
    elif style in ["u", "underlined", "underline"]:
        return f"<u>{caption_text}</u>"
    elif style in ["code", "monospace"]:
        return f"<code>{caption_text}</code>"
    else:
        return caption_text


async def upload_file(file_path, real_name, task_ctx=None):
    global Transfer, MSG
    start_t = datetime.now()
    if not task_ctx:
        BotTimes.task_start = start_t

    caption = format_caption(real_name, task_ctx)
    type_ = fileType(file_path)

    user_id = getattr(task_ctx, "user_id", None) or (task_ctx.chat_id if task_ctx and task_ctx.chat_id > 0 else 0)
    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}

    # Stream upload decision
    if task_ctx and "stream_upload" in task_ctx.options and task_ctx.options["stream_upload"] is not None:
        stream_mode = task_ctx.options["stream_upload"]
    elif u_conf:
        stream_mode = (u_conf.get("stream_upload") == "Media")
    else:
        stream_mode = BOT.Options.stream_upload

    f_type = type_ if stream_mode else "document"

    # Destination Routing:
    # 1. Custom dump channel set by user
    custom_dump = u_conf.get("dump_channel", "").strip() if u_conf else ""
    target_chat_id = None
    if custom_dump:
        try:
            target_chat_id = int(custom_dump)
        except ValueError:
            target_chat_id = custom_dump
        if task_ctx:
            task_ctx.delivered_to = "dump"

    # 2. If no custom dump channel: route to user's Bot DM when triggered from a group
    if not target_chat_id:
        send_dm = u_conf.get("send_to_dm", True) if u_conf else True
        if send_dm and user_id and user_id > 0 and task_ctx and task_ctx.chat_id < 0:
            target_chat_id = user_id
            task_ctx.delivered_to = "dm"
        elif task_ctx:
            target_chat_id = task_ctx.chat_id
            task_ctx.delivered_to = "chat"
        else:
            target_chat_id = MSG.sent_msg.chat.id if (MSG.sent_msg and hasattr(MSG.sent_msg, "chat")) else (BOT.ChatID or 0)

    logging.info(f"Uploading {real_name} to Telegram as {f_type} (Chat: {target_chat_id})...")

    # Detect if file is part of a split volume
    is_split_part = bool(re.search(r"\.part\d+|\.\d{3}$", real_name, re.IGNORECASE))

    # Sample video (Only for non-split standalone videos to avoid Colab CPU stall on 2GB splits)
    sample_dur = (task_ctx.options.get("sample_video") if task_ctx else 0) or u_conf.get("sample_duration", 0)
    if not is_split_part and type_ == "video" and sample_dur > 0:
        try:
            logging.info(f"Generating sample video ({sample_dur}s)...")
            sample_path = generate_sample_video(file_path, sample_dur)
            if sample_path and ospath.exists(sample_path):
                sample_caption = f"🎬 <b>[SAMPLE]</b> <code>{real_name}</code>"
                sample_thmb, sample_sec = thumbMaintainer(sample_path, task_ctx=task_ctx, user_id=user_id)
                await colab_bot.send_video(
                    chat_id=target_chat_id,
                    video=sample_path,
                    caption=sample_caption,
                    thumb=sample_thmb if (sample_thmb and ospath.exists(sample_thmb)) else None,
                    duration=int(sample_sec),
                    supports_streaming=True,
                )
                logging.info("Sample video uploaded successfully.")
        except Exception as se:
            logging.error(f"Sample video upload error: {se}")

    # Screenshots (Only for non-split standalone videos)
    shots_count = (task_ctx.options.get("screenshots") if task_ctx else 0) or u_conf.get("screenshot_count", 0)
    if not is_split_part and type_ == "video" and shots_count > 0:
        try:
            logging.info(f"Generating {shots_count} screenshots...")
            shots = generate_screenshots(file_path, shots_count)
            if shots:
                media_group = [InputMediaPhoto(media=sh) for sh in shots[:10]]
                if media_group:
                    media_group[0].caption = f"📸 <b>[SCREENSHOTS]</b> <code>{real_name}</code>"
                    await colab_bot.send_media_group(chat_id=target_chat_id, media=media_group)
                    logging.info("Screenshots album uploaded successfully.")
        except Exception as se:
            logging.error(f"Screenshots upload error: {se}")

    # Progress hook
    async def progress_bar(current, total):
        upload_speed = 4 * 1024 * 1024
        elapsed = (datetime.now() - start_t).seconds
        if current > 0 and elapsed > 0:
            upload_speed = current / elapsed

        if task_ctx:
            total_target = task_ctx.total_size if task_ctx.total_size > 0 else total
            already_uploaded = sum(task_ctx.up_bytes)
            total_processed = current + already_uploaded

            eta = (total_target - total_processed) / upload_speed if upload_speed > 0 else 0
            pct = min(100.0, max(0.0, (total_processed / total_target * 100) if total_target > 0 else 0))

            task_ctx.speed = f"{sizeUnit(upload_speed)}/s"
            task_ctx.percentage = pct
            task_ctx.eta = getTime(max(0, eta))
            task_ctx.done = sizeUnit(total_processed)
            task_ctx.left = sizeUnit(total_target)
            task_ctx.status_state = "Upload"
            task_ctx.engine = "DzGram ⚡"

            await status_bar(
                down_msg=f"<b>📤 UPLOADING » </b><code>{real_name}</code>\n",
                speed=task_ctx.speed,
                percentage=pct,
                eta=task_ctx.eta,
                done=task_ctx.done,
                left=task_ctx.left,
                engine="DzGram ⚡",
                task_ctx=task_ctx,
            )
        else:
            total_target = Transfer.total_down_size if Transfer.total_down_size > 0 else total
            already_uploaded = sum(Transfer.up_bytes)
            total_processed = current + already_uploaded

            eta = (total_target - total_processed) / upload_speed if upload_speed > 0 else 0
            pct = min(100.0, max(0.0, (total_processed / total_target * 100) if total_target > 0 else 0))

            await status_bar(
                down_msg=Messages.status_head,
                speed=f"{sizeUnit(upload_speed)}/s",
                percentage=pct,
                eta=getTime(max(0, eta)),
                done=sizeUnit(total_processed),
                left=sizeUnit(total_target),
                engine="DzGram ⚡",
            )

    try:
        sent_item = None
        thmb_path = None
        seconds = 0
        width, height = 0, 0

        if f_type == "video":
            file_path = videoExtFix(file_path)

            # Reuse cached thumbnail across split parts instead of running ffmpeg frame extraction again
            if task_ctx and getattr(task_ctx, "cached_thumb", None) and ospath.exists(task_ctx.cached_thumb):
                thmb_path = task_ctx.cached_thumb
                seconds = getattr(task_ctx, "cached_duration", 0)
            else:
                thmb_path, seconds = thumbMaintainer(file_path, task_ctx=task_ctx, user_id=user_id)
                if task_ctx and thmb_path and ospath.exists(thmb_path):
                    task_ctx.cached_thumb = thmb_path
                    task_ctx.cached_duration = seconds

            if thmb_path and ospath.exists(thmb_path):
                try:
                    with Image.open(thmb_path) as img:
                        width, height = img.size
                except Exception as img_err:
                    logging.warning(f"Error reading thumbnail dimensions: {img_err}")
                    thmb_path = None
        else:
            # Check user custom thumbnail or global thumbnail for documents & audio
            if user_id:
                u_thumb = SettingsManager.get_user_thumb_path(user_id)
                if ospath.exists(u_thumb):
                    thmb_path = u_thumb
            if not thmb_path and ospath.exists(Paths.THMB_PATH):
                thmb_path = Paths.THMB_PATH

        async def _do_send(dest_chat):
            if f_type == "video":
                return await colab_bot.send_video(
                    chat_id=dest_chat,
                    video=file_path,
                    supports_streaming=True,
                    width=width,
                    height=height,
                    caption=caption,
                    thumb=thmb_path,
                    duration=int(seconds),
                    progress=progress_bar,
                )
            elif f_type == "audio":
                return await colab_bot.send_audio(
                    chat_id=dest_chat,
                    audio=file_path,
                    caption=caption,
                    thumb=thmb_path if (thmb_path and ospath.exists(thmb_path)) else None,
                    progress=progress_bar,
                )
            elif f_type == "document":
                return await colab_bot.send_document(
                    chat_id=dest_chat,
                    document=file_path,
                    caption=caption,
                    thumb=thmb_path if (thmb_path and ospath.exists(thmb_path)) else None,
                    progress=progress_bar,
                )
            elif f_type == "photo":
                return await colab_bot.send_photo(
                    chat_id=dest_chat,
                    photo=file_path,
                    caption=caption,
                    progress=progress_bar,
                )
            return None

        try:
            sent_item = await _do_send(target_chat_id)
        except Exception as dest_err:
            if task_ctx and target_chat_id != task_ctx.chat_id:
                logging.warning(f"Failed to deliver to {target_chat_id} ({dest_err}), falling back to task chat {task_ctx.chat_id}...")
                target_chat_id = task_ctx.chat_id
                task_ctx.delivered_to = "chat"
                sent_item = await _do_send(target_chat_id)
            else:
                raise dest_err

        if task_ctx:
            task_ctx.sent_msg = sent_item
            if ospath.exists(file_path):
                task_ctx.up_bytes.append(ospath.getsize(file_path))
        else:
            MSG.sent_msg = sent_item
            Transfer.sent_file.append(sent_item)
            Transfer.sent_file_names.append(real_name)
            if ospath.exists(file_path):
                Transfer.up_bytes.append(ospath.getsize(file_path))

        # Backup forward to global DUMP_ID if set and different from target
        from bili_leecher import DUMP_ID
        if DUMP_ID and str(DUMP_ID).strip() not in ["0", ""] and sent_item:
            try:
                if str(DUMP_ID) != str(target_chat_id):
                    await sent_item.copy(chat_id=int(DUMP_ID))
            except Exception as d_err:
                logging.debug(f"Could not forward to DUMP_ID: {d_err}")

    except FloodWait as e:
        logging.warning(f"FloodWait: Waiting {e.value}s before retrying upload...")
        await sleep(e.value)
        await upload_file(file_path, real_name, task_ctx)
    except Exception as e:
        logging.error(f"Error when uploading {real_name}: {e}")
        # Fallback to document
        if f_type != "document":
            logging.info("Attempting fallback upload as generic document...")
            try:
                fallback_sent = await colab_bot.send_document(
                    chat_id=target_chat_id,
                    document=file_path,
                    caption=caption,
                    progress=progress_bar,
                )
                if task_ctx:
                    task_ctx.sent_msg = fallback_sent
                    if ospath.exists(file_path):
                        task_ctx.up_bytes.append(ospath.getsize(file_path))
                else:
                    MSG.sent_msg = fallback_sent
                    Transfer.sent_file.append(fallback_sent)
                    Transfer.sent_file_names.append(real_name)
                return
            except Exception as doc_err:
                logging.error(f"Fallback document upload also failed: {doc_err}")
        raise e
