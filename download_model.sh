#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  🤗 Hugging Face Model Downloader for ~/my_models"
echo "=========================================================="

MODELS_DIR="$HOME/my_models"
mkdir -p "$MODELS_DIR"

if [ -z "$1" ]; then
    echo "Uso: $0 <huggingface_repo_id> [nome_cartella_destinazione]"
    echo ""
    echo "Esempi:"
    echo "  $0 Qwen/Qwen2.5-Coder-14B-Instruct-AWQ Qwen2.5-Coder-14B-AWQ"
    echo "  $0 casperhansen/gemma-2-9b-it-awq Gemma-2-9B-AWQ"
    echo "  $0 Qwen/Qwen2.5-7B-Instruct Qwen2.5-7B"
    echo ""
    read -p "Inserisci il repo ID di Hugging Face (es. Qwen/Qwen2.5-Coder-14B-Instruct-AWQ): " REPO_ID
    if [ -z "$REPO_ID" ]; then
        echo "❌ Repo ID non valido. Operazione annullata."
        exit 1
    fi
else
    REPO_ID="$1"
fi

if [ -n "$2" ]; then
    FOLDER_NAME="$2"
else
    # Extract basename from repo id
    FOLDER_NAME="$(basename "$REPO_ID")"
fi

DEST_PATH="$MODELS_DIR/$FOLDER_NAME"

echo "📂 Target destination: $DEST_PATH"
echo "⬇️ Downloading model '$REPO_ID' via Podman..."
echo ""

podman run --rm -it \
  -v "$MODELS_DIR":/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir huggingface_hub && hf download '$REPO_ID' --local-dir '/download/$FOLDER_NAME'"

echo ""
echo "=========================================================="
echo "✅ DOWNLOAD COMPLETATO!"
echo " Modello salvato in: $DEST_PATH"
echo " Apri http://localhost:5000 per avviare il modello."
echo "=========================================================="
