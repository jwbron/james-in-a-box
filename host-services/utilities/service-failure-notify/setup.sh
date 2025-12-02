#!/bin/bash
# Setup script for Service Failure Notify template
set -eu

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="service-failure-notify@.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "Setting up Service Failure Notify..."

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Symlink template service file and verify
if ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"; then
    echo "✓ Template service symlinked"
else
    echo "✗ Failed to create symlink"
    exit 1
fi

# Reload systemd
systemctl --user daemon-reload
echo "✓ Systemd daemon reloaded"

echo ""
echo "Setup complete!"
echo ""
echo "This is a template service used by OnFailure= directives."
echo "It will be instantiated automatically when a service fails."
