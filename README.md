# ⚡ vLLM Intel Arc Server & Manager (`vllm-intel-arc-dashboard`)

**vLLM Intel Arc Server & Manager** è un'applicazione Web e Server API reattivo per eseguire e gestire Modelli Linguistici (LLM) tramite **vLLM** accelerato da **GPU Intel Arc** (B-Series B580/B570, A-Series A770/A750, Intel Core Ultra e Data Center GPU) su Linux.

L'applicazione trasforma il tuo PC in un server di inferenza locale compatibile sia con le **API OpenAI** (`/v1/...`) sia con le **API Ollama** (`/api/...`), accessibile da **qualsiasi dispositivo sulla tua rete LAN o via Tailscale** sulla porta **`5000`**.

Include una Dashboard Web reattiva ed un servizio di background **Systemd** che si avvia automaticamente all'avvio del computer.

---

## 🔥 CARATTERISTICHE PRINCIPALI

* **🤖 API Proxy "Stile Ollama" & OpenAI Compatibile (`:5000`)**: Espone endpoints universali `/v1/chat/completions`, `/v1/models`, `/api/tags`, `/api/ps` accessibili da qualsiasi client di rete.
* **⚡ Auto-Loading & Auto-Switch dei Modelli**: Proprio come Ollama, quando un client di rete (Open WebUI, Continue, Jan, Cursor) richiede un modello presente in `~/my_models`, il server lo carica o lo sostituisce automaticamente in VRAM!
* **🌍 Accesso da Rete Locale & Tailscale**: In ascolto su `0.0.0.0:5000` con CORS completamente abilitato.
* **📊 Telemetria VRAM Live**: Monitoraggio in tempo reale del consumo di VRAM della GPU Intel Arc tramite WebSocket.
* **📜 Live Log Streamer**: Visualizza i log di vLLM (`podman logs -f`) in tempo reale direttamente nel browser.

---

## 📌 CONFIGURAZIONE IN UN SOLO COMANDO (`configure_pc.sh`)

Per rendere l'installazione accessibile a chiunque, abbiamo creato lo wizard interattivo **`./configure_pc.sh`**.

Lo script compie automaticamente **tutti** i passaggi necessari:
1. **Rileva ed installa Podman**: Se Podman non è installato, lo scarica ed installa automaticamente tramite il gestore di pacchetti di sistema (`apt`, `dnf`, `pacman`).
2. **Configura i permessi hardware GPU Intel**: Aggiunge l'utente ai gruppi `render` e `video` per garantire l'accesso diretto alla scheda video.
3. **Prepara l'ambiente Python & Autostart Systemd**: Configura il virtual environment e registra il servizio `vllm-dashboard.service` per far partire l'app in background ad ogni avvio del PC.
4. **Scarica i Modelli LLM da Hugging Face**: Offre un menu interattivo per scaricare direttamente i modelli pre-testati ed ottimizzati per 16GB VRAM (es. `Qwen2.5-Coder-7B-Instruct-AWQ`, `Qwen2.5-7B-Instruct-AWQ`, `DeepSeek-R1-Distill-Qwen-7B-AWQ`) nella cartella `~/my_models`.

---

## 🚀 GUIDA COMPLETA DA ZERO

### 1. Clona la repository Git
```bash
git clone https://github.com/tuo-utente/vllm-intel-arc-dashboard.git
cd vllm-intel-arc-dashboard
```

### 2. Esegui la Configurazione Automatica (Una Tantum)
```bash
./configure_pc.sh
```

### 3. Apri la Dashboard nel Browser
Vai a: 👉 **[http://localhost:5000](http://localhost:5000)**

1. Se è il primo avvio ed il badge indica `Immagine non presente`, clicca su **`📥 Scarica Immagine vLLM`**.
2. Seleziona il modello dal menu a tendina e clicca **`▶️ Avvia / Switch Modello`**.
3. Interroga l'LLM con la **Test Chat integrata** o collega i tuoi client su **`http://<IP-DEL-TUO-PC>:5000/v1`**.

---

## 🌐 UTILIZZO VIA RETE LOCALE & TAILSCALE

Puoi utilizzare l'API da qualsiasi dispositivo sulla rete locale LAN o da qualsiasi parte del mondo via **Tailscale**:

### Indirizzi di Connessione:
* **Da Rete LAN Locale:** `http://192.168.X.X:5000/v1`
* **Da Tailscale (VPN):** `http://100.X.X.X:5000/v1`

### Esempio di chiamata API (con Streaming SSE):
```bash
curl http://192.168.X.X:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen2.5-Coder-7B-Instruct-AWQ",
    "messages": [{"role": "user", "content": "Scrivi una funzione Python per invertire una lista."}],
    "stream": true
  }'
```

---

## 📥 MODELLI CONSIGLIATI E COMANDI DI DOWNLOAD

I seguenti modelli AWQ sono stati testati e verificati per funzionare in modo ottimale sulla scheda video **Intel Arc B580 (16GB VRAM)**:

### 1️⃣ Qwen2.5-Coder-7B-Instruct-AWQ (Programmazione e Codice)
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

### 3️⃣ DeepSeek-R1-Distill-Qwen-7B-AWQ (Reasoning Avanzato e Logica)
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

## 🛠️ Comandi di Gestione Systemd

```bash
# Verificare lo stato del servizio
systemctl --user status vllm-dashboard.service

# Riavviare la dashboard / server API
systemctl --user restart vllm-dashboard.service

# Leggere i log di sistema
journalctl --user -u vllm-dashboard.service -f
```
