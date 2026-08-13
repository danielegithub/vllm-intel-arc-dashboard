Piano di Implementazione per Antigravity
Obiettivo: Creare un'applicazione Web leggera (FastAPI + Tailwind/HTMX + WebSockets) in esecuzione continua come servizio di sistema. La dashboard permetterà di monitorare l'uso della GPU Intel Arc, leggere i log in tempo reale del container vLLM e fare lo switch caldo tra i modelli salvati in ~/my_models.

Architecture Overview
Backend: Python (FastAPI + Uvicorn) per la gestione di Podman e l'invio di metriche/log via WebSockets.

Frontend: Dashboard SPA reattiva (HTML5 + Tailwind CSS + WebSockets) senza framework pesanti.

System Integration: Executable podman CLI, lettura metriche GPU Intel da /sys/class/drm o intel_gpu_top -J, gestione del demone via systemd utente.

Componenti e Funzionalità da Sviluppare
1. Backend Service (main.py)
[ ] Model Scanner API: Scansione dinamica delle sottocartelle dentro ~/my_models per elencare i modelli disponibili.

[ ] Podman Lifecycle Manager:

Endpoint per verificare lo stato del container vllm-intel-arc (running, stopped, none).

Endpoint per avviare/fermare/riavviare un modello selezionato usando l'immagine intel/vllm:0.17.0-xpu con i flag hardware per Intel Arc (--device /dev/dri:/dev/dri, --device xpu, --net=host, ecc.).

[ ] Log Streamer (WebSocket /ws/logs): Stream live dei log del container agganciato a podman logs -f vllm-intel-arc.

[ ] GPU Metrics Streamer (WebSocket /ws/gpu): Stream di telemetria VRAM e carico della GPU Intel Arc (tramite parsing di intel_gpu_top -J -s 1000 o lettura diretta sysfs).

2. Frontend Web UI (templates/index.html)
[ ] Header Status Card: Mostra lo stato attuale del server vLLM, l'endpoint attivi (http://localhost:8000/v1) e il modello attualmente in carica sulla VRAM.

[ ] Model Selector Control: Dropdown/Radio list dei modelli trovati in ~/my_models con pulsante "Switch & Restart".

[ ] GPU & VRAM Realtime Meter: Widget grafico con barre di progresso in tempo reale per percentuale d'uso della GPU e consumo VRAM (MB/GB).

[ ] Embedded Terminal Log View: Finestra stile terminale (xterm.js o log box scrollabile) che mostra l'output live di vLLM e avvisa in caso di errori OOM o inizializzazione completata.

3. Autostart & Service Integration
[ ] Creazione di un file di servizio systemd utente (~/.config/systemd/user/vllm-dashboard.service) per mantenere il server Web sempre attivo in background al boot della macchina.

Struttura del Progetto da Generare
Plaintext
vllm-intel-dashboard/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI server & WebSocket handlers
│   ├── podman_cli.py    # Podman wrapper commands
│   ├── gpu_mon.py       # Intel Arc metrics parser
│   └── templates/
│       └── index.html   # Web UI Dashboard
├── requirements.txt     # fastapi, uvicorn, websockets, psutil
├── install.sh           # Setup venv & systemd unit
└── README.md

AGGIUNTA AL PIANO DI IMPLEMENTAZIONE:

Genera anche un file 'docker-compose.yaml' (compatibile con podman-compose) per gestire il container vLLM.

Struttura del docker-compose.yaml da generare:
----------------------------------------------
version: '3.8'
services:
  vllm-server:
    container_name: vllm-intel-arc
    image: docker.io/intel/vllm:0.17.0-xpu
    network_mode: "host"
    ipc: "host"
    devices:
      - "/dev/dri:/dev/dri"
    volumes:
      - "${HOME}/my_models:/models:ro"
    environment:
      - MODEL_PATH=${CURRENT_MODEL_PATH}
      - MODEL_ALIAS=${CURRENT_MODEL_ALIAS}
    command: >
      vllm serve /models/${CURRENT_MODEL_PATH}
        --served-model-name ${CURRENT_MODEL_ALIAS}
        --device xpu
        --max-model-len 4096
        --port 8000
    restart: unless-stopped
----------------------------------------------

La Dashboard (FastAPI o Node.js) quando l'utente seleziona un nuovo modello dalla Web UI dovrà:
1. Aggiornare le variabili d'ambiente CURRENT_MODEL_PATH e CURRENT_MODEL_ALIAS in un file '.env'.
2. Eseguire 'podman-compose down' per fermare il container e liberare la VRAM della B580.
3. Eseguire 'podman-compose up -d' per avviare il nuovo modello.