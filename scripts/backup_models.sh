#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  📦 vLLM Models Backup Utility"
echo "=========================================================="

MODELS_DIR="${MODELS_DIR:-$HOME/my_models}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/.vllm-dashboard/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/models_backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

if [ ! -d "$MODELS_DIR" ] || [ -z "$(ls -A "$MODELS_DIR" 2>/dev/null)" ]; then
    echo "❌ Nessun modello trovato in $MODELS_DIR per il backup."
    exit 1
fi

echo "📂 Origine: $MODELS_DIR"
echo "📂 Destinazione: $BACKUP_FILE"
echo "⏳ Creazione archivio in corso..."

tar -czf "$BACKUP_FILE" -C "$(dirname "$MODELS_DIR")" "$(basename "$MODELS_DIR")"

echo ""
echo "=========================================================="
echo "🎉 BACKUP COMPLETATO CON SUCCESSO!"
echo " File: $BACKUP_FILE"
echo " Dimensione: $(du -sh "$BACKUP_FILE" | cut -f1)"
echo "=========================================================="
