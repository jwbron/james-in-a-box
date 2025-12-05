# Context Tracking

Use Beads to persist context across container restarts.

**Slack threads**: Use `task_id` from YAML frontmatter as label
**PRs**: Use `PR-XX` as label

```bash
bd --allow-stale list --label "$TASK_ID"  # Find existing context
bd --allow-stale create "Slack: summary" --labels slack-thread,$TASK_ID  # Create new
```

**Note**: `search` only checks title/description. Use `list --label` for labels.
