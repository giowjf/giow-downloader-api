#!/bin/bash
set -e

echo "[startup] Iniciando GIOW Downloader API..."
echo "[startup] yt-dlp version: $(yt-dlp --version)"
echo "[startup] node version: $(node --version)"

# Baixa o EJS solver em runtime (tem acesso à rede aqui, diferente do build)
echo "[startup] Baixando EJS solver..."
yt-dlp --remote-components ejs:github \
    --skip-download --print id \
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1 | head -3 || \
    echo "[startup] AVISO: EJS solver não pôde ser baixado — tentando sem ele"

echo "[startup] Iniciando gunicorn..."
exec gunicorn -b 0.0.0.0:5000 \
    --timeout 300 \
    --workers 2 \
    --worker-class gevent \
    --worker-connections 10 \
    app:app
