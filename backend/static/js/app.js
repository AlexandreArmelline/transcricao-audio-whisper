/* ==========================================================================
   BLOCO 1 - SELEÇÃO DE ELEMENTOS DO DOM
   ========================================================================== */

// 1.1 Referências aos elementos da interface
const btnGravar      = document.getElementById('btn-gravar');
const btnParar       = document.getElementById('btn-parar');
const btnApagar      = document.getElementById('btn-apagar');
const btnTranscrever = document.getElementById('btn-transcrever');
const btnCopiar      = document.getElementById('btn-copiar');
const btnSalvar      = document.getElementById('btn-salvar');
const btnAtualizar   = document.getElementById('btn-atualizar');

const statusEl       = document.getElementById('status');
const statusTransc   = document.getElementById('status-transcricao');
const cronometroEl   = document.getElementById('cronometro');
const playerAudio    = document.getElementById('player-audio');
const audioPlayback  = document.getElementById('audio-playback');
const selectIdioma   = document.getElementById('select-idioma');
const resultadoEl    = document.getElementById('resultado');
const mensagemEl     = document.getElementById('mensagem');
const listaEl        = document.getElementById('lista-transcricoes');
const avisoListaEl   = document.getElementById('aviso-lista');
const inputArquivo   = document.getElementById('input-arquivo');
const ajudaArquivo   = document.getElementById('nome-arquivo-ajuda');

// --------------------------------------------------------------------------
// Fim sub-bloco 1.1 Referências aos elementos da interface
// --------------------------------------------------------------------------
// Fim bloco 1 SELEÇÃO DE ELEMENTOS DO DOM
// ==========================================================================


/* ==========================================================================
   BLOCO 2 - VARIÁVEIS DE ESTADO DA APLICAÇÃO
   ========================================================================== */

// 2.1 Estado da gravação
let mediaRecorder = null;      // Gravador de mídia (MediaRecorder)
let gravando      = false;     // Indica se está gravando no momento
let chunks        = [];        // Pedaços (blobs) do áudio gravado
let blobAudio     = null;      // Blob final do áudio gravado
let timerId       = null;      // Identificador do cronômetro
let segundos      = 0;         // Contagem de segundos da gravação

// 2.2 Estado da transcrição (agora feita por IA no servidor)
let transcrevendo = false;     // Indica se está transcrevendo no momento
let arquivoAudio  = null;      // Nome do arquivo salvo no servidor (upload)
let extensaoGravacao = 'webm'; // Extensão do áudio gravado (webm/m4a/ogg)

// 2.3 Guarda o texto final transcrito
let textoFinal = '';

// --------------------------------------------------------------------------
// Fim sub-bloco 2.3 Guarda o texto final transcrito
// --------------------------------------------------------------------------
// Fim bloco 2 VARIÁVEIS DE ESTADO DA APLICAÇÃO
// ==========================================================================


/* ==========================================================================
   BLOCO 3 - FUNÇÕES AUXILIARES DE INTERFACE
   ========================================================================== */

// 3.1 Exibe uma mensagem de sucesso ou erro na tela
function exibirMensagem(texto, tipo) {
    mensagemEl.textContent = texto;
    mensagemEl.className = 'mensagem';
    if (tipo === 'sucesso' || tipo === 'erro') {
        mensagemEl.classList.add(`mensagem--${tipo}`);
    }
    mensagemEl.hidden = false;

    // Esconde a mensagem automaticamente após 6 segundos
    clearTimeout(exibirMensagem._timer);
    exibirMensagem._timer = setTimeout(() => {
        mensagemEl.hidden = true;
    }, 6000);
}

// 3.2 Define o texto e a classe de cor do status do gravador
function setStatus(el, texto, classe) {
    el.textContent = texto;
    el.className = 'status';
    if (classe) {
        el.classList.add(classe);
    }
}

// 3.3 Formata os segundos no padrão MM:SS
function formatarTempo(totalSegundos) {
    const min = String(Math.floor(totalSegundos / 60)).padStart(2, '0');
    const seg = String(totalSegundos % 60).padStart(2, '0');
    return `${min}:${seg}`;
}

// 3.4 Atualiza os botões conforme o estado da aplicação
function atualizarBotoes() {
    btnGravar.disabled      = gravando || transcrevendo;
    btnParar.disabled       = !gravando;
    btnApagar.disabled      = gravando || !blobAudio || transcrevendo;
    btnTranscrever.disabled = gravando || !blobAudio || transcrevendo;
    btnCopiar.disabled      = transcrevendo || !textoFinal.trim();
    btnSalvar.disabled      = transcrevendo || !textoFinal.trim();
    playerAudio.hidden      = !blobAudio;
}

// 3.5 Limpa o resultado da transcrição atual
function limparResultado() {
    textoFinal = '';
    arquivoAudio = null;
    resultadoEl.value = '';
    setStatus(statusTransc, '⏸️ Aguardando áudio para transcrever', null);
}

// --------------------------------------------------------------------------
// Fim sub-bloco 3.5 Limpa o resultado da transcrição atual
// --------------------------------------------------------------------------
// Fim bloco 3 FUNÇÕES AUXILIARES DE INTERFACE
// ==========================================================================


/* ==========================================================================
   BLOCO 4 - FUNÇÕES DE GRAVAÇÃO DE ÁUDIO
   ========================================================================== */

// 4.1 Função assíncrona que inicia a gravação do microfone
async function iniciarGravacao() {
    // 4.1.1 Verifica se o navegador suporta MediaRecorder
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        exibirMensagem('Seu navegador não suporta gravação de áudio. Use o Chrome ou o Edge mais recente.', 'erro');
        return;
    }

    try {
        // 4.1.2 Solicita acesso ao microfone
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // 4.1.3 Define o tipo MIME preferido, com suporte a celulares:
        //   - Chrome/Edge/Android -> audio/webm (Opus)
        //   - Safari (iPhone/iPad) -> audio/mp4 (AAC) — NÃO suporta webm
        const opcoes = {};
        if (window.MediaRecorder && MediaRecorder.isTypeSupported('audio/webm')) {
            opcoes.mimeType = 'audio/webm';
        } else if (window.MediaRecorder && MediaRecorder.isTypeSupported('audio/mp4')) {
            opcoes.mimeType = 'audio/mp4';
        }

        // 4.1.4 Cria o gravador e prepara o estado
        mediaRecorder = new MediaRecorder(stream, opcoes);
        chunks = [];
        gravando = true;

        // 4.1.5 Acumula os pedaços de dados durante a gravação
        mediaRecorder.ondataavailable = (evento) => {
            if (evento.data && evento.data.size > 0) {
                chunks.push(evento.data);
            }
        };

        // 4.1.6 Ao finalizar, monta o blob, libera o microfone e atualiza a tela
        mediaRecorder.onstop = () => {
            const tipoMime = mediaRecorder.mimeType || 'audio/webm';
            blobAudio = new Blob(chunks, { type: tipoMime });

            // Descobre a extensão correta conforme o formato gravado
            // (webm no Chrome/Android; mp4/m4a no Safari/iPhone)
            let extensao = 'webm';
            if (tipoMime.includes('mp4')) extensao = 'm4a';
            else if (tipoMime.includes('ogg')) extensao = 'ogg';
            else if (tipoMime.includes('mp3')) extensao = 'mp3';
            else if (tipoMime.includes('wav')) extensao = 'wav';
            extensaoGravacao = extensao;

            // Libera o stream do microfone (desliga o indicador de uso)
            stream.getTracks().forEach((trilha) => trilha.stop());

            // Prepara o player para ouvir o áudio
            audioPlayback.src = URL.createObjectURL(blobAudio);

            gravando = false;
            atualizarBotoes();
            limparResultado();
            setStatus(statusEl, '✅ Gravação concluída. Clique em 📝 Transcrever.', 'status--sucesso');
        };

        // 4.1.7 Inicia a gravação de fato
        mediaRecorder.start();

        // 4.1.8 Inicia o cronômetro
        segundos = 0;
        cronometroEl.textContent = formatarTempo(segundos);
        timerId = setInterval(() => {
            segundos += 1;
            cronometroEl.textContent = formatarTempo(segundos);
        }, 1000);

        // 4.1.9 Atualiza a interface para o estado de gravação
        setStatus(statusEl, '🔴 Gravando... fale ao microfone', 'status--gravando');
        atualizarBotoes();
    } catch (erro) {
        // 4.1.10 Trata a negativa/perda de permissão do usuário
        console.error('Erro ao acessar o microfone:', erro);
        exibirMensagem(
            'Não foi possível acessar o microfone. Verifique a permissão de uso no navegador.',
            'erro'
        );
        setStatus(statusEl, '⏸️ Pronto para gravar', null);
        gravando = false;
        atualizarBotoes();
    }
}

// 4.2 Para a gravação em andamento
function pararGravacao() {
    if (mediaRecorder && gravando) {
        mediaRecorder.stop(); // Dispara o evento onstop (que finaliza tudo)
        clearInterval(timerId);
        cronometroEl.textContent = '00:00';
    }
}

// 4.3 Apaga o áudio gravado atual
function apagarAudio() {
    blobAudio = null;
    audioPlayback.src = '';
    inputArquivo.value = '';
    ajudaArquivo.textContent = 'MP3, WAV, M4A, OGG, WEBM ou OPUS';
    limparResultado();
    setStatus(statusEl, '🗑️ Áudio apagado. Pronto para uma nova gravação.', null);
    atualizarBotoes();
}

// 4.4 Usa um arquivo de áudio escolhido pelo usuário (upload do dispositivo)
function selecionarArquivoAudio(evento) {
    const arquivo = evento.target.files && evento.target.files[0];
    if (!arquivo) return;

    // 4.4.1 Garante que é um arquivo de áudio
    if (!arquivo.type.startsWith('audio/')) {
        exibirMensagem('Por favor, selecione um arquivo de áudio válido.', 'erro');
        evento.target.value = '';
        return;
    }

    // 4.4.2 Descobre a extensão pelo nome do arquivo
    let extensao = 'webm';
    const nome = arquivo.name.toLowerCase();
    if (nome.endsWith('.mp3')) extensao = 'mp3';
    else if (nome.endsWith('.wav')) extensao = 'wav';
    else if (nome.endsWith('.m4a')) extensao = 'm4a';
    else if (nome.endsWith('.ogg')) extensao = 'ogg';
    else if (nome.endsWith('.opus')) extensao = 'opus';
    else if (nome.endsWith('.aac')) extensao = 'aac';
    else if (nome.endsWith('.mp4')) extensao = 'mp4';
    extensaoGravacao = extensao;

    // 4.4.3 Usa o arquivo como blob de áudio atual
    blobAudio = arquivo;
    audioPlayback.src = URL.createObjectURL(arquivo);
    ajudaArquivo.textContent = `✅ ${arquivo.name}`;

    limparResultado();
    setStatus(statusEl, '✅ Arquivo carregado. Clique em 📝 Transcrever.', 'status--sucesso');
    atualizarBotoes();
}

// --------------------------------------------------------------------------
// Fim sub-bloco 4.4 Usa um arquivo de áudio escolhido pelo usuário
// --------------------------------------------------------------------------
// Fim bloco 4 FUNÇÕES DE GRAVAÇÃO DE ÁUDIO
// ==========================================================================


/* ==========================================================================
   BLOCO 5 - FUNÇÕES DE TRANSCRIÇÃO (IA NO SERVIDOR - WHISPER)
   ========================================================================== */

// 5.1 Envia o áudio gravado para o servidor transcrever com a IA Whisper
async function transcreverAudio() {
    if (!blobAudio) {
        exibirMensagem('Grave um áudio primeiro.', 'erro');
        return;
    }

    // 5.1.1 Prepara o estado visual de transcrição
    transcrevendo = true;
    limparResultado();
    setStatus(statusTransc, '🧠 Enviando áudio para a IA...', 'status--transcrevendo');
    setStatus(statusEl, '🎙️ Áudio enviado para transcrição', 'status--sucesso');
    btnTranscrever.textContent = '⏳ Transcrevendo...';
    atualizarBotoes();

    try {
        // 5.1.2 Monta o FormData com o áudio e o idioma escolhido
        const dados = new FormData();
        dados.append('audio', blobAudio, `gravacao.${extensaoGravacao}`);
        dados.append('idioma', selectIdioma.value);

        setStatus(
            statusTransc,
            '🧠 IA analisando o áudio... (a 1ª vez pode demorar para carregar o modelo)',
            'status--transcrevendo'
        );

        // 5.1.3 Envia para a rota de transcrição com IA no servidor
        const resposta = await fetch('/transcrever', {
            method: 'POST',
            body: dados,
        });

        const dadosResposta = await resposta.json();

        if (!resposta.ok) {
            throw new Error(dadosResposta.erro || 'Erro ao transcrever.');
        }

        // 5.1.4 Preenche o resultado com o texto transcrito pela IA
        textoFinal = (dadosResposta.transcricao || '').trim();
        arquivoAudio = dadosResposta.arquivo || null;
        resultadoEl.value = textoFinal;

        if (textoFinal) {
            setStatus(statusTransc, '✅ Transcrição concluída pela IA!', 'status--sucesso');
            exibirMensagem(
                `✅ Transcrição concluída em ${dadosResposta.tempo_segundos || '?'}s (modelo ${dadosResposta.modelo || 'whisper'}).`,
                'sucesso'
            );
        } else {
            limparResultado();
            setStatus(statusTransc, '⚠️ Nenhuma fala reconhecida no áudio.', null);
            exibirMensagem('Nenhuma fala foi reconhecida. Tente gravar com a voz mais clara.', 'erro');
        }
    } catch (erro) {
        console.error('Erro na transcrição com IA:', erro);
        limparResultado();
        setStatus(statusTransc, '⛔ Falha na transcrição com a IA.', null);
        exibirMensagem(`❌ ${erro.message || 'Erro de conexão com o servidor.'}`, 'erro');
    } finally {
        transcrevendo = false;
        btnTranscrever.textContent = '📝 Transcrever áudio';
        atualizarBotoes();
    }
}

// --------------------------------------------------------------------------
// Fim sub-bloco 5.1 Envia o áudio para transcrever com a IA Whisper
// --------------------------------------------------------------------------
// Fim bloco 5 FUNÇÕES DE TRANSCRIÇÃO (IA NO SERVIDOR - WHISPER)
// ==========================================================================


/* ==========================================================================
   BLOCO 6 - AÇÕES DE TEXTO (COPIAR E SALVAR NO SERVIDOR)
   ========================================================================== */

// 6.1 Copia o texto transcrito para a área de transferência
async function copiarTexto() {
    const texto = resultadoEl.value.trim();
    if (!texto) return;

    try {
        await navigator.clipboard.writeText(texto);
        exibirMensagem('✅ Texto copiado para a área de transferência!', 'sucesso');
    } catch (erro) {
        // Fallback para navegadores sem permissão de clipboard
        resultadoEl.select();
        document.execCommand('copy');
        exibirMensagem('✅ Texto copiado!', 'sucesso');
    }
}

// 6.2 Envia o texto para o servidor salvar como arquivo .txt
async function salvarTranscricao() {
    const texto = (textoFinal || resultadoEl.value || '').trim();
    if (!texto) {
        exibirMensagem('Nada para salvar ainda.', 'erro');
        return;
    }

    // Desabilita o botão enquanto salva (evita envios duplicados)
    btnSalvar.disabled = true;
    btnSalvar.textContent = '💾 Salvando...';

    try {
        const resposta = await fetch('/salvar-transcricao', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ texto }),
        });

        const dados = await resposta.json();

        if (resposta.ok) {
            exibirMensagem(`✅ ${dados.mensagem} (${dados.arquivo})`, 'sucesso');
            listarTranscricoes(); // Atualiza o histórico
        } else {
            exibirMensagem(`❌ ${dados.erro || 'Erro ao salvar.'}`, 'erro');
        }
    } catch (erro) {
        console.error('Erro ao salvar transcrição:', erro);
        exibirMensagem('❌ Erro de conexão com o servidor.', 'erro');
    } finally {
        btnSalvar.disabled = false;
        btnSalvar.textContent = '💾 Salvar transcrição';
    }
}

// --------------------------------------------------------------------------
// Fim sub-bloco 6.2 Envia o texto para o servidor salvar como arquivo .txt
// --------------------------------------------------------------------------
// Fim bloco 6 AÇÕES DE TEXTO (COPIAR E SALVAR NO SERVIDOR)
// ==========================================================================


/* ==========================================================================
   BLOCO 7 - HISTÓRICO DE TRANSCRIÇÕES (CONSULTA/BACKEND)
   ========================================================================== */

// 7.1 Busca a lista de transcrições salvas no servidor
async function listarTranscricoes() {
    try {
        const resposta = await fetch('/transcricoes');
        const dados = await resposta.json();

        listaEl.innerHTML = '';
        avisoListaEl.hidden = true;

        // 7.1.1 Se não houver transcrições, exibe o aviso
        if (!dados.transcricoes || dados.transcricoes.length === 0) {
            avisoListaEl.hidden = false;
            return;
        }

        // 7.1.2 Cria um item da lista para cada transcrição encontrada
        dados.transcricoes.forEach((item) => {
            const li = document.createElement('li');
            li.className = 'lista__item';

            // Bloco de informações (nome + data)
            const info = document.createElement('div');
            info.className = 'lista__info';

            const nome = document.createElement('span');
            nome.className = 'lista__nome';
            nome.textContent = item.nome;

            const meta = document.createElement('span');
            meta.className = 'lista__meta';
            meta.textContent = `📅 ${item.data} • ${formatarBytes(item.tamanho_bytes)}`;

            info.appendChild(nome);
            info.appendChild(meta);

            // Bloco de ações (baixar / abrir)
            const acoes = document.createElement('div');
            acoes.className = 'lista__acoes';

            // Botão de download
            const btnBaixar = document.createElement('button');
            btnBaixar.type = 'button';
            btnBaixar.className = 'botao botao--salvar';
            btnBaixar.textContent = '⬇️ Baixar';
            btnBaixar.addEventListener('click', () => baixarTranscricao(item.nome));

            acoes.appendChild(btnBaixar);

            li.appendChild(info);
            li.appendChild(acoes);
            listaEl.appendChild(li);
        });
    } catch (erro) {
        console.error('Erro ao listar transcrições:', erro);
        avisoListaEl.textContent = 'Erro ao carregar a lista.';
        avisoListaEl.hidden = false;
    }
}

// 7.2 Dispara o download de um arquivo de transcrição
function baixarTranscricao(nomeArquivo) {
    window.location.href = `/transcricoes/${encodeURIComponent(nomeArquivo)}`;
}

// 7.3 Converte um valor em bytes para um formato legível (KB/MB)
function formatarBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// --------------------------------------------------------------------------
// Fim sub-bloco 7.3 Converte um valor em bytes para um formato legível (KB/MB)
// --------------------------------------------------------------------------
// Fim bloco 7 HISTÓRICO DE TRANSCRIÇÕES (CONSULTA/BACKEND)
// ==========================================================================


/* ==========================================================================
   BLOCO 8 - REGISTRO DE EVENTOS E INICIALIZAÇÃO
   ========================================================================== */

// 8.1 Associa cada botão à sua função correspondente
btnGravar.addEventListener('click', iniciarGravacao);
btnParar.addEventListener('click', pararGravacao);
btnApagar.addEventListener('click', apagarAudio);
btnTranscrever.addEventListener('click', transcreverAudio);
btnCopiar.addEventListener('click', copiarTexto);
btnSalvar.addEventListener('click', salvarTranscricao);
btnAtualizar.addEventListener('click', listarTranscricoes);
inputArquivo.addEventListener('change', selecionarArquivoAudio);

// 8.2 Ao carregar a página, inicia a interface no estado correto
document.addEventListener('DOMContentLoaded', () => {
    atualizarBotoes();
    listarTranscricoes();
});

// --------------------------------------------------------------------------
// Fim sub-bloco 8.2 Ao carregar a página, inicia a interface no estado correto
// --------------------------------------------------------------------------
// Fim bloco 8 REGISTRO DE EVENTOS E INICIALIZAÇÃO
// ==========================================================================


/* ==========================================================================
   ÍNDICE
   ==========================================================================
   1 SELEÇÃO DE ELEMENTOS DO DOM
     1.1 Referências aos elementos da interface
   2 VARIÁVEIS DE ESTADO DA APLICAÇÃO
     2.1 Estado da gravação
     2.2 Estado da transcrição (agora feita por IA no servidor)
     2.3 Guarda o texto final transcrito
   3 FUNÇÕES AUXILIARES DE INTERFACE
     3.1 Exibe uma mensagem de sucesso ou erro na tela
     3.2 Define o texto e a classe de cor do status do gravador
     3.3 Formata os segundos no padrão MM:SS
     3.4 Atualiza os botões conforme o estado da aplicação
     3.5 Limpa o resultado da transcrição atual
   4 FUNÇÕES DE GRAVAÇÃO DE ÁUDIO
     4.1 Função assíncrona que inicia a gravação do microfone
     4.2 Para a gravação em andamento
     4.3 Apaga o áudio gravado atual
     4.4 Usa um arquivo de áudio escolhido pelo usuário (upload do dispositivo)
   5 FUNÇÕES DE TRANSCRIÇÃO (IA NO SERVIDOR - WHISPER)
     5.1 Envia o áudio gravado para o servidor transcrever com a IA Whisper
   6 AÇÕES DE TEXTO (COPIAR E SALVAR NO SERVIDOR)
     6.1 Copia o texto transcrito para a área de transferência
     6.2 Envia o texto para o servidor salvar como arquivo .txt
   7 HISTÓRICO DE TRANSCRIÇÕES (CONSULTA/BACKEND)
     7.1 Busca a lista de transcrições salvas no servidor
     7.2 Dispara o download de um arquivo de transcrição
     7.3 Converte um valor em bytes para um formato legível (KB/MB)
   8 REGISTRO DE EVENTOS E INICIALIZAÇÃO
     8.1 Associa cada botão à sua função correspondente
     8.2 Ao carregar a página, inicia a interface no estado correto
   ========================================================================== */
