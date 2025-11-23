# Slack Notifier

Monitors `~/sharing/notifications/` and sends Slack DMs.

## Files
- `host-notify-ctl` - Control script
- `host-notify-slack.py` - Main watcher
- `slack-notifier.service` - Systemd service
- `setup.sh` - Installation

## Usage
```bash
./host-notify-ctl start|stop|status|logs
```
