#!/bin/bash
# .claude/hooks/session-end.sh
# Beads session-ending protocol
# Called automatically when Claude Code session ends

set -euo pipefail

# Exit silently if beads not available
command -v bd >/dev/null 2>&1 || exit 0

# Exit silently if beads directory doesn't exist
[ -d ~/beads ] || exit 0

cd ~/beads || exit 0

echo ""
echo "🧹 Beads Session-Ending Protocol"
echo ""

# 1. Show current in-progress work
IN_PROGRESS=$(bd --allow-stale list --status in_progress --json 2>/dev/null | jq -r 'length' 2>/dev/null || echo "0")
if [ "$IN_PROGRESS" -gt 0 ]; then
    echo "⚠️  WARNING: ${IN_PROGRESS} task(s) still in progress"
    echo "   Consider closing or updating them before exit:"
    echo ""
    bd --allow-stale list --status in_progress 2>/dev/null || true
    echo ""
    echo "   To close a task:"
    echo "   bd --allow-stale update <id> --status closed --notes \"Summary\""
    echo ""
fi

# 2. Show open tasks (may be forgotten work)
OPEN=$(bd --allow-stale list --status open --json 2>/dev/null | jq -r 'length' 2>/dev/null || echo "0")
if [ "$OPEN" -gt 0 ]; then
    echo "ℹ️  INFO: ${OPEN} open task(s) (not started)"
    echo ""
fi

# 3. Sync database
echo "Syncing beads database..."
if bd sync --flush-only 2>&1 | grep -iq "error" 2>/dev/null; then
    echo "⚠️  WARNING: Beads sync failed - changes may be lost"
    echo "   Manual sync: cd ~/beads && bd sync"
else
    echo "✓ Beads database synced"
fi

echo ""
echo "Session cleanup complete."
echo ""
