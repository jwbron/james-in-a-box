#!/bin/bash
#
# Incoming Message Watcher
#
# Runs INSIDE the Docker container. Monitors ~/sharing/incoming/ and ~/sharing/responses/
# for messages from the host Slack receiver. When a message arrives:
# - For tasks: Triggers Claude with the task content
# - For responses: Makes the response available to Claude
#
# This completes the bidirectional communication:
# Host Slack → host-receive-slack.py → ~/sharing/incoming/ → THIS SCRIPT → Claude
#

set -euo pipefail

# Configuration
INCOMING_DIR="${HOME}/sharing/incoming"
RESPONSES_DIR="${HOME}/sharing/responses"
STATE_DIR="${HOME}/sharing/tracking"
STATE_FILE="${STATE_DIR}/incoming-watcher.state"
LOG_FILE="${STATE_DIR}/incoming-watcher.log"

# Ensure directories exist
mkdir -p "$INCOMING_DIR" "$RESPONSES_DIR" "$STATE_DIR"

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] $*" | tee -a "$LOG_FILE"
}

# Initialize state
if [ ! -f "$STATE_FILE" ]; then
    echo "{}" > "$STATE_FILE"
fi

# Function to check if file has been processed
is_processed() {
    local file="$1"
    local filename=$(basename "$file")
    grep -q "\"${filename}\"" "$STATE_FILE" 2>/dev/null
}

# Mark file as processed
mark_processed() {
    local file="$1"
    local filename=$(basename "$file")
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Add to state file (simple JSON append)
    python3 - <<EOF
import json
state_file = "${STATE_FILE}"
try:
    with open(state_file, 'r') as f:
        state = json.load(f)
except:
    state = {}

state["${filename}"] = {
    "processed_at": "${timestamp}",
    "path": "${file}"
}

with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
EOF
}

# Process a new task
process_task() {
    local file="$1"
    local filename=$(basename "$file")

    log "📋 New task received: $filename"

    # Read task content
    local content=$(cat "$file")

    # Extract task description (after "## Message" header)
    local task_content=$(sed -n '/## Message/,/---/p' "$file" | sed '1d;$d' | sed '/^$/d')

    if [ -z "$task_content" ]; then
        log "⚠️ Empty task content in $filename"
        return 1
    fi

    log "Task: ${task_content:0:100}..."

    # Notify user via shared notifications (creates feedback loop)
    local notify_file="${HOME}/sharing/notifications/$(date +%Y%m%d-%H%M%S)-task-received.md"
    cat > "$notify_file" <<EOF
# 🎯 Task Received from Slack

**File:** \`$filename\`
**Time:** $(date '+%Y-%m-%d %H:%M:%S')

## Task Description

$task_content

---

**Status:** Acknowledged and ready to begin
**Next:** Claude will process this task

---
📨 *Delivered via Slack → incoming/ → Claude*
EOF

    log "✅ Task acknowledged: $notify_file"

    # TODO: In future, could automatically trigger Claude here
    # For now, Claude will pick this up when user starts conversation

    mark_processed "$file"
}

# Process a response to Claude's notification
process_response() {
    local file="$1"
    local filename=$(basename "$file")

    log "💬 Response received: $filename"

    # Read response content
    local content=$(cat "$file")

    # Check if it references a specific notification
    local referenced_notif=$(grep "Re:.*Notification" "$file" | sed -n 's/.*`\([^`]*\)`.*/\1/p')

    if [ -n "$referenced_notif" ]; then
        log "Response references: $referenced_notif"

        # Create a clearly labeled response file next to the original notification
        local response_link="${HOME}/sharing/notifications/RESPONSE-${referenced_notif}.md"
        cp "$file" "$response_link"
        log "✅ Response linked to notification: $response_link"
    else
        log "⚠️ Response does not reference specific notification"
    fi

    # Notify that response was received
    local notify_file="${HOME}/sharing/notifications/$(date +%Y%m%d-%H%M%S)-response-received.md"
    cat > "$notify_file" <<EOF
# 💬 Response Received from Slack

**File:** \`$filename\`
**Time:** $(date '+%Y-%m-%d %H:%M:%S')
$([ -n "$referenced_notif" ] && echo "**Re:** \`$referenced_notif\`")

## Response Content

$(sed -n '/## Message/,/---/p' "$file" | sed '1d;$d' | sed '/^$/d')

---

**Status:** Response available for review
**Location:** \`responses/$filename\`
$([ -n "$referenced_notif" ] && echo "**Linked:** \`notifications/RESPONSE-${referenced_notif}.md\`")

---
📨 *Delivered via Slack → responses/ → Claude*
EOF

    log "✅ Response processed: $notify_file"

    mark_processed "$file"
}

# Watch for new files
watch_directories() {
    log "👀 Starting incoming message watcher"
    log "Monitoring:"
    log "  - $INCOMING_DIR (new tasks)"
    log "  - $RESPONSES_DIR (responses to notifications)"

    while true; do
        # Check for new tasks
        if [ -d "$INCOMING_DIR" ]; then
            for file in "$INCOMING_DIR"/*.md; do
                [ -f "$file" ] || continue

                if ! is_processed "$file"; then
                    process_task "$file"
                fi
            done
        fi

        # Check for new responses
        if [ -d "$RESPONSES_DIR" ]; then
            for file in "$RESPONSES_DIR"/*.md; do
                [ -f "$file" ] || continue

                if ! is_processed "$file"; then
                    process_response "$file"
                fi
            done
        fi

        # Sleep before next check
        sleep 10
    done
}

# Main execution
log "=== Incoming Message Watcher Started ==="
log "PID: $$"

# Trap signals for graceful shutdown
trap 'log "Received shutdown signal, exiting..."; exit 0' SIGTERM SIGINT

# Start watching
watch_directories
