#!/bin/bash
# Setup script for venv-setup service
# This oneshot service ensures the Python venv exists before dependent services start
set -eu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="venv-setup.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up venv-setup service..."

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Symlink service file
if ln -sf "$SCRIPT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"; then
    echo "✓ Service file symlinked to $SYSTEMD_DIR/$SERVICE_NAME"
else
    echo "✗ Failed to create symlink"
    exit 1
fi

# Reload systemd
systemctl --user daemon-reload
echo "✓ Systemd daemon reloaded"

# Enable service
systemctl --user enable "$SERVICE_NAME"
echo "✓ Service enabled"

# Run the service once to ensure venv is created
echo "Running venv setup..."
systemctl --user start "$SERVICE_NAME"
echo "✓ Venv setup complete"

echo ""
echo "Setup complete!"
echo ""
echo "This is a oneshot service that ensures the Python venv exists."
echo "Other services (slack-notifier, slack-receiver, context-sync, github-token-refresher)"
echo "depend on this service and will start after it completes."
echo ""
echo "Useful commands:"
echo "  systemctl --user status $SERVICE_NAME    # Check status"
echo "  systemctl --user start $SERVICE_NAME     # Re-run venv setup"
echo "  journalctl --user -u $SERVICE_NAME       # View logs"
