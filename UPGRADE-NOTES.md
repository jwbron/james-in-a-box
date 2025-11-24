# Upgrade Notes: Exec-Based Architecture

This document describes how to upgrade your JIB installation to the new exec-based architecture.

## What Changed

### Architecture Changes
- **Watchers refactored** from continuous background processes → exec-based triggered analysis
- **jib --exec** now uses running container via `docker exec` (instead of spawning new containers)
- **Worktree support** added for git isolation with `--worktree` flag
- **All analysis scripts** now triggered by systemd services via `jib --exec --worktree`

### Files Modified
- `bin/jib` (jib-container/jib) - Exec and worktree support
- `Dockerfile` - Removed background watchers
- `components/github-sync/systemd/github-sync.service` - Added ExecStartPost
- `components/context-sync/systemd/context-sync.service` - Added ExecStartPost
- `components/slack-receiver/host-receive-slack.py` - Triggers via jib --exec

### Files Created
- `jib-container/components/github-watcher/check-monitor.py` - One-shot analysis
- `jib-container/components/incoming-processor.py` - Slack message processor

## Upgrade Steps

### 1. Pull Latest Changes
```bash
cd ~/khan/james-in-a-box
git pull origin main  # or: git fetch && git merge
```

### 2. Rebuild Docker Image
The Dockerfile changed significantly (removed background watchers, added new scripts):
```bash
bin/jib --rebuild
```

This will:
- Build new image with exec-based architecture
- Include new scripts (check-monitor.py, incoming-processor.py)
- Mount worktree base directory for isolation

### 3. Update Systemd Services
The service files now include `ExecStartPost` to trigger analysis:

```bash
# Update github-sync service
cd ~/khan/james-in-a-box/components/github-sync
./setup.sh

# Update context-sync service
cd ~/khan/james-in-a-box/components/context-sync
./setup.sh
```

This will:
- Install updated service files with ExecStartPost directives
- Reload systemd daemon
- Services will now trigger analysis after syncing

### 4. Restart Slack Receiver
The slack-receiver code changed to trigger via jib --exec:
```bash
systemctl --user restart slack-receiver.service
```

### 5. Verify Everything Works

**Check services are running:**
```bash
systemctl --user status github-sync.timer
systemctl --user status context-sync.timer
systemctl --user status slack-receiver.service
```

**Test github-sync (triggers analysis):**
```bash
systemctl --user start github-sync.service
journalctl --user -u github-sync.service -f
# Should see: Sync completes → Triggers check-monitor.py via jib --exec
```

**Test context-sync (triggers two watchers):**
```bash
systemctl --user start context-sync.service
journalctl --user -u context-sync.service -f
# Should see: Sync completes → Triggers jira-watcher.py and confluence-watcher.py
```

**Test jib --exec with worktree:**
```bash
# Start a JIB container first
bin/jib

# In another terminal, test exec with worktree
cd ~/khan/james-in-a-box
bin/jib --exec --worktree python3 -c "import os; print('Working dir:', os.getcwd())"
# Should see: Creates worktree → Runs command → Cleans up worktree
```

## What to Expect

### Before (Old Architecture)
```
Container starts → Background watchers start
  ↓
Watchers poll every 5 minutes
  ↓
Check for changes → Process → Repeat forever
```

### After (New Architecture)
```
Host service syncs data → Completes
  ↓
ExecStartPost triggers: jib --exec --worktree <script>
  ↓
Container: docker exec in running container
  ↓
Create temp worktree → Run script once → Exit → Cleanup worktree
```

### Benefits You'll Notice
- **Lower resource usage** - No continuous polling loops in container
- **Faster startup** - Container starts immediately (no watcher initialization)
- **Clearer logs** - Analysis runs appear in systemd journal for each service
- **Easier debugging** - Can manually trigger: `bin/jib --exec <script>`
- **Git isolation** - Multiple analyses can run concurrently without conflicts

## Troubleshooting

### "No running JIB container found"
If you see this when running `jib --exec`, start a container first:
```bash
bin/jib
```

### Analysis not running after sync
Check the service has ExecStartPost:
```bash
systemctl --user cat github-sync.service | grep ExecStartPost
# Should show: ExecStartPost=.../bin/jib --exec --worktree ...
```

If not, re-run setup:
```bash
cd ~/khan/james-in-a-box/components/github-sync
./setup.sh
```

### Worktree errors
Check that worktree base is mounted:
```bash
# Inside container
ls -la ~/.jib-worktrees/
# Should exist (may be empty if no exec commands recently run)
```

### Service fails to start
Check logs:
```bash
journalctl --user -u github-sync.service -n 50
journalctl --user -u context-sync.service -n 50
```

Common issues:
- Script path wrong (check ExecStartPost in service file)
- Container not running (start with `bin/jib`)
- Permissions (ensure scripts are executable)

## Rollback (If Needed)

If you encounter issues and need to roll back:

```bash
cd ~/khan/james-in-a-box
git log --oneline -10  # Find commit before refactoring
git checkout <commit-before-refactoring>
bin/jib --rebuild
# Re-run setup scripts for services
```

The old architecture commits are:
- Before exec-based refactoring: Check git log before commit `2e91e35`

## Questions?

If you encounter issues, check:
1. Docker container is running: `docker ps | grep jib`
2. Services are active: `systemctl --user list-units | grep -E "github-sync|context-sync|slack"`
3. Logs for errors: `journalctl --user -u <service-name> -n 50`

File issues at: https://github.com/anthropics/claude-code/issues
