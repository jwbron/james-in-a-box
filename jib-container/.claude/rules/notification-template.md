# Notifications

Send async Slack messages when: better approach found, security concerns, stuck after debugging, work completed.

**Don't send for**: Minor details, questions answerable from docs, routine updates.

```python
from notifications import slack_notify
slack_notify("Need Guidance: Topic", "What you need")
```

Or file-based: `cat > ~/sharing/notifications/$(date +%Y%m%d-%H%M%S)-topic.md`

**Priority**: Urgent (blocks/security) | High (architecture) | Medium (better approach) | Low (FYI)
