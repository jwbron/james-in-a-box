# Bidirectional Slack Communication - Quick Setup

Complete setup for two-way Slack communication with Claude.

## What This Enables

- **Claude → You**: Claude sends notifications when it needs guidance
- **You → Claude**: You respond to notifications or send new tasks via Slack DM
- **Remote access**: Control Claude from anywhere (phone, laptop, etc.)

## Prerequisites

1. Slack workspace access
2. Ability to create Slack apps
3. Python 3.x with pip
4. Running `jib` container

## Step-by-Step Setup

### 1. Install Python Dependencies (Host Machine)

```bash
# Install Slack SDK (required for receiving messages)
pip install slack-sdk

# Or with user install
pip install --user slack-sdk
```

### 2. Configure Slack App

**Need detailed instructions?** See `SLACK-APP-SETUP.md` for complete step-by-step guide with screenshots.

**Quick summary**:

1. Go to https://api.slack.com/apps
2. Create app or select existing "Claude Notifier"
3. Enable Socket Mode → Generate app token (`xapp-...`)
4. Add 5 bot scopes: `chat:write`, `channels:history`, `im:history`, `im:read`, `users:read`
5. Enable event: `message.im`
6. Install/Reinstall to workspace
7. Copy Bot User OAuth Token (`xoxb-...`)

**For first-time setup, follow SLACK-APP-SETUP.md for detailed instructions.**

### 3. Get Your Tokens

You'll need TWO tokens:

**Bot Token** (xoxb-...):
- OAuth & Permissions → Bot User OAuth Token
- Already used for sending notifications

**App Token** (xapp-...):
- Settings → Basic Information → App-Level Tokens
- Created in step 2.3 above

### 4. Configure Slack Receiver

```bash
# Run interactive setup
~/khan/james-in-a-box/bin/host-receive-ctl setup
```

Enter when prompted:
- **Slack Bot Token**: `xoxb-your-bot-token` (same as notifier)
- **Slack App Token**: `xapp-your-app-token` (NEW, from step 2)
- **Allowed Users**: Your Slack user ID (optional, leave empty to allow all)

**Find your Slack user ID**:
```bash
# Method 1: Send test DM to bot, check receiver logs
~/khan/james-in-a-box/bin/host-receive-ctl tail

# Method 2: Slack UI
# Click your profile → More → Copy member ID
```

### 5. Start Slack Receiver

```bash
# Start receiver
~/khan/james-in-a-box/bin/host-receive-ctl start

# Verify it's running
~/khan/james-in-a-box/bin/host-receive-ctl status
```

Expected output:
```
✓ Receiver is running (PID: 12345)
Configuration:
  Config file: ~/.config/jib-notifier/config.json
  Incoming dir: ~/.jib-sharing/incoming
  Responses dir: ~/.jib-sharing/responses
  Allowed users: U01234567 (or "All")
```

### 6. Restart Container (If Already Running)

The incoming-watcher will start automatically:

```bash
# Exit container if inside
exit

# Restart container
./jib
```

You should see:
```
✓ Context watcher started (monitoring ~/context-sync/)
✓ Incoming watcher started (monitoring ~/sharing/incoming/ and ~/sharing/responses/)
```

### 7. Test the System

**Test 1: Send a task to Claude**

Open Slack, message yourself (self-DM):
```
claude: Test task - analyze the codebase structure
```

Bot will respond in your self-DM with:
```
✅ Task received and queued for Claude
📁 Saved to: task-YYYYMMDD-HHMMSS.md
```

**Important**:
- Bot monitors your self-DM channel (<YOUR-CHANNEL-ID>) for `claude:` prefix
- Bot writes acknowledgments back to your self-DM
- All task communication stays in your self-DM
- Bot's DM channel is used only for notifications from Claude

Check it was received:
```bash
# Host: Check receiver logs
~/khan/james-in-a-box/bin/host-receive-ctl tail

# Should see: "Received message from <your name>"
# Should see: "Message written: incoming/task-YYYYMMDD-HHMMSS.md"

# Container: Check incoming watcher logs
docker exec -it jib bash
tail ~/sharing/tracking/incoming-watcher.log
# Should see: "New task received: task-YYYYMMDD-HHMMSS.md"
```

**Test 2: Claude sends notification, you respond**

Inside container, create a test notification:
```bash
cat > ~/sharing/notifications/20251121-143000-test.md <<'EOF'
# 🔔 Test Notification

This is a test notification from Claude.

Should we proceed with approach A or B?
EOF
```

Wait ~30 seconds, you should get Slack DM with notification showing timestamp.

In Slack:
1. Click "Reply in thread" on the notification
2. Type: `Proceed with approach A`
3. Send

Check response was processed:
```bash
# Container
tail ~/sharing/tracking/incoming-watcher.log
# Should see: "Response received: RESPONSE-20251121-143000.md"

# Check response file
cat ~/sharing/responses/RESPONSE-20251121-143000.md
```

## Verification Checklist

- [ ] Slack app has Socket Mode enabled
- [ ] App-level token (xapp-) created
- [ ] Bot has required scopes (chat:write, im:history, im:read, users:read)
- [ ] Event subscription enabled for `message.im`
- [ ] Python slack-sdk installed
- [ ] Receiver configured with both tokens
- [ ] Receiver running (check status)
- [ ] Container has incoming-watcher running
- [ ] Test message sent and acknowledged

## Auto-Start on Boot

### Enable Receiver as systemd Service

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/slack-receiver.service <<'EOF'
[Unit]
Description=Slack Message Receiver for Claude
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/khan/james-in-a-box/internal/host-receive-slack.py
Restart=on-failure
RestartSec=30s
Nice=10

[Install]
WantedBy=default.target
EOF

# Enable and start
systemctl --user daemon-reload
systemctl --user enable slack-receiver
systemctl --user start slack-receiver

# Check status
systemctl --user status slack-receiver
```

### Verify Both Services Running

```bash
systemctl --user status slack-notifier  # Outgoing (Claude → You)
systemctl --user status slack-receiver  # Incoming (You → Claude)
```

## Troubleshooting

### "Socket Mode connection failed"

**Check**:
1. Socket Mode is enabled in Slack app
2. App token (xapp-) is correct
3. Network connectivity

**Fix**:
```bash
# Verify token in config
cat ~/.config/jib-notifier/config.json | grep app_token

# Check logs for specific error
~/khan/james-in-a-box/bin/host-receive-ctl tail
```

### "Not receiving messages in Slack"

**Check**:
1. Slack notifier is running
2. Watching correct directory

**Fix**:
```bash
# Check notifier status
~/khan/james-in-a-box/bin/host-notify-ctl status

# Test by creating file
echo "test" > ~/.jib-sharing/notifications/test-notif.md

# Wait 30 seconds, check Slack
```

### "Claude not receiving my Slack messages"

**Check**:
1. Receiver is running
2. Incoming-watcher is running in container
3. Message format is correct

**Fix**:
```bash
# Host: Check receiver
~/khan/james-in-a-box/bin/host-receive-ctl status

# Container: Check watcher
docker exec -it jib bash
ps aux | grep incoming-watcher
tail -f ~/sharing/tracking/incoming-watcher.log

# Manually test
echo "test task" > ~/.jib-sharing/incoming/manual-test.md
```

### "Permission denied" or "Unauthorized"

**Check**:
1. Bot token has required scopes
2. App is installed to workspace
3. `allowed_users` config (if set)

**Fix**:
```bash
# Check config
cat ~/.config/jib-notifier/config.json

# Remove user whitelist to test
# Edit config.json: "allowed_users": []

# Restart receiver
~/khan/james-in-a-box/bin/host-receive-ctl restart
```

## Configuration Files

**Main config** (both notifier and receiver):
```
~/.config/jib-notifier/config.json
```

**Logs**:
```
~/.config/jib-notifier/notifier.log   # Outgoing
~/.config/jib-notifier/receiver.log   # Incoming
```

**Container logs**:
```
~/sharing/tracking/incoming-watcher.log  # Inside container
```

## Usage Tips

### Responding to Notifications

Include notification timestamp in your response:
```
RE: 20251121-143000 - Yes, proceed with that approach
```

Or just use "RE:" and mention key details:
```
RE: database migration - Use multi-phase approach
```

### Sending New Tasks

Just send the task description:
```
Implement OAuth2 following ADR-012 for JIRA-1234
```

Claude will acknowledge and queue the task.

### Checking Status

```
What are you working on?
```

Claude will respond with current status when you start a conversation.

## Next Steps

1. Complete setup checklist above
2. Test with a simple task
3. Test responding to a notification
4. Enable auto-start (systemd)
5. Start using from your phone/laptop remotely!

## More Information

- **Full documentation**: `BIDIRECTIONAL-SLACK.md`
- **Outgoing setup**: `HOST-SLACK-NOTIFIER.md`
- **Notification templates**: `../claude-rules/notification-template.md`
