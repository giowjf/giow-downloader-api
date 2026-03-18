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

# Clientes em ordem de confiabilidade
YOUTUBE_CLIENTS = ["tv", "web_embedded", "android", "ios", "web_creator", "web"]


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
      2. Arquivo fisico /app/cookies.txt
    """
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            cookies_data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, dir="/tmp"
            )
            tmp.write(cookies_data)
            tmp.flush()
            tmp.close()
            print("Cookies carregados via YOUTUBE_COOKIES_B64")
            return tmp.name
        except Exception as e:
            print(f"Erro ao decodificar YOUTUBE_COOKIES_B64: {e}")

    if os.path.exists("/app/cookies.txt"):
        print("Cookies carregados via /app/cookies.txt")
        return "/app/cookies.txt"

    print("Nenhum cookie encontrado — tentando sem autenticacao")
    return None


def build_ydl_opts(cookie_path, client, skip_download=True, output_path=None):
    opts = {
        "quiet": True,
        "nocheckcertificate": True,
        "skip_download": skip_download,
        "retries": 3,
        "fragment_retries": 3,
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
    if output_path:
        opts["outtmpl"] = output_path
    return opts


def extract_video_info(url):
    cookie_path = get_cookie_file()
    last_error = None

    for client in YOUTUBE_CLIENTS:
        try:
            print(f"Tentando client: {client}")
            ydl_opts = build_ydl_opts(cookie_path, client, skip_download=True)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            info["used_client"] = client
            print(f"Sucesso com client: {client}")
            return info
        except Exception as e:
            last_error = str(e)
            print(f"Client {client} falhou: {last_error[:120]}")
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
            if f.get("vcodec") == "none":
                continue
            resolution = f.get("resolution") or str(f.get("height", "?"))
            key = (f.get("ext"), resolution)
            if key in seen:
                continue
            seen.add(key)
            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "resolution": resolution,
                "filesize": f.get("filesize"),
                "fps": f.get("fps"),
            })

        formats.append({
            "format_id": "mp3",
            "ext": "mp3",
            "resolution": "audio only",
            "filesize": None,
            "fps": None,
        })

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

    if not url:
        return jsonify({"error": "missing url"}), 400

    try:
        filename = download_video(url, mode, format_id)
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
    return jsonify({
        "status": "running",
        "cookies": "present" if cookie_path else "missing",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
