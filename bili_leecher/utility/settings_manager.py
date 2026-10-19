# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Settings Manager specifically configured for Bilibili & Google Drive

import os
import re
import json
import logging
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bili_leecher.utility.variables import Paths

USERS_SETTINGS_FILE = os.path.join(Paths.BASE_DIR, "users_settings.json")
BOT_SETTINGS_FILE = os.path.join(Paths.BASE_DIR, "bot_settings.json")

DEFAULT_USER_SETTINGS = {
    "stream_upload": "Media",          # "Media" or "Document"
    "prefix": "",                      # Filename prefix
    "suffix": "",                      # Filename suffix
    "caption_style": "Monospace",      # "Monospace", "Bold", "Italic", "Underlined"
    "custom_caption": "",              # Custom caption template
    "bili_quality": "1080P",           # "8K", "4K", "1080P+", "1080P", "720P", "480P", "Audio"
    "sessdata": "",                    # Bilibili SESSDATA token
    "download_danmaku": False,         # Download bullet comments (.ass)
    "download_sub": True,              # Download subtitles
    "audio_only": False,               # Extract audio only
    "sample_duration": 0,              # 0 (off), 15, 30, 60
    "screenshot_count": 0,             # 0 (off), 3, 5, 10
    "split_video": "2.0GB",            # Preset display: 500MB, 1.0GB, 1.5GB, 2.0GB, 4.0GB
    "split_size_mb": 1950,             # Actual split size limit in MB
    "convert_video": "No",
    "video_out": "mp4",
    "has_thumb": False,
    "drive_folder_name": "BiliColabX_Uploads", # Target folder in MyDrive
    "drive_folder_id": "",             # Target Drive Folder ID for direct API upload
    "upload_target": "Telegram",       # "Telegram", "GoogleDrive", "All"
    "concurrent_videos": 4,            # Concurrent downloads (default 4)
    "engine": "BBDown - WEB",          # "BBDown - WEB", "BBDown - TV", "BBDown - APP", "yt-dlp"
    "upos_host": "upos-sz-mirrorhw.bilivideo.com", # UPOS CDN accelerator
    "dump_channel": "",
    "send_to_dm": True,
    "auto_delete_status": False,       # Disappear completed / status messages
    "archive_format": "zip",           # "zip", "7z", "rar", "tar", "tar.gz"
}

DEFAULT_BOT_SETTINGS = {
    "max_parallel_tasks": 4,           # Max concurrent downloads
    "leech_split_size": 2097152000,    # 2GB in bytes
    "default_engine": "BBDown",
    "default_mode": "leech",
    "default_sessdata": "",
    "drive_folder_name": "BiliColabX_Uploads",
    "auto_clean_temp": True,
    "auto_delete_commands": True,
    "auto_delete_status": False,       # Global auto-disappear for finished logs
    "permitted_users": [],
    "authorized_chats": [],
    "default_upload_target": "Telegram",
}


class SettingsManager:
    _users_data = None
    _bot_data = None

    @classmethod
    def _load_users(cls):
        if cls._users_data is None:
            if os.path.exists(USERS_SETTINGS_FILE):
                try:
                    with open(USERS_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cls._users_data = json.load(f)
                except Exception as e:
                    logging.error(f"Error loading users_settings.json: {e}")
                    cls._users_data = {}
            else:
                cls._users_data = {}
        return cls._users_data

    @classmethod
    def _save_users(cls):
        try:
            with open(USERS_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._users_data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving users_settings.json: {e}")

    @classmethod
    def _load_bot(cls):
        if cls._bot_data is None:
            if os.path.exists(BOT_SETTINGS_FILE):
                try:
                    with open(BOT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cls._bot_data = json.load(f)
                except Exception as e:
                    logging.error(f"Error loading bot_settings.json: {e}")
                    cls._bot_data = dict(DEFAULT_BOT_SETTINGS)
            else:
                cls._bot_data = dict(DEFAULT_BOT_SETTINGS)
        return cls._bot_data

    @classmethod
    def _save_bot(cls):
        try:
            with open(BOT_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._bot_data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving bot_settings.json: {e}")

    # ==================== User Settings API ====================

    @classmethod
    def get_user_settings(cls, user_id: int) -> dict:
        data = cls._load_users()
        uid = str(user_id)
        user_conf = dict(DEFAULT_USER_SETTINGS)
        if uid in data:
            user_conf.update(data[uid])

        thumb_path = cls.get_user_thumb_path(user_id)
        user_conf["has_thumb"] = os.path.exists(thumb_path)
        return user_conf

    @classmethod
    def set_user_setting(cls, user_id: int, key: str, value):
        data = cls._load_users()
        uid = str(user_id)
        if uid not in data:
            data[uid] = dict(DEFAULT_USER_SETTINGS)
        data[uid][key] = value
        cls._save_users()

    @classmethod
    def reset_user_settings(cls, user_id: int):
        data = cls._load_users()
        uid = str(user_id)
        if uid in data:
            del data[uid]
            cls._save_users()
        cls.delete_user_thumb(user_id)
        cls.delete_user_cookies(user_id)

    @classmethod
    def get_user_thumb_path(cls, user_id: int) -> str:
        thumbs_dir = os.path.join(Paths.WORK_PATH, "user_thumbs")
        os.makedirs(thumbs_dir, exist_ok=True)
        return os.path.join(thumbs_dir, f"thumb_{user_id}.jpg")

    @classmethod
    def save_user_thumb(cls, user_id: int, src_file: str) -> bool:
        try:
            from PIL import Image
            dst_path = cls.get_user_thumb_path(user_id)
            img = Image.open(src_file)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(dst_path, "JPEG", quality=90)
            cls.set_user_setting(user_id, "has_thumb", True)
            return True
        except Exception as e:
            logging.error(f"Error saving user thumbnail: {e}")
            return False

    @classmethod
    def delete_user_thumb(cls, user_id: int) -> bool:
        dst_path = cls.get_user_thumb_path(user_id)
        if os.path.exists(dst_path):
            try:
                os.remove(dst_path)
            except Exception:
                pass
        cls.set_user_setting(user_id, "has_thumb", False)
        return True

    # ==================== Cookie & SESSDATA Management ====================

    @classmethod
    def extract_sessdata(cls, text: str) -> str:
        if not text:
            return ""
        m = re.search(r"SESSDATA=([^;\s\r\n]+)", text)
        if m:
            return m.group(1).strip()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7 and parts[5] == "SESSDATA":
                return parts[6].strip()
            sp = line.split()
            if len(sp) >= 7 and sp[5] == "SESSDATA":
                return sp[6].strip()
        clean = text.strip()
        if len(clean) >= 16 and not any(ch in clean for ch in [" ", "\n", "\t", "<", ">", "{", "}"]):
            return clean
        return ""

    @classmethod
    def get_cookie_path(cls, user_id: int = None) -> str:
        if user_id:
            u_cookie = os.path.join(Paths.WORK_PATH, "user_cookies", f"cookies_{user_id}.txt")
            if os.path.exists(u_cookie) and os.path.getsize(u_cookie) > 0:
                return u_cookie

        candidates = [
            os.path.join(os.getcwd(), "cookies.txt"),
            os.path.join(Paths.BASE_DIR, "cookies.txt"),
            os.path.join(Paths.WORK_PATH, "cookies.txt"),
            "/content/cookies.txt",
        ]
        for c in candidates:
            if os.path.exists(c) and os.path.getsize(c) > 0:
                return c
        return ""

    @classmethod
    def get_sessdata(cls, user_id: int = None) -> str:
        if user_id:
            u_conf = cls.get_user_settings(user_id)
            if u_conf.get("sessdata"):
                return u_conf["sessdata"].strip()

            c_path = cls.get_cookie_path(user_id)
            if c_path and os.path.exists(c_path):
                try:
                    with open(c_path, "r", encoding="utf-8", errors="ignore") as f:
                        token = cls.extract_sessdata(f.read())
                        if token:
                            return token
                except Exception:
                    pass

        b_conf = cls.get_bot_settings()
        if b_conf.get("default_sessdata"):
            return b_conf["default_sessdata"].strip()

        g_cookie = cls.get_cookie_path(None)
        if g_cookie and os.path.exists(g_cookie):
            try:
                with open(g_cookie, "r", encoding="utf-8", errors="ignore") as f:
                    token = cls.extract_sessdata(f.read())
                    if token:
                        return token
            except Exception:
                pass

        return ""

    @classmethod
    def save_user_cookies(cls, user_id: int, file_path: str) -> bool:
        try:
            cookies_dir = os.path.join(Paths.WORK_PATH, "user_cookies")
            os.makedirs(cookies_dir, exist_ok=True)
            dst_path = os.path.join(cookies_dir, f"cookies_{user_id}.txt")

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            with open(dst_path, "w", encoding="utf-8") as f:
                f.write(content)

            sess = cls.extract_sessdata(content)
            if sess:
                cls.set_user_setting(user_id, "sessdata", sess)
            return True
        except Exception as e:
            logging.error(f"Error saving user cookies: {e}")
            return False

    @classmethod
    def delete_user_cookies(cls, user_id: int) -> bool:
        c_path = os.path.join(Paths.WORK_PATH, "user_cookies", f"cookies_{user_id}.txt")
        if os.path.exists(c_path):
            try:
                os.remove(c_path)
            except Exception:
                pass
        cls.set_user_setting(user_id, "sessdata", "")
        return True

    # ==================== Bot Settings API ====================

    @classmethod
    def get_bot_settings(cls) -> dict:
        data = cls._load_bot()
        bot_conf = dict(DEFAULT_BOT_SETTINGS)
        bot_conf.update(data)
        return bot_conf

    @classmethod
    def set_bot_setting(cls, key: str, value):
        data = cls._load_bot()
        data[key] = value
        cls._save_bot()

    @classmethod
    def is_user_permitted(cls, user_id: int, owner_id: int) -> bool:
        if owner_id == 0 or user_id == owner_id:
            return True
        b_conf = cls.get_bot_settings()
        permitted = b_conf.get("permitted_users", [])
        return user_id in permitted

    @classmethod
    def is_chat_authorized(cls, chat_id: int) -> bool:
        b_conf = cls.get_bot_settings()
        authorized = b_conf.get("authorized_chats", [])
        if not authorized:
            return True
        return chat_id in authorized


# ==================== Interactive UI Markups ====================

def get_user_settings_text(user_id: int) -> str:
    u = SettingsManager.get_user_settings(user_id)
    sess = SettingsManager.get_sessdata(user_id)
    sess_disp = f"✅ <code>{sess[:8]}...{sess[-6:]}</code> (VIP Active)" if sess else "❌ Anonymous (Free 1080P/720P)"

    stream_m = "🎬 Video (Streamable)" if u.get("stream_upload") == "Media" else "📁 Document (File)"
    bili_q = u.get("bili_quality", "1080P")
    split_sz = f"{u.get('split_size_mb', 1950)} MB"
    danmaku = "✅ ON" if u.get("download_danmaku") else "❌ OFF"
    subs = "✅ ON" if u.get("download_sub", True) else "❌ OFF"
    audio = "🎵 Audio Only" if u.get("audio_only") else "🎬 Video + Audio"
    dump = f"<code>{u.get('dump_channel')}</code>" if u.get("dump_channel") else ("🤖 Bot DM" if u.get("send_to_dm", True) else "💬 Group")

    conc = u.get("concurrent_videos", 4)
    engine = u.get("engine", "BBDown - WEB")

    # Google Drive status
    drive_mounted = os.path.exists("/content/drive/MyDrive") or os.path.exists(Paths.MOUNTED_DRIVE)
    drive_stat = "✅ Mounted (Colab MyDrive)" if drive_mounted else "⚠️ Not Mounted (/content/drive)"
    drive_folder = u.get("drive_folder_name", "BiliColabX_Uploads")
    drive_fid = u.get("drive_folder_id", "")
    drive_target_disp = f"✅ Folder ID: <code>{drive_fid[:10]}...</code>" if drive_fid else f"✅ <code>MyDrive/{drive_folder}</code>"

    # Cloud Accounts check
    gf_token = u.get("gofile_token", "")
    pd_token = u.get("pixeldrain_api_key", "") or u.get("pixeldrain_token", "")
    gf_tick = "✅" if gf_token else "⚪"
    pd_tick = "✅" if pd_token else "⚪"

    u_autodel = u.get("auto_delete_status", False)
    autodel_disp = "✅ ON (Disappear after 30s)" if u_autodel else "❌ OFF (Permanent)"

    from bili_leecher import colab_bot
    bot_has_prem = hasattr(colab_bot, "me") and getattr(colab_bot.me, "is_premium", False)
    tg_tier_disp = "⭐️ Premium (4GB Limit - Auto)" if bot_has_prem else "👤 Free Account (2GB Limit - Auto)"
    arc_fmt = u.get("archive_format", "zip").upper()

    return (
        f"<b>⚙️ User Settings (BiliColabX)</b>\n"
        f"<i>Personal preferences for Bilibili leeching & Google Drive mirroring:</i>\n\n"
        f"╭⌬ <b>Bilibili SESSDATA:</b> {sess_disp}\n"
        f"├⌬ <b>Telegram Tier    :</b> <code>{tg_tier_disp}</code>\n"
        f"├⌬ <b>Archive Format   :</b> <code>.{arc_fmt.lower()}</code>\n"
        f"├⌬ <b>Default Quality  :</b> <code>{bili_q}</code> ({audio})\n"
        f"├⌬ <b>Concurrency      :</b> <code>{conc} Parallel Downloads</code> (Default)\n"
        f"├⌬ <b>Download Engine  :</b> <code>{engine}</code>\n"
        f"├⌬ <b>Danmaku / Subs   :</b> <code>{danmaku}</code> | <code>{subs}</code>\n"
        f"├⌬ <b>Telegram Upload  :</b> <code>{stream_m}</code>\n"
        f"├⌬ <b>Split Limit      :</b> <code>{split_sz}</code>\n"
        f"├⌬ <b>Google Drive Sync:</b> {drive_stat}\n"
        f"├⌬ <b>Drive Destination:</b> {drive_target_disp}\n"
        f"├⌬ <b>Cloud Tokens     :</b> {gf_tick} Gofile | {pd_tick} PixelDrain\n"
        f"├⌬ <b>TG Delivery      :</b> <code>{dump}</code>\n"
        f"╰⌬ <b>Msg Disappear    :</b> {autodel_disp}\n"
    )


def get_user_settings_markup(user_id: int) -> InlineKeyboardMarkup:
    u = SettingsManager.get_user_settings(user_id)
    stream_lbl = "🎬 Upload: Media" if u.get("stream_upload") == "Media" else "📁 Upload: Document"
    bili_q = u.get("bili_quality", "1080P")
    split_sz = f"✂️ Split: {u.get('split_size_mb', 1950)}M"
    dm_lbl = "📥 Delivery: Bot DM" if u.get("send_to_dm", True) else "💬 Delivery: Group"
    danmaku_lbl = "💬 Danmaku: ON" if u.get("download_danmaku") else "💬 Danmaku: OFF"
    autodel_lbl = "⏳ Disappear: ✅ ON" if u.get("auto_delete_status", False) else "⏳ Disappear: ❌ OFF"
    conc_lbl = f"⚡ Concurrency: {u.get('concurrent_videos', 4)}x"
    eng_short = u.get("engine", "BBDown - WEB").replace("BBDown - ", "").split()[0]
    eng_lbl = f"⚙️ Engine: {eng_short}"

    arc_fmt = u.get("archive_format", "zip").upper()
    arc_btn_lbl = f"📦 Format: {arc_fmt}"

    sess = SettingsManager.get_sessdata(user_id)
    cookie_lbl = "🍪 SESSDATA: ✅" if sess else "🍪 SESSDATA: ❌"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"📺 Quality: {bili_q}", callback_data=f"uset_quality_{user_id}"),
            InlineKeyboardButton(cookie_lbl, callback_data=f"uset_cookies_{user_id}"),
        ],
        [
            InlineKeyboardButton(conc_lbl, callback_data=f"uset_conc_{user_id}"),
            InlineKeyboardButton(eng_lbl, callback_data=f"uset_engine_{user_id}"),
        ],
        [
            InlineKeyboardButton(stream_lbl, callback_data=f"uset_toggle_stream_{user_id}"),
            InlineKeyboardButton(split_sz, callback_data=f"uset_split_{user_id}"),
        ],
        [
            InlineKeyboardButton(arc_btn_lbl, callback_data=f"uset_arcfmt_{user_id}"),
            InlineKeyboardButton(danmaku_lbl, callback_data=f"uset_toggle_danmaku_{user_id}"),
        ],
        [
            InlineKeyboardButton(autodel_lbl, callback_data=f"uset_toggle_autodel_{user_id}"),
            InlineKeyboardButton(dm_lbl, callback_data=f"uset_toggle_dm_{user_id}"),
        ],
        [
            InlineKeyboardButton("📁 Drive Settings", callback_data=f"uset_drive_{user_id}"),
            InlineKeyboardButton("☁️ Cloud (Gofile/PD/RC)", callback_data=f"uset_cloud_{user_id}"),
        ],
        [
            InlineKeyboardButton("🖼 Thumbnail", callback_data=f"uset_thumb_{user_id}"),
            InlineKeyboardButton("✏️ Captions", callback_data=f"uset_captions_{user_id}"),
        ],
        [
            InlineKeyboardButton("🗂 Dump Channel", callback_data=f"uset_dump_{user_id}"),
            InlineKeyboardButton("🔄 Reset All", callback_data=f"uset_reset_{user_id}"),
        ],
        [
            InlineKeyboardButton("❌ Close Menu", callback_data="uset_close"),
        ],
    ])


def get_drive_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📁 Browse & Select Drive Folder", callback_data=f"df_browse_{user_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Set Drive Subfolder Name", callback_data=f"input_drive_folder_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔑 Set Drive Folder ID (API)", callback_data=f"input_drive_id_{user_id}"),
            InlineKeyboardButton("🗑 Clear Folder ID", callback_data=f"clear_drive_id_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_bili_quality_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("8K Ultra HD", callback_data=f"set_biliq_{user_id}_8K"),
            InlineKeyboardButton("4K Dolby/HDR", callback_data=f"set_biliq_{user_id}_4K"),
        ],
        [
            InlineKeyboardButton("1080P+ High Bitrate", callback_data=f"set_biliq_{user_id}_1080P+"),
            InlineKeyboardButton("1080P Full HD", callback_data=f"set_biliq_{user_id}_1080P"),
        ],
        [
            InlineKeyboardButton("720P HD", callback_data=f"set_biliq_{user_id}_720P"),
            InlineKeyboardButton("480P SD", callback_data=f"set_biliq_{user_id}_480P"),
        ],
        [
            InlineKeyboardButton("🎵 Audio Only (FLAC / 320K)", callback_data=f"set_biliq_{user_id}_Audio"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_split_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("500 MB", callback_data=f"set_split_{user_id}_500"),
            InlineKeyboardButton("1.0 GB", callback_data=f"set_split_{user_id}_1000"),
        ],
        [
            InlineKeyboardButton("1.5 GB", callback_data=f"set_split_{user_id}_1500"),
            InlineKeyboardButton("1.95 GB (Standard Default)", callback_data=f"set_split_{user_id}_1950"),
        ],
        [
            InlineKeyboardButton("3.90 GB (TG Premium Limit)", callback_data=f"set_split_{user_id}_3900"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_archive_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    u = SettingsManager.get_user_settings(user_id)
    cur = u.get("archive_format", "zip").lower()
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{'✅ ' if cur == 'zip' else ''}.ZIP", callback_data=f"set_arcfmt_{user_id}_zip"),
            InlineKeyboardButton(f"{'✅ ' if cur == '7z' else ''}.7Z", callback_data=f"set_arcfmt_{user_id}_7z"),
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if cur == 'rar' else ''}.RAR", callback_data=f"set_arcfmt_{user_id}_rar"),
            InlineKeyboardButton(f"{'✅ ' if cur == 'tar' else ''}.TAR", callback_data=f"set_arcfmt_{user_id}_tar"),
            InlineKeyboardButton(f"{'✅ ' if cur in ['tar.gz', 'tgz'] else ''}.TAR.GZ", callback_data=f"set_arcfmt_{user_id}_tar.gz"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_cookie_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    sess = SettingsManager.get_sessdata(user_id)
    tok_btn = "🔑 Update SESSDATA Token" if sess else "🔑 Set SESSDATA Token"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tok_btn, callback_data=f"input_sessdata_{user_id}"),
        ],
        [
            InlineKeyboardButton("📁 Upload cookies.txt", callback_data=f"prompt_upload_cookies_{user_id}"),
            InlineKeyboardButton("🗑 Delete Cookie", callback_data=f"del_user_cookie_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_cloud_settings_text(user_id: int) -> str:
    u = SettingsManager.get_user_settings(user_id)
    gf = u.get("gofile_token", "")
    gf_disp = f"✅ <code>{gf[:6]}...{gf[-4:]}</code> (Active)" if gf else "❌ None (Anonymous Mode)"
    pd = u.get("pixeldrain_api_key", "") or u.get("pixeldrain_token", "")
    pd_disp = f"✅ <code>{pd[:6]}...{pd[-4:]}</code> (Active)" if pd else "❌ None (Anonymous Mode)"

    from bili_leecher.uploader.cloud_uploader import get_rclone_config_path
    r_conf = get_rclone_config_path()
    r_stat = "✅ Active (Configured)" if os.path.exists(r_conf) else "❌ Missing (Drop rclone.conf in chat)"

    return (
        f"<b>☁️ Cloud Storage & Mirror Settings</b>\n\n"
        f"╭⌬ <b>Gofile Token   :</b> {gf_disp}\n"
        f"├⌬ <b>PixelDrain Key :</b> {pd_disp}\n"
        f"╰⌬ <b>Rclone Config  :</b> {r_stat}\n\n"
        f"<i>Configure your personal accounts below, or upload your <code>rclone.conf</code> directly into chat!</i>"
    )


def get_cloud_settings_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📁 Set Gofile Token", callback_data=f"input_gofile_{user_id}"),
            InlineKeyboardButton("🗑 Clear", callback_data=f"clear_gofile_{user_id}"),
        ],
        [
            InlineKeyboardButton("💧 Set PixelDrain Key", callback_data=f"input_pixeldrain_{user_id}"),
            InlineKeyboardButton("🗑 Clear", callback_data=f"clear_pixeldrain_{user_id}"),
        ],
        [
            InlineKeyboardButton("☁️ View Rclone Remotes", callback_data=f"view_rclone_{user_id}"),
            InlineKeyboardButton("📄 Upload rclone.conf", callback_data=f"prompt_rclone_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_thumb_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑 Delete Custom Thumb", callback_data=f"del_user_thumb_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_dump_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Set Custom Dump Channel ID", callback_data=f"input_dump_{user_id}"),
        ],
        [
            InlineKeyboardButton("🗑 Clear Dump Channel", callback_data=f"clear_dump_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_captions_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Set Prefix", callback_data=f"input_prefix_{user_id}"),
            InlineKeyboardButton("🗑 Clear Prefix", callback_data=f"clear_prefix_{user_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Set Suffix", callback_data=f"input_suffix_{user_id}"),
            InlineKeyboardButton("🗑 Clear Suffix", callback_data=f"clear_suffix_{user_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Custom Caption", callback_data=f"input_caption_{user_id}"),
            InlineKeyboardButton("🗑 Clear Caption", callback_data=f"clear_caption_{user_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_bot_settings_text() -> str:
    b = SettingsManager.get_bot_settings()
    par = b.get("max_parallel_tasks", 4)
    par_txt = f"{par} Parallel Downloads" if par > 0 else "Unlimited"
    sess = b.get("default_sessdata", "")
    sess_disp = f"<code>{sess[:8]}...</code>" if sess else "<i>(None)</i>"
    perm_cnt = len(b.get("permitted_users", []))
    b_autodel = b.get("auto_delete_status", False)
    b_autodel_disp = "✅ ON (Disappear after 30s)" if b_autodel else "❌ OFF (Permanent)"

    return (
        f"<b>🤖 Bot Administration Panel (BiliColabX)</b>\n\n"
        f"╭⌬ <b>Engine:</b> <code>BBDown + DzGram MTProto</code>\n"
        f"├⌬ <b>Max Parallel Tasks:</b> <code>{par_txt}</code>\n"
        f"├⌬ <b>Global SESSDATA:</b> {sess_disp}\n"
        f"├⌬ <b>Msg Disappear:</b> <code>{b_autodel_disp}</code>\n"
        f"╰⌬ <b>Permitted VIP Users:</b> <code>{perm_cnt} users</code>\n"
    )


def get_bot_settings_markup() -> InlineKeyboardMarkup:
    b = SettingsManager.get_bot_settings()
    b_autodel = b.get("auto_delete_status", False)
    b_autodel_lbl = "⏳ Disappear: ✅ ON" if b_autodel else "⏳ Disappear: ❌ OFF"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 Set Global SESSDATA", callback_data="bset_input_sessdata"),
            InlineKeyboardButton("🗑 Clear", callback_data="bset_clear_sessdata"),
        ],
        [
            InlineKeyboardButton("⚙️ Parallel: 2", callback_data="bset_par_2"),
            InlineKeyboardButton("⚙️ Parallel: 4", callback_data="bset_par_4"),
            InlineKeyboardButton("⚙️ Parallel: 6", callback_data="bset_par_6"),
        ],
        [
            InlineKeyboardButton(b_autodel_lbl, callback_data="bset_toggle_autodel"),
            InlineKeyboardButton("⚡ Speedtest", callback_data="bset_speedtest"),
        ],
        [
            InlineKeyboardButton("🧹 Clear Temp", callback_data="bset_cleartemp"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_concurrency_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1x (Sequential)", callback_data=f"set_conc_{user_id}_1"),
            InlineKeyboardButton("2x Parallel", callback_data=f"set_conc_{user_id}_2"),
        ],
        [
            InlineKeyboardButton("3x Parallel", callback_data=f"set_conc_{user_id}_3"),
            InlineKeyboardButton("4x (Default)", callback_data=f"set_conc_{user_id}_4"),
        ],
        [
            InlineKeyboardButton("6x High Speed", callback_data=f"set_conc_{user_id}_6"),
            InlineKeyboardButton("8x Max Extreme", callback_data=f"set_conc_{user_id}_8"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])


def get_engine_menu_markup(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 BBDown - WEB (Highest Compat)", callback_data=f"set_eng_{user_id}_web"),
        ],
        [
            InlineKeyboardButton("📺 BBDown - TV (Fastest Stream)", callback_data=f"set_eng_{user_id}_tv"),
        ],
        [
            InlineKeyboardButton("📱 BBDown - APP (Alternative)", callback_data=f"set_eng_{user_id}_app"),
        ],
        [
            InlineKeyboardButton("🎬 yt-dlp (Universal & Reliable)", callback_data=f"set_eng_{user_id}_ytdl"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Settings", callback_data=f"open_uset_{user_id}"),
            InlineKeyboardButton("❌ Close", callback_data="uset_close"),
        ],
    ])
