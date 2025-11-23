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

### Pull Request Commands
```
/pr create [repo]                - Create draft PR for current branch
/pr create [repo] --ready        - Create ready-for-review PR
```

**How it works:**
1. Detects current branch and base branch (main/master)
2. Uses JIB container to generate PR description with Claude
3. Follows Khan Academy commit template format
4. Pushes branch and creates PR via GitHub CLI
5. Sends notification with PR URL

**Examples:**
```
/pr create                       - Create PR in james-in-a-box
/pr create webapp                - Create PR in ~/khan/webapp
/pr create frontend --ready      - Create non-draft PR
```

**Requirements:**
- GitHub CLI (`gh`) installed and authenticated
- Current branch has commits ahead of base branch
- Branch is not the base branch (main/master)

### Examples
```
/jib restart
/service restart slack-notifier.service
/service logs slack-receiver.service 100
/pr create webapp
help                             - Show available commands
```

Commands execute asynchronously and send results as notifications (~30 seconds).
