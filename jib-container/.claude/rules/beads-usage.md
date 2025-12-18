# Beads Reference

> Full docs: `~/repos/james-in-a-box/docs/reference/beads.md`

| Command | Purpose |
|---------|---------|
| `bd --allow-stale list --status in_progress` | Resume work |
| `bd --allow-stale list --label "task-id"` | Find by label |
| `bd --allow-stale search "text"` | Search title/description |
| `bd --allow-stale create "Title" --labels type,source` | Create task |
| `bd --allow-stale update <id> --status closed --notes "Summary"` | Complete |

**Status**: `open` → `in_progress` → `closed` (or `blocked`)

**Labels**: `slack-thread`, `jira-XXXX`, `PR-XX`, `feature`, `bug`

**ALWAYS use `--allow-stale`** in ephemeral containers.
