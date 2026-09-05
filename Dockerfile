# =============================================================================
# Dockerfile — Imagem pronta para deploy (Render/Railway/Fly/qualquer PaaS)
# =============================================================================
# Recomendado: rodar com pelo menos 8 GB de RAM (16 GB para large-v3).
# Exemplo de run:
#   docker build -t transcricao-audio .
#   docker run -p 5000:5000 -e PORT=5000 -v transc_data:/data transcricao-audio
# =============================================================================

# 1.1 Imagem base com Python 3.11 (compatível com faster-whisper)
FROM python:3.11-slim

# 1.2 Instala bibliotecas de sistema necessárias para ffmpeg/áudio
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 1.3 Define o diretório de trabalho
WORKDIR /app

# 1.4 Copia as dependências primeiro (aproveita cache de camadas do Docker)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 1.5 Copia o código da aplicação
COPY backend /app/backend
COPY Procfile /app/Procfile
COPY runtime.txt /app/runtime.txt

# 1.6 Cria as pastas de dados (volume persistente recomendado em /data)
ENV PASTA_UPLOADS=/data/uploads \
    PASTA_TRANSCRICOES=/data/transcricoes \
    PASTA_MODELOS=/data/models \
    WHISPER_MODEL=auto \
    PORT=5000
RUN mkdir -p /data/uploads /data/transcricoes /data/models

# 1.7 Pré-baixa o modelo Whisper escolhido (evita demora na 1ª transcrição)
#     Ajuste WHISPER_MODEL no build se quiser fixar um modelo:
#       docker build --build-arg WHISPER_MODEL=large-v3 -t transcricao-audio .
ARG WHISPER_MODEL=auto
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN cd /app/backend && python pre_download_modelo.py || echo "Modelo será baixado no 1º uso"

# 1.8 Expõe a porta
EXPOSE 5000

# 1.9 Comando de inicialização (gunicorn com timeout alto para transcrições longas)
CMD ["gunicorn", "--chdir", "/app/backend", "-w", "1", "--timeout", "600", "-b", "0.0.0.0:5000", "app:app"]
