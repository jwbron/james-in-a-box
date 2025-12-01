#!/usr/bin/env bash
#
# Feature Analyzer - Setup Script
#
# Phase 1: Installs the feature-analyzer CLI tool to ~/.local/bin
# Phase 2: Installs systemd timer for automated ADR detection
# Phase 3: Adds doc generator and PR creator modules
# Phase 4: Adds rollback utilities
# Phase 5: Adds weekly code analyzer and timer
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

# Ensure Python files are executable
chmod +x "$SCRIPT_DIR/feature-analyzer.py"
chmod +x "$SCRIPT_DIR/adr_watcher.py"
chmod +x "$SCRIPT_DIR/doc_generator.py" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/pr_creator.py" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/weekly_analyzer.py" 2>/dev/null || true

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
echo "✓ Installed systemd service and timer (ADR watcher - 15min)"

# Phase 5: Install weekly timer
ln -sf "${SCRIPT_DIR}/feature-analyzer-weekly.service" "$SYSTEMD_DIR/"
ln -sf "${SCRIPT_DIR}/feature-analyzer-weekly.timer" "$SYSTEMD_DIR/"
echo "✓ Installed systemd service and timer (Weekly analyzer - Mondays 11am)"

# Reload systemd
systemctl --user daemon-reload
echo "✓ Reloaded systemd daemon"

# Enable timers
systemctl --user enable feature-analyzer-watcher.timer
echo "✓ Enabled feature-analyzer-watcher timer"

systemctl --user enable feature-analyzer-weekly.timer
echo "✓ Enabled feature-analyzer-weekly timer"

# Start timers
systemctl --user start feature-analyzer-watcher.timer
echo "✓ Started feature-analyzer-watcher timer"

systemctl --user start feature-analyzer-weekly.timer
echo "✓ Started feature-analyzer-weekly timer"

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
echo "Phase 3 - Multi-Doc Updates with PR Creation:"
echo "  # Generate updates and create PR"
echo "  feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md"
echo ""
echo "  # With LLM assistance (requires jib)"
echo "  feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --use-jib"
echo ""
echo "  # Run watcher in Phase 3 mode"
echo "  adr-watcher watch --phase3"
echo ""
echo "Phase 4 - Rollback Utilities:"
echo "  # List auto-generated commits"
echo "  feature-analyzer rollback list-commits"
echo ""
echo "  # Revert a file"
echo "  feature-analyzer rollback revert-file docs/README.md"
echo ""
echo "Phase 5 - Weekly Code Analysis (Mondays 11am):"
echo "  # Check timer status"
echo "  systemctl --user status feature-analyzer-weekly.timer"
echo ""
echo "  # Run manually"
echo "  feature-analyzer weekly-analyze --dry-run"
echo ""
echo "  # Run and create PR"
echo "  feature-analyzer weekly-analyze"
echo ""
