# Slack Notifier

Monitors `~/.jib-sharing/notifications/` and sends Slack DMs when files are created.

**Status**: Operational
**Type**: Host-side systemd service
**Purpose**: Claude → Slack communication (bidirectional with slack-receiver)

## Setup

```bash
cd ~/khan/james-in-a-box/components/slack-notifier
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
- `host-notify-slack.py` - Inotify-based file watcher
- `manage_notifier.sh` - Helper utilities

## Features

- Inotify-based file watching (instant detection)
- Batching support (15-second window)
- Thread support (replies in existing threads)
- Automatic retry on failure
- Systemd integration with auto-restart
