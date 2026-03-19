FROM python:3.11-slim

WORKDIR /app

# Node.js 20 — necessário para EJS nativo do yt-dlp
RUN apt-get update && apt-get install -y \
  ffmpeg curl git \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baixar o EJS solver script durante o build
# Isso evita o erro "Signature solving failed" em runtime
RUN yt-dlp --remote-components ejs:github --skip-download --print title \
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>/dev/null || \
    echo "[build] EJS solver baixado (ou falhou silenciosamente)"

# Copiar código
COPY . .
RUN mkdir -p /tmp/downloads

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", \
     "--timeout", "300", \
     "--workers", "2", \
     "--worker-class", "gevent", \
     "--worker-connections", "10", \
     "app:app"]
