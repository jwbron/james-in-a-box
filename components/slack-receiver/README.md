# Slack Receiver

Receives incoming Slack messages (DMs) and writes them to `~/.jib-sharing/incoming/` where the container can pick them up.

**Status**: Operational
**Type**: Host-side systemd service
**Purpose**: Slack → Claude communication (bidirectional with slack-notifier)

## Setup

```bash
cd ~/khan/james-in-a-box/components/slack-receiver
./setup.sh
```

This installs and starts the systemd service.

## Management

```bash
# Check status
systemctl --user status slack-receiver.service

# Restart service
systemctl --user restart slack-receiver.service

# View logs
journalctl --user -u slack-receiver.service -f

# Stop service
systemctl --user stop slack-receiver.service
```

## Files

- `slack-receiver.service` - Systemd service file
- `setup.sh` - Installation script
- `host-receive-slack.py` - Slack Socket Mode receiver
- `incoming-watcher.sh` - Monitor incoming directory

## Features

- Socket Mode (no webhook endpoint needed)
- Thread context detection
- Full conversation history in task files
- User authentication and allowlisting
- **Remote control commands** (restart/rebuild container, manage services)

## Remote Control Commands

Control JIB remotely via Slack DMs:

### Container Commands
```
/jib status          - Check container status
/jib restart         - Restart container
/jib rebuild         - Rebuild and restart container
/jib logs            - Show recent container logs
```

### Service Commands
```
/service list                    - List all JIB services
/service status <name>           - Check service status
/service restart <name>          - Restart a service
/service start <name>            - Start a service
/service stop <name>             - Stop a service
/service logs <name> [lines]     - Show service logs
```

### Examples
```
/jib restart
/service restart slack-notifier.service
/service logs slack-receiver.service 100
help                             - Show available commands
```

Commands execute asynchronously and send results as notifications (~30 seconds).
