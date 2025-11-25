# Slack App Setup - Complete Guide

Step-by-step instructions for creating and configuring your Slack app.

## Overview

You need **TWO tokens**:
1. **Bot Token** (`xoxb-...`) - For sending/receiving messages
2. **App Token** (`xapp-...`) - For Socket Mode connection (real-time messaging)

## Step-by-Step Setup

### 1. Create Slack App

**Option A: Using the Manifest (Fastest)**

1. Go to https://api.slack.com/apps
2. Click **"Create New App"**
3. Choose **"From an app manifest"**
4. Select your workspace
5. Choose **YAML** tab
6. Copy and paste contents of `host-services/slack/slack-notifier/slack-app-manifest.yaml`
7. Click **"Next"** → Review → **"Create"**
8. Skip to Step 3 (Enable Socket Mode)

**Option B: Manual Setup**

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. Enter app details:
   - **App Name**: `Claude Notifier`
   - **Workspace**: Select your workspace
4. Click **"Create App"**

### 2. Enable Messages Tab

1. In the left sidebar, click **"App Home"**
2. Scroll to **"Show Tabs"**
3. Enable **"Messages Tab"**
4. Check **"Allow users to send Slash commands and messages from the messages tab"**

### 3. Enable Socket Mode

1. In the left sidebar, click **"Socket Mode"**
2. Toggle **"Enable Socket Mode"** to **ON**
3. Generate an app-level token:
   - Click **"Generate Token and Scopes"**
   - **Token Name**: `socket-token`
   - **Scope**: Select `connections:write`
   - Click **"Generate"**
4. **Copy this token immediately** - format: `xapp-1-A01234567890-...`

### 4. Add Bot Scopes

1. Click **"OAuth & Permissions"**
2. Under **"Bot Token Scopes"**, add:
   - `chat:write` - Send messages
   - `channels:history` - Read thread parents
   - `im:history` - Read DM history
   - `im:read` - Read DM metadata
   - `users:read` - Get user info

### 5. Subscribe to Events

1. Click **"Event Subscriptions"**
2. Toggle **"Enable Events"** to **ON**
3. Under **"Subscribe to bot events"**, add:
   - `message.im` - Messages in DMs
4. Click **"Save Changes"**

### 6. Install to Workspace

1. Click **"OAuth & Permissions"**
2. Click **"Install to Workspace"**
3. Review and **"Allow"**
4. **Copy the Bot User OAuth Token** - format: `xoxb-...`

### 7. Get Your User ID

**From Slack UI:**
1. Click your profile picture
2. Click **"Profile"**
3. Click **"..."** → **"Copy member ID"**

**From URL:**
1. View your profile in browser
2. URL contains: `.../team/U07SK26JPJ5`
3. Your ID is `U07SK26JPJ5`

### 8. Get Your DM Channel ID

1. In Slack, open a DM with yourself (or the bot)
2. Look at the URL: `https://workspace.slack.com/archives/D07S8SAB5FE`
3. Channel ID is `D07S8SAB5FE`

## Token Summary

| Token | Format | Config Key |
|-------|--------|------------|
| Bot Token | `xoxb-...` | `slack_token` |
| App Token | `xapp-...` | `slack_app_token` |
| User ID | `U...` | `owner_user_id` |
| DM Channel | `D...` | `slack_channel` |

## Configuration

Create or edit `~/.config/jib-notifier/config.json`:

```json
{
  "slack_token": "xoxb-your-bot-token",
  "slack_app_token": "xapp-your-app-token",
  "slack_channel": "D07S8SAB5FE",
  "owner_user_id": "U07SK26JPJ5",
  "allowed_users": ["U07SK26JPJ5"]
}
```

Set permissions:
```bash
chmod 600 ~/.config/jib-notifier/config.json
```

## Start Services

```bash
# Using main setup script (recommended)
cd ~/khan/james-in-a-box
./setup.sh

# Or manually
systemctl --user start slack-notifier
systemctl --user start slack-receiver
```

## Verification Checklist

- [ ] Slack app created
- [ ] Socket Mode enabled
- [ ] App token (`xapp-...`) saved
- [ ] All 5 bot scopes added
- [ ] Event subscription (`message.im`) added
- [ ] App installed to workspace
- [ ] Bot token (`xoxb-...`) saved
- [ ] User ID obtained
- [ ] DM channel ID obtained
- [ ] Config file created

## Testing

```bash
# Check services
systemctl --user status slack-notifier slack-receiver

# View logs
journalctl --user -u slack-notifier -f
journalctl --user -u slack-receiver -f

# Test notification
echo "Test" > ~/.jib-sharing/notifications/test.md
# Check Slack in ~30 seconds

# Test receiving
# DM yourself: "claude: test task"
# Check ~/.jib-sharing/incoming/
```

## Troubleshooting

### "invalid_auth" Error
- Bot token is invalid or expired
- Reinstall app to workspace, get new token

### "missing_scope" Error
- Add missing scopes in OAuth & Permissions
- Reinstall app to workspace

### "Socket Mode connection failed"
- Verify Socket Mode is enabled
- Check app token is correct
- Regenerate app token if needed

### Not Receiving Messages
- Check `message.im` event is subscribed
- Verify receiver is running: `systemctl --user status slack-receiver`
- Check logs: `journalctl --user -u slack-receiver -n 50`

## Security Notes

- Store tokens in `~/.config/jib-notifier/config.json` (permissions 600)
- Never commit tokens to git
- Use `allowed_users` to restrict who can send commands
- Only grant required scopes

## References

- Slack App Management: https://api.slack.com/apps
- Socket Mode Docs: https://api.slack.com/apis/connections/socket
- Bot Scopes: https://api.slack.com/scopes
