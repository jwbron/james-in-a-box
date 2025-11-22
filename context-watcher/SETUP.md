# Context Watcher Setup Guide

Quick setup guide for the context monitoring system.

## Prerequisites

The SELinux issue has been fixed! The `claude-sandboxed` script now automatically adds the `:z` flag to all mount points, which tells Docker to relabel directories for container access.

## Setup Steps

### 1. Restart the Container (if needed)

If you're already in a running container, you'll need to restart it for the SELinux fixes to take effect:

```bash
# Exit the container
exit

# Rebuild and restart (on host)
~/khan/james-in-a-box/claude-sandboxed
```

### 2. Verify Directories

Once in the container:

```bash
# Check that directories are accessible
ls -la ~/sharing/
ls -la ~/tools/
ls -la ~/context-sync/

# Create necessary subdirectories
mkdir -p ~/sharing/{config,notifications,context-tracking}
mkdir -p ~/sharing/notifications/{draft-responses,action-items,code-plans,code-drafts}
```

### 3. Move Configuration Files

```bash
# Copy config to proper location
cp ~/khan/james-in-a-box/context-watcher/config/context-watcher.yaml ~/sharing/config/

# Edit with your details (name, email, teams, etc.)
vi ~/sharing/config/context-watcher.yaml
```

### 4. Update Watcher Script

The watcher script currently references the old location. Update it:

```bash
# Edit the watcher script
vi ~/khan/james-in-a-box/scripts/context-watcher.sh

# Change line 8 from:
CONFIG_FILE="${HOME}/khan/james-in-a-box/.context-watcher/config/context-watcher.yaml"

# To:
CONFIG_FILE="${HOME}/sharing/config/context-watcher.yaml"

# Change line 9 from:
STATE_FILE="${HOME}/khan/james-in-a-box/.context-watcher/tracking/watcher-state.json"

# To:
STATE_FILE="${HOME}/sharing/context-tracking/watcher-state.json"

# Change line 10 from:
LOG_FILE="${HOME}/khan/james-in-a-box/.context-watcher/tracking/watcher.log"

# To:
LOG_FILE="${HOME}/sharing/context-tracking/watcher.log"
```

Or run this sed command to do it automatically:

```bash
sed -i 's|${HOME}/khan/james-in-a-box/.context-watcher/config/context-watcher.yaml|${HOME}/sharing/config/context-watcher.yaml|' ~/khan/james-in-a-box/scripts/context-watcher.sh
sed -i 's|${HOME}/khan/james-in-a-box/.context-watcher/tracking/watcher-state.json|${HOME}/sharing/context-tracking/watcher-state.json|' ~/khan/james-in-a-box/scripts/context-watcher.sh
sed -i 's|${HOME}/khan/james-in-a-box/.context-watcher/tracking/watcher.log|${HOME}/sharing/context-tracking/watcher.log|' ~/khan/james-in-a-box/scripts/context-watcher.sh
```

### 5. Populate Context Sync Directory

On the host machine (not in container), set up your `~/context-sync` directory:

```bash
# Create the directory
mkdir -p ~/context-sync/{confluence,jira,github,slack}

# Example: Clone your Confluence docs (if you have them in git)
cd ~/context-sync/confluence
git clone <confluence-docs-repo>

# Example: Sync JIRA data (if you have a sync script)
cd ~/context-sync/jira
./sync-jira-data.sh

# Or manually copy exported data
cp -r /path/to/confluence-exports ~/context-sync/confluence/
```

### 6. Start the Watcher

```bash
# Make scripts executable (if not already)
chmod +x ~/khan/james-in-a-box/scripts/context-watcher*.sh

# Start the service
~/khan/james-in-a-box/scripts/context-watcher-ctl.sh start

# Check status
~/khan/james-in-a-box/scripts/context-watcher-ctl.sh status

# Watch logs
~/khan/james-in-a-box/scripts/context-watcher-ctl.sh tail
```

### 7. Test the System

Create a test file to verify everything works:

```bash
# Create a test change
echo "# Test ADR" > ~/context-sync/test-adr.md
echo "Author: Jacob Wiesblatt (@jwies)" >> ~/context-sync/test-adr.md
echo "" >> ~/context-sync/test-adr.md
echo "This is a test ADR to verify the context watcher is working." >> ~/context-sync/test-adr.md

# Wait for the next check cycle (default 5 minutes)
# Or restart the watcher to trigger immediate check
~/khan/james-in-a-box/scripts/context-watcher-ctl.sh restart

# Check for output in ~/sharing/notifications/
ls -la ~/sharing/notifications/

# View any summaries created
cat ~/sharing/notifications/summary-*.md
```

## Verification Checklist

- [ ] Container restarted with SELinux fixes
- [ ] `~/sharing/` directory is accessible
- [ ] `~/tools/` directory is accessible
- [ ] `~/context-sync/` directory exists and has content
- [ ] Configuration file copied to `~/sharing/config/`
- [ ] Configuration file customized with your details
- [ ] Watcher script paths updated
- [ ] Watcher service starts successfully
- [ ] Logs show watcher is monitoring
- [ ] Test file triggers analysis
- [ ] Outputs appear in `~/sharing/notifications/`

## Troubleshooting

### Still Getting Permission Denied

If you still can't access `~/sharing/` or `~/tools/` after restarting:

1. Check the mount in the container:
   ```bash
   mount | grep sharing
   mount | grep tools
   ```

2. Check if the `:z` flag is present in the mount options

3. If not, you may need to manually relabel from the host:
   ```bash
   # On host (outside container):
   sudo chcon -R -t container_file_t ~/.jib-sharing/
   sudo chcon -R -t container_file_t ~/.jib-tools/
   sudo chcon -R -t container_file_t ~/context-sync/
   ```

### Watcher Not Starting

1. Check for lock files:
   ```bash
   ls -la /tmp/context-watcher.lock
   rm /tmp/context-watcher.lock  # if stale
   ```

2. Check logs:
   ```bash
   cat ~/sharing/context-tracking/watcher.log
   ```

3. Test Claude CLI:
   ```bash
   claude --version
   which claude
   ```

### No Analysis Happening

1. Verify files are actually changing:
   ```bash
   touch ~/context-sync/test-change.txt
   ```

2. Check watcher state:
   ```bash
   cat ~/sharing/context-tracking/watcher-state.json
   ```

3. Manually trigger analysis:
   ```bash
   claude analyze-context-changes
   ```

## Next Steps

1. Populate `~/context-sync/` with your actual data sources
2. Configure automatic syncing of Confluence, JIRA, GitHub data to `~/context-sync/`
3. Adjust check interval in config if 5 minutes is too long/short
4. Review and iterate on the Claude analysis prompts in `~/.claude/commands/analyze-context-changes.md`
5. Set up auto-start in your `.bashrc` or container init script
6. **[Optional]** Set up host-side Slack notifier to get DMs when Claude creates outputs

## Auto-Start on Container Launch

Add to `~/.bashrc`:

```bash
# Auto-start context watcher
if [ -f ~/khan/james-in-a-box/scripts/context-watcher-ctl.sh ]; then
    ~/khan/james-in-a-box/scripts/context-watcher-ctl.sh start >/dev/null 2>&1
fi
```

Then the watcher will automatically start whenever you launch the container.

## Host-Side Slack Integration (Optional)

The context watcher writes outputs to `~/sharing/notifications/`. To get instant Slack notifications when Claude creates these files, you can set up the **host-side Slack notifier**.

This is a separate service that runs on your **host machine** (outside the container) and watches the shared directories for changes.

**Complete Flow:**
1. Context watcher (in container) detects changes in `~/context-sync/`
2. Claude analyzes and writes summaries to `~/sharing/notifications/`
3. Host notifier (on host) detects new files in `~/.jib-sharing/`
4. Slack DM sent to you with summary

**Setup:**

See [HOST-SLACK-NOTIFIER.md](../HOST-SLACK-NOTIFIER.md) for complete instructions.

Quick start:
```bash
# On host machine (not in container)

# 1. Install dependencies
sudo dnf install inotify-tools jq  # Fedora
# or
sudo apt install inotify-tools jq  # Ubuntu

# 2. Get Slack bot token from https://api.slack.com/apps
export SLACK_TOKEN="xoxb-your-token-here"

# 3. Run setup
~/khan/james-in-a-box/scripts/setup-host-notifier.sh

# 4. Start the notifier
~/khan/james-in-a-box/scripts/host-notify-ctl.sh start
```

This gives you immediate awareness whenever Claude creates notifications, draft responses, or action items.
