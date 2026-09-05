# =============================================================================
# BLOCO 1 - IMPORTAÇÕES E CONFIGURAÇÃO DA APLICAÇÃO
# =============================================================================

# 1.1 Importações da biblioteca padrão
import os
import time
import uuid
import datetime
import threading

# 1.2 Importações de terceiros (Flask)
from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_from_directory,
)

# 1.3 Configuração da aplicação
app = Flask(__name__)

# Caminhos do projeto (resolvidos a partir deste arquivo)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pastas configuráveis por variável de ambiente (útil para montar volumes
# persistentes em servidores de produção). Padrão: pasta local do projeto.
UPLOAD_FOLDER = os.environ.get(
    'PASTA_UPLOADS',
    os.path.join(BASE_DIR, 'uploads')
)
TRANSCRICOES_FOLDER = os.environ.get(
    'PASTA_TRANSCRICOES',
    os.path.join(os.path.dirname(BASE_DIR), 'transcricoes')
)

# Pasta onde o modelo Whisper fica em cache no disco. Manter em volume
# persistente no deploy evita re-baixar ~150 MB a cada reinício.
# - Se PASTA_MODELOS NÃO for definida: usa o cache padrão do Hugging Face
#   (~/.cache/huggingface no Linux/Windows) — ideal para testes locais, pois
#   aproveita modelos já baixados.
# - Em produção (Docker/plataforma): defina PASTA_MODELOS apontando para um
#   volume persistente (ex.: /data/models).
MODELOS_FOLDER = os.environ.get('PASTA_MODELOS') or None

# Cria as pastas, caso ainda não existam
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TRANSCRICOES_FOLDER, exist_ok=True)
if MODELOS_FOLDER:
    os.makedirs(MODELOS_FOLDER, exist_ok=True)

# Limite máximo de upload: 50 MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Formatos de áudio permitidos. Inclui os formatos produzidos por:
#   - Chrome/Edge/Android  -> webm, ogg (Opus)
#   - Safari (iPhone/iPad) -> m4a, mp4 (AAC)  <-- importante para celulares
#   - Uploads diversos     -> mp3, wav, aac, opus
EXTENSOES_PERMITIDAS = {
    'webm', 'ogg', 'mp3', 'wav', 'm4a', 'mp4', 'opus', 'aac',
}

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.3 Configuração da aplicação
# -----------------------------------------------------------------------------

# 1.4 Configuração da transcrição com IA (Whisper)
# -----------------------------------------------------------------------------
# O sistema ESCOLHE AUTOMATICAMENTE o melhor modelo conforme a memória RAM
# disponível do servidor:
#
#   RAM disponível >= 12 GB -> 'large-v3'  (o MAIS preciso da OpenAI)
#   RAM disponível >=  7 GB -> 'medium'
#   RAM disponível >=  3 GB -> 'small'
#   RAM disponível >=  2 GB -> 'base'
#   caso contrário          -> 'tiny'
#
# Assim, em servidores melhores a precisão aumenta sozinha, sem configuração.
# Você pode FIXAR um modelo manualmente pela variável de ambiente WHISPER_MODEL
# (ex.: WHISPER_MODEL=large-v3). Valores aceitos:
#   'tiny', 'base', 'small', 'medium', 'large-v3'  (ou 'auto' para automático)
WHISPER_MODEL = os.environ.get('WHISPER_MODEL', 'auto').strip().lower()

# Traduz o código de idioma do seletor do navegador para o código do Whisper
IDIOMAS_WHISPER = {
    'pt-BR': 'pt', 'pt': 'pt',
    'en-US': 'en', 'en': 'en',
    'es-ES': 'es', 'es': 'es',
    'fr-FR': 'fr', 'fr': 'fr',
    'de-DE': 'de', 'de': 'de',
    'it-IT': 'it', 'it': 'it',
}

# Prompt inicial em cada idioma: orienta o modelo a transcrever com a
# pontuação natural do idioma (melhora a precisão e evita "invenções").
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

# Trava para permitir apenas uma transcrição por vez (evita sobrecarga)
_LOCK_WHISPER = threading.Lock()
_MODELO_CARREGADO = None  # Guarda o modelo já carregado em memória (cache)

# Memória RAM aproximada necessária para o tipo float32 de cada modelo
# (usada para decidir entre float32 - mais preciso - e int8 - mais leve).
_RAM_FLOAT32_GB = {
    'tiny': 1.0,
    'base': 2.0,
    'small': 4.0,
    'medium': 10.0,
    'large-v3': 20.0,
}


# 1.4.1 Lê a memória RAM disponível do servidor (com psutil quando possível)
def obter_ram_disponivel_gb():
    """Retorna a RAM disponível em GB (float) ou 3.5 se não for possível medir."""
    try:
        import psutil  # import opcional (presente em produção)
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        # Fallback conservador: assume que cabe ao menos o modelo 'small'
        return 3.5


# 1.4.2 Decide o modelo e o tipo de precisão mais adequados ao servidor
def escolher_config_whisper():
    """Retorna (modelo, compute_type) conforme a RAM disponível."""
    # 1) Usuário fixou um modelo manualmente? Respeita a escolha.
    if WHISPER_MODEL and WHISPER_MODEL != 'auto':
        comp = os.environ.get('WHISPER_COMPUTE_TYPE', 'int8_float32').lower()
        return WHISPER_MODEL, comp

    # 2) Seleção automática: maior modelo que cabe na RAM disponível
    ram = obter_ram_disponivel_gb()
    if ram >= 12.0:
        modelo = 'large-v3'
    elif ram >= 7.0:
        modelo = 'medium'
    elif ram >= 3.0:
        modelo = 'small'
    elif ram >= 2.0:
        modelo = 'base'
    else:
        modelo = 'tiny'

    # 3) Escolhe o compute_type:
    #    float32 = máxima precisão (usa ~2x a RAM do int8)
    #    int8_float32 = excelente precisão com consumo reduzido
    comp = os.environ.get('WHISPER_COMPUTE_TYPE', '').lower()
    if not comp:
        necessidade_float = _RAM_FLOAT32_GB.get(modelo, 4.0)
        if ram >= necessidade_float + 2.0:
            comp = 'float32'
        else:
            comp = 'int8_float32'
    return modelo, comp


# Decide uma única vez na inicialização do processo
MODELO_ATIVO, COMPUTE_TYPE_ATIVO = escolher_config_whisper()
app.logger.info(
    'Whisper configurado: modelo=%s | compute_type=%s',
    MODELO_ATIVO, COMPUTE_TYPE_ATIVO,
)

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.4.2 Decide o modelo e o tipo de precisão mais adequados
# -----------------------------------------------------------------------------

# 1.4.3 Suporte ao Hugging Face Spaces ZeroGPU (GPU NVIDIA grátis)
# -----------------------------------------------------------------------------
# O ZeroGPU é o hardware gratuito dos Spaces novos. Ele fornece acesso a uma
# GPU NVIDIA (A100) por requisição — perfeito para o Whisper (muito mais
# rápido que CPU). Para usá-lo, decoramos a função pesada com @spaces.GPU e
# carregamos o modelo com device='cuda' e compute_type='float16'.

# Detecta se estamos rodando dentro de um Space do Hugging Face
def em_ambiente_hf_spaces():
    """True quando o código roda em um Hugging Face Space (ZeroGPU)."""
    return any(
        chave in os.environ
        for chave in ('SPACE_ID', 'SPACE_HOST', 'HF_SPACE', 'SPACES_GPU')
    )


# Tenta importar o decorator oficial do ZeroGPU (pacote `spaces`).
# - No HF Spaces ZeroGPU: vira o decorator real (aloca GPU para a função).
# - Em qualquer outro ambiente (local, Render, Railway...): vira um decorator
#   neutro que apenas repassa a função — nada muda no comportamento.
try:
    from spaces import GPU as _decorator_gpu  # type: ignore

    _ZEROGPU_DISPONIVEL = True
except Exception:  # noqa: BLE001 — pacote opcional ausente
    _ZEROGPU_DISPONIVEL = False

    def _decorator_gpu(funcao):
        """Decorator neutro quando o pacote `spaces` não está instalado."""
        return funcao

# Flag usada pelo app Gradio: True => transcrição deve usar a GPU (ZeroGPU).
USAR_ZEROGPU = _ZEROGPU_DISPONIVEL and em_ambiente_hf_spaces()
app.logger.info('ZeroGPU (Hugging Face): %s', 'ATIVO' if USAR_ZEROGPU else 'inativo')

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.4.3 Suporte ao Hugging Face Spaces ZeroGPU
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Fim sub-bloco 1.4 Configuração da transcrição com IA (Whisper)
# -----------------------------------------------------------------------------
# Fim bloco 1 IMPORTAÇÕES E CONFIGURAÇÃO DA APLICAÇÃO
# =============================================================================


# =============================================================================
# BLOCO 2 - FUNÇÕES AUXILIARES
# =============================================================================

# 2.1 Função para saber se a extensão do arquivo é permitida
def extensao_permitida(nome_arquivo):
    """Retorna True se a extensão do arquivo está na lista de permitidas."""
    if '.' not in nome_arquivo:
        return False
    extensao = nome_arquivo.rsplit('.', 1)[1].lower()
    return extensao in EXTENSOES_PERMITIDAS


# 2.2 Função que cria um nome de arquivo único
def nome_unico(extensao):
    """Gera um nome de arquivo único usando data/hora e UUID."""
    agora = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    codigo = uuid.uuid4().hex[:8]
    return f'audio_{agora}_{codigo}.{extensao}'


# 2.3 Função para gerar o nome do arquivo de transcrição (texto)
def nome_transcricao(extensao='txt'):
    """Gera um nome de arquivo de transcrição baseado na data/hora."""
    agora = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'transcricao_{agora}.{extensao}'

# -----------------------------------------------------------------------------
# Fim sub-bloco 2.3 Função para gerar o nome do arquivo de transcrição (texto)
# -----------------------------------------------------------------------------

# 2.4 Transcreve um arquivo de áudio com a IA Whisper (faster-whisper)
def transcrever_com_whisper(caminho_audio, codigo_idioma):
    """Converte o áudio em texto usando Whisper, executado no próprio servidor.

    O import é feito dentro da função (lazy) para o servidor não quebrar
    caso o pacote ainda não esteja instalado.
    """
    global _MODELO_CARREGADO

    # 2.4.1 Importa o pacote somente quando for necessário
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError(
            'Pacote faster-whisper não instalado. '
            'Execute no terminal: python -m pip install faster-whisper'
        )

    # 2.4.2 Converte o código do seletor (ex.: pt-BR) para o código do Whisper
    idioma = IDIOMAS_WHISPER.get(codigo_idioma, 'pt')

    # 2.4.3 Garante que apenas uma transcrição rode por vez
    with _LOCK_WHISPER:
        # Carrega o modelo apenas na primeira vez (fica em cache depois)
        # cpu_threads=0 usa todos os núcleos disponíveis.
        if _MODELO_CARREGADO is None:
            app.logger.info(
                'Carregando modelo Whisper "%s" (compute_type=%s)... '
                'Isso acontece apenas uma vez.',
                MODELO_ATIVO, COMPUTE_TYPE_ATIVO,
            )
            if USAR_ZEROGPU:
                # No ZeroGPU: roda na GPU NVIDIA (A100) com float16
                # (precisão máxima suportada em GPU e muito mais rápido).
                _MODELO_CARREGADO = WhisperModel(
                    MODELO_ATIVO,
                    device='cuda',
                    compute_type='float16',
                    download_root=MODELOS_FOLDER,
                )
            else:
                # Em CPU: usa o compute_type escolhido pela RAM disponível
                _MODELO_CARREGADO = WhisperModel(
                    MODELO_ATIVO,
                    device='cpu',
                    compute_type=COMPUTE_TYPE_ATIVO,
                    cpu_threads=0,      # usa todos os núcleos do processador
                    num_workers=1,      # uma transcrição por vez (estável)
                    download_root=MODELOS_FOLDER,  # cache persistente (ou padrão)
                )
            app.logger.info('Modelo Whisper carregado com sucesso.')

        # 2.4.4 Executa a transcrição com os parâmetros de MAIOR precisão
        segmentos, _info = _MODELO_CARREGADO.transcribe(
            caminho_audio,
            language=idioma,             # fixa o idioma (não fica "adivinhando")
            beam_size=5,                 # busca em feixe ampla (melhor precisão)
            best_of=5,                   # considera as 5 melhores hipóteses
            temperature=0.0,             # resposta determinística e mais fiel
            vad_filter=True,             # remove silêncios antes de transcrever
            vad_parameters={
                'min_silence_duration_ms': 500,  # ignora pausas curtas
            },
            condition_on_previous_text=True,     # mantém contexto entre frases
            word_timestamps=False,       # sem timestamps (mais rápido)
            without_timestamps=True,     # gera texto puro, sem marcas de tempo
            initial_prompt=PROMPTS_IDIOMA.get(idioma, PROMPTS_IDIOMA['pt']),
        )

        # 2.4.5 Une os trechos transcritos em um único texto
        texto = ' '.join(
            segmento.text.strip() for segmento in segmentos
        ).strip()

    return texto

# -----------------------------------------------------------------------------
# Fim sub-bloco 2.4 Transcreve um arquivo de áudio com a IA Whisper
# -----------------------------------------------------------------------------

# 2.5 Pré-carrega o modelo Whisper em memória (usado no startup do app Gradio)
def preaquecer_modelo():
    """Carrega o modelo Whisper em memória sem transcrever nada.

    Útil no Hugging Face Spaces: no primeiro acesso (após hibernação) o modelo
    de ~3 GB precisa ser baixado + carregado. Ao chamar isto em background no
    startup, o usuário não precisa esperar o download na primeira transcrição.
    """
    global _MODELO_CARREGADO
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return False

    with _LOCK_WHISPER:
        if _MODELO_CARREGADO is None:
            print(
                f'[preaquecimento] Baixando/carregando modelo '
                f'"{MODELO_ATIVO}" em background...',
                flush=True,
            )
            if USAR_ZEROGPU:
                _MODELO_CARREGADO = WhisperModel(
                    MODELO_ATIVO,
                    device='cuda',
                    compute_type='float16',
                    download_root=MODELOS_FOLDER,
                )
            else:
                _MODELO_CARREGADO = WhisperModel(
                    MODELO_ATIVO,
                    device='cpu',
                    compute_type=COMPUTE_TYPE_ATIVO,
                    cpu_threads=0,
                    num_workers=1,
                    download_root=MODELOS_FOLDER,
                )
            print('[preaquecimento] Modelo pronto em memória!', flush=True)
        return _MODELO_CARREGADO is not None

# -----------------------------------------------------------------------------
# Fim sub-bloco 2.5 Pré-carrega o modelo Whisper em memória
# -----------------------------------------------------------------------------
# Fim bloco 2 FUNÇÕES AUXILIARES
# =============================================================================


# =============================================================================
# BLOCO 3 - ROTAS DA APLICAÇÃO
# =============================================================================

# 3.1 Rota principal: renderiza a página
@app.route('/')
def index():
    return render_template(
        'index.html',
        modelo_ativo=MODELO_ATIVO,
        compute_type=COMPUTE_TYPE_ATIVO,
    )


# 3.2 Rota de verificação de saúde (health check) para plataformas de deploy
@app.route('/healthz')
def healthz():
    """Retorna 200 quando o servidor está de pé (usado por monitores)."""
    return jsonify({'status': 'ok', 'modelo': MODELO_ATIVO})


# 3.3 Rota que recebe o upload do áudio gravado
@app.route('/upload', methods=['POST'])
def upload_audio():
    """Recebe o arquivo de áudio enviado pelo navegador e o salva no servidor."""
    # Verifica se um arquivo foi enviado com o campo 'audio'
    if 'audio' not in request.files:
        return jsonify({'erro': 'Nenhum arquivo de áudio foi enviado.'}), 400

    arquivo = request.files['audio']

    # Verifica se o nome do arquivo não está vazio
    if arquivo.filename == '':
        return jsonify({'erro': 'Nome do arquivo vazio.'}), 400

    # Verifica se a extensão é permitida
    if not extensao_permitida(arquivo.filename):
        return jsonify({'erro': 'Formato de áudio não suportado.'}), 400

    # Obtém a extensão original do arquivo
    extensao = arquivo.filename.rsplit('.', 1)[1].lower()

    # Cria um nome único e salva o arquivo
    nome_final = nome_unico(extensao)
    caminho = os.path.join(UPLOAD_FOLDER, nome_final)
    arquivo.save(caminho)

    # Obtém o tamanho do arquivo salvo
    tamanho = os.path.getsize(caminho)

    return jsonify({
        'mensagem': 'Áudio salvo com sucesso!',
        'arquivo': nome_final,
        'tamanho_bytes': tamanho,
    }), 201


# 3.4 Rota que envia o áudio para transcrição com IA (Whisper)
@app.route('/transcrever', methods=['POST'])
def transcrever_audio_ia():
    """Recebe o áudio, salva e transcreve com Whisper no servidor."""
    # Verifica se um arquivo foi enviado com o campo 'audio'
    if 'audio' not in request.files:
        return jsonify({'erro': 'Nenhum arquivo de áudio foi enviado.'}), 400

    arquivo = request.files['audio']

    # Verifica se o nome do arquivo não está vazio
    if arquivo.filename == '':
        return jsonify({'erro': 'Nome do arquivo vazio.'}), 400

    # Verifica se a extensão é permitida
    if not extensao_permitida(arquivo.filename):
        return jsonify({'erro': 'Formato de áudio não suportado.'}), 400

    # Obtém a extensão original e salva o arquivo em uploads/
    extensao = arquivo.filename.rsplit('.', 1)[1].lower()
    nome_final = nome_unico(extensao)
    caminho = os.path.join(UPLOAD_FOLDER, nome_final)
    arquivo.save(caminho)

    # Idioma escolhido no seletor da página (padrão: pt-BR)
    idioma = request.form.get('idioma', 'pt-BR')

    inicio = time.time()
    try:
        # 3.4.1 Executa a transcrição com IA (pode demorar na primeira vez)
        texto = transcrever_com_whisper(caminho, idioma)
        duracao = round(time.time() - inicio, 1)

        return jsonify({
            'transcricao': texto,
            'arquivo': nome_final,
            'idioma': idioma,
            'modelo': MODELO_ATIVO,
            'compute_type': COMPUTE_TYPE_ATIVO,
            'tempo_segundos': duracao,
        }), 200

    except RuntimeError as erro:
        # Erro esperado (pacote não instalado) com mensagem clara
        return jsonify({'erro': str(erro)}), 500

    except Exception:
        # Erro inesperado (modelo, formato inválido, falta de memória etc.)
        app.logger.exception('Falha ao transcrever áudio com Whisper')
        return jsonify({
            'erro': (
                'Falha ao transcrever com a IA. Verifique se o modelo foi '
                'baixado (é preciso internet na primeira vez) e se o arquivo '
                'é um áudio válido.'
            )
        }), 500

# -----------------------------------------------------------------------------
# Fim sub-bloco 3.4 Rota que envia o áudio para transcrição com IA (Whisper)
# -----------------------------------------------------------------------------

# 3.5 Rota que salva o texto da transcrição como arquivo .txt
@app.route('/salvar-transcricao', methods=['POST'])
def salvar_transcricao():
    """Recebe o texto transcrito no cliente e o salva na pasta transcricoes."""
    dados = request.get_json(silent=True) or {}

    # Pega o texto (aceita tanto 'texto' quanto 'transcricao' como chave)
    texto = (dados.get('texto') or dados.get('transcricao') or '').strip()

    if not texto:
        return jsonify({'erro': 'Texto vazio. Nada para salvar.'}), 400

    # Cria o nome do arquivo e grava o texto com codificação UTF-8
    nome_final = nome_transcricao('txt')
    caminho = os.path.join(TRANSCRICOES_FOLDER, nome_final)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(texto)

    return jsonify({
        'mensagem': 'Transcrição salva com sucesso!',
        'arquivo': nome_final,
        'caminho': os.path.join('transcricoes', nome_final),
    }), 201


# 3.6 Rota que lista as transcrições salvas
@app.route('/transcricoes', methods=['GET'])
def listar_transcricoes():
    """Lista todos os arquivos .txt salvos na pasta de transcrições."""
    arquivos = []
    if os.path.isdir(TRANSCRICOES_FOLDER):
        for nome in sorted(os.listdir(TRANSCRICOES_FOLDER)):
            if nome.lower().endswith('.txt'):
                caminho = os.path.join(TRANSCRICOES_FOLDER, nome)
                tamanho = os.path.getsize(caminho)
                arquivos.append({
                    'nome': nome,
                    'tamanho_bytes': tamanho,
                    'data': datetime.datetime.fromtimestamp(
                        os.path.getmtime(caminho)
                    ).strftime('%d/%m/%Y %H:%M'),
                })
    return jsonify({'transcricoes': arquivos})


# 3.7 Rota para baixar/exibir o conteúdo de uma transcrição salva
@app.route('/transcricoes/<nome_arquivo>', methods=['GET'])
def baixar_transcricao(nome_arquivo):
    """Envia o arquivo .txt solicitado para download."""
    # send_from_directory já protege contra travessia de diretório (../)
    return send_from_directory(
        TRANSCRICOES_FOLDER, nome_arquivo, as_attachment=True
    )

# -----------------------------------------------------------------------------
# Fim sub-bloco 3.7 Rota para baixar/exibir o conteúdo de uma transcrição salva
# -----------------------------------------------------------------------------
# Fim bloco 3 ROTAS DA APLICAÇÃO
# =============================================================================


# =============================================================================
# BLOCO 4 - PONTO DE ENTRADA DO SERVIDOR
# =============================================================================

# 4.1 Executa o servidor (modo desenvolvimento quando FLASK_DEBUG=1)
if __name__ == '__main__':
    # Em produção (gunicorn/Procfile) este bloco não é usado — o gunicorn
    # importa `app` diretamente. Aqui servimos apenas para testes locais.
    porta = int(os.environ.get('PORT', '5000'))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'

    # host='0.0.0.0' permite acesso de outros dispositivos na rede local
    app.run(host='0.0.0.0', port=porta, debug=debug, use_reloader=debug)

# -----------------------------------------------------------------------------
# Fim sub-bloco 4.1 Executa o servidor (modo desenvolvimento quando FLASK_DEBUG=1)
# -----------------------------------------------------------------------------
# Fim bloco 4 PONTO DE ENTRADA DO SERVIDOR
# =============================================================================


# =============================================================================
# ÍNDICE
# =============================================================================
# 1 IMPORTAÇÕES E CONFIGURAÇÃO DA APLICAÇÃO
#   1.1 Importações da biblioteca padrão
#   1.2 Importações de terceiros (Flask)
#   1.3 Configuração da aplicação
#   1.4 Configuração da transcrição com IA (Whisper)
#     1.4.1 Lê a memória RAM disponível do servidor
#     1.4.2 Decide o modelo e o tipo de precisão mais adequados ao servidor
# 2 FUNÇÕES AUXILIARES
#   2.1 Função para saber se a extensão do arquivo é permitida
#   2.2 Função que cria um nome de arquivo único
#   2.3 Função para gerar o nome do arquivo de transcrição (texto)
#   2.4 Transcreve um arquivo de áudio com a IA Whisper (faster-whisper)
#   2.5 Pré-carrega o modelo Whisper em memória
# 3 ROTAS DA APLICAÇÃO
#   3.1 Rota principal: renderiza a página
#   3.2 Rota de verificação de saúde (health check)
#   3.3 Rota que recebe o upload do áudio gravado
#   3.4 Rota que envia o áudio para transcrição com IA (Whisper)
#   3.5 Rota que salva o texto da transcrição como arquivo .txt
#   3.6 Rota que lista as transcrições salvas
#   3.7 Rota para baixar/exibir o conteúdo de uma transcrição salva
# 4 PONTO DE ENTRADA DO SERVIDOR
#   4.1 Executa o servidor (modo desenvolvimento quando FLASK_DEBUG=1)
# =============================================================================
