# Quick Reference - Slack Bidirectional Communication

## TL;DR

**Respond to Claude**: Reply in thread to notification in bot's DM
**Send task to Claude**: DM the bot directly (any message)

## Setup (First Time Only)

1. **Create Slack app**: See `SLACK-APP-SETUP.md`
2. **Get tokens**: Bot token (`xoxb-...`) and App token (`xapp-...`)
3. **Configure**: `systemctl --user setup`
4. **Start receiver**: `systemctl --user start`
5. **Test**: Send `claude: test` to yourself in Slack

## Daily Usage

### When Claude Needs Guidance

**You receive in Slack**:
```
🔔 Claude Sandbox Changes Detected
notifications/: 20251121-143000-topic.md → Timestamp: 20251121-143000
💡 Reply in thread to respond to Claude
```

**You do**:
1. Click "Reply in thread"
2. Type your answer
3. Send

**No special format needed!** The timestamp is auto-extracted.

### When You Want Claude to Do Something

**In Slack, DM the bot**:
```
Implement OAuth2 for JIRA-1234
```

**Bot confirms** (in the same DM):
```
✅ Task received and queued for Claude
📁 Saved to: task-20251121-150000.md
```

**Then**:
- Start Claude session: `./jib`
- Claude will see the task in `~/sharing/incoming/`

## Common Commands

```bash
# Check receiver status
systemctl --user status

# View logs
systemctl --user tail

# Restart receiver
systemctl --user restart

# Start container
./jib
```

## Token Locations

- **Config**: `~/.config/jib-notifier/config.json`
- **Logs**: `~/.config/jib-notifier/receiver.log`
- **Tasks**: `~/.jib-sharing/incoming/`
- **Responses**: `~/.jib-sharing/responses/`
- **Notifications**: `~/.jib-sharing/notifications/`

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot not responding | Check `systemctl --user.sh status` |
| No self-DM messages detected | Verify channel ID in config matches your Slack DM channel |
| "invalid_auth" | Regenerate bot token, update config |
| Thread replies not working | Add `channels:history` scope |

## Required Slack Scopes

- `chat:write` - Send messages
- `channels:history` - Read threads
- `im:history` - Read DMs
- `im:read` - DM metadata
- `users:read` - User info

## File Locations

```
Host:
  ~/.config/jib-notifier/config.json          Bot config
  ~/.config/jib-notifier/receiver.log         Receiver logs
  ~/.jib-sharing/incoming/           Tasks from you
  ~/.jib-sharing/responses/          Your responses
  ~/.jib-sharing/notifications/      From Claude

Container:
  ~/sharing/incoming/                           Tasks from you
  ~/sharing/responses/                          Your responses
  ~/sharing/notifications/                      To you
  ~/sharing/tracking/incoming-watcher.log       Watcher logs
```

## Full Documentation

- **Slack App Setup**: See `../setup/slack-app-setup.md`
- **Bidirectional Setup**: See `../setup/slack-bidirectional.md`
- **Slack Architecture**: See `../architecture/slack-integration.md`
