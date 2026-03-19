import yt_dlp
import os
import uuid
import base64
import tempfile

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YOUTUBE_CLIENTS = ["mweb", "android", "ios", "tv", "web_embedded", "web"]


def get_cookie_file():
    """
    Retorna path de arquivo de cookies temporário.
    Prioridade:
      1. Env var YOUTUBE_COOKIES_B64
      2. Secret File do Render em /etc/secrets/cookies.txt
      3. Arquivo fisico /app/cookies.txt
    """
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data)
            tmp.flush()
            tmp.close()
            print(f"[cookies] Carregados via YOUTUBE_COOKIES_B64 ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro YOUTUBE_COOKIES_B64: {e}")

    if os.path.exists("/etc/secrets/cookies.txt"):
        try:
            with open("/etc/secrets/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data)
            tmp.flush()
            tmp.close()
            print(f"[cookies] Carregados de /etc/secrets/cookies.txt ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro /etc/secrets/cookies.txt: {e}")

    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data)
            tmp.flush()
            tmp.close()
            print(f"[cookies] Carregados de /app/cookies.txt ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro /app/cookies.txt: {e}")

    print("[cookies] NENHUM cookie encontrado!")
    return None


def download_video(url, mode="mp4", format_id=None, preferred_client=None):
    file_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    cookie_path = get_cookie_file()

    # Prioriza o cliente que funcionou no /analyze
    clients_to_try = list(YOUTUBE_CLIENTS)
    if preferred_client and preferred_client in clients_to_try:
        clients_to_try.remove(preferred_client)
        clients_to_try.insert(0, preferred_client)

    # Monta seletor de formato
    if mode == "mp3":
        fmt = "bestaudio/best"
    elif format_id and format_id != "mp3":
        # Tenta o format_id específico com mux de áudio, depois fallbacks genéricos
        fmt = (
            f"{format_id}+bestaudio[ext=m4a]/"
            f"{format_id}+bestaudio/"
            f"{format_id}/"
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080]/best"
        )
    else:
        fmt = (
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080]/best"
        )

    base_opts = {
        "outtmpl": output_path,
        "quiet": False,  # log visível para debug
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "format": fmt,
        # Não validar disponibilidade do formato antes de baixar
        "check_formats": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
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

    # po_token opcional
    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")

    last_error = None
    for client in clients_to_try:
        try:
            opts = dict(base_opts)
            opts["extractor_args"] = {
                "youtube": {"player_client": [client]}
            }

            if po_token and visitor_data:
                opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}"]
                opts["extractor_args"]["youtube"]["visitor_data"] = [visitor_data]

            print(f"[download] Tentando client={client} format={fmt[:60]}")

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
            print(f"[download] Client {client} falhou: {last_error[:150]}")
            continue

    raise Exception(f"Download falhou em todos os clientes. Ultimo erro: {last_error}")
