#!/usr/bin/env bash
# Setup shell aliases for transparent jib_logging wrappers.
#
# Source this file to replace bd, git, gh, and claude with logged versions:
#   source ~/khan/james-in-a-box/shared/jib_logging/bin/setup-aliases.sh
#
# The aliases are transparent - they accept all the same arguments and
# produce the same output as the original commands.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify the bin directory exists and has the wrappers
if [[ ! -x "${SCRIPT_DIR}/jib-bd" ]]; then
    echo "Warning: jib_logging wrappers not found in ${SCRIPT_DIR}" >&2
    return 1 2>/dev/null || exit 1
fi

# Create transparent aliases
alias bd="${SCRIPT_DIR}/jib-bd"
alias gh="${SCRIPT_DIR}/jib-gh"
alias claude="${SCRIPT_DIR}/jib-claude"

# For git, we need to be careful not to break git completions
# Use a function instead of alias for better compatibility
jib_git() {
    "${SCRIPT_DIR}/jib-git" "$@"
}
alias git='jib_git'

# Confirm setup (can be silenced with JIB_LOGGING_QUIET=1)
if [[ "${JIB_LOGGING_QUIET:-}" != "1" ]]; then
    echo "jib_logging: Transparent wrappers enabled for bd, git, gh, claude" >&2
fi
