#!/bin/bash
# Setup script for GitHub Sync component
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Setting up GitHub Sync..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create systemd user directory
mkdir -p "$SYSTEMD_DIR"

# Make sync script executable
chmod +x "$COMPONENT_DIR/sync.py"
echo "✓ Sync script made executable"

# Symlink service and timer files
echo "Installing systemd service and timer..."
ln -sf "$COMPONENT_DIR/systemd/github-sync.service" "$SYSTEMD_DIR/"
ln -sf "$COMPONENT_DIR/systemd/github-sync.timer" "$SYSTEMD_DIR/"

# Reload systemd
echo "Reloading systemd daemon..."
systemctl --user daemon-reload

# Check if gh is installed and authenticated
if ! command -v gh &> /dev/null; then
    echo ""
    echo "⚠ GitHub CLI (gh) not found"
    echo "  Install: https://cli.github.com/"
    echo "  Or: brew install gh (macOS) / sudo dnf install gh (Fedora)"
    echo ""
else
    echo "✓ GitHub CLI (gh) found"

    # Check authentication
    if gh auth status &> /dev/null; then
        echo "✓ GitHub CLI authenticated"
    else
        echo ""
        echo "⚠ GitHub CLI not authenticated"
        echo "  Run: gh auth login"
        echo ""
    fi
fi

# Create sync directory
SYNC_DIR="$HOME/context-sync/github"
mkdir -p "$SYNC_DIR"/{prs,checks}
echo "✓ Sync directory created: $SYNC_DIR"

# Enable timer (but don't start yet - user may need to configure first)
echo "Enabling github-sync timer..."
systemctl --user enable github-sync.timer

echo ""
echo "✅ GitHub sync installed"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Ensure gh is authenticated:"
echo "   gh auth status"
echo "   gh auth login  # if needed"
echo ""
echo "2. Run initial sync:"
echo "   systemctl --user start github-sync.service"
echo ""
echo "3. Enable automated syncing (every 15 min):"
echo "   systemctl --user start github-sync.timer"
echo ""
echo "4. Monitor sync:"
echo "   journalctl --user -u github-sync.service -f"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Management Commands:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  # Check timer status"
echo "  systemctl --user status github-sync.timer"
echo ""
echo "  # Check last sync"
echo "  systemctl --user status github-sync.service"
echo ""
echo "  # Manual sync"
echo "  systemctl --user start github-sync.service"
echo ""
echo "  # View logs"
echo "  journalctl --user -u github-sync.service -n 50"
echo ""
echo "  # Stop automated syncing"
echo "  systemctl --user stop github-sync.timer"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
