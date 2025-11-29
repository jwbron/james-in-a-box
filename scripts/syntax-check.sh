#!/usr/bin/env bash
# Check Python and Bash syntax
# Usage: syntax-check.sh [--python-only] [--bash-only]
#
# Exit codes:
#   0 - All syntax is valid
#   1 - Syntax errors found

set -euo pipefail

CHECK_PYTHON=true
CHECK_BASH=true

for arg in "$@"; do
  case $arg in
    --python-only)
      CHECK_BASH=false
      ;;
    --bash-only)
      CHECK_PYTHON=false
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

ERRORS=0

if $CHECK_PYTHON; then
  echo "==> Checking Python syntax..."
  PYTHON_FILES=$(find . -name "*.py" -type f ! -path "./.git/*" 2>/dev/null || true)

  if [ -z "$PYTHON_FILES" ]; then
    echo "No Python files found."
  else
    # shellcheck disable=SC2086
    if ! echo "$PYTHON_FILES" | xargs python -m py_compile 2>&1; then
      ERRORS=$((ERRORS + 1))
    else
      echo "All Python files have valid syntax"
    fi
  fi
fi

if $CHECK_BASH; then
  echo "==> Checking Bash syntax..."
  SHELL_FILES=$(find . -name "*.sh" -type f ! -path "./.git/*" 2>/dev/null || true)

  if [ -z "$SHELL_FILES" ]; then
    echo "No shell scripts found."
  else
    BASH_ERRORS=0
    for file in $SHELL_FILES; do
      if ! bash -n "$file" 2>&1; then
        BASH_ERRORS=$((BASH_ERRORS + 1))
      fi
    done

    if [ $BASH_ERRORS -gt 0 ]; then
      ERRORS=$((ERRORS + BASH_ERRORS))
    else
      echo "All Bash files have valid syntax"
    fi
  fi
fi

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "Syntax check failed with $ERRORS error(s)"
  exit 1
fi

echo ""
echo "All syntax checks passed!"
