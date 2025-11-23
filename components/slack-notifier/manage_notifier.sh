#!/bin/bash
# Manage Slack notifier systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="slack-notifier"
NOTIFIER_CTL="${SCRIPT_DIR}/../bin/host-notify-ctl"

show_usage() {
    cat <<EOF
Usage: $0 <command>

Commands:
    enable      Enable and start the Slack notifier service
    disable     Disable and stop the service
    start       Start the notifier (if not already running)
    stop        Stop the notifier
    restart     Restart the notifier
    status      Show service status
    logs        Show recent logs
    logs-follow Follow logs in real-time
    setup       Interactive setup (configure Slack token)

Examples:
    $0 setup         # First time: configure Slack token
    $0 enable        # Enable notifier to run on boot
    $0 start         # Start notifier now
    $0 status        # Check if notifier is running
    $0 logs          # View recent logs

EOF
}

case "${1:-}" in
    enable)
        echo "Installing systemd service file..."
        mkdir -p ~/.config/systemd/user

        # Create symlink (remove existing file/link first)
        rm -f ~/.config/systemd/user/jib-notifier.service
        ln -s "${SCRIPT_DIR}/systemd/jib-notifier.service" ~/.config/systemd/user/
        echo "✓ Symlink created in ~/.config/systemd/user/"

        echo "Reloading systemd daemon..."
        systemctl --user daemon-reload

        echo "Enabling slack-notifier service..."
        systemctl --user enable slack-notifier.service
        systemctl --user start slack-notifier.service
        echo "✓ Service enabled and started"
        echo ""
        systemctl --user status slack-notifier.service --no-pager
        ;;

    disable)
        echo "Disabling slack-notifier service..."
        systemctl --user stop slack-notifier.service
        systemctl --user disable slack-notifier.service
        echo "✓ Service disabled and stopped"
        ;;

    start)
        echo "Starting slack-notifier service..."
        systemctl --user start slack-notifier.service
        echo "✓ Service started"
        echo ""
        echo "View logs with: $0 logs-follow"
        ;;

    stop)
        echo "Stopping slack-notifier service..."
        systemctl --user stop slack-notifier.service
        echo "✓ Service stopped"
        ;;

    restart)
        echo "Restarting slack-notifier service..."
        systemctl --user restart slack-notifier.service
        echo "✓ Service restarted"
        echo ""
        systemctl --user status slack-notifier.service --no-pager
        ;;

    status)
        echo "=== Service Status ==="
        systemctl --user status slack-notifier.service --no-pager || true
        echo ""
        echo "=== Configuration ==="
        if [ -f ~/.config/jib-notifier/config.json ]; then
            echo "Config file: ~/.config/jib-notifier/config.json"
            echo "Permissions: $(stat -c '%a' ~/.config/jib-notifier/config.json 2>/dev/null || stat -f '%A' ~/.config/jib-notifier/config.json 2>/dev/null)"
        else
            echo "⚠ No config file found - run: $0 setup"
        fi
        ;;

    logs)
        echo "=== Recent Notifier Logs ==="
        journalctl --user -u slack-notifier.service -n 100 --no-pager
        ;;

    logs-follow)
        echo "=== Following Notifier Logs (Ctrl+C to stop) ==="
        journalctl --user -u slack-notifier.service -f
        ;;

    setup)
        # Use the control script for setup
        "$NOTIFIER_CTL" setup
        ;;

    *)
        show_usage
        exit 1
        ;;
esac
