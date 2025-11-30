# Beads Task Tracking (MANDATORY)

**You MUST use Beads automatically for ALL tasks.** This enables persistent memory across container restarts.

> **Full Reference:** `~/workspace/james-in-a-box/docs/reference/beads.md`

## ALWAYS Do This First

Before ANY work, run these commands:

```bash
cd ~/beads
bd --allow-stale list --status in_progress   # Resume existing work?
bd --allow-stale search "keywords"           # Related task exists?
```

**If task exists:** Resume it. **If not:** Create one.

## Core Commands

| Action | Command |
|--------|---------|
| **Create task** | `bd --allow-stale create "Title" --labels type,source` |
| **Start work** | `bd --allow-stale update <id> --status in_progress` |
| **Add notes** | `bd --allow-stale update <id> --notes "Progress..."` |
| **Complete** | `bd --allow-stale update <id> --status closed --notes "Summary"` |
| **Find ready work** | `bd --allow-stale ready` |
| **Search by text** | `bd --allow-stale search "text"` (title/description only) |
| **Find by label** | `bd --allow-stale list --label "label-name"` |
| **Show details** | `bd --allow-stale show <id>` |

**IMPORTANT**: `search` only checks title, description, and ID. To find tasks by label (like `task_id`), use `list --label`.

## Status Values

| Status | When to Use |
|--------|-------------|
| `open` | Task created, not started |
| `in_progress` | Actively working |
| `blocked` | Waiting on external dependency |
| `closed` | Work complete |

## When to Create Tasks

**ALWAYS create a task for:**
- New Slack requests (use `task_id` as label)
- PR work (use `PR-<number>` as label)
- Multi-step implementations
- Bugs discovered during other work

**Create discovered tasks:**
```bash
bd --allow-stale create "Found: <issue>" --deps discovered-from:$CURRENT_TASK
```

## When to Update Tasks

| Event | Action |
|-------|--------|
| Starting work | `--status in_progress` |
| Making decisions | `--notes "Decision: X because Y"` |
| Hitting blockers | `--status blocked --notes "Waiting on..."` |
| Creating PR | `--notes "PR #XX created"` |
| Completing work | `--status closed --notes "Summary"` |

## Common Labels

- **Source:** `slack`, `slack-thread`, `jira-XXXX`, `github-pr-XX`
- **Type:** `feature`, `bug`, `refactor`, `docs`, `test`
- **Priority:** `urgent`, `important`

## Workflow Example

```bash
# 1. Check for existing work
cd ~/beads
bd --allow-stale list --status in_progress
bd --allow-stale search "authentication"

# 2. Create task (if none found)
bd --allow-stale create "Implement OAuth flow" --labels feature,jira-1234

# 3. Start work
bd --allow-stale update bd-xxxx --status in_progress

# 4. Note progress
bd --allow-stale update bd-xxxx --notes "Completed token validation"

# 5. Complete
bd --allow-stale update bd-xxxx --status closed --notes "Done. PR #42 created."
```

## Critical Rules

1. **ALWAYS use `--allow-stale`** - Required in ephemeral containers
2. **ALWAYS check before creating** - Avoid duplicates
3. **ALWAYS update when done** - Never leave tasks hanging
4. **ALWAYS include in notifications** - Reference Beads ID in Slack/PRs

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Database out of sync" | Use `--allow-stale` |
| Can't find task by label | Use `bd --allow-stale list --label "label"` not search |
| Can't find task by text | `bd --allow-stale search "partial"` (title/desc only) |
| Changes not saving | Verify `cd ~/beads` first |

---

**Remember:** Beads is your persistent memory. Use it proactively.
