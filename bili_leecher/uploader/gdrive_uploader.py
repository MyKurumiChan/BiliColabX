# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Google Drive Direct Upload Engine for Google Colab

import os
import shutil
import logging
import threading
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from bili_leecher.utility.variables import Paths
from bili_leecher.utility.settings_manager import SettingsManager
import asyncio
from time import time
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bili_leecher.utility.helper import sizeUnit, getTime, status_bar

DEFAULT_DRIVE_FOLDER = "BiliColabX_Uploads"
DRIVE_PATH_CACHE = {}


def is_drive_mounted() -> bool:
    """Checks if Google Drive is mounted at /content/drive/MyDrive."""
    return os.path.exists("/content/drive/MyDrive") or os.path.exists(Paths.MOUNTED_DRIVE)


def get_drive_base_root() -> str:
    """Returns the primary Google Drive root path on Colab."""
    if os.path.exists("/content/drive/MyDrive"):
        return "/content/drive/MyDrive"
    return Paths.MOUNTED_DRIVE


def get_drive_destination_path(user_id: int = 0, custom_override: str = "") -> str:
    """Returns the target folder inside mounted Google Drive."""
    base_root = get_drive_base_root()
    if custom_override and custom_override.strip():
        folder_clean = custom_override.strip().strip("/\\")
        target = os.path.join(base_root, folder_clean)
    else:
        u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}
        custom_folder = u_conf.get("drive_folder_name", "").strip().strip("/\\") or DEFAULT_DRIVE_FOLDER
        target = os.path.join(base_root, custom_folder)

    os.makedirs(target, exist_ok=True)
    return target


def list_drive_subfolders(rel_path: str = "") -> List[str]:
    """Lists subdirectories inside a given relative path of MyDrive."""
    base_root = get_drive_base_root()
    clean_rel = rel_path.strip().strip("/\\")
    full_path = os.path.join(base_root, clean_rel) if clean_rel else base_root
    
    if not os.path.exists(full_path):
        return []
    
    try:
        dirs = [d for d in os.listdir(full_path) if os.path.isdir(os.path.join(full_path, d)) and not d.startswith(".")]
        return sorted(dirs)
    except Exception as e:
        logging.warning(f"Error listing drive subfolders in {full_path}: {e}")
        return []


def create_drive_folder(folder_path: str) -> str:
    """Creates a folder or nested folder in MyDrive."""
    base_root = get_drive_base_root()
    clean_path = folder_path.strip().strip("/\\")
    full_path = os.path.join(base_root, clean_path)
    os.makedirs(full_path, exist_ok=True)
    return clean_path


def get_drive_browser_text(rel_path: str = "", user_id: int = 0) -> str:
    clean_rel = rel_path.strip().strip("/\\")
    path_disp = f"MyDrive/{clean_rel}" if clean_rel else "MyDrive (Root)"
    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}
    current_default = u_conf.get("drive_folder_name", DEFAULT_DRIVE_FOLDER)

    dirs = list_drive_subfolders(rel_path)
    count_str = f"{len(dirs)} subfolders found" if dirs else "No subfolders inside"

    return (
        f"<b>📁 Google Drive Folder Browser</b>\n\n"
        f"📍 <b>Location:</b> <code>{path_disp}</code>\n"
        f"🎯 <b>Current Target:</b> <code>MyDrive/{current_default}</code>\n"
        f"📂 <i>{count_str}</i>\n\n"
        f"<i>Tap any subfolder to open it, or click <b>Select This Folder</b> to set it as your mirror destination.</i>"
    )


def get_drive_browser_markup(rel_path: str = "", user_id: int = 0) -> InlineKeyboardMarkup:
    clean_rel = rel_path.strip().strip("/\\")
    dirs = list_drive_subfolders(rel_path)

    buttons = []
    row = []
    for d in dirs[:12]:
        sub_rel = f"{clean_rel}/{d}".strip("/") if clean_rel else d
        h_id = f"{abs(hash(sub_rel)) % 10000000:07d}"
        DRIVE_PATH_CACHE[h_id] = sub_rel

        row.append(InlineKeyboardButton(f"📁 {d[:16]}", callback_data=f"dfn_{h_id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    cur_h = f"{abs(hash(clean_rel)) % 10000000:07d}"
    DRIVE_PATH_CACHE[cur_h] = clean_rel

    nav_row = []
    if clean_rel:
        parent_rel = os.path.dirname(clean_rel).replace("\\", "/").strip("/")
        par_h = f"{abs(hash(parent_rel)) % 10000000:07d}"
        DRIVE_PATH_CACHE[par_h] = parent_rel
        nav_row.append(InlineKeyboardButton("⬆️ Up", callback_data=f"dfn_{par_h}"))

    nav_row.append(InlineKeyboardButton("➕ New Folder", callback_data=f"dfm_{cur_h}"))
    buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("✅ Select This Folder", callback_data=f"dfs_{cur_h}"),
        InlineKeyboardButton("🔙 Back to Menu", callback_data=f"uset_drive_{user_id}"),
    ])

    return InlineKeyboardMarkup(buttons)


async def upload_to_google_drive(source_dir: str, user_id: int = 0, task_ctx=None, custom_folder: str = "") -> List[Dict[str, Any]]:
    """
    Direct Google Drive upload mechanism for Google Colab:
    1. If Google Drive is mounted at /content/drive/MyDrive:
       Directly transfers downloaded Bilibili media into the user's personal Google Drive folder!
    2. If a Google Drive Folder ID is configured:
       Uses Google Drive API (MediaFileUpload with chunked resumable upload) to upload directly into that folder!
    """
    if not custom_folder and task_ctx and task_ctx.options.get("drive_folder"):
        custom_folder = task_ctx.options["drive_folder"]

    u_conf = SettingsManager.get_user_settings(user_id) if user_id else {}
    folder_id = u_conf.get("drive_folder_id", "").strip()

    # Collect all video, audio, and subtitle files
    files_to_upload = []
    if os.path.isfile(source_dir):
        files_to_upload.append(source_dir)
    elif os.path.isdir(source_dir):
        for root, _, files in os.walk(source_dir):
            for f in files:
                f_low = f.lower()
                if not f_low.endswith((".part", ".tmp", ".log", ".aria2")):
                    files_to_upload.append(os.path.join(root, f))

    if not files_to_upload:
        logging.warning("No files found to upload to Google Drive.")
        return []

    # Method 1: Drive Folder ID with Google Drive API
    if folder_id:
        try:
            return await _upload_via_drive_api(files_to_upload, folder_id, task_ctx)
        except Exception as e:
            logging.error(f"Drive API upload failed: {e}. Falling back to mounted drive...")

    # Method 2: Native Google Drive Mount (/content/drive/MyDrive)
    if is_drive_mounted():
        dest_dir = get_drive_destination_path(user_id, custom_override=custom_folder)
        return await _copy_to_mounted_drive(files_to_upload, dest_dir, task_ctx)

    # If neither is available, attempt to mount drive if in Colab
    if os.path.exists("/content"):
        try:
            logging.info("Attempting automatic Google Drive mount...")
            from google.colab import drive
            drive.mount("/content/drive", force_remount=False)
            if is_drive_mounted():
                dest_dir = get_drive_destination_path(user_id, custom_override=custom_folder)
                return await _copy_to_mounted_drive(files_to_upload, dest_dir, task_ctx)
        except Exception as me:
            logging.error(f"Auto-mount drive failed: {me}")

    raise RuntimeError("Google Drive is not mounted! Please mount your drive in Colab via `drive.mount('/content/drive')` or set a Drive Folder ID in /usetting.")


async def _copy_to_mounted_drive(files: List[str], dest_dir: str, task_ctx=None) -> List[Dict[str, Any]]:
    """Copies downloaded files to mounted Google Drive folder with live MB/s speed, ETA, and progress."""
    results = []
    total_files = len(files)
    total_all_bytes = sum(os.path.getsize(f) for f in files if os.path.isfile(f))
    cumulative_copied = 0

    CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB high-speed transfer buffer

    for idx, f_path in enumerate(files, 1):
        fname = os.path.basename(f_path)
        f_size = os.path.getsize(f_path)
        target_path = os.path.join(dest_dir, fname)

        if task_ctx:
            task_ctx.status_state = "Drive Mirror 📁"
            task_ctx.engine = "Google Drive 📁"
            task_ctx.task_title = fname
            task_ctx.left = sizeUnit(total_all_bytes if total_files > 1 else f_size)

        logging.info(f"Transferring {fname} ({sizeUnit(f_size)}) to Google Drive: {dest_dir}...")

        file_copied = 0
        start_t = time()
        last_stat_update = 0

        with open(f_path, "rb") as src, open(target_path, "wb") as dst:
            while True:
                if task_ctx and task_ctx.is_cancelled:
                    logging.info("Task cancelled during Drive copy.")
                    try:
                        dst.close()
                        os.remove(target_path)
                    except Exception:
                        pass
                    return results

                chunk = src.read(CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
                file_copied += len(chunk)
                cumulative_copied += len(chunk)

                now = time()
                if now - last_stat_update >= 1.5 or file_copied == f_size:
                    last_stat_update = now
                    dt = max(0.05, now - start_t)
                    spd = file_copied / dt
                    spd_str = f"{sizeUnit(spd)}/s"

                    if total_files > 1:
                        overall_pct = (cumulative_copied / total_all_bytes) * 100.0 if total_all_bytes > 0 else 100.0
                        done_str = f"{sizeUnit(cumulative_copied)} ({idx}/{total_files})"
                        rem_bytes = max(0, total_all_bytes - cumulative_copied)
                    else:
                        overall_pct = (file_copied / f_size) * 100.0 if f_size > 0 else 100.0
                        done_str = sizeUnit(file_copied)
                        rem_bytes = max(0, f_size - file_copied)

                    eta_sec = rem_bytes / spd if spd > 0 else 0
                    eta_str = getTime(eta_sec) if eta_sec > 0 else "0s"

                    if task_ctx:
                        task_ctx.speed = spd_str
                        task_ctx.percentage = round(min(100.0, max(0.5, overall_pct)), 1)
                        task_ctx.eta = eta_str
                        task_ctx.done = done_str
                        task_ctx.left = sizeUnit(total_all_bytes if total_files > 1 else f_size)
                        task_ctx.status_state = f"Mirroring to Drive ({idx}/{total_files})" if total_files > 1 else "Mirroring to Drive 📁"

                        await status_bar(
                            down_msg=f"<b>📁 UPLOADING TO DRIVE » </b><code>{fname}</code>\n",
                            speed=task_ctx.speed,
                            percentage=task_ctx.percentage,
                            eta=task_ctx.eta,
                            done=task_ctx.done,
                            left=task_ctx.left,
                            engine="Google Drive 📁",
                            task_title=fname,
                            task_ctx=task_ctx,
                        )

                await asyncio.sleep(0)  # Yield CPU control to keep event loop responsive

        try:
            shutil.copystat(f_path, target_path)
        except Exception:
            pass

        results.append({
            "name": fname,
            "size": f_size,
            "path": target_path,
            "status": "Saved to MyDrive",
        })

    if task_ctx:
        task_ctx.percentage = 100.0
        task_ctx.status_state = "Drive Upload Complete ✅"
        task_ctx.speed = "Done"
        task_ctx.eta = "0s"
        await status_bar(
            down_msg=f"<b>📁 DRIVE MIRROR COMPLETE » </b><code>{task_ctx.task_title}</code>\n",
            speed="Done",
            percentage=100.0,
            eta="0s",
            done=task_ctx.done,
            left=task_ctx.left,
            engine="Google Drive 📁",
            task_title=task_ctx.task_title,
            task_ctx=task_ctx,
        )

    return results


async def _upload_via_drive_api(files: List[str], folder_id: str, task_ctx=None) -> List[Dict[str, Any]]:
    """Direct API upload using Google Colab default auth / credentials into specified folder ID."""
    from google.colab import auth
    from google.auth import default
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import httplib2
    import google_auth_httplib2

    auth.authenticate_user()
    creds, _ = default()

    http = httplib2.Http(timeout=300)
    http.redirect_codes = http.redirect_codes - {308}
    authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
    service = build("drive", "v3", http=authorized_http, cache_discovery=False)

    results = []
    total_files = len(files)

    for idx, f_path in enumerate(files, 1):
        fname = os.path.basename(f_path)
        f_size = os.path.getsize(f_path)

        if task_ctx:
            task_ctx.status_state = "Drive API 📁"
            task_ctx.engine = "Google Drive 📁"
            task_ctx.task_title = fname

        file_metadata = {
            "name": fname,
            "parents": [folder_id],
        }
        media = MediaFileUpload(f_path, resumable=True, chunksize=10485760)
        request = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink")

        response = None
        start_api_t = time()
        while response is None:
            status, response = request.next_chunk()
            if status and task_ctx:
                prog = getattr(status, "resumable_progress", 0)
                now_t = time()
                el = max(0.1, now_t - start_api_t)
                spd = prog / el if prog > 0 else 0
                rem = max(0, f_size - prog)
                eta_sec = rem / spd if spd > 0 else 0
                pct = int(status.progress() * 100)

                task_ctx.speed = f"{sizeUnit(spd)}/s"
                task_ctx.percentage = float(pct)
                task_ctx.eta = getTime(eta_sec) if eta_sec > 0 else "Syncing"
                task_ctx.done = sizeUnit(prog)
                task_ctx.left = sizeUnit(f_size)
                task_ctx.status_state = "Drive API 📁"

                await status_bar(
                    down_msg=f"<b>📁 UPLOADING TO DRIVE » </b><code>{fname}</code>\n",
                    speed=task_ctx.speed,
                    percentage=pct,
                    eta=task_ctx.eta,
                    done=task_ctx.done,
                    left=task_ctx.left,
                    engine="Google Drive 📁",
                    task_title=fname,
                    task_ctx=task_ctx,
                )

        file_id = response.get("id")
        link = response.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")
        results.append({
            "name": fname,
            "size": f_size,
            "id": file_id,
            "link": link,
            "status": "Uploaded via API",
        })

    return results

