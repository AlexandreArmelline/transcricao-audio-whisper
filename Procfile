# =============================================================================
# PROCFILE — usado por plataformas de deploy (Render, Railway, Fly.io, etc.)
# =============================================================================
#
# O comando abaixo inicia o servidor com gunicorn (WSGI de produção).
# - workers=1: garante que apenas UM processo roda a IA (o modelo Whisper
#   fica em memória; múltiplos workers duplicariam o consumo de RAM e
#   travaria máquinas menores). Se o servidor tiver MUITA RAM (16+ GB),
#   pode aumentar para 2-4 e adicionar threads.
# - timeout=600: transcrições longas (primeira carga do modelo ou áudios
#   grandes) podem demorar; evita que o gunicorn mate o worker.
# - preload=False (padrão): mantém o app leve na inicialização.
#
# Ajuste o número de workers conforme a RAM do servidor:
#   RAM ~2 GB  -> 1 worker (padrão)
#   RAM ~8+ GB -> gunicorn -w 2 ...
#   RAM ~16+GB -> gunicorn -w 4 --threads 2 ...
# =============================================================================

web: gunicorn --chdir backend -w 1 --threads 1 --timeout 600 -b 0.0.0.0:$PORT app:app
