# Context Watcher - Systemd Service

This directory contains systemd user service configuration for running context-watcher as a background service.

## Quick Start

```bash
# Enable and start the watcher
./manage_watcher.sh enable

# Check status
./manage_watcher.sh status

# View logs
./manage_watcher.sh logs
```

## What It Does

The context-watcher service:
- Runs continuously in the background as a systemd user service
- Monitors `~/context-sync/` for changes every 5 minutes (configurable)
- Batches changes within a 60-second window
- Triggers Claude analysis for relevant changes
- Saves notifications to `~/sharing/notifications/`
- Tracks state in `~/sharing/tracking/watcher-state.json`
- Logs to systemd journal (viewable with `journalctl`)

## Service vs Timer

**This setup uses a simple service** (not a timer) because:
- The script has its own internal loop with configurable intervals
- It handles batching and debouncing internally
- It maintains persistent state between checks
- Simpler to manage (one service vs service + timer)

If you prefer a timer-based approach (runs periodically and exits), you could:
1. Modify `context-watcher.sh` to run once and exit
2. Create a `context-watcher.timer` similar to `context-sync.timer`
3. Change service `Type=oneshot` instead of `Type=simple`

## Management Commands

### Enable Service (Start on Boot)

```bash
./manage_watcher.sh enable
```

This will:
1. Create a symlink in `~/.config/systemd/user/`
2. Reload systemd daemon
3. Enable the service to start on boot
4. Start the service immediately

### Check Status

```bash
./manage_watcher.sh status
```

Shows:
- Service status (running/stopped)
- Lock file status
- Current state file contents

### View Logs

```bash
# Recent logs
./manage_watcher.sh logs

# Follow logs in real-time
./manage_watcher.sh logs-follow
```

### Control Service

```bash
# Start (if stopped)
./manage_watcher.sh start

# Stop
./manage_watcher.sh stop

# Restart
./manage_watcher.sh restart

# Disable (stop and prevent auto-start)
./manage_watcher.sh disable
```

## Configuration

### Initial Setup

Run the setup script to create your configuration:

```bash
cd ~/khan/cursor-sandboxed/context-watcher
./setup.sh
```

This creates `~/.config/context-watcher/config.yaml` with secure permissions (600).

### Watcher Settings

Edit `~/.config/context-watcher/config.yaml`:

```yaml
processing:
  check_interval_seconds: 300  # How often to check for changes
  batch_changes: true
  batch_window_seconds: 60     # Wait this long for more changes
```

### Service Settings

Edit `systemd/context-watcher.service` to change:

```ini
# Restart behavior
Restart=on-failure
RestartSec=30s

# Resource limits
Nice=10  # Lower priority (0-19, higher = lower priority)
```

After editing, reload:
```bash
systemctl --user daemon-reload
./manage_watcher.sh restart
```

## File Locations

### Repository (Code)
- Service definition: `~/khan/cursor-sandboxed/context-watcher/systemd/context-watcher.service`
- Script: `~/khan/cursor-sandboxed/scripts/context-watcher.sh`
- Template config: `~/khan/cursor-sandboxed/context-watcher/config/context-watcher.yaml`

### User Config (~/.config/context-watcher/)
- **Config**: `~/.config/context-watcher/config.yaml` (permissions: 600)
- **State**: `~/.config/context-watcher/watcher-state.json`
- **Logs**: `~/.config/context-watcher/watcher.log`
- **Permissions**: Directory is 700, config file is 600 for security

### Systemd
- Installed service: `~/.config/systemd/user/context-watcher.service` (symlink)
- Systemd logs: `journalctl --user -u context-watcher.service`

### Runtime
- Lock file: `/tmp/context-watcher.lock` (prevents multiple instances)
- Notifications: `~/.claude-sandbox-sharing/notifications/`

## Troubleshooting

### Service Won't Start

```bash
# Check the service status
./manage_watcher.sh status

# View detailed logs
./manage_watcher.sh logs

# Check if lock file is stale
ls -la /tmp/context-watcher.lock
# If stale, remove it:
rm /tmp/context-watcher.lock
```

### Changes Not Being Detected

```bash
# Check if service is running
./manage_watcher.sh status

# Verify context-sync directory exists
ls -la ~/context-sync/

# Check state file
cat ~/sharing/tracking/watcher-state.json

# Manually trigger a check (restart service)
./manage_watcher.sh restart
```

### High CPU/Memory Usage

The service runs with reduced priority (`Nice=10`) by default. To further limit resources:

Edit `systemd/context-watcher.service`:
```ini
# Add under [Service]
CPUQuota=50%          # Limit to 50% of one CPU
MemoryMax=500M        # Limit to 500MB RAM
```

Then:
```bash
systemctl --user daemon-reload
./manage_watcher.sh restart
```

### View What the Watcher is Doing

```bash
# Follow logs in real-time
./manage_watcher.sh logs-follow

# Check last activity
tail -f ~/sharing/tracking/watcher.log

# See what files were last processed
cat ~/sharing/tracking/watcher-state.json | jq '.'
```

## Integration with Claude Sandboxed

The context-watcher can trigger Claude analysis, but note that:

- `~/khan/` is mounted **read-only** in claude-sandboxed
- The watcher runs on the **host**, not in the container
- If the watcher invokes Claude, it would need to:
  - Run `claude` on the host (with full access), OR
  - Stage notifications in `~/sharing/` for review

### Current Behavior

The script at line 128 attempts to run:
```bash
claude --prompt-file "$prompt_file" --output-dir ~/sharing/notifications
```

This runs Claude **on the host** with full access. If you want Claude to run in the sandbox instead, modify the script to:

```bash
# Option 1: Save prompt for manual review
cp "$prompt_file" ~/sharing/notifications/pending-analysis-$(date +%s).txt

# Option 2: Invoke claude-sandboxed container
docker exec claude-sandbox claude --prompt-file "/path/to/prompt"
```

## Comparison with context-sync

| Feature | context-sync | context-watcher |
|---------|-------------|-----------------|
| Type | Timer (periodic) | Service (continuous) |
| Runs | Every 15 min | Checks every 5 min |
| Duration | Runs and exits | Runs continuously |
| Purpose | Pull updates | Monitor changes |
| Output | `~/context-sync/` | `~/sharing/notifications/` |
| Config | `.env` file | YAML config |

Both can run simultaneously - context-sync pulls updates, context-watcher monitors for changes.

## Uninstall

```bash
# Disable and remove
./manage_watcher.sh disable
rm ~/.config/systemd/user/context-watcher.service
systemctl --user daemon-reload
```

The script and config remain in the repository for re-enabling later.
