# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Cloud Direct Downloader: Gofile & PixelDrain Resolver & Aria2c Engine

import os
import re
import logging
import asyncio
import aiohttp
from typing import Tuple, Optional
from urllib.parse import urlparse

from bili_leecher.utility.variables import Paths
from bili_leecher.utility.helper import sizeUnit, getTime, status_bar
from bili_leecher.downloader.bbdown import read_stream_lines, parse_size_to_bytes

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def is_cloud_download_url(url: str) -> bool:
    """Checks if the URL is from Gofile or PixelDrain."""
    low = url.lower()
    return any(d in low for d in ["pixeldrain.com", "gofile.io"])


async def resolve_pixeldrain_url(url: str) -> Tuple[str, str]:
    """Resolves a PixelDrain view link to direct stream URL and filename."""
    m = re.search(r"pixeldrain\.com/(?:u|api/file)/([a-zA-Z0-9]+)", url)
    if not m:
        return url, "pixeldrain_file"
    file_id = m.group(1)
    direct_url = f"https://pixeldrain.com/api/file/{file_id}"
    
    filename = f"pixeldrain_{file_id}"
    try:
        info_url = f"https://pixeldrain.com/api/file/{file_id}/info"
        async with aiohttp.ClientSession() as session:
            async with session.get(info_url, headers={"User-Agent": BROWSER_UA}, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("name"):
                        filename = data["name"]
    except Exception as e:
        logging.warning(f"Failed to fetch PixelDrain file info: {e}")

    return direct_url, filename


async def resolve_gofile_url(url: str) -> Tuple[str, str]:
    """Resolves a Gofile content link to direct download link and filename."""
    m = re.search(r"gofile\.io/d/([a-zA-Z0-9]+)", url)
    if not m:
        return url, "gofile_file"
    content_id = m.group(1)
    
    api_url = f"https://api.gofile.io/contents/{content_id}?wt=4fd6sg89d7s6"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers={"User-Agent": BROWSER_UA}, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "ok" and data.get("data", {}).get("children"):
                        children = data["data"]["children"]
                        # First child
                        first_id = next(iter(children))
                        child_info = children[first_id]
                        direct_link = child_info.get("link")
                        name = child_info.get("name", f"gofile_{content_id}")
                        if direct_link:
                            return direct_link, name
    except Exception as e:
        logging.warning(f"Failed to resolve Gofile link: {e}")

    return url, f"gofile_{content_id}"


async def download_cloud_url(url: str, task_ctx=None):
    """
    Downloads files from PixelDrain or Gofile using Aria2c with full 16-thread acceleration.
    """
    down_dir = task_ctx.down_path if task_ctx else Paths.down_path
    os.makedirs(down_dir, exist_ok=True)

    if "pixeldrain.com" in url.lower():
        direct_url, fname = await resolve_pixeldrain_url(url)
        engine_label = "PixelDrain ⚡"
    else:
        direct_url, fname = await resolve_gofile_url(url)
        engine_label = "Gofile 📁"

    if task_ctx:
        task_ctx.task_title = fname
        task_ctx.status_state = "Downloading"
        task_ctx.engine = engine_label

    logging.info(f"Downloading from {engine_label}: {direct_url} -> {down_dir}/{fname}")

    cmd = [
        "aria2c",
        direct_url,
        "-d", down_dir,
        "-o", fname,
        "--console-log-level=warn",
        "--summary-interval=1",
        "-x", "16",
        "-s", "16",
        "-j", "16",
        "-k", "1M",
        "--min-split-size=1M",
        "--max-connection-per-server=16",
        "--split=16",
        "--file-allocation=falloc",
        "--disk-cache=64M",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    pattern_aria2 = re.compile(
        r"\[#\w+\s+([0-9.]+\s*[KMGT]?i?B)\s*/\s*([0-9.]+\s*[KMGT]?i?B)\s*\(?([0-9.]+)%\)?.*?DL:\s*([0-9.]+\s*[KMGT]?i?B)(?:.*?ETA:\s*([0-9a-zA-Z:]+))?",
        re.IGNORECASE,
    )

    async for line in read_stream_lines(proc.stdout):
        m_a2 = pattern_aria2.search(line)
        if m_a2 and task_ctx:
            p_done, p_tot, p_pct, p_spd, p_eta = m_a2.groups()
            task_ctx.percentage = float(p_pct)
            task_ctx.done = p_done.strip()
            task_ctx.left = p_tot.strip()
            task_ctx.speed = f"{p_spd.strip()}/s"
            if p_eta:
                task_ctx.eta = p_eta.strip()
            task_ctx.total_size = parse_size_to_bytes(p_tot)

            await status_bar(
                down_msg=f"<b>📥 DOWNLOADING » </b><code>{fname}</code>\n",
                speed=task_ctx.speed,
                percentage=task_ctx.percentage,
                eta=task_ctx.eta,
                done=task_ctx.done,
                left=task_ctx.left,
                engine=engine_label,
                task_title=fname,
                task_ctx=task_ctx,
            )

    await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"Download failed with exit code: {proc.returncode}")

    if task_ctx:
        task_ctx.percentage = 100.0
        task_ctx.status_state = "Complete ✅"

