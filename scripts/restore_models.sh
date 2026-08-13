#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  🔄 vLLM Models Restore Utility"
echo "=========================================================="

MODELS_DIR="${MODELS_DIR:-$HOME/my_models}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/.vllm-dashboard/backups}"

mkdir -p "$MODELS_DIR"

if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR"/*.tar.gz 2>/dev/null)" ]; then
    echo "❌ Nessun backup (.tar.gz) trovato in $BACKUP_DIR."
    exit 1
fi

if [ -n "$1" ]; then
    BACKUP_FILE="$1"
else
    echo "Seleziona uno dei backup disponibili:"
    echo ""
    select FILE in "$BACKUP_DIR"/*.tar.gz; do
        if [ -n "$FILE" ]; then
            BACKUP_FILE="$FILE"
            break
        fi
    done
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ File di backup '$BACKUP_FILE' non trovato."
    exit 1
fi

echo ""
echo "📂 Archivio: $BACKUP_FILE"
echo "📂 Destinazione: $MODELS_DIR"
echo "⏳ Ripristino in corso..."

tar -xzf "$BACKUP_FILE" -C "$(dirname "$MODELS_DIR")"

echo ""
echo "=========================================================="
echo "🎉 RIPRISTINO COMPLETATO CON SUCCESSO!"
echo " Modelli ripristinati in: $MODELS_DIR"
echo "=========================================================="
