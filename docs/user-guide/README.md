# User Guide

Day-to-day usage documentation for james-in-a-box.

## Getting Started

See the main [README.md](../../README.md) for:
- Quick start guide
- Architecture overview
- Usage patterns
- Security model

## Common Tasks

**Start a Session:**
```bash
cd ~/khan/james-in-a-box
bin/jib
```

**Use Slash Commands (inside container):**
```
/load-context project-name
/save-context project-name
/create-pr
```

**Create a PR:**
```bash
# Inside container - commit changes then create PR:
gh pr create --title "Your title" --body "Description" --base main
```

**Check Task Status:**
```bash
bd --allow-stale list --status in_progress    # Current tasks
bd --allow-stale list                         # All tasks
```

## Workflow Overview

1. **Start container**: `bin/jib`
2. **Check for tasks**: `bd --allow-stale list` or check `~/sharing/incoming/`
3. **Load context**: `/load-context <project-name>`
4. **Work on task**: Claude works in isolated git worktree
5. **Commit changes**: Git commit to temp branch
6. **Create PR**: `gh pr create --title "..." --body "..." --base main`
7. **Save learnings**: `/save-context <project-name>`
8. **Complete task**: `bd --allow-stale update <task-id> --status closed`

## Key Directories

| Inside Container | Purpose |
|-----------------|---------|
| `~/khan/` | Code workspace (git worktree) |
| `~/context-sync/` | Confluence/JIRA docs (read-only) |
| `~/sharing/incoming/` | Tasks from Slack |
| `~/sharing/notifications/` | Outgoing notifications |
| `~/sharing/context/` | Saved context (persists) |
| `~/beads/` | Task tracking database |

## See Also

- [Setup Guides](../setup/) - Initial installation
- [Architecture](../architecture/) - System design
- [Reference](../reference/) - Quick reference docs
- [Slack Quick Reference](../reference/slack-quick-reference.md) - Slack commands
