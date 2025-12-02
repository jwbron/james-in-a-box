#!/bin/bash
# Setup script for Service Failure Notify template
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="service-failure-notify@.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up Service Failure Notify..."

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Symlink template service file
ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
echo "✓ Template service symlinked"

# Reload systemd
systemctl --user daemon-reload
echo "✓ Systemd daemon reloaded"

echo ""
echo "Setup complete!"
echo ""
echo "This is a template service used by OnFailure= directives."
echo "It will be instantiated automatically when a service fails."
