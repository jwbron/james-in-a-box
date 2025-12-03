#!/bin/bash
# Setup script for confluence-doc-discoverer
# Creates symlinks and prepares the tool for use

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_NAME="confluence-doc-discoverer"
TOOL_SCRIPT="$SCRIPT_DIR/confluence-doc-discoverer.py"

echo "Setting up $TOOL_NAME..."

# Ensure script is executable
chmod +x "$TOOL_SCRIPT"

# Create symlink in ~/.local/bin
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

if [ -L "$LOCAL_BIN/$TOOL_NAME" ]; then
    rm "$LOCAL_BIN/$TOOL_NAME"
fi

ln -s "$TOOL_SCRIPT" "$LOCAL_BIN/$TOOL_NAME"
echo "  Created symlink: $LOCAL_BIN/$TOOL_NAME"

# Verify PATH
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
    echo ""
    echo "Note: Add $LOCAL_BIN to your PATH if not already present:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "Setup complete! Run '$TOOL_NAME --help' for usage."
