#!/bin/bash
#
# Shared humanization functions for shell wrappers.
#
# Source this file to use the humanize_text function:
#   source "$(dirname "$0")/common/humanize.sh"
#

# Humanizer script location (relative to scripts directory)
_HUMANIZE_COMMON_DIR="$(dirname "${BASH_SOURCE[0]}")"
_HUMANIZE_SCRIPT="${_HUMANIZE_COMMON_DIR}/../humanize-text"

# Skip humanization if disabled (default: enabled)
JIB_HUMANIZE_ENABLED="${JIB_HUMANIZE_ENABLED:-true}"

# Function to humanize text for natural readability
# Returns humanized text on stdout, or original text if humanization fails/disabled
#
# Usage:
#   humanize_text "text to humanize"
#   humanize_text "text to humanize" "context for logging"
#
humanize_text() {
    local text="$1"
    local context="$2"  # Optional: for logging (e.g., "PR title", "commit message")

    # Skip if disabled
    if [ "$JIB_HUMANIZE_ENABLED" != "true" ]; then
        echo "$text"
        return
    fi

    # Skip if humanizer script not available
    if [ ! -x "$_HUMANIZE_SCRIPT" ]; then
        echo "$text"
        return
    fi

    # Skip short text (< 50 chars)
    if [ ${#text} -lt 50 ]; then
        echo "$text"
        return
    fi

    # Humanize text (fail-open: returns original on error)
    local result
    result=$("$_HUMANIZE_SCRIPT" "$text" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$result" ]; then
        echo "$result"
    else
        echo "$text"
    fi
}
