import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

COBALT_API = "https://api.cobalt.tools/api/json"


@app.route("/")
def home():
    return {"status": "Giow Downloader API usando Cobalt"}


@app.route("/analyze", methods=["POST"])
def analyze():

    data = request.get_json()
    url = data.get("url")

    try:

        r = requests.post(
            COBALT_API,
            json={
                "url": url
            },
            timeout=30
        )

        result = r.json()

        if "url" not in result:
            return jsonify({"error": "Não foi possível analisar o vídeo"})

        return jsonify({
            "resolutions": ["Qualidade automática"],
            "download": result["url"]
        })

    except Exception as e:

        return jsonify({"error": str(e)})


@app.route("/download", methods=["POST"])
def download():

    data = request.get_json()
    url = data.get("url")

    try:

        r = requests.post(
            COBALT_API,
            json={
                "url": url
            },
            timeout=30
        )

        result = r.json()

        if "url" not in result:
            return jsonify({"error": "Falha ao gerar download"})

        return jsonify({
            "download": result["url"]
        })

    except Exception as e:

        return jsonify({"error": str(e)})


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
