# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Dedicated Task Pipeline & Concurrency Manager

import os
import shutil
import logging
from time import time
from datetime import datetime
from asyncio import sleep, get_event_loop
from os import makedirs, path as ospath
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bili_leecher import OWNER, colab_bot, DUMP_ID
from bili_leecher.downloader.manager import calDownSize, get_d_name, downloadManager
from bili_leecher.uploader.gdrive_uploader import upload_to_google_drive, is_drive_mounted
from bili_leecher.uploader.cloud_uploader import (
    upload_path_to_gofile,
    upload_path_to_pixeldrain,
    upload_path_via_rclone,
)
from bili_leecher.utility.settings_manager import SettingsManager
from bili_leecher.utility.helper import (
    getSize,
    sizeUnit,
    keyboard,
    sysINFO,
    is_torrent_or_magnet,
    automated_video_merge,
    render_multi_status,
)
from bili_leecher.utility.handler import (
    Leech,
    Unzip_Handler,
    Zip_Handler,
    SendLogs,
    cancelTask,
)
from bili_leecher.utility.variables import (
    BOT,
    MSG,
    BotTimes,
    Messages,
    Paths,
    Transfer,
)

ACTIVE_TASKS = {}       # task_id -> TaskContext
CHAT_STATUS_MSGS = {}   # chat_id -> Message (Live unified status message per chat)


class TaskContext:
    def __init__(self, task_id: str, chat_id: int, user_name: str, mode: str, mode_type: str, is_ytdl: bool, links: list, options: dict, user_id: int = 0):
        self.task_id = task_id
        self.chat_id = chat_id
        self.user_id = user_id or (chat_id if chat_id > 0 else 0)
        self.user_name = user_name
        self.mode = mode               # "leech" or "mirror" (drive)
        self.mode_type = mode_type     # "normal", "zip", "unzip"
        self.is_ytdl = is_ytdl
        self.links = list(links)
        self.options = dict(options)
        self.delivered_to = "chat"

        # Isolated directory tree for this task
        self.work_path = ospath.join(Paths.WORK_PATH, f"task_{task_id}")
        self.down_path = ospath.join(self.work_path, "Downloads")
        self.temp_zpath = ospath.join(self.work_path, "Leeched_Files")
        self.temp_unzip_path = ospath.join(self.work_path, "Unzipped_Files")
        self.temp_files_dir = ospath.join(self.work_path, "leech_temp")
        self.thumbnail_ytdl = ospath.join(self.work_path, "ytdl_thumbnails")
        self.samples_dir = ospath.join(self.work_path, "samples")
        self.screenshots_dir = ospath.join(self.work_path, "screenshots")

        # Live status tracking
        clean_name = ospath.basename(str(links[0]).split("?")[0].rstrip("/")) if links else "Bilibili Task..."
        self.task_title = options.get("custom_name") or clean_name
        self.status_state = "Download"

        has_vip = bool(SettingsManager.get_sessdata(self.user_id))
        self.engine = "BBDown 📺 (🍪 VIP)" if has_vip else "BBDown 📺"

        self.speed = "0 B/s"
        self.percentage = 0.0
        self.eta = "N/A"
        self.done = "0 B"
        self.left = "N/A"
        self.total_size = 0
        self.up_bytes = []
        self.start_time = datetime.now()
        self.last_update = 0
        self.is_cancelled = False
        self.status_msg = None
        self.sent_msg = None
        self.asyncio_task = None

        # Multi-part & batch live tracking
        self.active_parts = {}         # {part_num: {"name": str, "pct": float, "speed": str, "done": str, "left": str, "eta": str, "state": str}}
        self.completed_parts_count = 0
        self.total_parts_count = 1
        self.batch_index = 1
        self.batch_total = len(self.links) if self.links else 1


async def task_starter(message, text):
    try:
        await message.delete()
    except Exception:
        pass
    try:
        src_request_msg = await message.reply_text(text)
    except Exception:
        src_request_msg = await colab_bot.send_message(chat_id=message.chat.id, text=text)
    return src_request_msg


async def dispatch_task(mode_type: str, mode: str, is_ytdl: bool, links: list, user_name: str, chat_id: int, options: dict, message=None, user_id: int = 0):
    bot_conf = SettingsManager.get_bot_settings()
    max_parallel = bot_conf.get("max_parallel_tasks", 4)

    if not links:
        return

    if not user_id and message and message.from_user:
        user_id = message.from_user.id
    if not user_id:
        user_id = chat_id if chat_id > 0 else 0

    tasks_to_start = []
    for link in links:
        t_id = f"{int(time() * 1000) % 1000000:06d}"
        ctx = TaskContext(
            task_id=t_id,
            chat_id=chat_id,
            user_name=user_name,
            mode=mode,
            mode_type=mode_type,
            is_ytdl=is_ytdl,
            links=[link],
            options=options,
            user_id=user_id,
        )

        can_start = (max_parallel == 0) or (len(ACTIVE_TASKS) < max_parallel)
        if can_start:
            ACTIVE_TASKS[t_id] = ctx
            tasks_to_start.append(ctx)
            BOT.State.task_going = True
        else:
            BOT.Queue.append(ctx)
            pos = len(BOT.Queue)
            if message:
                try:
                    await message.reply_text(f"⏳ <b>Task Queued!</b> <code>#{t_id}</code> (Position: #{pos})")
                except Exception:
                    pass

    if message:
        try:
            await message.delete()
        except Exception:
            pass

    old_stat = CHAT_STATUS_MSGS.get(chat_id)
    multi_txt = render_multi_status(ACTIVE_TASKS)
    new_stat_msg = None

    if old_stat:
        try:
            await old_stat.edit_text(multi_txt, reply_markup=keyboard(), disable_web_page_preview=True)
            new_stat_msg = old_stat
        except Exception:
            new_stat_msg = None

    if not new_stat_msg and ACTIVE_TASKS:
        try:
            new_stat_msg = await colab_bot.send_message(
                chat_id=chat_id,
                text=multi_txt,
                reply_markup=keyboard(),
                disable_web_page_preview=True,
            )
        except Exception as e:
            logging.warning(f"Error posting status card: {e}")

    if new_stat_msg:
        CHAT_STATUS_MSGS[chat_id] = new_stat_msg
        for t_c in ACTIVE_TASKS.values():
            if t_c.chat_id == chat_id:
                t_c.status_msg = new_stat_msg

    loop = get_event_loop()
    for ctx in tasks_to_start:
        if new_stat_msg:
            ctx.status_msg = new_stat_msg
        ctx.asyncio_task = loop.create_task(run_task_pipeline(ctx))


async def run_task_pipeline(task_ctx: TaskContext):
    try:
        makedirs(task_ctx.work_path, exist_ok=True)
        makedirs(task_ctx.down_path, exist_ok=True)
        makedirs(task_ctx.thumbnail_ytdl, exist_ok=True)

        target_chat = task_ctx.chat_id or OWNER
        if target_chat in CHAT_STATUS_MSGS:
            task_ctx.status_msg = CHAT_STATUS_MSGS[target_chat]

        is_zip = task_ctx.mode_type == "zip"
        is_unzip = task_ctx.mode_type == "unzip"

        if task_ctx.mode == "leech":
            await Do_Leech_Task(task_ctx, is_zip, is_unzip)
        else:
            await Do_Mirror_Task(task_ctx, is_zip, is_unzip)

    except Exception as e:
        logging.error(f"Error in Task #{task_ctx.task_id}: {e}")
        try:
            if task_ctx.status_msg:
                await task_ctx.status_msg.edit_text(f"⚠️ <b>Task #{task_ctx.task_id} Error:</b> <code>{e}</code>")
        except Exception:
            pass

    finally:
        if task_ctx.task_id in ACTIVE_TASKS:
            del ACTIVE_TASKS[task_ctx.task_id]

        if ospath.exists(task_ctx.work_path):
            try:
                shutil.rmtree(task_ctx.work_path)
            except Exception:
                pass

        if task_ctx.chat_id in CHAT_STATUS_MSGS:
            try:
                if ACTIVE_TASKS:
                    multi_txt = render_multi_status(ACTIVE_TASKS)
                    await CHAT_STATUS_MSGS[task_ctx.chat_id].edit_text(multi_txt, reply_markup=keyboard(), disable_web_page_preview=True)
                else:
                    try:
                        await CHAT_STATUS_MSGS[task_ctx.chat_id].delete()
                    except Exception:
                        pass
                    del CHAT_STATUS_MSGS[task_ctx.chat_id]
            except Exception:
                pass

        if BOT.Queue:
            next_ctx = BOT.Queue.pop(0)
            t_id = next_ctx.task_id
            ACTIVE_TASKS[t_id] = next_ctx
            loop = get_event_loop()
            next_ctx.asyncio_task = loop.create_task(run_task_pipeline(next_ctx))

        BOT.State.task_going = len(ACTIVE_TASKS) > 0


async def Do_Leech_Task(task_ctx: TaskContext, is_zip: bool, is_unzip: bool):
    logging.info(f"Starting Bilibili download for Task #{task_ctx.task_id}...")
    await downloadManager(task_ctx.links, task_ctx.is_ytdl, task_ctx)

    if task_ctx.is_cancelled:
        return

    task_ctx.total_size = getSize(task_ctx.down_path)
    if task_ctx.total_size == 0:
        err_msg = task_ctx.error or "Download failed: 0 bytes received from Bilibili."
        await cancelTask(err_msg, task_id=task_ctx.task_id)
        return

    # Merge multi-part if requested
    if task_ctx.options.get("is_merge"):
        try:
            task_ctx.status_state = "Merging"
            task_ctx.engine = "FFmpeg 🎬"
            merged = automated_video_merge(task_ctx.down_path)
            if merged:
                task_ctx.task_title = ospath.basename(merged)
                task_ctx.total_size = getSize(task_ctx.down_path)
        except Exception as me:
            logging.error(f"Merge error: {me}")

    upload_target = (task_ctx.options.get("upload_target") or "telegram").lower()
    is_gf = bool(task_ctx.options.get("is_gf")) or bool(task_ctx.options.get("gofile")) or (upload_target in ["gofile", "gf"])
    is_pd = bool(task_ctx.options.get("is_pd")) or bool(task_ctx.options.get("pixeldrain")) or (upload_target in ["pixeldrain", "pd"])
    rc_target = task_ctx.options.get("rc_target") or task_ctx.options.get("rclone_remote") or ""
    custom_df = task_ctx.options.get("custom_df") or task_ctx.options.get("drive_folder") or ""
    is_drive = upload_target in ["drive", "gdrive", "googledrive", "all"]

    if is_zip:
        await Zip_Handler(task_ctx.down_path, True, True, task_ctx)
        upload_source = task_ctx.temp_zpath
    elif is_unzip:
        await Unzip_Handler(task_ctx.down_path, True, task_ctx)
        upload_source = task_ctx.temp_unzip_path
    else:
        upload_source = task_ctx.down_path

    # 1. Google Drive upload if requested
    if is_drive and not task_ctx.is_cancelled:
        drive_res = await upload_to_google_drive(upload_source, user_id=task_ctx.chat_id, task_ctx=task_ctx, custom_folder=custom_df)
        if drive_res:
            res_txt = "<b>📁 Bilibili Media Uploaded to Google Drive!</b>\n\n"
            for item in drive_res:
                res_txt += f"• <code>{item['name']}</code> ({sizeUnit(item['size'])})\n  📍 <i>{item.get('path', item.get('status'))}</i>\n"
            try:
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt)
            except Exception:
                pass

    # 2. Gofile Upload
    if is_gf and not task_ctx.is_cancelled:
        try:
            gf_res = await upload_path_to_gofile(upload_source, user_id=task_ctx.chat_id, task_ctx=task_ctx)
            if gf_res:
                res_txt = "<b>🚀 Uploaded to Gofile!</b>\n\n"
                for item in gf_res:
                    res_txt += f"• <b>{item['name']}</b> ({sizeUnit(item['size'])})\n  🔗 <a href='{item['url']}'>{item['url']}</a>\n\n"
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt, disable_web_page_preview=True)
        except Exception as gfe:
            logging.error(f"Gofile upload error: {gfe}")
            await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=f"⚠️ <b>Gofile Upload Error:</b> <code>{gfe}</code>")

    # 3. PixelDrain Upload
    if is_pd and not task_ctx.is_cancelled:
        try:
            pd_res = await upload_path_to_pixeldrain(upload_source, user_id=task_ctx.chat_id, task_ctx=task_ctx)
            if pd_res:
                res_txt = "<b>⚡ Uploaded to PixelDrain!</b>\n\n"
                for item in pd_res:
                    res_txt += f"• <b>{item['name']}</b> ({sizeUnit(item['size'])})\n  🔗 <a href='{item['url']}'>{item['url']}</a>\n\n"
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt, disable_web_page_preview=True)
        except Exception as pde:
            logging.error(f"PixelDrain upload error: {pde}")
            await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=f"⚠️ <b>PixelDrain Upload Error:</b> <code>{pde}</code>")

    # 4. Rclone Mirror
    if rc_target and not task_ctx.is_cancelled:
        try:
            rc_res = await upload_path_via_rclone(upload_source, rc_target, task_ctx=task_ctx)
            if rc_res:
                res_txt = f"<b>☁️ Mirrored to Rclone Remote!</b>\n\n• Target: <code>{rc_target}</code>\n• Total: <code>{sizeUnit(rc_res['size'])}</code>\n"
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt)
        except Exception as rce:
            logging.error(f"Rclone transfer error: {rce}")
            await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=f"⚠️ <b>Rclone Mirror Error:</b> <code>{rce}</code>")

    # 5. Telegram MTProto upload (default unless exclusively sent to another service)
    only_cloud = (is_gf or is_pd or rc_target or is_drive) and (upload_target not in ["telegram", "tg", "all"])
    if not only_cloud and not task_ctx.is_cancelled:
        task_ctx.status_state = "Upload"
        task_ctx.engine = "DzGram ⚡"
        await Leech(upload_source, True, task_ctx)
        await SendLogs(True, task_ctx)


async def Do_Mirror_Task(task_ctx: TaskContext, is_zip: bool, is_unzip: bool):
    """Directly downloads and mirrors Bilibili video into Google Drive or other clouds."""
    logging.info(f"Starting Bilibili mirror for Task #{task_ctx.task_id}...")
    await downloadManager(task_ctx.links, task_ctx.is_ytdl, task_ctx)

    if task_ctx.is_cancelled:
        return

    task_ctx.total_size = getSize(task_ctx.down_path)
    if task_ctx.total_size == 0:
        await cancelTask("Download produced 0 bytes.", task_id=task_ctx.task_id)
        return

    # Merge multi-part if requested
    if task_ctx.options.get("is_merge"):
        try:
            task_ctx.status_state = "Merging"
            task_ctx.engine = "FFmpeg 🎬"
            merged = automated_video_merge(task_ctx.down_path)
            if merged:
                task_ctx.task_title = ospath.basename(merged)
                task_ctx.total_size = getSize(task_ctx.down_path)
        except Exception as me:
            logging.error(f"Merge error: {me}")

    if is_zip:
        await Zip_Handler(task_ctx.down_path, True, True, task_ctx)
        upload_source = task_ctx.temp_zpath
    elif is_unzip:
        await Unzip_Handler(task_ctx.down_path, True, task_ctx)
        upload_source = task_ctx.temp_unzip_path
    else:
        upload_source = task_ctx.down_path

    custom_df = task_ctx.options.get("custom_df") or task_ctx.options.get("drive_folder") or ""
    upload_target = (task_ctx.options.get("upload_target") or "googledrive").lower()
    is_gf = bool(task_ctx.options.get("is_gf")) or bool(task_ctx.options.get("gofile")) or (upload_target in ["gofile", "gf"])
    is_pd = bool(task_ctx.options.get("is_pd")) or bool(task_ctx.options.get("pixeldrain")) or (upload_target in ["pixeldrain", "pd"])
    rc_target = task_ctx.options.get("rc_target") or task_ctx.options.get("rclone_remote") or ""

    # Gofile mirror if requested with -gf
    if is_gf and not task_ctx.is_cancelled:
        try:
            gf_res = await upload_path_to_gofile(upload_source, user_id=task_ctx.chat_id, task_ctx=task_ctx)
            if gf_res:
                res_txt = "<b>🚀 Mirrored to Gofile!</b>\n\n"
                for item in gf_res:
                    res_txt += f"• <b>{item['name']}</b> ({sizeUnit(item['size'])})\n  🔗 <a href='{item['url']}'>{item['url']}</a>\n\n"
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt, disable_web_page_preview=True)
        except Exception as gfe:
            logging.error(f"Gofile mirror error: {gfe}")

    # PixelDrain mirror if requested with -pd
    if is_pd and not task_ctx.is_cancelled:
        try:
            pd_res = await upload_path_to_pixeldrain(upload_source, user_id=task_ctx.chat_id, task_ctx=task_ctx)
            if pd_res:
                res_txt = "<b>⚡ Mirrored to PixelDrain!</b>\n\n"
                for item in pd_res:
                    res_txt += f"• <b>{item['name']}</b> ({sizeUnit(item['size'])})\n  🔗 <a href='{item['url']}'>{item['url']}</a>\n\n"
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt, disable_web_page_preview=True)
        except Exception as pde:
            logging.error(f"PixelDrain mirror error: {pde}")

    # Rclone mirror if requested with -rc
    if rc_target and not task_ctx.is_cancelled:
        try:
            rc_res = await upload_path_via_rclone(upload_source, rc_target, task_ctx=task_ctx)
            if rc_res:
                res_txt = f"<b>☁️ Mirrored to Rclone Remote!</b>\n\n• Target: <code>{rc_target}</code>\n• Total: <code>{sizeUnit(rc_res['size'])}</code>\n"
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt)
        except Exception as rce:
            logging.error(f"Rclone mirror error: {rce}")

    # Google Drive Mirror (default for /mirror or if no alternative exclusively requested)
    if not (is_gf or is_pd or rc_target) or task_ctx.options.get("upload_target") in ["drive", "gdrive", "googledrive", "all"]:
        drive_res = await upload_to_google_drive(upload_source, user_id=task_ctx.chat_id, task_ctx=task_ctx, custom_folder=custom_df)
        if drive_res and not task_ctx.is_cancelled:
            res_txt = "<b>📁 Bilibili Media Mirrored to Google Drive!</b>\n\n"
            for item in drive_res:
                loc = item.get("path") or item.get("link") or item.get("status")
                link = item.get("link")
                if link:
                    res_txt += f"• <b>{item['name']}</b> ({sizeUnit(item['size'])})\n  🔗 <a href='{link}'>Open in Google Drive</a>\n  📍 <code>{loc}</code>\n\n"
                else:
                    res_txt += f"• <b>{item['name']}</b> ({sizeUnit(item['size'])})\n  📍 <code>{loc}</code>\n\n"
            try:
                await colab_bot.send_message(chat_id=(task_ctx.chat_id or OWNER), text=res_txt, disable_web_page_preview=True)
            except Exception:
                pass

    await SendLogs(False, task_ctx)
