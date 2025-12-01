#!/bin/bash
# Setup script for GitHub Token Refresher service
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="github-token-refresher.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up GitHub Token Refresher service..."
echo ""

# Check for GitHub App credentials
APP_ID_FILE="${HOME}/.config/jib/github-app-id"
INSTALLATION_ID_FILE="${HOME}/.config/jib/github-app-installation-id"
PRIVATE_KEY_FILE="${HOME}/.config/jib/github-app.pem"

if [[ ! -f "$APP_ID_FILE" ]] || [[ ! -f "$INSTALLATION_ID_FILE" ]] || [[ ! -f "$PRIVATE_KEY_FILE" ]]; then
    echo "WARNING: GitHub App credentials not fully configured."
    echo ""
    echo "Expected files:"
    echo "  - $APP_ID_FILE"
    echo "  - $INSTALLATION_ID_FILE"
    echo "  - $PRIVATE_KEY_FILE"
    echo ""
    echo "The service will start but won't function until credentials are configured."
    echo "See docs/setup/github-app-setup.md for instructions."
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
echo "✓ Sharing directory exists: ${HOME}/.jib-sharing"

# Make the script executable
chmod +x "$COMPONENT_DIR/github-token-refresher.py"
echo "✓ Script made executable"

# Symlink service file
mkdir -p "$SYSTEMD_DIR"
ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
echo "✓ Service file symlinked to $SYSTEMD_DIR/$SERVICE_NAME"

# Reload systemd
systemctl --user daemon-reload
echo "✓ Systemd daemon reloaded"

# Enable service
systemctl --user enable "$SERVICE_NAME"
echo "✓ Service enabled"

# Start service
systemctl --user start "$SERVICE_NAME"
echo "✓ Service started"

# Wait a moment for initial token generation
sleep 2

# Check if token file was created
TOKEN_FILE="${HOME}/.jib-sharing/.github-token"
if [[ -f "$TOKEN_FILE" ]]; then
    echo ""
    echo "✓ Initial token generated successfully!"
    echo "  Token file: $TOKEN_FILE"
    # Show expiry time
    EXPIRES_AT=$(python3 -c "import json; print(json.load(open('$TOKEN_FILE'))['expires_at'])" 2>/dev/null || echo "unknown")
    echo "  Expires at: $EXPIRES_AT"
else
    echo ""
    echo "⚠ Token file not yet created."
    echo "  Check service logs: journalctl --user -u $SERVICE_NAME -f"
fi

echo ""
echo "Service status:"
systemctl --user status "$SERVICE_NAME" --no-pager || true

echo ""
echo "Setup complete!"
echo ""
echo "The service will:"
echo "  - Generate a fresh GitHub token every 45 minutes"
echo "  - Write tokens to ~/.jib-sharing/.github-token"
echo "  - Running containers will automatically use refreshed tokens"
echo ""
echo "Useful commands:"
echo "  systemctl --user status $SERVICE_NAME    # Check status"
echo "  systemctl --user restart $SERVICE_NAME   # Restart service"
echo "  systemctl --user stop $SERVICE_NAME      # Stop service"
echo "  journalctl --user -u $SERVICE_NAME -f    # View logs"
echo "  cat ~/.jib-sharing/.github-token         # View current token info"

