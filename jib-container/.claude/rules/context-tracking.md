# Context Tracking with Beads

Persistent memory across container restarts via the Beads task tracking system.

## Core Principle

**Every conversation needs persistent context.** Use Beads to track:
- Slack thread conversations (via task_id)
- GitHub PR work (via PR number/branch)
- Multi-session tasks

## Quick Reference

| Scenario | Action |
|----------|--------|
| New Slack message | `bd --allow-stale list --label "$TASK_ID"` then create/resume task |
| New PR work | `bd --allow-stale list --label "PR-$NUMBER"` or search by branch |
| Resuming work | `bd --allow-stale show <id>` → read previous context |
| During work | `bd --allow-stale update <id> --notes "Progress..."` |
| Completing work | `bd --allow-stale update <id> --status closed --notes "Summary"` |

## Slack Thread Context

When processing Slack messages, the `task_id` from the message's YAML frontmatter is your key:

```yaml
---
task_id: "task-20251125-134311"
thread_ts: "1732567891.123456"
---
```

**ALWAYS check for existing context first:**
```bash
cd ~/beads
# Use list --label to find tasks by task_id (search only checks title/description)
bd --allow-stale list --label "$TASK_ID"
# If found: load context with bd --allow-stale show <id>
# If not found: create new task with task_id as label
bd --allow-stale create "Slack: <summary>" --labels slack-thread,$TASK_ID
```

**IMPORTANT**: `bd search` does NOT search labels - it only searches title, description, and ID.
Use `bd list --label` to find tasks by their task_id label.

## GitHub PR Context

When working on PRs, create Beads tasks with PR identifiers:

```bash
# Create/find task for PR work
bd --allow-stale search "PR-123"
bd --allow-stale search "feature-branch"

# Include in task labels for searchability
bd --allow-stale create "Implement PR #123 feedback" --labels pr,PR-123,feature-branch
```

**Track in notes:**
- PR state (open, merged, closed)
- Review feedback received
- Commits made
- Files changed

## Why This Matters

1. **Containers are ephemeral** - Each Slack message may spawn a new container
2. **Context must persist** - Without Beads, you lose all memory between sessions
3. **Threads are conversations** - Users expect you to remember history
4. **PRs are multi-session** - Reviews and iterations span multiple container runs

## See Also

- `beads-usage.md` for quick Beads command reference
- `~/khan/james-in-a-box/docs/reference/beads.md` for comprehensive documentation
- `mission.md` for overall workflow
