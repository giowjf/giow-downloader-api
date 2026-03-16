FROM python:3.11-slim

# instalar ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# criar diretório da app
WORKDIR /app

# copiar arquivos
COPY . .

# instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# expor porta
EXPOSE 10000

# iniciar servidor
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]