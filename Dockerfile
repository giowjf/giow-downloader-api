FROM python:3.11-slim

WORKDIR /app

# Node.js 20 (necessário para o bgutil pot provider)
RUN apt-get update && apt-get install -y \
  ffmpeg \
  curl \
  supervisor \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

# Instalar o servidor bgutil (gerador automático de PO Token)
RUN pip show bgutil-ytdlp-pot-provider | grep Location | awk '{print $2}' | \
    xargs -I{} find {} -name "server" -type d 2>/dev/null | head -1 > /tmp/server_path.txt || true

# Copiar código da API
COPY . .
RUN mkdir -p /tmp/downloads

# Configurar supervisor para rodar API + bgutil server juntos
RUN mkdir -p /etc/supervisor/conf.d
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 5000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
