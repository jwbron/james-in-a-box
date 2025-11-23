# Context Watcher System

Automated monitoring and analysis of changes in `~/context-sync` with Claude.

## Overview

This system watches for changes in your context sync directory and uses Claude to:
- Identify changes relevant to you (ADRs you authored, responses to your comments, team mentions, ticket updates)
- Generate summaries of important changes
- Draft responses to questions/comments
- Track action items
- Update a running log of context changes

## Quick Start

### 1. Fix SELinux Permissions

First, fix the SELinux labels on your shared directories (run from host, not container):

```bash
# On the host machine:
sudo chcon -R -t container_file_t ~/.jib-sharing/
sudo chcon -R -t container_file_t ~/context-sync/
```

Or add to your docker-compose.yml / container startup script:

```yaml
volumes:
  - ~/.jib-sharing:/home/jwies/sharing:Z
  - ~/context-sync:/home/jwies/context-sync:Z
```

The `:Z` flag automatically sets the correct SELinux label.

### 2. Create Directories

```bash
mkdir -p ~/sharing/{config,notifications,context-tracking}
mkdir -p ~/sharing/notifications/{draft-responses,action-items,code-plans,code-drafts}
mkdir -p ~/context-sync
```

### 3. Move Configuration

```bash
# Move config to the proper location
cp ~/khan/james-in-a-box/context-watcher/config/context-watcher.yaml ~/sharing/config/

# Update the config with your details
vi ~/sharing/config/context-watcher.yaml
```

### 4. Start the Watcher

```bash
# Start in background
~/khan/james-in-a-box/bin/context-watcher-ctl start

# Check status
~/khan/james-in-a-box/bin/context-watcher-ctl status

# View logs
~/khan/james-in-a-box/bin/context-watcher-ctl tail
```

## Usage

### Managing the Service

```bash
# Start the watcher
./bin/context-watcher-ctl start

# Stop the watcher
./bin/context-watcher-ctl stop

# Restart the watcher
./bin/context-watcher-ctl restart

# Check status
./bin/context-watcher-ctl status

# View logs (interactive)
./bin/context-watcher-ctl logs

# Tail logs (follow)
./bin/context-watcher-ctl tail
```

### Manual Analysis

You can also manually trigger Claude to analyze changes:

```bash
# Use the slash command
claude analyze-context-changes

# Or call Claude directly with a prompt
claude --prompt "Analyze the recent changes in ~/context-sync and identify anything relevant to Jacob (jwies)"
```

### Configuration

Edit `~/sharing/config/context-watcher.yaml` to customize:

- Your identity (name, username, email)
- Teams and tags to monitor
- JIRA projects and ticket patterns
- Keywords to watch for
- Actions to take (summaries, responses, code generation)
- Check intervals and batching settings

## How It Works

1. **File Watcher** (`context-watcher.sh`):
   - Monitors `~/context-sync` for file changes every 5 minutes (configurable)
   - Batches changes together (60 second window by default)
   - Maintains state to track what's been processed

2. **Claude Analysis** (slash command):
   - Receives list of changed files
   - Reads each file and determines relevance
   - Applies filters based on your configuration
   - Takes appropriate actions for relevant changes

3. **Outputs**:
   - **Summaries**: `~/sharing/notifications/summary-*.md`
   - **Draft Responses**: `~/sharing/notifications/draft-responses/response-*.md`
   - **Action Items**: `~/sharing/notifications/action-items/items-*.md`
   - **Tracking Log**: `~/sharing/context-tracking/updates.md`
   - **Code Plans**: `~/sharing/notifications/code-plans/plan-*.md`
   - **Code Drafts**: `~/sharing/notifications/code-drafts/`

## Relevance Criteria

Changes are considered relevant if they:

1. Affect ADRs you authored (checked via git blame/history)
2. Contain responses to your comments
3. Mention you directly (@jwies, Jacob, Jacob Wiesblatt)
4. Tag your team (infra-platform, infrastructure-platform)
5. Update JIRA tickets you're assigned to or watching
6. Contain configured keywords (kacontext, environ, secrets, etc.)

## File Structure

```
~/khan/james-in-a-box/context-watcher/
├── config/
│   └── context-watcher.yaml    # Configuration
├── tracking/
│   ├── watcher-state.json      # State tracking
│   └── watcher.log             # Service logs
└── README.md                   # This file

~/sharing/
├── config/
│   └── context-watcher.yaml    # Configuration (copy here)
├── notifications/
│   ├── summary-*.md            # Change summaries
│   ├── draft-responses/        # Response drafts
│   ├── action-items/           # Action item lists
│   ├── code-plans/             # Code implementation plans
│   └── code-drafts/            # Draft code
└── context-tracking/
    └── updates.md              # Running log of changes

~/.claude/commands/
└── analyze-context-changes.md  # Claude slash command

~/khan/james-in-a-box/scripts/
├── context-watcher.sh          # Main watcher service
└── context-watcher-ctl.sh      # Control script
```

## Troubleshooting

### Watcher Won't Start

1. Check for lock file: `ls -la /tmp/context-watcher.lock`
2. Remove if stale: `rm /tmp/context-watcher.lock`
3. Check logs: `./bin/context-watcher-ctl logs`

### Can't Write to ~/sharing

This is an SELinux issue. Fix with:

```bash
# From host:
sudo chcon -R -t container_file_t ~/.jib-sharing/

# Or update docker-compose to use :Z flag on volumes
```

### No Changes Detected

1. Check that `~/context-sync` exists and has files
2. Verify check interval in config (`processing.check_interval_seconds`)
3. Check that files are actually being modified (use `ls -lt ~/context-sync`)
4. Review watcher logs for errors

### Claude Not Analyzing

1. Check Claude CLI is available: `which claude`
2. Test Claude: `claude --version`
3. Check the logs for errors: `./bin/context-watcher-ctl tail`

## Advanced Usage

### Running at Container Startup

Add to your container's startup script or `.bashrc`:

```bash
# Auto-start context watcher
if [ -f ~/khan/james-in-a-box/bin/context-watcher-ctl ]; then
    ~/khan/james-in-a-box/bin/context-watcher-ctl start
fi
```

### Customizing Analysis

Edit `~/.claude/commands/analyze-context-changes.md` to customize how Claude analyzes changes.

### Integration with Other Tools

The watcher outputs structured markdown files that can be:
- Parsed by other scripts
- Indexed for search
- Fed into notification systems
- Tracked in git

## Next Steps

1. Set up your `~/context-sync` directory (mount Confluence, GitHub, JIRA data here)
2. Configure `~/sharing/config/context-watcher.yaml` with your details
3. Start the watcher and test with some sample changes
4. Review outputs in `~/sharing/notifications/`
5. Iterate on configuration and prompts as needed
6. **[Optional]** Set up host-side Slack notifier for instant DMs when outputs are created

## Host-Side Slack Notifications (Optional)

The context watcher writes outputs to `~/sharing/notifications/`. To get **instant Slack DMs** when Claude creates these files, you can set up a companion host-side notifier.

This runs on your **host machine** (outside the container) and watches the shared directories:

```
Context changes → Container watcher → Claude analysis → Output files → Host notifier → Slack DM
```

**Benefits:**
- Immediate awareness of Claude's work
- No need to check `~/sharing/notifications/` manually
- Get notified about summaries, draft responses, and action items
- Works alongside the container watcher automatically

**Quick Setup:**

See [../HOST-SLACK-NOTIFIER.md](../HOST-SLACK-NOTIFIER.md) for complete instructions.

```bash
# On host machine (not in container)
sudo dnf install inotify-tools jq  # Install dependencies
export SLACK_TOKEN="xoxb-your-token-here"  # Set Slack token
~/khan/james-in-a-box/scripts/setup-host-notifier.sh  # Run setup
~/khan/james-in-a-box/scripts/host-notify-ctl.sh start  # Start service
```

## Support

- Configuration: Edit `~/sharing/config/context-watcher.yaml`
- Slash command: Edit `~/.claude/commands/analyze-context-changes.md`
- Watcher logic: Edit `~/khan/james-in-a-box/internal/context-watcher.sh`
- Report issues: Check logs and adjust configuration
