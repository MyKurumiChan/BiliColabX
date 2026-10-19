# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import os
import re
import sys
import json
import random
import logging
import platform
import subprocess
import shutil
import psutil
from time import time
from datetime import datetime
from io import BytesIO
import asyncio
from asyncio import sleep, get_event_loop
from pyrogram import filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

from bili_leecher import colab_bot, OWNER, bot_start_time
from bili_leecher.utility.handler import cancelTask
from bili_leecher.utility.variables import BOT, MSG, BotTimes, Paths, Messages
from bili_leecher.utility.task_manager import (
    task_starter,
    dispatch_task,
    ACTIVE_TASKS,
    CHAT_STATUS_MSGS,
    TaskContext,
)
from bili_leecher.utility.settings_manager import (
    SettingsManager,
    get_user_settings_text,
    get_user_settings_markup,
    get_bili_quality_markup,
    get_cookie_menu_markup,
    get_thumb_menu_markup,
    get_split_menu_markup,
    get_archive_menu_markup,
    get_dump_menu_markup,
    get_captions_menu_markup,
    get_concurrency_markup,
    get_engine_menu_markup,
    get_bot_settings_text,
    get_bot_settings_markup,
    get_cloud_settings_text,
    get_cloud_settings_markup,
)
from bili_leecher.utility.helper import (
    isLink,
    is_bilibili_url,
    download_thumbnail_from_url,
    sizeUnit,
    getTime,
    is_torrent_or_magnet,
    sysINFO,
    keyboard,
    quality_buttons,
    render_multi_status,
)
from bili_leecher.downloader.bilibili_helper import (
    normalize_bilibili_url,
    fetch_bilibili_info,
    parse_range_spec,
)
from bili_leecher.uploader.gdrive_uploader import (
    get_drive_browser_text,
    get_drive_browser_markup,
    create_drive_folder,
    DRIVE_PATH_CACHE,
    get_drive_base_root,
)
from bili_leecher.uploader.cloud_uploader import (
    list_rclone_remotes,
    get_rclone_config_path,
)

USER_INPUT_STATES = {}  # user_id -> state string (e.g. "set_sessdata", "set_prefix")
PENDING_BILI_LINKS = {} # user_id -> url string awaiting quality selection


def parse_bili_flags_and_links(input_text: str, reply_message=None):
    """
    Parses Bilibili URLs, ranges, engines, and flags from command text or replied message.
    Supports single links, multi-links (separated by newline, \\n, or spaces), and rich flags.
    """
    raw_text = (input_text or "").replace(r"\n", "\n").replace("\\n", "\n").strip()
    all_tokens = raw_text.split()
    if all_tokens and all_tokens[0].startswith("/"):
        tokens = all_tokens[1:]
    else:
        tokens = all_tokens

    links = []
    custom_name = ""
    stream_upload = None
    mode_type = "normal"
    password = ""
    is_split = None
    is_merge = False
    bili_quality = None
    range_spec = None
    download_danmaku = False
    download_sub = True
    audio_only = False
    sample_video = 0
    screenshots = 0
    custom_caption = ""
    thumb_url = ""
    upload_target = None
    engine = None
    concurrent_videos = None
    upos_host = None
    custom_df = ""
    is_gf = False
    is_pd = False
    rc_target = ""
    archive_format = None
    split_size_mb = 0
    is_prem = None

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        if tok == "-n" and i + 1 < len(tokens):
            custom_name = tokens[i + 1]
            i += 2
        elif tok in ["-df", "-dir", "-folder"] and i + 1 < len(tokens):
            custom_df = tokens[i + 1]
            if not upload_target:
                upload_target = "googledrive"
            i += 2
        elif tok in ["-gf", "-gofile"]:
            is_gf = True
            upload_target = "gofile"
            i += 1
        elif tok in ["-pd", "-pixeldrain"]:
            is_pd = True
            upload_target = "pixeldrain"
            i += 1
        elif tok in ["-rc", "-rclone"] and i + 1 < len(tokens):
            rc_target = tokens[i + 1]
            upload_target = "rclone"
            i += 2
        elif tok in ["-up", "-target"] and i + 1 < len(tokens):
            upload_target = tokens[i + 1].lower()
            i += 2
        elif tok in ["-drive", "-gd", "-gdrive"]:
            upload_target = "googledrive"
            i += 1
        elif tok in ["-tg", "-telegram"]:
            upload_target = "telegram"
            i += 1
        elif tok == "-all":
            upload_target = "all"
            i += 1
        elif tok == "-doc":
            stream_upload = False
            i += 1
        elif tok == "-med":
            stream_upload = True
            i += 1
        elif tok in ["-z", "-zip"]:
            mode_type = "zip"
            archive_format = "zip"
            i += 1
        elif tok in ["-7z", "-7zip"]:
            mode_type = "zip"
            archive_format = "7z"
            i += 1
        elif tok in ["-rar"]:
            mode_type = "zip"
            archive_format = "rar"
            i += 1
        elif tok in ["-tar"]:
            mode_type = "zip"
            archive_format = "tar"
            i += 1
        elif tok in ["-tgz", "-targz", "-tar.gz"]:
            mode_type = "zip"
            archive_format = "tar.gz"
            i += 1
        elif tok in ["-arc", "-archive", "-fmt"] and i + 1 < len(tokens):
            mode_type = "zip"
            archive_format = tokens[i + 1].lower().strip().lstrip(".")
            i += 2
        elif tok in ["-split", "-sp"] and i + 1 < len(tokens):
            val = tokens[i + 1].lower().strip()
            if "gb" in val or "g" in val:
                num = float(re.sub(r"[^\d.]", "", val) or 2)
                split_size_mb = 3950 if num >= 3.5 else int(num * 1024)
            elif "mb" in val or "m" in val:
                split_size_mb = int(re.sub(r"[^\d]", "", val) or 1950)
            elif val.isdigit():
                split_size_mb = int(val)
            i += 2
        elif tok in ["-prem", "-premium"]:
            is_prem = True
            i += 1
        elif tok in ["-free"]:
            is_prem = False
            i += 1
        elif tok == "-e":
            mode_type = "unzip"
            i += 1
        elif tok == "-p" and i + 1 < len(tokens):
            val = tokens[i + 1]
            if re.match(r"^\d+(-\d+)?$", val) or val.isdigit():
                range_spec = val
            else:
                password = val
            i += 2
        elif tok in ["-range", "-part", "-parts"] and i + 1 < len(tokens):
            range_spec = tokens[i + 1]
            i += 2
        elif tok == "-start" and i + 1 < len(tokens):
            start_v = tokens[i + 1]
            end_v = start_v
            if i + 2 < len(tokens) and tokens[i + 2] == "-end" and i + 3 < len(tokens):
                end_v = tokens[i + 3]
                i += 4
            else:
                i += 2
            range_spec = f"{start_v}-{end_v}"
        elif tok in ["-dd", "-danmaku"]:
            download_danmaku = True
            i += 1
        elif tok in ["-sub", "-subs"]:
            download_sub = True
            i += 1
        elif tok in ["-nosub", "-nosubs"]:
            download_sub = False
            i += 1
        elif tok in ["-audio", "-mp3"]:
            audio_only = True
            bili_quality = "Audio"
            i += 1
        elif tok in ["-m", "-merge"]:
            is_merge = True
            i += 1
        elif tok in ["-tv"]:
            engine = "BBDown - TV"
            i += 1
        elif tok in ["-app"]:
            engine = "BBDown - APP"
            i += 1
        elif tok in ["-web"]:
            engine = "BBDown - WEB"
            i += 1
        elif tok in ["-ytdl", "-yt-dlp"]:
            engine = "yt-dlp"
            i += 1
        elif tok in ["-engine"] and i + 1 < len(tokens):
            engine = tokens[i + 1]
            i += 2
        elif tok in ["-conc", "-concurrency", "-parallel"] and i + 1 < len(tokens):
            try:
                concurrent_videos = int(tokens[i + 1])
            except Exception:
                pass
            i += 2
        elif tok in ["-upos"] and i + 1 < len(tokens):
            upos_host = tokens[i + 1]
            i += 2
        elif tok in ["-8k", "-4k", "-1080p+", "-1080p", "-720p", "-480p"]:
            bili_quality = tok[1:].upper()
            i += 1
        elif tok in ["-ss", "-sample"] and i + 1 < len(tokens) and tokens[i + 1].isdigit():
            sample_video = int(tokens[i + 1])
            i += 2
        elif tok in ["-shots", "-sshot"] and i + 1 < len(tokens) and tokens[i + 1].isdigit():
            screenshots = int(tokens[i + 1])
            i += 2
        elif tok == "-c" and i + 1 < len(tokens):
            cap_parts = []
            i += 1
            while i < len(tokens) and not tokens[i].startswith("-"):
                cap_parts.append(tokens[i])
                i += 1
            custom_caption = " ".join(cap_parts)
        elif tok == "-thumb" and i + 1 < len(tokens) and tokens[i + 1].startswith(("http://", "https://")):
            thumb_url = tokens[i + 1]
            i += 2
        elif tok in ["-s", "-q"] and i + 1 < len(tokens):
            bili_quality = tokens[i + 1].upper()
            i += 2
        elif re.match(r"^\d+-\d+$", tok):
            range_spec = tok
            i += 1
        elif tok.startswith(("http://", "https://", "b23.tv", "bilibili.com")):
            links.append(tok)
            i += 1
        else:
            embedded = re.findall(r"https?://[^\s<>'\"]+", tok)
            if embedded:
                links.extend(embedded)
            i += 1

    if reply_message:
        source_text = (reply_message.text or "") + " " + (reply_message.caption or "")
        if source_text.strip():
            found_urls = re.findall(r"https?://[^\s<>'\"]+", source_text)
            if found_urls:
                links.extend(found_urls)

    clean_links = []
    seen = set()
    for lk in links:
        if lk not in seen:
            seen.add(lk)
            clean_links.append(lk)

    options = {
        "custom_name": custom_name,
        "stream_upload": stream_upload,
        "mode_type": mode_type,
        "is_split": is_split,
        "is_merge": is_merge,
        "bili_quality": bili_quality,
        "range": range_spec,
        "download_danmaku": download_danmaku,
        "download_sub": download_sub,
        "audio_only": audio_only,
        "sample_video": sample_video,
        "screenshots": screenshots,
        "custom_caption": custom_caption,
        "thumb_url": thumb_url,
        "zip_pswd": password,
        "unzip_pswd": password,
        "upload_target": upload_target,
        "engine": engine,
        "concurrent_videos": concurrent_videos,
        "upos_host": upos_host,
        "custom_df": custom_df,
        "drive_folder": custom_df,
        "is_gf": is_gf,
        "is_pd": is_pd,
        "rc_target": rc_target,
        "archive_format": archive_format,
        "split_size_mb": split_size_mb,
        "is_prem": is_prem,
    }

    return clean_links, options


def check_access(message):
    u_id = message.from_user.id if message.from_user else message.chat.id
    chat_type = str(message.chat.type).lower()
    is_pm = ("private" in chat_type) or (message.chat.id > 0)
    is_owner = (OWNER == 0) or (u_id == OWNER)
    is_permitted = is_owner or SettingsManager.is_user_permitted(u_id, OWNER)

    if is_pm and not is_permitted:
        return False, (
            "⚠️ <b>Access Restricted: Personal Chat (PM)</b>\n\n"
            "<i>Free users can use BiliColabX inside authorized groups!</i>\n"
            "<blockquote>Send your Bilibili links in our group. Permitted users can use bot in personal chat.</blockquote>"
        )

    if not is_pm and not is_owner and not SettingsManager.is_chat_authorized(message.chat.id):
        return False, (
            "⚠️ <b>This group is not authorized to use BiliColabX!</b>\n"
            "<i>Please ask the bot owner to authorize this group.</i>"
        )

    return True, ""


# ==================== Bot Command Handlers ====================

def get_welcome_text(user_id: int, user_name: str) -> str:
    is_owner = (OWNER == 0) or (user_id == OWNER)
    is_perm = is_owner or SettingsManager.is_user_permitted(user_id, OWNER)
    user_tier = "👑 Owner / Admin" if is_owner else ("🌟 Permitted (VIP Personal Access)" if is_perm else "👤 Free User")

    u_conf = SettingsManager.get_user_settings(user_id)
    split_size = f"{u_conf.get('split_size_mb', 1950)} MB"
    has_vip = bool(SettingsManager.get_sessdata(user_id))
    vip_status = "✅ SESSDATA Active (VIP Unlocked)" if has_vip else "⚠️ Anonymous (Free 1080P/720P)"
    default_q = u_conf.get("bili_quality", "1080P")
    drive_mounted = os.path.exists("/content/drive/MyDrive") or os.path.exists(Paths.MOUNTED_DRIVE)
    drive_stat = "✅ Mounted (Colab MyDrive)" if drive_mounted else "⚠️ Not Mounted"

    return (
        f"👋 <b>Welcome to BiliColabX, {user_name}! 📺🚀</b>\n\n"
        f"<i>An ultra-fast Bilibili Leecher & Multi-Cloud Mirror Bot on Google Colab.</i>\n"
        f"<i>Powered by BBDown Engine, DzGram MTProto, Aria2c & Rust WarpCrypto</i>\n\n"
        f"╭⌬ <b>User       :</b> <b>{user_name}</b> (<code>{user_id}</code>)\n"
        f"├⌬ <b>Access Tier:</b> <i>{user_tier}</i>\n"
        f"├⌬ <b>VIP Cookie :</b> <i>{vip_status}</i>\n"
        f"├⌬ <b>Resolution :</b> <code>{default_q}</code> | Split: <code>{split_size}</code>\n"
        f"├⌬ <b>Google Drive:</b> <i>{drive_stat}</i>\n"
        f"╰⌬ <b>Active Engine:</b> <code>BBDown (WEB/TV/APP) + yt-dlp</code>\n\n"
        f"<blockquote><b>🌟 How to get started:</b>\n"
        f"• Paste any Bilibili URL directly (e.g. <code>https://www.bilibili.com/video/BV...</code>)\n"
        f"• Tap <b>📖 Help & Guide</b> below for all commands, flags, and examples!</blockquote>"
    )


def get_welcome_markup(user_id: int) -> InlineKeyboardMarkup:
    repo_url = os.environ.get("REPO_URL", "https://github.com/MyKurumiChan/BiliColabX")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help & Guide", callback_data="open_help"),
            InlineKeyboardButton("⭐ GitHub Repo", url=repo_url),
        ],
        [
            InlineKeyboardButton("👤 User Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("🤖 Bot Settings", callback_data="open_bset"),
        ],
        [
            InlineKeyboardButton("📊 Server Stats", callback_data="cmd_stats"),
            InlineKeyboardButton("⚡ Speedtest", callback_data="bset_speedtest"),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_help_text() -> str:
    return (
        "<b>📖 BiliColabX — Complete Usage Guide 📺🚀</b>\n\n"
        "<b>📥 1. Basic Downloading & Leeching:</b>\n"
        "• <b>Direct Paste:</b> Paste any Bilibili URL into chat to choose resolution.\n"
        "• <code>/bili &lt;url&gt;</code> (or <code>/b</code>, <code>/leech</code>) : Download & leech to Telegram.\n"
        "• <code>/mirror &lt;url&gt;</code> (or <code>/m</code>, <code>/drive</code>) : Download & save to Google Drive.\n\n"
        "<b>📑 2. Multi-Part (分P) & Episode Ranges:</b>\n"
        "• Specific range: <code>/bili https://b23.tv/xxxx 1-10</code>\n"
        "• Flag range: <code>/bili https://b23.tv/xxxx -range 1-20</code>\n"
        "• Batch multi-link: Paste multiple links separated by newlines.\n\n"
        "<b>🚩 3. Popular Flags:</b>\n"
        "• <b>Cloud Destination:</b> <code>-df &lt;folder&gt;</code> (Google Drive subfolder)\n"
        "• <b>Multi-Cloud:</b> <code>-gf</code> (Gofile), <code>-pd</code> (PixelDrain), <code>-rc &lt;remote:path&gt;</code> (Rclone)\n"
        "• <b>Quality:</b> <code>-q 8k|4k|1080p+|1080p|720p|480p</code> or shortcut <code>-4k</code>\n"
        "• <b>Lossless Audio:</b> <code>-audio</code> or <code>-mp3</code> (FLAC / 320k)\n"
        "• <b>Danmaku & Subs:</b> <code>-dd</code> (bullet comments .ass), <code>-sub</code> (subtitles)\n"
        "• <b>Archive Formats:</b> <code>-zip</code>, <code>-7z</code>, <code>-rar</code>, <code>-tar</code>, <code>-tgz</code> (or <code>-arc &lt;fmt&gt;</code>)\n"
        "• <b>Multi-Volume Split:</b> <code>-split 500m|1g|1950m|3950m</code> (or <code>-sp &lt;size&gt;</code>)\n"
        "• <b>Telegram Tier:</b> <code>-prem</code> (4GB limit) / <code>-free</code> (2GB limit)\n"
        "• <b>Merge Videos:</b> <code>-m</code> (merge multi-part video into 1 file)\n"
        "• <b>Concurrency:</b> <code>-conc &lt;1-8&gt;</code> (parallel download streams)\n"
        "• <b>Engines:</b> <code>-web</code> (BBDown Web), <code>-tv</code> (BBDown TV), <code>-app</code> (APP), <code>-ytdl</code> (yt-dlp)\n\n"
        "<b>⚙️ 4. Quick Utilities:</b>\n"
        "• <code>/dfolder</code> : Interactive Google Drive folder browser\n"
        "• <code>/cookies</code> : Upload your Bilibili <code>cookies.txt</code>\n"
        "• <code>/sessdata &lt;token&gt;</code> : Set VIP SESSDATA directly\n"
        "• <code>/stats</code> : Colab server metrics & free disk/RAM\n"
        "• <code>/speedtest</code> : Test Colab network speed\n"
        "• <code>/status</code> : Live single-window download dashboard\n"
        "• <code>/usetting</code> : Open personal user settings\n"
        "• <code>/cancel &lt;id&gt;</code> or <code>/cancelall</code> : Cancel active tasks"
    )


def get_help_markup(user_id: int = 0) -> InlineKeyboardMarkup:
    repo_url = os.environ.get("REPO_URL", "https://github.com/MyKurumiChan/BiliColabX")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Back to Welcome", callback_data="open_start"),
            InlineKeyboardButton("⭐ GitHub Repo", url=repo_url),
        ],
        [
            InlineKeyboardButton("👤 User Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("⚡ Speedtest", callback_data="bset_speedtest"),
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


@colab_bot.on_message(filters.command(["start"]))
async def start_cmd(client, message):
    try:
        await message.delete()
    except Exception:
        pass
    u_id = message.from_user.id if message.from_user else message.chat.id
    u_name = message.from_user.first_name if message.from_user else "User"
    txt = get_welcome_text(u_id, u_name)
    markup = get_welcome_markup(u_id)
    try:
        await message.reply_text(txt, reply_markup=markup)
    except Exception:
        await colab_bot.send_message(chat_id=message.chat.id, text=txt, reply_markup=markup)


@colab_bot.on_message(filters.command(["help", "h"]))
async def help_cmd(client, message):
    try:
        await message.delete()
    except Exception:
        pass
    u_id = message.from_user.id if message.from_user else message.chat.id
    txt = get_help_text()
    markup = get_help_markup(u_id)
    try:
        await message.reply_text(txt, reply_markup=markup)
    except Exception:
        await colab_bot.send_message(chat_id=message.chat.id, text=txt, reply_markup=markup)


@colab_bot.on_message(filters.command(["bili", "b", "leech", "l", "tupload"]))
async def bilibili_leech(client, message):
    allowed, reason = check_access(message)
    if not allowed:
        await message.reply_text(reason)
        return

    links, options = parse_bili_flags_and_links(message.text, message.reply_to_message)
    user_name = message.from_user.first_name if message.from_user else "User"

    for lk in links:
        if is_torrent_or_magnet(lk):
            await message.reply_text("⚠️ Torrent / Magnet links are strictly prohibited by Google Colab policies.")
            return

    if links:
        if options.get("thumb_url"):
            download_thumbnail_from_url(options["thumb_url"], user_id=message.chat.id)

        await dispatch_task(
            mode_type=options.get("mode_type", "normal"),
            mode="leech",
            is_ytdl=False,
            links=links,
            user_name=user_name,
            chat_id=message.chat.id,
            options=options,
            message=message,
        )
    else:
        text = (
            "<b>⚡ Send Bilibili Video / Series Link to Leech 📺»</b>\n\n"
            "Supported Features & Flags:\n"
            "• <code>/bili &lt;url&gt;</code> (Auto-detects multi-part & single videos)\n"
            "• <code>/bili &lt;url&gt; 1-10</code> (Download parts 1 to 10)\n"
            "• <code>/bili &lt;url1&gt; \\n &lt;url2&gt;</code> (Batch download multiple links)\n"
            "• Flags: <code>-q 4k</code>, <code>-audio</code>, <code>-dd</code> (danmaku), <code>-tv</code>, <code>-app</code>, <code>-ytdl</code>, <code>-conc 4</code>\n"
            "• Mirror: <code>/mirror &lt;url&gt;</code> (Upload to Google Drive)"
        )
        await task_starter(message, text)


@colab_bot.on_message(filters.command(["binfo", "info", "bi"]))
async def bilibili_info_command(client, message):
    allowed, reason = check_access(message)
    if not allowed:
        await message.reply_text(reason)
        return

    (links, *_) = parse_bili_flags_and_links(message.text, message.reply_to_message)
    if not links:
        await message.reply_text("⚠️ Please provide a Bilibili link: <code>/binfo https://b23.tv/...</code>")
        return

    target_url = links[0]
    u_id = message.from_user.id if message.from_user else message.chat.id
    sessdata = SettingsManager.get_sessdata(u_id)

    status_msg = await message.reply_text("🔍 <b>Probing Bilibili metadata... Please wait</b>")

    info = await fetch_bilibili_info(target_url, sessdata=sessdata)
    title = info.get("title", "Unknown Title")
    uploader = info.get("owner", "Unknown")
    duration = getTime(info.get("duration", 0))
    parts_count = info.get("part_count", 1)
    pic = info.get("pic", "")

    desc_text = (
        f"<b>📺 Bilibili Video Inspector</b>\n\n"
        f"🏷 <b>Title:</b> <code>{title}</code>\n"
        f"👤 <b>Uploader:</b> <b>{uploader}</b>\n"
        f"⏱ <b>Duration:</b> <code>{duration}</code>\n"
        f"📑 <b>Total Parts:</b> <code>{parts_count} part(s)</code>\n"
        f"🍪 <b>VIP Status:</b> <i>{'✅ Active' if sessdata else '❌ Anonymous'}</i>\n"
    )

    if parts_count > 1:
        desc_text += f"\n<b>Episodes / Multi-Part Preview:</b>\n"
        for p in info.get("parts", [])[:5]:
            desc_text += f"• P{p['page']}: <code>{p['part'][:30]}</code> ({getTime(p['duration'])})\n"
        if parts_count > 5:
            desc_text += f"<i>... and {parts_count - 5} more parts available!</i>\n"

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Download All", callback_data=f"bili_dl_{u_id}_1080P"),
            InlineKeyboardButton("🎵 Download Audio", callback_data=f"bili_dl_{u_id}_Audio"),
        ],
        [
            InlineKeyboardButton("📺 Choose Quality", callback_data=f"bili_chooseq_{u_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ]
    ])

    try:
        await status_msg.delete()
    except Exception:
        pass

    PENDING_BILI_LINKS[u_id] = target_url

    if pic:
        try:
            await colab_bot.send_photo(chat_id=message.chat.id, photo=pic, caption=desc_text, reply_markup=markup)
            return
        except Exception:
            pass

    await colab_bot.send_message(chat_id=message.chat.id, text=desc_text, reply_markup=markup)


@colab_bot.on_message(filters.command(["mirror", "m", "drive", "gdrive", "gdupload"]))
async def bilibili_mirror(client, message):
    allowed, reason = check_access(message)
    if not allowed:
        await message.reply_text(reason)
        return

    links, options = parse_bili_flags_and_links(message.text, message.reply_to_message)
    options["upload_target"] = options.get("upload_target") or "googledrive"
    user_name = message.from_user.first_name if message.from_user else "User"

    for lk in links:
        if is_torrent_or_magnet(lk):
            await message.reply_text("⚠️ Torrent / Magnet links are strictly prohibited by Google Colab policies.")
            return

    if links:
        await dispatch_task(
            mode_type=options.get("mode_type", "normal"),
            mode="mirror",
            is_ytdl=False,
            links=links,
            user_name=user_name,
            chat_id=message.chat.id,
            options=options,
            message=message,
        )
    else:
        text = (
            "<b>⚡ Send Bilibili Link to Mirror to Drive / Cloud 🔗»</b>\n\n"
            "<code>/mirror https://b23.tv/xxxx</code>\n"
            "<code>/mirror https://b23.tv/xxxx -gofile</code>"
        )
        await task_starter(message, text)


@colab_bot.on_message(filters.command(["cookies", "cookie"]))
async def cookie_handler(client, message):
    u_id = message.from_user.id if message.from_user else message.chat.id
    doc = message.document or (message.reply_to_message.document if message.reply_to_message else None)

    if doc and doc.file_name.lower().endswith((".txt", ".cookie", ".cookies")):
        down_dir = os.path.join(Paths.WORK_PATH, "user_cookies")
        os.makedirs(down_dir, exist_ok=True)
        tmp_path = os.path.join(down_dir, f"temp_{u_id}.txt")
        await message.download(file_name=tmp_path)
        SettingsManager.save_user_cookies(u_id, tmp_path)
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        sess = SettingsManager.get_sessdata(u_id)
        if sess:
            await message.reply_text(
                f"✅ <b>Bilibili Cookies Uploaded Successfully!</b>\n\n"
                f"🔑 <b>Extracted SESSDATA:</b> <code>{sess[:10]}...{sess[-6:]}</code>\n"
                f"🌟 VIP features (1080P+, 4K, 8K & member anime) are now unlocked for your account!"
            )
        else:
            await message.reply_text("✅ Cookies file saved. Note: No explicit SESSDATA token found in file.")
    else:
        sess = SettingsManager.get_sessdata(u_id)
        sess_disp = f"<code>{sess[:10]}...{sess[-6:]}</code>" if sess else "❌ None configured"
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🍪 Set SESSDATA", callback_data=f"uset_cookies_{u_id}"),
                InlineKeyboardButton("❌ Close", callback_data="uset_close"),
            ]
        ])
        await message.reply_text(
            f"<b>🍪 Bilibili Cookie Manager</b>\n\n"
            f"• <b>Current SESSDATA:</b> {sess_disp}\n\n"
            f"<b>To configure:</b>\n"
            f"1. Upload your <code>cookies.txt</code> file here with <code>/cookies</code> in caption.\n"
            f"2. Or set token directly: <code>/sessdata your_token_here</code>\n"
            f"3. To remove: <code>/delcookies</code>",
            reply_markup=markup
        )


@colab_bot.on_message(filters.command(["sessdata", "setcookie"]))
async def sessdata_direct_cmd(client, message):
    u_id = message.from_user.id if message.from_user else message.chat.id
    tokens = message.text.split(maxsplit=1)
    if len(tokens) > 1:
        raw_token = tokens[1].strip()
        sess = SettingsManager.extract_sessdata(raw_token)
        if sess:
            SettingsManager.set_user_setting(u_id, "sessdata", sess)
            await message.reply_text(
                f"✅ <b>SESSDATA Token Set!</b>\n"
                f"<code>{sess[:10]}...{sess[-6:]}</code>\n"
                f"<i>VIP downloads unlocked for your tasks.</i>"
            )
        else:
            await message.reply_text("⚠️ Could not parse a valid SESSDATA token. Please check format.")
    else:
        await message.reply_text("⚠️ Usage: <code>/sessdata your_bilibili_sessdata_token</code>")


@colab_bot.on_message(filters.command(["delcookies", "delcookie", "clearcookies"]))
async def delcookies_cmd(client, message):
    u_id = message.from_user.id if message.from_user else message.chat.id
    SettingsManager.delete_user_cookies(u_id)
    await message.reply_text("🗑 <b>Your Bilibili cookies and SESSDATA have been cleared.</b>")


@colab_bot.on_message(filters.command(["rclone", "rc"]))
async def rclone_cmd(client, message):
    from bili_leecher.uploader.cloud_uploader import list_rclone_remotes, get_rclone_config_path
    remotes = await list_rclone_remotes()
    conf_p = get_rclone_config_path()
    if remotes:
        rem_list = "\n".join([f"• <code>{r}:</code>" for r in remotes])
        txt = (
            f"<b>☁️ Configured Rclone Remotes ({len(remotes)})</b>\n\n"
            f"{rem_list}\n\n"
            f"<b>Usage Example:</b>\n"
            f"<code>/mirror &lt;url&gt; -rc {remotes[0]}:Folder</code>\n\n"
            f"<i>Config: <code>{conf_p}</code></i>"
        )
    else:
        txt = (
            f"<b>☁️ Rclone Remotes</b>\n\n"
            f"⚠️ No remotes detected in <code>{conf_p}</code>.\n\n"
            f"<i>Upload your <code>rclone.conf</code> file directly into chat to activate all your cloud remotes!</i>"
        )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("☁️ Cloud Settings", callback_data=f"uset_cloud_{message.from_user.id if message.from_user else message.chat.id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ]
    ])
    await message.reply_text(txt, reply_markup=markup)


@colab_bot.on_message(filters.document)
async def document_upload_listener(client, message):
    doc = message.document
    if not doc or not doc.file_name:
        return

    f_low = doc.file_name.lower()
    u_id = message.from_user.id if message.from_user else message.chat.id

    # 1. Rclone config upload
    if f_low == "rclone.conf" or f_low.endswith(".conf") and "rclone" in f_low:
        from bili_leecher.uploader.cloud_uploader import get_rclone_config_path
        target_conf = get_rclone_config_path()
        target_dir = os.path.dirname(target_conf)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        await message.download(file_name=target_conf)

        # Also save a copy in /content/rclone.conf and root
        for fallback_p in ["/content/rclone.conf", "/root/.config/rclone/rclone.conf", os.path.join(Paths.WORK_PATH, "rclone.conf")]:
            try:
                os.makedirs(os.path.dirname(fallback_p), exist_ok=True)
                shutil.copy2(target_conf, fallback_p)
            except Exception:
                pass

        from bili_leecher.uploader.cloud_uploader import list_rclone_remotes
        remotes = await list_rclone_remotes()
        rem_str = ", ".join([f"<code>{r}</code>" for r in remotes]) if remotes else "None parsed"
        await message.reply_text(
            f"✅ <b>rclone.conf uploaded & activated!</b>\n\n"
            f"📁 <b>Saved to:</b> <code>{target_conf}</code>\n"
            f"☁️ <b>Detected Remotes:</b> {rem_str}\n\n"
            f"<i>Now you can mirror with: <code>/mirror &lt;url&gt; -rc {remotes[0] if remotes else 'remote'}:Folder</code></i>"
        )
        return

    # 2. Cookies.txt upload
    if f_low.endswith((".txt", ".cookie", ".cookies")) and ("cookie" in f_low or "bilibili" in f_low):
        down_dir = os.path.join(Paths.WORK_PATH, "user_cookies")
        os.makedirs(down_dir, exist_ok=True)
        tmp_path = os.path.join(down_dir, f"temp_{u_id}.txt")
        await message.download(file_name=tmp_path)
        SettingsManager.save_user_cookies(u_id, tmp_path)
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        sess = SettingsManager.get_sessdata(u_id)
        if sess:
            await message.reply_text(
                f"✅ <b>Bilibili Cookies Uploaded Successfully!</b>\n\n"
                f"🔑 <b>Extracted SESSDATA:</b> <code>{sess[:10]}...{sess[-6:]}</code>\n"
                f"🌟 VIP features unlocked for your account!"
            )
        else:
            await message.reply_text("✅ Cookies file saved. Note: No explicit SESSDATA token found in file.")
        return


@colab_bot.on_message(filters.command(["status", "s"]))
async def live_status_cmd(client, message):
    try:
        await message.delete()
    except Exception:
        pass
    text = render_multi_status(ACTIVE_TASKS)
    await message.reply_text(text, reply_markup=keyboard(), disable_web_page_preview=True)


@colab_bot.on_message(filters.command(["usetting", "usersettings"]))
async def usetting_cmd(client, message):
    try:
        await message.delete()
    except Exception:
        pass
    u_id = message.from_user.id if message.from_user else message.chat.id
    text = get_user_settings_text(u_id)
    markup = get_user_settings_markup(u_id)
    await message.reply_text(text, reply_markup=markup)


@colab_bot.on_message(filters.command(["bsetting", "botsettings"]))
async def bsetting_cmd(client, message):
    try:
        await message.delete()
    except Exception:
        pass
    u_id = message.from_user.id if message.from_user else message.chat.id
    if OWNER != 0 and u_id != OWNER:
        await message.reply_text("⚠️ This command is restricted to the bot owner.")
        return
    text = get_bot_settings_text()
    markup = get_bot_settings_markup()
    await message.reply_text(text, reply_markup=markup)


@colab_bot.on_message(filters.command(["cancel", "c"]))
async def cancel_task_cmd(client, message):
    parts = message.text.split()
    t_id = parts[1].replace("cancel_", "") if len(parts) > 1 else None
    await cancelTask("Cancelled by user request.", task_id=t_id)
    await message.reply_text(f"🛑 <b>Task #{t_id or 'current'} cancellation triggered.</b>")


@colab_bot.on_message(filters.command(["cancelall", "call"]))
async def cancelall_cmd(client, message):
    count = len(ACTIVE_TASKS)
    for tid in list(ACTIVE_TASKS.keys()):
        await cancelTask("Cancelled by /cancelall.", task_id=tid)
    BOT.Queue.clear()
    await message.reply_text(f"🛑 <b>All {count} active tasks and pending queues cancelled.</b>")


def get_server_metrics_text() -> str:
    cpu = psutil.cpu_percent(interval=0.2)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime = getTime(time() - bot_start_time)

    # Google Drive storage check if mounted
    drive_line = ""
    if os.path.exists("/content/drive/MyDrive"):
        try:
            d_stat = psutil.disk_usage("/content/drive/MyDrive")
            drive_line = (
                f"\n📁 <b>Google Drive Storage:</b>\n"
                f"├ <b>Used:</b> <code>{sizeUnit(d_stat.used)}</code> ({d_stat.percent}%)\n"
                f"├ <b>Free:</b> <code>{sizeUnit(d_stat.free)}</code>\n"
                f"╰ <b>Total:</b> <code>{sizeUnit(d_stat.total)}</code>\n"
            )
        except Exception:
            pass

    return (
        f"<b>📊 Colab Server Metrics</b>\n\n"
        f"⏱ <b>Bot Uptime:</b> <code>{uptime}</code>\n"
        f"🧠 <b>CPU Load:</b> <code>{cpu}%</code> ({psutil.cpu_count(logical=True)} vCPUs)\n\n"
        f"💾 <b>RAM Memory:</b>\n"
        f"├ <b>Used:</b> <code>{sizeUnit(ram.used)}</code> ({ram.percent}%)\n"
        f"├ <b>Free:</b> <code>{sizeUnit(ram.available)}</code>\n"
        f"╰ <b>Total:</b> <code>{sizeUnit(ram.total)}</code>\n\n"
        f"💿 <b>Colab Local Disk (/):</b>\n"
        f"├ <b>Used:</b> <code>{sizeUnit(disk.used)}</code> ({disk.percent}%)\n"
        f"├ <b>Free:</b> <code>{sizeUnit(disk.free)}</code> (Available for DL)\n"
        f"╰ <b>Total:</b> <code>{sizeUnit(disk.total)}</code>\n"
        f"{drive_line}\n"
        f"🚀 <b>Active Tasks:</b> <code>{len(ACTIVE_TASKS)} parallel</code>"
    )


@colab_bot.on_message(filters.command(["stats", "st", "server"]))
async def stats_cmd(client, message):
    text = get_server_metrics_text()
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚡ Speedtest", callback_data="bset_speedtest"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ]
    ])
    await message.reply_text(text, reply_markup=markup)


async def perform_colab_speedtest() -> str:
    """Run an asynchronous network speed test on Colab and return formatted text."""
    bin_path = shutil.which("speedtest-cli") or shutil.which("speedtest")
    if not bin_path:
        try:
            p_inst = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "-q", "speedtest-cli",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(p_inst.communicate(), timeout=30)
            bin_path = shutil.which("speedtest-cli")
        except Exception as e:
            logging.warning(f"Failed to auto-install speedtest-cli: {e}")

    cmd = [bin_path, "--simple"] if bin_path else [sys.executable, "-m", "speedtest", "--simple"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=50)
        out_text = stdout.decode("utf-8", errors="ignore").strip()
        if "Download:" in out_text:
            lines = out_text.splitlines()
            ping = "N/A"
            dl = "N/A"
            ul = "N/A"
            for line in lines:
                if "Ping:" in line:
                    ping = line.split(":", 1)[1].strip()
                elif "Download:" in line:
                    dl = line.split(":", 1)[1].strip()
                elif "Upload:" in line:
                    ul = line.split(":", 1)[1].strip()

            return (
                "⚡ <b>Colab Network Speedtest Results</b>\n\n"
                f"📡 <b>Ping / Latency:</b> <code>{ping}</code>\n"
                f"⬇️ <b>Download Speed:</b> <code>{dl}</code>\n"
                f"⬆️ <b>Upload Speed:</b> <code>{ul}</code>\n\n"
                "🌐 <b>Host Environment:</b> <code>Google Colab Cloud Network</code>\n"
                f"🚀 <i>Tested at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>"
            )
        else:
            err_msg = stderr.decode("utf-8", errors="ignore").strip()
            logging.warning(f"Speedtest error output: {err_msg}")
    except asyncio.TimeoutError:
        return "⚠️ <b>Speedtest timed out</b> (network latency or server busy). Please try again in a moment."
    except Exception as e:
        logging.error(f"Error during speedtest: {e}")

    return "⚠️ <b>Speedtest unavailable:</b> Unable to connect to speedtest servers right now. Please test again later."


@colab_bot.on_message(filters.command(["speedtest", "speed", "sp"]))
async def speedtest_cmd(client, message):
    status_msg = await message.reply_text("⚡ <i>Running Colab network speed test... Please wait ~15-20 seconds.</i>")
    result = await perform_colab_speedtest()
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Server Stats", callback_data="cmd_stats"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ]
    ])
    await status_msg.edit_text(result, reply_markup=markup)


@colab_bot.on_message(filters.command(["restart", "r"]))
async def restart_cmd(client, message):
    u_id = message.from_user.id if message.from_user else message.chat.id
    if OWNER != 0 and u_id != OWNER:
        await message.reply_text("⚠️ Only owner can restart the bot.")
        return
    await message.reply_text("🔄 <b>Restarting BiliColabX engine... Please wait 5 seconds.</b>")
    os.execv(sys.executable, [sys.executable, "-m", "bili_leecher"])


# Direct link listener in PM: If user pastes a Bilibili URL, process immediately
@colab_bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "h", "bili", "b", "leech", "l", "mirror", "m", "drive", "gdrive", "dfolder", "browse", "binfo", "info", "cookies", "cookie", "sessdata", "delcookies", "status", "s", "usetting", "bsetting", "cancel", "cancelall", "restart", "stats", "st", "server", "speedtest", "speed", "sp", "rclone", "rc"]))
async def direct_message_listener(client, message):
    u_id = message.from_user.id if message.from_user else message.chat.id

    # Check if user is in an input state (e.g. Setting SESSDATA, Prefix)
    state = USER_INPUT_STATES.get(u_id)
    if state:
        txt = message.text.strip()
        if state == "set_sessdata":
            sess = SettingsManager.extract_sessdata(txt)
            if sess:
                SettingsManager.set_user_setting(u_id, "sessdata", sess)
                await message.reply_text(f"✅ SESSDATA token saved: <code>{sess[:10]}...</code>")
            else:
                await message.reply_text("⚠️ Invalid token format.")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_prefix":
            SettingsManager.set_user_setting(u_id, "prefix", txt)
            await message.reply_text(f"✅ Prefix set to: <code>{txt}</code>")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_suffix":
            SettingsManager.set_user_setting(u_id, "suffix", txt)
            await message.reply_text(f"✅ Suffix set to: <code>{txt}</code>")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_caption":
            SettingsManager.set_user_setting(u_id, "custom_caption", txt)
            await message.reply_text("✅ Custom caption template saved.")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_dump":
            SettingsManager.set_user_setting(u_id, "dump_channel", txt)
            await message.reply_text(f"✅ Dump channel set to: <code>{txt}</code>")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_drive_folder":
            SettingsManager.set_user_setting(u_id, "drive_folder_name", txt)
            await message.reply_text(f"✅ Drive subfolder set to: <code>MyDrive/{txt}</code>")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_gofile":
            SettingsManager.set_user_setting(u_id, "gofile_token", "" if txt.lower() == "none" else txt)
            await message.reply_text(f"✅ Gofile token updated!")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_pixeldrain":
            clean_key = "" if txt.lower() == "none" else txt
            SettingsManager.set_user_setting(u_id, "pixeldrain_api_key", clean_key)
            SettingsManager.set_user_setting(u_id, "pixeldrain_token", clean_key)
            await message.reply_text(f"✅ PixelDrain API key updated!")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_global_sessdata":
            sess = SettingsManager.extract_sessdata(txt)
            if sess:
                SettingsManager.set_bot_setting("default_sessdata", sess)
                await message.reply_text(f"✅ <b>Global SESSDATA set for all bot users:</b> <code>{sess[:10]}...</code>")
            else:
                await message.reply_text("⚠️ Invalid token format.")
            del USER_INPUT_STATES[u_id]
            return
        elif state == "set_drive_id":
            SettingsManager.set_user_setting(u_id, "drive_folder_id", txt)
            await message.reply_text(f"✅ Drive Folder ID set to: <code>{txt}</code>")
            del USER_INPUT_STATES[u_id]
            return
        elif state.startswith("set_drive_mkdir_"):
            h_id = state.replace("set_drive_mkdir_", "")
            parent_rel = DRIVE_PATH_CACHE.get(h_id, "")
            folder_name = txt.strip().strip("/\\")
            full_sub = f"{parent_rel}/{folder_name}".strip("/") if parent_rel else folder_name
            create_drive_folder(full_sub)
            SettingsManager.set_user_setting(u_id, "drive_folder_name", full_sub)
            del USER_INPUT_STATES[u_id]
            await message.reply_text(
                f"✅ <b>Folder Created Successfully!</b>\n"
                f"📁 <code>MyDrive/{full_sub}</code>\n"
                f"<i>Set as your active Google Drive mirror destination.</i>",
                reply_markup=get_drive_browser_markup(full_sub, user_id=u_id)
            )
            return

    # If message contains Bilibili URLs or batch links
    if is_bilibili_url(message.text) or "bilibili.com" in message.text or "b23.tv" in message.text:
        links, options = parse_bili_flags_and_links(message.text)
        if len(links) > 1:
            user_name = message.from_user.first_name if message.from_user else "User"
            await message.reply_text(
                f"🚀 <b>Batch Download Detected ({len(links)} links)!</b>\n"
                f"<i>Launching concurrent download pipeline...</i>"
            )
            await dispatch_task(
                mode_type=options.get("mode_type", "normal"),
                mode="leech",
                is_ytdl=False,
                links=links,
                user_name=user_name,
                chat_id=message.chat.id,
                options=options,
                message=message,
            )
            return
        elif len(links) == 1:
            PENDING_BILI_LINKS[u_id] = links[0]
            markup = quality_buttons(links[0], user_id=u_id)
            await message.reply_text(
                f"<b>📺 Bilibili Link Detected!</b>\n<code>{links[0][:50]}...</code>\n\n"
                f"<i>Select your preferred download quality or tap directly to leech:</i>",
                reply_markup=markup
            )
            return


@colab_bot.on_message(filters.command(["concurrency", "conc", "parallel"]))
async def set_concurrency_cmd(client, message):
    tokens = message.text.split()
    u_id = message.from_user.id if message.from_user else message.chat.id
    if len(tokens) > 1 and tokens[1].isdigit():
        val = max(1, min(8, int(tokens[1])))
        SettingsManager.set_user_setting(u_id, "concurrent_videos", val)
        await message.reply_text(f"⚡ <b>Concurrency updated!</b>\nNow downloading up to <code>{val} videos in parallel</code>.")
    else:
        u_conf = SettingsManager.get_user_settings(u_id)
        cur = u_conf.get("concurrent_videos", 4)
        await message.reply_text(
            f"⚡ <b>Current Concurrency:</b> <code>{cur} Parallel Downloads</code>\n"
            f"<i>Choose a new concurrency limit below or use: <code>/conc 4</code></i>",
            reply_markup=get_concurrency_markup(u_id)
        )


@colab_bot.on_message(filters.command(["engine", "eng"]))
async def set_engine_cmd(client, message):
    tokens = message.text.split()
    u_id = message.from_user.id if message.from_user else message.chat.id
    if len(tokens) > 1:
        choice = tokens[1].lower()
        eng_map = {
            "web": "BBDown - WEB",
            "tv": "BBDown - TV",
            "app": "BBDown - APP",
            "ytdl": "yt-dlp",
            "yt-dlp": "yt-dlp",
        }
        chosen = eng_map.get(choice, "BBDown - WEB")
        SettingsManager.set_user_setting(u_id, "engine", chosen)
        await message.reply_text(f"⚙️ <b>Download Engine updated!</b>\nActive Engine: <code>{chosen}</code>")
    else:
        u_conf = SettingsManager.get_user_settings(u_id)
        cur = u_conf.get("engine", "BBDown - WEB")
        await message.reply_text(
            f"⚙️ <b>Active Engine:</b> <code>{cur}</code>\n"
            f"<i>Select preferred download engine below:</i>",
            reply_markup=get_engine_menu_markup(u_id)
        )


@colab_bot.on_message(filters.command(["dfolder", "setdrivefolder", "drivefolder", "browse"]))
async def drive_folder_cmd(client, message):
    allowed, reason = check_access(message)
    if not allowed:
        await message.reply_text(reason)
        return

    u_id = message.from_user.id if message.from_user else message.chat.id
    tokens = message.text.split(maxsplit=1)
    if len(tokens) > 1:
        folder_arg = tokens[1].strip().strip("/\\")
        create_drive_folder(folder_arg)
        SettingsManager.set_user_setting(u_id, "drive_folder_name", folder_arg)
        await message.reply_text(
            f"✅ <b>Google Drive Target Folder Updated!</b>\n\n"
            f"📁 <b>Active Path:</b> <code>MyDrive/{folder_arg}</code>\n"
            f"<i>Subfolder created and ready for uploads.</i>"
        )
    else:
        # Open interactive folder browser
        browser_text = get_drive_browser_text("", user_id=u_id)
        markup = get_drive_browser_markup("", user_id=u_id)
        await message.reply_text(browser_text, reply_markup=markup)


@colab_bot.on_message(filters.command(["rclone", "rconfig"]))
async def rclone_remotes_cmd(client, message):
    allowed, reason = check_access(message)
    if not allowed:
        await message.reply_text(reason)
        return

    remotes = await list_rclone_remotes()
    conf_path = get_rclone_config_path()
    has_conf = os.path.exists(conf_path)

    if remotes:
        rem_list = "\n".join([f"• <code>{r}:</code>" for r in remotes])
        text = (
            f"<b>☁️ Configured Rclone Remotes ({len(remotes)})</b>\n\n"
            f"{rem_list}\n\n"
            f"<b>How to Mirror via Rclone:</b>\n"
            f"• <code>/mirror &lt;url&gt; -rc {remotes[0]}:Bilibili</code>\n"
            f"• <code>/bili &lt;url&gt; -rc {remotes[0]}:Videos -z</code> (Zip & upload)\n\n"
            f"<i>Config file located at: <code>{conf_path}</code></i>"
        )
    else:
        text = (
            f"<b>☁️ Rclone Cloud Remotes</b>\n\n"
            f"⚠️ <b>No rclone remotes found!</b>\n"
            f"Config file: <code>{conf_path}</code> ({'Found' if has_conf else 'Missing'})\n\n"
            f"<b>To configure Rclone on Colab:</b>\n"
            f"1. Run <code>!rclone config</code> in a Colab notebook cell.\n"
            f"2. Or upload your <code>rclone.conf</code> to <code>/root/.config/rclone/rclone.conf</code>."
        )

    await message.reply_text(text)


@colab_bot.on_message(filters.command(["gofile"]))
async def gofile_token_cmd(client, message):
    u_id = message.from_user.id if message.from_user else message.chat.id
    tokens = message.text.split(maxsplit=1)
    if len(tokens) > 1:
        token = tokens[1].strip()
        SettingsManager.set_user_setting(u_id, "gofile_token", token)
        await message.reply_text(
            f"✅ <b>Gofile API Token Saved!</b>\n"
            f"<code>{token[:6]}...{token[-4:]}</code>\n"
            f"<i>Your uploads will now be attached to your personal Gofile account.</i>"
        )
    else:
        cur_tok = SettingsManager.get_user_settings(u_id).get("gofile_token", "")
        disp = f"<code>{cur_tok[:6]}...{cur_tok[-4:]}</code>" if cur_tok else "❌ None (Anonymous Mode)"
        await message.reply_text(
            f"<b>📁 Gofile Configuration</b>\n\n"
            f"• <b>Current Token:</b> {disp}\n\n"
            f"Usage: <code>/gofile your_api_token</code>\n"
            f"To clear: <code>/gofile none</code>\n"
            f"<i>(Anonymous uploads work without any token!)</i>"
        )


@colab_bot.on_message(filters.command(["pixeldrain"]))
async def pixeldrain_key_cmd(client, message):
    u_id = message.from_user.id if message.from_user else message.chat.id
    tokens = message.text.split(maxsplit=1)
    if len(tokens) > 1:
        key = tokens[1].strip()
        SettingsManager.set_user_setting(u_id, "pixeldrain_api_key", key)
        await message.reply_text(
            f"✅ <b>PixelDrain API Key Saved!</b>\n"
            f"<code>{key[:6]}...{key[-4:]}</code>\n"
            f"<i>Your uploads will now be linked to your PixelDrain account.</i>"
        )
    else:
        cur_key = SettingsManager.get_user_settings(u_id).get("pixeldrain_api_key", "")
        disp = f"<code>{cur_key[:6]}...{cur_key[-4:]}</code>" if cur_key else "❌ None (Anonymous Mode)"
        await message.reply_text(
            f"<b>💧 PixelDrain Configuration</b>\n\n"
            f"• <b>Current API Key:</b> {disp}\n\n"
            f"Usage: <code>/pixeldrain your_api_key</code>\n"
            f"To clear: <code>/pixeldrain none</code>\n"
            f"<i>(Anonymous uploads work without any key!)</i>"
        )


# ==================== Callback Query Handlers ====================

@colab_bot.on_callback_query()
async def callback_router(client, query: CallbackQuery):
    data = query.data
    u_id = query.from_user.id if query.from_user else 0

    if data == "uset_close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # Drive Folder Browser Callbacks
    elif data.startswith("df_browse_"):
        target_uid = int(data.split("_")[2])
        text = get_drive_browser_text("", user_id=target_uid)
        markup = get_drive_browser_markup("", user_id=target_uid)
        await query.message.edit_text(text, reply_markup=markup)
        return

    elif data.startswith("dfn_"):
        h_id = data.split("_")[1]
        rel_path = DRIVE_PATH_CACHE.get(h_id, "")
        text = get_drive_browser_text(rel_path, user_id=u_id)
        markup = get_drive_browser_markup(rel_path, user_id=u_id)
        await query.message.edit_text(text, reply_markup=markup)
        return

    elif data.startswith("dfs_"):
        h_id = data.split("_")[1]
        rel_path = DRIVE_PATH_CACHE.get(h_id, "")
        selected_folder = rel_path if rel_path else "BiliColabX_Uploads"
        create_drive_folder(selected_folder)
        SettingsManager.set_user_setting(u_id, "drive_folder_name", selected_folder)
        await query.answer(f"Drive destination set: MyDrive/{selected_folder} ✅", show_alert=True)
        await query.message.edit_text(get_user_settings_text(u_id), reply_markup=get_user_settings_markup(u_id))
        return

    elif data.startswith("dfm_"):
        h_id = data.split("_")[1]
        USER_INPUT_STATES[u_id] = f"set_drive_mkdir_{h_id}"
        await query.message.edit_text(
            "➕ <b>Create New Folder:</b>\n\n"
            "<i>Please send the name of the new folder as a text message:</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"dfn_{h_id}")]])
        )
        return

    elif data == "ref":
        txt = render_multi_status(ACTIVE_TASKS)
        try:
            await query.message.edit_text(txt, reply_markup=keyboard(), disable_web_page_preview=True)
            await query.answer("Dashboard Refreshed ♻️")
        except Exception:
            await query.answer("Status unchanged.")
        return

    elif data.startswith("cancel_"):
        tid = data.split("_", 1)[1]
        await cancelTask("User cancelled via status button.", task_id=tid)
        await query.answer("Task Cancelled 🛑")
        return

    # Direct Bilibili Quality Download buttons from inline prompt
    elif data.startswith("bili_dl_"):
        parts = data.split("_")
        q_choice = parts[3] if len(parts) > 3 else "1080P"
        target_url = PENDING_BILI_LINKS.get(u_id)
        if not target_url:
            await query.answer("Link expired. Please send the link again.", show_alert=True)
            return

        is_audio = (q_choice == "Audio")
        is_danmaku = (q_choice == "Danmaku")
        opt = {
            "bili_quality": "1080P" if is_danmaku else q_choice,
            "audio_only": is_audio,
            "download_danmaku": is_danmaku,
        }

        try:
            await query.message.delete()
        except Exception:
            pass

        await dispatch_task(
            mode_type="normal",
            mode="leech",
            is_ytdl=False,
            links=[target_url],
            user_name=query.from_user.first_name,
            chat_id=query.message.chat.id,
            options=opt,
            message=query.message,
            user_id=u_id,
        )
        return

    # Open User Settings
    elif data.startswith("open_uset_"):
        target_uid = int(data.split("_")[2])
        txt = get_user_settings_text(target_uid)
        markup = get_user_settings_markup(target_uid)
        try:
            await query.message.edit_text(txt, reply_markup=markup)
        except Exception:
            pass
        return

    elif data.startswith("uset_quality_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text("📺 <b>Select Default Bilibili Resolution:</b>", reply_markup=get_bili_quality_markup(target_uid))
        return

    elif data.startswith("set_biliq_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        q_val = parts[3]
        SettingsManager.set_user_setting(target_uid, "bili_quality", q_val)
        SettingsManager.set_user_setting(target_uid, "audio_only", q_val == "Audio")
        await query.answer(f"Default quality set to {q_val} ✅")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_conc_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text(
            "⚡ <b>Select Parallel Concurrency Limit:</b>\n"
            "<i>Higher concurrency downloads multi-part videos faster in parallel.</i>",
            reply_markup=get_concurrency_markup(target_uid),
        )
        return

    elif data.startswith("set_conc_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        val = int(parts[3])
        SettingsManager.set_user_setting(target_uid, "concurrent_videos", val)
        await query.answer(f"Concurrency set to {val}x ⚡")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_engine_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text(
            "⚙️ <b>Select Download Engine:</b>\n\n"
            "• <b>BBDown - WEB:</b> Highest compatibility (Supports VIP 8K/4K/1080P+)\n"
            "• <b>BBDown - TV:</b> High-speed TV stream routing\n"
            "• <b>BBDown - APP:</b> Alternative mobile stream format\n"
            "• <b>yt-dlp:</b> Universal fallback engine",
            reply_markup=get_engine_menu_markup(target_uid),
        )
        return

    elif data.startswith("set_eng_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        e_key = parts[3]
        eng_map = {
            "web": "BBDown - WEB",
            "tv": "BBDown - TV",
            "app": "BBDown - APP",
            "ytdl": "yt-dlp",
        }
        chosen = eng_map.get(e_key, "BBDown - WEB")
        SettingsManager.set_user_setting(target_uid, "engine", chosen)
        await query.answer(f"Engine set to {chosen} ⚙️")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_cookies_"):
        target_uid = int(data.split("_")[2])
        sess = SettingsManager.get_sessdata(target_uid)
        sess_txt = f"<code>{sess[:10]}...</code>" if sess else "None"
        text = (
            f"<b>🍪 SESSDATA & Cookie Management</b>\n\n"
            f"• <b>Active SESSDATA:</b> {sess_txt}\n\n"
            f"<i>To set SESSDATA, tap 'Set SESSDATA Token' below and paste your token, or send your cookies.txt file!</i>"
        )
        await query.message.edit_text(text, reply_markup=get_cookie_menu_markup(target_uid))
        return

    elif data.startswith("input_sessdata_"):
        target_uid = int(data.split("_")[2])
        USER_INPUT_STATES[target_uid] = "set_sessdata"
        await query.message.edit_text(
            "🔑 <b>Please send your Bilibili SESSDATA token as a text message now:</b>\n"
            "<i>(Example: 6e4a2bc0%2C1745...)</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"open_uset_{target_uid}")]])
        )
        return

    elif data.startswith("del_user_cookie_"):
        target_uid = int(data.split("_")[3])
        SettingsManager.delete_user_cookies(target_uid)
        await query.answer("Cookies Deleted 🗑")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_toggle_stream_"):
        target_uid = int(data.split("_")[3])
        u = SettingsManager.get_user_settings(target_uid)
        new_val = "Document" if u.get("stream_upload") == "Media" else "Media"
        SettingsManager.set_user_setting(target_uid, "stream_upload", new_val)
        await query.answer(f"Upload mode: {new_val}")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_toggle_danmaku_"):
        target_uid = int(data.split("_")[3])
        u = SettingsManager.get_user_settings(target_uid)
        new_val = not u.get("download_danmaku", False)
        SettingsManager.set_user_setting(target_uid, "download_danmaku", new_val)
        await query.answer(f"Danmaku: {'ON' if new_val else 'OFF'}")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_toggle_dm_"):
        target_uid = int(data.split("_")[3])
        u = SettingsManager.get_user_settings(target_uid)
        new_val = not u.get("send_to_dm", True)
        SettingsManager.set_user_setting(target_uid, "send_to_dm", new_val)
        await query.answer(f"DM Delivery: {'ON' if new_val else 'OFF'}")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_split_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text("✂️ <b>Select Video Split Size Limit:</b>", reply_markup=get_split_menu_markup(target_uid))
        return

    elif data.startswith("uset_arcfmt_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text("📦 <b>Select Default Archive Compression Format:</b>", reply_markup=get_archive_menu_markup(target_uid))
        return

    elif data.startswith("set_arcfmt_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        fmt = parts[3]
        SettingsManager.set_user_setting(target_uid, "archive_format", fmt)
        await query.answer(f"Archive format set to .{fmt} 📦")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("set_split_"):
        parts = data.split("_")
        target_uid = int(parts[2])
        mb = int(parts[3])
        SettingsManager.set_user_setting(target_uid, "split_size_mb", mb)
        SettingsManager.set_user_setting(target_uid, "split_video", f"{mb/1000:.1f}GB")
        await query.answer(f"Split size: {mb}MB ✅")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_reset_"):
        target_uid = int(data.split("_")[2])
        SettingsManager.reset_user_settings(target_uid)
        await query.answer("All settings reset to defaults.")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_captions_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text("✏️ <b>Prefix, Suffix & Caption Config:</b>", reply_markup=get_captions_menu_markup(target_uid))
        return

    elif data.startswith("input_prefix_"):
        target_uid = int(data.split("_")[2])
        USER_INPUT_STATES[target_uid] = "set_prefix"
        await query.message.edit_text("✏️ <b>Send your filename prefix now:</b>")
        return

    elif data.startswith("clear_prefix_"):
        target_uid = int(data.split("_")[2])
        SettingsManager.set_user_setting(target_uid, "prefix", "")
        await query.answer("Prefix cleared.")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("input_suffix_"):
        target_uid = int(data.split("_")[2])
        USER_INPUT_STATES[target_uid] = "set_suffix"
        await query.message.edit_text("✏️ <b>Send your filename suffix now:</b>")
        return

    elif data.startswith("clear_suffix_"):
        target_uid = int(data.split("_")[2])
        SettingsManager.set_user_setting(target_uid, "suffix", "")
        await query.answer("Suffix cleared.")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("input_caption_"):
        target_uid = int(data.split("_")[2])
        USER_INPUT_STATES[target_uid] = "set_caption"
        await query.message.edit_text("✏️ <b>Send your custom caption template now:</b>")
        return

    elif data.startswith("clear_caption_"):
        target_uid = int(data.split("_")[2])
        SettingsManager.set_user_setting(target_uid, "custom_caption", "")
        await query.answer("Caption cleared.")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_dump_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text("🗂 <b>Custom Dump Channel:</b>", reply_markup=get_dump_menu_markup(target_uid))
        return

    elif data.startswith("input_dump_"):
        target_uid = int(data.split("_")[2])
        USER_INPUT_STATES[target_uid] = "set_dump"
        await query.message.edit_text("🗂 <b>Send your Channel ID (e.g. -100...) now:</b>")
        return

    elif data.startswith("clear_dump_"):
        target_uid = int(data.split("_")[2])
        SettingsManager.set_user_setting(target_uid, "dump_channel", "")
        await query.answer("Dump channel cleared.")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_drive_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text("📁 <b>Google Drive Configuration:</b>", reply_markup=get_drive_menu_markup(target_uid))
        return

    elif data.startswith("input_drive_folder_"):
        target_uid = int(data.split("_")[3])
        USER_INPUT_STATES[target_uid] = "set_drive_folder"
        await query.message.edit_text("📁 <b>Send the folder name inside your Google Drive (e.g. Bilibili_Videos):</b>")
        return

    elif data.startswith("input_drive_id_"):
        target_uid = int(data.split("_")[3])
        USER_INPUT_STATES[target_uid] = "set_drive_id"
        await query.message.edit_text("🔑 <b>Send your Google Drive Folder ID (e.g. 1AbCdEfGhI...):</b>")
        return

    elif data.startswith("clear_drive_id_"):
        target_uid = int(data.split("_")[3])
        SettingsManager.set_user_setting(target_uid, "drive_folder_id", "")
        await query.answer("Folder ID cleared. Reverting to MyDrive subfolder.")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data.startswith("uset_cloud_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text(get_cloud_settings_text(target_uid), reply_markup=get_cloud_settings_markup(target_uid))
        return

    elif data.startswith("input_gofile_"):
        target_uid = int(data.split("_")[2])
        USER_INPUT_STATES[target_uid] = "set_gofile"
        await query.message.edit_text(
            "📁 <b>Set Gofile Token:</b>\n\n"
            "<i>Send your Gofile API account token now (or send <code>none</code> to remove):</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"uset_cloud_{target_uid}")]])
        )
        return

    elif data.startswith("clear_gofile_"):
        target_uid = int(data.split("_")[2])
        SettingsManager.set_user_setting(target_uid, "gofile_token", "")
        await query.answer("Gofile token cleared (Anonymous mode).")
        await query.message.edit_text(get_cloud_settings_text(target_uid), reply_markup=get_cloud_settings_markup(target_uid))
        return

    elif data.startswith("input_pixeldrain_"):
        target_uid = int(data.split("_")[2])
        USER_INPUT_STATES[target_uid] = "set_pixeldrain"
        await query.message.edit_text(
            "💧 <b>Set PixelDrain API Key:</b>\n\n"
            "<i>Send your PixelDrain API key now (or send <code>none</code> to remove):</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"uset_cloud_{target_uid}")]])
        )
        return

    elif data.startswith("clear_pixeldrain_"):
        target_uid = int(data.split("_")[2])
        SettingsManager.set_user_setting(target_uid, "pixeldrain_api_key", "")
        SettingsManager.set_user_setting(target_uid, "pixeldrain_token", "")
        await query.answer("PixelDrain API key cleared (Anonymous mode).")
        await query.message.edit_text(get_cloud_settings_text(target_uid), reply_markup=get_cloud_settings_markup(target_uid))
        return

    elif data.startswith("view_rclone_"):
        target_uid = int(data.split("_")[2])
        from bili_leecher.uploader.cloud_uploader import list_rclone_remotes, get_rclone_config_path
        remotes = await list_rclone_remotes()
        conf_p = get_rclone_config_path()
        if remotes:
            rem_list = "\n".join([f"• <code>{r}:</code>" for r in remotes])
            txt = f"<b>☁️ Available Rclone Remotes ({len(remotes)})</b>\n\n{rem_list}\n\n<i>Config: <code>{conf_p}</code></i>"
        else:
            txt = (
                f"<b>☁️ Rclone Remotes</b>\n\n"
                f"⚠️ No remotes detected in <code>{conf_p}</code>.\n\n"
                f"<i>Upload your <code>rclone.conf</code> file directly into chat to activate!</i>"
            )
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Cloud", callback_data=f"uset_cloud_{target_uid}")]]))
        return

    elif data.startswith("prompt_rclone_"):
        target_uid = int(data.split("_")[2])
        await query.message.edit_text(
            "📄 <b>Upload rclone.conf</b>\n\n"
            "<i>Send your <code>rclone.conf</code> file as a document into this chat right now. The bot will automatically detect, save, and activate all your cloud remotes!</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"uset_cloud_{target_uid}")]])
        )
        return

    elif data.startswith("prompt_upload_cookies_"):
        target_uid = int(data.split("_")[3])
        await query.message.edit_text(
            "🍪 <b>Upload cookies.txt</b>\n\n"
            "<i>Send your <code>cookies.txt</code> file as a document into this chat. The bot will extract your VIP SESSDATA automatically!</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"uset_cookies_{target_uid}")]])
        )
        return

    elif data == "open_bset":
        if OWNER != 0 and u_id != OWNER:
            await query.answer("Owner only area.", show_alert=True)
            return
        await query.message.edit_text(get_bot_settings_text(), reply_markup=get_bot_settings_markup())
        return

    elif data == "bset_input_sessdata":
        if OWNER != 0 and u_id != OWNER:
            await query.answer("Owner only area.", show_alert=True)
            return
        USER_INPUT_STATES[u_id] = "set_global_sessdata"
        await query.message.edit_text(
            "🔑 <b>Set Global Bot SESSDATA:</b>\n\n"
            "<i>Paste the global Bilibili SESSDATA token that will serve all bot users as the default VIP account:</i>",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="open_bset")]])
        )
        return

    elif data == "bset_clear_sessdata":
        if OWNER != 0 and u_id != OWNER:
            await query.answer("Owner only area.", show_alert=True)
            return
        SettingsManager.set_bot_setting("default_sessdata", "")
        await query.answer("Global SESSDATA cleared.")
        await query.message.edit_text(get_bot_settings_text(), reply_markup=get_bot_settings_markup())
        return

    elif data.startswith("bset_par_"):
        val = int(data.split("_")[2])
        SettingsManager.set_bot_setting("max_parallel_tasks", val)
        await query.answer(f"Parallel downloads set to {val}")
        await query.message.edit_text(get_bot_settings_text(), reply_markup=get_bot_settings_markup())
        return

    elif data == "bset_cleartemp":
        if os.path.exists(Paths.WORK_PATH):
            shutil.rmtree(Paths.WORK_PATH, ignore_errors=True)
            os.makedirs(Paths.WORK_PATH, exist_ok=True)
        await query.answer("Temporary cache wiped! 🧹", show_alert=True)
        return

    elif data == "open_help":
        await query.message.edit_text(get_help_text(), reply_markup=get_help_markup(u_id))
        return

    elif data.startswith("open_start"):
        u_name = query.from_user.first_name if query.from_user else "User"
        await query.message.edit_text(get_welcome_text(u_id, u_name), reply_markup=get_welcome_markup(u_id))
        return

    elif data == "cmd_stats":
        txt = get_server_metrics_text()
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ Speedtest", callback_data="bset_speedtest"),
                InlineKeyboardButton("🔙 Back to Welcome", callback_data="open_start"),
            ],
            [
                InlineKeyboardButton("❌ Close", callback_data="uset_close"),
            ]
        ])
        await query.message.edit_text(txt, reply_markup=markup)
        return

    elif data.startswith("uset_toggle_autodel_"):
        target_uid = int(data.split("_")[3])
        cur = SettingsManager.get_user_settings(target_uid).get("auto_delete_status", False)
        SettingsManager.set_user_setting(target_uid, "auto_delete_status", not cur)
        await query.answer(f"Message Disappear set to {'ON (30s)' if not cur else 'OFF'}")
        await query.message.edit_text(get_user_settings_text(target_uid), reply_markup=get_user_settings_markup(target_uid))
        return

    elif data == "bset_toggle_autodel":
        if OWNER != 0 and u_id != OWNER:
            await query.answer("Owner only area.", show_alert=True)
            return
        cur = SettingsManager.get_bot_setting("auto_delete_status", False)
        SettingsManager.set_bot_setting("auto_delete_status", not cur)
        await query.answer(f"Global Message Disappear set to {'ON (30s)' if not cur else 'OFF'}")
        await query.message.edit_text(get_bot_settings_text(), reply_markup=get_bot_settings_markup())
        return

    elif data == "bset_speedtest":
        await query.answer("Starting network speed test...")
        await query.message.edit_text("⚡ <i>Running Colab network speed test... Please wait ~15-20 seconds.</i>")
        res = await perform_colab_speedtest()
        await query.message.edit_text(
            res,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔙 Back to Bot Settings", callback_data="open_bset"),
                    InlineKeyboardButton("❌ Close", callback_data="uset_close"),
                ]
            ])
        )
        return


# ==================== Main Runner Entry Point ====================

if __name__ == "__main__":
    banner = r"""
  ____  _ _ _  ____      _       _     __  __
 |  _ \(_) (_)/ ___|___ | | __ _| |__  \ \/ /
 | |_) | | | | |   / _ \| |/ _` | '_ \  \  / 
 |  _ <| | | | |__| (_) | | (_| | |_) | /  \ 
 |_| \_\_|_|_|\____\___/|_|\__,_|_.__/ /_/\_\
                                             
 📺 BiliColabX — Exclusive Bilibili Leecher & Cloud Mirror
 🚀 Powered by BBDown, DzGram MTProto & Google Colab
"""
    print(banner)
    logging.info("Starting BiliColabX Telegram Client...")
    colab_bot.run()

