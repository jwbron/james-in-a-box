# Container Directory Watcher

Automatically cleans up orphaned container directories from stopped or crashed jib containers.

**Status**: Operational
**Type**: Host-side systemd timer service
**Purpose**: Prevent disk space accumulation from orphaned container data

## Overview

Each jib container gets its own **isolated git directory** in `~/.jib-worktrees/{container-id}/`. This directory contains:
- Isolated `.git-{repo}` directories with independent git state
- Working tree copies for code editing

When containers exit normally, these directories are cleaned up automatically. However, if a container crashes or is forcefully killed, directories may be left behind.

This service runs periodically to detect and remove orphaned directories.

## Isolation Model

With the isolated git approach:
- **Complete isolation**: Each container has its own git refs, branches, and config
- **No shared state**: Containers cannot affect host repos or each other
- **Simple cleanup**: Just delete the container directory (no git operations needed)
- **Object sharing**: Git objects are shared via alternates (read-only, safe)

## How It Works

1. **Timer triggers every 15 minutes**
2. **Scans** `~/.jib-worktrees/` for container directories
3. **Checks** if corresponding Docker container still exists
4. **Removes** directories for non-existent containers
5. **Logs** all cleanup operations to systemd journal

## Directory Layout

```
~/.jib-worktrees/
├── jib-20251123-103045-12345/       # Container ID (timestamp-based)
│   ├── .git-webapp/                  # Isolated git dir for webapp
│   ├── .git-frontend/                # Isolated git dir for frontend
│   ├── webapp/                       # Working tree (worktree of .git-webapp)
│   ├── frontend/                     # Working tree (worktree of .git-frontend)
│   └── ...
└── jib-exec-20251123-103120-12346/   # Exec container
    ├── .git-webapp/
    ├── webapp/
    └── ...
```

Each container gets a unique ID based on timestamp and process ID.

## Setup

```bash
cd ~/khan/james-in-a-box/host-services/utilities/worktree-watcher
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

The watcher only removes directories for containers that no longer exist. If a container is running or stopped (but not removed), its directory is preserved.

**Note**: With isolated git, there are no shared branches or refs to worry about. Each container's git state is completely independent and ephemeral.

## Manual Cleanup

To manually clean up all container directories:

```bash
# Stop all jib containers first
docker stop $(docker ps -q --filter "name=jib-")

# Run cleanup
systemctl --user start worktree-watcher.service

# Or run script directly
~/khan/james-in-a-box/host-services/utilities/worktree-watcher/worktree-watcher.sh
```

## Troubleshooting

### Directories not being cleaned up

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

Some files may be owned by root (from Docker). Manual cleanup:
```bash
sudo rm -rf ~/.jib-worktrees/jib-{container-id}
```

### View cleanup history

```bash
journalctl --user -u worktree-watcher.service --since "1 day ago"
```

## Integration

This component works with:
- **jib**: Creates isolated git directories on container start, cleans up on normal exit
- **Worktree Watcher**: Handles cleanup for crashed/killed containers
- **Docker containers**: Each container gets completely isolated workspace

Together, they ensure your host repositories (`~/khan/webapp`, etc.) are **never modified** by container operations.
