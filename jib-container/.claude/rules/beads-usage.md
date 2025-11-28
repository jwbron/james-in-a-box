# Beads - Automatic Task Memory System

Git-backed persistent memory that **YOU MUST USE AUTOMATICALLY** for all tasks.

**Location**: `~/beads/` | **Storage**: `~/.jib-sharing/beads/` on host

## Core Rules

1. **Every task needs a Bead** - Always check/create before starting work
2. **Always use `--allow-stale`** - Required in ephemeral containers
3. **Update as you work** - Status and notes should reflect current state
4. **Mark complete** - Closed status with summary when done

## Quick Reference

```bash
cd ~/beads

# ALWAYS START HERE
bd --allow-stale list --status in_progress   # Any unfinished work?
bd --allow-stale search "keywords"           # Related task exists?

# Create task
bd --allow-stale create "Task title" --labels feature,jira-1234

# Update status
bd --allow-stale update <id> --status in_progress
bd --allow-stale update <id> --status blocked
bd --allow-stale update <id> --status closed

# Add notes (decisions, progress, blockers)
bd --allow-stale update <id> --notes "Progress: completed X, starting Y"

# View details
bd --allow-stale show <id>

# Find ready work (no blockers)
bd --allow-stale ready
```

## Status Flow

`open` → `in_progress` → `closed`
                ↓
            `blocked` (waiting on something)

## Task Breakdown

For multi-step tasks, create subtasks:

```bash
# Parent task
bd --allow-stale create "Implement auth system" --labels feature
# Subtasks with dependencies
bd --allow-stale create "Design schema" --parent bd-a3f8
bd --allow-stale create "Implement endpoints" --parent bd-a3f8 --deps blocks:bd-b7c2
bd --allow-stale create "Write tests" --parent bd-a3f8 --deps blocks:bd-d4e9
```

## Labeling Conventions

| Type | Labels |
|------|--------|
| **Source** | `slack`, `jira-1234`, `github-pr-123` |
| **Type** | `feature`, `bug`, `refactor`, `docs`, `test` |
| **Priority** | `urgent`, `important` |
| **Area** | `auth`, `api`, `frontend`, `database` |

## Standard Workflow

```bash
# 1. Check for existing work
cd ~/beads
bd --allow-stale list --status in_progress
bd --allow-stale search "relevant keywords"

# 2. Create or resume task
bd --allow-stale create "Task from context" --labels type,source
bd --allow-stale update <id> --status in_progress

# 3. Work and update progress
bd --allow-stale update <id> --notes "Approach: using X per ADR-042"

# 4. Complete with summary
bd --allow-stale update <id> --status closed
bd --allow-stale update <id> --notes "Done: summary, tests passing, PR #123"
```

## Integration

- **Slack/PR context**: See `context-tracking.md` for thread and PR persistence
- **Notifications**: Reference Bead ID when sending guidance requests
- **@save-context**: Include Bead IDs in context docs for tracking

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Database sync error | Use `--allow-stale` flag |
| Changes not persisting | Verify `cd ~/beads`, check `git status` |
| Conflict with other container | Normal - hash IDs prevent conflicts |

---
**Remember**: Beads is AUTOMATIC. Create/update tasks proactively based on context.
