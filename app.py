import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

COBALT_API = "https://api.cobalt.tools/api"


def get_cobalt(url):
r = requests.post(
    COBALT_API,
    json={
        "url": url,
        "vCodec": "h264",
        "vQuality": "max"
    },
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json"
    },
    timeout=30
)

    return r.json()


@app.route("/")
def home():
    return {"status": "Giow Downloader API usando Cobalt"}


@app.route("/analyze", methods=["POST"])
def analyze():

    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL não enviada"})

    try:

        result = get_cobalt(url)

        if result.get("status") not in ["success", "stream"]:
            return jsonify({
                "error": result.get("text", "Não foi possível analisar o vídeo"),
                "debug": result
            })

        download_url = result.get("url")

        if not download_url:
            return jsonify({
                "error": "API não retornou link de download",
                "debug": result
            })

        return jsonify({
            "resolutions": ["Qualidade automática"],
            "download": download_url
        })

    except Exception as e:

        return jsonify({"error": str(e)})


@app.route("/download", methods=["POST"])
def download():

    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL não enviada"})

    try:

        result = get_cobalt(url)

        if result.get("status") not in ["success", "stream"]:
            return jsonify({
                "error": result.get("text", "Falha ao gerar download"),
                "debug": result
            })

        download_url = result.get("url")

        if not download_url:
            return jsonify({
                "error": "API não retornou link de download",
                "debug": result
            })

        return jsonify({
            "download": download_url
        })

    except Exception as e:

        return jsonify({"error": str(e)})


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
