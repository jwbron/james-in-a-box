# Slack Thread Context - Persistent Memory via Beads

## Overview

When processing Slack messages, you MUST use the Slack thread ID to maintain persistent context across container restarts. This ensures continuity in conversations even when containers are ephemeral.

**CRITICAL**: Every Slack thread is a conversation. Use the thread ID as a unique key to save/load context from Beads.

## How Thread IDs Work

Slack task files include YAML frontmatter with thread context:
```yaml
---
task_id: "task-20251125-134311"
thread_ts: "1732567891.123456"
channel: "D123ABC456"
---
```

The `task_id` is your primary key for tracking work. The `thread_ts` is the Slack thread timestamp used for response threading.

## MANDATORY Workflow

### When Receiving a Slack Message

**ALWAYS do this FIRST before any other work:**

```bash
# 1. Extract the task ID from the prompt's Message Details section
TASK_ID="task-20251125-134311"  # From the prompt

# 2. Search for existing context in Beads
cd ~/beads
bd --allow-stale search "$TASK_ID"

# 3A. If found - LOAD the context
bd --allow-stale show <found-id>  # Review previous work, decisions, progress

# 3B. If not found - CREATE new task with task ID as label
bd --allow-stale create "Slack: $TASK_ID" --labels slack-thread,"$TASK_ID" --description "Slack thread context for $TASK_ID"
bd --allow-stale update <new-id> --status in_progress
```

**NOTE**: Use `--allow-stale` flag to avoid sync issues in ephemeral containers.

### During Work

**Update Beads with context as you work:**

```bash
# Add notes about decisions, findings, progress
bd --allow-stale update <task-id> --notes "User clarified: X. Implementing Y approach. Related to PR #123."

# If task involves specific files or PRs, document them
bd --allow-stale update <task-id> --notes "Working on files: src/foo.py, src/bar.py. Branch: feature-xyz"
```

### When Completing Work

**ALWAYS save context before the container exits:**

```bash
# Add comprehensive summary for future resumption
bd --allow-stale update <task-id> --notes "Summary: Implemented X, created PR #456. User feedback pending. Next steps: Y, Z."

# If waiting for user response, note what you're waiting for
bd --allow-stale update <task-id> --notes "Awaiting: User decision on caching strategy. Options presented: Redis vs in-memory."
```

## Complete Example

```bash
# Slack message arrives with: Task ID: task-20251125-134311

# Step 1: Check for existing context
cd ~/beads
bd --allow-stale search "task-20251125-134311"

# Result: Found existing task beads-abc123
bd --allow-stale show beads-abc123
# Shows: "User asked about OAuth2 implementation. I proposed using httpOnly cookies per ADR-042.
#         Waiting for approval. Files affected: auth/oauth.py, auth/session.py"

# Step 2: User's response is: "Yes, proceed with httpOnly cookies"

# Step 3: Update context with new information
bd --allow-stale update beads-abc123 --status in_progress
bd --allow-stale update beads-abc123 --notes "User approved httpOnly cookies approach. Implementing now."

# Step 4: Do the work...

# Step 5: Update context with results
bd --allow-stale update beads-abc123 --notes "Implemented OAuth2 with httpOnly cookies. PR #789 created. Tests passing."
bd --allow-stale update beads-abc123 --status closed
```

## Why This Matters

1. **Containers are ephemeral**: Each Slack message may spawn a new container
2. **Context must persist**: Without Beads, you lose all memory between messages
3. **Threads are conversations**: Users expect you to remember the thread's history
4. **Avoid confusion**: Loading context prevents asking the same questions twice

## Thread ID Formats

Task IDs may appear in these formats:
- `task-YYYYMMDD-HHMMSS` - New task format
- `response-YYYYMMDD-HHMMSS` - Response to existing thread
- `YYYYMMDD-HHMMSS` - Timestamp only

All should be used as search terms and labels in Beads.

## Full Thread Context

When a message arrives as a thread reply, the incoming processor provides full thread history in the prompt under "## Thread Context". This includes all previous messages in the conversation - use this to understand the full context before responding.

## Integration with Other Rules

This rule works alongside:
- **beads-usage.md**: General Beads workflow (this adds Slack-specific requirements)
- **mission.md**: Overall agent behavior (context preservation supports autonomy)
- **notification-template.md**: When sending notifications, include thread context

## Quick Reference

| When | Action |
|------|--------|
| Message arrives | `bd --allow-stale search "$TASK_ID"` |
| New thread | `bd --allow-stale create "Slack: $TASK_ID" --labels slack-thread,"$TASK_ID"` |
| Existing thread | `bd --allow-stale show <id>` then `bd --allow-stale update <id> --status in_progress` |
| During work | `bd --allow-stale update <id> --notes "Progress..."` |
| Before exit | `bd --allow-stale update <id> --notes "Summary and next steps..."` |

**Remember**: The task ID is your key to persistent memory. NEVER process a Slack message without first checking Beads for existing context.
