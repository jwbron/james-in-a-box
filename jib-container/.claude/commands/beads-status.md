# Beads Status Overview

Show current Beads task status and what's ready to work on.

Run these commands and provide a summary:

```bash
cd ~/beads

echo "=== Tasks Ready to Work On (No Blockers) ==="
beads ready 2>/dev/null || echo "No ready tasks found"

echo ""
echo "=== Tasks Currently In Progress ==="
beads list --status in-progress 2>/dev/null || echo "No tasks in progress"

echo ""
echo "=== Blocked Tasks ==="
beads list --status blocked 2>/dev/null || echo "No blocked tasks"

echo ""
echo "=== Recently Completed Tasks ==="
beads list --status done 2>/dev/null | head -5 || echo "No completed tasks"
```

After showing the output, provide a brief summary highlighting:
- Number of ready tasks
- Current work in progress
- Any blocked tasks that need attention
- Recommendations for what to work on next
