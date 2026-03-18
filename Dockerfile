FROM python:3.11-slim

WORKDIR /app

# instalar dependências do sistema (ffmpeg + chromium + node)

RUN apt-get update && apt-get install -y 
ffmpeg 
curl 
nodejs 
npm 
wget 
gnupg 
ca-certificates 
fonts-liberation 
libappindicator3-1 
libasound2 
libatk-bridge2.0-0 
libatk1.0-0 
libcups2 
libdbus-1-3 
libgbm1 
libgtk-3-0 
libnspr4 
libnss3 
libx11-xcb1 
libxcomposite1 
libxdamage1 
libxrandr2 
xdg-utils 
chromium 
&& rm -rf /var/lib/apt/lists/*

# copiar requirements python

COPY requirements.txt .

# instalar dependências python

RUN pip install --no-cache-dir -r requirements.txt

# garantir yt-dlp atualizado

RUN pip install -U yt-dlp

# copiar package.json do puppeteer

COPY package.json .

# instalar puppeteer

RUN npm install

# copiar resto do projeto

COPY . .

# criar pasta temporária

RUN mkdir -p /tmp/downloads

# gerar cookies automaticamente ao iniciar container

RUN node generateCookies.js || true

# expor porta

EXPOSE 5000

# iniciar API

CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
