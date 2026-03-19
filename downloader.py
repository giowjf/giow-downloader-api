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
            print(f"[cookies] /etc/secrets ({len(data)} bytes)")
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


def build_extractor_args(client_list):
    """Monta extractor_args conforme doc oficial do yt-dlp."""
    args = {
        "player_client": client_list,
        "formats": ["missing_pot"],
    }
    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")
    if po_token:
        args["po_token"] = [f"web+{po_token}"]
        if visitor_data:
            args["visitor_data"] = [visitor_data]
    return args


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

    # Ordem de tentativa — mesma lógica do /analyze
    attempts = [
        ["web", "default"],
        ["android"],
        ["ios"],
        ["mweb"],
    ]

    # Prioriza o cliente que funcionou no /analyze
    if preferred_client:
        preferred = [c.strip() for c in preferred_client.split(",") if c.strip()]
        if preferred and preferred not in attempts:
            attempts.insert(0, preferred)

    base_opts = {
        "outtmpl": output_path,
        "quiet": False,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "format": fmt,
        "check_formats": False,
        "http_headers": {
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
    for client_list in attempts:
        label = ",".join(client_list)
        try:
            opts = dict(base_opts)
            opts["extractor_args"] = {"youtube": build_extractor_args(client_list)}

            print(f"[download] client={label} fmt={fmt[:80]}")

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
            print(f"[download] client={label} falhou: {last_error[:200]}")
            continue

    raise Exception(f"Download falhou em todos os clientes. Ultimo erro: {last_error}")
