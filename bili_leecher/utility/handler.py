# TGColabX - Based on WZML-X & XronTrix10
# Copyright (c) 2024-2026 TGColabX

import os
import shutil
import logging
import pathlib
from asyncio import sleep, get_event_loop
from time import time
from bili_leecher import OWNER, colab_bot
from natsort import natsorted
from datetime import datetime
from os import makedirs, path as ospath
from bili_leecher.uploader.telegram import upload_file
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from bili_leecher.utility.settings_manager import SettingsManager
from bili_leecher.utility.variables import (
    BOT,
    MSG,
    BotTimes,
    Messages,
    Paths,
    Transfer,
)
from bili_leecher.utility.converters import (
    archive,
    extract,
    videoConverter,
    sizeChecker,
)
from bili_leecher.utility.helper import (
    fileType,
    getSize,
    getTime,
    keyboard,
    shortFileName,
    sizeUnit,
    sysINFO,
)


async def Leech(folder_path: str, remove: bool, task_ctx=None):
    global BOT, BotTimes, Messages, Paths, Transfer

    raw_files = [str(p) for p in pathlib.Path(folder_path).glob("**/*") if p.is_file()]
    has_media = any(fileType(f) in ["video", "audio"] for f in raw_files)

    # Filter out helper thumbnails and metadata if media exists so thumbnail is NOT uploaded as a standalone file!
    files = []
    for f in natsorted(raw_files):
        f_low = f.lower()
        if f_low.endswith((".part", ".ytdl", ".info.json", ".description", ".annotations.xml")):
            continue
        if has_media and f_low.endswith((".webp", ".jpg", ".jpeg", ".png", ".vtt", ".srt", ".ass")):
            logging.info(f"Skipping auxiliary thumbnail/subtitle file from separate upload: {f}")
            continue
        files.append(f)

    if not files:
        err_msg = "No files found to leech!"
        logging.error(err_msg)
        if task_ctx:
            await cancelTask(err_msg, task_id=task_ctx.task_id)
        return

    if task_ctx and task_ctx.is_ytdl and not has_media:
        err_msg = "yt-dlp failed to download any video or audio stream!"
        logging.error(err_msg)
        await cancelTask(err_msg, task_id=task_ctx.task_id)
        return

    # Converting Video Files if enabled
    convert_video_opt = (task_ctx.options.get("convert_video") if task_ctx else None) or BOT.Options.convert_video
    for file_path in files:
        if convert_video_opt and fileType(file_path) == "video":
            await videoConverter(file_path)

    total_size = getSize(folder_path)
    if task_ctx:
        task_ctx.total_size = total_size
    else:
        Transfer.total_down_size = total_size

    # Re-evaluate files after conversion
    raw_files = [str(p) for p in pathlib.Path(folder_path).glob("**/*") if p.is_file()]
    has_media = any(fileType(f) in ["video", "audio"] for f in raw_files)
    files = []
    for f in natsorted(raw_files):
        f_low = f.lower()
        if f_low.endswith((".part", ".ytdl", ".info.json", ".description", ".annotations.xml")):
            continue
        if has_media and f_low.endswith((".webp", ".jpg", ".jpeg", ".png", ".vtt", ".srt", ".ass")):
            continue
        files.append(f)

    temp_zpath = task_ctx.temp_zpath if task_ctx else Paths.temp_zpath
    temp_files_dir = task_ctx.temp_files_dir if task_ctx else Paths.temp_files_dir
    makedirs(temp_zpath, exist_ok=True)
    makedirs(temp_files_dir, exist_ok=True)

    for file_path in files:
        if task_ctx and task_ctx.is_cancelled:
            logging.info(f"Task {task_ctx.task_id} cancelled during Leech loop.")
            return

        leech = await sizeChecker(file_path, remove, task_ctx=task_ctx)

        if leech:  # File was split
            if ospath.exists(file_path) and remove:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

            dir_list = natsorted(os.listdir(temp_zpath)) if ospath.exists(temp_zpath) else []
            count = 1

            total_split_size = getSize(temp_zpath)
            if total_split_size > 0:
                if task_ctx:
                    task_ctx.total_size = total_split_size
                else:
                    Transfer.total_down_size = total_split_size

            for dir_path in dir_list:
                if task_ctx and task_ctx.is_cancelled:
                    return
                short_path = ospath.join(temp_zpath, dir_path)
                file_name = ospath.basename(short_path)
                new_path = shortFileName(short_path)
                try:
                    os.rename(short_path, new_path)
                except Exception:
                    new_path = short_path

                if task_ctx:
                    task_ctx.status_text = f"Uploading Part {count}/{len(dir_list)}"
                    task_ctx.task_title = file_name

                await upload_file(new_path, file_name, task_ctx=task_ctx)
                count += 1

                # Clean up uploaded part
                if ospath.exists(new_path):
                    try:
                        os.remove(new_path)
                    except Exception:
                        pass

                # Short breather between consecutive split parts to allow MTProto upload session & Telegram DC buffers to flush
                await sleep(1.5)

        else:
            if not ospath.exists(temp_files_dir):
                makedirs(temp_files_dir, exist_ok=True)

            if not remove:
                file_path = shutil.copy(file_path, temp_files_dir)
            file_name = ospath.basename(file_path)
            new_path = shortFileName(file_path)
            try:
                os.rename(file_path, new_path)
            except Exception:
                new_path = file_path

            if task_ctx:
                task_ctx.status_text = "Uploading..."
                task_ctx.task_title = file_name

            await upload_file(new_path, file_name, task_ctx=task_ctx)

            if remove and ospath.exists(new_path):
                try:
                    os.remove(new_path)
                except Exception:
                    pass

    if remove and ospath.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
        except Exception:
            pass


async def Zip_Handler(down_path: str, is_split: bool, remove: bool, task_ctx=None):
    temp_zpath = task_ctx.temp_zpath if task_ctx else Paths.temp_zpath
    target_msg = task_ctx.status_msg if (task_ctx and task_ctx.status_msg) else MSG.status_msg
    t_name = task_ctx.task_title if task_ctx else Messages.download_name

    status_head = f"<b>🔐 ZIPPING » </b>\n\n<code>{t_name}</code>\n"
    try:
        if target_msg:
            await target_msg.edit_text(
                text=status_head + sysINFO(),
                reply_markup=keyboard(task_ctx),
            )
    except Exception as e2:
        logging.error(f"Problem in ZipHandler: {e2}")

    logging.info("Now ZIPPING the folder...")
    makedirs(temp_zpath, exist_ok=True)

    # Resolve split_size_mb for Zip_Handler
    user_id = getattr(task_ctx, "user_id", None) or (task_ctx.chat_id if task_ctx else 0)
    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}
    from bili_leecher import colab_bot
    bot_has_prem = hasattr(colab_bot, "me") and getattr(colab_bot.me, "is_premium", False)
    task_prem_opt = task_ctx.options.get("is_prem") if task_ctx else None
    if task_prem_opt is not None:
        is_prem = bool(task_prem_opt)
    else:
        is_prem = bot_has_prem

    max_allowed_mb = 3950 if is_prem else 1950
    task_split_mb = task_ctx.options.get("split_size_mb") if task_ctx else 0
    split_sz_mb = min(int(task_split_mb), max_allowed_mb) if task_split_mb else min(int(u_conf.get("split_size_mb", 1950)), max_allowed_mb)

    await archive(down_path, is_split, remove, split_size_mb=split_sz_mb, target_dir=temp_zpath, task_ctx=task_ctx)
    await sleep(2)

    total_zsize = getSize(temp_zpath)
    if task_ctx:
        task_ctx.total_size = total_zsize
    else:
        Transfer.total_down_size = total_zsize

    if remove and ospath.exists(down_path):
        try:
            shutil.rmtree(down_path)
        except Exception:
            pass


async def Unzip_Handler(down_path: str, remove: bool, task_ctx=None):
    temp_unzip = task_ctx.temp_unzip_path if task_ctx else Paths.temp_unzip_path
    target_msg = task_ctx.status_msg if (task_ctx and task_ctx.status_msg) else MSG.status_msg
    t_name = task_ctx.task_title if task_ctx else Messages.download_name

    status_head = f"\n<b>📂 EXTRACTING » </b>\n\n<code>{t_name}</code>\n"
    try:
        if target_msg:
            await target_msg.edit_text(
                text=status_head + "\n⏳ __Starting extraction...__" + sysINFO(),
                reply_markup=keyboard(task_ctx),
            )
    except Exception:
        pass

    makedirs(temp_unzip, exist_ok=True)
    filenames = [str(p) for p in pathlib.Path(down_path).glob("**/*") if p.is_file()]
    for f in natsorted(filenames):
        short_path = ospath.join(down_path, f)
        filename = ospath.basename(f).lower()
        _, ext = ospath.splitext(filename)
        try:
            if ospath.exists(short_path):
                if ext in [".7z", ".gz", ".zip", ".rar", ".001", ".tar", ".z01"]:
                    await extract(short_path, remove, temp_unzip_path=temp_unzip, task_ctx=task_ctx)
                else:
                    shutil.copy(short_path, temp_unzip)
        except Exception as e5:
            logging.error(f"UZLeech Launcher Exception: {e5}")

    if remove and ospath.exists(down_path):
        try:
            shutil.rmtree(down_path)
        except Exception:
            pass


async def cancelTask(Reason: str, task_id: str = None, cancel_all: bool = False):
    """
    Cancels a specific running task by task_id, or cancels all tasks if cancel_all=True.
    """
    from bili_leecher.utility.task_manager import ACTIVE_TASKS

    if cancel_all:
        logging.info("Cancelling all active and queued tasks...")
        for tid, ctx in list(ACTIVE_TASKS.items()):
            ctx.is_cancelled = True
            if ctx.asyncio_task and not ctx.asyncio_task.done():
                ctx.asyncio_task.cancel()
            if ospath.exists(ctx.work_path):
                try:
                    shutil.rmtree(ctx.work_path)
                except Exception:
                    pass
            try:
                if ctx.status_msg:
                    await ctx.status_msg.edit_text(f"🛑 <b>Task #{tid} Cancelled:</b> <i>{Reason}</i>")
            except Exception:
                pass
        ACTIVE_TASKS.clear()
        BOT.Queue.clear()
        BOT.State.task_going = False
        return

    if task_id and task_id in ACTIVE_TASKS:
        ctx = ACTIVE_TASKS.pop(task_id)
        ctx.is_cancelled = True
        if ctx.asyncio_task and not ctx.asyncio_task.done():
            ctx.asyncio_task.cancel()
        if ospath.exists(ctx.work_path):
            try:
                shutil.rmtree(ctx.work_path)
            except Exception:
                pass
        try:
            if ctx.status_msg:
                await ctx.status_msg.edit_text(f"🛑 <b>Task #{task_id} Cancelled:</b> <i>{Reason}</i>")
        except Exception:
            pass
        return

    # Fallback: Cancel most recent or single active task
    if ACTIVE_TASKS:
        tid, ctx = next(iter(ACTIVE_TASKS.items()))
        del ACTIVE_TASKS[tid]
        ctx.is_cancelled = True
        if ctx.asyncio_task and not ctx.asyncio_task.done():
            ctx.asyncio_task.cancel()
        if ospath.exists(ctx.work_path):
            try:
                shutil.rmtree(ctx.work_path)
            except Exception:
                pass
        try:
            if ctx.status_msg:
                await ctx.status_msg.edit_text(f"🛑 <b>Task #{tid} Cancelled:</b> <i>{Reason}</i>")
        except Exception:
            pass
    else:
        BOT.State.task_going = False


async def SendLogs(is_leech: bool, task_ctx=None):
    global Transfer, Messages

    if task_ctx:
        raw_size = sum(task_ctx.up_bytes) if is_leech else task_ctx.total_size
        if raw_size == 0:
            logging.warning(f"SendLogs skipped for Task #{task_ctx.task_id}: 0 bytes processed.")
            return

        size = sizeUnit(raw_size)
        t_name = task_ctx.task_title or "Completed Task"
        elapsed = getTime(max(1, (datetime.now() - task_ctx.start_time).seconds))
        mode_str = task_ctx.mode.upper()
        target_chat = task_ctx.chat_id or OWNER
        target_msg = task_ctx.status_msg
    else:
        raw_size = sum(Transfer.up_bytes) if is_leech else Transfer.total_down_size
        if raw_size == 0:
            logging.warning("SendLogs skipped for global task: 0 bytes processed.")
            return

        size = sizeUnit(raw_size)
        t_name = Messages.download_name
        elapsed = getTime((datetime.now() - BotTimes.start_time).seconds)
        mode_str = BOT.Mode.mode.upper()
        target_chat = BOT.ChatID or OWNER
        target_msg = MSG.status_msg

    last_text = (
        f"<b>#{mode_str}_COMPLETE 🔥</b>\n\n"
        f"<blockquote>╭ <b>📛 Name   :</b> <code>{t_name}</code>\n"
        f"┊ <b>📦 Size   :</b> <code>{size}</code>\n"
        f"┊ <b>⚙️ Engine :</b> <i>BiliColabX (BBDown Core)</i>\n"
        f"╰ <b>🍃 Time   :</b> <code>{elapsed}</code></blockquote>\n"
        f"<blockquote><i>Powered by BiliColabX & BBDown</i></blockquote>"
    )

    close_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Close", callback_data="uset_close")]])
    sent_or_edited = None
    try:
        if target_msg:
            sent_or_edited = await target_msg.edit_text(text=last_text, reply_markup=close_markup, disable_web_page_preview=True)
        else:
            sent_or_edited = await colab_bot.send_message(chat_id=target_chat, text=last_text, reply_markup=close_markup, disable_web_page_preview=True)
    except Exception as e:
        logging.warning(f"Failed to edit status message at completion: {e}")

    # Check auto-disappear preference (user or bot level)
    try:
        from bili_leecher.utility.settings_manager import SettingsManager
        user_id = task_ctx.chat_id if task_ctx else (BOT.ChatID or OWNER)
        u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}
        b_conf = SettingsManager.get_bot_settings()
        if u_conf.get("auto_delete_status", False) or b_conf.get("auto_delete_status", False):
            msg_to_del = sent_or_edited or target_msg
            if msg_to_del:
                async def _auto_disappear(m):
                    try:
                        await sleep(30)
                        await m.delete()
                    except Exception:
                        pass
                get_event_loop().create_task(_auto_disappear(msg_to_del))
    except Exception as ade:
        logging.warning(f"Auto-disappear schedule error: {ade}")
