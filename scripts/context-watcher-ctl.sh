#!/bin/bash
# Context Watcher Control Script
# Start, stop, and manage the context watcher service

set -euo pipefail

WATCHER_SCRIPT="${HOME}/khan/cursor-sandboxed/scripts/context-watcher.sh"
LOCK_FILE="/tmp/context-watcher.lock"
LOG_FILE="${HOME}/sharing/context-tracking/watcher.log"

usage() {
    cat << EOF
Usage: $0 {start|stop|restart|status|logs|tail}

Commands:
  start    - Start the context watcher in the background
  stop     - Stop the context watcher
  restart  - Restart the context watcher
  status   - Check if the watcher is running
  logs     - View the watcher log file
  tail     - Tail the watcher log file

EOF
    exit 1
}

start() {
    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo "Context watcher is already running (PID: $PID)"
            return 1
        else
            echo "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi

    echo "Starting context watcher..."
    nohup "$WATCHER_SCRIPT" > /dev/null 2>&1 &
    sleep 1

    if [ -f "$LOCK_FILE" ]; then
        PID=$(cat "$LOCK_FILE")
        echo "Context watcher started (PID: $PID)"
        echo "Logs: $LOG_FILE"
        return 0
    else
        echo "Failed to start context watcher"
        return 1
    fi
}

stop() {
    if [ ! -f "$LOCK_FILE" ]; then
        echo "Context watcher is not running"
        return 1
    fi

    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping context watcher (PID: $PID)..."
        kill "$PID"
        sleep 1

        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing..."
            kill -9 "$PID"
        fi

        rm -f "$LOCK_FILE"
        echo "Context watcher stopped"
    else
        echo "Context watcher is not running (stale lock file)"
        rm -f "$LOCK_FILE"
    fi
}

status() {
    if [ ! -f "$LOCK_FILE" ]; then
        echo "Context watcher is NOT running"
        return 1
    fi

    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Context watcher is running (PID: $PID)"
        echo "Log file: $LOG_FILE"

        # Show recent activity
        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "Recent activity:"
            tail -5 "$LOG_FILE"
        fi
        return 0
    else
        echo "Context watcher is NOT running (stale lock file)"
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
        stop
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
