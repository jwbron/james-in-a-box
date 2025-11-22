#!/bin/bash
# Setup script for context-watcher
# Creates configuration in ~/.config/context-watcher/ with secure permissions

set -e

CONFIG_DIR="${HOME}/.config/context-watcher"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
TEMPLATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/config"
TEMPLATE_FILE="${TEMPLATE_DIR}/context-watcher.yaml"

echo "=== Context Watcher Setup ==="
echo ""

# Create config directory with secure permissions
if [ ! -d "$CONFIG_DIR" ]; then
    echo "Creating configuration directory: $CONFIG_DIR"
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
    echo "✓ Directory created with secure permissions (700)"
else
    echo "✓ Configuration directory exists: $CONFIG_DIR"
fi

# Check if config already exists
if [ -f "$CONFIG_FILE" ]; then
    echo ""
    echo "⚠ Configuration file already exists:"
    echo "  $CONFIG_FILE"
    echo ""
    read -p "Overwrite with template? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing configuration"
        echo ""
        echo "To edit manually:"
        echo "  vim $CONFIG_FILE"
        exit 0
    fi
fi

# Copy template to config directory
if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "ERROR: Template file not found: $TEMPLATE_FILE"
    exit 1
fi

echo "Copying configuration template..."
cp "$TEMPLATE_FILE" "$CONFIG_FILE"
chmod 600 "$CONFIG_FILE"
echo "✓ Configuration file created with secure permissions (600)"

# Get user information
echo ""
echo "Let's configure your user information"
echo "(You can edit $CONFIG_FILE manually later)"
echo ""

read -p "Your full name [Jacob Wiesblatt]: " USER_NAME
USER_NAME=${USER_NAME:-"Jacob Wiesblatt"}

read -p "Your username [jwies]: " USERNAME
USERNAME=${USERNAME:-"jwies"}

read -p "Your email [jacob@khanacademy.org]: " USER_EMAIL
USER_EMAIL=${USER_EMAIL:-"jacob@khanacademy.org"}

read -p "Your GitHub username [jwiesblatt]: " GITHUB_USER
GITHUB_USER=${GITHUB_USER:-"jwiesblatt"}

# Update config file with user info
if command -v sed &> /dev/null; then
    sed -i "s/name: \".*\"/name: \"$USER_NAME\"/" "$CONFIG_FILE"
    sed -i "s/username: \".*\"/username: \"$USERNAME\"/" "$CONFIG_FILE"
    sed -i "s/email: \".*\"/email: \"$USER_EMAIL\"/" "$CONFIG_FILE"
    sed -i "s/github_username: \".*\"/github_username: \"$GITHUB_USER\"/" "$CONFIG_FILE"
    echo "✓ Configuration updated with your information"
else
    echo "⚠ sed not found - please edit $CONFIG_FILE manually"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Configuration location: $CONFIG_FILE"
echo "Permissions: $(stat -c '%a' "$CONFIG_FILE" 2>/dev/null || stat -f '%A' "$CONFIG_FILE" 2>/dev/null)"
echo ""
echo "Next steps:"
echo "  1. Review and customize: vim $CONFIG_FILE"
echo "  2. Enable the watcher: ./manage_watcher.sh enable"
echo "  3. Check status: ./manage_watcher.sh status"
echo ""
echo "Files and locations:"
echo "  Config:        $CONFIG_FILE"
echo "  State:         $CONFIG_DIR/watcher-state.json"
echo "  Logs:          $CONFIG_DIR/watcher.log"
echo "  Notifications: ~/.claude-sandbox-sharing/notifications/"
echo ""
