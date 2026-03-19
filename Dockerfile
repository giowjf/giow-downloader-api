FROM python:3.11-slim

WORKDIR /app

# Node.js 20 — runtime JS para o yt-dlp resolver desafios do YouTube
RUN apt-get update && apt-get install -y \
  ffmpeg curl \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/*

# yt-dlp[default] inclui o pacote yt-dlp-ejs com todos os scripts EJS
# Isso elimina a necessidade de baixar o solver em runtime
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Criar yt-dlp.conf para habilitar Node.js automaticamente sem precisar
# passar --js-runtimes node em cada chamada
RUN mkdir -p /root/.config/yt-dlp && \
    echo "--js-runtimes node" > /root/.config/yt-dlp/config

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
