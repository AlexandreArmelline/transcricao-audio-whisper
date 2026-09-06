# =============================================================================
# BLOCO 1 - IMPORTAÇÕES E CONFIGURAÇÃO INICIAL
# =============================================================================

# 1.1 Importações da biblioteca padrão
# -----------------------------------------------------------------------------
import os
import sys
import time
import threading
import datetime
import uuid

# 1.1.1 Ativa as bibliotecas CUDA do ctranslate2 (se instaladas via pip)
# -----------------------------------------------------------------------------
# Deve rodar ANTES de qualquer import do faster-whisper/ctranslate2 (que tenta
# carregar libcublas.so.12 ao ser importado). No ZeroGPU do HF Spaces as libs
# vêm dos pacotes nvidia-*-cu12 em site-packages/nvidia/*/lib — este módulo as
# localiza, ativa o LD_LIBRARY_PATH e as carrega via ctypes no processo.
import config_cuda  # noqa: E402,F401  (efeito colateral intencional no import)

# 1.2 Coloca a pasta backend/ no caminho de import do Python
# -----------------------------------------------------------------------------
# Este arquivo (app.py) fica na RAIZ do repositório e importa a lógica
# de transcrição existente em backend/app.py. Para o `import app` encontrar o
# arquivo certo (backend/app.py), precisamos adicionar a pasta backend ao path.
CAMINHO_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, CAMINHO_BACKEND)

# 1.3 Reutiliza a lógica de transcrição já existente no backend Flask
# -----------------------------------------------------------------------------
# - transcrever_com_whisper: função que transcreve o áudio com o faster-whisper
# - preaquecer_modelo: carrega o modelo em memória (chamado em background)
# - MODELO_ATIVO / COMPUTE_TYPE_ATIVO: modelo escolhido conforme a RAM do
#   servidor (no HF Spaces free são 16 GB -> large-v3 com int8_float32)
from app import (  # noqa: E402
    transcrever_com_whisper,
    preaquecer_modelo,
    MODELO_ATIVO,
    COMPUTE_TYPE_ATIVO,
    USAR_ZEROGPU,
)

# 1.4 Importa o Gradio (interface web)
# -----------------------------------------------------------------------------
import gradio as gr  # noqa: E402

# 1.5 Decorator oficial do Hugging Face Spaces ZeroGPU
# -----------------------------------------------------------------------------
# Quando rodamos no ZeroGPU, a função que usa a GPU precisa ser decorada com
# @spaces.GPU. A GPU é alocada SOMENTE enquanto essa função executa — por isso
# o modelo deve ser carregado dentro da própria função (ou num helper chamado
# por ela), nunca no módulo. Nos demais ambientes usamos um decorator neutro.
if USAR_ZEROGPU:
    from spaces import GPU  # noqa: E402
else:
    def GPU(funcao):  # noqa: N802 — nome compatível com o pacote oficial
        """Decorator neutro quando não estamos no ZeroGPU."""
        return funcao

# 1.5 Pasta onde as transcrições .txt serão salvas
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSCRICOES_FOLDER = os.environ.get(
    'PASTA_TRANSCRICOES',
    os.path.join(BASE_DIR, 'transcricoes'),
)
os.makedirs(TRANSCRICOES_FOLDER, exist_ok=True)

# 1.6 Idiomas disponíveis no seletor da interface (rótulo -> código interno)
# -----------------------------------------------------------------------------
IDIOMAS_UI = {
    'Português (Brasil)': 'pt-BR',
    'Inglês (EUA)': 'en-US',
    'Espanhol': 'es-ES',
    'Francês': 'fr-FR',
    'Alemão': 'de-DE',
    'Italiano': 'it-IT',
}

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.6 Idiomas disponíveis no seletor da interface
# -----------------------------------------------------------------------------
# Fim bloco 1 IMPORTAÇÕES E CONFIGURAÇÃO INICIAL
# =============================================================================


# =============================================================================
# BLOCO 2 - FUNÇÃO PRINCIPAL DE TRANSCRIÇÃO (usada pela interface Gradio)
# =============================================================================

# 2.1 Função chamada quando o usuário clica em "Transcrever"
# -----------------------------------------------------------------------------
@GPU  # noqa: E305 — no ZeroGPU aloca a GPU NVIDIA só durante a execução
def transcrever_audio(arquivo_audio, idioma_ui):
    """Recebe o áudio (upload ou microfone) e devolve o texto transcrito.

    Parâmetros:
        arquivo_audio: caminho do arquivo temporário criado pelo Gradio.
        idioma_ui:     rótulo do idioma escolhido (ex.: 'Português (Brasil)').

    Retorno:
        texto_transcrito:  o texto gerado pela IA.
        caminho_txt:       caminho do arquivo .txt gerado (para download).
        status_html:       mensagem de status exibida ao usuário.
    """
    # 2.1.1 Valida se um áudio foi enviado/gravado
    if not arquivo_audio:
        raise gr.Error('🎤 Grave um áudio no microfone ou envie um arquivo.')

    # 2.1.2 Converte o rótulo do idioma para o código interno (ex.: pt-BR)
    codigo_idioma = IDIOMAS_UI.get(idioma_ui, 'pt-BR')

    # 2.1.3 Executa a transcrição com Whisper (mede o tempo gasto)
    inicio = time.time()
    try:
        if USAR_ZEROGPU:
            # Ambiente ZeroGPU (HF Spaces com GPU NVIDIA): a transcrição roda
            # no módulo dedicado transcricao_zerogpu.py, onde a função é
            # decorada com @spaces.GPU (a GPU é alocada só durante a chamada).
            # O modelo large-v3 roda em float16 na GPU — MUITO mais rápido.
            from transcricao_zerogpu import transcrever_no_gpu

            texto = transcrever_no_gpu(arquivo_audio, codigo_idioma)
        else:
            # Ambiente normal (CPU): usa a lógica original do backend Flask,
            # que escolhe o melhor modelo conforme a RAM disponível.
            texto = transcrever_com_whisper(arquivo_audio, codigo_idioma)
    except Exception as erro:  # noqa: BLE001 — qualquer erro vira mensagem amigável
        raise gr.Error(f'❌ Falha ao transcrever: {erro}')
    duracao = round(time.time() - inicio, 1)

    if not texto.strip():
        raise gr.Error('⚠️ Nenhuma fala foi detectada no áudio.')

    # 2.1.4 Salva a transcrição em um arquivo .txt (para download)
    nome_txt = f'transcricao_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}.txt'
    caminho_txt = os.path.join(TRANSCRICOES_FOLDER, nome_txt)
    with open(caminho_txt, 'w', encoding='utf-8') as arquivo:
        arquivo.write(texto)

    # 2.1.5 Monta a mensagem de status com o modelo usado
    if USAR_ZEROGPU:
        modelo_usado = 'large-v3 (GPU ZeroGPU)'
        compute_usado = 'float16'
    else:
        modelo_usado = MODELO_ATIVO
        compute_usado = COMPUTE_TYPE_ATIVO
    status = (
        f'✅ Transcrição concluída em **{duracao} s** '
        f'(modelo `{modelo_usado}` · `{compute_usado}`).'
    )

    return texto, caminho_txt, status

# -----------------------------------------------------------------------------
# Fim sub-bloco 2.1 Função chamada quando o usuário clica em "Transcrever"
# -----------------------------------------------------------------------------
# Fim bloco 2 FUNÇÃO PRINCIPAL DE TRANSCRIÇÃO
# =============================================================================


# =============================================================================
# BLOCO 3 - CONSTRUÇÃO DA INTERFACE GRADIO
# =============================================================================

# 3.1 Tema visual (cores do Gradio)
# -----------------------------------------------------------------------------
tema = gr.themes.Soft(primary_hue='indigo', secondary_hue='purple')

# 3.2 Montagem da interface com blocos (layout)
# -----------------------------------------------------------------------------
with gr.Blocks(
    theme=tema,
    title='🎙️ Transcrição de Áudio com Whisper IA',
    css='footer {visibility: hidden}',
) as demo:

    # 3.2.1 Cabeçalho da página
    gr.Markdown(
        '# 🎙️ Transcrição de Áudio com Whisper IA\n'
        'Grave um áudio pelo **microfone** ou envie um arquivo e receba a '
        'transcrição automática com a **IA Whisper** rodando no próprio servidor.'
    )

    # 3.2.2 Entrada de áudio (microfone + upload) e seletor de idioma
    with gr.Row():
        with gr.Column(scale=2):
            entrada_audio = gr.Audio(
                sources=['microphone', 'upload'],
                type='filepath',
                label='🎤 Áudio (grave ou envie um arquivo)',
            )
        with gr.Column(scale=1):
            seletor_idioma = gr.Dropdown(
                choices=list(IDIOMAS_UI.keys()),
                value='Português (Brasil)',
                label='🌐 Idioma do áudio',
            )
            botao_transcrever = gr.Button(
                '✨ Transcrever agora', variant='primary', size='lg'
            )

    # 3.2.3 Área de saída: texto transcrito + download do .txt + status
    saida_texto = gr.Textbox(
        label='📝 Transcrição',
        lines=12,
        placeholder='O texto transcrito aparecerá aqui...',
        show_copy_button=True,
    )
    with gr.Row():
        saida_arquivo = gr.File(label='⬇️ Baixar transcrição (.txt)')
        saida_status = gr.Markdown()

    # 3.2.4 Ação do botão "Transcrever"
    botao_transcrever.click(
        fn=transcrever_audio,
        inputs=[entrada_audio, seletor_idioma],
        outputs=[saida_texto, saida_arquivo, saida_status],
    )

    # 3.2.5 Avisos e instruções
    with gr.Accordion('ℹ️ Como usar / informações', open=False):
        gr.Markdown(
            '- 🎤 **Gravação:** permita o acesso ao microfone do navegador '
            '(funciona no celular e no computador).\n'
            '- 📂 **Upload:** aceita MP3, WAV, M4A, OGG, WEBM, OPUS e AAC.\n'
            '- ⏳ **Primeira transcrição:** o modelo Whisper (cerca de 2–3 GB) '
            'é baixado automaticamente na primeira vez — pode levar alguns '
            'minutos. Depois fica salvo em cache e fica rápido.\n'
            '- 🧠 **Precisão máxima:** no Hugging Face Spaces com ZeroGPU o '
            'sistema usa o modelo **large-v3** rodando em **GPU NVIDIA** — o '
            'mais preciso da OpenAI e com transcrição muito rápida.\n'
            '- 📱 Funciona em celulares e computadores.\n'
            '- 🛡️ Seu áudio é processado **neste servidor** — nada é enviado '
            'para APIs externas.'
        )

# -----------------------------------------------------------------------------
# Fim sub-bloco 3.2 Montagem da interface com blocos (layout)
# -----------------------------------------------------------------------------
# Fim bloco 3 CONSTRUÇÃO DA INTERFACE GRADIO
# =============================================================================


# =============================================================================
# BLOCO 4 - PONTO DE ENTRADA (SUBIR O SERVIDOR)
# =============================================================================

# 4.1 Executa a interface Gradio quando o script é rodado diretamente
# -----------------------------------------------------------------------------
# O Hugging Face Spaces roda `python app.py` e espera o servidor na porta da
# variável PORT (default 7860).
if __name__ == '__main__':
    porta = int(os.environ.get('PORT', '7860'))

    # 4.1.1 Pré-carrega o modelo Whisper em background (não bloqueia o startup)
    # -------------------------------------------------------------------------
    # O HF Spaces grátis hiberna após ~48h sem uso. Quando alguém acessa, o
    # container sobe e este thread já começa a baixar/carregar o modelo
    # (large-v3 ~3 GB na primeira vez). Assim a primeira transcrição é rápida.
    #
    # IMPORTANTE (ZeroGPU): no Hugging Face com ZeroGPU não devemos carregar o
    # modelo em CPU no startup — a GPU é alocada por chamada e o carregamento
    # acontece dentro da função @spaces.GPU (1ª transcrição). O preaquecimento
    # abaixo usa a função de CPU (útil em hardware CPU common); no ZeroGPU a
    # própria @spaces.GPU já cuida do cache entre chamadas.
    if not USAR_ZEROGPU:
        threading.Thread(target=preaquecer_modelo, daemon=True).start()

    # 4.1.2 Sobe o servidor Gradio
    demo.queue().launch(
        server_name='0.0.0.0',
        server_port=porta,
        show_error=True,
    )

# -----------------------------------------------------------------------------
# Fim sub-bloco 4.1 Executa a interface Gradio quando o script é rodado
# -----------------------------------------------------------------------------
# Fim bloco 4 PONTO DE ENTRADA (SUBIR O SERVIDOR)
# =============================================================================


# =============================================================================
# ÍNDICE
# =============================================================================
# 1 IMPORTAÇÕES E CONFIGURAÇÃO INICIAL
#   1.1 Importações da biblioteca padrão
#   1.2 Coloca a pasta backend/ no caminho de import do Python
#   1.3 Reutiliza a lógica de transcrição do backend Flask
#   1.4 Importa o Gradio (interface web)
#   1.5 Pasta onde as transcrições .txt serão salvas
#   1.6 Idiomas disponíveis no seletor da interface
# 2 FUNÇÃO PRINCIPAL DE TRANSCRIÇÃO (usada pela interface Gradio)
#   2.1 Função chamada quando o usuário clica em "Transcrever"
# 3 CONSTRUÇÃO DA INTERFACE GRADIO
#   3.1 Tema visual
#   3.2 Montagem da interface com blocos (layout)
# 4 PONTO DE ENTRADA (SUBIR O SERVIDOR)
#   4.1 Executa a interface Gradio quando o script é rodado diretamente
#     4.1.1 Pré-carrega o modelo Whisper em background
#     4.1.2 Sobe o servidor Gradio
# =============================================================================
