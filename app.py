import os
import yt_dlp
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "downloads"

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


def get_video_info(url):

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "socket_timeout": 15,
        "retries": 3,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
        "http_headers": {
            "User-Agent": "com.google.android.youtube/19.09.37"
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return info


def download_video(url):

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_FOLDER}/%(id)s.%(ext)s",
        "format": "bv*+ba/b",
        "socket_timeout": 15,
        "retries": 3,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"]
            }
        },
        "http_headers": {
            "User-Agent": "com.google.android.youtube/19.09.37"
        },
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    filename = ydl.prepare_filename(info)

    return filename


@app.route("/")
def home():
    return {"status": "Giow Downloader API usando yt-dlp"}


@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():

    if request.method == "OPTIONS":
        return {}, 200

    data = request.get_json()

    if not data:
        return jsonify({"error": "Body vazio"}), 400

    url = data.get("url")

    if not url:
        return jsonify({"error": "URL não enviada"}), 400

    try:

        info = get_video_info(url)

        formats = []

        for f in info.get("formats", []):
            if f.get("height"):
                formats.append(f"{f['height']}p")

        formats = sorted(list(set(formats)))

        return jsonify({
            "title": info.get("title"),
            "resolutions": formats
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST", "OPTIONS"])
def download():

    if request.method == "OPTIONS":
        return {}, 200

    data = request.get_json()

    if not data:
        return jsonify({"error": "Body vazio"}), 400

    url = data.get("url")

    if not url:
        return jsonify({"error": "URL não enviada"}), 400

    try:

        file_path = download_video(url)

        return jsonify({
            "file": file_path
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
