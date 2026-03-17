FROM python:3.11-slim

WORKDIR /app

# instalar ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# copiar requirements
COPY requirements.txt .

# instalar dependências python
RUN pip install --no-cache-dir -r requirements.txt

# garantir yt-dlp atualizado
RUN pip install -U yt-dlp

# copiar projeto
COPY . .

# criar pasta downloads
RUN mkdir -p downloads

# expor porta
EXPOSE 5000

# iniciar servidor
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--timeout", "120", "app:app"]
