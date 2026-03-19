import yt_dlp
import os
import uuid
import base64
import tempfile

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Clientes compatíveis COM cookies (android/ios não suportam cookies no yt-dlp)
CLIENTS_WITH_COOKIES = [
    ["web", "default"],
    ["mweb"],
]

# Clientes compatíveis SEM cookies
CLIENTS_WITHOUT_COOKIES = [
    ["android"],
    ["ios"],
    ["web", "default"],
    ["mweb"],
]


def get_cookie_file():
    """Carrega cookies em ordem de prioridade. Idêntico ao app.py."""
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
    """
    Monta extractor_args.
    Node.js no container habilita EJS nativo do yt-dlp — resolve PO Token
    automaticamente sem servidor externo.
    """
    args = {
        "player_client": client_list,
        "formats": ["missing_pot"],
    }
    # Fallback manual
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

    # Escolhe lista de clientes baseado na disponibilidade de cookies
    # android/ios não suportam cookies no yt-dlp — seriam descartados com aviso
    clients_to_try = list(CLIENTS_WITH_COOKIES if cookie_path else CLIENTS_WITHOUT_COOKIES)
    if preferred_client:
        preferred = [c.strip() for c in preferred_client.split(",") if c.strip()]
        if preferred and preferred not in clients_to_try:
            clients_to_try.insert(0, preferred)
            print(f"[download] Priorizando client={preferred_client} (usado no /analyze)")

    # Seletor de formato com fallbacks em cascata
    if mode == "mp3":
        fmt = "bestaudio/best"
    elif format_id and format_id != "mp3":
        # Tenta o formato específico + mux de áudio, depois fallback genérico
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

    base_opts = {
        "outtmpl": output_path,
        "quiet": False,           # logs visíveis no Render para debug
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "format": fmt,
        "check_formats": False,
        "http_headers": {"Accept-Language": "en-US,en;q=0.9"},
        "js_runtimes": ["node"],
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
    for client_list in clients_to_try:
        label = ",".join(client_list)
        try:
            opts = dict(base_opts)
            opts["extractor_args"] = {"youtube": build_extractor_args(client_list)}

            print(f"[download] Tentando client={label} | formato={fmt[:60]}")

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                if mode == "mp3":
                    base = os.path.splitext(os.path.basename(filename))[0]
                    filename = os.path.join(DOWNLOAD_DIR, base + ".mp3")

                final_name = os.path.basename(filename)
                print(f"[download] Sucesso com client={label}: {final_name}")
                return final_name

        except Exception as e:
            last_error = str(e)
            print(f"[download] client={label} falhou: {last_error[:300]}")
            continue

    raise Exception(f"Download falhou em todos os clientes. Ultimo erro: {last_error}")
