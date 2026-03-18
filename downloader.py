import yt_dlp
import os
import uuid

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_video(url, mode="mp4"):

    file_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")

    cookie_path = "/app/cookies.txt"

    ydl_opts = {
        "outtmpl": output_path,
        "quiet": True,
        "nocheckcertificate": True,
        "cookiefile": cookie_path if os.path.exists(cookie_path) else None,
    }

    if mode == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })
    else:
        ydl_opts.update({
            "format": "bestvideo+bestaudio/best"
        })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        filename = ydl.prepare_filename(info)

        if mode == "mp3":
            filename = filename.rsplit(".", 1)[0] + ".mp3"

        return os.path.basename(filename)
