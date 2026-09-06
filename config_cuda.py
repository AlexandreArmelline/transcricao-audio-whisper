# =============================================================================
# config_cuda.py — ATIVAÇÃO DAS BIBLIOTECAS CUDA DO CTRANSLATE2
# =============================================================================
# PROBLEMA RESOLVIDO:
#   No Hugging Face Spaces ZeroGPU (e em qualquer container que exponha GPU
#   NVIDIA mas NÃO tenha as bibliotecas de runtime do CUDA no caminho do
#   loader), o faster-whisper (motor ctranslate2) falha ao carregar o modelo
#   com:
#
#       Library libcublas.12 is not found or cannot be loaded
#
#   O ctranslate2 NÃO embute essas bibliotecas e, no Linux, o loader dinâmico
#   resolve "libcublas.so.12" pelo LD_LIBRARY_PATH do processo (definido no
#   START do processo). As bibliotecas CUDA instaladas via pip (pacotes
#   nvidia-*-cu12) ficam em site-packages/nvidia/*/lib, que NÃO está no
#   LD_LIBRARY_PATH padrão.
#
# SOLUÇÃO (dupla, para funcionar em 100% dos cenários):
#   1) LD_LIBRARY_PATH:  este módulo roda no IMPORT (antes de qualquer
#      subprocesso do ZeroGPU ser criado). Ao setar LD_LIBRARY_PATH no
#      os.environ ANTES do spawn do worker GPU, o loader dinâmico do
#      subprocesso já enxerga as pastas nvidia/*/lib. (O ZeroGPU executa a
#      função @GPU em um worker subprocesso que herda o ambiente do pai.)
#
#   2) ctypes no processo: mesmo que o ctranslate2 seja carregado no MESMO
#      processo (cenário sem subprocesso), o LD_LIBRARY_PATH de runtime não
#      vale para dlopen já iniciado. Então também carregamos as .so via
#      ctypes com RTLD_GLOBAL, NA ORDEM CORRETA de dependências:
#          libcudart.so.12  (nvidia-cuda-runtime-cu12)  -> carregar 1º
#          libcublas.so.12 / libcublasLt.so.12 (nvidia-cublas-cu12)
#          libcudnn.so.9   (nvidia-cudnn-cu12)          -> carregar por último
#      (libcublas depende de libcudart; carregar cudart antes evita falha de
#      símbolo. RTLD_GLOBAL garante que os símbolos fiquem visíveis para os
#      próximos dlopen do ctranslate2.)
#
# O módulo é 100% inofensivo quando CUDA não existe (retorna False sem erro):
#   - Windows / macOS: não há pastas nvidia/... -> retorna False;
#   - Linux sem nvidia-*-cu12 instalado: não há pastas -> retorna False.
# =============================================================================

# =============================================================================
# 1 BLOCO 1 - LOCALIZAÇÃO DAS BIBLIOTECAS
# =============================================================================

# 1.1 Importações
# -----------------------------------------------------------------------------
import os
import glob
import sysconfig
import ctypes


# 1.2 Mapa de prioridade: nome do pacote -> papel no carregamento
# -----------------------------------------------------------------------------
# A ordem de carregamento via ctypes precisa respeitar as dependências:
#   cuda_runtime (libcudart) -> cublas (usa libcudart) -> cudnn (usa ambos)
ORDEM_CARREGAMENTO = (
    'cuda_runtime',   # libcudart.so.12
    'cublas',         # libcublas.so.12 / libcublasLt.so.12
    'cudnn',          # libcudnn.so.9
)


# 1.3 Localiza as pastas nvidia/*/lib dentro do Python instalado
# -----------------------------------------------------------------------------
def _pastas_por_pacote():
    """Retorna {nome_pacote: [pastas/lib]} encontradas em site-packages."""
    bases = set()

    # Caminhos oficiais do Python (purelib/platlib)
    for chave in ('purelib', 'platlib'):
        caminho = sysconfig.get_paths().get(chave)
        if caminho:
            bases.add(caminho)

    # Caminhos de site (inclui usuário e virtuais)
    try:
        import site  # import local para não poluir o escopo
        bases.update(site.getsitepackages())
        bases.add(site.getusersitepackages())
    except Exception:
        pass

    resultado = {}
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        padrao = os.path.join(base, 'nvidia', '*', 'lib')
        for pasta in glob.glob(padrao):
            if not os.path.isdir(pasta):
                continue
            nome = os.path.basename(os.path.dirname(pasta))  # ex.: cublas
            resultado.setdefault(nome, [])
            if pasta not in resultado[nome]:
                resultado[nome].append(pasta)
    return resultado


# -----------------------------------------------------------------------------
# Fim sub-bloco 1.3 Localiza as pastas nvidia/*/lib dentro do Python
# -----------------------------------------------------------------------------
# Fim bloco 1 LOCALIZAÇÃO DAS BIBLIOTECAS
# =============================================================================


# =============================================================================
# 2 BLOCO 2 - ATIVAÇÃO DAS BIBLIOTECAS
# =============================================================================

# 2.1 Função principal: ativa o CUDA (LD_LIBRARY_PATH + ctypes)
# -----------------------------------------------------------------------------
def ativar_cuda():
    """Tenta disponibilizar libcublas/libcudnn/libcudart para o ctranslate2.

    Retorno:
        True  -> encontrou pastas nvidia e tentou ativar;
        False -> não há bibliotecas CUDA instaladas via pip (CPU puro).
    """
    pacotes = _pastas_por_pacote()
    if not pacotes:
        return False

    # 2.1.1 Monta o LD_LIBRARY_PATH (herdado por subprocessos do ZeroGPU)
    # -------------------------------------------------------------------
    todas_pastas = [
        pasta
        for pastas in pacotes.values()
        for pasta in pastas
    ]
    atual = os.environ.get('LD_LIBRARY_PATH', '')
    novo = os.pathsep.join(todas_pastas)
    if novo and novo not in atual:
        os.environ['LD_LIBRARY_PATH'] = (
            novo + (os.pathsep + atual if atual else '')
        )

    # 2.1.2 Carrega as .so no processo atual via ctypes (RTLD_GLOBAL)
    # -------------------------------------------------------------------
    # Ordem respeita ORDEM_CARREGAMENTO (dependências primeiro).
    # RTLD_GLOBAL (ctypes.DEFAULT_MODE é RTLD_LOCAL) deixa os símbolos
    # visíveis para os próximos dlopen do ctranslate2.
    try:
        RTLD_GLOBAL = os.environ.get('RTLD_GLOBAL', '1') and 0x10000
    except Exception:  # noqa: BLE001
        RTLD_GLOBAL = 0x10000  # valor padrão no Linux (glibc)

    def _carregar_pasta(pasta):
        carregou_alguma = False
        for lib in sorted(glob.glob(os.path.join(pasta, '*.so*'))):
            if not os.path.isfile(lib):
                continue
            try:
                ctypes.CDLL(lib, mode=RTLD_GLOBAL)
                carregou_alguma = True
            except Exception:  # noqa: BLE001 — tenta a próxima .so
                continue
        return carregou_alguma

    for nome_pacote in ORDEM_CARREGAMENTO:
        for pasta in pacotes.get(nome_pacote, []):
            _carregar_pasta(pasta)

    # Carrega qualquer outro pacote nvidia (não listado) como reforço
    ja_vistos = set(ORDEM_CARREGAMENTO)
    for nome_pacote, pastas in pacotes.items():
        if nome_pacote not in ja_vistos:
            for pasta in pastas:
                _carregar_pasta(pasta)

    # 2.1.3 Diagnóstico (não bloqueia): informa o que foi encontrado
    # -------------------------------------------------------------------
    tem_cublas = bool(pacotes.get('cublas'))
    tem_cudart = bool(pacotes.get('cuda_runtime'))
    print(
        '[config_cuda] CUDA ativado via pip: '
        f'cublas={tem_cublas} cudart={tem_cudart} '
        f'cudnn={bool(pacotes.get("cudnn"))} | '
        f'LD_LIBRARY_PATH atualizado com {len(todas_pastas)} pasta(s).',
        flush=True,
    )
    return True


# 2.2 Executa a ativação automaticamente no import (conveniência)
# -----------------------------------------------------------------------------
# O ctranslate2 pode ser carregado no processo principal OU num subprocesso
# do ZeroGPU que importa os módulos do app — nos dois casos este import roda
# antes de qualquer uso do faster-whisper (que é importado de forma lazy).
_ATIVADO = ativar_cuda()

# -----------------------------------------------------------------------------
# Fim sub-bloco 2.2 Executa a ativação automaticamente no import
# -----------------------------------------------------------------------------
# Fim bloco 2 ATIVAÇÃO DAS BIBLIOTECAS
# =============================================================================


# =============================================================================
# ÍNDICE
# =============================================================================
# 1 LOCALIZAÇÃO DAS BIBLIOTECAS
#   1.1 Importações
#   1.2 Mapa de prioridade: nome do pacote -> papel no carregamento
#   1.3 Localiza as pastas nvidia/*/lib dentro do Python instalado
# 2 ATIVAÇÃO DAS BIBLIOTECAS
#   2.1 Função principal: ativa o CUDA (LD_LIBRARY_PATH + ctypes)
#   2.2 Executa a ativação automaticamente no import
# =============================================================================
