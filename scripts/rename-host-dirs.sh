#!/bin/bash
#
# Rename Host Directories - james-in-a-box Migration
#
# This script renames the old claude-sandbox directories to the new jib naming scheme.
# Run this ON THE HOST MACHINE (not in the container).
#

set -euo pipefail

echo "=== james-in-a-box Directory Rename Script ==="
echo ""
echo "This script will rename the following directories:"
echo "  ~/.claude-sandbox-sharing -> ~/.jib-sharing"
echo "  ~/.claude-sandbox-tools   -> ~/.jib-tools"
echo "  ~/.config/slack-notifier  -> ~/.config/jib-notifier"
echo ""

# Check if running in container
if [ -f "/.dockerenv" ]; then
    echo "ERROR: This script must be run on the HOST machine, not in the container!"
    echo "Exit the container and run this script on your host."
    exit 1
fi

# Check what exists
echo "Checking current directories..."
echo ""

if [ -d "$HOME/.claude-sandbox-sharing" ]; then
    echo "✓ Found: ~/.claude-sandbox-sharing"
    SHARING_EXISTS=1
else
    echo "  (not found: ~/.claude-sandbox-sharing)"
    SHARING_EXISTS=0
fi

if [ -d "$HOME/.claude-sandbox-tools" ]; then
    echo "✓ Found: ~/.claude-sandbox-tools"
    TOOLS_EXISTS=1
else
    echo "  (not found: ~/.claude-sandbox-tools)"
    TOOLS_EXISTS=0
fi

if [ -d "$HOME/.config/slack-notifier" ]; then
    echo "✓ Found: ~/.config/slack-notifier"
    NOTIFIER_EXISTS=1
else
    echo "  (not found: ~/.config/slack-notifier)"
    NOTIFIER_EXISTS=0
fi

echo ""

# Check if new directories already exist
CONFLICTS=0
if [ -d "$HOME/.jib-sharing" ]; then
    echo "⚠ WARNING: ~/.jib-sharing already exists!"
    CONFLICTS=1
fi

if [ -d "$HOME/.jib-tools" ]; then
    echo "⚠ WARNING: ~/.jib-tools already exists!"
    CONFLICTS=1
fi

if [ -d "$HOME/.config/jib-notifier" ]; then
    echo "⚠ WARNING: ~/.config/jib-notifier already exists!"
    CONFLICTS=1
fi

if [ $CONFLICTS -eq 1 ]; then
    echo ""
    echo "ERROR: One or more target directories already exist."
    echo "Please resolve conflicts manually before running this script."
    exit 1
fi

# Confirm with user
echo "Ready to rename directories. Continue? (yes/no)"
read -r response

if [ "$response" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Renaming directories..."

# Rename sharing directory
if [ $SHARING_EXISTS -eq 1 ]; then
    mv "$HOME/.claude-sandbox-sharing" "$HOME/.jib-sharing"
    echo "✓ Renamed: ~/.claude-sandbox-sharing -> ~/.jib-sharing"
fi

# Rename tools directory
if [ $TOOLS_EXISTS -eq 1 ]; then
    mv "$HOME/.claude-sandbox-tools" "$HOME/.jib-tools"
    echo "✓ Renamed: ~/.claude-sandbox-tools -> ~/.jib-tools"
fi

# Rename notifier config directory
if [ $NOTIFIER_EXISTS -eq 1 ]; then
    mv "$HOME/.config/slack-notifier" "$HOME/.config/jib-notifier"
    echo "✓ Renamed: ~/.config/slack-notifier -> ~/.config/jib-notifier"

    # Update config file paths inside the config
    if [ -f "$HOME/.config/jib-notifier/config.json" ]; then
        sed -i 's|\.claude-sandbox-sharing|.jib-sharing|g' "$HOME/.config/jib-notifier/config.json"
        sed -i 's|\.claude-sandbox-tools|.jib-tools|g' "$HOME/.config/jib-notifier/config.json"
        echo "  ✓ Updated paths in config.json"
    fi
fi

echo ""
echo "=== Migration Complete! ==="
echo ""
echo "Next steps:"
echo "1. Rename the repository directory:"
echo "   cd ~/khan && mv cursor-sandboxed james-in-a-box"
echo ""
echo "2. Restart any running notifier services:"
echo "   cd ~/khan/james-in-a-box"
echo "   ./scripts/host-notify-ctl.sh restart"
echo "   ./scripts/host-receive-ctl.sh restart"
echo ""
echo "3. Update your docker run command to use new paths and repo name"
echo ""
