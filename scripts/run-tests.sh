#!/usr/bin/env bash
# Run Python tests with pytest
# Usage: run-tests.sh [pytest args...]
#
# Exit codes:
#   0 - All tests pass
#   1 - Test failures

set -euo pipefail

# Find the repo root (where this script is in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "==> Running pytest..."

# Check if tests directory exists
if [ ! -d "tests" ]; then
  echo "No tests directory found, skipping pytest"
  exit 0
fi

# Pass through any arguments to pytest
if [ $# -gt 0 ]; then
  pytest tests/ "$@"
else
  pytest tests/ -v --tb=short
fi
