# Slack Integration - Quick Start

Get Slack notifications working in 10 minutes.

## Prerequisites

- Python 3.x
- [uv](https://docs.astral.sh/uv/) (installed automatically by setup.sh)
- A Slack workspace you can add apps to

## Quick Setup

The main setup script handles everything:

```bash
cd ~/workspace/james-in-a-box
./setup.sh
```

This will:
1. Install Python dependencies (slack-sdk)
2. Prompt for Slack tokens
3. Configure and start the notifier and receiver services

## Manual Setup (if needed)

### 1. Install Dependencies

```bash
cd ~/workspace/james-in-a-box/host-services
uv sync
```

### 2. Create Slack App

See [Slack App Setup](slack-app-setup.md) for detailed instructions. You'll need:
- **Bot Token** (`xoxb-...`) - For sending messages
- **App Token** (`xapp-...`) - For Socket Mode (receiving messages)

### 3. Configure and Start Services

```bash
# Slack notifier (Claude → You)
cd ~/workspace/james-in-a-box/host-services/slack/slack-notifier
./setup.sh

# Slack receiver (You → Claude)
cd ~/workspace/james-in-a-box/host-services/slack/slack-receiver
./setup.sh
```

## Configuration

Tokens are stored in `~/.config/jib-notifier/config.json`:

```json
{
  "slack_token": "xoxb-your-bot-token",
  "slack_app_token": "xapp-your-app-token",
  "slack_channel": "D07S8SAB5FE",
  "owner_user_id": "U07SK26JPJ5"
}
```

## Verify It's Working

```bash
# Check service status
systemctl --user status slack-notifier
systemctl --user status slack-receiver

# View logs
journalctl --user -u slack-notifier -f
journalctl --user -u slack-receiver -f
```

## Test Notifications

```bash
# Create a test notification
echo "Test notification" > ~/.jib-sharing/notifications/test-$(date +%s).md

# Wait ~30 seconds, check Slack for DM
```

## Test Receiving Messages

1. Open Slack and DM yourself
2. Send: `claude: test task`
3. Check `~/.jib-sharing/incoming/` for the task file

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Service won't start | Check `journalctl --user -u <service> -n 50` |
| No notifications | Verify token in config, check notifier logs |
| Can't receive messages | Ensure Socket Mode enabled in Slack app |
| Invalid token | Regenerate from https://api.slack.com/apps |

## Next Steps

- [Slack App Setup](slack-app-setup.md) - Detailed Slack app configuration
- [Bidirectional Setup](slack-bidirectional.md) - Two-way communication details
- [Slack Quick Reference](../reference/slack-quick-reference.md) - Daily usage
