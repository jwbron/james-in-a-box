# Context Watcher - Quick Start

Monitor `~/context-sync/` for changes and trigger Claude analysis for relevant updates.

## One-Time Setup

```bash
cd ~/khan/cursor-sandboxed/context-watcher

# 1. Create configuration
./setup.sh

# 2. Review and customize (optional)
vim ~/.config/context-watcher/config.yaml

# 3. Enable the systemd service
./manage_watcher.sh enable
```

Done! The watcher is now running in the background.

## Usage

### Check Status

```bash
./manage_watcher.sh status
```

### View Logs

```bash
# Recent logs
./manage_watcher.sh logs

# Follow in real-time
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

## How It Works

1. **Monitors**: Watches `~/context-sync/` for file changes
2. **Filters**: Checks if changes are relevant to you (based on `~/.config/context-watcher/config.yaml`)
3. **Batches**: Waits 60 seconds to collect multiple changes
4. **Analyzes**: Triggers Claude to analyze changes
5. **Notifies**: Saves results to `~/.claude-sandbox-sharing/notifications/`
6. **Repeats**: Checks every 5 minutes

## Configuration

Edit `~/.config/context-watcher/config.yaml` to customize:

### What to Watch For

```yaml
user:
  name: "Your Name"
  username: "yourusername"
  email: "you@example.com"

teams:
  - "your-team-name"
  - "@team-mention"

keywords:
  - "specific"
  - "keywords"
  - "to watch"

jira:
  projects:
    - "PROJ"
  assigned_to_me: true
  watching: true
```

### How to Process

```yaml
processing:
  check_interval_seconds: 300  # How often to check (5 minutes)
  batch_changes: true
  batch_window_seconds: 60     # Wait time for batching

actions:
  write_summaries: true
  create_draft_responses: true
  suggest_action_items: true
```

After editing, restart:
```bash
./manage_watcher.sh restart
```

## File Locations

### Configuration and State
- **Config**: `~/.config/context-watcher/config.yaml` (edit this)
- **State**: `~/.config/context-watcher/watcher-state.json` (auto-managed)
- **Logs**: `~/.config/context-watcher/watcher.log`
- **Permissions**: Directory 700, config 600 (secure)

### Notifications
- `~/.claude-sandbox-sharing/notifications/` (Claude's analysis output)

### Systemd
- Service: `~/.config/systemd/user/context-watcher.service` (symlink)
- View: `systemctl --user status context-watcher`

## Examples

### Monitor Infrastructure Platform Changes

```yaml
# ~/.config/context-watcher/config.yaml
teams:
  - "infra-platform"
  - "infrastructure-platform"

keywords:
  - "deployment"
  - "terraform"
  - "kubernetes"

jira:
  projects:
    - "INFRA"
  assigned_to_me: true
```

### Get Notified About ADR Updates

```yaml
keywords:
  - "ADR"
  - "Architecture Decision"
```

The watcher will notify you when:
- ADRs you authored are updated
- Someone comments on your ADRs
- New ADRs mention your team

## Integration with Context-Sync

Works seamlessly with `context-sync`:

```bash
# context-sync pulls updates every 15 minutes
cd ~/khan/confluence-cursor-sync
./manage_scheduler.sh enable

# context-watcher monitors for relevant changes
cd ~/khan/cursor-sandboxed/context-watcher
./manage_watcher.sh enable
```

Flow:
1. **context-sync** pulls Confluence/JIRA updates → `~/context-sync/`
2. **context-watcher** detects changes → triggers Claude analysis
3. **Claude** creates summaries → `~/.claude-sandbox-sharing/notifications/`
4. **You** review notifications and take action

## Troubleshooting

### Service Won't Start

```bash
# Check systemd status
./manage_watcher.sh status

# View error logs
./manage_watcher.sh logs

# Check for stale lock file
rm /tmp/context-watcher.lock
./manage_watcher.sh restart
```

### No Notifications

```bash
# Check if changes are being detected
tail -f ~/.config/context-watcher/watcher.log

# Verify context-sync directory exists
ls ~/context-sync/

# Check configuration
cat ~/.config/context-watcher/config.yaml
```

### High CPU Usage

The watcher runs with low priority (`Nice=10`) by default. Check:

```bash
# View resource usage
systemctl --user status context-watcher

# Check interval settings
grep check_interval ~/.config/context-watcher/config.yaml

# Consider increasing interval to reduce checks:
# check_interval_seconds: 600  # 10 minutes instead of 5
```

## Security

- Config directory: `~/.config/context-watcher/` (permissions: 700)
- Config file: `config.yaml` (permissions: 600)
- No credentials stored (uses Claude OAuth from host)
- Runs as your user (no elevated privileges)

## Uninstall

```bash
# Stop and disable
./manage_watcher.sh disable

# Remove symlink
rm ~/.config/systemd/user/context-watcher.service
systemctl --user daemon-reload

# Optionally remove config
rm -rf ~/.config/context-watcher/
```

The source code remains in `~/khan/cursor-sandboxed/context-watcher/` for re-enabling.

## Next Steps

- **Customize config**: Edit `~/.config/context-watcher/config.yaml` with your teams/keywords
- **Check notifications**: Browse `~/.claude-sandbox-sharing/notifications/`
- **Integrate with workflow**: Review notifications as part of your daily routine
- **Tune frequency**: Adjust `check_interval_seconds` based on your needs

## Documentation

- Full docs: `systemd/README.md`
- Setup guide: `SETUP.md`
- Repository info: `README.md`
