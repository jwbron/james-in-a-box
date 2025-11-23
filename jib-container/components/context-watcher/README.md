# Context Watcher

Monitors `~/context-sync/` for Confluence and JIRA document updates.

**Status**: Operational
**Type**: Container component (runs inside Docker)
**Purpose**: Notify agent when context documents change

## Overview

The context watcher uses `inotifywait` to monitor the context sync directory for changes:
- Confluence docs (`~/context-sync/confluence/`)
- JIRA tickets (`~/context-sync/jira/`)

When changes are detected, it can trigger agent workflows to incorporate new context.

## How It Works

1. Starts automatically when container launches (via `docker-setup.py`)
2. Watches `~/context-sync/` recursively for file changes
3. Logs events to `~/sharing/tracking/watcher.log`
4. Agent can read logs to detect new context availability

## Management

The watcher starts automatically. Manual control:

```bash
# Inside container
./context-watcher-ctl start
./context-watcher-ctl stop
./context-watcher-ctl status

# View logs
tail -f ~/sharing/tracking/watcher.log
```

## Configuration

See `config/README.md` for filtering options and watch patterns.

## Files

- `context-watcher-ctl` - Control script (start/stop/status)
- `context-watcher.sh` - Main watcher script
- `config/` - Configuration files

## Troubleshooting

**Watcher not starting**:
```bash
# Check if running
ps aux | grep context-watcher

# Check logs
cat ~/sharing/tracking/watcher.log

# Restart
./context-watcher-ctl restart
```

**Directory not found**:
- Ensure `~/context-sync/` is mounted from host
- Check Docker volume mounts in `jib` script
