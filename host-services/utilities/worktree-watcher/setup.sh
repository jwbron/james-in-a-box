#!/bin/bash
# Setup script for jib Worktree Watcher
# Installs systemd service and timer for cleaning up orphaned worktrees

set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="worktree-watcher"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Setting up jib Worktree Watcher..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Make script executable
chmod +x "$COMPONENT_DIR/worktree-watcher.py"

# Symlink service and timer files
echo "Installing systemd service and timer..."
ln -sf "$COMPONENT_DIR/${SERVICE_NAME}.service" "$SYSTEMD_DIR/"
ln -sf "$COMPONENT_DIR/${SERVICE_NAME}.timer" "$SYSTEMD_DIR/"

# Reload systemd
echo "Reloading systemd daemon..."
systemctl --user daemon-reload

# Enable and start timer
echo "Enabling and starting timer..."
systemctl --user enable "${SERVICE_NAME}.timer"
systemctl --user start "${SERVICE_NAME}.timer"

echo ""
echo "✅ Worktree watcher installed and started"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Management Commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  # Check timer status"
echo "  systemctl --user status ${SERVICE_NAME}.timer"
echo ""
echo "  # Check service status"
echo "  systemctl --user status ${SERVICE_NAME}.service"
echo ""
echo "  # View logs"
echo "  journalctl --user -u ${SERVICE_NAME}.service -f"
echo ""
echo "  # Manual cleanup run"
echo "  systemctl --user start ${SERVICE_NAME}.service"
echo ""
echo "  # List all timers"
echo "  systemctl --user list-timers"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
