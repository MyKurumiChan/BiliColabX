# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Cloud Upload Engine: Gofile, PixelDrain & Rclone Integration

import os
import re
import json
import base64
import random
import logging
import asyncio
import subprocess
from time import time
from datetime import datetime
from typing import List, Dict, Any, Optional

import aiohttp
from bili_leecher.utility.helper import sizeUnit, getTime, status_bar, getSize
from bili_leecher.utility.settings_manager import SettingsManager

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


class AsyncProgressFileReader:
    """Async file reader with live progress tracking for aiohttp streaming uploads."""
    def __init__(self, filepath, callback=None):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.total_size = os.path.getsize(filepath)
        self.callback = callback
        self.uploaded = 0
        self.file_obj = None

    async def __aenter__(self):
        self.file_obj = open(self.filepath, "rb")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.file_obj:
            self.file_obj.close()

    def read(self, chunk_size=1024 * 512):
        chunk = self.file_obj.read(chunk_size)
        if chunk:
            self.uploaded += len(chunk)
            if self.callback:
                self.callback(self.uploaded, self.total_size)
        return chunk


# ==================== GOFILE UPLOADER ====================

async def get_gofile_server() -> str:
    """Fetches an active best Gofile upload server."""
    url = "https://api.gofile.io/servers"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"User-Agent": BROWSER_UA}, timeout=15) as resp:
                data = await resp.json()
                if data.get("status") == "ok" and data.get("data", {}).get("servers"):
                    servers = data["data"]["servers"]
                    return random.choice(servers)["name"]
    except Exception as e:
        logging.warning(f"Error fetching Gofile server: {e}")
    return "store1"


async def upload_file_to_gofile(file_path: str, token: str = "", folder_id: str = "", task_ctx=None) -> dict:
    """
    Uploads a single file to Gofile using official API with live speed and progress streaming.
    Returns: {"url": download_link, "name": filename, "size": filesize, "file_id": id}
    """
    user_id = task_ctx.chat_id if task_ctx else None
    if not token and user_id:
        u_conf = SettingsManager.get_user_settings(user_id)
        token = u_conf.get("gofile_token", "")
    if not token:
        b_conf = SettingsManager.get_bot_settings()
        token = b_conf.get("gofile_token", "")

    server = await get_gofile_server()
    upload_url = f"https://{server}.gofile.io/uploadfile"
    file_name = os.path.basename(file_path)
    total_size = os.path.getsize(file_path)
    start_t = time()
    last_update_t = 0

    async def progress_hook(uploaded, total):
        nonlocal last_update_t
        now = time()
        if now - last_update_t >= 1.5 or uploaded == total:
            last_update_t = now
            elapsed = max(0.1, now - start_t)
            speed = uploaded / elapsed
            pct = round((uploaded / total) * 100, 1) if total > 0 else 0
            rem_bytes = max(0, total - uploaded)
            eta_sec = rem_bytes / speed if speed > 0 else 0

            if task_ctx:
                task_ctx.done = sizeUnit(uploaded)
                task_ctx.left = sizeUnit(total)
                task_ctx.speed = f"{sizeUnit(speed)}/s"
                task_ctx.eta = getTime(eta_sec)
                task_ctx.percentage = pct
                task_ctx.status_state = "Gofile Upload 🚀"
                task_ctx.engine = "Gofile 📁"
                await status_bar(
                    down_msg=f"<b>📁 UPLOADING TO GOFILE » </b><code>{file_name}</code>\n",
                    speed=task_ctx.speed,
                    percentage=pct,
                    eta=task_ctx.eta,
                    done=task_ctx.done,
                    left=task_ctx.left,
                    engine="Gofile 📁",
                    task_title=file_name,
                    task_ctx=task_ctx,
                )

    logging.info(f"Uploading {file_name} ({sizeUnit(total_size)}) to Gofile server {server}...")

    data = aiohttp.FormData()
    if token:
        data.add_field("token", token)
    if folder_id:
        data.add_field("folderId", folder_id)

    loop = asyncio.get_event_loop()

    def sync_progress_callback(uploaded, total):
        asyncio.run_coroutine_threadsafe(progress_hook(uploaded, total), loop)

    async with AsyncProgressFileReader(file_path, sync_progress_callback) as pfile:
        data.add_field("file", pfile.file_obj, filename=file_name)
        async with aiohttp.ClientSession() as session:
            async with session.post(upload_url, data=data, timeout=aiohttp.ClientTimeout(total=7200)) as resp:
                res = await resp.json(content_type=None)

    if res.get("status") == "ok":
        d_page = res["data"]["downloadPage"]
        logging.info(f"Gofile upload complete! Link: {d_page}")
        return {
            "url": d_page,
            "name": file_name,
            "size": total_size,
            "code": res["data"].get("code"),
            "file_id": res["data"].get("fileId"),
        }
    else:
        raise RuntimeError(f"Gofile upload error: {res.get('status')} - {res.get('error', '')}")


async def upload_path_to_gofile(path: str, user_id: int = None, task_ctx=None) -> list:
    """Uploads file or directory to Gofile. Returns list of uploaded items."""
    results = []
    if os.path.isfile(path):
        res = await upload_file_to_gofile(path, task_ctx=task_ctx)
        results.append(res)
    elif os.path.isdir(path):
        for root, _, files in os.walk(path):
            for f in sorted(files):
                if task_ctx and task_ctx.is_cancelled:
                    break
                fp = os.path.join(root, f)
                if not f.lower().endswith((".part", ".aria2", ".tmp", ".log")):
                    res = await upload_file_to_gofile(fp, task_ctx=task_ctx)
                    results.append(res)
    return results


# ==================== PIXELDRAIN UPLOADER ====================

async def upload_file_to_pixeldrain(file_path: str, api_key: str = "", task_ctx=None) -> dict:
    """
    Uploads a single file to Pixeldrain using PUT /api/file/{filename} with live progress.
    Supports user personal API key or anonymous upload.
    Returns: {"url": download_link, "name": filename, "size": filesize, "id": file_id}
    """
    user_id = task_ctx.chat_id if task_ctx else None
    if not api_key and user_id:
        u_conf = SettingsManager.get_user_settings(user_id)
        api_key = u_conf.get("pixeldrain_api_key", "") or u_conf.get("pixeldrain_token", "")
    if not api_key:
        b_conf = SettingsManager.get_bot_settings()
        api_key = b_conf.get("pixeldrain_api_key", "") or b_conf.get("pixeldrain_token", "")

    file_name = os.path.basename(file_path).replace(" ", ".")
    total_size = os.path.getsize(file_path)
    start_t = time()
    upload_url = f"https://pixeldrain.com/api/file/{file_name}"
    last_update_t = 0

    headers = {"User-Agent": BROWSER_UA}
    if api_key:
        auth_str = base64.b64encode(f":{api_key}".encode()).decode()
        headers["Authorization"] = f"Basic {auth_str}"

    async def progress_hook(uploaded, total):
        nonlocal last_update_t
        now = time()
        if now - last_update_t >= 1.5 or uploaded == total:
            last_update_t = now
            elapsed = max(0.1, now - start_t)
            speed = uploaded / elapsed
            pct = round((uploaded / total) * 100, 1) if total > 0 else 0
            rem_bytes = max(0, total - uploaded)
            eta_sec = rem_bytes / speed if speed > 0 else 0

            if task_ctx:
                task_ctx.done = sizeUnit(uploaded)
                task_ctx.left = sizeUnit(total)
                task_ctx.speed = f"{sizeUnit(speed)}/s"
                task_ctx.eta = getTime(eta_sec)
                task_ctx.percentage = pct
                task_ctx.status_state = "Pixeldrain Upload ⚡"
                task_ctx.engine = "Pixeldrain ⚡"
                await status_bar(
                    down_msg=f"<b>⚡ UPLOADING TO PIXELDRAIN » </b><code>{file_name}</code>\n",
                    speed=task_ctx.speed,
                    percentage=pct,
                    eta=task_ctx.eta,
                    done=task_ctx.done,
                    left=task_ctx.left,
                    engine="Pixeldrain ⚡",
                    task_title=file_name,
                    task_ctx=task_ctx,
                )

    logging.info(f"Uploading {file_name} ({sizeUnit(total_size)}) to Pixeldrain...")

    loop = asyncio.get_event_loop()

    def sync_progress_callback(uploaded, total):
        asyncio.run_coroutine_threadsafe(progress_hook(uploaded, total), loop)

    async with AsyncProgressFileReader(file_path, sync_progress_callback) as pfile:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.put(upload_url, data=pfile.file_obj, timeout=aiohttp.ClientTimeout(total=7200)) as resp:
                res = await resp.json(content_type=None)

    if res.get("success") or "id" in res:
        file_id = res.get("id")
        dl_link = f"https://pixeldrain.com/u/{file_id}"
        logging.info(f"Pixeldrain upload complete! Link: {dl_link}")
        return {
            "url": dl_link,
            "id": file_id,
            "name": file_name,
            "size": total_size,
        }
    else:
        raise RuntimeError(f"Pixeldrain upload error: {res.get('message', 'Upload rejected')}")


async def create_pixeldrain_list(title: str, file_ids: list, api_key: str = "") -> str:
    """Creates a Pixeldrain List containing multiple uploaded files."""
    if not api_key:
        return ""
    headers = {
        "User-Agent": BROWSER_UA,
        "Authorization": f"Basic {base64.b64encode(f':{api_key}'.encode()).decode()}",
    }
    payload = {
        "title": title,
        "anonymous": False,
        "files": [{"id": fid} for fid in file_ids],
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post("https://pixeldrain.com/api/list", json=payload, timeout=20) as resp:
            data = await resp.json(content_type=None)
            if data.get("success") and "id" in data:
                return f"https://pixeldrain.com/l/{data['id']}"
    return ""


async def upload_path_to_pixeldrain(path: str, user_id: int = None, task_ctx=None) -> list:
    """Uploads file or directory to Pixeldrain, packaging directories into a list if possible."""
    results = []
    if os.path.isfile(path):
        res = await upload_file_to_pixeldrain(path, task_ctx=task_ctx)
        results.append(res)
    elif os.path.isdir(path):
        file_ids = []
        for root, _, files in os.walk(path):
            for f in sorted(files):
                if task_ctx and task_ctx.is_cancelled:
                    break
                fp = os.path.join(root, f)
                if not f.lower().endswith((".part", ".aria2", ".tmp", ".log")):
                    res = await upload_file_to_pixeldrain(fp, task_ctx=task_ctx)
                    results.append(res)
                    if res.get("id"):
                        file_ids.append(res["id"])

        if len(file_ids) > 1:
            try:
                list_url = await create_pixeldrain_list(os.path.basename(path), file_ids)
                if list_url:
                    results.append({"url": list_url, "name": f"List: {os.path.basename(path)}", "size": getSize(path)})
            except Exception as le:
                logging.warning(f"Pixeldrain list creation note: {le}")
    return results


# ==================== RCLONE MIRROR UPLOADER ====================

def get_rclone_config_path() -> str:
    """Returns path to rclone.conf."""
    from bili_leecher.utility.variables import Paths
    default_paths = [
        os.path.join(Paths.WORK_PATH, "rclone.conf"),
        os.path.join(os.getcwd(), "rclone.conf"),
        "/content/rclone.conf",
        "/root/.config/rclone/rclone.conf",
        os.path.expanduser("~/.config/rclone/rclone.conf"),
    ]
    for p in default_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return "/root/.config/rclone/rclone.conf"


async def list_rclone_remotes() -> List[str]:
    """Returns list of configured rclone remotes."""
    try:
        cmd = ["rclone", "listremotes"]
        conf_path = get_rclone_config_path()
        if os.path.exists(conf_path):
            cmd.extend(["--config", conf_path])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return [line.strip().rstrip(":") for line in stdout.decode().splitlines() if line.strip()]
    except Exception as e:
        logging.warning(f"Error checking rclone remotes: {e}")
    return []


async def upload_path_via_rclone(source_path: str, remote_target: str, task_ctx=None) -> Dict[str, Any]:
    """
    Mirrors files or directories to any cloud supported by Rclone (OneDrive, Mega, Dropbox, S3, FTP, etc.).
    Parses live progress and streams speed, ETA, and percentage into Telegram.
    """
    if task_ctx:
        task_ctx.status_state = "Rclone Mirror ☁️"
        task_ctx.engine = f"Rclone: {remote_target}"

    cmd = [
        "rclone", "copy", source_path, remote_target,
        "--progress",
        "--stats-one-line",
        "--stats", "1.5s",
        "--transfers", "8",
        "--checkers", "16",
        "--buffer-size", "64M",
        "--drive-chunk-size", "64M",
    ]

    conf_path = get_rclone_config_path()
    if os.path.exists(conf_path):
        cmd.extend(["--config", conf_path])

    logging.info(f"Starting Rclone mirror command: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    pattern_rclone = re.compile(
        r"([0-9.]+\s*[KMGT]?i?B)\s*/\s*([0-9.]+\s*[KMGT]?i?B),\s*([0-9.]+)%,\s*([0-9.]+\s*[KMGT]?i?B/s),\s*ETA\s*([0-9a-zA-Z:]+)",
        re.IGNORECASE,
    )

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        l_str = line.decode("utf-8", errors="ignore").strip()
        m = pattern_rclone.search(l_str)
        if m and task_ctx:
            done_s, tot_s, pct_s, spd_s, eta_s = m.groups()
            task_ctx.done = done_s
            task_ctx.left = tot_s
            task_ctx.percentage = float(pct_s)
            task_ctx.speed = spd_s
            task_ctx.eta = eta_s
            task_ctx.status_state = "Rclone Mirror ☁️"
            await status_bar(
                down_msg=f"<b>☁️ RCLONE MIRROR » </b><code>{remote_target}</code>\n",
                speed=task_ctx.speed,
                percentage=task_ctx.percentage,
                eta=task_ctx.eta,
                done=task_ctx.done,
                left=task_ctx.left,
                engine=f"Rclone: {remote_target}",
                task_title=remote_target,
                task_ctx=task_ctx,
            )

    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Rclone transfer failed with exit code: {proc.returncode}")

    return {
        "status": "success",
        "remote": remote_target,
        "name": os.path.basename(source_path),
        "size": getSize(source_path),
    }

