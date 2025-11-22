# Slack App Setup - Complete Guide

Step-by-step instructions for creating and configuring your Slack app to work with the bidirectional communication system.

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
4. Select your workspace (e.g., khanbottesting)
5. Choose **YAML** tab
6. Copy and paste contents of `slack-app-manifest.yaml` from this directory
7. Click **"Next"** → Review → **"Create"**
8. Done! Skip to Step 2 (Enable Socket Mode)

**Option B: Manual Setup (Step-by-step)**

1. Go to https://api.slack.com/apps
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Enter app details:
   - **App Name**: `Claude Notifier` (or your preferred name)
   - **Workspace**: Select your workspace (e.g., khanbottesting)
5. Click **"Create App"**

### 2. Enable Messages Tab (Allow DMs to Bot)

The bot needs to be able to receive direct messages.

1. In the left sidebar, click **"App Home"**
2. Scroll down to **"Show Tabs"** section
3. Check the box: **"Allow users to send Slash commands and messages from the messages tab"**
4. Ensure **"Messages Tab"** is enabled

This allows you to find the bot in your DMs and message it directly.

### 3. Enable Socket Mode

Socket Mode allows the bot to receive messages in real-time without needing a public webhook URL.

1. In the left sidebar, click **"Socket Mode"**
2. Toggle **"Enable Socket Mode"** to **ON**
3. You'll be prompted to generate an app-level token:
   - Click **"Generate Token and Scopes"**
   - **Token Name**: `socket-token`
   - **Scope**: Select `connections:write`
   - Click **"Generate"**
4. **IMPORTANT**: Copy and save this token immediately
   - Format: `xapp-1-A01234567890-1234567890123-abcdef1234567890...`
   - This is your **App Token** - you'll need it later
   - You won't be able to see it again!
5. Click **"Done"**

### 4. Add Bot Scopes (Permissions)

1. In the left sidebar, click **"OAuth & Permissions"**
2. Scroll down to **"Scopes"** section
3. Under **"Bot Token Scopes"**, click **"Add an OAuth Scope"**
4. Add these scopes one by one:

   **Required scopes**:
   - `chat:write` - Send messages (notifications to you)
   - `channels:history` - Read thread parent messages (extract timestamps)
   - `im:history` - Read DM history (receive your messages)
   - `im:read` - Read DM metadata (know which DM is yours)
   - `users:read` - Get user info (validate authorized users)

5. Your scopes section should now show all 5 scopes

### 5. Subscribe to Bot Events

This tells Slack which events to send to your bot.

1. In the left sidebar, click **"Event Subscriptions"**
2. Toggle **"Enable Events"** to **ON**
3. Scroll to **"Subscribe to bot events"**
4. Click **"Add Bot User Event"**
5. Add this event:
   - `message.im` - Messages sent to your bot or in DMs

6. Click **"Save Changes"** at the bottom

### 6. Install App to Workspace

1. In the left sidebar, click **"OAuth & Permissions"**
2. At the top, click **"Install to Workspace"** (or "Reinstall to Workspace" if updating)
3. Review the permissions
4. Click **"Allow"**
5. You'll be redirected back to the OAuth & Permissions page
6. **IMPORTANT**: Copy the **"Bot User OAuth Token"**
   - Format: `xoxb-1234567890123-1234567890123-abcdefghijklmnopqrstuvwx`
   - This is your **Bot Token** - you'll need it later
   - Keep this page open or save the token somewhere safe

### 7. Get Your Slack User ID

You need your user ID to configure the allowed users list.

**Method 1: From Profile URL**
1. In Slack, click your profile picture
2. Click **"View profile"**
3. Look at the URL: `https://khanbottesting.slack.com/team/U07SK26JPJ5`
4. Your user ID is the part after `/team/`
5. Example: `U07SK26JPJ5`

**Method 2: From Slack UI**
1. Click your profile picture in Slack
2. Click **"Profile"**
3. Click the three dots (More)
4. Click **"Copy member ID"**
5. Your user ID format: `U01234567AB`

**Method 2: From API**
```bash
# Use the bot token you just got
curl -H "Authorization: Bearer xoxb-YOUR-BOT-TOKEN" \
  "https://slack.com/api/users.list" | \
  jq '.members[] | select(.name=="YOUR_SLACK_USERNAME") | .id'
```

**Method 3: After starting receiver**
Send a test message and check logs - the user ID will be shown.

### 8. Get Your Self-DM Channel ID

You need your self-DM channel ID for the bot to recognize your task messages.

**Method 1: From Slack URL**
1. In Slack, open your self-DM (message yourself)
2. Look at the URL: `https://khanbottesting.slack.com/archives/D07S8SAB5FE`
3. The channel ID is the part after `/archives/`
4. Example: `D07S8SAB5FE`

**Method 2: From API**
```bash
curl -H "Authorization: Bearer xoxb-YOUR-BOT-TOKEN" \
  "https://slack.com/api/conversations.list?types=im" | \
  jq '.channels[] | select(.is_im==true and .user=="YOUR_USER_ID") | .id'
```

## Token Summary

After completing the above steps, you should have:

| Token Type | Format | Example | Where to Use |
|------------|--------|---------|--------------|
| **Bot Token** | `xoxb-...` | `xoxb-1234567890123-1234567890123-abc...` | Config: `slack_token` |
| **App Token** | `xapp-...` | `xapp-1-A01234567890-1234567890123-abc...` | Config: `slack_app_token` |
| **User ID** | `U...` | `U07SK26JPJ5` | Config: `owner_user_id` |
| **Self-DM Channel** | `D...` | `D07S8SAB5FE` | Config: `self_dm_channel` |

## Configuration

### Option 1: Interactive Setup (Recommended)

```bash
~/khan/james-in-a-box/scripts/host-receive-ctl.sh setup
```

Enter when prompted:
- **Slack Bot Token**: `xoxb-...` (from step 5)
- **Slack App Token**: `xapp-...` (from step 2)
- **Self-DM Channel ID**: `D07S8SAB5FE` (from step 7)
- **Your User ID**: `U07SK26JPJ5` (from step 6)
- **Allowed Users**: `U07SK26JPJ5` (same as your user ID, or leave empty)

### Option 2: Manual Configuration

Create `~/.config/jib-notifier/config.json`:

```json
{
  "slack_token": "xoxb-1234567890123-1234567890123-abcdefghijklmnopqrstuvwx",
  "slack_app_token": "xapp-1-A01234567890-1234567890123-abcdef1234567890abcdef1234567890abcdef1234567890abcdef12",
  "self_dm_channel": "D07S8SAB5FE",
  "owner_user_id": "U07SK26JPJ5",
  "allowed_users": ["U07SK26JPJ5"],
  "incoming_directory": "~/.jib-sharing/incoming",
  "responses_directory": "~/.jib-sharing/responses"
}
```

Set secure permissions:
```bash
chmod 600 ~/.config/jib-notifier/config.json
```

## Verification Checklist

Before proceeding, verify:

- [ ] Slack app created
- [ ] Socket Mode enabled
- [ ] App token (`xapp-...`) generated and saved
- [ ] All 5 bot scopes added
- [ ] Event subscription (`message.im`) added
- [ ] App installed to workspace
- [ ] Bot token (`xoxb-...`) copied and saved
- [ ] Your user ID obtained
- [ ] Self-DM channel ID verified (`<YOUR-CHANNEL-ID>`)
- [ ] Config file created with both tokens

## Testing

### Start the Receiver

```bash
~/khan/james-in-a-box/scripts/host-receive-ctl.sh start
```

Expected output:
```
Starting Slack receiver...
✓ Receiver started (PID: 12345)
  Logs: ~/.config/jib-notifier/receiver.log
```

### Check Status

```bash
~/khan/james-in-a-box/scripts/host-receive-ctl.sh status
```

Expected output:
```
✓ Receiver is running (PID: 12345)

Configuration:
  Config file: ~/.config/jib-notifier/config.json
  Incoming dir: ~/.jib-sharing/incoming
  Responses dir: ~/.jib-sharing/responses
  Allowed users: U01234567AB
```

### View Logs

```bash
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail
```

You should see:
```
[2025-11-21 15:30:00] INFO: Starting Slack receiver (PID: 12345)
[2025-11-21 15:30:01] INFO: Bot user ID: U98765432XY
[2025-11-21 15:30:01] INFO: Incoming messages → ~/.jib-sharing/incoming
[2025-11-21 15:30:01] INFO: Responses → ~/.jib-sharing/responses
[2025-11-21 15:30:01] INFO: Allowed users: U01234567AB
[2025-11-21 15:30:02] INFO: Connected to Slack Socket Mode
[2025-11-21 15:30:02] INFO: Listening for direct messages...
```

### Send Test Message

In Slack, message yourself:
```
claude: test task
```

Check logs:
```bash
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail
```

Should show:
```
[2025-11-21 15:31:00] INFO: Received message from James Wiesebron (U01234567AB): claude: test task
[2025-11-21 15:31:00] INFO: Message written: ~/.jib-sharing/incoming/task-20251121-153100.md
```

And in Slack, you should get a reply in your self-DM:
```
✅ Task received and queued for Claude
📁 Saved to: task-20251121-153100.md
```

## Troubleshooting

### "invalid_auth" Error

**Problem**: Bot token is invalid or expired

**Fix**:
1. Go to https://api.slack.com/apps
2. Select your app
3. Go to "OAuth & Permissions"
4. Copy the Bot User OAuth Token again
5. Update config: `~/khan/james-in-a-box/scripts/host-receive-ctl.sh setup`

### "missing_scope" Error

**Problem**: Bot doesn't have required permissions

**Fix**:
1. Go to https://api.slack.com/apps
2. Select your app
3. Go to "OAuth & Permissions"
4. Add missing scopes from step 3 above
5. Click "Reinstall to Workspace" at the top
6. Restart receiver: `~/khan/james-in-a-box/scripts/host-receive-ctl.sh restart`

### "Socket Mode connection failed"

**Problem**: App token is invalid or Socket Mode not enabled

**Fix**:
1. Verify Socket Mode is enabled (step 2)
2. Verify app token is correct in config
3. If needed, regenerate app token:
   - Go to "Basic Information" → "App-Level Tokens"
   - Revoke old token
   - Generate new token with `connections:write` scope
   - Update config

### Not Receiving Messages

**Checklist**:
1. [ ] Receiver is running: `host-receive-ctl.sh status`
2. [ ] Event subscription enabled with `message.im`
3. [ ] Self-DM channel ID is correct (`<YOUR-CHANNEL-ID>`)
4. [ ] Message starts with `claude:` prefix
5. [ ] Your user ID is in `allowed_users` (or list is empty)

**Debug**:
```bash
# Watch logs in real-time
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail

# In another terminal, send test message
# Then check if anything appears in logs
```

### Bot Not Responding to Self-DM

**Problem**: Self-DM channel ID might be different

**Fix**:
1. Find your actual self-DM channel:
   ```bash
   # Message yourself in Slack
   # Look at URL: .../archives/DXXXXXX
   ```

2. Update the hardcoded channel ID in `host-receive-slack.py`:
   ```python
   # Line ~200
   if channel == '<YOUR-CHANNEL-ID>' and text.lower().startswith('claude:'):
   # Change to your actual channel ID
   if channel == 'DYOURCHANNELID' and text.lower().startswith('claude:'):
   ```

3. Restart receiver

## Security Best Practices

### Token Storage

✅ **DO**:
- Store tokens in `~/.config/jib-notifier/config.json` with 600 permissions
- Use environment variables for temporary testing
- Keep tokens out of git repositories

❌ **DON'T**:
- Commit tokens to git
- Share tokens in Slack/email
- Store tokens in world-readable files

### Scope Minimization

Only grant the scopes needed:
- `chat:write` - Required for sending
- `channels:history` - Only for thread parents
- `im:history` - Only for DMs
- `im:read` - Only for metadata
- `users:read` - Only for user info

Don't add extra scopes "just in case".

### User Whitelist

For single-user setup:
```json
"allowed_users": ["U01234567AB"]
```

This ensures only you can send commands to Claude.

## Next Steps

1. ✅ Complete this setup
2. ✅ Test with `claude: test task`
3. ✅ Start container: `./jib`
4. ✅ Test notification response (see BIDIRECTIONAL-SETUP.md)
5. ✅ Enable auto-start (systemd)

## References

- **Slack App Management**: https://api.slack.com/apps
- **Socket Mode Docs**: https://api.slack.com/apis/connections/socket
- **Bot Scopes Reference**: https://api.slack.com/scopes
- **Testing Tools**: https://api.slack.com/methods
