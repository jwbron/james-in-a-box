#!/bin/bash
# Control script for Slack notifier service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTIFIER_SCRIPT="${SCRIPT_DIR}/host-notify-slack.py"
LOCK_FILE="/tmp/slack-notifier.lock"
CONFIG_DIR="${HOME}/.config/slack-notifier"
LOG_FILE="${CONFIG_DIR}/notifier.log"

show_usage() {
    cat <<EOF
Usage: $0 <command>

Commands:
    start       Start the Slack notifier
    stop        Stop the Slack notifier
    restart     Restart the Slack notifier
    status      Show notifier status
    logs        Show recent logs
    tail        Follow logs in real-time
    setup       Interactive setup

Examples:
    $0 start         # Start the notifier
    $0 status        # Check if running
    $0 logs          # View recent logs

EOF
}

get_pid() {
    if [ -f "$LOCK_FILE" ]; then
        cat "$LOCK_FILE"
    fi
}

is_running() {
    local pid=$(get_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

case "${1:-}" in
    start)
        if is_running; then
            echo "⚠ Notifier is already running (PID: $(get_pid))"
            exit 0
        fi

        # Check if config exists
        if [ ! -f "${CONFIG_DIR}/config.json" ]; then
            echo "⚠ No configuration found. Running setup..."
            "$0" setup
        fi

        echo "Starting Slack notifier..."

        # Start the notifier in the background
        nohup python3 "$NOTIFIER_SCRIPT" >> "$LOG_FILE" 2>&1 &
        local pid=$!

        # Save PID
        echo $pid > "$LOCK_FILE"

        # Wait a moment to check if it started successfully
        sleep 2
        if is_running; then
            echo "✓ Notifier started (PID: $pid)"
            echo "  View logs: $0 tail"
        else
            echo "✗ Failed to start notifier"
            echo "  Check logs: $0 logs"
            exit 1
        fi
        ;;

    stop)
        if ! is_running; then
            echo "⚠ Notifier is not running"
            rm -f "$LOCK_FILE"
            exit 0
        fi

        local pid=$(get_pid)
        echo "Stopping Slack notifier (PID: $pid)..."

        kill "$pid" 2>/dev/null || true

        # Wait for process to stop
        local count=0
        while kill -0 "$pid" 2>/dev/null && [ $count -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done

        if kill -0 "$pid" 2>/dev/null; then
            echo "⚠ Process did not stop gracefully, forcing..."
            kill -9 "$pid" 2>/dev/null || true
        fi

        rm -f "$LOCK_FILE"
        echo "✓ Notifier stopped"
        ;;

    restart)
        "$0" stop
        sleep 2
        "$0" start
        ;;

    status)
        echo "=== Slack Notifier Status ==="
        if is_running; then
            local pid=$(get_pid)
            echo "✓ Notifier is running (PID: $pid)"
            echo ""
            echo "Process info:"
            ps -p "$pid" -o pid,vsz,rss,etime,cmd --no-headers 2>/dev/null || echo "  (process info unavailable)"
        else
            echo "✗ Notifier is not running"
            if [ -f "$LOCK_FILE" ]; then
                echo "  (stale lock file found: $LOCK_FILE)"
            fi
        fi

        echo ""
        echo "=== Configuration ==="
        if [ -f "${CONFIG_DIR}/config.json" ]; then
            echo "Config file: ${CONFIG_DIR}/config.json"
            echo "Permissions: $(stat -c '%a' "${CONFIG_DIR}/config.json" 2>/dev/null || stat -f '%A' "${CONFIG_DIR}/config.json" 2>/dev/null)"
            echo ""
            echo "Watched directories:"
            python3 -c "import json; config=json.load(open('${CONFIG_DIR}/config.json')); print('\\n'.join('  - ' + d for d in config.get('watch_directories', [])))" 2>/dev/null || echo "  (unable to read config)"
        else
            echo "⚠ No config file found"
            echo "  Run: $0 setup"
        fi

        echo ""
        echo "=== Recent Activity ==="
        if [ -f "$LOG_FILE" ]; then
            tail -5 "$LOG_FILE" | sed 's/^/  /'
        else
            echo "  No log file yet"
        fi
        ;;

    logs)
        if [ -f "$LOG_FILE" ]; then
            tail -50 "$LOG_FILE"
        else
            echo "No log file found at: $LOG_FILE"
        fi
        ;;

    tail)
        if [ -f "$LOG_FILE" ]; then
            echo "Following logs (Ctrl+C to stop)..."
            tail -f "$LOG_FILE"
        else
            echo "No log file found at: $LOG_FILE"
            exit 1
        fi
        ;;

    setup)
        echo "=== Slack Notifier Setup ==="
        echo ""

        # Create config directory
        mkdir -p "$CONFIG_DIR"
        chmod 700 "$CONFIG_DIR"

        # Get Slack token
        if [ -n "$SLACK_TOKEN" ]; then
            echo "Using SLACK_TOKEN from environment"
            token="$SLACK_TOKEN"
        else
            echo "Enter your Slack Bot token (starts with xoxb-):"
            echo "(Get from: https://api.slack.com/apps)"
            read -r token
        fi

        if [ -z "$token" ]; then
            echo "Error: No token provided"
            exit 1
        fi

        # Get Slack channel
        echo ""
        echo "Enter Slack channel/DM ID [D04CMDR7LBT]:"
        read -r channel
        channel=${channel:-"D04CMDR7LBT"}

        # Create config
        cat > "${CONFIG_DIR}/config.json" <<EOF
{
  "slack_token": "$token",
  "slack_channel": "$channel",
  "batch_window_seconds": 30,
  "watch_directories": [
    "$HOME/.claude-sandbox-sharing",
    "$HOME/.claude-sandbox-tools"
  ]
}
EOF
        chmod 600 "${CONFIG_DIR}/config.json"

        echo ""
        echo "✓ Configuration saved to: ${CONFIG_DIR}/config.json"
        echo "  Permissions: 600 (secure)"
        echo ""
        echo "Next steps:"
        echo "  1. Review config: cat ${CONFIG_DIR}/config.json"
        echo "  2. Start notifier: $0 start"
        echo "  3. Test: echo 'test' > ~/.claude-sandbox-sharing/test.txt"
        ;;

    *)
        show_usage
        exit 1
        ;;
esac
