#!/usr/bin/env bash
# Setup shell aliases for transparent jib_logging wrappers.
#
# Source this file to replace bd and claude with logged versions:
#   source ~/repos/james-in-a-box/shared/jib_logging/bin/setup-aliases.sh
#
# The aliases are transparent - they accept all the same arguments and
# produce the same output as the original commands.
#
# Note: git/gh wrappers were removed. The gateway sidecar provides
# purpose-built clients with security validation for those tools.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Verify the bin directory exists and has the wrappers
if [[ ! -x "${SCRIPT_DIR}/jib-bd" ]]; then
    echo "Warning: jib_logging wrappers not found in ${SCRIPT_DIR}" >&2
    return 1 2>/dev/null || exit 1
fi

# Create transparent aliases
alias bd="${SCRIPT_DIR}/jib-bd"
alias claude="${SCRIPT_DIR}/jib-claude"

# Confirm setup (can be silenced with JIB_LOGGING_QUIET=1)
if [[ "${JIB_LOGGING_QUIET:-}" != "1" ]]; then
    echo "jib_logging: Transparent wrappers enabled for bd, claude" >&2
fi
