#!/usr/bin/env bash
#
# Feature Analyzer - Setup Script
#
# Installs the feature-analyzer CLI tool to ~/.local/bin
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"

echo "Setting up Feature Analyzer..."

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Create symlink
ln -sf "$SCRIPT_DIR/feature-analyzer.py" "$INSTALL_DIR/feature-analyzer"

echo "✓ Installed feature-analyzer to $INSTALL_DIR/feature-analyzer"
echo ""
echo "Ensure $INSTALL_DIR is in your PATH:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "Usage:"
echo "  feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --validate-only"
echo ""
