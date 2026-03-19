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

# Clientes em ordem de confiabilidade para extração de metadados
YOUTUBE_CLIENTS = ["mweb", "android", "ios", "tv", "web_embedded", "web_creator", "web"]


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
      2. Secret File do Render em /etc/secrets/cookies.txt
      3. Arquivo fisico /app/cookies.txt (fallback legado)
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

    # Secret File do Render — copia para /tmp pois /etc/secrets é read-only
    if os.path.exists("/etc/secrets/cookies.txt"):
        try:
            with open("/etc/secrets/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, dir="/tmp"
            )
            tmp.write(data)
            tmp.flush()
            tmp.close()
            print("Cookies copiados de /etc/secrets/cookies.txt para /tmp")
            return tmp.name
        except Exception as e:
            print(f"Erro ao copiar cookies do Secret File: {e}")

    # Fallback legado — também copia para /tmp por segurança
    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, dir="/tmp"
            )
            tmp.write(data)
            tmp.flush()
            tmp.close()
            print("Cookies copiados de /app/cookies.txt para /tmp")
            return tmp.name
        except Exception as e:
            print(f"Erro ao copiar cookies legados: {e}")

    print("Nenhum cookie encontrado — tentando sem autenticacao")
    return None


def build_ydl_opts(cookie_path, client, skip_download=True, output_path=None):
    opts = {
        "quiet": True,
        "nocheckcertificate": True,
        "skip_download": skip_download,
        "retries": 3,
        "fragment_retries": 3,
        # Ao analisar, não forçar validação de formato específico.
        # "bestvideo/best" aceita qualquer formato disponível pelo cliente.
        "format": "bestvideo/best",
        # Não abortar se algum formato não estiver disponível neste cliente
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
                "player_client": [client],
            }
        },
    }
    if cookie_path:
        opts["cookiefile"] = cookie_path
    if output_path:
        opts["outtmpl"] = output_path

    # Suporte a po_token para contornar bot detection sem cookies
    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")
    if po_token and visitor_data:
        opts["extractor_args"]["youtube"]["po_token"] = [f"web+{po_token}"]
        opts["extractor_args"]["youtube"]["visitor_data"] = [visitor_data]

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

            if not info:
                last_error = f"Client {client} retornou info vazio"
                print(last_error)
                continue

            info["used_client"] = client
            n_formats = len(info.get("formats") or [])
            print(f"Sucesso com client: {client} ({n_formats} formatos)")
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
            vcodec = f.get("vcodec") or ""
            acodec = f.get("acodec") or ""

            # Pular streams de audio-only (vcodec=="none"); null/ausente = manter
            if vcodec == "none":
                continue

            # Pular formatos sem resolucao util (storyboards, thumbnails)
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
    preferred_client = data.get("preferred_client")  # cliente que funcionou no /analyze

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
        "cookies": "present" if cookie_path else "missing",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
