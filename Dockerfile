FROM python:3.11-slim

WORKDIR /app

# Dependências do sistema: apenas o essencial
RUN apt-get update && apt-get install -y \
  ffmpeg \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sempre garantir yt-dlp mais recente no build
RUN pip install -U yt-dlp

# Copiar código
COPY . .

# Criar pasta de downloads temporários
RUN mkdir -p /tmp/downloads

EXPOSE 5000

# startup.sh atualiza yt-dlp antes de subir o servidor
CMD ["bash", "-c", "pip install -q -U yt-dlp && gunicorn -b 0.0.0.0:5000 --timeout 180 --workers 2 app:app"]
