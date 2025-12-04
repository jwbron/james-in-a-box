# Beads Task Tracking Reference

> Persistent task memory system for autonomous agents. Git-backed, multi-container safe.

**Binary:** `/usr/local/bin/bd` (v0.25.1+)
**Location:** `~/beads/` (symlink to `~/.jib-sharing/beads/`)
**Documentation:** [github.com/cristoslc/llm-beads](https://github.com/cristoslc/llm-beads)

## Quick Reference

```bash
# ALWAYS START HERE - check for existing work
bd --allow-stale list --status in_progress
bd --allow-stale search "keywords"

# Create task (use searchable title - see "Task Title Best Practices" below)
bd --allow-stale create "Feature Name (PR #XXX) - repo" --labels feature,repo-name,pr-XXX

# Update status
bd --allow-stale update <id> --status in_progress
bd --allow-stale update <id> --status closed --notes "Summary"

# Find ready work
bd --allow-stale ready
```

> **Note:** The `BEADS_DIR` environment variable is set automatically, so `bd` can be run from any directory.

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

## Task Title Best Practices

**Titles must be searchable.** Future sessions will search by keywords, PR numbers, and feature names to find existing work.

**Good titles:**
- `Phase 2: LLM Documentation Index Generator (PR #141)`
- `Fix auth token refresh bug (PR #89) - james-in-a-box`
- `Add Slack notification threading - jira-1234`
- `Implement user settings API - webapp`

**Bad titles:**
- `Resolve merge conflicts` (too generic - won't match searches)
- `Fix bug` (not searchable - no context)
- `WIP` (meaningless for future discovery)
- `Update code` (no specifics)

**Include in titles:**
- Feature/task name (what the work accomplishes)
- PR number if created: `(PR #XXX)`
- Repository name for multi-repo work
- JIRA ticket if applicable: `jira-XXXX`

**Update titles when context changes:**
```bash
# After creating a PR, update the title to include the PR number
bd --allow-stale update <id> --title "Feature Name (PR #141) - repo-name"
```

## Finding Existing Tasks

**Search strategies for discovering related work:**

```bash
# Search by PR number (most reliable for PR-related work)
bd --allow-stale search "PR-141"
bd --allow-stale search "pr-141"

# Search by repository name
bd --allow-stale search "james-in-a-box"
bd --allow-stale search "webapp"

# Search by feature/area keywords
bd --allow-stale search "index-generator"
bd --allow-stale search "llm-documentation"
bd --allow-stale search "authentication"

# Search by JIRA ticket
bd --allow-stale search "jira-1234"
bd --allow-stale search "JIRA-1234"

# List recent in-progress work
bd --allow-stale list --status in_progress

# List by label
bd --allow-stale list --label pr-141
bd --allow-stale list --label james-in-a-box
```

**If search finds nothing but you expect a task:**
- Try different keyword variations (singular/plural, abbreviations)
- Search for partial terms: `bd --allow-stale search "index"` instead of `index-generator`
- Check for typos in search terms
- Use `bd --allow-stale list` to browse all tasks
- Check `bd --allow-stale list --status closed` for completed work

## Labeling Conventions

| Category | Labels | Purpose |
|----------|--------|---------|
| **Source** | `slack`, `slack-thread`, `jira-XXXX`, `github-pr-XX` | Track where task originated |
| **Type** | `feature`, `bug`, `refactor`, `docs`, `test` | Categorize work type |
| **Priority** | `urgent`, `important` | Flag critical items |
| **Status** | `needs-triage`, `blocked-external`, `waiting-review` | Additional status info |
| **Repository** | `james-in-a-box`, `webapp`, `services` | Multi-repo discoverability |
| **PR Tracking** | `pr-141`, `pr-89` | Searchable PR number format |
| **Feature Area** | `llm-documentation`, `index-generator`, `auth` | Feature-based search |

**Always include these labels for discoverability:**
- Repository name (e.g., `james-in-a-box`) - enables finding all work on a repo
- PR number when created (e.g., `pr-141`) - enables finding work by PR
- Feature/area keywords (e.g., `index-generator`) - enables finding related work

## Best Practices

### DO:
- ✅ Check for existing tasks before creating new ones
- ✅ Always use `--allow-stale` in containers
- ✅ **Use searchable titles** with feature name, PR#, and repo name
- ✅ **Add labels** for repository, PR number, and feature area
- ✅ **Update title** when PR is created to include PR number
- ✅ Update status immediately when starting/finishing work
- ✅ Add notes with progress, decisions, and context
- ✅ Include Beads ID in PR descriptions and Slack notifications
- ✅ Create discovered-from tasks for issues found during work
- ✅ Mark tasks closed with summary when done

### DON'T:
- ❌ Skip checking for existing tasks
- ❌ **Use generic titles** like "Fix bug" or "Resolve conflicts"
- ❌ **Omit repository labels** when working on multiple repos
- ❌ Leave tasks in_progress when switching to other work
- ❌ Forget to update status when completing work
- ❌ Create duplicate tasks for the same work
- ❌ Omit `--allow-stale` (will cause errors in containers)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Database out of sync" error | Use `--allow-stale` flag |
| "No beads database found" | Verify `BEADS_DIR` env var is set |
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
