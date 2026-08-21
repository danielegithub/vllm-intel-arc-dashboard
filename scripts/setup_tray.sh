#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$PROJECT_DIR/vllm-dashboard-tray.desktop"
TARGET_FILE="$AUTOSTART_DIR/vllm-dashboard-tray.desktop"

mkdir -p "$AUTOSTART_DIR"

# Assicura che i percorsi nel file .desktop siano corretti
cat <<EOF > "$TARGET_FILE"
[Desktop Entry]
Type=Application
Name=vLLM Dashboard System Tray
Comment=Monitora e gestisce il servizio vLLM Dashboard dalla tray bar
Exec=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/scripts/tray_indicator.py
Icon=$PROJECT_DIR/assets/vllm-logo.png
Terminal=false
Categories=Utility;System;
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

chmod +x "$TARGET_FILE"
chmod +x "$PROJECT_DIR/scripts/tray_indicator.py"

echo "✅ System Tray Autostart configurato con successo in $TARGET_FILE"
echo "👉 Puoi avviarlo subito eseguendo: $PROJECT_DIR/venv/bin/python $PROJECT_DIR/scripts/tray_indicator.py &"
