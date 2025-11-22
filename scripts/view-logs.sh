#!/bin/bash
# View Claude container logs from the host

SHARING_DIR="${HOME}/.claude-sandbox-sharing"
TRACKING_DIR="${SHARING_DIR}/tracking"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

show_help() {
    echo "View Claude container logs"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  incoming    - View incoming-watcher logs (Slack message processing)"
    echo "  claude      - View Claude task execution logs"
    echo "  context     - View context-watcher logs"
    echo "  all         - View all logs"
    echo "  tail        - Tail all logs in real-time"
    echo "  list        - List all available log files"
    echo ""
    echo "Examples:"
    echo "  $0 incoming       # View incoming message logs"
    echo "  $0 tail           # Follow all logs in real-time"
}

list_logs() {
    echo -e "${GREEN}=== Available Logs ===${NC}"
    echo ""
    if [ -d "$TRACKING_DIR" ]; then
        ls -lh "$TRACKING_DIR"/*.log 2>/dev/null || echo "No log files found"
    else
        echo "Tracking directory not found: $TRACKING_DIR"
        echo "Is the container running?"
    fi
}

view_incoming() {
    local log_file="$TRACKING_DIR/incoming-watcher.log"
    if [ -f "$log_file" ]; then
        echo -e "${BLUE}=== Incoming Message Watcher Logs ===${NC}"
        tail -n 50 "$log_file"
    else
        echo "Log file not found: $log_file"
    fi
}

view_claude() {
    local log_file="$TRACKING_DIR/claude-tasks.log"
    if [ -f "$log_file" ]; then
        echo -e "${BLUE}=== Claude Task Execution Logs ===${NC}"
        tail -n 50 "$log_file"
    else
        echo "Log file not found: $log_file"
    fi
}

view_context() {
    local log_file="$TRACKING_DIR/watcher.log"
    if [ -f "$log_file" ]; then
        echo -e "${BLUE}=== Context Watcher Logs ===${NC}"
        tail -n 50 "$log_file"
    else
        echo "Log file not found: $log_file"
    fi
}

view_all() {
    view_incoming
    echo ""
    view_claude
    echo ""
    view_context
}

tail_all() {
    echo -e "${BLUE}=== Tailing All Logs (Ctrl+C to stop) ===${NC}"
    echo ""

    if [ -d "$TRACKING_DIR" ]; then
        tail -f "$TRACKING_DIR"/*.log 2>/dev/null
    else
        echo "Tracking directory not found: $TRACKING_DIR"
        echo "Is the container running?"
    fi
}

case "${1:-}" in
    incoming)
        view_incoming
        ;;
    claude)
        view_claude
        ;;
    context)
        view_context
        ;;
    all)
        view_all
        ;;
    tail)
        tail_all
        ;;
    list)
        list_logs
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -z "$1" ]; then
            view_all
        else
            echo "Unknown command: $1"
            echo ""
            show_help
            exit 1
        fi
        ;;
esac
