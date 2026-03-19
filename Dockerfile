FROM python:3.11-slim

WORKDIR /app

# Node.js 20 + dependências do sistema
RUN apt-get update && apt-get install -y \
  ffmpeg curl supervisor git \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Clonar e compilar o servidor bgutil (JavaScript)
# O plugin Python (bgutil-ytdlp-pot-provider) é só o conector —
# o servidor JS precisa ser construído separadamente
RUN git clone --single-branch --branch master \
    https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git \
    /bgutil

RUN cd /bgutil/server && npm ci && npx tsc

# Copiar código da API
COPY . .
RUN mkdir -p /tmp/downloads /var/log/supervisor

# Configurar supervisord
RUN mkdir -p /etc/supervisor/conf.d
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 5000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
