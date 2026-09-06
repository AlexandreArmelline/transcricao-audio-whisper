# =============================================================================
# BLOCO 1 - NÚCLEO DE TRANSCRIÇÃO PARA HUGGING FACE ZEROGPU (GPU NVIDIA)
# =============================================================================
# Este módulo é usado SOMENTE quando o app roda em um Space do Hugging Face
# com hardware ZeroGPU (GPU NVIDIA gratuita).
#
# IMPORTANTE (arquitetura):
# -----------------------------------------------------------------------------
# No ZeroGPU a função que usa GPU deve ser decorada com @spaces.GPU e a GPU é
# alocada APENAS durante a execução dela. Para NÃO aninhar dois decorators
# (o que causaria alocação dupla), a função decorada fica no app.py (raiz):
#
#     @GPU
#     def transcrever_audio(...):          # <-- decorada (app.py)
#         texto = transcrever_no_gpu(...)  # <-- função pura (este módulo)
#
# Este módulo exporta a função PURA (sem decorator). Ela é chamada DENTRO do
# contexto GPU já alocado pela função decorada. O modelo é carregado na 1ª
# chamada e fica em cache na variável global _MODELO (persiste no worker).

# 1.1 Importações
# -----------------------------------------------------------------------------
import os

# 1.2 Configurações
# -----------------------------------------------------------------------------
# No ZeroGPU usamos o modelo MAIS PRECISO (large-v3) com float16 (precisão
# nativa de GPU — excelente e muito rápida).
MODELO_ZEROGPU = os.environ.get('WHISPER_MODEL_ZEROGPU', 'large-v3').strip()
COMPUTE_ZEROGPU = 'float16'

# Cache do modelo em memória (carregado apenas na 1ª chamada do worker)
_MODELO = None

# Traduz o código do seletor (pt-BR, en-US...) para o código do Whisper (pt, en)
IDIOMAS_WHISPER = {
    'pt-BR': 'pt', 'pt': 'pt',
    'en-US': 'en', 'en': 'en',
    'es-ES': 'es', 'es': 'es',
    'fr-FR': 'fr', 'fr': 'fr',
    'de-DE': 'de', 'de': 'de',
    'it-IT': 'it', 'it': 'it',
}

# Prompt inicial em cada idioma (melhora a pontuação da transcrição)
PROMPTS_IDIOMA = {
    'pt': 'Transcreva exatamente o que foi dito, mantendo a pontuação '
          'natural do português.',
    'en': 'Transcribe exactly what was said, keeping the natural English '
          'punctuation.',
    'es': 'Transcriba exactamente lo que se dijo, manteniendo la puntuación '
          'natural del español.',
    'fr': 'Transcrivez exactement ce qui a été dit, en conservant la '
          'ponctuation naturelle du français.',
    'de': 'Transkribieren Sie genau das Gesagte und behalten Sie die '
          'natürliche deutsche Zeichensetzung bei.',
    'it': 'Trascrivi esattamente ciò che è stato detto, mantenendo la '
          'punteggiatura naturale dell\'italiano.',
}

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.2 Configurações
# -----------------------------------------------------------------------------
# Fim bloco 1 NÚCLEO DE TRANSCRIÇÃO PARA HUGGING FACE ZEROGPU
# =============================================================================


# =============================================================================
# BLOCO 2 - FUNÇÃO PURA DE TRANSCRIÇÃO (chamada dentro do contexto @GPU)
# =============================================================================

# 2.1 Função principal: transcreve o áudio usando a GPU do ZeroGPU
# -----------------------------------------------------------------------------
def transcrever_no_gpu(caminho_audio, codigo_idioma):
    """Transcreve um áudio usando Whisper na GPU (ZeroGPU).

    ATENÇÃO: esta função NÃO possui @spaces.GPU. Ela DEVE ser chamada de
    dentro de uma função decorada com @GPU (a GPU já está alocada). Por isso
    o modelo é carregado aqui dentro (na 1ª chamada) e fica em cache na
    variável global _MODELO para as chamadas seguintes.

    Parâmetros:
        caminho_audio: caminho do arquivo de áudio (upload/microfone).
        codigo_idioma: código do idioma (ex.: 'pt-BR', 'en-US').

    Retorno:
        texto transcrito (str).
    """
    global _MODELO

    # 2.1.0 Garante que as bibliotecas CUDA estejam ativas NESTE processo
    # -------------------------------------------------------------------
    # O decorator @spaces.GPU executa esta função em um worker/subprocesso
    # com GPU. Esse processo reimporta os módulos do app — então o
    # config_cuda (importado no topo do app.py) roda aqui também. Por
    # segurança, chamamos a ativação explicitamente antes de importar o
    # faster-whisper (ctranslate2), que procura libcublas.so.12 no load.
    try:
        from config_cuda import ativar_cuda  # import relativo ao projeto
        ativar_cuda()
    except Exception:
        pass  # sem config_cuda (CPU) — segue o fluxo

    # 2.1.1 Importa o faster-whisper dentro da função (worker GPU)
    from faster_whisper import WhisperModel

    # 2.1.2 Converte o idioma (ex.: pt-BR -> pt)
    idioma = IDIOMAS_WHISPER.get(codigo_idioma, 'pt')

    # 2.1.3 Carrega o modelo apenas na primeira chamada (cache no worker)
    # ---------------------------------------------------------------------
    # Tenta PRIMEIRO na GPU (mais rápido). Se as bibliotecas CUDA não
    # estiverem disponíveis (libcublas.12 etc.), cai para a CPU com um
    # modelo MENOR (large-v3 em CPU de Space ficaria lento demais).
    if _MODELO is None:
        try:
            print(
                f'[ZeroGPU] Carregando modelo "{MODELO_ZEROGPU}" '
                f'(compute_type={COMPUTE_ZEROGPU}) na GPU...',
                flush=True,
            )
            _MODELO = WhisperModel(
                MODELO_ZEROGPU,
                device='cuda',
                compute_type=COMPUTE_ZEROGPU,
            )
            print('[ZeroGPU] Modelo pronto na GPU!', flush=True)
        except Exception as erro:  # noqa: BLE001 — CUDA indisponível
            # Fallback CPU: escolhe um modelo razoável (não o large-v3).
            modelo_cpu = os.environ.get(
                'WHISPER_MODEL_CPU_FALLBACK', 'medium'
            ).strip()
            print(
                f'[ZeroGPU] GPU indisponível ({erro}). '
                f'Usando CPU com modelo "{modelo_cpu}" (int8_float32)...',
                flush=True,
            )
            _MODELO = WhisperModel(
                modelo_cpu,
                device='cpu',
                compute_type='int8_float32',
                cpu_threads=0,
            )
            print('[ZeroGPU] Modelo pronto na CPU (fallback)!', flush=True)

    # 2.1.4 Executa a transcrição com parâmetros de máxima precisão
    segmentos, _info = _MODELO.transcribe(
        caminho_audio,
        language=idioma,
        beam_size=5,
        best_of=5,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={
            'min_silence_duration_ms': 500,
        },
        condition_on_previous_text=True,
        without_timestamps=True,
        initial_prompt=PROMPTS_IDIOMA.get(idioma, PROMPTS_IDIOMA['pt']),
    )

    # 2.1.5 Une os trechos em um único texto
    texto = ' '.join(
        segmento.text.strip() for segmento in segmentos
    ).strip()

    return texto

# -----------------------------------------------------------------------------
# Fim sub-bloco 2.1 Função principal: transcreve o áudio usando a GPU
# -----------------------------------------------------------------------------
# Fim bloco 2 FUNÇÃO PURA DE TRANSCRIÇÃO
# =============================================================================


# =============================================================================
# ÍNDICE
# =============================================================================
# 1 NÚCLEO DE TRANSCRIÇÃO PARA HUGGING FACE ZEROGPU
#   1.1 Importações
#   1.2 Configurações
# 2 FUNÇÃO PURA DE TRANSCRIÇÃO
#   2.1 Função principal: transcreve o áudio usando a GPU
# =============================================================================
