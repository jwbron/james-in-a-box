# Beads Task Tracking Reference

> Persistent task memory system for autonomous agents. Git-backed, multi-container safe.

**Binary:** `/usr/local/bin/bd` (v0.25.1+)
**Location:** `~/beads/` (symlink to `~/.jib-sharing/beads/`)
**Documentation:** [github.com/cristoslc/llm-beads](https://github.com/cristoslc/llm-beads)

## Quick Reference

```bash
cd ~/beads

# ALWAYS START HERE - check for existing work
bd --allow-stale list --status in_progress
bd --allow-stale search "keywords"

# Create task
bd --allow-stale create "Task title" --labels feature,jira-1234

# Update status
bd --allow-stale update <id> --status in_progress
bd --allow-stale update <id> --status closed --notes "Summary"

# Find ready work
bd --allow-stale ready
```

## Why `--allow-stale` is Required

In ephemeral containers, the database may be newer than git sync state. The `--allow-stale` flag bypasses staleness checks that would otherwise block operations. **Always use this flag.**

## Status Values

| Status | Description | Use When |
|--------|-------------|----------|
| `open` | Not started | Task created, waiting for work to begin |
| `in_progress` | Actively working | You've started working on the task |
| `blocked` | Cannot proceed | Waiting on external dependency |
| `closed` | Complete | Work is done, PR created, or abandoned |

**Status Flow:**
```
open → in_progress → closed
           ↓
        blocked → in_progress → closed
```

## Command Reference

### Creating Tasks

```bash
# Basic creation
bd --allow-stale create "Task title"

# With labels (comma-separated)
bd --allow-stale create "Task title" --labels feature,jira-1234,slack

# With priority (0=highest, 4=lowest)
bd --allow-stale create "Task title" --priority 1

# With type
bd --allow-stale create "Task title" --type bug  # bug|feature|task|epic|chore

# With parent (for subtasks)
bd --allow-stale create "Subtask" --parent bd-a3f8

# With description
bd --allow-stale create "Task title" --description "Detailed description here"

# With dependencies
bd --allow-stale create "Task" --deps blocks:bd-b1,discovered-from:bd-a3f8
```

### Updating Tasks

```bash
# Change status
bd --allow-stale update <id> --status in_progress
bd --allow-stale update <id> --status closed

# Add notes (appended to existing)
bd --allow-stale update <id> --notes "Progress: completed step 1"

# Change priority
bd --allow-stale update <id> --priority 1

# Add labels
bd --allow-stale update <id> --add-label urgent

# Remove labels
bd --allow-stale update <id> --remove-label urgent

# Update multiple fields
bd --allow-stale update <id> --status closed --notes "Done. PR #123 created."
```

### Viewing Tasks

```bash
# Show task details
bd --allow-stale show <id>

# List all tasks
bd --allow-stale list

# Filter by status
bd --allow-stale list --status in_progress
bd --allow-stale list --status open

# Filter by label
bd --allow-stale list --label jira-1234

# Limit results
bd --allow-stale list --limit 10

# Search by text
bd --allow-stale search "authentication"
bd --allow-stale search "PR-123"
```

### Finding Work

```bash
# Show tasks ready to work on (no blockers)
bd --allow-stale ready

# Limit ready work
bd --allow-stale ready --limit 5

# Filter ready work by priority
bd --allow-stale ready --priority 1

# Show blocked tasks
bd --allow-stale blocked
```

### Managing Dependencies

```bash
# Add dependency (task2 depends on task1)
bd --allow-stale dep add <task2> <task1>

# Add with explicit type
bd --allow-stale dep add <task2> <task1> --type blocks

# Remove dependency
bd --allow-stale dep remove <task2> <task1>

# Show dependency tree
bd --allow-stale dep tree <id>

# Check for circular dependencies
bd --allow-stale dep cycles
```

**Dependency Types:**
| Type | Purpose | Affects Ready Work |
|------|---------|-------------------|
| `blocks` | Hard blocker | Yes - blocks until resolved |
| `related` | Soft reference | No |
| `discovered-from` | Found during other work | No |

### JSON Output (For Programmatic Use)

All commands support `--json` for machine-readable output:

```bash
bd --allow-stale list --json
bd --allow-stale ready --json
bd --allow-stale show <id> --json
```

### Sync Operations

```bash
# Import from JSONL (after git pull)
bd sync --import-only

# Export to JSONL (before git push)
bd sync --flush-only

# Full sync (git pull + import + export + git push)
bd sync
```

## Agent Workflow Patterns

### Pattern 1: Starting Work (Container Startup)

**ALWAYS do this first when starting any session:**

```bash
cd ~/beads

# 1. Check for in-progress work to resume
bd --allow-stale list --status in_progress

# 2. Search for related tasks
bd --allow-stale search "keywords from current task"

# 3. If found, show details and resume
bd --allow-stale show <id>
bd --allow-stale update <id> --notes "Resuming work..."
```

### Pattern 2: New Task Creation

```bash
# 1. Check if task already exists
bd --allow-stale search "task description keywords"

# 2. If not found, create it
bd --allow-stale create "Task description" --labels source,type

# 3. Mark as in progress
bd --allow-stale update <id> --status in_progress
```

### Pattern 3: Work Discovery (Finding Issues During Work)

When you discover additional work while implementing something:

```bash
# Create task linked to parent work
bd --allow-stale create "Found: <issue description>" \
    --type bug \
    --deps discovered-from:$CURRENT_TASK_ID \
    --labels discovered,needs-triage
```

### Pattern 4: Completing Work

```bash
# 1. Mark complete with summary
bd --allow-stale update <id> --status closed \
    --notes "Done: <summary>. PR #XX created. Tests passing."

# 2. Check for child tasks
bd --allow-stale list --label "parent:$id"
```

### Pattern 5: Slack Thread Context

When processing Slack messages, use the `task_id` from YAML frontmatter:

```bash
# Search for existing context
bd --allow-stale search "$TASK_ID"

# If found, show and resume
bd --allow-stale show <bead-id>

# If not found, create with task_id as label
bd --allow-stale create "Slack: <summary>" --labels slack-thread,$TASK_ID
```

### Pattern 6: PR Work Context

```bash
# Search for PR-related tasks
bd --allow-stale search "PR-$NUMBER"
bd --allow-stale search "$BRANCH_NAME"

# Create task for PR work
bd --allow-stale create "PR #$NUMBER: <description>" \
    --labels pr,PR-$NUMBER,$BRANCH_NAME
```

## Labeling Conventions

| Category | Labels | Purpose |
|----------|--------|---------|
| **Source** | `slack`, `slack-thread`, `jira-XXXX`, `github-pr-XX` | Track where task originated |
| **Type** | `feature`, `bug`, `refactor`, `docs`, `test` | Categorize work type |
| **Priority** | `urgent`, `important` | Flag critical items |
| **Status** | `needs-triage`, `blocked-external`, `waiting-review` | Additional status info |
| **Project** | `james-in-a-box`, `webapp`, etc. | Multi-project tracking |

## Best Practices

### DO:
- ✅ Check for existing tasks before creating new ones
- ✅ Always use `--allow-stale` in containers
- ✅ Update status immediately when starting/finishing work
- ✅ Add notes with progress, decisions, and context
- ✅ Include Beads ID in PR descriptions and Slack notifications
- ✅ Create discovered-from tasks for issues found during work
- ✅ Mark tasks closed with summary when done

### DON'T:
- ❌ Skip checking for existing tasks
- ❌ Leave tasks in_progress when switching to other work
- ❌ Forget to update status when completing work
- ❌ Create duplicate tasks for the same work
- ❌ Omit `--allow-stale` (will cause errors in containers)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Database out of sync" error | Use `--allow-stale` flag |
| Changes not persisting | Verify you're in `~/beads/`, run `git status` |
| Can't find task | Try `bd --allow-stale search "partial text"` |
| Duplicate tasks created | Search before creating: `bd --allow-stale search "keywords"` |
| Task shows blocked incorrectly | Check `bd --allow-stale dep tree <id>` for hidden blockers |

## Integration with Other Systems

### Slack Notifications
Reference Beads ID when sending notifications:
```markdown
**Beads Task:** bd-a3f8
```

### PR Descriptions
Include Beads tracking:
```markdown
## Tracking
- **Beads:** bd-a3f8
- **JIRA:** JIRA-1234
```

### Context Saving
Include active Beads tasks when saving context:
```bash
@save-context project-name
# Context includes reference to active Beads tasks
```

---

*See also: [Beads Usage Rules](../../jib-container/.claude/rules/beads-usage.md) for quick reference.*
