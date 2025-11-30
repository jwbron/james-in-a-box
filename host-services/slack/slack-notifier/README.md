# Slack Notifier

Monitors `~/.jib-sharing/notifications/` and sends Slack DMs when files are created.

**Status**: Operational
**Type**: Host-side systemd service
**Purpose**: Claude → Slack communication (bidirectional with slack-receiver)

## Setup

```bash
cd ~/workspace/james-in-a-box/host-services/slack/slack-notifier
./setup.sh
```

This installs and starts the systemd service.

## Management

```bash
# Check status
systemctl --user status slack-notifier.service

# Restart service
systemctl --user restart slack-notifier.service

# View logs
journalctl --user -u slack-notifier.service -f

# Stop service
systemctl --user stop slack-notifier.service
```

## Files

- `slack-notifier.service` - Systemd service file
- `setup.sh` - Installation script
- `slack-notifier.py` - Inotify-based file watcher
- `slack-app-manifest.yaml` - Slack app configuration manifest

## Features

- Inotify-based file watching (instant detection)
- Batching support (15-second window)
- Thread support (replies in existing threads)
- Automatic retry on failure
- Systemd integration with auto-restart

## Threading Pattern

The notifier supports two notification patterns:

### Pattern 1: Simple Notifications (Single Message)
Creates a single top-level message from a file:
```
YYYYMMDD-HHMMSS-topic.md → Top-level Slack message
```

### Pattern 2: Automated Reports (Summary + Thread)
Creates a top-level summary with detailed thread reply:
```
YYYYMMDD-HHMMSS-topic.md         → Top-level summary message
RESPONSE-YYYYMMDD-HHMMSS-topic.md → Threaded reply with full detail
```

**How it works**:
1. Notifier detects files with matching timestamp in filename
2. Files starting with `RESPONSE-` are posted as thread replies
3. Thread parent is found by matching the timestamp
4. This creates a clean mobile-first experience:
   - Summary visible in feed
   - Full detail accessible in thread

**Used by**:
- Conversation analyzer
- Codebase analyzer
- Other automated analysis tools

See: `jib-container/.claude/rules/notification-template.md` for implementation details
