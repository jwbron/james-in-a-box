# Host Services

This directory contains systemd services and timers that run on the host machine to support james-in-a-box.

## Services Overview

| Component | Type | Timer | Description |
|-----------|------|-------|-------------|
| slack-notifier | simple (long-running) | No | Sends Slack notifications |
| slack-receiver | simple (long-running) | No | Receives Slack messages |
| context-sync | oneshot | hourly | Syncs Confluence/JIRA context |
| github-watcher | oneshot | 5min | Monitors GitHub for activity |
| worktree-watcher | oneshot | 15min | Cleans orphaned git worktrees |
| github-token-refresher | simple (long-running) | No | Refreshes GitHub App tokens |
| feature-analyzer-watcher | oneshot | 15min | Detects newly implemented ADRs |
| conversation-analyzer | oneshot | weekly | Analyzes conversation patterns |
| adr-researcher | oneshot | weekly | Researches ADR topics |
| doc-generator | oneshot | weekly | Generates documentation |
| index-generator | oneshot | weekly | Generates doc index |

## Systemd Standards

All services follow these conventions for consistency.

### Service Files

```ini
[Unit]
Description=JIB <Component Name> - <Brief description>
Documentation=file://%h/khan/james-in-a-box/host-services/<path>/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=<oneshot|simple>
WorkingDirectory=%h/khan/james-in-a-box
ExecStart=<command>

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=<component-name>

# Security (baseline for all services)
NoNewPrivileges=yes
PrivateTmp=yes

# For long-running services only:
Restart=on-failure
RestartSec=30s

[Install]
WantedBy=default.target
```

### Timer Files

```ini
[Unit]
Description=<Timer description>
Documentation=file://%h/khan/james-in-a-box/host-services/<path>/README.md

[Timer]
# Choose one scheduling approach:
OnCalendar=<schedule>          # For scheduled tasks (e.g., "Mon 11:00", "hourly")
# OR
OnBootSec=<time>               # For periodic tasks (e.g., "5min")
OnUnitActiveSec=<interval>     # Repeat interval (e.g., "15min")

# Always include:
Persistent=true
RandomizedDelaySec=<appropriate delay>

[Install]
WantedBy=timers.target
```

### Key Standards

1. **Documentation paths**: Use `%h` specifier instead of hardcoded paths (e.g., `file://%h/khan/...` not `file:///home/user/khan/...`)

2. **WantedBy target**: Use `default.target` for services (user session), `timers.target` for timers

3. **Network dependencies**: Use `After=network-online.target` and `Wants=network-online.target` for services that need network

4. **Security baseline**: All services should include at minimum:
   - `NoNewPrivileges=yes`
   - `PrivateTmp=yes`

5. **Logging**: Always include `StandardOutput=journal`, `StandardError=journal`, and `SyslogIdentifier=<name>`

### Setup Scripts

All `setup.sh` scripts should:

1. Create `~/.config/systemd/user/` directory if needed
2. Symlink the service file (and timer if applicable)
3. Reload systemd daemon: `systemctl --user daemon-reload`
4. Enable the service/timer: `systemctl --user enable <name>`
5. Start the service/timer: `systemctl --user start <name>`

## Common Commands

```bash
# View all JIB timers
systemctl --user list-timers | grep -E "(context|github|worktree|conversation|adr|doc|index)"

# Check service status
systemctl --user status <service-name>

# View logs
journalctl --user -u <service-name> -f

# Run a oneshot service manually
systemctl --user start <service-name>.service

# Restart a long-running service
systemctl --user restart <service-name>
```

## Directory Structure

```
host-services/
├── analysis/
│   ├── adr-researcher/      # Weekly ADR research
│   ├── conversation-analyzer/# Weekly conversation analysis
│   ├── doc-generator/       # Documentation generation
│   ├── feature-analyzer/    # ADR detection & doc sync (15min)
│   ├── github-watcher/      # GitHub activity monitor
│   ├── index-generator/     # Doc index generation
│   └── spec-enricher/       # Spec enrichment (no systemd)
├── slack/
│   ├── slack-notifier/      # Outbound Slack messages
│   └── slack-receiver/      # Inbound Slack messages
├── sync/
│   └── context-sync/        # Confluence/JIRA sync
└── utilities/
    ├── github-token-refresher/  # Token management
    └── worktree-watcher/        # Git worktree cleanup
```
