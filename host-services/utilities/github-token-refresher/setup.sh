#!/bin/bash
# Setup script for GitHub Token Refresher service
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="github-token-refresher.service"
TIMER_NAME="github-token-refresher.timer"
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

# Ensure gateway secrets directory exists
mkdir -p "${HOME}/.jib-gateway"
echo "✓ Gateway secrets directory exists: ${HOME}/.jib-gateway"

# Make the script executable
chmod +x "$COMPONENT_DIR/github-token-refresher.py"
echo "✓ Script made executable"

# Symlink service and timer files
mkdir -p "$SYSTEMD_DIR"
ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
ln -sf "$COMPONENT_DIR/$TIMER_NAME" "$SYSTEMD_DIR/"
echo "✓ Service file symlinked to $SYSTEMD_DIR/$SERVICE_NAME"
echo "✓ Timer file symlinked to $SYSTEMD_DIR/$TIMER_NAME"

# Stop old daemon-style service if it was running as a daemon (migration)
# Note: We only stop it, we don't disable it - the service file is still needed
# for the timer to trigger. The timer will manage when the service runs.
systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true

# Reload systemd to pick up new/changed unit files
systemctl --user daemon-reload
echo "✓ Systemd daemon reloaded"

# Enable and start timer (timer triggers the service)
systemctl --user enable "$TIMER_NAME"
echo "✓ Timer enabled"

systemctl --user start "$TIMER_NAME"
echo "✓ Timer started"

# Run service once immediately to generate initial token
systemctl --user start "$SERVICE_NAME"
echo "✓ Initial token refresh triggered"

# Wait a moment for initial token generation
sleep 2

# Check if token file was created
TOKEN_FILE="${HOME}/.jib-gateway/.github-token"
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
echo "Timer status:"
systemctl --user status "$TIMER_NAME" --no-pager || true

echo ""
echo "Setup complete!"
echo ""
echo "The timer will:"
echo "  - Trigger token refresh every 30 minutes"
echo "  - Run immediately on boot"
echo "  - Catch up on missed runs after suspend/hibernate (Persistent=true)"
echo "  - Write tokens to ~/.jib-gateway/.github-token"
echo "  - Running containers will automatically use refreshed tokens"
echo ""
echo "Useful commands:"
echo "  systemctl --user status $TIMER_NAME      # Check timer status"
echo "  systemctl --user list-timers             # See next scheduled run"
echo "  systemctl --user start $SERVICE_NAME     # Force immediate refresh"
echo "  journalctl --user -u $SERVICE_NAME -f    # View logs"
echo "  cat ~/.jib-gateway/.github-token         # View current token info"

