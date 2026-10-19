# BiliColabX - Exclusive Bilibili Telegram Leecher & Cloud Mirror
# Based on TGColabX, BBDown & DzGram Engine

import os
from time import time
from datetime import datetime


class BOT:
    SOURCE = []
    TASK = None
    ActiveTasks = []
    Queue = []             # Multi-task queue holding pending tasks
    ActiveTask = None      # Currently executing task object
    CurrentTaskIndex = 1
    TaskUser = "Owner"
    StatusState = "Download"
    CurrentEngine = "BBDown"
    ChatID = 0

    class Setting:
        stream_upload = "Media"
        convert_video = "Yes"
        convert_quality = "Low"
        caption = "Monospace"
        split_video = "Split Videos"
        prefix = ""
        suffix = ""
        thumbnail = False
        sample_duration = 30
        screenshot_count = 5

    class Options:
        stream_upload = True
        convert_video = True
        convert_quality = False
        is_split = True
        is_merge = False
        sample_video = 0
        screenshots = 0
        caption = "code"
        custom_caption = ""
        video_out = "mp4"
        custom_name = ""
        zip_pswd = ""
        unzip_pswd = ""
        bili_quality = "1080P"
        ytdl_format = "bv*+ba/b"
        ytdl_quality = "best"
        thumb_url = ""
        download_danmaku = False
        download_sub = False
        audio_only = False

    class Mode:
        mode = "leech"
        type = "normal"
        is_bili = True
        ytdl = False

    class State:
        started = False
        task_going = False
        prefix = False
        suffix = False
        custom_caption = False


class BBDOWN:
    header = ""
    speed = ""
    percentage = 0.0
    eta = ""
    done = ""
    left = ""


class YTDL:
    header = ""
    speed = ""
    percentage = 0.0
    eta = ""
    done = ""
    left = ""


class Transfer:
    down_bytes = [0, 0]
    up_bytes = [0, 0]
    total_down_size = 0
    sent_file = []
    sent_file_names = []


class TaskError:
    state = False
    text = ""


class BotTimes:
    current_time = time()
    start_time = datetime.now()
    task_start = datetime.now()


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Paths:
    BASE_DIR = BASE_DIR
    WORK_PATH = os.path.join(BASE_DIR, "BOT_WORK")
    THMB_PATH = os.path.join(BASE_DIR, "bili_leecher", "Thumbnail.jpg")
    VIDEO_FRAME = os.path.join(WORK_PATH, "video_frame.jpg")
    HERO_IMAGE = os.path.join(WORK_PATH, "Hero.jpg")
    DEFAULT_HERO = os.path.join(BASE_DIR, "custom_thmb.jpg")
    MOUNTED_DRIVE = "/content/drive"
    down_path = os.path.join(WORK_PATH, "Downloads")
    temp_dirleech_path = os.path.join(WORK_PATH, "dir_leech_temp")
    mirror_dir = "/content/drive/MyDrive/BiliColabX Uploads"
    temp_zpath = os.path.join(WORK_PATH, "Leeched_Files")
    temp_unzip_path = os.path.join(WORK_PATH, "Unzipped_Files")
    temp_files_dir = os.path.join(WORK_PATH, "leech_temp")
    thumbnail_ytdl = os.path.join(WORK_PATH, "ytdl_thumbnails")
    samples_dir = os.path.join(WORK_PATH, "samples")
    screenshots_dir = os.path.join(WORK_PATH, "screenshots")
    access_token = "/content/token.pickle"


class Messages:
    download_name = ""
    task_msg = ""
    status_head = "<b>📥 DOWNLOADING » </b>\n"
    dump_task = ""
    src_link = ""
    link_p = ""


class MSG:
    sent_msg = None
    status_msg = None


class Aria2c:
    link_info = False
    pic_dwn_url = "https://picsum.photos/900/600"


class Gdrive:
    service = None

