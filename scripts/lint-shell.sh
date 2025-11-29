#!/usr/bin/env bash
# Lint shell scripts with bashate
# Usage: lint-shell.sh
#
# Exit codes:
#   0 - All checks pass
#   1 - Lint issues found

set -euo pipefail

# Find the repo root (where this script is in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "==> Linting shell scripts with bashate..."

# Find all .sh files, excluding .git directory
SHELL_FILES=$(find . -name "*.sh" -type f ! -path "./.git/*" 2>/dev/null || true)

if [ -z "$SHELL_FILES" ]; then
  echo "No shell scripts found."
  exit 0
fi

# Ignoring:
# E003 - indent not multiple of 4
# E006 - long lines
# E042 - local hides errors
# shellcheck disable=SC2086
echo "$SHELL_FILES" | xargs bashate -i E003,E006,E042

echo "Shell linting passed!"
