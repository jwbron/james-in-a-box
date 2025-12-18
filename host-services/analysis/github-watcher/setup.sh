#!/bin/bash
# Setup script for GitHub Watcher host-side services
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up GitHub Watcher services..."

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

# Install all three services and timers
for service in ci-fixer comment-responder pr-reviewer; do
    ln -sf "${SCRIPT_DIR}/${service}.service" ~/.config/systemd/user/
    ln -sf "${SCRIPT_DIR}/${service}.timer" ~/.config/systemd/user/
done

# Reload systemd
systemctl --user daemon-reload

# Enable and start all three timers
for service in ci-fixer comment-responder pr-reviewer; do
    systemctl --user enable "${service}.timer"
    systemctl --user start "${service}.timer"
    echo "✓ ${service}.timer enabled and started"
done

echo ""
echo "Setup complete!"
echo ""
echo "Three separate services are now running (every 5 minutes each):"
echo "  - ci-fixer: Fix check failures and merge conflicts"
echo "  - comment-responder: Respond to PR comments"
echo "  - pr-reviewer: Review PRs (opt-in via assignment)"
echo ""
echo "To run services manually:"
echo "  systemctl --user start ci-fixer.service"
echo "  systemctl --user start comment-responder.service"
echo "  systemctl --user start pr-reviewer.service"
echo ""
echo "To check status:"
echo "  systemctl --user list-timers 'ci-fixer*' 'comment-responder*' 'pr-reviewer*'"
echo ""
echo "To view logs:"
echo "  journalctl --user -u ci-fixer.service -f"
echo "  journalctl --user -u comment-responder.service -f"
echo "  journalctl --user -u pr-reviewer.service -f"
