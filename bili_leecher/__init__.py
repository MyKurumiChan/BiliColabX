# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import os
import sys
import json
import logging
from time import time
from pyrogram.client import Client
from pyrogram.enums import ParseMode

# Headless environment configurations (prevent ALSA/SDL sound card errors on Linux/Colab)
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

# DzGram MTProto High-Performance Transfer Tuning (Connection Pooling, Rust WarpCrypto & Adaptive Pacing)
os.environ.setdefault("DZGRAM_BOT_UPLOAD_POOL", "3")
os.environ.setdefault("DZGRAM_BOT_UPLOAD_RATE", "512")
os.environ.setdefault("DZGRAM_BOT_UPLOAD_WORKERS", "4")
os.environ.setdefault("DZGRAM_BOT_DL_POOL", "3")
os.environ.setdefault("DZGRAM_BOT_DL_WORKERS", "4")
os.environ.setdefault("DZGRAM_CRYPTO_WORKERS", "4")
os.environ.setdefault("DZGRAM_MEDIA_SESSION_IDLE_TIMEOUT", "180")

# Clean logging: filter out internal MTProto connection/ping noise
logging.getLogger("pyrogram.session.session").setLevel(logging.ERROR)
logging.getLogger("pyrogram.session.auth").setLevel(logging.WARNING)
logging.getLogger("pyrogram.connection.connection").setLevel(logging.WARNING)

bot_start_time = time()

try:
    from uvloop import install
    install()
except Exception:
    pass

# Read the dictionary from the credentials file
base_repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
possible_cred_paths = [
    os.path.join(base_repo_dir, "credentials.json"),
    os.path.join(os.getcwd(), "credentials.json"),
    "/content/BiliColabX/credentials.json",
    "/content/Bilibili-Dnl/credentials.json",
    "/content/TGColabX/credentials.json",
    "/content/TG-Leecher-Testimh/credentials.json",
]

cred_path = None
for p in possible_cred_paths:
    if os.path.exists(p):
        cred_path = p
        break

credentials = {}
if cred_path and os.path.exists(cred_path):
    try:
        with open(cred_path, "r", encoding="utf-8") as file:
            credentials = json.loads(file.read())
    except Exception as e:
        print(f"Error loading credentials.json: {e}")

API_ID = int(credentials.get("API_ID") or os.environ.get("API_ID", 0) or 0)
API_HASH = str(credentials.get("API_HASH") or os.environ.get("API_HASH", ""))
BOT_TOKEN = str(credentials.get("BOT_TOKEN") or os.environ.get("BOT_TOKEN", ""))
OWNER = int(credentials.get("USER_ID") or os.environ.get("USER_ID") or os.environ.get("OWNER", 0) or 0)
DUMP_ID = credentials.get("DUMP_ID") or os.environ.get("DUMP_ID", 0)

dump_str = str(DUMP_ID).strip()
if dump_str and dump_str != "0":
    if not dump_str.startswith("-100"):
        if dump_str.startswith("-"):
            dump_str = dump_str[1:]
        if dump_str.startswith("100"):
            dump_str = "-" + dump_str
        else:
            dump_str = "-100" + dump_str
    try:
        DUMP_ID = int(dump_str)
    except ValueError:
        pass

# Real-time unbuffered logging for Google Colab and terminals
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pyrogram.*")
warnings.filterwarnings("ignore", message=".*link_preview_options.*")

logging.getLogger("pyrogram.syncer").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session").setLevel(logging.WARNING)
logging.getLogger("pyrogram.connection").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

if not API_ID or not BOT_TOKEN or not API_HASH:
    logging.warning("⚠️ Telegram credentials not fully set (API_ID, API_HASH, or BOT_TOKEN is empty).")

client_kwargs = {
    "api_id": API_ID,
    "api_hash": API_HASH,
    "bot_token": BOT_TOKEN,
    "parse_mode": ParseMode.HTML,
    "workers": 16,
}
try:
    import inspect
    sig = inspect.signature(Client.__init__)
    if "max_concurrent_transmissions" in sig.parameters:
        client_kwargs["max_concurrent_transmissions"] = 10
    if "link_preview_options" in sig.parameters:
        try:
            from pyrogram.types import LinkPreviewOptions
            client_kwargs["link_preview_options"] = LinkPreviewOptions(is_disabled=True)
        except Exception:
            pass
except Exception:
    pass

colab_bot = Client("bilicolabx_bot", **client_kwargs)

