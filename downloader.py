import yt_dlp
import uuid
import os

DOWNLOAD_DIR = "/tmp/downloads"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def download_video(url, mode="mp4"):

    filename = str(uuid.uuid4())

    if mode == "mp3":

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{DOWNLOAD_DIR}/{filename}.%(ext)s",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        }

        ext = "mp3"

    else:
        }
        ydl_opts = {
            "format": "bestvideo+bestaudio/best",
            "cookiefile": "cookies.txt",
            "outtmpl": f"{DOWNLOAD_DIR}/{filename}.%(ext)s",
            "merge_output_format": "mp4"
        }

        ext = "mp4"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return f"{filename}.{ext}"
