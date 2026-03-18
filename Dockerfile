FROM python:3.11-slim

WORKDIR /app

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

# instalar dependências do sistema

RUN apt-get update && apt-get install -y \
  ffmpeg \
  curl \
  nodejs \
  npm \
  chromium \
  fonts-liberation \
  libgtk-3-0 \
  libnss3 \
  libx11-xcb1 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  libgbm1 \
  xdg-utils \
  && rm -rf /var/lib/apt/lists/*

# copiar requirements python

COPY requirements.txt .

# instalar dependências python

RUN pip install --no-cache-dir -r requirements.txt

# garantir yt-dlp atualizado

RUN pip install -U yt-dlp

# copiar package.json

COPY package.json .

# instalar puppeteer

RUN npm install

# copiar resto do projeto

COPY . .

# criar pasta downloads

RUN mkdir -p /tmp/downloads

# expor porta

EXPOSE 5000

# iniciar servidor

CMD gunicorn -b 0.0.0.0:5000 --timeout 120 app:app
