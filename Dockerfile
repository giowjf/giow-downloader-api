FROM python:3.11-slim

WORKDIR /app

# Node.js 20 é necessário para o yt-dlp resolver desafios JS do YouTube (EJS nativo)
# Sem ele, o yt-dlp não consegue gerar PO Token — elimina necessidade do bgutil
RUN apt-get update && apt-get install -y \
  ffmpeg curl git \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .
RUN mkdir -p /tmp/downloads

EXPOSE 5000

# gevent permite workers assíncronos — downloads não travam outros requests
CMD ["gunicorn", "-b", "0.0.0.0:5000", \
     "--timeout", "300", \
     "--workers", "2", \
     "--worker-class", "gevent", \
     "--worker-connections", "10", \
     "app:app"]
