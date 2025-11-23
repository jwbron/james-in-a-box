# Slack Notifier - Quick Start

Monitor `~/.jib-sharing/` for changes and send Slack notifications.

## Prerequisites

Install Python dependencies:

```bash
pip install --user inotify requests
```

## One-Time Setup

```bash
cd ~/khan/james-in-a-box/jib-notifier

# 1. Configure Slack token
./manage_notifier.sh setup

# 2. Enable the systemd service
./manage_notifier.sh enable
```

Done! The notifier is now running in the background.

## Setup Details

During setup you'll need:

1. **Slack Bot Token** (starts with `xoxb-`)
   - Get from: https://api.slack.com/apps
   - Required scopes: `chat:write`

2. **Slack Channel ID** (required)
   - For DMs: Find your DM channel ID (see instructions below)
   - For channels: `#channel-name` or channel ID
   - **How to find**: Open Slack in browser, navigate to DM/channel, copy ID from URL: `https://workspace.slack.com/archives/<CHANNEL_ID>`

Configuration is saved to `~/.config/jib-notifier/config.json` with secure permissions (600).

## Usage

### Check Status

```bash
./manage_notifier.sh status
```

### View Logs

```bash
# Recent logs
./manage_notifier.sh logs

# Follow in real-time
./manage_notifier.sh logs-follow
```

### Control Service

```bash
# Start (if stopped)
./manage_notifier.sh start

# Stop
./manage_notifier.sh stop

# Restart
./manage_notifier.sh restart

# Disable (stop and prevent auto-start)
./manage_notifier.sh disable
```

## How It Works

1. **Monitors**: Watches `~/.jib-sharing/` for file changes
2. **Batches**: Collects changes over 30-second window
3. **Notifies**: Sends Slack DM with list of changed files
4. **Runs continuously**: Systemd service ensures it's always running

## Example Notification

```
🔔 Claude Sandbox Changes Detected

.jib-sharing/ (`/home/jwies/.jib-sharing`):
  • `notifications/summary-2025-01-15.md`
  • `context-tracking/updates.md`

Total changes: 2
```

## Configuration

Edit `~/.config/jib-notifier/config.json`:

```json
{
  "slack_token": "xoxb-your-token",
  "slack_channel": "<YOUR-CHANNEL-ID>",  // Replace with your actual Slack channel/DM ID
  "batch_window_seconds": 30,
  "watch_directories": [
    "/home/jwies/.jib-sharing"
  ]
}
```

After editing, restart:
```bash
./manage_notifier.sh restart
```

## File Locations

### Configuration and Logs
- **Config**: `~/.config/jib-notifier/config.json` (permissions: 600)
- **Logs**: `~/.config/jib-notifier/notifier.log`
- **Systemd logs**: `journalctl --user -u slack-notifier`

### Service Files
- **Service**: `~/.config/systemd/user/jib-notifier.service` (symlink)
- **Source**: `~/khan/james-in-a-box/jib-notifier/systemd/jib-notifier.service`
- **Script**: `~/khan/james-in-a-box/scripts/host-notify-slack.py`

### Runtime
- **Lock file**: `/tmp/jib-notifier.lock`

## Testing

Test the notifier by creating a file:

```bash
# Create a test file
echo "test" > ~/.jib-sharing/test.txt

# Wait 30 seconds (batch window)

# Check Slack for notification
```

View what happened:
```bash
./manage_notifier.sh logs
```

## Troubleshooting

### Service Won't Start

```bash
# Check status
./manage_notifier.sh status

# View logs
./manage_notifier.sh logs

# Check Python dependencies
python3 -c "import inotify, requests; print('Dependencies OK')"
```

### No Notifications

```bash
# Check if service is running
./manage_notifier.sh status

# Verify config
cat ~/.config/jib-notifier/config.json

# Test Slack token
python3 ~/khan/james-in-a-box/scripts/host-notify-slack.py
# (will start in foreground, Ctrl+C to stop)
```

### Invalid Slack Token

```bash
# Reconfigure
./manage_notifier.sh setup

# Restart service
./manage_notifier.sh restart
```

## Integration with Claude Sandbox

This notifier complements the james-in-a-box (jib) workflow:

```
┌─────────────────────────────────────┐
│  Claude in Container                │
│  - Analyzes context                 │
│  - Creates summaries                │
│  - Stages changes                   │
│  └─> Writes to ~/sharing/           │
└─────────────────────────────────────┘
              │
              ▼ (mounted to host)
┌─────────────────────────────────────┐
│  Host: ~/.jib-sharing/   │
└─────────────────────────────────────┘
              │
              ▼ (inotify watches)
┌─────────────────────────────────────┐
│  Slack Notifier                     │
│  - Detects changes                  │
│  - Batches updates                  │
│  └─> Sends Slack DM                 │
└─────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────┐
│  You get notified                   │
│  - Review changes                   │
│  - Take action                      │
└─────────────────────────────────────┘
```

## Uninstall

```bash
# Stop and disable
./manage_notifier.sh disable

# Remove symlink
rm ~/.config/systemd/user/jib-notifier.service
systemctl --user daemon-reload

# Optionally remove config
rm -rf ~/.config/jib-notifier/
```

## Security Notes

- Configuration stored in `~/.config/jib-notifier/` (permissions: 700)
- Config file has permissions 600 (only you can read)
- Slack token never written to logs
- Runs as your user (no elevated privileges)

## Next Steps

1. Get Slack bot token from https://api.slack.com/apps
2. Run setup: `./manage_notifier.sh setup`
3. Enable service: `./manage_notifier.sh enable`
4. Test by creating a file in `~/.jib-sharing/`
5. Check Slack for notification!
