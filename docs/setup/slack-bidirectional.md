# Bidirectional Slack Communication

Two-way Slack communication with Claude.

## What This Enables

- **Claude → You**: Notifications when Claude needs guidance or completes work
- **You → Claude**: Send tasks and respond to notifications via Slack DM
- **Remote access**: Control Claude from anywhere (phone, laptop)

## Prerequisites

1. Completed [Slack App Setup](slack-app-setup.md)
2. Both tokens configured (`xoxb-...` and `xapp-...`)
3. Services installed via `./setup.sh`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  You (Slack)                                            │
│  - DM yourself with "claude: <task>"                    │
│  - Reply to notification threads                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Host: slack-receiver.service                           │
│  - Monitors Slack via Socket Mode                       │
│  - Writes to ~/.jib-sharing/incoming/                   │
│  - Writes to ~/.jib-sharing/responses/                  │
└────────────────────┬────────────────────────────────────┘
                     │ (mounted)
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Container: incoming-watcher                            │
│  - Monitors ~/sharing/incoming/ and ~/sharing/responses/│
│  - Processes tasks for Claude                           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Container: Claude                                      │
│  - Reads incoming tasks                                 │
│  - Writes to ~/sharing/notifications/                   │
└────────────────────┬────────────────────────────────────┘
                     │ (mounted)
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Host: slack-notifier.service                           │
│  - Monitors ~/.jib-sharing/notifications/               │
│  - Batches changes (30 seconds)                         │
│  - Sends Slack DMs                                      │
└─────────────────────────────────────────────────────────┘
```

## Setup

### 1. Run Main Setup

```bash
cd ~/repos/james-in-a-box
./setup.sh
```

This installs and starts both services:
- `slack-notifier.service` - Outgoing notifications
- `slack-receiver.service` - Incoming messages

### 2. Verify Services

```bash
systemctl --user status slack-notifier slack-receiver
```

Both should show `active (running)`.

### 3. Start Container

```bash
bin/jib
```

The incoming-watcher starts automatically inside the container.

## Usage

### Send a Task to Claude

DM yourself in Slack:
```
claude: Implement the user authentication feature
```

You'll get a confirmation:
```
✅ Task received and queued for Claude
📁 Saved to: task-20251121-153100.md
```

### Respond to a Notification

When Claude sends a notification asking for guidance:

1. Click **"Reply in thread"** on the notification
2. Type your response
3. Send

The response is delivered to Claude via `~/sharing/responses/`.

### Check What Claude is Working On

Send:
```
claude: What are you working on?
```

## File Locations

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `~/.jib-sharing/incoming/` | `~/sharing/incoming/` | New tasks from Slack |
| `~/.jib-sharing/responses/` | `~/sharing/responses/` | Thread responses |
| `~/.jib-sharing/notifications/` | `~/sharing/notifications/` | Outgoing notifications |

## Troubleshooting

### Not Receiving Notifications

```bash
# Check notifier is running
systemctl --user status slack-notifier

# View logs
journalctl --user -u slack-notifier -n 50

# Test manually
echo "Test" > ~/.jib-sharing/notifications/test.md
# Should appear in Slack within 30 seconds
```

### Claude Not Receiving Tasks

```bash
# Check receiver is running
systemctl --user status slack-receiver

# View logs
journalctl --user -u slack-receiver -n 50

# Check incoming directory
ls -la ~/.jib-sharing/incoming/

# Inside container, check watcher
docker exec -it jib-claude bash
ls -la ~/sharing/incoming/
```

### Socket Mode Connection Failed

1. Verify Socket Mode is enabled in Slack app
2. Check app token (`xapp-...`) is correct
3. View receiver logs for specific error

### Permission Errors

```bash
# Ensure correct permissions
chmod 700 ~/.config/jib-notifier
chmod 600 ~/.config/jib-notifier/config.json
chmod 755 ~/.jib-sharing
```

## Auto-Start on Boot

Services are enabled by default during setup. Verify with:

```bash
systemctl --user is-enabled slack-notifier
systemctl --user is-enabled slack-receiver
```

To enable lingering (services start before login):
```bash
loginctl enable-linger $USER
```

## Configuration

Edit `~/.config/jib-notifier/config.json`:

```json
{
  "slack_token": "xoxb-...",
  "slack_app_token": "xapp-...",
  "slack_channel": "D07S8SAB5FE",
  "owner_user_id": "U07SK26JPJ5",
  "allowed_users": ["U07SK26JPJ5"],
  "batch_window_seconds": 30
}
```

After editing, restart services:
```bash
systemctl --user restart slack-notifier slack-receiver
```

## See Also

- [Slack Quick Reference](../reference/slack-quick-reference.md) - Daily usage
- [Slack App Setup](slack-app-setup.md) - Token configuration
- [Architecture: Slack Integration](../architecture/slack-integration.md) - Design details
