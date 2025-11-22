#!/bin/bash
# Control script for Slack receiver

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECEIVER_SCRIPT="${SCRIPT_DIR}/host-receive-slack.py"
PID_FILE="${HOME}/.config/jib-notifier/receiver.pid"
LOG_FILE="${HOME}/.config/jib-notifier/receiver.log"
CONFIG_FILE="${HOME}/.config/jib-notifier/config.json"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_python_deps() {
    if ! python3 -c "import slack_sdk" 2>/dev/null; then
        echo -e "${RED}Error: slack_sdk not installed${NC}"
        echo "Install with: pip install slack-sdk"
        return 1
    fi
    return 0
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            # Stale PID file
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        cat "$PID_FILE"
    fi
}

start() {
    if is_running; then
        echo -e "${YELLOW}✓ Receiver already running (PID: $(get_pid))${NC}"
        return 0
    fi

    # Check dependencies
    if ! check_python_deps; then
        return 1
    fi

    # Check config
    if [ ! -f "$CONFIG_FILE" ]; then
        echo -e "${YELLOW}⚠ Config not found. Run 'setup' first or set SLACK_TOKEN and SLACK_APP_TOKEN${NC}"
        return 1
    fi

    echo "Starting Slack receiver..."
    nohup python3 "$RECEIVER_SCRIPT" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    sleep 1

    if is_running; then
        echo -e "${GREEN}✓ Receiver started (PID: $pid)${NC}"
        echo "  Logs: $LOG_FILE"
        return 0
    else
        echo -e "${RED}✗ Failed to start receiver${NC}"
        echo "  Check logs: $LOG_FILE"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop() {
    if ! is_running; then
        echo -e "${YELLOW}✓ Receiver not running${NC}"
        return 0
    fi

    local pid=$(get_pid)
    echo "Stopping receiver (PID: $pid)..."

    kill "$pid" 2>/dev/null

    # Wait for graceful shutdown
    local count=0
    while is_running && [ $count -lt 10 ]; do
        sleep 1
        ((count++))
    done

    if is_running; then
        echo -e "${YELLOW}⚠ Graceful shutdown failed, forcing...${NC}"
        kill -9 "$pid" 2>/dev/null
        sleep 1
    fi

    rm -f "$PID_FILE"
    echo -e "${GREEN}✓ Receiver stopped${NC}"
}

status() {
    if is_running; then
        local pid=$(get_pid)
        echo -e "${GREEN}✓ Receiver is running (PID: $pid)${NC}"

        # Show config
        if [ -f "$CONFIG_FILE" ]; then
            echo ""
            echo "Configuration:"
            echo "  Config file: $CONFIG_FILE"
            echo "  Log file: $LOG_FILE"

            # Parse config
            if command -v jq > /dev/null 2>&1; then
                local incoming=$(jq -r '.incoming_directory // "~/.jib-sharing/incoming"' "$CONFIG_FILE")
                local responses=$(jq -r '.responses_directory // "~/.jib-sharing/responses"' "$CONFIG_FILE")
                local self_dm=$(jq -r '.self_dm_channel // ""' "$CONFIG_FILE")
                local owner_id=$(jq -r '.owner_user_id // ""' "$CONFIG_FILE")
                local allowed=$(jq -r '.allowed_users // [] | join(", ")' "$CONFIG_FILE")

                echo "  Incoming dir: $incoming"
                echo "  Responses dir: $responses"
                if [ -n "$self_dm" ]; then
                    echo "  Self-DM channel: $self_dm"
                fi
                if [ -n "$owner_id" ]; then
                    echo "  Owner user ID: $owner_id"
                fi
                if [ -n "$allowed" ]; then
                    echo "  Allowed users: $allowed"
                else
                    echo "  Allowed users: All (no whitelist)"
                fi
            fi
        fi

        return 0
    else
        echo -e "${RED}✗ Receiver is not running${NC}"
        return 1
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -n 50 "$LOG_FILE"
    else
        echo "No log file found: $LOG_FILE"
    fi
}

tail_logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file found: $LOG_FILE"
        echo "Start the receiver first."
    fi
}

setup() {
    echo "=== Slack Receiver Setup ==="
    echo ""

    mkdir -p "$(dirname "$CONFIG_FILE")"

    # Get tokens
    read -p "Slack Bot Token (SLACK_TOKEN, starts with xoxb-): " slack_token
    read -p "Slack App Token (SLACK_APP_TOKEN, starts with xapp-): " slack_app_token

    # Get self-DM channel and user ID
    echo ""
    echo "Your Slack workspace information:"
    echo "Example: Self-DM URL: https://workspace.slack.com/archives/D07S8SAB5FE"
    echo "         Profile URL: https://workspace.slack.com/team/U07SK26JPJ5"
    read -p "Your self-DM channel ID (e.g., D07S8SAB5FE): " self_dm_channel
    read -p "Your Slack user ID (e.g., U07SK26JPJ5): " owner_user_id

    # Optional: allowed users
    echo ""
    echo "Allowed users (optional - leave empty to allow all):"
    echo "Enter Slack user IDs separated by commas (e.g., U01234,U56789)"
    read -p "Allowed users: " allowed_users_input

    # Parse allowed users
    if [ -n "$allowed_users_input" ]; then
        allowed_users=$(echo "$allowed_users_input" | python3 -c "import sys, json; print(json.dumps([u.strip() for u in sys.stdin.read().split(',')]))")
    else
        allowed_users="[]"
    fi

    # Create config
    cat > "$CONFIG_FILE" << EOF
{
  "slack_token": "$slack_token",
  "slack_app_token": "$slack_app_token",
  "allowed_users": $allowed_users,
  "self_dm_channel": "$self_dm_channel",
  "owner_user_id": "$owner_user_id",
  "incoming_directory": "~/.jib-sharing/incoming",
  "responses_directory": "~/.jib-sharing/responses"
}
EOF

    chmod 600 "$CONFIG_FILE"

    echo ""
    echo -e "${GREEN}✓ Configuration saved to: $CONFIG_FILE${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Ensure your Slack app has Socket Mode enabled"
    echo "  2. Start the receiver: $0 start"
    echo "  3. Send a test DM to your bot"
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
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
    setup)
        setup
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|tail|setup}"
        echo ""
        echo "Commands:"
        echo "  start    - Start the Slack receiver"
        echo "  stop     - Stop the Slack receiver"
        echo "  restart  - Restart the Slack receiver"
        echo "  status   - Show receiver status and configuration"
        echo "  logs     - View recent logs"
        echo "  tail     - Follow logs in real-time"
        echo "  setup    - Interactive configuration setup"
        exit 1
        ;;
esac
