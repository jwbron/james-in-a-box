#!/bin/bash
# Manage context-watcher systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="context-watcher"

show_usage() {
    cat <<EOF
Usage: $0 <command>

Commands:
    enable      Enable and start the context watcher service
    disable     Disable and stop the service
    start       Start the watcher (if not already running)
    stop        Stop the watcher
    restart     Restart the watcher
    status      Show service status
    logs        Show recent logs
    logs-follow Follow logs in real-time

Examples:
    $0 enable        # Enable context watcher to run on boot
    $0 start         # Start watcher now
    $0 status        # Check if watcher is running
    $0 logs          # View recent watcher logs

EOF
}

case "${1:-}" in
    enable)
        echo "Installing systemd service file..."
        mkdir -p ~/.config/systemd/user

        # Create symlink (remove existing file/link first)
        rm -f ~/.config/systemd/user/context-watcher.service
        ln -s "${SCRIPT_DIR}/systemd/context-watcher.service" ~/.config/systemd/user/
        echo "✓ Symlink created in ~/.config/systemd/user/"

        echo "Reloading systemd daemon..."
        systemctl --user daemon-reload

        echo "Enabling context-watcher service..."
        systemctl --user enable context-watcher.service
        systemctl --user start context-watcher.service
        echo "✓ Service enabled and started"
        echo ""
        systemctl --user status context-watcher.service --no-pager
        ;;

    disable)
        echo "Disabling context-watcher service..."
        systemctl --user stop context-watcher.service
        systemctl --user disable context-watcher.service
        echo "✓ Service disabled and stopped"
        ;;

    start)
        echo "Starting context-watcher service..."
        systemctl --user start context-watcher.service
        echo "✓ Service started"
        echo ""
        echo "View logs with: $0 logs-follow"
        ;;

    stop)
        echo "Stopping context-watcher service..."
        systemctl --user stop context-watcher.service
        echo "✓ Service stopped"
        ;;

    restart)
        echo "Restarting context-watcher service..."
        systemctl --user restart context-watcher.service
        echo "✓ Service restarted"
        echo ""
        systemctl --user status context-watcher.service --no-pager
        ;;

    status)
        echo "=== Service Status ==="
        systemctl --user status context-watcher.service --no-pager || true
        echo ""
        echo "=== Lock File ==="
        if [ -f /tmp/context-watcher.lock ]; then
            echo "Lock file exists: /tmp/context-watcher.lock"
            echo "PID: $(cat /tmp/context-watcher.lock)"
        else
            echo "No lock file found"
        fi
        echo ""
        echo "=== Configuration ==="
        if [ -f ~/.config/context-watcher/config.yaml ]; then
            echo "Config file: ~/.config/context-watcher/config.yaml"
            echo "Permissions: $(stat -c '%a' ~/.config/context-watcher/config.yaml 2>/dev/null || stat -f '%A' ~/.config/context-watcher/config.yaml 2>/dev/null)"
        else
            echo "⚠ No config file found - run ./setup.sh first"
        fi
        echo ""
        echo "=== State File ==="
        if [ -f ~/.config/context-watcher/watcher-state.json ]; then
            echo "State file: ~/.config/context-watcher/watcher-state.json"
            cat ~/.config/context-watcher/watcher-state.json | jq '.' 2>/dev/null || cat ~/.config/context-watcher/watcher-state.json
        else
            echo "No state file found (will be created on first run)"
        fi
        ;;

    logs)
        echo "=== Recent Watcher Logs ==="
        journalctl --user -u context-watcher.service -n 100 --no-pager
        ;;

    logs-follow)
        echo "=== Following Watcher Logs (Ctrl+C to stop) ==="
        journalctl --user -u context-watcher.service -f
        ;;

    *)
        show_usage
        exit 1
        ;;
esac
