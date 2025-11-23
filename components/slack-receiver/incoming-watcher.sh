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
TASK_OUTPUT_DIR="${HOME}/sharing/task-output"
STATE_FILE="${STATE_DIR}/incoming-watcher.state"
LOG_FILE="${STATE_DIR}/incoming-watcher.log"
CLAUDE_LOG_FILE="${STATE_DIR}/claude-tasks.log"

# Configurable polling interval (seconds)
# How often to check for new messages from Slack
# Lower = faster response to messages, Higher = less CPU usage
# Default: 10 seconds, can be overridden via environment variable
CHECK_INTERVAL="${CHECK_INTERVAL:-10}"

# Ensure directories exist
mkdir -p "$INCOMING_DIR" "$RESPONSES_DIR" "$STATE_DIR" "$TASK_OUTPUT_DIR"

# Create log files if they don't exist
touch "$LOG_FILE" "$CLAUDE_LOG_FILE"

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
    mkdir -p "${HOME}/sharing/notifications"
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

    # Automatically invoke Claude to process the task
    log "🤖 Invoking Claude to process task..."

    # Create output directory for this task
    local task_timestamp=$(date +%Y%m%d-%H%M%S)
    local output_dir="${TASK_OUTPUT_DIR}/${task_timestamp}"
    mkdir -p "$output_dir"

    # Build the full prompt with context
    local full_prompt="# Task from Slack (Received: $(date '+%Y-%m-%d %H:%M:%S'))

You received this task via Slack DM. Complete it autonomously following the guidelines in your mission.

**What to do**:
1. Read and understand the task below
2. Gather context from codebase, Confluence docs, or saved context as needed
3. Complete the task (implement, test, document)
4. Save any code changes to \`~/sharing/staged-changes/\`
5. **REQUIRED**: When done, write a completion summary to \`~/sharing/notifications/\`

**IMPORTANT - How to respond**:
When you complete this task (or need guidance), you MUST write a notification file:

\`\`\`bash
cat > ~/sharing/notifications/\$(date +%Y%m%d-%H%M%S)-task-response.md <<'EOF'
# ✅ Task Complete: [Brief description]

**Status**: [Completed/Need Guidance/Blocked]

## What I Did
[Summary of work completed]

## Results
[What was produced - code changes, analysis, etc.]

## Next Steps
[What human should review or do next, if anything]
EOF
\`\`\`

This notification will be sent to the human via Slack automatically.

**Task**:
$task_content

**Remember**:
- ~/khan/ is read-only. Stage any code changes in ~/sharing/staged-changes/ with clear documentation.
- You MUST create a notification file when done - this is how you communicate back via Slack."

    # Invoke Claude in non-interactive mode with the task
    # Claude will use the rules from ~/CLAUDE.md automatically
    # Run from home directory so paths work correctly
    # Use --dangerously-skip-permissions to bypass all permission prompts (safe in sandbox)
    if cd "${HOME}" && claude --print --dangerously-skip-permissions "$full_prompt" > "$output_dir/output.log" 2>&1; then
        log "✅ Claude completed task successfully"

        # Create completion notification
        local completion_file="${HOME}/sharing/notifications/$(date +%Y%m%d-%H%M%S)-task-completed.md"
        # Convert container path to host path for the notification
        local host_output_path="${output_dir/${HOME}\/sharing/${HOME}\/.jib-sharing}"
        cat > "$completion_file" <<EOF
# ✅ Task Completed

**Original task:** \`$filename\`
**Completed:** $(date '+%Y-%m-%d %H:%M:%S')

## Task
$task_content

## Output
See: \`$host_output_path/output.log\`

---
📨 *Processed by Claude automatically*
EOF
        log "📬 Completion notification: $completion_file"

        # Also log summary to claude-tasks.log
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Task completed: $filename" >> "$CLAUDE_LOG_FILE"
        echo "Output: $output_dir/output.log" >> "$CLAUDE_LOG_FILE"
    else
        log "❌ Claude failed to process task"

        # Create error notification
        local error_file="${HOME}/sharing/notifications/$(date +%Y%m%d-%H%M%S)-task-failed.md"
        # Convert container path to host path for the notification
        local host_output_path="${output_dir/${HOME}\/sharing/${HOME}\/.jib-sharing}"
        cat > "$error_file" <<EOF
# ❌ Task Failed

**Original task:** \`$filename\`
**Failed:** $(date '+%Y-%m-%d %H:%M:%S')

## Task
$task_content

## Error
Claude encountered an error. Check logs: \`$host_output_path/output.log\`

---
📨 *Processed by Claude automatically*
EOF
        log "📬 Error notification: $error_file"

        # Also log error to claude-tasks.log
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ Task failed: $filename" >> "$CLAUDE_LOG_FILE"
        echo "Error log: $output_dir/output.log" >> "$CLAUDE_LOG_FILE"
    fi

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
    log "PID: $$"
    log ""
    log "Directories:"
    log "  - Incoming: $INCOMING_DIR"
    log "  - Responses: $RESPONSES_DIR"
    log "  - Task output: $TASK_OUTPUT_DIR"
    log ""
    log "Logs:"
    log "  - Watcher: $LOG_FILE"
    log "  - Claude tasks: $CLAUDE_LOG_FILE"
    log ""
    log "Monitoring for new files..."

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
        sleep "$CHECK_INTERVAL"
    done
}

# Main execution
log "=== Incoming Message Watcher Started ==="
log "PID: $$"
log "Monitoring: ${INCOMING_DIR} and ${RESPONSES_DIR}"
log "Check interval: ${CHECK_INTERVAL} seconds"

# Trap signals for graceful shutdown
trap 'log "Received shutdown signal, exiting..."; exit 0' SIGTERM SIGINT

# Start watching
watch_directories
