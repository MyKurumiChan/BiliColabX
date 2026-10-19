# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Copyright (c) 2024-2026 BiliColabX

# @title 📺 BiliColabX - Main Colab Leecher Code { display-mode: "form" }

API_ID = 0  # @param {type: "integer"}
API_HASH = ""  # @param {type: "string"}
BOT_TOKEN = ""  # @param {type: "string"}
USER_ID = 0  # @param {type: "integer"}
DUMP_ID = 0  # @param {type: "integer"}
REPO_URL = "https://github.com/MyKurumiChan/BiliColabX"  # @param {type: "string"}
DEFAULT_SESSDATA = ""  # @param {type: "string"}
DEFAULT_RESOLUTION = "1080P"  # @param ["8K", "4K", "1080P+", "1080P", "720P", "480P", "Audio"]
CONCURRENT_VIDEOS = 4  # @param {type:"slider", min:1, max:8, step:1}
MOUNT_GOOGLE_DRIVE = True  # @param {type: "boolean"}
GOOGLE_DRIVE_FOLDER = "BiliColabX_Uploads"  # @param {type: "string"}

import os
import sys
import json
import time
import shutil
import platform
import subprocess
from threading import Thread

banner = r"""

  ____  _ _ _  ____      _       _     __  __
 |  _ \(_) (_)/ ___|___ | | __ _| |__  \ \/ /
 | |_) | | | | |   / _ \| |/ _` | '_ \  \  / 
 |  _ <| | | | |__| (_) | | (_| | |_) | /  \ 
 |_| \_\_|_|_|\____\___/|_|\__,_|_.__/ /_/\_\
                                             
 📺 BiliColabX — Exclusive Bilibili Telegram Leecher & Google Drive Mirror
 ⚡ Powered by BBDown, DzGram MTProto, Aria2c & Rust WarpCrypto
 🌟 Features: 8K/4K/1080P+ VIP, Multi-Part Range, Danmaku, Audio, Google Drive & TG Leech
 💖 Developed for: Google Colab & Bilibili Enthusiasts

"""

print(banner)

# Validate credentials early
missing_creds = []
if not API_ID or str(API_ID).strip() == "0":
    missing_creds.append("API_ID")
if not API_HASH or not str(API_HASH).strip():
    missing_creds.append("API_HASH")
if not BOT_TOKEN or not str(BOT_TOKEN).strip():
    missing_creds.append("BOT_TOKEN")

if missing_creds:
    print("=" * 80)
    print("❌ CONFIGURATION ERROR: Missing Telegram API credentials!")
    print(f"👉 Missing fields: {', '.join(missing_creds)}")
    print("👉 Please fill in API_ID, API_HASH, and BOT_TOKEN in the form parameters above!")
    print("   Get API_ID & API_HASH from: https://my.telegram.org")
    print("   Get BOT_TOKEN from: https://t.me/BotFather")
    print("=" * 80)
    sys.exit(1)

is_colab = os.path.exists("/content")
cwd = os.getcwd()

# Step 1: Clean Google Drive Mount (BEFORE any background thread starts)
if is_colab and MOUNT_GOOGLE_DRIVE:
    if os.path.exists("/content/drive/MyDrive"):
        print("✅ Google Drive is already mounted and accessible at /content/drive/MyDrive")
    else:
        try:
            print("\n🔗 Mounting Google Drive...")
            print("👉 If Colab shows a 'Connect to Google Drive' popup, please click 'Allow/Connect'.")
            from google.colab import drive
            drive.mount("/content/drive", force_remount=False)
            print("✅ Google Drive mounted successfully!\n")
        except Exception as drive_err:
            print(f"⚠️ Google Drive mount skipped or encountered: {drive_err}")
            print("👉 The bot will continue running. You can also click the folder icon on the left sidebar to mount Drive anytime.\n")

Working = True

def Loading():
    white = 37
    black = 0
    while Working:
        print("\r" + "░" * white + "▒▒" + "▓" * black + "▒▒" + "░" * white, end="", flush=True)
        black = (black + 2) % 75
        white = (white - 1) if white != 0 else 37
        time.sleep(1)

_Thread = Thread(target=Loading, name="Prepare", args=())
_Thread.start()

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

if os.path.exists("/content/sample_data"):
    try:
        shutil.rmtree("/content/sample_data")
    except Exception:
        pass

# Determine repo directory
if is_colab:
    repo_name = REPO_URL.rstrip("/").split("/")[-1].replace(".git", "")
    repo_dir = f"/content/{repo_name}"

    if os.path.exists("/content/Bilibili-Dnl") and not os.path.exists(repo_dir):
        repo_dir = "/content/Bilibili-Dnl"
    elif not os.path.exists(repo_dir):
        clone_res = subprocess.run(f"git clone --depth=1 {REPO_URL} {repo_dir}", shell=True, capture_output=True, text=True)
        if clone_res.returncode != 0 or not os.path.exists(repo_dir):
            if os.path.exists("/content/Bilibili-Dnl"):
                repo_dir = "/content/Bilibili-Dnl"
            else:
                Working = False
                try:
                    _Thread.join(timeout=2)
                except Exception:
                    pass
                print("\n" + "=" * 80)
                print(f"❌ REPOSITORY CLONE FAILED for: {REPO_URL}")
                print(f"Error output:\n{clone_res.stderr.strip() or clone_res.stdout.strip()}")
                print("=" * 80)
                sys.exit(1)
    else:
        # If repo directory already exists, ensure latest commits are pulled
        if os.path.exists(os.path.join(repo_dir, ".git")):
            subprocess.run("git pull --rebase", shell=True, cwd=repo_dir, capture_output=True)
else:
    repo_dir = cwd

# Self-heal / hotfix any legacy issues in repo_dir
for c_dir in set([repo_dir, "/content/BiliColabX", "/content/bili_leecher", "/content/Bilibili-Dnl"]):
    bb_path = os.path.join(c_dir, "bili_leecher", "downloader", "bbdown.py")
    if os.path.exists(bb_path):
        try:
            with open(bb_path, "r", encoding="utf-8") as bf:
                txt = bf.read()
            if "-> Tuple[str, bool]:" in txt:
                txt = txt.replace("-> Tuple[str, bool]:", ":")
                with open(bb_path, "w", encoding="utf-8") as bf:
                    bf.write(txt)
        except Exception:
            pass

    bh_path = os.path.join(c_dir, "bili_leecher", "downloader", "bilibili_helper.py")
    if os.path.exists(bh_path):
        try:
            with open(bh_path, "r", encoding="utf-8") as bh:
                txt = bh.read()
            if "def is_bilibili_url" not in txt:
                txt = (
                    "def is_bilibili_url(link: str) -> bool:\n"
                    "    low = str(link).lower().strip()\n"
                    "    return any(d in low for d in ['bilibili.com', 'b23.tv', 'bili2233.cn', 'bilivideo.com'])\n\n"
                    + txt
                )
                with open(bh_path, "w", encoding="utf-8") as bh:
                    bh.write(txt)
        except Exception:
            pass

# Install Linux system packages on Colab / Linux
if platform.system() == "Linux":
    subprocess.run(
        "apt update -qq && apt install -y -qq ffmpeg aria2 mediainfo p7zip-full unrar wget curl unzip",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Auto-install latest BBDown Linux release
    if not shutil.which("BBDown") and not os.path.exists("/usr/local/bin/BBDown"):
        try:
            bbdown_install = (
                "LATEST_RELEASE=$(curl -s https://api.github.com/repos/nilaoda/BBDown/releases/latest "
                "| grep 'browser_download_url.*linux-x64.zip' | cut -d '\"' -f 4) && "
                "wget -qO /tmp/BBDown.zip \"$LATEST_RELEASE\" && "
                "unzip -q -o /tmp/BBDown.zip -d /usr/local/bin/ && "
                "chmod +x /usr/local/bin/BBDown && "
                "rm -f /tmp/BBDown.zip"
            )
            subprocess.run(bbdown_install, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

req_path = os.path.join(repo_dir, "requirements.txt")
if os.path.exists(req_path):
    subprocess.run(f"pip3 install --upgrade -r {req_path}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

credentials = {
    "API_ID": API_ID,
    "API_HASH": API_HASH,
    "BOT_TOKEN": BOT_TOKEN,
    "USER_ID": USER_ID,
    "DUMP_ID": DUMP_ID,
    "DEFAULT_SESSDATA": DEFAULT_SESSDATA,
    "DEFAULT_RESOLUTION": DEFAULT_RESOLUTION,
    "CONCURRENT_VIDEOS": CONCURRENT_VIDEOS,
    "GOOGLE_DRIVE_FOLDER": GOOGLE_DRIVE_FOLDER,
}

with open(os.path.join(repo_dir, "credentials.json"), "w", encoding="utf-8") as f:
    f.write(json.dumps(credentials, indent=2))

# Initialize default user settings with form params
users_settings_path = os.path.join(repo_dir, "users_settings.json")
users_data = {}
if os.path.exists(users_settings_path):
    try:
        with open(users_settings_path, "r", encoding="utf-8") as f:
            users_data = json.load(f)
    except Exception:
        users_data = {}

uid_str = str(USER_ID)
if USER_ID and uid_str != "0":
    u_obj = users_data.get(uid_str, {})
    if "concurrent_videos" not in u_obj:
        u_obj["concurrent_videos"] = int(CONCURRENT_VIDEOS or 4)
    if DEFAULT_SESSDATA and not u_obj.get("sessdata"):
        u_obj["sessdata"] = DEFAULT_SESSDATA
    if DEFAULT_RESOLUTION and not u_obj.get("bili_quality"):
        u_obj["bili_quality"] = DEFAULT_RESOLUTION
    users_data[uid_str] = u_obj
    try:
        with open(users_settings_path, "w", encoding="utf-8") as f:
            json.dump(users_data, f, indent=2)
    except Exception:
        pass

Working = False
try:
    _Thread.join(timeout=3)
except Exception:
    pass

# Pre-flight check
preflight = subprocess.run(
    [
        sys.executable,
        "-c",
        "import bili_leecher; from bili_leecher.downloader.bilibili_helper import is_bilibili_url; from bili_leecher.downloader.bbdown import map_resolution_to_bbdown; from bili_leecher.downloader.manager import downloadManager; print('✅ BiliColabX modules loaded successfully.')",
    ],
    cwd=repo_dir,
    capture_output=True,
    text=True,
)
if preflight.returncode != 0:
    print("\n" + "=" * 80)
    print("❌ PRE-FLIGHT VERIFICATION FAILED:")
    print(preflight.stderr.strip() or preflight.stdout.strip())
    print("=" * 80)
    sys.exit(1)

try:
    from IPython.display import clear_output
    clear_output(wait=True)
except Exception:
    pass

print(banner)

# Remove any previous session files to ensure clean start
for s in ["bilicolabx_bot.session", "my_bot.session"]:
    sp = os.path.join(repo_dir, s)
    if os.path.exists(sp):
        try:
            os.remove(sp)
        except Exception:
            pass

print("\n🚀 Starting BiliColabX Live Engine.... Logs streaming below:\n" + "-" * 80)

proc = subprocess.Popen(
    [sys.executable, "-u", "-m", "bili_leecher"],
    cwd=repo_dir,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

for line in iter(proc.stdout.readline, ""):
    print(line, end="", flush=True)

proc.stdout.close()
return_code = proc.wait()
if return_code != 0:
    print(f"\n⚠️ Bot process terminated with exit code: {return_code}")

