import os
import base64
import tempfile
import yt_dlp
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from downloader import download_video

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type"], methods=["GET", "POST", "OPTIONS"])

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def cors_preflight():
    r = make_response()
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return r


def get_cookie_file():
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] B64 ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro B64: {e}")

    if os.path.exists("/etc/secrets/cookies.txt"):
        try:
            with open("/etc/secrets/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] /etc/secrets ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro secret: {e}")

    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] /app ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro /app: {e}")

    print("[cookies] Nenhum cookie!")
    return None


def build_extractor_args(client_list):
    """
    Monta extractor_args seguindo a documentação oficial do yt-dlp:
    https://github.com/yt-dlp/yt-dlp/wiki/Extractors

    - po_token: necessário para web client em IPs de datacenter.
      Formato: "web+TOKEN" (para cliente web logado com cookies)
    - player_client: lista de clientes a usar.
      "web,default" = cliente web + fallback padrão (recomendado pela doc oficial)
    - formats=missing_pot: inclui formatos mesmo sem GVS PO Token
      (necessário para ios/mweb em datacenter; pode retornar 403 no download)
    """
    args = {
        "player_client": client_list,
        "formats": ["missing_pot"],  # inclui formatos mesmo sem PO Token de GVS
    }

    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")
    if po_token:
        # Formato: "web+TOKEN" — vincula o token ao cliente web
        args["po_token"] = [f"web+{po_token}"]
        if visitor_data:
            args["visitor_data"] = [visitor_data]
        print(f"[po_token] Configurado ✓")

    return args


def extract_video_info(url):
    """
    Tenta extrair metadados usando múltiplos clientes.

    Ordem baseada na documentação oficial e issue #12482:
    1. "web,default" com po_token (melhor qualidade, recomendado pela doc oficial)
    2. "android" (retorna DASH sem SABR, funciona sem po_token)
    3. "ios" (DASH mas exige GVS PO Token; missing_pot força inclusão)
    4. "mweb" (HLS muxado, qualidade menor mas mais compatível)
    """
    cookie_path = get_cookie_file()
    last_error = None

    attempts = [
        ["web", "default"],   # recomendado pela doc oficial com po_token
        ["android"],           # único que retorna DASH sem SABR
        ["ios"],               # DASH mas exige GVS po_token
        ["mweb"],              # HLS, fallback final
    ]

    for client_list in attempts:
        label = ",".join(client_list)
        try:
            print(f"[analyze] Tentando player_client={label}")
            opts = {
                "quiet": True,
                "skip_download": True,
                "nocheckcertificate": True,
                "check_formats": False,
                "ignore_no_formats_error": True,
                "extractor_args": {
                    "youtube": build_extractor_args(client_list)
                },
                "http_headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            if cookie_path:
                opts["cookiefile"] = cookie_path

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                last_error = f"client={label} retornou vazio"
                continue

            all_fmts = info.get("formats") or []
            video_fmts = [f for f in all_fmts
                          if (f.get("vcodec") or "none") != "none"
                          and (f.get("height") or 0) > 0]

            print(f"[analyze] OK client={label}: {len(all_fmts)} total, {len(video_fmts)} com vídeo")
            info["used_client"] = label
            return info

        except Exception as e:
            last_error = str(e)
            print(f"[analyze] client={label} falhou: {last_error[:200]}")
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
            "client_used": info.get("used_client", ""),
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
    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    return jsonify({
        "status": "running",
        "yt_dlp_version": yt_dlp.version.__version__,
        "cookies_loaded": cookie_path is not None,
        "secrets_file_exists": os.path.exists("/etc/secrets/cookies.txt"),
        "cookies_b64_env": bool(os.environ.get("YOUTUBE_COOKIES_B64")),
        # po_token é ESSENCIAL para formatos de alta qualidade em datacenter
        "po_token_configured": bool(po_token),
        # Instrução clara se faltar o po_token
        "po_token_needed": (
            "Configure YOUTUBE_PO_TOKEN via Render > Environment. "
            "Veja README.md para instruções."
        ) if not po_token else "OK",
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
