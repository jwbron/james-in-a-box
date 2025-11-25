# Slack Thread Context - Persistent Memory via Beads

## Overview

When processing Slack messages, you MUST use the Slack thread ID to maintain persistent context across container restarts. This ensures continuity in conversations even when containers are ephemeral.

**CRITICAL**: Every Slack thread is a conversation. Use the thread ID as a unique key to save/load context from Beads.

## How Thread IDs Work

Slack thread responses include a **Thread Context** section with a Task ID:
```
## Thread Context
**Task ID:** `response-20251125-134311`
```

This Task ID is derived from the thread's parent message timestamp and serves as a unique identifier for the conversation.

## MANDATORY Workflow

### When Receiving a Slack Message

**ALWAYS do this FIRST before any other work:**

```bash
# 1. Extract the thread ID from the prompt (Task ID in Thread Context)
THREAD_ID="response-20251125-134311"  # From the prompt's Thread Context

# 2. Search for existing context in Beads
cd ~/beads
bd list --search "$THREAD_ID"

# 3A. If found - LOAD the context
bd show <found-id>  # Review previous work, decisions, progress

# 3B. If not found - CREATE new task with thread ID as tag
bd create "Slack thread: $THREAD_ID" --label slack-thread --label "$THREAD_ID"
```

### During Work

**Update Beads with context as you work:**

```bash
# Add notes about decisions, findings, progress
bd update <task-id> --notes "User clarified: X. Implementing Y approach. Related to PR #123."

# If task involves specific files or PRs, document them
bd update <task-id> --notes "Working on files: src/foo.py, src/bar.py. Branch: feature-xyz"
```

### When Completing Work

**ALWAYS save context before the container exits:**

```bash
# Add comprehensive summary for future resumption
bd update <task-id> --notes "Summary: Implemented X, created PR #456. User feedback pending. Next steps: Y, Z."

# If waiting for user response, note what you're waiting for
bd update <task-id> --notes "Awaiting: User decision on caching strategy. Options presented: Redis vs in-memory."
```

## Complete Example

```bash
# Slack message arrives with: Task ID: response-20251125-134311

# Step 1: Check for existing context
cd ~/beads
bd list --search "response-20251125-134311"

# Result: Found existing task beads-abc123
bd show beads-abc123
# Shows: "User asked about OAuth2 implementation. I proposed using httpOnly cookies per ADR-042.
#         Waiting for approval. Files affected: auth/oauth.py, auth/session.py"

# Step 2: User's response is: "Yes, proceed with httpOnly cookies"

# Step 3: Update context with new information
bd update beads-abc123 --status in_progress
bd update beads-abc123 --notes "User approved httpOnly cookies approach. Implementing now."

# Step 4: Do the work...

# Step 5: Update context with results
bd update beads-abc123 --notes "Implemented OAuth2 with httpOnly cookies. PR #789 created. Tests passing."
bd update beads-abc123 --status done
```

## Why This Matters

1. **Containers are ephemeral**: Each Slack message may spawn a new container
2. **Context must persist**: Without Beads, you lose all memory between messages
3. **Threads are conversations**: Users expect you to remember the thread's history
4. **Avoid confusion**: Loading context prevents asking the same questions twice

## Thread ID Formats

Thread IDs may appear in these formats:
- `response-YYYYMMDD-HHMMSS` - Standard response format
- `task-YYYYMMDD-HHMMSS` - New task format
- `YYYYMMDD-HHMMSS` - Timestamp only

All should be used as search terms and tags in Beads.

## Integration with Other Rules

This rule works alongside:
- **beads-usage.md**: General Beads workflow (this adds Slack-specific requirements)
- **mission.md**: Overall agent behavior (context preservation supports autonomy)
- **notification-template.md**: When sending notifications, include thread context

## Quick Reference

| When | Action |
|------|--------|
| Message arrives | `bd list --search "$THREAD_ID"` |
| New thread | `bd create "..." --label slack-thread --label "$THREAD_ID"` |
| Existing thread | `bd show <id>` then `bd update <id> --status in_progress` |
| During work | `bd update <id> --notes "Progress..."` |
| Before exit | `bd update <id> --notes "Summary and next steps..."` |

**Remember**: The thread ID is your key to persistent memory. NEVER process a Slack message without first checking Beads for existing context.
