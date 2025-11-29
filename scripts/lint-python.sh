#!/usr/bin/env bash
# Lint Python files with ruff
# Usage: lint-python.sh [--fix] [--check-only]
#
# Options:
#   --fix         Auto-fix issues (including unsafe fixes)
#   --check-only  Only check, don't fix (default)
#
# Exit codes:
#   0 - All checks pass
#   1 - Lint issues found (or fixed if --fix)

set -euo pipefail

FIX_MODE=false

for arg in "$@"; do
  case $arg in
    --fix)
      FIX_MODE=true
      ;;
    --check-only)
      FIX_MODE=false
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

# Find the repo root (where this script is in scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

if $FIX_MODE; then
  echo "==> Fixing Python files with ruff..."
  ruff check --fix --unsafe-fixes .
  ruff format .
  echo "Python files fixed!"
else
  echo "==> Checking Python files with ruff..."

  CHECK_FAILED=false
  FORMAT_FAILED=false

  if ! ruff check .; then
    CHECK_FAILED=true
  fi

  if ! ruff format --check .; then
    FORMAT_FAILED=true
  fi

  if $CHECK_FAILED || $FORMAT_FAILED; then
    echo ""
    echo "Python linting failed. Run with --fix to auto-fix."
    exit 1
  fi

  echo "Python linting passed!"
fi
