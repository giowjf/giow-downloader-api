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

# Copiar código e scripts
COPY . .
RUN mkdir -p /tmp/downloads && chmod +x /app/startup.sh

EXPOSE 5000

# startup.sh baixa o EJS solver em runtime (onde há acesso à rede)
# e depois inicia o gunicorn
CMD ["/app/startup.sh"]
