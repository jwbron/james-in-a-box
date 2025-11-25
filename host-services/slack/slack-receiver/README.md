# Slack Receiver

Receives incoming Slack messages (DMs) and writes them to `~/.jib-sharing/incoming/` where the container can pick them up.

**Status**: Operational
**Type**: Host-side systemd service
**Purpose**: Slack → Claude communication (bidirectional with slack-notifier)

## Setup

```bash
cd ~/khan/james-in-a-box/host-services/slack/slack-receiver
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
- `slack-receiver.py` - Slack Socket Mode receiver (triggers processing via `jib --exec`)
- `remote-control.sh` - Remote control command handler
- `create-pr.sh` - PR creation helper script

## How It Works

```
Slack DM received
        ↓
slack-receiver.py (Socket Mode)
        ↓
Write message to ~/.jib-sharing/incoming/ or ~/.jib-sharing/responses/
        ↓
Trigger processing via `jib --exec incoming-processor.py <message-file>`
        ↓
jib Container (one-time processing)
incoming-processor.py reads message → creates notification → exits
        ↓
Notification sent to Slack via slack-notifier
```

This exec-based pattern ensures processing only runs when messages are received (event-driven).

## Features

- Socket Mode (no webhook endpoint needed)
- Thread context detection
- Full conversation history in task files
- User authentication and allowlisting
- **Remote control commands** (restart/rebuild container, manage services)
- **Event-driven processing** via `jib --exec` (no background watchers)

## Remote Control Commands

Control jib remotely via Slack DMs:

### Container Commands
```
/jib status          - Check container status
/jib restart         - Restart container
/jib rebuild         - Rebuild and restart container
/jib logs            - Show recent container logs
```

### Service Commands
```
/service list                    - List all jib services
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
2. Uses jib container to generate PR description with Claude
3. Follows Khan Academy commit template format
4. Pushes branch and creates PR via GitHub CLI
5. Sends notification with PR URL and branch details

**Notification includes:**
- Repository name
- Source branch (your changes)
- Target branch (merging into)
- Draft/ready status
- PR URL and description preview

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
