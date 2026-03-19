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
      1. Env var YOUTUBE_COOKIES_B64 (conteúdo do cookies.txt em base64)
      2. Secret File do Render em /etc/secrets/cookies.txt
      3. Arquivo fisico /app/cookies.txt (fallback legado)
    """
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

    # Secret File do Render — copia para /tmp pois /etc/secrets é read-only
    if os.path.exists("/etc/secrets/cookies.txt"):
        try:
            with open("/etc/secrets/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data)
            tmp.flush()
            tmp.close()
            return tmp.name
        except Exception:
            pass

    # Fallback legado — também copia para /tmp por segurança
    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data)
            tmp.flush()
            tmp.close()
            return tmp.name
        except Exception:
            pass

    return None


def download_video(url, mode="mp4", format_id=None, preferred_client=None):
    file_id = str(uuid.uuid4())
    output_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.%(ext)s")
    cookie_path = get_cookie_file()

    # Prioriza o cliente que funcionou no /analyze, evitando incompatibilidade de format_id
    clients_to_try = list(YOUTUBE_CLIENTS)
    if preferred_client and preferred_client in clients_to_try:
        clients_to_try.remove(preferred_client)
        clients_to_try.insert(0, preferred_client)

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
        # Fallbacks em ordem:
        #   1. format_id + melhor áudio m4a (mux perfeito para mp4)
        #   2. format_id + qualquer áudio disponível
        #   3. format_id sozinho (já pode ter áudio embutido)
        #   4. melhor vídeo+áudio genérico até 1080p
        base_opts["format"] = (
            f"{format_id}+bestaudio[ext=m4a]/"
            f"{format_id}+bestaudio/"
            f"{format_id}/"
            f"bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        )
    else:
        base_opts["format"] = (
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
        )

    last_error = None
    for client in clients_to_try:
        try:
            opts = dict(base_opts)

            # Mescla corretamente sem sobrescrever outras extractor_args
            opts.setdefault("extractor_args", {})
            opts["extractor_args"]["youtube"] = {"player_client": [client]}

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)

                # Correção segura para MP3 com títulos especiais
                if mode == "mp3":
                    base = os.path.splitext(os.path.basename(filename))[0]
                    filename = os.path.join(DOWNLOAD_DIR, base + ".mp3")

                return os.path.basename(filename)

        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(f"Download falhou em todos os clientes. Ultimo erro: {last_error}")
