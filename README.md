# ⚡ vLLM Intel Arc Server & Manager (`vllm-intel-arc-dashboard`)

**vLLM Intel Arc Server & Manager** è un'applicazione Web e Server API reattivo per eseguire e gestire Modelli Linguistici (LLM) tramite **vLLM** accelerato da **GPU Intel Arc** (B-Series B580/B570, A-Series A770/A750, Intel Core Ultra e Data Center GPU) su Linux.

L'applicazione trasforma il tuo PC in un server di inferenza locale compatibile sia con le **API OpenAI** (`/v1/...`) sia con le **API Ollama** (`/api/...`), accessibile da **qualsiasi dispositivo sulla tua rete LAN o via Tailscale** sulla porta **`5000`**.

Include una Dashboard Web reattiva ed un servizio di background **Systemd** che si avvia automaticamente all'avvio del computer.

---

## 🗺️ ARCHITETTURA DELLE PORTE

| Porta | Servizio | Descrizione |
|---|---|---|
| **`5000`** | **vLLM Dashboard & API Server** (`app/main.py`) | **Porta principale del progetto.** Web UI, API OpenAI (`/v1/...`), API Ollama (`/api/...`) e WebSockets. |
| **`8000`** | **Container vLLM Intel Arc** (`podman`) | Usata internamente dal container vLLM (il backend fa da proxy e gestisce l'auto-loading). |
| **`3000`** | **Open WebUI** *(Opzionale)* | Porta predefinita se installi Open WebUI come interfaccia chat client esterna. |

---

## 🔥 CARATTERISTICHE PRINCIPALI

* **🤖 API Proxy "Stile Ollama" & OpenAI Compatibile (`:5000`)**: Espone endpoint universali `/v1/chat/completions`, `/v1/models`, `/api/tags`, `/api/ps` utilizzabili da qualsiasi applicazione AI (Open WebUI, Continue.dev, Cursor, Jan, LM Studio, Obsidian).
* **⚡ Auto-Loading & Auto-Switch dei Modelli**: Se un client richiede un modello presente in `~/my_models`, il server arresta il vecchio container e avvia automaticamente il nuovo modello in VRAM.
* **🌍 Accesso da Rete Locale & Tailscale**: In ascolto su `0.0.0.0:5000` con CORS Smart per LAN e subnet Tailscale (`100.0.0.0/8`).
* **📊 Telemetria VRAM Live**: Monitoraggio in tempo reale del consumo VRAM della GPU Intel Arc tramite driver `xe` (/proc/fdinfo) via WebSocket.
* **📜 Live Log Streamer**: Streaming in tempo reale dei log del container vLLM (`podman logs -f`) e degli eventi di sistema.
* **🛡️ Protezione e Validazione**: Sanitizzazione input (anti path-traversal e whitelist flag vLLM) e protezione opzionale con API Key per operazioni amministrative.
* **🏥 Health Check (`GET /health`)**: Endpoint di monitoraggio per verificare salute di vLLM Server, Podman e Filesystem.
* **📦 Utility di Backup/Restore**: Script bash per archiviare e ripristinare i modelli in un click.

---

## 📌 CONFIGURAZIONE IN UN SOLO COMANDO (`configure_pc.sh`)

Per configurare tutto il sistema da zero, basta eseguire lo wizard interattivo:

```bash
./configure_pc.sh
```

Lo script compie automaticamente **tutti** i passaggi necessari:
1. **Rileva ed installa Podman**: Scarica ed installa Podman tramite il gestore di pacchetti (`apt`, `dnf`, `pacman`).
2. **Configura i permessi hardware GPU Intel**: Aggiunge l'utente ai gruppi `render` e `video` per garantire l'accesso diretto alla scheda video.
3. **Prepara l'ambiente Python & Autostart Systemd**: Configura il virtual environment e registra il servizio `vllm-dashboard.service` per far partire l'app in background ad ogni avvio del PC.
4. **Scarica i Modelli LLM**: Menu interattivo per scaricare direttamente i modelli pre-testati ed ottimizzati per 16GB VRAM in `~/my_models`.

---

## ⚙️ CONFIGURAZIONE DEL SERVER

Il sistema supporta una gerarchia di configurazione a tre livelli: **Default → File YAML (`vllm-dashboard.yaml`) → Variabili d'Ambiente (`.env`)**.

### 1. Configurazione via YAML (`vllm-dashboard.yaml`)
Copia il template di esempio ed inserisci le tue preferenze:
```bash
cp vllm-dashboard.yaml.example vllm-dashboard.yaml
```

Esempio `vllm-dashboard.yaml`:
```yaml
server:
  host: 0.0.0.0
  port: 5000
  log_level: INFO

gpu:
  memory_utilization: 0.70
  dtype: float16
  max_model_len: 2048

podman:
  container_name: vllm-intel-arc
  image_name: docker.io/intel/vllm:0.17.0-xpu
  image_pull_timeout: 600
  container_start_timeout: 120

model:
  models_dir: ~/my_models

security:
  api_key: ""
  enable_cors: true
```

### 2. Configurazione via `.env`
```bash
cp .env.example .env
```

Parametri principali in `.env`:
```bash
API_KEY=                         # Opzionale: imposta una chiave per proteggere start/stop/pull
SERVER_HOST=0.0.0.0
SERVER_PORT=5000
MODELS_DIR=~/my_models
GPU_MEMORY_UTILIZATION=0.70
DEFAULT_DTYPE=float16
MAX_MODEL_LEN=2048
IMAGE_PULL_TIMEOUT=600
CONTAINER_START_TIMEOUT=120
```

---

## 🌐 INTEGRAZIONE CON I CLIENT (LAN & TAILSCALE)

Il server risponde a tutte le richieste di inferenza sulla porta **`5000`** (l'inferenza non richiede API Key sulla rete locale).

* **Indirizzo LAN Locale:** `http://192.168.X.X:5000/v1`
* **Indirizzo Tailscale (VPN):** `http://100.X.X.X:5000/v1`

### 1. Open WebUI (Interfaccia Web Chat)
1. Apri le impostazioni di Open WebUI (`http://localhost:3000` o remoto).
2. Vai su **Settings → Connections / Models → OpenAI API**.
3. Inserisci:
   - **URL:** `http://<IP-DEL-SERVER>:5000/v1`
   - **API Key:** `vllm` (o qualsiasi stringa, non verificata per inferenza)
4. I modelli presenti in `~/my_models` appariranno automaticamente nella lista dei modelli!

### 2. Continue.dev (VS Code / JetBrains Extension)
Nel tuo file `~/.continue/config.json`:
```json
{
  "models": [
    {
      "title": "Qwen 2.5 Coder Intel Arc",
      "provider": "openai",
      "model": "Qwen2.5-Coder-7B-Instruct-AWQ",
      "apiBase": "http://192.168.X.X:5000/v1",
      "apiKey": "none"
    }
  ]
}
```

### 3. Cursor IDE
1. Vai su **Cursor Settings → Models → OpenAI API Key**.
2. Abilita **Override OpenAI Base URL**.
3. Inserisci: `http://192.168.X.X:5000/v1`
4. Aggiungi il nome esatto del modello (es. `Qwen2.5-Coder-7B-Instruct-AWQ`).

### 4. Script Python (`openai` SDK)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://192.168.X.X:5000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="Qwen2.5-Coder-7B-Instruct-AWQ",
    messages=[{"role": "user", "content": "Ciao! Chi sei?"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
print()
```

### 5. Chiamata diretta con `curl` (Streaming SSE)
```bash
curl http://192.168.X.X:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen2.5-Coder-7B-Instruct-AWQ",
    "messages": [{"role": "user", "content": "Scrivi una funzione Python per calcolare il fattoriale."}],
    "stream": true
  }'
```

---

## 📥 MODELLI CONSIGLIATI E COMANDI DI DOWNLOAD

I seguenti modelli AWQ sono stati testati e verificati per funzionare in modo ottimale su **Intel Arc B580 (16GB VRAM)**:

### 1️⃣ Qwen2.5-Coder-7B-Instruct-AWQ (Coding & Programmazione)
```bash
podman run --rm -it \
  -v ~/my_models:/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir huggingface_hub && hf download Qwen/Qwen2.5-Coder-7B-Instruct-AWQ --local-dir /download/Qwen2.5-Coder-7B-Instruct-AWQ"
```

### 2️⃣ Qwen2.5-7B-Instruct-AWQ (Chat Generale, Italiano e Scrittura)
```bash
podman run --rm -it \
  -v ~/my_models:/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir huggingface_hub && hf download Qwen/Qwen2.5-7B-Instruct-AWQ --local-dir /download/Qwen2.5-7B-Instruct-AWQ"
```

### 3️⃣ DeepSeek-R1-Distill-Qwen-7B-AWQ (Reasoning Avanzato e Matematica)
```bash
podman run --rm -it \
  -v ~/my_models:/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir huggingface_hub && hf download casperhansen/deepseek-r1-distill-qwen-7b-awq --local-dir /download/DeepSeek-R1-Distill-Qwen-7B-AWQ"
```

### 4️⃣ Llama-3-8B-Instruct-AWQ (Meta Llama 3)
```bash
podman run --rm -it \
  -v ~/my_models:/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir huggingface_hub && hf download casperhansen/llama-3-8b-instruct-awq --local-dir /download/Llama-3-8B-Instruct-AWQ"
```

---

## 📦 UTILITY DI BACKUP E RIPRISTINO

Il progetto include due script nella cartella `scripts/`:

```bash
# Esegue il backup compresso (.tar.gz) di ~/my_models in ~/.vllm-dashboard/backups/
./scripts/backup_models.sh

# Mostra il menu interattivo per ripristinare un backup esistente
./scripts/restore_models.sh
```

---

## 🧪 ESECUZIONE DEI TEST AUTOMATICI

Il progetto dispone di una suite di test unitari con `pytest`:

```bash
./venv/bin/pytest tests/ -v
```

Include verifiche per:
* **Validazione input e sanitizzazione flag vLLM** (`tests/test_validators.py`)
* **Gerarchia di configurazione e variabili d'ambiente** (`tests/test_config.py`)
* **Calcolo VRAM GPU Intel Arc e telemetria host** (`tests/test_gpu_mon.py`)

---

## 🛠️ COMANDI DI GESTIONE SYSTEMD

```bash
# Verificare lo stato del servizio
systemctl --user status vllm-dashboard.service

# Riavviare la dashboard / server API
systemctl --user restart vllm-dashboard.service

# Visualizzare i log di sistema in tempo reale
journalctl --user -u vllm-dashboard.service -f
```
