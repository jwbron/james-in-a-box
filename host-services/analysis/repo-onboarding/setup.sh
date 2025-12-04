#!/bin/bash
# Setup script for repo-onboarding tools
# Creates symlinks and prepares the tools for use

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up repo-onboarding tools..."

# Ensure scripts are executable
chmod +x "$SCRIPT_DIR/jib-internal-devtools-setup"
chmod +x "$SCRIPT_DIR/jib-regenerate-indexes"
chmod +x "$SCRIPT_DIR/docs-index-updater.py"

# Create symlinks in ~/.local/bin
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

# Remove existing symlinks if they exist
for tool in jib-internal-devtools-setup jib-regenerate-indexes docs-index-updater; do
    if [ -L "$LOCAL_BIN/$tool" ]; then
        rm "$LOCAL_BIN/$tool"
    fi
done

# Create new symlinks
ln -s "$SCRIPT_DIR/jib-internal-devtools-setup" "$LOCAL_BIN/jib-internal-devtools-setup"
ln -s "$SCRIPT_DIR/jib-regenerate-indexes" "$LOCAL_BIN/jib-regenerate-indexes"
ln -s "$SCRIPT_DIR/docs-index-updater.py" "$LOCAL_BIN/docs-index-updater"

echo "  Created symlinks:"
echo "    - $LOCAL_BIN/jib-internal-devtools-setup"
echo "    - $LOCAL_BIN/jib-regenerate-indexes"
echo "    - $LOCAL_BIN/docs-index-updater"

# Also setup confluence-doc-discoverer if it exists
CONFLUENCE_SETUP="$(dirname "$SCRIPT_DIR")/confluence-doc-discoverer/setup.sh"
if [ -f "$CONFLUENCE_SETUP" ]; then
    echo ""
    echo "Setting up confluence-doc-discoverer..."
    bash "$CONFLUENCE_SETUP"
fi

# Verify PATH
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo ""
    echo "Note: Add $LOCAL_BIN to your PATH if not already present:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "Setup complete!"
echo ""
echo "Available commands:"
echo "  jib-internal-devtools-setup  - Full repository onboarding"
echo "  jib-regenerate-indexes       - Quick index regeneration"
echo "  docs-index-updater           - Update docs/index.md"
echo "  confluence-doc-discoverer    - Find relevant Confluence docs"
echo ""
echo "Run 'jib-internal-devtools-setup --help' for usage."
