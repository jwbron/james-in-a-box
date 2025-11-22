# Host-Side Slack Notifier

Monitors shared directories on the **host machine** (outside the container) and sends Slack DMs when changes are detected.

## Overview

This system watches:
- `~/.claude-sandbox-sharing/` - Shared data between host and container
- `~/.claude-sandbox-tools/` - Shared tools directory

When changes are detected, it sends a Slack direct message to James Wiesebron with a summary of what changed.

## Prerequisites

### 1. Install Dependencies (Host Machine)

**Fedora/RHEL:**
```bash
sudo dnf install inotify-tools jq
```

**Ubuntu/Debian:**
```bash
sudo apt install inotify-tools jq
```

**macOS:**
```bash
brew install fswatch jq
# Note: The script uses inotifywait (Linux). For macOS, you'll need to modify it to use fswatch.
```

### 2. Get a Slack Bot Token

1. Go to https://api.slack.com/apps
2. Click "Create New App" or select an existing app
3. Choose "From scratch"
4. Name it "Claude Notifier" and select your workspace
5. Go to "OAuth & Permissions" in the sidebar
6. Scroll to "Scopes" → "Bot Token Scopes"
7. Add these scopes:
   - `chat:write` - Send messages
   - `channels:history` - Read channel history (if needed)
8. Click "Install to Workspace" at the top
9. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

### 3. Set Environment Variable

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
export SLACK_TOKEN="xoxb-your-token-here"
```

Then reload:
```bash
source ~/.bashrc
```

Or set it temporarily for testing:
```bash
export SLACK_TOKEN="xoxb-your-token-here"
```

## Usage

### Start the Notifier

```bash
# Make sure SLACK_TOKEN is set
export SLACK_TOKEN="xoxb-your-token-here"

# Start the service
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh start
```

### Check Status

```bash
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh status
```

### View Logs

```bash
# View all logs
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh logs

# Tail logs (live view)
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh tail
```

### Stop the Notifier

```bash
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh stop
```

### Restart

```bash
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh restart
```

## How It Works

### Change Detection

The script uses `inotifywait` to monitor file system events:
- **CREATE** - New files created
- **MODIFY** - Files modified
- **DELETE** - Files deleted
- **MOVE** - Files moved/renamed

### Batching

To avoid spam, changes are batched over a 30-second window. All changes within 30 seconds are grouped into a single Slack message.

### Message Format

```
🔔 Claude Sandbox Changes Detected

Sharing Directory (~/.claude-sandbox-sharing/):
  • notifications/summary-2025-01-15.md
  • context-tracking/watcher-state.json

Tools Directory (~/.claude-sandbox-tools/):
  • scripts/new-helper.sh

Total changes: 3
```

### Filtering

The script automatically filters out:
- Temporary files (`.swp`, `.tmp`, `.lock`)
- Git metadata (`.git/` directories)
- Other noise

## Configuration

### Change Watched Directories

Edit `~/khan/cursor-sandboxed/scripts/host-notify-slack.sh`:

```bash
WATCH_DIRS=(
    "${HOME}/.claude-sandbox-sharing"
    "${HOME}/.claude-sandbox-tools"
    "${HOME}/context-sync"  # Add more directories
)
```

### Change Batch Window

Edit the `BATCH_WINDOW` variable:

```bash
BATCH_WINDOW=30  # seconds (default: 30)
```

Increase for less frequent notifications, decrease for more real-time updates.

### Change Slack Channel

To send to a different channel/user, update `SLACK_CHANNEL`:

```bash
SLACK_CHANNEL="D04CMDR7LBT"  # DM channel ID
# Or use a channel name:
SLACK_CHANNEL="#notifications"
```

## Auto-Start on Boot

### systemd (Linux)

Create `/etc/systemd/system/claude-notifier.service`:

```ini
[Unit]
Description=Claude Sandbox Slack Notifier
After=network.target

[Service]
Type=simple
User=jwies
Environment="SLACK_TOKEN=xoxb-your-token-here"
ExecStart=/home/jwies/khan/cursor-sandboxed/scripts/host-notify-slack.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable claude-notifier
sudo systemctl start claude-notifier
sudo systemctl status claude-notifier
```

### User Session (No sudo)

Create `~/.config/systemd/user/claude-notifier.service`:

```ini
[Unit]
Description=Claude Sandbox Slack Notifier
After=network.target

[Service]
Type=simple
Environment="SLACK_TOKEN=xoxb-your-token-here"
ExecStart=%h/khan/cursor-sandboxed/scripts/host-notify-slack.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

Enable and start:
```bash
systemctl --user daemon-reload
systemctl --user enable claude-notifier
systemctl --user start claude-notifier
systemctl --user status claude-notifier
```

### Manual Auto-Start

Add to `~/.bashrc`:

```bash
# Auto-start Claude notifier
if [ -n "$SLACK_TOKEN" ] && ! pgrep -f host-notify-slack.sh > /dev/null; then
    ~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh start >/dev/null 2>&1
fi
```

## Troubleshooting

### "inotifywait not found"

Install inotify-tools:
```bash
# Fedora
sudo dnf install inotify-tools

# Ubuntu
sudo apt install inotify-tools
```

### "jq not found"

Install jq:
```bash
# Fedora
sudo dnf install jq

# Ubuntu
sudo apt install jq
```

### "SLACK_TOKEN environment variable not set"

Make sure to export the token:
```bash
export SLACK_TOKEN="xoxb-your-token-here"
```

Add it to `~/.bashrc` to persist across sessions.

### "Failed to send Slack message: invalid_auth"

Your Slack token is invalid or expired. Get a new token from https://api.slack.com/apps

### "Failed to send Slack message: missing_scope"

Your Slack app needs the `chat:write` scope. Go to your app settings and add it under "OAuth & Permissions" → "Bot Token Scopes".

### No Notifications Being Sent

1. Check if the notifier is running:
   ```bash
   ~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh status
   ```

2. Check logs:
   ```bash
   ~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh tail
   ```

3. Test by creating a file:
   ```bash
   echo "test" > ~/.claude-sandbox-sharing/test.txt
   ```

4. Wait 30 seconds (batch window) and check Slack

### Notifier Keeps Crashing

Check the logs:
```bash
cat ~/.claude-sandbox-notify/notify.log
```

Common issues:
- Watched directory doesn't exist yet
- Slack token expired
- Network issues

## Files and Locations

### Host Machine

- **Main Script**: `~/khan/cursor-sandboxed/scripts/host-notify-slack.sh`
- **Control Script**: `~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh`
- **State Directory**: `~/.claude-sandbox-notify/`
- **Log File**: `~/.claude-sandbox-notify/notify.log`
- **Lock File**: `/tmp/claude-notify.lock`

### Watched Directories

- **Sharing**: `~/.claude-sandbox-sharing/` (container: `~/sharing/`)
- **Tools**: `~/.claude-sandbox-tools/` (container: `~/tools/`)

## Integration with Container Watcher

This host-side notifier works alongside the container-based context watcher:

**Container Watcher** (`context-watcher.sh`):
- Runs inside the Docker container
- Watches `~/context-sync/` for upstream data changes
- Uses Claude to analyze changes
- Writes outputs to `~/sharing/notifications/`

**Host Notifier** (`host-notify-slack.sh`):
- Runs on the host machine
- Watches `~/.claude-sandbox-sharing/` for outputs
- Sends Slack DMs when Claude creates notifications
- Provides immediate awareness of Claude's work

**Complete Flow:**
1. Confluence/JIRA/GitHub data syncs to `~/context-sync/`
2. Container watcher detects changes
3. Claude analyzes and creates summaries in `~/sharing/notifications/`
4. Host notifier detects new files in `~/.claude-sandbox-sharing/`
5. Slack DM sent to you with summary

## Next Steps

1. Install dependencies (`inotify-tools`, `jq`)
2. Get Slack bot token from https://api.slack.com/apps
3. Set `SLACK_TOKEN` environment variable
4. Start the notifier
5. Test by creating a file in `~/.claude-sandbox-sharing/`
6. Set up auto-start (systemd or `.bashrc`)

## Example Session

```bash
# One-time setup
sudo dnf install inotify-tools jq
export SLACK_TOKEN="xoxb-1234567890-..."
echo 'export SLACK_TOKEN="xoxb-1234567890-..."' >> ~/.bashrc

# Start notifier
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh start
# Output: ✓ Notifier started (PID: 12345)

# Check status
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh status
# Output: ✓ Notifier is running (PID: 12345)

# Test it
echo "test" > ~/.claude-sandbox-sharing/test.txt

# Wait 30 seconds, check Slack DM from Claude Notifier bot

# View logs
~/khan/cursor-sandboxed/scripts/host-notify-ctl.sh tail
# Output: [2025-01-15 10:30:15] Change detected: /home/jwies/.claude-sandbox-sharing/test.txt
#         [2025-01-15 10:30:45] Sending notification for 1 change(s)
#         [2025-01-15 10:30:46] Notification sent successfully
```
