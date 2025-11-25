#!/bin/bash
# Host-side Slack Notification Script
# Watches shared directories and sends Slack DMs when changes occur

set -euo pipefail

# Configuration
SLACK_TOKEN="${SLACK_TOKEN:-}"
# SECURITY FIX: Use environment variable for channel ID instead of hardcoding
SLACK_CHANNEL="${SLACK_CHANNEL:-}"

WATCH_DIRS=(
    "${HOME}/.jib-sharing"
)

# State and logging
STATE_DIR="${HOME}/.jib-notify"
STATE_FILE="${STATE_DIR}/notify-state.json"
LOG_FILE="${STATE_DIR}/notify.log"
# SECURITY FIX: Use user-controlled directory instead of /tmp to prevent race conditions
LOCK_FILE="${STATE_DIR}/notify.lock"

# Notification batching
BATCH_WINDOW=30  # seconds to batch changes before notifying
LAST_NOTIFY=0

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "$LOG_FILE" >&2
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${GREEN}[INFO]${NC} $*" | tee -a "$LOG_FILE"
}

check_dependencies() {
    if ! command -v inotifywait &> /dev/null; then
        error "inotifywait not found. Please install inotify-tools:"
        error "  sudo dnf install inotify-tools  # Fedora"
        error "  sudo apt install inotify-tools  # Ubuntu/Debian"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        error "jq not found. Please install jq:"
        error "  sudo dnf install jq  # Fedora"
        error "  sudo apt install jq  # Ubuntu/Debian"
        exit 1
    fi

    if [ -z "$SLACK_TOKEN" ]; then
        error "SLACK_TOKEN environment variable not set"
        error "Please set it to your Slack bot token:"
        error "  export SLACK_TOKEN=xoxb-your-token-here"
        error ""
        error "For secure storage, use:"
        error "  mkdir -p ~/.config/jib-notifier"
        error "  echo 'xoxb-your-token-here' > ~/.config/jib-notifier/slack-token"
        error "  chmod 600 ~/.config/jib-notifier/slack-token"
        error "  export SLACK_TOKEN=\$(cat ~/.config/jib-notifier/slack-token)"
        exit 1
    fi

    # SECURITY FIX: Require SLACK_CHANNEL to be set
    if [ -z "$SLACK_CHANNEL" ]; then
        error "SLACK_CHANNEL environment variable not set"
        error "Please set it to your Slack channel/DM ID:"
        error "  export SLACK_CHANNEL=D04CMDR7LBT  # Your DM channel ID"
        error ""
        error "To find your DM channel ID:"
        error "  1. Open Slack in browser"
        error "  2. Navigate to your DM with the bot"
        error "  3. Copy the ID from the URL: https://workspace.slack.com/archives/<CHANNEL_ID>"
        exit 1
    fi
}

setup_dirs() {
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"

    # Initialize state file if it doesn't exist
    if [ ! -f "$STATE_FILE" ]; then
        echo '{"last_notify": 0, "pending_changes": []}' > "$STATE_FILE"
    fi
}

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local pid
        pid=$(cat "$LOCK_FILE")
        # Validate PID is numeric and process exists
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            error "Another instance is already running (PID: $pid)"
            exit 1
        else
            warn "Removing stale lock file"
            rm -f "$LOCK_FILE"
        fi
    fi

    echo $$ > "$LOCK_FILE"
}

release_lock() {
    rm -f "$LOCK_FILE"
}

send_slack_message() {
    local message="$1"

    # Escape message for JSON
    local json_message
    json_message=$(jq -n --arg msg "$message" --arg channel "$SLACK_CHANNEL" '{
        channel: $channel,
        text: $msg
    }')

    local response
    response=$(curl -s -X POST https://slack.com/api/chat.postMessage \
        -H "Authorization: Bearer $SLACK_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$json_message")

    local ok
    ok=$(echo "$response" | jq -r '.ok')

    if [ "$ok" != "true" ]; then
        local error_msg
        error_msg=$(echo "$response" | jq -r '.error')
        error "Failed to send Slack message: $error_msg"
        return 1
    fi

    return 0
}

format_change_message() {
    local changes=("$@")
    local message

    message="🔔 *Claude Sandbox Changes Detected*\n\n"

    # Group changes by directory
    local sharing_changes=()

    for change in "${changes[@]}"; do
        if [[ "$change" == *".jib-sharing"* ]]; then
            sharing_changes+=("$change")
        fi
    done

    if [ ${#sharing_changes[@]} -gt 0 ]; then
        message+="*Sharing Directory* (\`~/.jib-sharing/\`):\n"
        for change in "${sharing_changes[@]}"; do
            # Extract relative path
            local rel_path="${change#*/.jib-sharing/}"
            message+="  • \`$rel_path\`\n"
        done
        message+="\n"
    fi

    message+="_Total changes: ${#changes[@]}_"

    echo -e "$message"
}

notify_changes() {
    local changes=("$@")

    if [ ${#changes[@]} -eq 0 ]; then
        return 0
    fi

    info "Sending notification for ${#changes[@]} change(s)"

    local message
    message=$(format_change_message "${changes[@]}")

    if send_slack_message "$message"; then
        info "Notification sent successfully"
    else
        error "Failed to send notification"
        return 1
    fi
}

watch_directories() {
    local pending_changes=()
    local last_batch_time=$(date +%s)

    info "Starting to watch directories..."
    for dir in "${WATCH_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            info "  - $dir"
        else
            warn "  - $dir (does not exist yet)"
        fi
    done

    # Build inotifywait command with all directories
    local watch_args=()
    for dir in "${WATCH_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            watch_args+=("$dir")
        fi
    done

    if [ ${#watch_args[@]} -eq 0 ]; then
        error "No directories to watch!"
        exit 1
    fi

    # Watch for file changes
    inotifywait -m -r -e modify,create,delete,move \
        --format '%w%f' \
        "${watch_args[@]}" 2>/dev/null | while read -r file; do

        local current_time=$(date +%s)

        # Skip temporary files and lock files
        if [[ "$file" =~ \.(swp|tmp|lock)$ ]] || [[ "$file" =~ /\.git/ ]]; then
            continue
        fi

        # Add to pending changes
        pending_changes+=("$file")
        log "Change detected: $file"

        # Check if we should send notification
        local time_since_last=$((current_time - last_batch_time))

        if [ $time_since_last -ge $BATCH_WINDOW ]; then
            # Send notification with all pending changes
            if [ ${#pending_changes[@]} -gt 0 ]; then
                notify_changes "${pending_changes[@]}"
                pending_changes=()
                last_batch_time=$current_time
            fi
        fi
    done
}

cleanup() {
    info "Shutting down..."
    release_lock
    exit 0
}

main() {
    log "Host Slack Notifier starting..."

    # Setup
    check_dependencies
    setup_dirs
    acquire_lock

    # Trap signals for cleanup
    trap cleanup SIGINT SIGTERM

    # Start watching
    info "Monitoring shared directories for changes..."
    info "Batch window: ${BATCH_WINDOW}s"
    info "Slack channel: $SLACK_CHANNEL"

    watch_directories
}

# Run main function
main
