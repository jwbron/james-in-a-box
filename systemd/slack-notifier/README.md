# Slack Notifier Service

Systemd service for Slack notification integration.

## Service

**File:** `slack-notifier.service`

Watches `~/.jib-sharing/notifications/` and sends new notifications to Slack.

**Install:**
```bash
bin/host-notify-ctl install
bin/host-notify-ctl enable
```

## Configuration

Requires Slack bot token configured in:
- Environment variable: `SLACK_TOKEN`
- Or config file: `~/.jib-notify/config.json`

See: [Slack Setup Guide](../../docs/setup/slack-quickstart.md)

## Managing

```bash
# Start/stop
bin/host-notify-ctl start
bin/host-notify-ctl stop

# Check status
bin/host-notify-ctl status

# View logs
journalctl --user -u slack-notifier -f
```
