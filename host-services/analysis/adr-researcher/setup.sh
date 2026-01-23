#!/bin/bash
# Setup script for ADR Researcher host-side service
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up ADR Researcher..."

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
    echo "Make sure ~/repos/james-in-a-box/bin is in your PATH"
fi

# Create state directory
mkdir -p ~/.local/share/adr-researcher

# Install systemd user services
mkdir -p ~/.config/systemd/user

ln -sf "${SCRIPT_DIR}/adr-researcher.service" ~/.config/systemd/user/
ln -sf "${SCRIPT_DIR}/adr-researcher.timer" ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable and start timer
systemctl --user enable adr-researcher.timer
echo "✓ Timer enabled"

systemctl --user start adr-researcher.timer
echo "✓ Timer started"

echo ""
echo "Setup complete!"
echo ""
echo "Automated weekly research enabled (Mondays at 11am)."
echo ""
echo "To run manually:"
echo "  systemctl --user start adr-researcher.service"
echo ""
echo "To check status:"
echo "  systemctl --user status adr-researcher.timer"
echo "  journalctl --user -u adr-researcher.service -f"
echo ""
echo "Additional manual run modes:"
echo "  bin/adr-researcher --scope open-prs    # Research ADRs in open PRs"
echo "  bin/adr-researcher --scope merged      # Update implemented ADRs"
echo "  bin/adr-researcher --generate \"topic\"  # Generate new ADR"

