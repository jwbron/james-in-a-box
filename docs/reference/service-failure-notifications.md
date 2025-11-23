# Service Failure Notifications

Automatic Slack notifications when host systemd services fail.

## Overview

When a systemd service fails on the host, you'll automatically receive a Slack DM with:
- Service status and error details
- Recent log entries (last 50 lines)
- Recommended troubleshooting steps
- Direct commands to investigate and fix

## How It Works

```
Service fails
    ↓
systemd triggers OnFailure=service-failure-notify@%n.service
    ↓
notify-service-failure.sh creates notification file
    ↓
File written to ~/sharing/notifications/
    ↓
host-notify-slack.py detects new file
    ↓
Slack DM sent to you
```

## Installation

**On the host machine** (not in container):

```bash
cd ~/khan/james-in-a-box
./install/setup-failure-notifications.sh
```

This will:
1. Install the failure notification service template
2. Update your service files to use OnFailure directives
3. Reload systemd daemon
4. Show status of affected services

## Services Monitored

- **codebase-analyzer.service** - Daily code analysis
- **conversation-analyzer.service** - Conversation analysis
- **slack-notifier.service** - Notification service itself

## Testing

Test the notification system:

```bash
# On host
systemctl --user start service-failure-notify@test.service
```

You should receive a Slack notification within ~30 seconds.

## Notification Format

Slack messages include:

### Header
```
🚨 Service Failure: codebase-analyzer.service
Priority: High
Time: 2025-11-23 14:30:00
```

### Service Status
Full `systemctl status` output showing:
- Active/inactive state
- Exit code and signal
- Memory/CPU usage
- Recent state changes

### Recent Logs
Last 50 lines from journald for the failed service

### Recommended Actions
1. View live logs: `journalctl --user -u <service> -f`
2. Check status: `systemctl --user status <service>`
3. Restart if needed: `systemctl --user restart <service>`
4. Use control script: `~/khan/james-in-a-box/bin/*-ctl status`

## Troubleshooting

### Not receiving notifications

**Check notification service is installed:**
```bash
systemctl --user cat service-failure-notify@.service
```

**Check services have OnFailure directive:**
```bash
systemctl --user show codebase-analyzer.service -p OnFailure
# Should show: OnFailure=service-failure-notify@%n.service
```

**Check Slack notifier is running:**
```bash
systemctl --user status slack-notifier.service
```

**Test manually:**
```bash
# Create a test notification
~/khan/james-in-a-box/internal/notify-service-failure.sh test.service

# Check file was created
ls -la ~/sharing/notifications/ | grep service-failure
```

### Notification created but no Slack message

1. **Check Slack notifier logs:**
   ```bash
   journalctl --user -u slack-notifier.service -f
   ```

2. **Verify notification file exists:**
   ```bash
   ls ~/sharing/notifications/*service-failure*
   ```

3. **Check Slack token is configured:**
   ```bash
   cat ~/.config/jib-notifier/config.json
   ```

### Too many notifications

If a service is flapping (failing repeatedly), you may get multiple notifications.

**Stop the notifications:**
```bash
systemctl --user stop <service>.service
systemctl --user disable <service>.service
```

**Fix the underlying issue, then re-enable:**
```bash
systemctl --user enable <service>.service
systemctl --user start <service>.service
```

## Configuration

### Add failure notifications to new services

Edit your service file:

```ini
[Unit]
Description=My Custom Service
OnFailure=service-failure-notify@%n.service

[Service]
Type=simple
ExecStart=/path/to/script.sh
...
```

Then reload systemd:
```bash
systemctl --user daemon-reload
```

### Customize notification script

Edit: `~/khan/james-in-a-box/internal/notify-service-failure.sh`

Change:
- Number of log lines included (default: 50)
- Notification format
- Priority level
- Additional context

### Disable for specific service

Remove the OnFailure directive from the service file and reload:

```bash
# Edit service file, remove: OnFailure=...
systemctl --user daemon-reload
```

## Files

```
james-in-a-box/
├── systemd/common/
│   └── service-failure-notify@.service     # Template service
├── internal/
│   └── notify-service-failure.sh           # Notification script
├── install/
│   └── setup-failure-notifications.sh      # Installation script
└── docs/reference/
    └── service-failure-notifications.md    # This file
```

## Security

- **Read-only access**: Script only reads service status
- **Limited writes**: Only writes to ~/sharing/notifications/
- **No credentials**: Uses existing Slack notification system
- **Sandboxed**: Runs with systemd security restrictions

## Related

- [Host Slack Notifier](../architecture/host-slack-notifier.md) - Slack notification system
- [Slack Quick Reference](slack-quick-reference.md) - Slack integration overview
- [Codebase Analyzer](codebase-analyzer.md) - One of the monitored services

## Future Enhancements

- [ ] Rate limiting for flapping services
- [ ] Aggregated digest (multiple failures in one message)
- [ ] Auto-restart after N failures
- [ ] Integration with incident management
- [ ] Failure trend analysis
