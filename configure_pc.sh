#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  ⚡ Intel Arc GPU & vLLM Manager - PC Setup Wizard"
echo "=========================================================="
echo ""

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
MODELS_DIR="$HOME/my_models"
mkdir -p "$MODELS_DIR"

# ---------------------------------------------------------
# Step 1: Check and Install Podman if missing
# ---------------------------------------------------------
echo "🔍 [1/4] Verifica installazione Podman..."
if command -v podman >/dev/null 2>&1; then
    PODMAN_VER="$(podman --version)"
    echo "  ✅ Podman è già installato: $PODMAN_VER"
else
    echo "  ⚠️ Podman non è installato sul sistema."
    read -p "  Vuoi installare Podman adesso usando sudo? [Y/n]: " INSTALL_PODMAN
    INSTALL_PODMAN=${INSTALL_PODMAN:-Y}

    if [[ "$INSTALL_PODMAN" =~ ^[Yy]$ ]]; then
        echo "  📦 Installazione di Podman in corso..."
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update -qq
            sudo apt-get install -y podman
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y podman
        elif command -v pacman >/dev/null 2>&1; then
            sudo pacman -S --noconfirm podman
        else
            echo "  ❌ Impossibile identificare il gestore di pacchetti. Per favore installa Podman manualmente."
            exit 1
        fi
        echo "  ✅ Podman installato con successo!"
    else
        echo "  ⚠️ Installazione Podman ignorata. L'applicazione richiede Podman per eseguire vLLM."
    fi
fi

# ---------------------------------------------------------
# Step 2: Check Intel GPU DRM permissions & User Groups
# ---------------------------------------------------------
echo ""
echo "🔍 [2/4] Verifica permessi hardware GPU Intel..."
if ls /dev/dri/renderD* >/dev/null 2>&1; then
    echo "  ✅ Dispositivo GPU Intel rilevato in /dev/dri."
else
    echo "  ⚠️ Attenzione: Nessun nodo /dev/dri/renderD* trovato. Assicurati che i driver Intel siano attivi."
fi

# Ensure user belongs to video and render groups
CURRENT_USER="$USER"
if ! groups "$CURRENT_USER" | grep -q "render"; then
    echo "  ➕ Aggiunta utente '$CURRENT_USER' al gruppo 'render' per l'accesso diretto alla GPU..."
    sudo usermod -aG render "$CURRENT_USER" || true
fi
if ! groups "$CURRENT_USER" | grep -q "video"; then
    sudo usermod -aG video "$CURRENT_USER" || true
fi

# ---------------------------------------------------------
# Step 3: Run Project Setup & Systemd Service Autostart
# ---------------------------------------------------------
echo ""
echo "⚙️ [3/4] Configurazione ambiente Python e Servizio Autostart Systemd..."
bash "$PROJECT_DIR/install.sh"

# ---------------------------------------------------------
# Step 4: Interactive Hugging Face Model Downloader
# ---------------------------------------------------------
echo ""
echo "🤗 [4/4] Download Modelli LLM da Hugging Face"
echo "I modelli verranno salvati in: $MODELS_DIR"
echo ""
echo "Seleziona un modello consigliato da scaricare o inserisci un Repo ID custom:"
echo "  1) Qwen2.5-Coder-14B-Instruct-AWQ (Codice - Qwen/Qwen2.5-Coder-14B-Instruct-AWQ)"
echo "  2) Qwen2.5-14B-Instruct-AWQ       (Generale - Qwen/Qwen2.5-14B-Instruct-AWQ)"
echo "  3) Gemma-2-9B-IT-AWQ              (Google - casperhansen/gemma-2-9b-it-awq)"
echo "  4) Qwen2.5-7B-Instruct            (Generale 7B - Qwen/Qwen2.5-7B-Instruct)"
echo "  5) Inserisci Repo ID personalizzato Hugging Face"
echo "  6) Salta il download dei modelli (Ho già i miei modelli in ~/my_models)"
echo ""
read -p "Scelta [1-6]: " CHOICE

case "$CHOICE" in
    1)
        REPO_ID="Qwen/Qwen2.5-Coder-14B-Instruct-AWQ"
        FOLDER_NAME="Qwen2.5-Coder-14B-AWQ"
        ;;
    2)
        REPO_ID="Qwen/Qwen2.5-14B-Instruct-AWQ"
        FOLDER_NAME="Qwen2.5-14B-AWQ"
        ;;
    3)
        REPO_ID="casperhansen/gemma-2-9b-it-awq"
        FOLDER_NAME="Gemma-2-9B-AWQ"
        ;;
    4)
        REPO_ID="Qwen/Qwen2.5-7B-Instruct"
        FOLDER_NAME="Qwen2.5-7B"
        ;;
    5)
        echo ""
        read -p "Inserisci il repo ID di Hugging Face (es. Qwen/Qwen2.5-7B-Instruct): " REPO_ID
        if [ -z "$REPO_ID" ]; then
            echo "❌ Repo ID non valido. Download saltato."
            REPO_ID=""
        fi
        read -p "Inserisci il nome della cartella di destinazione (invio per '$(basename "$REPO_ID")'): " FOLDER_NAME
        if [ -z "$FOLDER_NAME" ]; then
            FOLDER_NAME="$(basename "$REPO_ID")"
        fi
        ;;
    *)
        echo "ℹ️ Download modelli saltato."
        REPO_ID=""
        ;;
esac

if [ -n "$REPO_ID" ]; then
    DEST_PATH="$MODELS_DIR/$FOLDER_NAME"
    echo ""
    echo "📂 Destinazione salvataggio: $DEST_PATH"
    echo "⬇️ Avvio download di '$REPO_ID' tramite Podman..."
    echo ""

    podman run --rm -it \
      -v "$MODELS_DIR":/download \
      docker.io/library/python:3.11-slim \
      bash -c "pip install --no-cache-dir huggingface_hub && hf download '$REPO_ID' --local-dir '/download/$FOLDER_NAME'"

    echo ""
    echo "✅ Download completato: $DEST_PATH"
fi

echo ""
echo "=========================================================="
echo "🎉 CONFIGURAZIONE SISTEMA COMPLETATA CON SUCCESSO!"
echo "=========================================================="
echo "🌐 Dashboard Web UI attiva su: http://localhost:5000"
echo "🤖 vLLM OpenAI API URL:       http://localhost:8000/v1"
echo "=========================================================="
