# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import re
import json
import logging
import urllib.parse
import urllib.request
import aiohttp
from typing import Dict, Any, List, Tuple


def is_bilibili_url(link: str) -> bool:
    """Checks if the URL is a Bilibili video, audio, collection, series, or short link."""
    low = str(link).lower().strip()
    return any(domain in low for domain in [
        "bilibili.com",
        "b23.tv",
        "bili2233.cn",
        "bilivideo.com",
    ])


def normalize_bilibili_url(url: str) -> str:
    """
    Cleans and auto-corrects Bilibili URLs for maximum BBDown compatibility.
    - Resolves space collections / series lists by appending '?type=series'
    - Strips tracking query parameters except crucial ones (sid, fid, ep_id, p, type)
    """
    url = url.strip()

    # Expand short links like b23.tv
    if "b23.tv" in url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                url = resp.geturl()
        except Exception as e:
            logging.warning(f"Failed to expand b23.tv link: {e}")

    # Fix space lists format
    if "space.bilibili.com" in url and "/lists/" in url:
        if "?" not in url:
            url = f"{url}?type=series"
        elif "type=" not in url:
            url = f"{url}&type=series"

    return url


def parse_bilibili_id(url: str):
    """
    Extracts ID type and ID value from Bilibili URL.
    Returns: ('bvid', 'BV...') or ('aid', 'av...') or ('ep', 'ep...') or ('ss', 'ss...') or ('url', url)
    """
    bv_m = re.search(r"(BV[a-zA-Z0-9]+)", url)
    if bv_m:
        return "bvid", bv_m.group(1)

    av_m = re.search(r"av(\d+)", url, re.IGNORECASE)
    if av_m:
        return "aid", av_m.group(1)

    ep_m = re.search(r"ep(\d+)", url)
    if ep_m:
        return "ep", ep_m.group(1)

    ss_m = re.search(r"ss(\d+)", url)
    if ss_m:
        return "ss", ss_m.group(1)

    return "url", url


def parse_range_spec(range_text: str):
    """
    Parses range string like '1-10', '5', '1 20', 'P1-P5' into (start_part, end_part).
    Returns (1, 1) default if not specified.
    """
    if not range_text:
        return 1, 1

    clean = range_text.lower().replace("p", "").strip()
    if "-" in clean:
        parts = clean.split("-")
        try:
            s = int(parts[0].strip())
            e = int(parts[1].strip())
            return min(s, e), max(s, e)
        except Exception:
            return 1, 1

    sp = clean.split()
    if len(sp) == 2:
        try:
            s = int(sp[0].strip())
            e = int(sp[1].strip())
            return min(s, e), max(s, e)
        except Exception:
            return 1, 1

    if clean.isdigit():
        val = int(clean)
        return val, val

    return 1, 1


async def fetch_bilibili_info(url: str, sessdata: str = "") -> Dict[str, Any]:
    """
    Fetches rich Bilibili video/bangumi metadata using public Web APIs.
    Returns a dictionary with title, cover, duration, uploader, part count, parts list.
    """
    clean_url = normalize_bilibili_url(url)
    id_type, id_val = parse_bilibili_id(clean_url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    }
    if sessdata:
        headers["Cookie"] = f"SESSDATA={sessdata}"

    result = {
        "title": "Bilibili Video",
        "pic": "",
        "owner": "Bilibili Uploader",
        "duration": 0,
        "part_count": 1,
        "parts": [],
        "is_playlist": False,
        "desc": "",
        "bvid": id_val if id_type == "bvid" else "",
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Standard Video API
            if id_type in ["bvid", "aid"]:
                param = f"bvid={id_val}" if id_type == "bvid" else f"aid={id_val}"
                api_url = f"https://api.bilibili.com/x/web-interface/view?{param}"
                async with session.get(api_url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == 0 and "data" in data:
                            d = data["data"]
                            result["title"] = d.get("title", result["title"])
                            result["pic"] = d.get("pic", "")
                            result["owner"] = d.get("owner", {}).get("name", result["owner"])
                            result["duration"] = d.get("duration", 0)
                            result["desc"] = d.get("desc", "")
                            pages = d.get("pages", [])
                            result["part_count"] = len(pages)
                            result["is_playlist"] = len(pages) > 1
                            for p in pages:
                                result["parts"].append({
                                    "page": p.get("page", 1),
                                    "part": p.get("part", f"Part {p.get('page')}"),
                                    "duration": p.get("duration", 0),
                                    "cid": p.get("cid", 0),
                                })
                            return result

            # 2. Anime / Bangumi API
            elif id_type in ["ep", "ss"]:
                param = f"ep_id={id_val}" if id_type == "ep" else f"season_id={id_val}"
                api_url = f"https://api.bilibili.com/pgc/view/web/season?{param}"
                async with session.get(api_url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("code") == 0 and "result" in data:
                            r = data["result"]
                            result["title"] = r.get("title", result["title"])
                            result["pic"] = r.get("cover", "")
                            result["owner"] = "Bilibili Bangumi"
                            episodes = r.get("episodes", [])
                            result["part_count"] = len(episodes)
                            result["is_playlist"] = len(episodes) > 1
                            for idx, ep in enumerate(episodes, 1):
                                result["parts"].append({
                                    "page": idx,
                                    "part": ep.get("show_title", f"Episode {idx}"),
                                    "duration": ep.get("duration", 0),
                                    "cid": ep.get("cid", 0),
                                })
                            return result

    except Exception as e:
        logging.warning(f"Error fetching Bilibili info from API: {e}")

    return result

