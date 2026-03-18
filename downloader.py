import yt_dlp
import os
import uuid

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YOUTUBE_CLIENTS = ["tv", "web_embedded", "android", "ios", "web"]


def get_cookie_file():
    import base64, tempfile
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data)
            tmp.flush()
            tmp.close()
            return tmp.name
        except Exception:
            pass
    if os.path.exists("/app/cookies.txt"):
        return "/app/cookies.txt"
    return None


def download_video(url, mode="mp4", format_id=None):
    file_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    cookie_path = get_cookie_file()

    base_opts = {
        "outtmpl": output_path,
        "quiet": True,
        "nocheckcertificate": True,
        "retries": 3,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    if cookie_path:
        base_opts["cookiefile"] = cookie_path

    if mode == "mp3":
        base_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })
    elif format_id and format_id != "mp3":
        # formato especifico selecionado
        base_opts["format"] = f"{format_id}+bestaudio/best[height<=1080]/best"
    else:
        base_opts["format"] = "bestvideo[height<=1080]+bestaudio/best"

    last_error = None
    for client in YOUTUBE_CLIENTS:
        try:
            opts = dict(base_opts)
            opts["extractor_args"] = {"youtube": {"player_client": [client]}}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if mode == "mp3":
                    filename = filename.rsplit(".", 1)[0] + ".mp3"
                return os.path.basename(filename)
        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(f"Download falhou em todos os clientes. Ultimo erro: {last_error}")
