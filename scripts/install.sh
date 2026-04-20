#!/bin/bash
set -e

INSTALL_DIR=/opt/meshcore-dashboard

echo "Installing MeshCore Dashboard to $INSTALL_DIR..."

mkdir -p "$INSTALL_DIR/data"
cp -r meshcore_dashboard "$INSTALL_DIR/"
cp pyproject.toml uv.lock "$INSTALL_DIR/"

cd "$INSTALL_DIR"
uv sync --frozen

# Write systemd unit
cat > /etc/systemd/system/meshcore-dashboard.service << 'EOF'
[Unit]
Description=MeshCore Repeater Dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/meshcore-dashboard
ExecStart=/opt/meshcore-dashboard/.venv/bin/uvicorn meshcore_dashboard.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
EnvironmentFile=/opt/meshcore-dashboard/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable meshcore-dashboard

echo ""
echo "Install complete. Create /opt/meshcore-dashboard/.env with:"
echo "  BASIC_AUTH_USER=admin"
echo "  BASIC_AUTH_PASS=<your-password>"
echo "  SERIAL_PORT=/dev/ttyACM0"
echo ""
echo "Then: systemctl start meshcore-dashboard"
