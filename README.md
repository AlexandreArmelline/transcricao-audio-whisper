# 🎙️ Sistema Web de Gravação e Transcrição de Áudio (Whisper IA)

Sistema web que **grava áudio pelo microfone** (desktop ou celular) e **transcreve automaticamente**
com a **IA Whisper** (OpenAI) rodando **no próprio servidor** — sem depender do navegador, sem limite
de duração e com alta precisão.

![Fluxo](https://img.shields.io/badge/Flask-3.x-000000) ![IA](https://img.shields.io/badge/Whisper-faster--whisper-10b981)

---

## ✨ Funcionalidades

- 🎤 **Gravação pelo microfone** direto no navegador (desktop e celular);
- 📂 **Upload de arquivo de áudio** já existente (MP3, WAV, M4A, OGG, WEBM, OPUS, AAC);
- 🧠 **Transcrição com IA Whisper** no servidor — analisa o áudio **completo**, sem cortes;
- 🌐 Suporte a **6 idiomas** (PT-BR, EN, ES, FR, DE, IT);
- 📝 **Copiar** o texto, **salvar** como `.txt` e **baixar** transcrições salvas;
- 📱 Interface **responsiva** (funciona bem em celulares);
- ⚙️ **Escolha automática do modelo** conforme a RAM do servidor (de `tiny` até o `large-v3`).

---

## 🧠 Qual modelo Whisper será usado?

O sistema **mede a memória RAM disponível** e escolhe o **mais preciso que couber**:

| RAM livre no servidor | Modelo | Precisão |
|---|---|---|
| ≥ 12 GB | `large-v3` | ⭐⭐⭐⭐⭐ Máxima (OpenAI) |
| ≥ 7 GB  | `medium` | ⭐⭐⭐⭐ Alta |
| ≥ 3 GB  | `small`  | ⭐⭐⭐ Boa |
| ≥ 2 GB  | `base`   | ⭐⭐ Média |
| < 2 GB  | `tiny`   | ⭐ Rápida |

> 💡 **Para máxima precisão** use um servidor com **pelo menos 12 GB de RAM**
> (ex.: Render/Cloud Run com 16 GB) — aí o `large-v3` é ativado automaticamente.
> Também é possível **fixar** um modelo com a variável `WHISPER_MODEL`:
> `WHISPER_MODEL=large-v3`, `medium`, `small` etc.

---

## 📁 Estrutura

```
├── backend/
│   ├── app.py                  → Aplicação Flask (rotas + IA Whisper)
│   ├── requirements.txt        → Dependências Python
│   ├── pre_download_modelo.py  → Baixa o modelo no build (evita demora na 1ª transcrição)
│   ├── templates/index.html    → Página principal
│   ├── static/                 → CSS e JavaScript
│   ├── uploads/                → Áudios enviados (gerado em runtime)
│   └── models/                 → Cache do modelo Whisper (gerado, persistente)
├── transcricoes/               → Transcrições .txt salvas (gerado em runtime)
├── Procfile                    → Comando de start (Render/Railway/Fly)
├── runtime.txt                 → Versão do Python
├── requirements.txt            → (raiz) aponta para o backend, se necessário
└── README.md
```

> ⚠️ As pastas `backend/uploads/`, `backend/models/` e `transcricoes/` são **geradas em runtime**
> e estão no `.gitignore`. Se quiser manter o histórico de transcrições entre deploys, configure
> um **volume persistente** apontando para elas (ver variáveis abaixo).

---

## 🚀 Deploy — passo a passo (Render / Railway / Fly.io / qualquer PaaS Linux)

### 1. Envie o código para o GitHub

```bash
git init
git add .
git commit -m "Sistema de transcrição de áudio pronto para deploy"
git remote add origin https://github.com/SEU_USUARIO/transcricao-audio.git
git push -u origin main
```

### 2. Crie o serviço na plataforma (exemplos)

#### 🟢 Render (recomendado — simples)
1. **New → Web Service** → conecte o repositório;
2. **Runtime:** `Python 3`; **Build Command:** `pip install -r backend/requirements.txt && python backend/pre_download_modelo.py`; **Start Command:** `gunicorn --chdir backend -w 1 --timeout 600 -b 0.0.0.0:$PORT app:app`;
3. **Instance Type:** escolha com **RAM suficiente** para o modelo desejado (tabela acima). Mínimo recomendado: **8 GB** (`small`/`medium`); ideal: **16 GB** (`large-v3`);
4. Deploy! 🎉

> ⚠️ O `pre_download_modelo.py` no build baixa o modelo uma única vez. Em plataformas com disco
> efêmero (Render Free/Starter reinicia o disco), a 1ª transcrição de cada ciclo pode demorar
> enquanto baixa o modelo de novo. Para evitar isso, use um **disco persistente** (Render: *Disks*)
> montado em `backend/models`.

#### 🟠 Railway
1. **New Project → Deploy from GitHub repo**;
2. Adicione as variáveis de ambiente (tabela abaixo);
3. **Build:** `pip install -r backend/requirements.txt && python backend/pre_download_modelo.py`
4. **Start:** `gunicorn --chdir backend -w 1 --timeout 600 -b 0.0.0.0:$PORT app:app`

#### 🔵 Fly.io
```bash
fly launch
fly scale memory 8192   # ou 16384 para large-v3
fly deploy
```
Adicione um volume para `backend/models` e `transcricoes` se quiser persistência.

---

## ⚙️ Variáveis de ambiente (todas opcionais)

| Variável | Padrão | Descrição |
|---|---|---|
| `WHISPER_MODEL` | `auto` | Fixa o modelo: `tiny`, `base`, `small`, `medium`, `large-v3` ou `auto` |
| `WHISPER_COMPUTE_TYPE` | auto | `int8_float32` (leve) ou `float32` (máxima precisão) |
| `PASTA_UPLOADS` | `backend/uploads` | Onde ficam os áudios enviados |
| `PASTA_TRANSCRICOES` | `transcricoes` | Onde ficam os `.txt` salvos |
| `PASTA_MODELOS` | `backend/models` | Cache do modelo Whisper (persistente) |
| `PORT` | `5000` | Porta (a plataforma costuma definir sozinha) |
| `FLASK_DEBUG` | `0` | `1` apenas em desenvolvimento |

---

## 💻 Rodando localmente (testes)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                     # http://127.0.0.1:5000
```

> No Windows, o gunicorn não funciona — use `python app.py` (Flask dev server) para testes locais.

---

## 🔒 Segurança (considerações de produção)

- As rotas de upload aceitam apenas extensões de áudio (webm, ogg, mp3, wav, m4a, mp4, opus, aac);
- `send_from_directory` protege contra travessia de diretório no download;
- **Recomendado:** colocar atrás de HTTPS (a maioria das plataformas já fornece) — o acesso ao
  microfone via `getUserMedia` **exige HTTPS** (ou localhost) no navegador;
- Em produção com múltiplos usuários, considere autenticação (a transcrição usa CPU intensiva;
  `-w 1` limita a 1 transcrição por vez para não derrubar o servidor).

---

## 📄 Licença

Projeto de uso livre para estudo e implantação. IA Whisper é da OpenAI (licença MIT para os modelos).
