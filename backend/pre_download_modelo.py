# =============================================================================
# BLOCO 1 - PRÉ-DOWNLOAD DO MODELO WHISPER (USAR DURANTE O BUILD DO DEPLOY)
# =============================================================================

# 1.1 Este script baixa antecipadamente o modelo Whisper que será usado em
#     produção, evitando que a PRIMEIRA transcrição de um usuário demore
#     (ou falhe por falta de internet).
#
#     COMO USAR (no comando de build da plataforma de deploy):
#         python backend/pre_download_modelo.py
#
#     O modelo escolhido é o MESMO que o app usará em runtime (auto = melhor
#     conforme a RAM do servidor). Para fixar um modelo:
#         WHISPER_MODEL=large-v3 python backend/pre_download_modelo.py
# -----------------------------------------------------------------------------

# 1.2 Importa a configuração do próprio app (escolha automática do modelo)
import os

# Garante que a escolha automática respeite a RAM do servidor de build
os.environ.setdefault('WHISPER_MODEL', 'auto')

# Importa o app apenas para reutilizar a lógica de escolha (não inicia servidor)
try:
    from app import MODELO_ATIVO, COMPUTE_TYPE_ATIVO
except ImportError:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    from app import MODELO_ATIVO, COMPUTE_TYPE_ATIVO

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.2 Importa a configuração do próprio app
# -----------------------------------------------------------------------------

# 1.3 Executa o download/verificação do modelo escolhido
if __name__ == '__main__':
    print(f'[pre-download] Baixando/verificando modelo "{MODELO_ATIVO}" '
          f'(compute_type={COMPUTE_TYPE_ATIVO})...')

    from faster_whisper import WhisperModel

    # Usa a mesma lógica do app: cache padrão ou PASTA_MODELOS se definida
    import os as _os
    pasta_modelos = _os.environ.get('PASTA_MODELOS') or None

    # Instanciar o modelo força o download do Hugging Face (se ainda não existir)
    modelo = WhisperModel(
        MODELO_ATIVO,
        device='cpu',
        compute_type=COMPUTE_TYPE_ATIVO,
        cpu_threads=2,   # apenas para o build; runtime usará todos os núcleos
        download_root=pasta_modelos,
    )

    print('[pre-download] Modelo pronto e em cache no disco!')

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.3 Executa o download/verificação do modelo escolhido
# -----------------------------------------------------------------------------
# Fim bloco 1 PRÉ-DOWNLOAD DO MODELO WHISPER
# =============================================================================
