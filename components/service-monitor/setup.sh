#!/bin/bash
# Setup systemd service failure notifications
# Installs the failure notification template and updates services

set -euo pipefail

REPO_DIR="${HOME}/khan/james-in-a-box"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

echo "=== Setting up service failure notifications ==="
echo ""

# Create systemd user directory if it doesn't exist
mkdir -p "$SYSTEMD_USER_DIR"

# Install the failure notification service template
echo "1. Installing service-failure-notify@.service template..."
cp "${REPO_DIR}/systemd/common/service-failure-notify@.service" "$SYSTEMD_USER_DIR/"
echo "   ✓ Installed to ${SYSTEMD_USER_DIR}/service-failure-notify@.service"
echo ""

# Link or copy the updated service files
echo "2. Installing updated service files..."

# Codebase analyzer
if [ -f "$SYSTEMD_USER_DIR/codebase-analyzer.service" ]; then
    echo "   → Updating codebase-analyzer.service"
    cp "${REPO_DIR}/systemd/analyzers/codebase-analyzer.service" "$SYSTEMD_USER_DIR/"
fi

# Conversation analyzer
if [ -f "$SYSTEMD_USER_DIR/conversation-analyzer.service" ]; then
    echo "   → Updating conversation-analyzer.service"
    cp "${REPO_DIR}/systemd/analyzers/conversation-analyzer.service" "$SYSTEMD_USER_DIR/"
fi

# Slack notifier
if [ -f "$SYSTEMD_USER_DIR/slack-notifier.service" ]; then
    echo "   → Updating slack-notifier.service"
    cp "${REPO_DIR}/systemd/slack-notifier/slack-notifier.service" "$SYSTEMD_USER_DIR/"
fi

echo ""

# Reload systemd
echo "3. Reloading systemd daemon..."
systemctl --user daemon-reload
echo "   ✓ Daemon reloaded"
echo ""

# Check if services are running and restart them
echo "4. Checking running services..."
for service in codebase-analyzer conversation-analyzer slack-notifier; do
    if systemctl --user is-active --quiet "${service}.service" 2>/dev/null; then
        echo "   → ${service}.service is running"
        echo "     To apply changes, restart with: systemctl --user restart ${service}.service"
    fi
done
echo ""

echo "=== Setup complete! ==="
echo ""
echo "What this does:"
echo "  • When a service fails, systemd triggers service-failure-notify@<service-name>.service"
echo "  • The notification script creates a file in ~/sharing/notifications/"
echo "  • host-notify-slack.py picks it up and sends a Slack DM"
echo ""
echo "Services configured for failure notifications:"
echo "  • codebase-analyzer.service"
echo "  • conversation-analyzer.service"
echo "  • slack-notifier.service"
echo ""
echo "Test failure notification:"
echo "  systemctl --user start service-failure-notify@test.service"
echo ""
echo "View notification template:"
echo "  systemctl --user cat service-failure-notify@.service"
echo ""
