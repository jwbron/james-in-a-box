# Bidirectional Slack Communication

Complete system for two-way communication between you and Claude via private Slack DMs.

## Overview

This system enables:
1. **Claude → You**: Claude sends notifications when it needs guidance (already implemented)
2. **You → Claude**: You respond to Claude's questions or trigger new tasks via Slack DMs (NEW)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  You (Slack DM)                                             │
│  • Send tasks to Claude                                     │
│  • Respond to Claude's notifications                        │
│  • Access from anywhere (remote work)                       │
└─────────────────────────────────────────────────────────────┘
                           ▲                    │
                           │                    │
        (2) Notification   │                    │  (1) Your message
            sent via       │                    │      received via
            host-notify    │                    │      host-receive
            -slack.py      │                    │      -slack.py
                           │                    │
                           │                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Host Machine (Outside Container)                           │
│  • host-notify-slack.py  - Sends Claude's notifications     │
│  • host-receive-slack.py - Receives your messages (NEW)     │
│                                                              │
│  Shared directories:                                        │
│  • ~/.jib-sharing/notifications/  ← Claude       │
│  • ~/.jib-sharing/incoming/       → Claude (NEW) │
│  • ~/.jib-sharing/responses/      → Claude (NEW) │
└─────────────────────────────────────────────────────────────┘
                           ▲                    │
                           │                    │
        Files detected by  │                    │  Files written to
        context-watcher    │                    │  incoming-watcher
                           │                    │  (NEW)
                           │                    ▼
┌─────────────────────────────────────────────────────────────┐
│  Docker Container (Claude's Environment)                    │
│  • Claude agent - Analyzes code, implements features        │
│  • context-watcher - Monitors context changes               │
│  • incoming-watcher - Monitors your messages (NEW)          │
│                                                              │
│  Container directories:                                     │
│  • ~/sharing/notifications/  - Claude's notifications       │
│  • ~/sharing/incoming/       - Your new tasks (NEW)         │
│  • ~/sharing/responses/      - Your responses (NEW)         │
└─────────────────────────────────────────────────────────────┘
```

## Communication Flows

### Flow 1: Claude → You (Notifications)

**When**: Claude needs guidance, finds better approach, skeptical about solution, etc.

```
Claude writes notification
    ↓
~/sharing/notifications/YYYYMMDD-HHMMSS-topic.md
    ↓
host-notify-slack.py detects change (~30 seconds)
    ↓
Slack DM sent to you
    ↓
You receive notification on phone/desktop
```

**Example notification from Claude**:
```markdown
# 🔔 Need Guidance: Better Caching Strategy Found

Priority: Medium
Topic: Architecture

Working on Redis caching for user service (JIRA-1234). Spec says to cache
user objects, but I found caching user sessions would reduce DB load by 80%
instead of 40%. Should I switch to session caching?
```

### Flow 2: You → Claude (Responses)

**When**: Responding to Claude's notification

**How**: Reply in the Slack notification thread

```
Claude's notification appears in Slack with timestamp visible
    ↓
You click "Reply in thread"
    ↓
You send: "Yes, switch to session caching and update the spec"
    ↓
host-receive-slack.py receives thread reply
    ↓
Extracts notification timestamp from parent message
    ↓
Writes to ~/.jib-sharing/responses/RESPONSE-20251121-143000.md
    ↓
incoming-watcher.sh (in container) detects file
    ↓
Links response to original notification
    ↓
Claude sees response in ~/sharing/responses/ (or waits for it if blocked)
```

**Your Slack action**:
1. Click "Reply in thread" on the notification
2. Type your response: `Yes, switch to session caching and update the spec. Coordinate with auth-service team.`
3. Send

**Result**: File created at `responses/RESPONSE-20251121-143000.md` and linked to original notification

### Flow 3: You → Claude (New Tasks)

**When**: Triggering Claude to work on something new

**How**: Send self-DM in Slack starting with `claude:` (case insensitive)

```
You send message to yourself in Slack: "claude: Add OAuth2 support following ADR-012"
    ↓
host-receive-slack.py receives message in your self-DM channel
    ↓
Detects "claude:" prefix, extracts task content
    ↓
Writes to ~/.jib-sharing/incoming/task-YYYYMMDD-HHMMSS.md
    ↓
incoming-watcher.sh (in container) detects file
    ↓
Acknowledges task receipt via notification
    ↓
Claude picks up task when you start conversation
```

**Your Slack action**:
1. Open your self-DM (message yourself)
2. Type: `claude: Implement OAuth2 flow following ADR-012 for JIRA-1234. Write tests and update docs.`
3. Send

**Bot's response** (in your self-DM):
```
✅ Task received and queued for Claude
📁 Saved to: task-20251121-150000.md
```

**Important**:
- Bot **monitors** your self-DM channel (`<YOUR-CHANNEL-ID>`) for `claude:` prefix
- Bot **writes acknowledgments** back to your self-DM (same channel)
- All task communication happens in your self-DM
- Bot's own DM channel stays clean for notifications only

**Why self-DM?**
- All task requests and confirmations in one place
- Easy to access from anywhere (phone, laptop)
- Simple prefix makes intent clear
- Can review full task history
- Clean separation: self-DM = tasks, bot DM = notifications

**Result**: Task queued in `incoming/task-20251121-150000.md`

## Setup

### Prerequisites

1. **Slack App with Socket Mode** (required for receiving messages)
2. **Python dependencies**: `slack-sdk`
3. **Two Slack tokens**:
   - Bot token (xoxb-...) - for sending/receiving messages
   - App token (xapp-...) - for Socket Mode connection

### Step 1: Configure Slack App

1. Go to https://api.slack.com/apps
2. Select your existing app or create new one ("Claude Notifier")
3. Enable Socket Mode:
   - Go to "Socket Mode" in sidebar
   - Toggle "Enable Socket Mode" to ON
   - Click "Generate" to create app-level token
   - Name it "socket-token" with scope `connections:write`
   - **Save this token** (starts with `xapp-`)

4. Add bot scopes (OAuth & Permissions):
   - `chat:write` - Send messages
   - `im:history` - Read DM history
   - `im:read` - Read DM metadata
   - `users:read` - Get user info

5. Enable events (Event Subscriptions):
   - Toggle "Enable Events" to ON
   - Add bot event: `message.im` (Direct messages)
   - Save changes

6. Reinstall app to workspace if needed

### Step 2: Install Dependencies (Host Machine)

```bash
# Install Python Slack SDK
pip install slack-sdk

# Or with user install
pip install --user slack-sdk
```

### Step 3: Configure Receiver

```bash
# Run interactive setup
~/khan/james-in-a-box/scripts/host-receive-ctl.sh setup

# It will prompt for:
# - SLACK_TOKEN (bot token, xoxb-...)
# - SLACK_APP_TOKEN (app token, xapp-...)
# - Allowed users (optional - your Slack user ID)
```

**Configuration file**: `~/.config/jib-notifier/config.json`

```json
{
  "slack_token": "xoxb-your-bot-token",
  "slack_app_token": "xapp-your-app-token",
  "allowed_users": ["U01234567"],  // Your Slack user ID (optional)
  "incoming_directory": "~/.jib-sharing/incoming",
  "responses_directory": "~/.jib-sharing/responses"
}
```

**Security**: Config file has 600 permissions (owner read/write only)

### Step 4: Start Receiver

```bash
# Start receiver
~/khan/james-in-a-box/scripts/host-receive-ctl.sh start

# Check status
~/khan/james-in-a-box/scripts/host-receive-ctl.sh status

# View logs
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail
```

### Step 5: Start Container

The incoming-watcher will start automatically when container boots:

```bash
./jib
```

You should see:
```
✓ Context watcher started (monitoring ~/context-sync/)
✓ Incoming watcher started (monitoring ~/sharing/incoming/ and ~/sharing/responses/)
```

### Step 6: Test

Send a test DM to your Slack bot:

```
Test task: analyze the codebase structure
```

Check logs:
```bash
# Host receiver logs
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail

# Container watcher logs (inside container)
tail -f ~/sharing/tracking/incoming-watcher.log
```

## Usage Examples

### Example 1: Responding to Claude's Notification

**Claude's notification** (appears in Slack):
```
🔔 Claude Sandbox Changes Detected

notifications/ (~/.jib-sharing/):
  • 20251121-143000-db-migration.md → Timestamp: 20251121-143000

💡 Reply in thread to respond to Claude
```

**Your action**:
1. Click "Reply in thread"
2. Type: `Yes, proceed with multi-phase migration. Zero downtime is critical. Coordinate with DB team before starting.`
3. Send

**Result**:
- Response written to `responses/RESPONSE-20251121-143000.md`
- Linked to original notification
- Claude sees your response in `~/sharing/responses/` (or is waiting for it)

### Example 2: Triggering New Task

**Your action**:
1. Open self-DM in Slack (message yourself)
2. Type: `claude: Add rate limiting to API endpoints. Follow ADR-045. Include metrics and alerting.`
3. Send

**Bot response** (in your self-DM):
```
✅ Task received and queued for Claude
📁 Saved to: task-20251121-150000.md
```

**Result**:
- Task written to `incoming/task-20251121-150000.md`
- Acknowledgment notification sent
- Claude picks up task when you start conversation

### Example 3: Remote Work Session

You're away from your workstation but want to trigger work:

**Your action** (from phone):
1. Open Slack self-DM
2. Type: `claude: Status update - what are you working on?`
3. Send

**Result**:
- Task queued in `incoming/`
- When you start Claude session later, it will provide status
- Or Claude may send notification with current status

## File Organization

### Host Machine

```
~/.jib-sharing/
├── notifications/          # Claude → You (notifications)
│   ├── 20251121-143000-need-guidance.md
│   └── RESPONSE-20251121-143000.md  # Your response linked here
├── incoming/               # You → Claude (new tasks)
│   └── task-20251121-150000.md
└── responses/              # You → Claude (responses to notifications)
    └── response-20251121-150500.md

~/.config/jib-notifier/
├── config.json            # Slack tokens and configuration (600 perms)
├── notifier.log          # Outgoing notifications log
└── receiver.log          # Incoming messages log
```

### Container

```
~/sharing/
├── notifications/         # Mounted from host
├── incoming/              # Mounted from host
└── responses/             # Mounted from host

~/sharing/tracking/
├── incoming-watcher.log   # Incoming watcher logs
├── incoming-watcher.state # Processed messages tracking
└── watcher.log            # Context watcher logs
```

## Management Commands

### Receiver Control

```bash
# Start/stop receiver
~/khan/james-in-a-box/scripts/host-receive-ctl.sh start
~/khan/james-in-a-box/scripts/host-receive-ctl.sh stop
~/khan/james-in-a-box/scripts/host-receive-ctl.sh restart

# Monitor
~/khan/james-in-a-box/scripts/host-receive-ctl.sh status
~/khan/james-in-a-box/scripts/host-receive-ctl.sh logs
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail

# Configure
~/khan/james-in-a-box/scripts/host-receive-ctl.sh setup
```

### Notifier Control (Outgoing)

```bash
# Already configured from HOST-SLACK-NOTIFIER.md
~/khan/james-in-a-box/scripts/host-notify-ctl.sh status
~/khan/james-in-a-box/scripts/host-notify-ctl.sh logs
```

### Container Watchers

Both watchers start automatically in container. Check logs:

```bash
# Inside container
tail -f ~/sharing/tracking/watcher.log           # Context watcher
tail -f ~/sharing/tracking/incoming-watcher.log  # Incoming messages watcher
```

## Auto-Start on Boot

### Using systemd (Recommended)

Already implemented in `slack-notifier/manage_notifier.sh`:

```bash
# Enable notifier (already done)
cd ~/khan/james-in-a-box/jib-notifier
./manage_notifier.sh enable

# Enable receiver (NEW)
# Create ~/.config/systemd/user/slack-receiver.service
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/slack-receiver.service <<'EOF'
[Unit]
Description=Slack Message Receiver for Claude
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 %h/khan/james-in-a-box/scripts/host-receive-slack.py
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
systemctl --user status slack-receiver
```

### Check Services

```bash
# Both should be running
systemctl --user status slack-notifier  # Outgoing notifications
systemctl --user status slack-receiver  # Incoming messages
```

## Troubleshooting

### Receiver Not Starting

**Check dependencies**:
```bash
python3 -c "import slack_sdk"
# If error: pip install slack-sdk
```

**Check config**:
```bash
cat ~/.config/jib-notifier/config.json
# Ensure slack_token and slack_app_token are set
```

**Check logs**:
```bash
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail
```

### Not Receiving Messages

1. **Check Socket Mode is enabled** in Slack app settings
2. **Check bot events** are configured (`message.im`)
3. **Check receiver is running**:
   ```bash
   ~/khan/james-in-a-box/scripts/host-receive-ctl.sh status
   ```
4. **Check allowed_users** in config (if set, must include your user ID)
5. **Check logs** for errors:
   ```bash
   ~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail
   ```

### Messages Not Being Processed in Container

1. **Check incoming-watcher is running**:
   ```bash
   # Inside container
   ps aux | grep incoming-watcher
   ```

2. **Check logs**:
   ```bash
   # Inside container
   tail -f ~/sharing/tracking/incoming-watcher.log
   ```

3. **Check directories exist**:
   ```bash
   # Inside container
   ls -la ~/sharing/incoming/
   ls -la ~/sharing/responses/
   ```

4. **Manually trigger test**:
   ```bash
   # On host
   echo "Test task" > ~/.jib-sharing/incoming/test-task.md

   # Check container logs
   ```

### Getting Your Slack User ID

Send a DM to your bot, then check receiver logs:

```bash
~/khan/james-in-a-box/scripts/host-receive-ctl.sh tail
# Look for: "Received message from <name> (U01234567)"
```

Or use Slack API:
```bash
curl -H "Authorization: Bearer xoxb-your-token" \
  https://slack.com/api/users.list | jq '.members[] | select(.name=="yourname") | .id'
```

## Security Considerations

### Credential Storage

- **Slack tokens** stored in `~/.config/jib-notifier/config.json` with 600 permissions
- **Not in git repository** - excluded via .gitignore
- **Not accessible from container** - outside mount points

### User Authentication

- **Optional whitelist** - `allowed_users` in config restricts who can send messages
- **Bot checks sender** - messages from unauthorized users are rejected
- **Audit trail** - all messages logged with user ID and timestamp

### Message Validation

- Receiver validates message format
- Container watcher marks processed messages to prevent duplicates
- State tracking in `~/sharing/tracking/incoming-watcher.state`

## Integration with Existing Workflows

This system complements existing workflows:

### Context Sync → Claude → You
```
confluence-cursor-sync.timer (host)
    ↓
~/context-sync/confluence/ (host)
    ↓
context-watcher.sh (container)
    ↓
Claude analyzes changes
    ↓
~/sharing/notifications/ (container)
    ↓
host-notify-slack.py (host)
    ↓
Slack DM to you
```

### You → Claude (via Slack)
```
Your Slack DM
    ↓
host-receive-slack.py (host)
    ↓
~/.jib-sharing/incoming/ (host)
    ↓
incoming-watcher.sh (container)
    ↓
Acknowledges receipt
    ↓
Claude processes when conversation starts
```

### Complete Loop
```
Claude sends notification → You receive Slack DM → You respond via Slack →
Claude receives response → Claude continues work → Claude sends update
```

## Quick Usage Reference

### Responding to Claude's Notifications

**What you see**:
```
🔔 Claude Sandbox Changes Detected
notifications/: 20251121-143000-topic.md → Timestamp: 20251121-143000
💡 Reply in thread to respond to Claude
```

**What you do**:
1. Click "Reply in thread"
2. Type your response (no special format needed)
3. Send

The system extracts the timestamp from the parent message automatically.

### Sending New Tasks to Claude

**Message yourself** in Slack with `claude:` prefix:
```
claude: Implement OAuth2 for JIRA-1234
Claude: add rate limiting to API
CLAUDE: refactor auth service
```

**Bot responds in your self-DM**:
```
✅ Task received and queued for Claude
📁 Saved to: task-20251121-150000.md
```

**How it works**:
- Bot monitors your self-DM channel (<YOUR-CHANNEL-ID>)
- Detects messages starting with `claude:` (case insensitive)
- Writes acknowledgment back to your self-DM
- All task communication stays in self-DM

### Why This Pattern?

- **Thread replies**: Natural UX, timestamp auto-extracted, keeps context
- **Self-DM for tasks**: Clean separation (bot = notifications, self = tasks)
- **`claude:` prefix**: Clear intent, easy to search history

### Bot Access and Privacy

**What the bot can access**:
- ✅ Your self-DM channel (`<YOUR-CHANNEL-ID>`) - only monitors for `claude:` prefix
- ✅ Direct messages TO the bot - for thread replies to notifications
- ✅ Thread parent messages - to extract notification timestamps

**What the bot CANNOT access**:
- ❌ Other DMs (between you and other people)
- ❌ Channel messages (unless bot is @mentioned)
- ❌ Your self-DM messages without `claude:` prefix (ignored)

**Where bot writes**:
- Your self-DM (`<YOUR-CHANNEL-ID>`) - task acknowledgments
- Bot's DM with you - notification messages (from Claude)

## Next Steps

1. **Set up Socket Mode** in Slack app
2. **Get app token** (xapp-...) for Socket Mode
3. **Run setup**: `host-receive-ctl.sh setup`
4. **Start receiver**: `host-receive-ctl.sh start`
5. **Restart container** to start incoming-watcher
6. **Test**: Send `claude: test task` to yourself
7. **Enable auto-start** with systemd

## References

- **Slack App Setup**: `slack-notifier/SLACK-APP-SETUP.md` - Detailed token creation guide
- **Quick Setup**: `slack-notifier/BIDIRECTIONAL-SETUP.md` - Fast setup checklist
- **Outgoing notifications**: `HOST-SLACK-NOTIFIER.md`
- **Claude notification system**: `claude-rules/notification-template.md`
- **Slack Socket Mode docs**: https://api.slack.com/apis/connections/socket
- **Slack SDK for Python**: https://slack.dev/python-slack-sdk/
