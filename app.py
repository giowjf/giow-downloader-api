import os
import base64
import tempfile
import yt_dlp
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from downloader import download_video

app = Flask(__name__)

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    allow_headers=["Content-Type"],
    methods=["GET", "POST", "OPTIONS"]
)

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Clientes YouTube em ordem de preferência.
# "mweb" e "android" são os mais tolerantes com IPs de datacenter.
YOUTUBE_CLIENTS = ["mweb", "android", "ios", "tv", "web_embedded", "web"]


def cors_preflight():
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


def get_cookie_file():
    """
    Retorna path de arquivo de cookies temporário.
    Prioridade:
      1. Env var YOUTUBE_COOKIES_B64 (conteúdo do cookies.txt em base64)
      2. Secret File do Render em /etc/secrets/cookies.txt  ← você está usando este
      3. Arquivo fisico /app/cookies.txt (fallback legado)
    """
    # 1. Env var base64
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            cookies_data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(cookies_data)
            tmp.flush()
            tmp.close()
            print(f"[cookies] Carregados via YOUTUBE_COOKIES_B64 ({len(cookies_data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro ao decodificar YOUTUBE_COOKIES_B64: {e}")

    # 2. Secret File do Render (/etc/secrets/cookies.txt)
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
            print(f"[cookies] Erro ao ler /etc/secrets/cookies.txt: {e}")

    # 3. Fallback legado
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
            print(f"[cookies] Erro ao ler /app/cookies.txt: {e}")

    print("[cookies] NENHUM cookie encontrado — bot detection provável!")
    return None


def make_ydl_opts(cookie_path, client, extra=None):
    """
    Monta as opções base do yt-dlp para um cliente específico.
    NÃO define 'format' aqui — cada chamador define o que precisa.
    """
    opts = {
        "quiet": True,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        # Não validar disponibilidade de formato antes de tentar — evita
        # "Requested format is not available" em IPs de datacenter
        "check_formats": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": {
            "youtube": {
                "player_client": [client],
            }
        },
    }

    if cookie_path:
        opts["cookiefile"] = cookie_path

    # Suporte a po_token (alternativa a cookies)
    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")
    if po_token and visitor_data:
        opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}"]
        opts["extractor_args"]["youtube"]["visitor_data"] = [visitor_data]

    if extra:
        opts.update(extra)

    return opts


def extract_video_info(url):
    """
    Tenta extrair metadados + lista COMPLETA de formatos do vídeo.
    Usa skip_download=True e format="bestvideo+bestaudio/best" para
    forçar o yt-dlp a listar todos os streams disponíveis.
    """
    cookie_path = get_cookie_file()
    last_error = None

    for client in YOUTUBE_CLIENTS:
        try:
            print(f"[analyze] Tentando client: {client}")
            opts = make_ydl_opts(cookie_path, client, extra={
                "skip_download": True,
                # "all" retorna todos os formatos sem validar disponibilidade
                "format": "all",
                # Não abortar se algum formato não puder ser verificado
                "check_formats": False,
                "ignore_no_formats_error": True,
            })

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                last_error = f"Client {client} retornou vazio"
                print(f"[analyze] {last_error}")
                continue

            n = len(info.get("formats") or [])
            print(f"[analyze] Sucesso com {client}: {n} formatos encontrados")
            info["used_client"] = client
            return info

        except Exception as e:
            last_error = str(e)
            print(f"[analyze] Client {client} falhou: {last_error[:150]}")
            continue

    raise Exception(f"Todos os clientes falharam. Ultimo erro: {last_error}")


@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return cors_preflight()

    data = request.json
    url = data.get("url") if data else None

    if not url:
        return jsonify({"error": "missing url"}), 400

    try:
        info = extract_video_info(url)
        formats = []
        seen = set()

        for f in info.get("formats", []):
            vcodec = f.get("vcodec") or ""
            acodec = f.get("acodec") or ""

            # Ignorar streams de áudio puro (sem vídeo)
            if vcodec == "none":
                continue

            # Ignorar formatos sem resolução válida (storyboards, etc)
            height = f.get("height") or 0
            resolution = f.get("resolution") or (f"{height}p" if height else None)
            if not resolution or resolution in ("none", "0", "0p"):
                continue

            key = (f.get("ext"), resolution)
            if key in seen:
                continue
            seen.add(key)

            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": resolution,
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "fps": f.get("fps"),
                "acodec": acodec,  # "none" = DASH sem áudio (precisa de mux)
            })

        # MP3 sempre disponível via conversão
        formats.append({
            "format_id": "mp3",
            "ext": "mp3",
            "resolution": "audio only",
            "filesize": None,
            "fps": None,
            "acodec": "mp3",
        })

        print(f"[analyze] Retornando {len(formats)} formatos para o front")

        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "formats": formats,
            "client_used": info.get("used_client"),
        })

    except Exception as e:
        return jsonify({"error": "Falha ao extrair informacoes", "details": str(e)}), 500


@app.route("/download", methods=["POST", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return cors_preflight()

    data = request.json
    url = data.get("url")
    mode = data.get("mode", "mp4")
    format_id = data.get("format_id")
    preferred_client = data.get("preferred_client")

    if not url:
        return jsonify({"error": "missing url"}), 400

    try:
        filename = download_video(url, mode, format_id, preferred_client)
        path = os.path.join(DOWNLOAD_DIR, filename)
        response = send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

        @response.call_on_close
        def cleanup():
            try:
                os.remove(path)
            except Exception:
                pass

        return response

    except Exception as e:
        return jsonify({"error": "Falha no download", "details": str(e)}), 500


@app.route("/")
def health():
    cookie_path = get_cookie_file()
    # Checar existência dos secrets
    secrets_exist = os.path.exists("/etc/secrets/cookies.txt")
    return jsonify({
        "status": "running",
        "cookies_loaded": cookie_path is not None,
        "secrets_file_exists": secrets_exist,
        "cookies_b64_env": bool(os.environ.get("YOUTUBE_COOKIES_B64")),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
