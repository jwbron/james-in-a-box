#!/bin/bash
# Setup script for Slack Receiver service
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="slack-receiver.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up Slack Receiver service..."

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

# Check status
echo ""
echo "Service status:"
systemctl --user status "$SERVICE_NAME" --no-pager

echo ""
echo "Setup complete!"
echo ""
echo "Useful commands:"
echo "  systemctl --user status $SERVICE_NAME    # Check status"
echo "  systemctl --user restart $SERVICE_NAME   # Restart service"
echo "  systemctl --user stop $SERVICE_NAME      # Stop service"
echo "  journalctl --user -u $SERVICE_NAME -f    # View logs"

