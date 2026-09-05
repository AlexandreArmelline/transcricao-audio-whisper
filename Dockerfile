# =============================================================================
# Dockerfile — Sistema de Transcrição de Áudio (Whisper)
# Compatível com: Hugging Face Spaces (16 GB RAM free) e demais PaaS (Docker)
# =============================================================================
# ► Para Hugging Face Spaces (recomendado — grátis, 2 vCPU + 16 GB RAM):
#   O HF Spaces usa este Dockerfile automaticamente e faz proxy para a
#   porta 7860. Com o modelo large-v3 (int8) a precisão é máxima.
#
# ► Como rodar localmente (teste):
#   docker build -t transcricao-audio .
#   docker run -p 7860:7860 transcricao-audio
#   → abra http://localhost:7860
# =============================================================================

# 1.1 Imagem base com Python 3.11 (compatível com faster-whisper)
# -----------------------------------------------------------------------------
FROM python:3.11-slim

# 1.2 Instala bibliotecas de sistema necessárias (ffmpeg para áudio)
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 1.3 Define o diretório de trabalho
# -----------------------------------------------------------------------------
WORKDIR /app

# 1.4 Copia e instala as dependências (cache de camadas do Docker)
# -----------------------------------------------------------------------------
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 1.5 Copia o código da aplicação
# -----------------------------------------------------------------------------
COPY backend /app/backend

# 1.6 Variáveis de ambiente (configuração de produção)
# -----------------------------------------------------------------------------
# WHISPER_MODEL=large-v3  → o modelo MAIS preciso da OpenAI (roda em 16 GB
#                           com compute_type int8_float32, ~5 GB de RAM).
#                           Para mudar: small / medium / auto (automático).
# WHISPER_COMPUTE_TYPE=int8_float32 → excelente precisão e consumo reduzido.
# PORT é lida em runtime; o HF Spaces espera a porta 7860.
ENV WHISPER_MODEL=large-v3 \
    WHISPER_COMPUTE_TYPE=int8_float32 \
    PASTA_UPLOADS=/app/backend/uploads \
    PASTA_TRANSCRICOES=/app/transcricoes \
    PASTA_MODELOS=/app/backend/models \
    PORT=7860

# Cria as pastas de dados usadas em runtime
RUN mkdir -p /app/backend/uploads /app/transcricoes /app/backend/models

# 1.7 Pré-baixa o modelo Whisper durante o BUILD (1ª transcrição instantânea)
# -----------------------------------------------------------------------------
# Isso evita que o primeiro usuário espere o download de ~3 GB.
# (Se o build falhar por rede, o modelo é baixado no 1º uso automaticamente.)
RUN cd /app/backend && python pre_download_modelo.py \
    || echo "Modelo será baixado no 1º uso (sem internet durante o build)."

# 1.8 Expõe a porta usada pelo Hugging Face Spaces (7860)
# -----------------------------------------------------------------------------
EXPOSE 7860

# 1.9 Comando de inicialização (gunicorn, 1 worker, timeout alto p/ áudios longos)
# -----------------------------------------------------------------------------
# Lê a porta da variável PORT (HF Spaces injeta PORT=7860 automaticamente;
# Render/Railway injetam a porta deles). Padrão: 7860.
CMD ["sh", "-c", "gunicorn --chdir /app/backend -w 1 --timeout 900 -b 0.0.0.0:${PORT:-7860} app:app"]

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.9 Comando de inicialização
# -----------------------------------------------------------------------------
# Fim bloco 1 DOCKERFILE DO SISTEMA DE TRANSCRIÇÃO
# =============================================================================

# =============================================================================
# ÍNDICE
# =============================================================================
# 1 DOCKERFILE DO SISTEMA DE TRANSCRIÇÃO
#   1.1 Imagem base (Python 3.11)
#   1.2 Bibliotecas de sistema (ffmpeg)
#   1.3 Diretório de trabalho
#   1.4 Dependências Python
#   1.5 Código da aplicação
#   1.6 Variáveis de ambiente
#   1.7 Pré-download do modelo Whisper
#   1.8 Porta exposta (7860)
#   1.9 Comando de inicialização (gunicorn)
# =============================================================================
