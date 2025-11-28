# Notification Guidelines

Async notifications to human via Slack.

## When to Send Notifications

**Send for:**
- Found a better approach than requested
- Security concerns or critical issues
- Architecture decisions not in ADRs
- Stuck after reasonable debugging
- Work completed (branch/commits ready for PR)

**Don't send for:**
- Minor implementation details
- Questions answerable from Confluence/ADRs
- Routine status updates

## Sending Notifications

### Option 1: Python Library (Preferred)

```python
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / "khan" / "james-in-a-box" / "jib-container" / "shared"))
from notifications import slack_notify, NotificationContext

# Simple notification
slack_notify("Need Guidance: Topic", "What you need")

# With threading context
ctx = NotificationContext(task_id="task-id", repository="owner/repo")
slack_notify("Title", "Body", context=ctx)
```

### Option 2: File-Based (Legacy)

```bash
cat > ~/sharing/notifications/$(date +%Y%m%d-%H%M%S)-topic.md <<'EOF'
# 🔔 Need Guidance: [Topic]

**Priority**: [Low/Medium/High/Urgent]

## Context
[1-2 sentences: what you're working on]

## Issue
[What you need guidance on]

## Recommendation
[Clear recommendation: "I recommend X because Y"]

## Can I proceed?
- [ ] Yes, proceed with original
- [ ] Yes, proceed with alternative
- [ ] Wait for discussion
EOF
```

## Thread Replies

Include `thread_ts` in YAML frontmatter to reply in existing thread:

```markdown
---
task_id: "task-20251124-111907"
thread_ts: "1732428847.123456"
---
# Response content...
```

## Priority Guidelines

| Priority | When |
|----------|------|
| **Urgent** | Blocks work, security issue, data loss risk |
| **High** | Architectural decision, breaking change |
| **Medium** | Better approach found, skeptical about solution |
| **Low** | Nice-to-have, informational |

## Work Completed Notifications

When you've finished and committed changes:

```markdown
# ✅ Work Completed: [Brief description]

**Repository**: [repo name]
**Branch**: `[branch-name]`
**Commits**: [number]

## What Was Done
[2-3 sentence summary]

## Next Steps
- [ ] Human review commits on branch
- [ ] Create PR
```

## Blocking vs Non-Blocking

| Block (wait for response) | Continue |
|---------------------------|----------|
| Security concerns | Better approach found |
| Ambiguous requirements | Performance optimizations |
| Destructive operations | Minor implementation details |

---
Both methods trigger Slack DM within ~30 seconds.
