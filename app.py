```python
import yt_dlp
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from downloader import download_video

app = Flask(__name__)
CORS(app)

YOUTUBE_CLIENTS = [
    "tv",
    "android",
    "ios",
    "web_creator",
    "web_embedded",
    "web"
]


def extract_video_info(url):

    last_error = None

    for client in YOUTUBE_CLIENTS:

        try:

            ydl_opts = {
                "quiet": True,
                "nocheckcertificate": True,
                "skip_download": True,
                "retries": 2,

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


@app.route("/analyze", methods=["POST"])
def analyze():

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


@app.route("/download", methods=["POST"])
def download():

    data = request.json
    url = data.get("url")
    mode = data.get("mode", "mp4")

    if not url:
        return jsonify({"error": "missing url"}), 400

    try:

        file = download_video(url, mode)

        return jsonify({
            "file": f"downloads/{file}"
        })

    except Exception as e:

        return jsonify({
            "error": "download failed",
            "details": str(e)
        }), 500


@app.route("/downloads/<path:filename>")
def serve_file(filename):
    return send_from_directory("downloads", filename)


@app.route("/")
def health():
    return {"status": "running"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```
