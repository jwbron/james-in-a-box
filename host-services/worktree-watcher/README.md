# Worktree Watcher

Automatically cleans up orphaned git worktrees from stopped or crashed jib containers.

**Status**: Operational
**Type**: Host-side systemd timer service
**Purpose**: Prevent worktree accumulation and disk space waste

## Overview

Each jib container gets its own ephemeral git worktree to isolate changes from the host repository. When containers exit normally, worktrees are cleaned up automatically. However, if a container crashes or is forcefully killed, worktrees may be left behind.

This service runs periodically to detect and remove orphaned worktrees.

## How It Works

1. **Timer triggers every 15 minutes**
2. **Scans** `~/.jib-worktrees/` for container worktree directories
3. **Checks** if corresponding Docker container still exists
4. **Removes** worktrees and directories for non-existent containers
5. **Logs** all cleanup operations to systemd journal

## Worktree Layout

```
~/.jib-worktrees/
├── jib-20251123-103045-12345/    # Container ID (timestamp-based)
│   ├── webapp/                   # Worktree for webapp repo
│   ├── frontend/                 # Worktree for frontend repo
│   └── ...
└── jib-20251123-103120-12346/
    ├── webapp/
    └── ...
```

Each container gets a unique ID based on timestamp and process ID.

## Setup

```bash
cd ~/khan/james-in-a-box/host-services/worktree-watcher
./setup.sh
```

This installs and starts the systemd timer.

## Management

```bash
# Check timer status
systemctl --user status worktree-watcher.timer

# Check service status (last run)
systemctl --user status worktree-watcher.service

# View logs
journalctl --user -u worktree-watcher.service -f

# Manual cleanup run (don't wait for timer)
systemctl --user start worktree-watcher.service

# Stop timer
systemctl --user stop worktree-watcher.timer

# Disable timer (won't start on boot)
systemctl --user disable worktree-watcher.timer
```

## Files

- `worktree-watcher.sh` - Main cleanup script
- `worktree-watcher.service` - Systemd service file
- `worktree-watcher.timer` - Systemd timer file
- `setup.sh` - Installation script

## Schedule

- **On boot**: 5 minutes after system starts
- **Recurring**: Every 15 minutes
- **Persistent**: Timer state persists across reboots

## Safety

The watcher only removes worktrees for containers that no longer exist. If a container is running or stopped (but not removed), its worktrees are preserved.

## Manual Cleanup

To manually clean up all worktrees:

```bash
# Stop all jib containers first
docker stop $(docker ps -q --filter "name=jib-")

# Run cleanup
systemctl --user start worktree-watcher.service

# Or run script directly
~/khan/james-in-a-box/host-services/worktree-watcher/worktree-watcher.sh
```

## Troubleshooting

### Worktrees not being cleaned up

Check if timer is running:
```bash
systemctl --user list-timers | grep worktree
```

If not listed, enable and start:
```bash
systemctl --user enable worktree-watcher.timer
systemctl --user start worktree-watcher.timer
```

### Permission errors

Ensure script is executable:
```bash
chmod +x ~/khan/james-in-a-box/host-services/worktree-watcher/worktree-watcher.sh
```

### View cleanup history

```bash
journalctl --user -u worktree-watcher.service --since "1 day ago"
```

## Integration

This component works with:
- **bin/jib**: Creates worktrees on container start, cleans up on normal exit
- **Worktree Watcher**: Handles cleanup for crashed/killed containers
- **Docker containers**: Each container gets isolated workspace

Together, they ensure your host repositories (`~/khan/webapp`, etc.) stay clean while containers can work independently.
