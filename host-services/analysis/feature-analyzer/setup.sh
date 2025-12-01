#!/usr/bin/env bash
#
# Feature Analyzer - Setup Script
#
# Phase 1: Installs the feature-analyzer CLI tool to ~/.local/bin
# Phase 2: Installs systemd timer for automated ADR detection
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"
STATE_DIR="$HOME/.local/share/feature-analyzer"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "Setting up Feature Analyzer..."
echo ""

# ==========================================
# Phase 1: CLI Tool Installation
# ==========================================

echo "=== Phase 1: CLI Tool ==="

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Create symlink for main CLI tool
ln -sf "$SCRIPT_DIR/feature-analyzer.py" "$INSTALL_DIR/feature-analyzer"
echo "✓ Installed feature-analyzer to $INSTALL_DIR/feature-analyzer"

# Create symlink for watcher CLI tool
ln -sf "$SCRIPT_DIR/adr_watcher.py" "$INSTALL_DIR/adr-watcher"
echo "✓ Installed adr-watcher to $INSTALL_DIR/adr-watcher"

# ==========================================
# Phase 2: Automated ADR Detection
# ==========================================

echo ""
echo "=== Phase 2: Automated ADR Detection ==="

# Create state directory
mkdir -p "$STATE_DIR"
echo "✓ Created state directory: $STATE_DIR"

# Install systemd user services
mkdir -p "$SYSTEMD_DIR"

ln -sf "${SCRIPT_DIR}/feature-analyzer-watcher.service" "$SYSTEMD_DIR/"
ln -sf "${SCRIPT_DIR}/feature-analyzer-watcher.timer" "$SYSTEMD_DIR/"
echo "✓ Installed systemd service and timer"

# Reload systemd
systemctl --user daemon-reload
echo "✓ Reloaded systemd daemon"

# Enable timer
systemctl --user enable feature-analyzer-watcher.timer
echo "✓ Enabled feature-analyzer-watcher timer"

# Start timer
systemctl --user start feature-analyzer-watcher.timer
echo "✓ Started feature-analyzer-watcher timer"

# ==========================================
# Summary
# ==========================================

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Ensure $INSTALL_DIR is in your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "Phase 1 - Manual CLI:"
echo "  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --validate-only"
echo ""
echo "Phase 2 - Automated Watcher (every 15 minutes):"
echo "  # Check status"
echo "  systemctl --user status feature-analyzer-watcher.timer"
echo ""
echo "  # View logs"
echo "  journalctl --user -u feature-analyzer-watcher.service -f"
echo ""
echo "  # Run manually"
echo "  systemctl --user start feature-analyzer-watcher.service"
echo ""
echo "  # Check watcher status"
echo "  adr-watcher status"
echo ""
