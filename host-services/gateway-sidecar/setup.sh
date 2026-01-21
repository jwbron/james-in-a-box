#!/bin/bash
# Setup script for Gateway Sidecar service
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="gateway-sidecar.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up Gateway Sidecar service..."
echo ""

# Check for github-token-refresher service
if ! systemctl --user is-enabled github-token-refresher.service >/dev/null 2>&1; then
    echo "WARNING: github-token-refresher.service is not enabled."
    echo "The gateway requires this service for GitHub authentication."
    echo ""
    echo "Please run first:"
    echo "  ./host-services/utilities/github-token-refresher/setup.sh"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled."
        exit 1
    fi
fi

# Ensure sharing directory exists
mkdir -p "${HOME}/.jib-sharing"
echo "Sharing directory exists: ${HOME}/.jib-sharing"

# Ensure host-services venv exists with required dependencies
VENV_DIR="${COMPONENT_DIR}/../.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating host-services virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip
fi

# Install dependencies if needed
if ! "$VENV_DIR/bin/python" -c "import flask" 2>/dev/null; then
    echo "Installing Flask..."
    "$VENV_DIR/bin/pip" install flask waitress
fi

echo "Dependencies installed"

# Make the gateway script executable
chmod +x "$COMPONENT_DIR/gateway.py"
echo "Gateway script made executable"

# Symlink service file
mkdir -p "$SYSTEMD_DIR"
ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
echo "Service file symlinked to $SYSTEMD_DIR/$SERVICE_NAME"

# Reload systemd
systemctl --user daemon-reload
echo "Systemd daemon reloaded"

# Enable service
systemctl --user enable "$SERVICE_NAME"
echo "Service enabled"

# Start service
systemctl --user start "$SERVICE_NAME"
echo "Service started"

# Wait for service to be ready
echo ""
echo "Waiting for gateway to be ready..."
sleep 2

# Health check
HEALTH_URL="http://localhost:9847/api/v1/health"
if curl -s "$HEALTH_URL" | grep -q '"status"'; then
    echo ""
    echo "Gateway is running!"
    echo ""
    curl -s "$HEALTH_URL" | python3 -m json.tool
else
    echo ""
    echo "WARNING: Gateway health check failed."
    echo "Check service logs: journalctl --user -u $SERVICE_NAME -f"
fi

echo ""
echo "Service status:"
systemctl --user status "$SERVICE_NAME" --no-pager || true

echo ""
echo "Setup complete!"
echo ""
echo "The gateway sidecar:"
echo "  - Listens on http://localhost:9847"
echo "  - Enforces branch/PR ownership policies"
echo "  - Blocks merge operations (human must merge via GitHub UI)"
echo ""
echo "Useful commands:"
echo "  systemctl --user status $SERVICE_NAME    # Check status"
echo "  systemctl --user restart $SERVICE_NAME   # Restart service"
echo "  systemctl --user stop $SERVICE_NAME      # Stop service"
echo "  journalctl --user -u $SERVICE_NAME -f    # View logs"
echo "  curl http://localhost:9847/api/v1/health # Health check"
