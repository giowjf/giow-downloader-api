import os
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

# diretório temporário de downloads
DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YOUTUBE_CLIENTS = [
    "tv",
    "android",
    "ios",
    "web_creator",
    "web_embedded",
    "web"
]


def cors_preflight():
    response = make_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


def extract_video_info(url):

    last_error = None
    cookie_path = "/app/cookies.txt"

    for client in YOUTUBE_CLIENTS:

        try:

            ydl_opts = {
                "quiet": True,
                "nocheckcertificate": True,
                "skip_download": True,
                "retries": 2,

                # usa cookie só se existir
                "cookiefile": cookie_path if os.path.exists(cookie_path) else None,

                "http_headers": {
                    "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 12)",
                    "Accept-Language": "en-US,en;q=0.9"
                },

                "extractor_args": {
                    "youtube": {
                        "player_client": [client],
                        "player_skip": ["configs"]
                    }
                }
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            info["used_client"] = client
            return info

        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(last_error)


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

        for f in info.get("formats", []):

            if f.get("vcodec") != "none":

                formats.append({
                    "format_id": f.get("format_id"),
                    "ext": f.get("ext"),
                    "resolution": f.get("resolution"),
                    "filesize": f.get("filesize"),
                    "url": f.get("url")
                })

        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "formats": formats,
            "client_used": info.get("used_client")
        })

    except Exception as e:

        return jsonify({
            "error": "failed to extract video",
            "details": str(e)
        }), 500


@app.route("/download", methods=["POST", "OPTIONS"])
def download():

    if request.method == "OPTIONS":
        return cors_preflight()

    data = request.json
    url = data.get("url")
    mode = data.get("mode", "mp4")

    if not url:
        return jsonify({"error": "missing url"}), 400

    try:

        file = download_video(url, mode)
        path = os.path.join(DOWNLOAD_DIR, file)

        response = send_from_directory(
            DOWNLOAD_DIR,
            file,
            as_attachment=True
        )

        # apagar arquivo depois do envio
        try:
            os.remove(path)
        except:
            pass

        return response

    except Exception as e:

        return jsonify({
            "error": "download failed",
            "details": str(e)
        }), 500


@app.route("/")
def health():
    return {"status": "running"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
