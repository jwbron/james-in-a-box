# Beads Task Tracking Reference

> Persistent task memory system for autonomous agents. Git-backed, multi-container safe.

**Binary:** `/usr/local/bin/bd`
**Location:** `~/beads/` (symlink to `~/.jib-sharing/beads/`)
**Documentation:** [github.com/steveyegge/beads](https://github.com/steveyegge/beads)

## Quick Reference

```bash
# ALWAYS START HERE - check for existing work
bd --allow-stale list -s in_progress
bd --allow-stale search "keywords"

# Show ready work (no blockers)
bd --allow-stale ready

# Create task (use searchable title - see "Task Title Best Practices" below)
bd --allow-stale create "Feature Name (PR #XXX) - repo" -l feature,repo-name,pr-XXX

# Claim task atomically (sets assignee + status in one operation)
bd --allow-stale update <id> --claim

# Complete task
bd --allow-stale close <id> -r "Summary. PR #XXX created."
```

> **Note:** The `BEADS_DIR` environment variable is set automatically, so `bd` can be run from any directory.

## Short Flags Reference

| Short | Long | Used With |
|-------|------|-----------|
| `-s` | `--status` | update, list, search |
| `-s` | `--sort` | ready (different meaning!) |
| `-l` | `--labels` / `--label` | create, list, search, ready |
| `-p` | `--priority` | create, update, list, ready |
| `-t` | `--type` | create, update, list, search, ready |
| `-r` | `--reason` | close |
| `-r` | `--reverse` | list, search (different meaning!) |
| `-n` | `--limit` | list, search, ready |
| `-a` | `--assignee` | create, update, list, search, ready |
| `-d` | `--description` | create, update |
| `-e` | `--estimate` | create, update |

**Note:** `--notes` and `--append-notes` have NO short flags. Use the full flag name.

## Why `--allow-stale` is Required

In ephemeral containers, the database may be newer than git sync state. The `--allow-stale` flag bypasses staleness checks that would otherwise block operations. **Always use this flag.**

## Status Values

| Status | Description | Use When |
|--------|-------------|----------|
| `open` | Not started | Task created, waiting for work to begin |
| `in_progress` | Actively working | You've started working on the task |
| `blocked` | Cannot proceed | Waiting on external dependency |
| `deferred` | Postponed | Hidden from `bd ready` until defer date |
| `closed` | Complete | Work is done, PR created, or abandoned |

**Status Flow:**
```
open → in_progress → closed
           ↓
        blocked → in_progress → closed
           ↓
        deferred → open → in_progress → closed
```

## Command Reference

### Creating Tasks

```bash
# Basic creation
bd --allow-stale create "Task title"

# With labels (comma-separated)
bd --allow-stale create "Task title" -l feature,jira-1234,slack

# With priority (0=highest, 4=lowest)
bd --allow-stale create "Task title" -p 1

# With type
bd --allow-stale create "Task title" -t bug  # bug|feature|task|epic|chore

# With parent (for subtasks)
bd --allow-stale create "Subtask" --parent bd-a3f8

# With description
bd --allow-stale create "Task title" -d "Detailed description here"

# With dependencies
bd --allow-stale create "Task" --deps blocks:bd-b1,discovered-from:bd-a3f8

# Quick capture (outputs only the ID)
bd --allow-stale q "Quick task title"
```

### Claiming and Starting Work

```bash
# Atomic claim (sets assignee to you + status to in_progress)
# Fails if already claimed by someone else
bd --allow-stale update <id> --claim

# Manual status update
bd --allow-stale update <id> -s in_progress
```

### Updating Tasks

```bash
# Change status
bd --allow-stale update <id> -s in_progress
bd --allow-stale update <id> -s blocked

# Add notes (appended to existing)
bd --allow-stale update <id> --notes "Progress: completed step 1"

# Change priority
bd --allow-stale update <id> -p 1

# Add labels
bd --allow-stale update <id> --add-label urgent

# Remove labels
bd --allow-stale update <id> --remove-label urgent

# Update title
bd --allow-stale update <id> --title "New title (PR #123)"
```

### Completing Tasks

```bash
# Close with reason (preferred)
bd --allow-stale close <id> -r "Done. PR #123 created. Tests passing."

# Close and show suggested next work
bd --allow-stale close <id> -r "Complete" --suggest-next

# Close multiple tasks
bd --allow-stale close bd-a1 bd-a2 bd-a3 -r "Batch complete"
```

### Viewing Tasks

```bash
# Show task details
bd --allow-stale show <id>

# List all open tasks
bd --allow-stale list

# Filter by status
bd --allow-stale list -s in_progress
bd --allow-stale list -s open

# Filter by label
bd --allow-stale list -l jira-1234

# Filter by multiple labels (AND)
bd --allow-stale list -l feature -l webapp

# Filter by any of multiple labels (OR)
bd --allow-stale list --label-any feature,bug

# Limit results
bd --allow-stale list -n 10

# Search by text (title, description, ID)
bd --allow-stale search "authentication"
bd --allow-stale search "PR-123"

# Search with filters
bd --allow-stale search "bug" -s open -l backend
```

### Finding Work

```bash
# Show tasks ready to work on (no blockers, open or in_progress)
bd --allow-stale ready

# Limit ready work
bd --allow-stale ready -n 5

# Filter ready work by priority
bd --allow-stale ready -p 1

# Show only unassigned ready work
bd --allow-stale ready -u

# Show blocked tasks
bd --allow-stale blocked

# Show stale tasks (not updated recently)
bd --allow-stale stale
```

### Managing Dependencies

```bash
# Add dependency (task2 depends on task1)
bd --allow-stale dep add <task2> <task1>

# Add with explicit type
bd --allow-stale dep add <task2> <task1> --type blocks

# Remove dependency
bd --allow-stale dep remove <task2> <task1>

# Show dependency graph
bd --allow-stale graph <id>
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
# Full sync (recommended)
bd sync

# Check database health
bd doctor

# Fix database issues
bd doctor --fix
```

## Agent Workflow Patterns

### Pattern 1: Starting Work (Container Startup)

**ALWAYS do this first when starting any session:**

```bash
# 1. Check for in-progress work to resume
bd --allow-stale list -s in_progress

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
bd --allow-stale create "Task description" -l source,type

# 3. Claim it atomically
bd --allow-stale update <id> --claim
```

### Pattern 3: Work Discovery (Finding Issues During Work)

When you discover additional work while implementing something:

```bash
# Create task linked to parent work
bd --allow-stale create "Found: <issue description>" \
    -t bug \
    --deps discovered-from:$CURRENT_TASK_ID \
    -l discovered,needs-triage
```

### Pattern 4: Completing Work

```bash
# 1. Close with summary
bd --allow-stale close <id> -r "Done: <summary>. PR #XX created. Tests passing."

# 2. Check for child tasks
bd --allow-stale list -l "parent:$id"
```

### Pattern 5: Slack Thread Context

When processing Slack messages, use the `task_id` from YAML frontmatter:

```bash
# Search for existing context
bd --allow-stale search "$TASK_ID"

# If found, show and resume
bd --allow-stale show <bead-id>

# If not found, create with task_id as label
bd --allow-stale create "Slack: <summary>" -l slack-thread,$TASK_ID
```

### Pattern 6: PR Work Context

```bash
# Search for PR-related tasks
bd --allow-stale search "PR-$NUMBER"
bd --allow-stale search "$BRANCH_NAME"

# Create task for PR work
bd --allow-stale create "PR #$NUMBER: <description>" -l pr,PR-$NUMBER,$BRANCH_NAME
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
bd --allow-stale list -s in_progress

# List by label
bd --allow-stale list -l pr-141
bd --allow-stale list -l james-in-a-box
```

**If search finds nothing but you expect a task:**
- Try different keyword variations (singular/plural, abbreviations)
- Search for partial terms: `bd --allow-stale search "index"` instead of `index-generator`
- Check for typos in search terms
- Use `bd --allow-stale list` to browse all tasks
- Check `bd --allow-stale list -s closed` for completed work

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
- ✅ **Use `--claim` to atomically start work**
- ✅ **Use `bd close` to complete tasks** (not `update --status closed`)
- ✅ **Use searchable titles** with feature name, PR#, and repo name
- ✅ **Add labels** for repository, PR number, and feature area
- ✅ **Update title** when PR is created to include PR number
- ✅ Update status immediately when starting/finishing work
- ✅ Add notes with progress, decisions, and context
- ✅ Include Beads ID in PR descriptions and Slack notifications
- ✅ Create discovered-from tasks for issues found during work

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
| Task shows blocked incorrectly | Check `bd --allow-stale graph <id>` for hidden blockers |
| Database corruption | Run `bd doctor --fix` |

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
