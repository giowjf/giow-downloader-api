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
            print(f"[cookies] /etc/secrets/cookies.txt ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro secret: {e}")

    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] /app/cookies.txt ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro /app: {e}")

    print("[cookies] Nenhum cookie encontrado!")
    return None


def extract_video_info(url):
    """
    Estratégia baseada nos issues #12482 e #16155 do yt-dlp (2025/2026):
    - O cliente 'web' agora usa SABR (sem links diretos de download)
    - O cliente 'android' ainda retorna formatos DASH baixáveis
    - 'tv' retorna HLS muxado (qualidade limitada mas funciona)
    - Combinação 'android,tv' cobre DASH + HLS como fallback
    """
    cookie_path = get_cookie_file()
    last_error = None

    # Cada tentativa é uma combinação diferente de clientes + opções
    attempts = [
        # 1. Android: único cliente que retorna DASH sem SABR em 2026
        {
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                    "formats": ["missing_pot"],
                }
            }
        },
        # 2. Android + TV juntos (mais formatos)
        {
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "tv"],
                    "formats": ["missing_pot"],
                }
            }
        },
        # 3. iOS: outro cliente com DASH direto
        {
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios"],
                    "formats": ["missing_pot"],
                }
            }
        },
        # 4. mweb: HLS mas com cookies pode ter formatos extras
        {
            "extractor_args": {
                "youtube": {
                    "player_client": ["mweb"],
                    "formats": ["missing_pot"],
                }
            }
        },
    ]

    for i, extra_args in enumerate(attempts):
        client_label = extra_args["extractor_args"]["youtube"]["player_client"]
        try:
            print(f"[analyze] Tentativa {i+1}: client={client_label}")

            opts = {
                "quiet": True,
                "skip_download": True,
                "nocheckcertificate": True,
                "check_formats": False,
                "ignore_no_formats_error": True,
                "http_headers": {
                    "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            opts.update(extra_args)

            if cookie_path:
                opts["cookiefile"] = cookie_path

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                last_error = f"retornou vazio"
                continue

            all_fmts = info.get("formats") or []
            # Conta formatos de vídeo reais (não storyboards, não só-áudio)
            video_fmts = [
                f for f in all_fmts
                if (f.get("vcodec") or "") not in ("none", "")
                and (f.get("height") or 0) > 0
            ]
            print(f"[analyze] OK client={client_label}: {len(all_fmts)} total, {len(video_fmts)} vídeo")

            info["used_clients"] = client_label
            return info

        except Exception as e:
            last_error = str(e)
            print(f"[analyze] client={client_label} falhou: {last_error[:200]}")
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

            # Pular áudio puro
            if vcodec == "none":
                continue

            # Pular storyboards e formatos sem resolução
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
