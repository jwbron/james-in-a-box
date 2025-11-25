#!/bin/bash
# Setup systemd service failure notifications
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$COMPONENT_DIR/../.." && pwd)"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up service failure notifications..."

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Symlink the failure notification service template
ln -sf "$COMPONENT_DIR/service-failure-notify@.service" "$SYSTEMD_DIR/"
echo "✓ Service template symlinked to $SYSTEMD_DIR/service-failure-notify@.service"

# Reload systemd
systemctl --user daemon-reload
echo "✓ Systemd daemon reloaded"

echo ""
echo "Setup complete!"
echo ""
echo "What this does:"
echo "  • When a service fails, systemd triggers service-failure-notify@<service-name>.service"
echo "  • The notification script creates a file in ~/.jib-sharing/notifications/"
echo "  • Slack notifier picks it up and sends a Slack DM"
echo ""
echo "Services with failure notifications:"
echo "  • codebase-analyzer.service"
echo "  • conversation-analyzer.service"
echo "  • slack-notifier.service"
echo ""
echo "Test failure notification:"
echo "  systemctl --user start service-failure-notify@test.service"
