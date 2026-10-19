# 📺 BiliColabX — Exclusive Bilibili Telegram Leecher & Cloud Mirror

<p align="center">
  <img src="https://cdn.aptoide.com/imgs/3/4/b/34be5e6d6b33fdcfc21a55763966e3f9_fgraphic.jpg" width="520" alt="BiliColabX Logo">
  <br>
  <b>An ultra-fast, clean Telegram Leecher & Multi-Cloud Mirror Bot built exclusively for Bilibili (bilibili.com) on Google Colab.</b><br>
  <i>Powered by BBDown Engine, DzGram MTProto, 16-Thread Aria2c, UPOS CDN Mirrors, Google Drive, PixelDrain, Gofile & Rclone.</i>
</p>

---

## 🌟 Why BiliColabX?

* 🎯 **100% Dedicated to Bilibili**: Completely stripped of bloatware and third-party downloaders. Built from the ground up specifically for **bilibili.com**.
* ⚡ **Live Download Speed & ETA**: Real-time speed and progress calculation based on active disk byte growth and Aria2c stream parsing. Never freezes during FFmpeg audio/video muxing!
* 🚀 **Colab Zero-Bandwidth Google Drive Mirror**: Direct integration with Google Colab (`/content/drive/MyDrive`). Downloaded media is saved directly into your Google Drive without using your home internet bandwidth!
* 📁 **Interactive Google Drive Folder Browser**: Browse MyDrive subfolders with inline buttons (`/dfolder`), create new folders on the fly, and set destination folders dynamically.
* ☁️ **Gofile, PixelDrain & Rclone Integration**: Mirror directly to Gofile (`-gf`), PixelDrain (`-pd`), or any of 50+ Rclone remotes (`-rc remote:path`), with zip archiving (`-z`) and clickable URLs delivered in Telegram upon completion!
* 📄 **Direct File Drag-and-Drop**: Simply drop your `rclone.conf` or `cookies.txt` directly into Telegram chat — the bot auto-installs and activates them instantly!
* ⚡ **Configurable Concurrency (Default: 4x)**: Download multiple parts or multiple links concurrently. Default concurrency is set to 4 and can be customized anytime per download (`-conc 6`) or in `/usetting`.
* 🌐 **Multi-Engine Routing**: Choose between **BBDown WEB** (highest compatibility, VIP 8K/4K/1080P+), **BBDown TV** (fastest streaming), **BBDown APP**, or **yt-dlp** via simple flags (`-web`, `-tv`, `-app`, `-ytdl`).
* 🚀 **UPOS CDN Acceleration**: Uses high-speed mirror hosts (`upos-sz-mirrorhw.bilivideo.com`) for blazing fast Bilibili downloads on overseas Colab servers.
* 📑 **Multi-Link & Multi-Part (分P) Batch Support**: Paste a single link, an episode range (e.g. `1-20`), or a list of multiple URLs separated by newlines — the bot handles everything automatically.
* 📊 **Per-Part Live Download Status**: Multi-part and batch downloads display individual progress for each concurrent part in real time (e.g. `P1`, `P2`, `P3`), showing each part's separate progress bar, speed, downloaded/total size, ETA, and muxing/merging state!
* 🛡️ **Anti-Ban Delay Staggering**: Automatically staggers parallel video parts to protect your IP from Bilibili HTTP 412/429 anti-bot rate limits.
* 🍪 **VIP Authentication (SESSDATA & cookies.txt)**: Direct support for Bilibili VIP tokens to unlock **8K Ultra HD**, **4K Dolby Vision/HDR**, **1080P 60FPS**, and member-exclusive anime. Configurable per-user (`/usetting`) or globally (`/bsetting`).
* 💬 **Bullet Danmaku & Subtitles**: Download live bullet comments as `.ass` subtitle files (`-dd`) and subtitles (`-sub`).
* 🎵 **Lossless Audio Mode**: Extract original Hi-Res FLAC or 320kbps Dolby Atmos audio streams (`-audio`).
* 🪟 **Live Status Card with Free Space**: Real-time status dashboard displaying active tasks, progress bars, speed, ETA, and live remaining disk space (`Free: XX GB`) and available RAM (`Free: XX GB`).
* 📊 **Colab Server Metrics & Speed Test**: Dedicated `/stats` command with complete breakdowns of CPU cores, RAM, Colab local storage, and Google Drive storage, plus standalone `/speedtest` to measure Colab multi-gigabit network speeds.
* ✅ **Visual Status Ticks**: Clear green ticks (`✅`) across user & bot settings indicating active VIP SESSDATA, mounted Drive, Gofile, PixelDrain, and Rclone configs at a glance.

---

## ⚡ Quick Start: 3 Ways to Download

### 1. Paste Links Directly (Easiest)
Just send any Bilibili link directly to the bot in private chat:
```
https://www.bilibili.com/video/BV1xx411c7mD
```
The bot displays an interactive resolution menu (4K, 1080P+, 1080P, 720P, Audio, Danmaku). Tap your choice and it downloads immediately!

### 2. Multi-Link Batch Download
Paste multiple Bilibili URLs separated by newlines:
```
https://www.bilibili.com/video/BV1k8ZAYAEYa?p=1
https://www.bilibili.com/video/BV1k8ZAYAEYa?p=2
https://www.bilibili.com/video/BV1k8ZAYAEYa?p=3
```
The bot automatically detects batch mode and downloads all links concurrently!

### 3. Using Commands with Flexible Flags
```
/bili https://www.bilibili.com/video/BV1xx411c7mD 1-10 -q 4k -dd
/mirror https://www.bilibili.com/video/BV1xx411c7mD -df Anime/Season1
/mirror https://b23.tv/xxxx -gofile -z
```

---

## 📋 Clean Commands Reference

To keep the bot clean and avoid confusion, all detailed configurations are handled seamlessly via **flags** on `/bili` / `/mirror` or inside the interactive **`/usetting`** dashboard!

### 🔹 Primary Commands
| Command | Aliases | Description |
| :--- | :--- | :--- |
| `/start` | — | Welcome message with direct links to GitHub Repo, Help, Settings & Metrics |
| `/help` | `/h` | Complete usage guide: download options, episode ranges, flags & examples |
| `/bili <url>` | `/b`, `/leech`, `/l` | Download and leech Bilibili video/playlist to Telegram |
| `/mirror <url>` | `/m`, `/drive`, `/gdrive` | Download and save directly to Google Drive or Cloud Targets |
| `/dfolder [name]` | `/browse` | Open interactive Google Drive folder browser or set active folder |
| `/rclone` | `/rc` | List all configured Rclone cloud remotes and mirror syntax |
| `/usetting` | `/usersettings` | Interactive User Settings menu (Drive, Cloud tokens, VIP, Split, Disappear, Concurrency) |
| `/bsetting` | `/botsettings` | Admin panel: Global VIP SESSDATA, parallel limits, speedtest, global auto-disappear |
| `/stats` | `/st`, `/server` | Colab server metrics (CPU cores, RAM breakdown, disk free, Google Drive storage) |
| `/speedtest` | `/speed`, `/sp` | Standalone Colab network speed test (Ping, Download, Upload speeds) |
| `/status` | `/s` | Live single-window download dashboard with free space info |
| `/cancel <id>` | `/c` | Cancel a specific running task |
| `/cancelall` | `/call` | Cancel all active tasks and queues |
| `/restart` | `/r` | Clean temporary files and restart bot |

---

## 🚩 Flexible Flags Reference

Everything you need to customize is controllable through flags directly in your `/bili` or `/mirror` commands:

### 🔹 Storage & Cloud Targets
| Flag | Shortcut | Description |
| :--- | :--- | :--- |
| `-df <folder>` | `-dir`, `-folder` | Custom Google Drive folder destination (e.g. `-df Anime/2026`) |
| `-gf` | `-gofile` | Mirror to Gofile cloud storage |
| `-pd` | `-pixeldrain` | Mirror to PixelDrain cloud storage |
| `-rc <remote:path>` | `-rclone` | Mirror to any Rclone remote (OneDrive, Mega, S3, FTP, etc.) |
| `-drive` | `-gd` | Mirror directly to Google Drive |
| `-tg` | — | Send to Telegram |

### 🔹 Quality & Audio
| Flag | Shortcut | Description |
| :--- | :--- | :--- |
| `-q <res>` | `-s` | Resolution: `8k`, `4k`, `1080p+`, `1080p`, `720p`, `480p`, `audio` |
| `-8k`, `-4k`, `-1080p+`, `-1080p`, `-720p`, `-480p` | — | Direct quality shortcuts |
| `-audio` | `-mp3` | Extract audio only (lossless FLAC / 320kbps Dolby Atmos) |

### 🔹 Engines & UPOS CDN Mirrors
| Flag | Shortcut | Description |
| :--- | :--- | :--- |
| `-web` | — | BBDown Web Mode (Default, highest compatibility) |
| `-tv` | — | BBDown TV Mode (Fast streaming CDN) |
| `-app` | — | BBDown Mobile APP Mode |
| `-ytdl` | `-yt-dlp` | Universal yt-dlp fallback engine |
| `-upos <host>` | — | Custom UPOS mirror (default: `upos-sz-mirrorhw.bilivideo.com`) |

### 🔹 Performance & Episode Range
| Flag | Shortcut | Description |
| :--- | :--- | :--- |
| `1-20` | `-p 1-20`, `-range 1-20` | Download specific episode range of a series or playlist |
| `-conc <1-8>` | `-parallel` | Set parallel download concurrency for this task (e.g. `-conc 6`) |

### 🔹 Danmaku, Subtitles & Multi-Format Archives
| Flag | Shortcut | Description |
| :--- | :--- | :--- |
| `-dd` | `-danmaku` | Download bullet comments as `.ass` subtitle |
| `-sub` / `-nosub` | — | Download or skip subtitles |
| `-doc` / `-med` | — | Upload as Document file or Streamable Media |
| `-m` | `-merge` | Merge multi-part video into one file |
| `-z`, `-zip` | — | Compress to `.zip` archive before uploading |
| `-7z` | `-7zip` | Compress to `.7z` archive (encrypted headers support) |
| `-rar` | — | Compress to `.rar` multi-volume archive |
| `-tar` / `-tgz` | `-targz` | Archive as `.tar` or compressed `.tar.gz` |
| `-arc <fmt>` | `-archive`, `-fmt` | Custom archive format: `zip`, `7z`, `rar`, `tar`, `tar.gz` |
| `-split <size>` | `-sp` | Custom multi-volume split size (e.g. `-split 500m`, `-split 1g`, `-split 1950m`, `-split 3950m`) |
| `-prem` / `-free` | `-premium` | Override auto-detected Telegram limit (Premium 4GB vs Free 2GB) |
| `-p <pswd>` | — | Archive password (when archive flags or `-e` are used) |
| `-e` | — | Extract from archive before uploading |
| `-n <name>` | — | Set custom output filename |
| `-ss <sec>` | — | Generate sample preview clip (e.g. `-ss 30`) |
| `-shots <num>` | — | Generate screenshot album (e.g. `-shots 5`) |

---

## 💡 Practical Examples

```bash
# 1. Download series episodes 1 through 10 with 4K resolution and Danmaku:
/bili https://www.bilibili.com/video/BV1xx411c7mD 1-10 -q 4k -dd

# 2. Mirror a multi-part tutorial directly into a custom Google Drive subfolder:
/mirror https://www.bilibili.com/video/BV1xx411c7mD -df Courses/Python

# 3. Create a 7z multi-volume archive split at 1GB parts with password:
/mirror https://b23.tv/xxxx -7z -split 1g -p mySecretPassword

# 4. Rar archive uploaded directly to Gofile:
/mirror https://b23.tv/xxxx -rar -gofile

# 5. Download 4K series with Telegram Premium 4GB volume limits:
/bili https://b23.tv/xxxx 1-20 -4k -prem

# 6. Mirror directly to PixelDrain:
/mirror https://b23.tv/xxxx -pixeldrain

# 7. Mirror to an Rclone remote (OneDrive, Mega, S3):
/mirror https://b23.tv/xxxx -rc onedrive:Bilibili_Archive

# 8. Extract lossless audio (FLAC / 320k) from a music video:
/bili https://b23.tv/xxxx -audio

# 9. High-concurrency download (6 parallel streams):
/bili https://b23.tv/xxxx 1-30 -conc 6
```

---

## 📁 Google Drive & Cloud Storage Mirroring

### 1. Google Drive (Direct Colab Mount)
* **Custom Folder Flag**: Use `-df <subfolder>` (e.g. `/mirror <url> -df Anime/Season1`) to automatically create and upload to that folder in MyDrive.
* **Interactive Folder Browser**: Type `/dfolder` or `/browse` to navigate folders and subfolders with inline buttons, create new folders, and select your active destination folder.
* **Live Transfer Progress**: Streaming chunked transfer provides real-time MB/s speed, ETA, and percentage directly in Telegram.
* **Clickable Links**: Direct links are generated in Telegram upon completion!

### 2. Gofile & PixelDrain
* Upload directly using `-gf` / `-gofile` or `-pd` / `-pixeldrain`.
* Combine with `-z` to zip your media and subtitles before uploading.
* Configure personal accounts via `/usetting` -> `☁️ Cloud (Gofile/PD/RC)`, or leave blank for instant anonymous uploads.
* Direct leeching: Paste any Gofile or PixelDrain link to download directly at multi-gigabit speeds!

### 3. Rclone Cloud Remotes
* Supports all 50+ cloud providers supported by Rclone (Google Drive, OneDrive, Mega, Dropbox, WebDAV, SFTP, S3, etc.).
* **Instant Activation**: Upload your `rclone.conf` directly as a Telegram document into chat. The bot auto-saves and validates it.
* Run `/rclone` to see your configured remotes.
* Use `/mirror <url> -rc <remote:folder>` to mirror files with real-time speed, ETA, and progress stats.

---

## 📊 Colab Server Metrics & Network Speed Test

### 1. Server Metrics (`/stats`, `/st`, `/server`)
Monitor the health and resources of your Colab runtime in real time:
* 🧠 **CPU & Cores**: Current CPU load and number of vCPUs available.
* 💾 **RAM Memory**: Breakdown of Used, Free (available), and Total RAM.
* 💿 **Colab Local Disk (`/`)**: Used space, Total space, and **Free disk available for ongoing downloads**.
* 📁 **Google Drive Storage**: Real-time storage stats (Used, Free, Total) for mounted Google Drive.
* 🚀 **Active Tasks**: Count of current parallel download streams.

### 2. Standalone Speed Test (`/speedtest`, `/speed`, `/sp`)
Test Colab's network pipeline to international servers anytime directly from chat:
* Measures network **Ping / Latency**, **Download Speed** (usually 100-500+ Mbps on Colab), and **Upload Speed**.
* Also accessible via inline button in `/bsetting` -> `⚡ Speedtest`.

### 3. Visual Status Ticks in Settings
* All menus (`/usetting` and `/bsetting`) display clear green ticks `✅` next to configured credentials (VIP SESSDATA, mounted Drive, Gofile, PixelDrain, Rclone).

---

## 🍪 How to Get Bilibili SESSDATA (VIP 4K/8K)

### Method 1: SESSDATA Token (Fastest — 30 Seconds)
1. Open [bilibili.com](https://www.bilibili.com) on your computer browser and log in.
2. Press `F12` (Developer Tools) -> Go to **Application** (or **Storage**) -> **Cookies** -> `https://www.bilibili.com`.
3. Find the cookie named **`SESSDATA`** and copy its value.
4. Set it in bot:
   * **User VIP**: Set in `/usetting` -> `🍪 SESSDATA Token`.
   * **Global VIP**: Set in `/bsetting` -> `🔑 Set Global SESSDATA` (serves all bot users).

### Method 2: Upload `cookies.txt`
1. Use a browser extension like **Get cookies.txt LOCALLY**.
2. Export your cookies for `bilibili.com` to `cookies.txt`.
3. Simply drag and drop `cookies.txt` as a document into your Telegram chat with the bot. It auto-extracts your VIP SESSDATA!

---

## 🚀 Running on Google Colab

1. Open **[Google Colab](https://colab.research.google.com/)** and create a new notebook.
2. Copy and paste the entire code from [`main.py`](main.py) into the first cell.
3. Fill in your Telegram credentials in the form fields:
   * **`API_ID`** & **`API_HASH`**: From [my.telegram.org](https://my.telegram.org)
   * **`BOT_TOKEN`**: From [@BotFather](https://t.me/BotFather)
   * **`USER_ID`**: Your Telegram numeric ID
   * **`CONCURRENT_VIDEOS`**: `4` (Default, adjustable from 1 to 8)
   * **`MOUNT_GOOGLE_DRIVE`**: `True`
4. Run the cell! The bot will:
   * Auto-mount your Google Drive
   * Auto-install `BBDown`, `aria2c`, `ffmpeg`, and dependencies
   * Start streaming live logs in Colab
5. Open Telegram and send `/start` to your bot!

---

## ⚖️ License
Distributed under the GNU General Public License v3.0. For educational and personal backup purposes only.
