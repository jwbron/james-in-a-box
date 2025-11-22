# Quick Reference - Slack Bidirectional Communication

## TL;DR

**Respond to Claude**: Reply in thread to notification
**Send task to Claude**: Self-DM with `claude: [task]`

## Setup (First Time Only)

1. **Create Slack app**: See `SLACK-APP-SETUP.md`
2. **Get tokens**: Bot token (`xoxb-...`) and App token (`xapp-...`)
3. **Configure**: `~/khan/cursor-sandboxed/scripts/host-receive-ctl.sh setup`
4. **Start receiver**: `~/khan/cursor-sandboxed/scripts/host-receive-ctl.sh start`
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

**In Slack, message yourself**:
```
claude: Implement OAuth2 for JIRA-1234
```

**Bot confirms** (in your self-DM):
```
✅ Task received and queued for Claude
```

**Then**:
- Start Claude session: `./claude-sandboxed`
- Claude will see the task in `~/sharing/incoming/`

## Common Commands

```bash
# Check receiver status
~/khan/cursor-sandboxed/scripts/host-receive-ctl.sh status

# View logs
~/khan/cursor-sandboxed/scripts/host-receive-ctl.sh tail

# Restart receiver
~/khan/cursor-sandboxed/scripts/host-receive-ctl.sh restart

# Start container
./claude-sandboxed
```

## Token Locations

- **Config**: `~/.config/slack-notifier/config.json`
- **Logs**: `~/.config/slack-notifier/receiver.log`
- **Tasks**: `~/.claude-sandbox-sharing/incoming/`
- **Responses**: `~/.claude-sandbox-sharing/responses/`
- **Notifications**: `~/.claude-sandbox-sharing/notifications/`

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot not responding | Check `host-receive-ctl.sh status` |
| No self-DM messages detected | Verify channel ID in code is `D04CMDR7LBT` |
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
  ~/.config/slack-notifier/config.json          Bot config
  ~/.config/slack-notifier/receiver.log         Receiver logs
  ~/.claude-sandbox-sharing/incoming/           Tasks from you
  ~/.claude-sandbox-sharing/responses/          Your responses
  ~/.claude-sandbox-sharing/notifications/      From Claude

Container:
  ~/sharing/incoming/                           Tasks from you
  ~/sharing/responses/                          Your responses
  ~/sharing/notifications/                      To you
  ~/sharing/tracking/incoming-watcher.log       Watcher logs
```

## Full Documentation

- **Slack App Setup**: `SLACK-APP-SETUP.md`
- **Bidirectional Setup**: `BIDIRECTIONAL-SETUP.md`
- **Complete Guide**: `../BIDIRECTIONAL-SLACK.md`
