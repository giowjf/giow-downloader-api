import os
import uuid
import yt_dlp
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


@app.route("/")
def home():
    return {"status": "Giow Downloader API rodando"}


@app.route("/analyze", methods=["POST"])
def analyze():

    data = request.get_json()
    url = data.get("url")

    try:

        resolutions = set()

        ydl_opts = {
            "quiet": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"]
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=False)

            if "formats" not in info:
                return jsonify({"error": "Nenhum formato encontrado"})

            for f in info["formats"]:

                if f.get("height"):

                    h = int(f["height"])

                    if h >= 144:
                        resolutions.add(f"{h}p")

        sorted_res = sorted(
            resolutions,
            key=lambda x: int(x.replace("p", "")),
            reverse=True
        )

        return jsonify({
            "resolutions": ["Qualidade mais alta"] + sorted_res
        })

    except Exception as e:

        return jsonify({"error": str(e)})


@app.route("/download", methods=["POST"])
def download():

    data = request.get_json()

    url = data.get("url")
    mode = data.get("mode")
    resolution = data.get("resolution")

    file_id = str(uuid.uuid4())

    try:

        ydl_opts_base = {
    "quiet": True,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
    },
    "extractor_args": {
        "youtube": {
            "player_client": [
                "android",
                "ios",
                "web"
            ]
        }
    }
}

        if mode == "mp3":

            filename = f"{file_id}.mp3"

            ydl_opts = {
                **ydl_opts_base,
                "format": "bestaudio/best",
                "outtmpl": os.path.join(DOWNLOAD_DIR, filename),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192"
                }]
            }

        else:

            filename = f"{file_id}.mp4"

            if resolution == "Qualidade mais alta":
                fmt = "bestvideo+bestaudio/best"
            else:
                h = int(resolution.replace("p", ""))
                fmt = f"bestvideo[height<={h}]+bestaudio/best"

            ydl_opts = {
                **ydl_opts_base,
                "format": fmt,
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(DOWNLOAD_DIR, filename)
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return send_file(
            os.path.join(DOWNLOAD_DIR, filename),
            as_attachment=True
        )

    except Exception as e:

        return jsonify({"error": str(e)})


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
