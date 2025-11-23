#!/bin/bash
# Context Watcher Service
# Monitors ~/context-sync for changes and triggers Claude analysis

set -euo pipefail

# Configuration
CONTEXT_DIR="${HOME}/context-sync"
CONFIG_DIR="${HOME}/.config/context-watcher"
CONFIG_FILE="${CONFIG_DIR}/config.yaml"
STATE_FILE="${CONFIG_DIR}/watcher-state.json"
LOG_FILE="${CONFIG_DIR}/watcher.log"
LOCK_FILE="/tmp/context-watcher.lock"
NOTIFICATIONS_DIR="${HOME}/.jib-sharing/notifications"

# Ensure directories exist
mkdir -p "$CONFIG_DIR" "$CONTEXT_DIR" "$NOTIFICATIONS_DIR"
chmod 700 "$CONFIG_DIR"  # Secure permissions for config directory

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Check if another instance is running
if [ -f "$LOCK_FILE" ]; then
    PID=$(cat "$LOCK_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        log "Another instance is already running (PID: $PID)"
        exit 1
    else
        log "Removing stale lock file"
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"; log "Context watcher stopped"' EXIT

log "Context watcher started (PID: $$)"

# Initialize state file
if [ ! -f "$STATE_FILE" ]; then
    echo '{"last_check": 0, "processed_files": {}}' > "$STATE_FILE"
fi

# Get configuration values
CHECK_INTERVAL=300
BATCH_WINDOW=60

if command -v yq &> /dev/null && [ -f "$CONFIG_FILE" ]; then
    CHECK_INTERVAL=$(yq eval '.processing.check_interval_seconds // 300' "$CONFIG_FILE" 2>/dev/null || echo "300")
    BATCH_WINDOW=$(yq eval '.processing.batch_window_seconds // 60' "$CONFIG_FILE" 2>/dev/null || echo "60")
fi

# Function to compute file hash
file_hash() {
    sha256sum "$1" 2>/dev/null | awk '{print $1}'
}

# Function to get changed files since last check
get_changed_files() {
    local last_check=$1
    local changed_files=""

    if [ ! -d "$CONTEXT_DIR" ]; then
        return 0
    fi

    # Find files modified since last check
    while IFS= read -r file; do
        # Skip if file matches ignore patterns
        skip=false
        for pattern in "*.tmp" "*.swp" ".git/*" "node_modules/*"; do
            if [[ "$file" == $pattern ]]; then
                skip=true
                break
            fi
        done

        if [ "$skip" = false ]; then
            changed_files+="$file"$'\n'
        fi
    done < <(find "$CONTEXT_DIR" -type f -newermt "@$last_check" 2>/dev/null | sort)

    echo -n "$changed_files"
}

# Function to trigger Claude analysis
analyze_changes() {
    local changed_files=$1

    if [ -z "$changed_files" ]; then
        return 0
    fi

    local num_files=$(echo "$changed_files" | grep -c '^' || echo "0")
    log "Triggering Claude analysis for $num_files changed file(s)"

    # Create temp file with changes
    local temp_file=$(mktemp)
    echo "$changed_files" > "$temp_file"

    # Prepare the analysis prompt
    local prompt_file=$(mktemp)
    cat > "$prompt_file" << 'EOF'
You are monitoring context changes for Jacob Wiesblatt (jwies). Analyze the following changed files and determine if they're relevant to him.

Relevant changes include:
- ADRs authored by Jacob
- Responses to his comments
- Mentions of @jwies, Jacob, or Jacob Wiesblatt
- Tags for infra-platform, infrastructure-platform, or infrastructure platform
- Updates to INFRA or ENG JIRA tickets he's assigned to or watching
- Comments on his work

For each relevant change:
1. Summarize what changed and why it matters
2. Draft a response if needed (save to ~/sharing/notifications/draft-responses/)
3. Suggest action items (save to ~/sharing/notifications/action-items/)
4. Update the tracking doc at ~/sharing/context-tracking/updates.md

Changed files:
EOF
    cat "$temp_file" >> "$prompt_file"

    # Run Claude analysis
    cd "${HOME}/khan/james-in-a-box" || cd "$HOME"

    if claude --prompt-file "$prompt_file" --output-dir "$NOTIFICATIONS_DIR" >> "$LOG_FILE" 2>&1; then
        log "Analysis completed successfully"
    else
        local exit_code=$?
        log "ERROR: Analysis failed (exit code: $exit_code)"
    fi

    rm -f "$temp_file" "$prompt_file"
}

# Main loop
log "Monitoring $CONTEXT_DIR (check interval: ${CHECK_INTERVAL}s, batch window: ${BATCH_WINDOW}s)"

while true; do
    # Read last check time
    LAST_CHECK=$(jq -r '.last_check' "$STATE_FILE" 2>/dev/null || echo "0")
    CURRENT_TIME=$(date +%s)

    # Get changed files
    CHANGED_FILES=$(get_changed_files "$LAST_CHECK")

    if [ -n "$CHANGED_FILES" ]; then
        num=$(echo "$CHANGED_FILES" | grep -c '^' || echo "0")
        log "Detected $num changed file(s)"

        # Wait for batch window
        if [ "$BATCH_WINDOW" -gt 0 ]; then
            log "Waiting ${BATCH_WINDOW}s for additional changes..."
            sleep "$BATCH_WINDOW"
            CHANGED_FILES=$(get_changed_files "$LAST_CHECK")
        fi

        # Trigger analysis
        analyze_changes "$CHANGED_FILES"
    fi

    # Update last check time
    echo "{\"last_check\": $CURRENT_TIME}" > "$STATE_FILE"

    # Sleep until next check
    sleep "$CHECK_INTERVAL"
done
