#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  🤗 Hugging Face Model Downloader for Intel Arc & vLLM"
echo "=========================================================="

MODELS_DIR="$HOME/my_models"
mkdir -p "$MODELS_DIR"

# Check if arguments were passed
if [ -n "$1" ]; then
    REPO_ID="$1"
    if [ -n "$2" ]; then
        FOLDER_NAME="$2"
    else
        FOLDER_NAME="$(basename "$REPO_ID")"
    fi
else
    # Interactive Menu
    echo "Seleziona uno dei modelli verificati ed ottimizzati per Intel Arc B580 (16GB VRAM):"
    echo ""
    echo "  1) Qwen2.5-Coder-7B-Instruct-AWQ        (Programmazione & Codice)"
    echo "  2) Qwen2.5-7B-Instruct-AWQ              (Chat Generale & Italiano)"
    echo "  3) DeepSeek-R1-Distill-Qwen-7B-AWQ      (Ragionamento Avanzato & Logica)"
    echo "  4) Llama-3-8B-Instruct-AWQ              (Meta Llama 3 8B)"
    echo "  5) Qwen2.5-3B-Instruct-AWQ              (Ultraveloce 3B)"
    echo "  6) Inserisci Repo ID personalizzato Hugging Face"
    echo ""
    read -p "Scelta [1-6]: " CHOICE

    case "$CHOICE" in
        1)
            REPO_ID="Qwen/Qwen2.5-Coder-7B-Instruct-AWQ"
            FOLDER_NAME="Qwen2.5-Coder-7B-Instruct-AWQ"
            ;;
        2)
            REPO_ID="Qwen/Qwen2.5-7B-Instruct-AWQ"
            FOLDER_NAME="Qwen2.5-7B-Instruct-AWQ"
            ;;
        3)
            REPO_ID="casperhansen/deepseek-r1-distill-qwen-7b-awq"
            FOLDER_NAME="DeepSeek-R1-Distill-Qwen-7B-AWQ"
            ;;
        4)
            REPO_ID="casperhansen/llama-3-8b-instruct-awq"
            FOLDER_NAME="Llama-3-8B-Instruct-AWQ"
            ;;
        5)
            REPO_ID="Qwen/Qwen2.5-3B-Instruct-AWQ"
            FOLDER_NAME="Qwen2.5-3B-Instruct-AWQ"
            ;;
        6)
            echo ""
            read -p "Inserisci il repo ID di Hugging Face (es. Qwen/Qwen2.5-7B-Instruct-AWQ): " REPO_ID
            if [ -z "$REPO_ID" ]; then
                echo "❌ Repo ID non valido. Operazione annullata."
                exit 1
            fi
            read -p "Inserisci il nome della cartella di destinazione (invio per '$(basename "$REPO_ID")'): " FOLDER_NAME
            if [ -z "$FOLDER_NAME" ]; then
                FOLDER_NAME="$(basename "$REPO_ID")"
            fi
            ;;
        *)
            echo "❌ Scelta non valida. Operazione annullata."
            exit 1
            ;;
    esac
fi

DEST_PATH="$MODELS_DIR/$FOLDER_NAME"

echo ""
echo "📂 Destinazione salvataggio: $DEST_PATH"
echo "⬇️ Avvio download di '$REPO_ID' tramite Podman..."
echo ""

podman run --rm -it \
  -v "$MODELS_DIR":/download \
  docker.io/library/python:3.11-slim \
  bash -c "pip install --no-cache-dir \"huggingface_hub[cli]\" && huggingface-cli download \"$REPO_ID\" --local-dir \"/download/$FOLDER_NAME\" --local-dir-use-symlinks False"

echo ""
echo "=========================================================="
echo "🎉 DOWNLOAD COMPLETATO CON SUCCESSO!"
echo " Modello salvato in: $DEST_PATH"
echo " Apri http://localhost:5000 nel browser per avviarlo su Intel Arc."
echo "=========================================================="
