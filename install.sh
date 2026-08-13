#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  vLLM Intel Arc B580 Podman Manager - Install & Autostart"
echo "=========================================================="

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="vllm-dashboard.service"

echo "📂 Project Path: $PROJECT_DIR"

# 1. Ensure ~/my_models exists
mkdir -p "$HOME/my_models"
echo "✅ Directory ~/my_models verified."

# 2. Setup Virtual Environment
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "⚙️ Creating Python Virtual Environment..."
    python3 -m venv "$PROJECT_DIR/venv"
fi

echo "📦 Installing Python Dependencies..."
"$PROJECT_DIR/venv/bin/pip" install --upgrade pip --quiet
"$PROJECT_DIR/venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" --quiet
echo "✅ Python dependencies installed successfully."

# 3. Setup Systemd User Unit
mkdir -p "$SYSTEMD_USER_DIR"

ESCAPED_DIR="${PROJECT_DIR// /\\ }"

cat <<EOF > "$SYSTEMD_USER_DIR/$SERVICE_NAME"
[Unit]
Description=vLLM Intel Arc B580 Podman Manager Web Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=$ESCAPED_DIR
ExecStart=$ESCAPED_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000 --timeout-graceful-shutdown 2
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

echo "✅ Systemd service created at $SYSTEMD_USER_DIR/$SERVICE_NAME"

# 4. Enable & Start Systemd Service
echo "🔄 Reloading Systemd User Daemon..."
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

# 5. Enable lingering for autostart on boot without active login
if command -v loginctl >/dev/null 2>&1; then
    echo "🔒 Enabling user lingering for boot autostart..."
    loginctl enable-linger "$USER" || true
fi

echo ""
echo "=========================================================="
echo "🎉 INSTALLATION & SERVICE ACTIVATION COMPLETE!"
echo "=========================================================="
echo "🌐 Dashboard Web UI active at: http://localhost:5000"
echo "🤖 vLLM OpenAI API URL:       http://localhost:8000/v1"
echo "=========================================================="
