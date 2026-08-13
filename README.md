# ⚡ vLLM Intel GPU Manager (Podman & Systemd)

**vLLM Intel GPU Manager** è un'applicazione Web reattiva e completamente automatizzata per eseguire e gestire Modelli Linguistici (LLM) tramite **vLLM** accelerato da **GPU Intel** (discrete ed integrate) su Linux.

L'applicazione trasforma il tuo computer in un server di inferenza locale compatibile con le **API OpenAI**, fornendo una Dashboard Web ed un servizio di background **Systemd** che si avvia automaticamente all'accensione del PC.

---

## 📌 CONFIGURAZIONE IN UN SOLO COMANDO (`configure_pc.sh`)

Per rendere l'installazione accessibile a chiunque, abbiamo creato lo wizard interattivo **`./configure_pc.sh`**.

Lo script compie automaticamente **tutti** i passaggi necessari:
1. **Rileva ed installa Podman**: Se Podman non è installato, lo scarica ed installa automaticamente tramite il gestore di pacchetti di sistema (`apt`, `dnf`, `pacman`).
2. **Configura i permessi hardware GPU Intel**: Aggiunge l'utente ai gruppi `render` e `video` per garantire l'accesso diretto alla scheda video.
3. **Prepara l'ambiente Python & Autostart Systemd**: Configura il virtual environment e registra il servizio `vllm-dashboard.service` per far partire l'app in background ad ogni avvio del PC.
4. **Scarica i Modelli LLM da Hugging Face**: Offre un menu interattivo per scaricare direttamente i modelli pre-testati (es. `Qwen2.5-Coder-14B-AWQ`, `Qwen2.5-14B-AWQ`, `Gemma-2-9B-AWQ`) nella cartella `~/my_models`.

---

## 🚀 GUIDA COMPLETA DA ZERO

### 1. Clona la repository Git
```bash
git clone https://github.com/tuo-utente/vllm-intel-dashboard.git
cd vllm-intel-dashboard
```

### 2. Esegui la Configurazione Automatica (Una Tantum)
```bash
./configure_pc.sh
```

### 3. Apri la Dashboard nel Browser
Vai a: 👉 **[http://localhost:5000](http://localhost:5000)**

1. Se è il primo avvio ed il badge indica `Immagine non presente`, clicca su **`📥 Scarica Immagine vLLM`**.
2. Seleziona il modello dal menu a tendina e clicca **`▶️ Avvia / Switch Modello`**.
3. Interroga l'LLM con la **Test Chat integrata** o collega i tuoi client (Open WebUI, Jan, Continue) su **`http://localhost:8000/v1`**.

---

## 📥 SCARICARE ALTRI MODELLI DA HUGGING FACE

Puoi anche eseguire lo script in qualsiasi momento per scaricare nuovi modelli:

```bash
# Esecuzione interattiva
./download_model.sh

# Oppure da linea di comando:
./download_model.sh Qwen/Qwen2.5-14B-Instruct-AWQ Qwen2.5-14B-AWQ
```

---

## 🌟 Caratteristiche Principali della Dashboard

* **🎮 Supporto Universale GPU Intel**: Compatibile con Intel Arc B-Series (B580/B570), Arc A-Series (A770/A750/A380), Intel Core Ultra e Data Center GPU.
* **📊 Telemetria VRAM Live**: Monitoraggio in tempo reale del consumo VRAM della scheda Intel Arc via WebSocket.
* **🔄 Hot-Switch Modelli**: Sostituisci il modello caricato in memoria con un clic senza riavviare il PC.
* **💬 Test Chat OpenAI-Compatible**: Prova l'inferenza dell'LLM direttamente nella dashboard.
* **📜 Live Log Streamer**: Visualizza i log di vLLM (`podman logs -f`) in tempo reale con evidenziazione errori.

---

## 🛠️ Comandi di Gestione Systemd

```bash
# Verificare lo stato del servizio
systemctl --user status vllm-dashboard.service

# Riavviare la dashboard
systemctl --user restart vllm-dashboard.service

# Leggere i log di sistema
journalctl --user -u vllm-dashboard.service -f
```
