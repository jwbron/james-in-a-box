# Communication Features

Bidirectional Slack integration for human-agent communication.

## Overview

JIB provides seamless two-way communication with humans via Slack:
- **Outbound**: Agent sends notifications, status updates, and questions
- **Inbound**: Humans send tasks, commands, and feedback via DMs

## Features

### Slack Notifier Service

**Purpose**: Sends Slack DMs when the agent needs to communicate with humans.

**Location**: `host-services/slack/slack-notifier/`

**Helper Scripts**:
```bash
# Setup
bin/setup-slack-notifier

# Service management
systemctl --user status slack-notifier.service
systemctl --user restart slack-notifier.service
journalctl --user -u slack-notifier.service -f
```

**Usage** (from within container):
```python
from notifications import slack_notify, NotificationContext

# Simple notification
slack_notify("Need Guidance: Topic", "What you need guidance on")

# With threading context
ctx = NotificationContext(task_id="task-id", repository="owner/repo")
slack_notify("Title", "Body", context=ctx)
```

**Configuration**: `~/.jib-sharing/.env`
- `SLACK_TOKEN`: Bot token (xoxb-...)
- `SLACK_DEFAULT_CHANNEL`: Default DM user ID

**Key Capabilities**:
- Thread replies via YAML frontmatter
- Message batching (15-second window)
- Auto-chunking for long content
- Automatic retry on failures

### Slack Receiver Service

**Purpose**: Receives incoming Slack DMs and triggers container processing.

**Location**: `host-services/slack/slack-receiver/`

**Helper Scripts**:
```bash
# Setup
bin/setup-slack-receiver

# Service management
systemctl --user status slack-receiver.service
systemctl --user restart slack-receiver.service
journalctl --user -u slack-receiver.service -f
```

**Remote Control Commands** (via Slack DM):
```
/jib status      # Container status
/jib restart     # Restart container
/jib rebuild     # Rebuild container
/jib logs        # Recent logs

/service list    # List all services
/service status <name>  # Service status
/service restart <name> # Restart service
```

**Configuration**: `~/.jib-sharing/.env`
- `SLACK_APP_TOKEN`: App-level token (xapp-...)
- `SLACK_ALLOWED_USERS`: Comma-separated user IDs

**Key Capabilities**:
- Thread context preservation
- User authentication/allowlisting
- Container process monitoring
- Message chunking

### Slack Message Processor

**Purpose**: Container-side processor for incoming Slack messages.

**Location**: `jib-container/jib-tasks/slack/incoming-processor.py`

**Invoked by**: Slack receiver via `jib --exec`

**Key Capabilities**:
- Routes messages to Claude Code for task execution
- YAML frontmatter parsing for thread context
- Automatic success/failure notifications
- Beads integration for task tracking

### Container Notifications Library

**Purpose**: Python library for sending notifications from container code.

**Location**: `shared/notifications.py`

**Usage Examples**:
```python
from notifications import (
    slack_notify,
    NotificationContext,
    get_slack_service
)

# Simple notification
slack_notify("Title", "Body content")

# With context for threading
ctx = NotificationContext(
    task_id="my-task",
    repository="owner/repo",
    pr_number=123
)
slack_notify("PR Update", "Changes pushed", context=ctx)

# Specialized notifications
slack = get_slack_service()
slack.notify_pr_created(url, title, branch, base, repo)
slack.notify_code_pushed(branch, repo, commit_message)
```

## Architecture

```
[Human via Slack DM]
        │
        ▼
┌─────────────────┐     ┌─────────────────┐
│  Slack Receiver │────▶│  jib --exec     │
│   (host-side)   │     │  (container)    │
└─────────────────┘     └─────────────────┘
        │                       │
        │                       ▼
        │               ┌─────────────────┐
        │               │ Claude Code     │
        │               │ processes task  │
        │               └─────────────────┘
        │                       │
        │                       ▼
        │               ┌─────────────────┐
        │               │ notifications/  │
        │               │ directory       │
        │               └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  Slack Notifier │◀────│ File watcher    │
│   (host-side)   │     │                 │
└─────────────────┘     └─────────────────┘
        │
        ▼
[Human receives DM]
```

## Troubleshooting

### Notifications not sending

1. Check notifier service: `systemctl --user status slack-notifier.service`
2. Verify token: `echo $SLACK_TOKEN` (should start with xoxb-)
3. Check logs: `journalctl --user -u slack-notifier.service -n 50`

### Messages not received

1. Check receiver service: `systemctl --user status slack-receiver.service`
2. Verify app token: Must be xapp- format
3. Check user allowlist in `.env`

### Thread replies not working

1. Ensure `thread_ts` is in YAML frontmatter
2. Check `task_id` is consistent across messages
3. Verify NotificationContext includes thread info

## Related Documentation

- [Slack Integration Architecture](../architecture/slack-integration.md)
- [Host Slack Notifier Details](../architecture/host-slack-notifier.md)
- [Slack Quickstart](../setup/slack-quickstart.md)
- [Slack App Setup](../setup/slack-app-setup.md)
- [Slack Bidirectional Setup](../setup/slack-bidirectional.md)

## Source Files

| Component | Path |
|-----------|------|
| Slack Notifier | `host-services/slack/slack-notifier/slack-notifier.py` |
| Slack Receiver | `host-services/slack/slack-receiver/slack-receiver.py` |
| Message Processor | `jib-container/jib-tasks/slack/incoming-processor.py` |
| Notifications Library | `shared/notifications.py` |
| Host Command Handler | `host-services/slack/slack-receiver/host_command_handler.py` |

---

*Auto-generated by Feature Analyzer*
