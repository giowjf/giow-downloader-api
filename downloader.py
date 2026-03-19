import yt_dlp
import os
import uuid
import base64
import tempfile

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def get_cookie_file():
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            return tmp.name
        except Exception:
            pass
    if os.path.exists("/etc/secrets/cookies.txt"):
        try:
            with open("/etc/secrets/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] /etc/secrets/cookies.txt ({len(data)} bytes)")
            return tmp.name
        except Exception:
            pass
    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            return tmp.name
        except Exception:
            pass
    return None


def download_video(url, mode="mp4", format_id=None, preferred_client=None):
    file_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    cookie_path = get_cookie_file()

    # Seletor de formato
    if mode == "mp3":
        fmt = "bestaudio/best"
    elif format_id and format_id != "mp3":
        fmt = (
            f"{format_id}+bestaudio[ext=m4a]/"
            f"{format_id}+bestaudio/"
            f"{format_id}/"
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/best"
        )
    else:
        fmt = (
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/best"
        )

    # Tentativas em ordem — android primeiro pois não usa SABR
    attempts = [
        ["android"],
        ["android", "tv"],
        ["ios"],
        ["mweb"],
    ]

    # Se o /analyze informou qual cliente funcionou, tenta ele primeiro
    if preferred_client:
        preferred = [c.strip() for c in preferred_client.split("+") if c.strip()]
        if preferred not in attempts:
            attempts.insert(0, preferred)

    base_opts = {
        "outtmpl": output_path,
        "quiet": False,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "format": fmt,
        "check_formats": False,
        # User-Agent do app Android do YouTube
        "http_headers": {
            "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    if mode == "mp3":
        base_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    if cookie_path:
        base_opts["cookiefile"] = cookie_path

    last_error = None
    for clients in attempts:
        label = "+".join(clients)
        try:
            opts = dict(base_opts)
            opts["extractor_args"] = {
                "youtube": {
                    "player_client": clients,
                    "formats": ["missing_pot"],
                }
            }
            print(f"[download] client={label} fmt={fmt[:60]}")

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                if mode == "mp3":
                    base = os.path.splitext(os.path.basename(filename))[0]
                    filename = os.path.join(DOWNLOAD_DIR, base + ".mp3")

                print(f"[download] Sucesso: {os.path.basename(filename)}")
                return os.path.basename(filename)

        except Exception as e:
            last_error = str(e)
            print(f"[download] {label} falhou: {last_error[:200]}")
            continue

    raise Exception(f"Download falhou em todos os clientes. Ultimo erro: {last_error}")
