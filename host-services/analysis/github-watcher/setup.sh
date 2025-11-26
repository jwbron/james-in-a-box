#!/bin/bash
# Setup script for GitHub Watcher host-side service
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up GitHub Watcher..."

# Check prerequisites
if ! command -v gh &> /dev/null; then
    echo "ERROR: gh (GitHub CLI) is not installed"
    echo "Install it with: brew install gh (macOS) or apt install gh (Linux)"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "ERROR: gh is not authenticated"
    echo "Run: gh auth login"
    exit 1
fi

if ! command -v jib &> /dev/null; then
    echo "WARNING: jib command not found in PATH"
    echo "Make sure ~/khan/james-in-a-box/bin is in your PATH"
fi

# Create state directory
mkdir -p ~/.local/share/github-watcher

# Install systemd user services
mkdir -p ~/.config/systemd/user

cp "${SCRIPT_DIR}/github-watcher.service" ~/.config/systemd/user/
cp "${SCRIPT_DIR}/github-watcher.timer" ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

echo ""
echo "Setup complete!"
echo ""
echo "To enable automated monitoring:"
echo "  systemctl --user enable --now github-watcher.timer"
echo ""
echo "To run manually:"
echo "  systemctl --user start github-watcher.service"
echo ""
echo "To check status:"
echo "  systemctl --user status github-watcher.timer"
echo "  journalctl --user -u github-watcher.service -f"
