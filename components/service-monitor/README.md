# Service Monitor

Sends Slack notifications when jib services fail.

**Status**: Operational
**Type**: Host-side systemd service template
**Purpose**: Monitor service health and alert on failures

## Setup

```bash
cd ~/khan/james-in-a-box/components/service-monitor
./setup.sh
```

This installs the service template and configures failure notifications.

## How It Works

When a monitored service fails, systemd triggers `service-failure-notify@<service-name>.service`, which:
1. Writes notification to `~/.jib-sharing/notifications/`
2. Slack notifier picks it up (~30 seconds)
3. You receive DM with failure details

## Monitored Services

- `codebase-analyzer.service`
- `conversation-analyzer.service`
- `slack-notifier.service`
- `slack-receiver.service`

## Testing

```bash
# Trigger test notification
systemctl --user start service-failure-notify@test.service

# Check notifications directory
ls ~/.jib-sharing/notifications/
```

## Files

- `notify-service-failure.sh` - Notification script
- `service-failure-notify@.service` - Systemd service template
- `setup.sh` - Installation script

## Management

The service template doesn't need management - it's triggered automatically by systemd on failures.

To check if it's installed:
```bash
systemctl --user list-unit-files | grep service-failure-notify
```
