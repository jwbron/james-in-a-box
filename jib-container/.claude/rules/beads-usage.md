# Beads Reference

> Full docs: `~/repos/james-in-a-box/docs/reference/beads.md`

| Command | Purpose |
|---------|---------|
| `bd --allow-stale list -s in_progress` | Resume work |
| `bd --allow-stale list -l "label"` | Find by label |
| `bd --allow-stale search "text"` | Search title/description |
| `bd --allow-stale ready` | Show unblocked work |
| `bd --allow-stale create "Title" -l label1,label2` | Create task |
| `bd --allow-stale update <id> -s in_progress` | Start working |
| `bd --allow-stale update <id> --claim` | Atomic claim (sets assignee + in_progress) |
| `bd --allow-stale close <id> -r "Summary"` | Complete task |

**Status**: `open` → `in_progress` → `closed` (or `blocked`, `deferred`)

**Labels**: `slack-thread`, `jira-XXXX`, `PR-XX`, `feature`, `bug`

**Short flags**: `-s` status, `-l` labels, `-p` priority, `-t` type, `-r` reason, `-n` limit

**ALWAYS use `--allow-stale`** in ephemeral containers.
