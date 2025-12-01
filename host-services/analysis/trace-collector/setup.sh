#!/bin/bash
# Setup script for LLM Trace Collector
# Configures Claude Code hooks for trace collection
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACES_DIR="${HOME}/sharing/traces"
CLAUDE_SETTINGS="${HOME}/.claude/settings.json"
HOOK_HANDLER="${COMPONENT_DIR}/hook_handler.py"

echo "Setting up LLM Trace Collector..."

# Create traces storage directory
if [ ! -d "$TRACES_DIR" ]; then
    mkdir -p "$TRACES_DIR"
    echo "✓ Created traces directory: $TRACES_DIR"
else
    echo "✓ Traces directory exists: $TRACES_DIR"
fi

# Create logs directory for error logging
LOGS_DIR="${HOME}/sharing/logs"
if [ ! -d "$LOGS_DIR" ]; then
    mkdir -p "$LOGS_DIR"
    echo "✓ Created logs directory: $LOGS_DIR"
fi

# Configure Claude Code hooks
echo "Configuring Claude Code hooks..."

# Ensure .claude directory exists
mkdir -p "${HOME}/.claude"

# Define the hook commands
POST_TOOL_USE_CMD="python3 ${HOOK_HANDLER} post-tool-use"
SESSION_END_CMD="python3 ${HOOK_HANDLER} session-end"

# Create or update settings.json with hooks
if [ -f "$CLAUDE_SETTINGS" ]; then
    # Settings file exists - need to merge hooks
    echo "  Existing settings found, merging hooks..."

    # Check if jq is available for JSON manipulation
    if command -v jq &> /dev/null; then
        # Use jq for proper JSON manipulation
        TEMP_FILE=$(mktemp)

        # Read existing settings and add/update hooks
        jq --arg post_cmd "$POST_TOOL_USE_CMD" \
           --arg end_cmd "$SESSION_END_CMD" '
            # Ensure hooks object exists
            .hooks //= {} |
            # Ensure PostToolUse array exists and add our hook if not present
            .hooks.PostToolUse //= [] |
            if (.hooks.PostToolUse | map(select(.command | contains("trace-collector"))) | length) == 0 then
                .hooks.PostToolUse += [{"type": "command", "command": $post_cmd}]
            else
                .
            end |
            # Ensure SessionEnd array exists and add our hook if not present
            .hooks.SessionEnd //= [] |
            if (.hooks.SessionEnd | map(select(.command | contains("trace-collector"))) | length) == 0 then
                .hooks.SessionEnd += [{"type": "command", "command": $end_cmd}]
            else
                .
            end
        ' "$CLAUDE_SETTINGS" > "$TEMP_FILE"

        mv "$TEMP_FILE" "$CLAUDE_SETTINGS"
        echo "✓ Hooks merged into existing settings"
    else
        # No jq available - check if hooks already configured
        if grep -q "trace-collector" "$CLAUDE_SETTINGS" 2>/dev/null; then
            echo "✓ Trace collector hooks already configured"
        else
            echo "⚠ jq not available for JSON manipulation"
            echo "  Please manually add hooks to $CLAUDE_SETTINGS:"
            echo ""
            echo '  "hooks": {'
            echo '    "PostToolUse": [{"type": "command", "command": "'"$POST_TOOL_USE_CMD"'"}],'
            echo '    "SessionEnd": [{"type": "command", "command": "'"$SESSION_END_CMD"'"}]'
            echo '  }'
        fi
    fi
else
    # No settings file - create new one with hooks
    cat > "$CLAUDE_SETTINGS" << EOF
{
  "hooks": {
    "PostToolUse": [
      {
        "type": "command",
        "command": "$POST_TOOL_USE_CMD"
      }
    ],
    "SessionEnd": [
      {
        "type": "command",
        "command": "$SESSION_END_CMD"
      }
    ]
  }
}
EOF
    echo "✓ Created settings with hooks: $CLAUDE_SETTINGS"
fi

# Verify hook handler is executable
if [ -f "$HOOK_HANDLER" ]; then
    echo "✓ Hook handler found: $HOOK_HANDLER"
else
    echo "✗ Hook handler not found: $HOOK_HANDLER"
    exit 1
fi

echo ""
echo "Setup complete!"
echo ""
echo "Trace collection will automatically start with your next Claude Code session."
echo ""
echo "Useful commands:"
echo "  python3 ${COMPONENT_DIR}/trace_reader.py list        # List collected sessions"
echo "  python3 ${COMPONENT_DIR}/trace_reader.py summary     # Show tool call summary"
echo "  python3 ${COMPONENT_DIR}/trace_reader.py show <id>   # Show session details"
echo ""
echo "Trace storage: $TRACES_DIR"
echo "Error log: ${LOGS_DIR}/trace-collector-errors.log"
