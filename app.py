import os
import uuid
import yt_dlp
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# inicialização do Flask
app = Flask(__name__)
CORS(app)

# pasta onde os downloads serão armazenados
DOWNLOAD_DIR = "downloads"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


# rota de teste
@app.route("/")
def home():
    return {"status": "Giow Downloader API rodando"}


# analisar resoluções do vídeo
@app.route("/analyze", methods=["POST"])
def analyze():

    data = request.get_json()
    url = data.get("url")

    try:

        resolutions = set()

        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:

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


# download do arquivo
@app.route("/download", methods=["POST"])
def download():

    data = request.get_json()

    url = data.get("url")
    mode = data.get("mode")
    resolution = data.get("resolution")

    file_id = str(uuid.uuid4())

    try:

        if mode == "mp3":

            filename = f"{file_id}.mp3"

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(DOWNLOAD_DIR, filename),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192"
                }],
                "quiet": True
            }

        else:

            filename = f"{file_id}.mp4"

            if resolution == "Qualidade mais alta":
                fmt = "bestvideo+bestaudio/best"
            else:
                h = int(resolution.replace("p", ""))
                fmt = f"bestvideo[height<={h}]+bestaudio/best"

            ydl_opts = {
                "format": fmt,
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(DOWNLOAD_DIR, filename),
                "quiet": True
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        return send_file(
            os.path.join(DOWNLOAD_DIR, filename),
            as_attachment=True
        )

    except Exception as e:

        return jsonify({"error": str(e)})


# execução local (Render usa gunicorn)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
