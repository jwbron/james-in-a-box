#!/bin/bash
# Setup script for Context Sync component
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"
# Shared virtual environment is now managed by main setup.sh using uv
# Dependencies are defined in host-services/pyproject.toml

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Setting up Context Sync..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Dependencies are now managed centrally via uv in host-services/pyproject.toml
echo "✓ Dependencies managed by uv (host-services/pyproject.toml)"

# Symlink service and timer files
echo "Installing systemd service and timer..."
ln -sf "$COMPONENT_DIR/context-sync.service" "$SYSTEMD_DIR/"
ln -sf "$COMPONENT_DIR/context-sync.timer" "$SYSTEMD_DIR/"

# Reload systemd
echo "Reloading systemd daemon..."
systemctl --user daemon-reload

# Check if configuration exists
CONFIG_DIR="$HOME/.config/context-sync"
if [ ! -f "$CONFIG_DIR/.env" ]; then
    echo ""
    echo "⚠ Configuration not found"
    echo "  Create $CONFIG_DIR/.env with your credentials"
    echo "  See $COMPONENT_DIR/docs/README.md for configuration details"
    echo ""
fi

# Enable timer (but don't start yet - user may need to configure first)
echo "Enabling context-sync timer..."
systemctl --user enable context-sync.timer

echo ""
echo "✅ Context sync installed"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Configure credentials (if not done):"
echo "   $COMPONENT_DIR/docs/README.md"
echo ""
echo "2. Run initial sync:"
echo "   systemctl --user start context-sync.service"
echo ""
echo "3. Enable automated hourly syncing:"
echo "   systemctl --user start context-sync.timer"
echo ""
echo "4. Monitor sync:"
echo "   journalctl --user -u context-sync.service -f"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Management Commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  # Check timer status"
echo "  systemctl --user status context-sync.timer"
echo ""
echo "  # Check last sync"
echo "  systemctl --user status context-sync.service"
echo ""
echo "  # Manual sync"
echo "  systemctl --user start context-sync.service"
echo ""
echo "  # View logs"
echo "  journalctl --user -u context-sync.service -n 50"
echo ""
echo "  # Stop automated syncing"
echo "  systemctl --user stop context-sync.timer"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
