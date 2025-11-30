# JIB Container Log Persistence

This document describes the log persistence and correlation system for JIB containers.

## Overview

JIB containers are ephemeral - they're removed after execution completes. To preserve logs for debugging and auditing, the system now:

1. **Persists container logs** to `~/.jib-sharing/container-logs/`
2. **Creates correlation links** between task IDs, thread timestamps, and container IDs
3. **Maintains a searchable log index** for quick lookups

## Log Locations

| Location | Contents | Persisted? |
|----------|----------|------------|
| `~/.jib-sharing/container-logs/` | Docker container stdout/stderr | Yes |
| `~/.jib-sharing/logs/` | Claude output streams (real-time) | Yes |
| Docker daemon logs | Internal Docker logs | Via json-file driver |

## Log Correlation

Every container execution is tagged with correlation IDs:

### Environment Variables (Inside Container)
- `CONTAINER_ID` - Unique container identifier (e.g., `jib-exec-20251129-222239-12345`)
- `JIB_TASK_ID` - Task identifier from Slack (e.g., `task-20251129-222239`)
- `JIB_THREAD_TS` - Slack thread timestamp (e.g., `1764483758.159619`)

### Docker Labels
- `jib.container_id` - Container ID label
- `jib.task_id` - Task ID label (if available)

### Log Index File
`~/.jib-sharing/container-logs/log-index.json` contains:
```json
{
  "task_to_container": {
    "task-20251129-222239": "jib-exec-20251129-222239-12345"
  },
  "thread_to_task": {
    "1764483758.159619": "task-20251129-222239"
  },
  "entries": [
    {
      "container_id": "jib-exec-20251129-222239-12345",
      "task_id": "task-20251129-222239",
      "thread_ts": "1764483758.159619",
      "log_file": "/home/user/.jib-sharing/container-logs/jib-exec-20251129-222239-12345.log",
      "timestamp": "2025-11-29T22:22:39.123456"
    }
  ]
}
```

## Using the jib-logs Utility

The `jib-logs` utility provides easy access to persisted logs:

### List Recent Logs
```bash
jib-logs                    # List last 20 logs
jib-logs --list 50          # List last 50 logs
```

### View Logs for a Task
```bash
jib-logs task-20251129-222239
```

### Search Logs
```bash
jib-logs --search "error"           # Search all logs
jib-logs --search "authentication"  # Case-insensitive regex
```

### Follow Logs (Tail)
```bash
jib-logs --tail task-20251129-222239
```

### Clean Up Old Logs
```bash
jib-logs --cleanup --days 7         # Remove logs older than 7 days
jib-logs --cleanup --days 30 --dry-run  # Preview what would be removed
```

## Log File Structure

Each container log file contains:

```
=== Container: jib-exec-20251129-222239-12345 ===
=== Saved: 2025-11-29T22:25:00.123456 ===
=== Task ID: task-20251129-222239 ===
=== Thread TS: 1764483758.159619 ===
==================================================

=== STDOUT ===
[Container stdout output...]

=== STDERR ===
[Container stderr output...]
```

## Correlation Flow

When a Slack message triggers a container:

1. **slack-receiver** writes message to `~/.jib-sharing/incoming/task-{timestamp}.md`
2. **jib --exec** extracts task_id and thread_ts from the task file
3. Container is started with correlation environment variables and Docker labels
4. On container exit, logs are captured via `docker logs` and saved
5. Log index is updated with correlation mappings
6. Symlink is created: `task-{id}.log -> jib-exec-{container-id}.log`

## Debugging a Slack Thread

To find all logs related to a Slack thread:

```bash
# If you have the thread timestamp
jib-logs --search "1764483758.159619"

# If you have the task ID
jib-logs task-20251129-222239

# Search by content
jib-logs --search "your error message"
```

## Storage Management

Logs are stored with rotation:
- Container logs: No automatic rotation (use `jib-logs --cleanup`)
- Claude output logs: Also use manual cleanup

Recommended cleanup policy:
```bash
# Add to crontab for weekly cleanup
0 0 * * 0 /path/to/jib-logs --cleanup --days 14
```

## Troubleshooting

### Logs Not Being Saved
1. Check if `~/.jib-sharing/container-logs/` exists and is writable
2. Verify container completed (not killed mid-execution)
3. Check jib launcher output for errors

### Can't Find Logs for a Task
1. Try searching: `jib-logs --search "task-20251129"`
2. Check the log index: `cat ~/.jib-sharing/container-logs/log-index.json`
3. List all logs: `jib-logs --list 100`

### Old Logs Taking Up Space
```bash
# Check disk usage
du -sh ~/.jib-sharing/container-logs/
du -sh ~/.jib-sharing/logs/

# Clean up
jib-logs --cleanup --days 7
```
