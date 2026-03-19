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

# Combinações de clientes a tentar em ordem.
# tv_embedded e ios_downgraded foram REMOVIDOS no yt-dlp 2026.01.31.
# "default,android" é a combinação mais estável para datacenter com cookies.
ANALYZE_CLIENTS = [
    ["default", "android"],
    ["mweb"],
    ["ios"],
    ["web"],
]


def cors_preflight():
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


def get_cookie_file():
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] Via YOUTUBE_COOKIES_B64 ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro B64: {e}")

    if os.path.exists("/etc/secrets/cookies.txt"):
        try:
            with open("/etc/secrets/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] Via /etc/secrets/cookies.txt ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro secret: {e}")

    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] Via /app/cookies.txt ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro /app: {e}")

    print("[cookies] Nenhum cookie encontrado!")
    return None


def make_base_opts(cookie_path, clients, extra=None):
    """
    `formats=missing_pot` é ESSENCIAL para IPs de datacenter:
    instrui o yt-dlp a incluir formatos mesmo sem Proof-of-Origin Token,
    caso contrário a lista de formatos fica vazia ou o download falha.
    Ref: github.com/yt-dlp/yt-dlp/issues/16155
    """
    opts = {
        "quiet": True,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "check_formats": False,
        "ignore_no_formats_error": True,
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
                "player_client": clients,
                "formats": ["missing_pot"],
            }
        },
    }

    if cookie_path:
        opts["cookiefile"] = cookie_path

    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")
    if po_token and visitor_data:
        opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}"]
        opts["extractor_args"]["youtube"]["visitor_data"] = [visitor_data]

    if extra:
        opts.update(extra)

    return opts


def extract_video_info(url):
    cookie_path = get_cookie_file()
    last_error = None

    for clients in ANALYZE_CLIENTS:
        label = "+".join(clients)
        try:
            print(f"[analyze] Tentando clients={label}")
            opts = make_base_opts(cookie_path, clients, extra={"skip_download": True})

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                last_error = f"clients={label} retornou vazio"
                print(f"[analyze] {last_error}")
                continue

            n = len(info.get("formats") or [])
            print(f"[analyze] OK clients={label}: {n} formatos")
            info["used_clients"] = clients
            return info

        except Exception as e:
            last_error = str(e)
            print(f"[analyze] {label} falhou: {last_error[:200]}")
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

            if vcodec == "none":
                continue

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
                "acodec": acodec,
            })

        formats.append({
            "format_id": "mp3",
            "ext": "mp3",
            "resolution": "audio only",
            "filesize": None,
            "fps": None,
            "acodec": "mp3",
        })

        print(f"[analyze] Retornando {len(formats)} formatos")

        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "formats": formats,
            "client_used": "+".join(info.get("used_clients", [])),
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
    return jsonify({
        "status": "running",
        "cookies_loaded": cookie_path is not None,
        "secrets_file_exists": os.path.exists("/etc/secrets/cookies.txt"),
        "cookies_b64_env": bool(os.environ.get("YOUTUBE_COOKIES_B64")),
        "po_token_configured": bool(os.environ.get("YOUTUBE_PO_TOKEN")),
        "yt_dlp_version": yt_dlp.version.__version__,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
