# ⚡ vLLM Intel GPU Manager (Podman & Systemd)

**vLLM Intel GPU Manager** è un'applicazione Web reattiva *"chiavi in mano"* per eseguire e gestire Modelli Linguistici (LLM) tramite **vLLM** accelerato da **GPU Intel** (discrete ed integrate) su Linux.

L'applicazione trasforma il tuo computer in un server di inferenza locale compatibile con le **API OpenAI**, fornendo una Dashboard Web ed un servizio di background **Systemd** che si avvia automaticamente all'accensione del PC.

---

## 📌 COSA SERVE PER FAR FUNZIONARE IL PROGETTO? (Requisiti)

Chiunque scarichi questo progetto da Git ha bisogno soltanto di 3 cose:

1. **Hardware**: Un PC Linux con una **GPU Intel** (Arc B580, B570, A770, A750, A380 o grafica integrata Intel Core Ultra / Iris Xe).
2. **Podman** (o Docker): Installato sul sistema (`sudo apt install podman`).
3. **Almeno un Modello LLM**: Salvato nella cartella `~/my_models` della tua Home.

---

## 📥 COME SCARICARE I MODELLI DA HUGGING FACE IN `~/my_models`

I modelli di Intelligenza Artificiale devono essere salvati dentro la cartella `~/my_models`. 
Puoi scaricarli facilmente in **due modi**:

### Metodo A: Usando lo script interattivo del progetto (CONSIGLIATO)
Esegui semplicemente lo script `./download_model.sh`:

```bash
./download_model.sh
```

Lo script mostrerà un menu interattivo con i modelli verificati per Intel Arc B580 / 16GB VRAM:
1. `Qwen2.5-Coder-14B-Instruct-AWQ` (Specializzato in Codice)
2. `Qwen2.5-14B-Instruct-AWQ` (Generale 14B)
3. `gemma-2-9b-it-awq` (Google Gemma 2 9B)
4. `Qwen2.5-7B-Instruct` (Generale 7B)
5. *Oppure inserire un Repo ID personalizzato*.

In alternativa puoi passare direttamente i parametri da linea di comando:
```bash
./download_model.sh Qwen/Qwen2.5-14B-Instruct-AWQ Qwen2.5-14B-AWQ
```

### Metodo B: Usando direttamente il comando Podman
```bash
# Download Qwen2.5-Coder-14B-AWQ
podman run --rm -it \
  -v ~/my_models:/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir huggingface_hub && hf download Qwen/Qwen2.5-Coder-14B-Instruct-AWQ --local-dir /download/Qwen2.5-Coder-14B-AWQ"

# Download Qwen2.5-14B-AWQ
podman run --rm -it \
  -v ~/my_models:/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir huggingface_hub && hf download Qwen/Qwen2.5-14B-Instruct-AWQ --local-dir /download/Qwen2.5-14B-AWQ"
```

---

## 🚀 GUIDA COMPLETA DA ZERO (Passo per Passo)

### 1. Clona la repository Git
```bash
git clone https://github.com/tuo-utente/vllm-intel-dashboard.git
cd vllm-intel-dashboard
```

### 2. Esegui l'Installatore (Una Tantum)
```bash
./install.sh
```
> **Cosa fa?** Crea l'ambiente virtuale Python `venv/`, installa le librerie e configura il servizio **Systemd** (`vllm-dashboard.service`). Da questo momento in poi, la Dashboard **si avvierà automaticamente ad ogni accensione del PC**.

### 3. Scarica un Modello LLM
```bash
./download_model.sh
```

### 4. Apri la Dashboard nel Browser
Vai a: 👉 **[http://localhost:5000](http://localhost:5000)**

1. Se è il primo avvio ed il badge indica `Immagine non presente`, clicca su **`📥 Scarica Immagine vLLM`**.
2. Seleziona il modello dal menu a tendina e clicca **`▶️ Avvia / Switch Modello`**.
3. Interroga l'LLM con la **Test Chat integrata** o collega i tuoi client (Open WebUI, Jan, Continue) su **`http://localhost:8000/v1`**.

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
