#!/bin/bash
# Host Slack Notifier Control Script
# Manage the host-side Slack notification service

set -euo pipefail

NOTIFIER_SCRIPT="${HOME}/khan/cursor-sandboxed/scripts/host-notify-slack.sh"
LOCK_FILE="/tmp/claude-notify.lock"
LOG_FILE="${HOME}/.claude-sandbox-notify/notify.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    cat << EOF
Usage: $0 {start|stop|restart|status|logs|tail}

Commands:
  start    - Start the Slack notifier in the background
  stop     - Stop the Slack notifier
  restart  - Restart the Slack notifier
  status   - Check if the notifier is running
  logs     - View the notifier log file
  tail     - Tail the notifier log file

Environment Variables:
  SLACK_TOKEN  - Your Slack bot token (required)

Example:
  export SLACK_TOKEN=xoxb-your-token-here
  $0 start

EOF
    exit 1
}

start() {
    if [ -z "${SLACK_TOKEN:-}" ]; then
        echo -e "${RED}Error:${NC} SLACK_TOKEN environment variable not set"
        echo "Please set your Slack bot token:"
        echo "  export SLACK_TOKEN=xoxb-your-token-here"
        echo ""
        echo "To get a Slack bot token:"
        echo "  1. Go to https://api.slack.com/apps"
        echo "  2. Create a new app or select existing"
        echo "  3. Go to 'OAuth & Permissions'"
        echo "  4. Add bot token scopes: chat:write, channels:history"
        echo "  5. Install app to workspace"
        echo "  6. Copy the 'Bot User OAuth Token'"
        exit 1
    fi

    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "${YELLOW}Notifier is already running${NC} (PID: $PID)"
            return 1
        else
            echo "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi

    echo -e "${GREEN}Starting${NC} Slack notifier..."

    # Export SLACK_TOKEN for the child process
    export SLACK_TOKEN

    nohup "$NOTIFIER_SCRIPT" > /dev/null 2>&1 &
    sleep 2

    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        echo -e "${GREEN}✓${NC} Notifier started (PID: $PID)"
        echo "Logs: $LOG_FILE"
        return 0
    else
        echo -e "${RED}✗${NC} Failed to start notifier"
        echo "Check logs: $LOG_FILE"
        return 1
    fi
}

stop() {
    if [ ! -f "$LOCK_FILE" ]; then
        echo -e "${YELLOW}Notifier is not running${NC}"
        return 1
    fi

    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${YELLOW}Stopping${NC} notifier (PID: $PID)..."
        kill "$PID"
        sleep 1

        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing..."
            kill -9 "$PID"
        fi

        rm -f "$LOCK_FILE"
        echo -e "${GREEN}✓${NC} Notifier stopped"
    else
        echo -e "${YELLOW}Notifier is not running${NC} (stale lock file)"
        rm -f "$LOCK_FILE"
    fi
}

status() {
    if [ ! -f "$LOCK_FILE" ]; then
        echo -e "${RED}✗${NC} Notifier is NOT running"
        return 1
    fi

    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Notifier is running (PID: $PID)"
        echo "Log file: $LOG_FILE"

        # Show recent activity
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "Recent activity:"
            tail -5 "$LOG_FILE"
        fi
        return 0
    else
        echo -e "${RED}✗${NC} Notifier is NOT running (stale lock file)"
        rm -f "$LOCK_FILE"
        return 1
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        less "$LOG_FILE"
    else
        echo "No log file found at $LOG_FILE"
        return 1
    fi
}

tail_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file found at $LOG_FILE"
        echo "Waiting for log file to be created..."
        mkdir -p "$(dirname "$LOG_FILE")"
        touch "$LOG_FILE"
        tail -f "$LOG_FILE"
    fi
}

# Main command handling
case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop || true
        sleep 1
        start
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    tail)
        tail_logs
        ;;
    *)
        usage
        ;;
esac
