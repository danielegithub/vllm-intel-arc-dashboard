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
    echo "Seleziona uno dei modelli verificati o inserisci un Repo ID personalizzato:"
    echo ""
    echo "  1) Qwen2.5-Coder-14B-Instruct-AWQ (Codice - Qwen/Qwen2.5-Coder-14B-Instruct-AWQ)"
    echo "  2) Qwen2.5-14B-Instruct-AWQ       (Generale - Qwen/Qwen2.5-14B-Instruct-AWQ)"
    echo "  3) Gemma-2-9B-IT-AWQ              (Google - casperhansen/gemma-2-9b-it-awq)"
    echo "  4) Qwen2.5-7B-Instruct            (Generale 7B - Qwen/Qwen2.5-7B-Instruct)"
    echo "  5) Inserisci Repo ID personalizzato Hugging Face"
    echo ""
    read -p "Scelta [1-5]: " CHOICE

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
  bash -c "pip install --no-cache-dir huggingface_hub && hf download '$REPO_ID' --local-dir '/download/$FOLDER_NAME'"

echo ""
echo "=========================================================="
echo "🎉 DOWNLOAD COMPLETATO CON SUCCESSO!"
echo " Modello salvato in: $DEST_PATH"
echo " Apri http://localhost:5000 nel browser per avviarlo su Intel Arc."
echo "=========================================================="
