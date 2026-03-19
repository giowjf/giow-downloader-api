import os
import subprocess
import base64
import tempfile
import urllib.request
import yt_dlp
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from downloader import download_video

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type"], methods=["GET", "POST", "OPTIONS"])

DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Clientes compatíveis COM cookies (web suporta, android/ios não suportam)
CLIENTS_WITH_COOKIES = [
    ["web", "default"],   # melhor qualidade com cookies
    ["mweb"],             # fallback HLS
]

# Clientes compatíveis SEM cookies
CLIENTS_WITHOUT_COOKIES = [
    ["android"],          # DASH sem SABR, sem necessidade de PO Token
    ["ios"],              # DASH com GVS token
    ["web", "default"],  # fallback
    ["mweb"],
]


def cors_preflight():
    r = make_response()
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return r


def get_cookie_file():
    """
    Carrega cookies em ordem de prioridade.
    Retorna path do arquivo temporário ou None.
    """
    # 1. Env var base64
    cookies_b64 = os.environ.get("YOUTUBE_COOKIES_B64")
    if cookies_b64:
        try:
            data = base64.b64decode(cookies_b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] Carregado via B64 ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro B64: {e}")

    # 2. Secret File do Render
    if os.path.exists("/etc/secrets/cookies.txt"):
        try:
            with open("/etc/secrets/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] Carregado via /etc/secrets ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro secret file: {e}")

    # 3. Fallback legado
    if os.path.exists("/app/cookies.txt"):
        try:
            with open("/app/cookies.txt", "r") as f:
                data = f.read()
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp")
            tmp.write(data); tmp.flush(); tmp.close()
            print(f"[cookies] Carregado via /app ({len(data)} bytes)")
            return tmp.name
        except Exception as e:
            print(f"[cookies] Erro /app: {e}")

    print("[cookies] AVISO: nenhum cookie encontrado — downloads podem falhar")
    return None


def build_extractor_args(client_list):
    """
    Monta extractor_args para o yt-dlp.

    Com Node.js instalado no container, o yt-dlp usa EJS nativo para
    resolver desafios do YouTube — elimina necessidade de bgutil externo.

    Fallback: env var YOUTUBE_PO_TOKEN para token manual.
    """
    args = {
        "player_client": client_list,
        # Inclui formatos mesmo sem GVS PO Token (necessário em IPs de datacenter)
        "formats": ["missing_pot"],
    }

    # Token manual — fallback caso EJS nativo não resolva
    po_token = os.environ.get("YOUTUBE_PO_TOKEN")
    visitor_data = os.environ.get("YOUTUBE_VISITOR_DATA")
    if po_token:
        args["po_token"] = [f"web+{po_token}"]
        if visitor_data:
            args["visitor_data"] = [visitor_data]
        print("[po_token] Usando token manual configurado")

    return args


def extract_video_info(url):
    """
    Tenta extrair metadados do vídeo testando múltiplos clientes em sequência.
    Usa clientes diferentes dependendo se cookies estão disponíveis,
    pois android/ios não suportam cookies no yt-dlp.
    """
    cookie_path = get_cookie_file()
    last_error = None

    # Escolhe lista de clientes baseado na disponibilidade de cookies
    clients = CLIENTS_WITH_COOKIES if cookie_path else CLIENTS_WITHOUT_COOKIES
    print(f"[analyze] Usando {'clientes com cookies' if cookie_path else 'clientes sem cookies'}: {clients}")

    for client_list in clients:
        label = ",".join(client_list)
        try:
            print(f"[analyze] Tentando client={label}")
            opts = {
                "quiet": True,
                "skip_download": True,
                "nocheckcertificate": True,
                "check_formats": False,
                "ignore_no_formats_error": True,
                "extractor_args": {"youtube": build_extractor_args(client_list)},
                "http_headers": {"Accept-Language": "en-US,en;q=0.9"},
            }
            if cookie_path:
                opts["cookiefile"] = cookie_path

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if not info:
                last_error = f"client={label} retornou vazio"
                print(f"[analyze] {last_error}")
                continue

            all_fmts = info.get("formats") or []
            video_fmts = [f for f in all_fmts
                          if (f.get("vcodec") or "none") != "none"
                          and (f.get("height") or 0) > 0]

            print(f"[analyze] client={label} OK — {len(all_fmts)} formatos totais, {len(video_fmts)} com vídeo")

            if len(video_fmts) == 0:
                last_error = f"client={label} retornou {len(all_fmts)} formatos mas nenhum com vídeo"
                print(f"[analyze] {last_error} — tentando próximo cliente")
                continue

            info["used_client"] = label
            return info

        except Exception as e:
            last_error = str(e)
            print(f"[analyze] client={label} falhou: {last_error[:300]}")
            continue

    raise Exception(f"Todos os clientes falharam. Ultimo erro: {last_error}")


# ─── Diagnóstico ────────────────────────────────────────────────────────────

def check_node():
    """Verifica se Node.js está disponível para EJS nativo do yt-dlp."""
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return {"available": True, "version": result.stdout.strip()}
        return {"available": False, "error": result.stderr.strip()}
    except Exception as e:
        return {"available": False, "error": str(e)}


def check_ytdlp_formats(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ"):
    """
    Testa extração real do yt-dlp.
    Retorna quantos formatos de vídeo foram encontrados.
    """
    cookie_path = get_cookie_file()
    try:
        opts = {
            "quiet": True,
            "skip_download": True,
            "nocheckcertificate": True,
            "check_formats": False,
            "ignore_no_formats_error": True,
            "extractor_args": {"youtube": build_extractor_args(["android"])},
        }
        if cookie_path:
            opts["cookiefile"] = cookie_path

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        all_fmts = info.get("formats") or []
        video_fmts = [f for f in all_fmts
                      if (f.get("vcodec") or "none") != "none"
                      and (f.get("height") or 0) > 0]
        resolutions = sorted(set(
            f"{f.get('height')}p" for f in video_fmts if f.get("height")
        ), key=lambda x: int(x[:-1]), reverse=True)[:5]

        return {
            "ok": len(video_fmts) > 0,
            "total_formats": len(all_fmts),
            "video_formats": len(video_fmts),
            "sample_resolutions": resolutions,
        }
    except Exception as e:
        error = str(e)
        if "Sign in" in error or "bot" in error.lower():
            cause = "bot_detection"
        elif "format" in error.lower():
            cause = "no_formats"
        else:
            cause = "unknown"
        return {"ok": False, "error": error[:300], "cause": cause}


# ─── Rotas ──────────────────────────────────────────────────────────────────

@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return cors_preflight()

    data = request.json
    url = data.get("url") if data else None
    if not url:
        return jsonify({"error": "missing url"}), 400

    print(f"[analyze] Iniciando para: {url}")
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

        # MP3 sempre disponível via conversão
        formats.append({
            "format_id": "mp3",
            "ext": "mp3",
            "resolution": "audio only",
            "filesize": None,
            "fps": None,
            "acodec": "mp3",
        })

        print(f"[analyze] Concluído: {len(formats)} formatos retornados (client={info.get('used_client')})")
        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "formats": formats,
            "client_used": info.get("used_client", ""),
        })

    except Exception as e:
        print(f"[analyze] ERRO: {e}")
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

    print(f"[download] Iniciando: mode={mode} format_id={format_id} client={preferred_client}")
    try:
        filename = download_video(url, mode, format_id, preferred_client)
        path = os.path.join(DOWNLOAD_DIR, filename)
        response = send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

        @response.call_on_close
        def cleanup():
            try:
                os.remove(path)
                print(f"[download] Arquivo removido: {filename}")
            except Exception:
                pass

        return response

    except Exception as e:
        print(f"[download] ERRO: {e}")
        return jsonify({"error": "Falha no download", "details": str(e)}), 500


@app.route("/")
def health():
    cookie_path = get_cookie_file()
    node = check_node()
    return jsonify({
        "status": "running",
        "yt_dlp_version": yt_dlp.version.__version__,
        "cookies_loaded": cookie_path is not None,
        "secrets_file_exists": os.path.exists("/etc/secrets/cookies.txt"),
        "node_available": node,
        "po_token_manual": bool(os.environ.get("YOUTUBE_PO_TOKEN")),
    })


@app.route("/diag")
def diag():
    """
    Diagnóstico completo — chame após cada deploy para verificar toda a cadeia.
    Faz uma extração real do YouTube (~5-10s).
    """
    print("[diag] Iniciando diagnóstico completo...")
    cookie_path = get_cookie_file()
    node = check_node()
    ytdlp_test = check_ytdlp_formats()

    all_ok = cookie_path is not None and node.get("available") and ytdlp_test.get("ok")

    result = {
        "overall": "OK" if all_ok else "PROBLEMAS ENCONTRADOS",
        "checks": {
            "1_cookies": {
                "ok": cookie_path is not None,
                "detail": "Cookies carregados" if cookie_path else "NENHUM cookie encontrado",
            },
            "2_node_js": {
                "ok": node.get("available", False),
                "detail": node,
            },
            "3_ytdlp_youtube": {
                "ok": ytdlp_test.get("ok", False),
                "detail": ytdlp_test,
            },
        },
        "diagnosis": [],
    }

    if not cookie_path:
        result["diagnosis"].append({
            "problema": "Cookies ausentes",
            "causa": "Secret File não encontrado",
            "acao": "Verificar Secret File no Render Dashboard > giow-downloader-api > Secret Files",
        })

    if not node.get("available"):
        result["diagnosis"].append({
            "problema": "Node.js não encontrado",
            "causa": "Dockerfile não instalou Node.js corretamente",
            "acao": "Verificar logs do build no Render — etapa de instalação do Node.js",
        })

    if not ytdlp_test.get("ok"):
        cause = ytdlp_test.get("cause", "")
        if cause == "bot_detection":
            result["diagnosis"].append({
                "problema": "YouTube bloqueou como bot",
                "causa": "Node.js indisponível (EJS nativo falhou) + cookies insuficientes",
                "acao": "Verificar check 2 (Node.js). Se OK, renovar cookies no Secret File.",
            })
        elif cause == "no_formats":
            result["diagnosis"].append({
                "problema": "Nenhum formato de vídeo disponível",
                "causa": "PO Token ausente — YouTube não entrega DASH para IPs de datacenter",
                "acao": "Node.js precisa estar disponível para EJS nativo funcionar",
            })
        else:
            result["diagnosis"].append({
                "problema": "Extração falhou",
                "causa": ytdlp_test.get("error", "erro desconhecido"),
                "acao": "Verificar logs completos no Render Dashboard > Logs",
            })

    if all_ok:
        result["diagnosis"].append({
            "status": "Sistema funcionando corretamente",
            "formatos_disponiveis": ytdlp_test.get("sample_resolutions"),
        })

    print(f"[diag] Resultado: {result['overall']}")
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
