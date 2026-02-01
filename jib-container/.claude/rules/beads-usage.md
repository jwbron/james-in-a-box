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
| `bd --allow-stale update <id> --add-label PR-XX` | Add label to existing task |
| `bd --allow-stale close <id> -r "Summary"` | Complete task |

**Status**: `open` → `in_progress` → `closed` (or `blocked`, `deferred`)

**Labels**: `slack-thread`, `jira-XXXX`, `PR-XX`, `feature`, `bug`

**Short flags** (vary by command):
- `-s` status (update, list, search) | `-l` labels (create, list, search, ready)
- `-p` priority (create, update, list, ready) | `-t` type (create, update, list, search, ready)
- `-r` reason (close only) | `-n` limit (list, search, ready only)
- `-a` assignee (create, update, list, search, ready) | `-d` description (create, update)

**Note:** `--notes` has NO short flag. Use full `--notes "text"` or `--append-notes "text"`.

**Update labels**: `--add-label`, `--remove-label`, `--set-labels` (no short flags)

**ALWAYS use `--allow-stale`** in ephemeral containers.
