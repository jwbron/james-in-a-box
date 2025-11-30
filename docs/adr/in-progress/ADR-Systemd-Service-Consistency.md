# ADR: Systemd Service Consistency Standards

**Status:** Draft
**Created:** 2025-11-30
**Author:** jib

## Context

The james-in-a-box project uses multiple systemd services and timers for host-side automation. An audit revealed significant inconsistencies across these services in:
- Service file structure and fields
- Timer configurations
- Setup script behavior (enabling vs just symlinking)
- Documentation URL patterns
- Security hardening

This inconsistency makes maintenance harder and can lead to unexpected behavior during setup.

## Current State Audit

### Services Inventory

| Component | Service Type | Timer? | Setup Enables? | Setup Starts? |
|-----------|--------------|--------|----------------|---------------|
| slack-notifier | simple (long-running) | No | Yes | Yes |
| slack-receiver | simple (long-running) | No | Yes | Yes |
| context-sync | oneshot | Yes (hourly) | Yes | No |
| github-watcher | oneshot | Yes (5min) | No | No |
| worktree-watcher | oneshot | Yes (15min) | Yes | Yes |
| github-token-refresher | simple (long-running) | No | Yes | Yes |
| conversation-analyzer | oneshot | Yes (weekly) | Yes | Yes |
| adr-researcher | oneshot | Yes (weekly) | No | No |
| doc-generator | oneshot | Yes (weekly) | Yes | Yes (dynamically created) |
| index-generator | oneshot | Yes (weekly) | Yes | Yes (dynamically created) |
| spec-enricher | N/A (no systemd) | No | N/A | N/A |

### Inconsistencies Found

#### 1. Service File Structure

**Issue: Inconsistent Unit section fields**

| Service | Documentation | After | Wants | OnFailure |
|---------|--------------|-------|-------|-----------|
| slack-notifier | file:// path | - | - | Yes |
| slack-receiver | https:// URL | network-online.target | Yes | - |
| context-sync | file:// path | - | - | - |
| github-watcher | - | network-online.target | Yes | - |
| worktree-watcher | file:// path | network.target | - | - |
| github-token-refresher | file:// path | network-online.target | Yes | - |
| conversation-analyzer | https:// URL | network-online.target | Yes | Yes |
| adr-researcher | - | network-online.target | Yes | - |

**Problems:**
- Some use `file://` paths, some use `https://` URLs, some have no Documentation
- Inconsistent use of `After=network.target` vs `After=network-online.target`
- Inconsistent use of `Wants=network-online.target`
- Only 2 services have `OnFailure` handlers

#### 2. Timer File Structure

| Timer | OnCalendar | OnBootSec | OnUnitActiveSec | RandomizedDelaySec | Requires | Unit |
|-------|------------|-----------|-----------------|-------------------|----------|------|
| context-sync | hourly | 5min | - | 2min | - | - |
| github-watcher | - | 1min | 5min | - | - | - |
| worktree-watcher | - | 5min | 15min | - | - | - |
| conversation-analyzer | Mon 11:00 | - | - | 5min | Yes | Yes (explicit) |
| adr-researcher | Mon 11:00 | - | - | - | - | - |

**Problems:**
- Only conversation-analyzer explicitly specifies `Requires=` and `Unit=`
- Inconsistent use of RandomizedDelaySec (good for avoiding load spikes)
- Some timers mix OnCalendar with OnBootSec (context-sync), some don't

#### 3. Setup Script Behavior

**Issue: Inconsistent enable/start behavior**

| Script | Creates Dir? | Daemon Reload? | Enables Timer? | Starts Timer? |
|--------|--------------|----------------|----------------|---------------|
| adr-researcher | mkdir state | Yes | No | No |
| github-watcher | mkdir state | Yes | No | No |
| conversation-analyzer | - | Yes | Yes | Yes |
| context-sync | - | Yes | Yes | No |
| worktree-watcher | - | Yes | Yes | Yes |
| slack-notifier | - | Yes | Yes | Yes |
| slack-receiver | - | Yes | Yes | Yes |
| github-token-refresher | - | Yes | Yes | Yes |
| doc-generator | - | Yes | Yes | Yes |
| index-generator | - | Yes | Yes | Yes |

**Problems:**
- adr-researcher and github-watcher don't auto-enable their timers
- context-sync enables but doesn't start the timer
- Root setup.sh expects all services to be enabled by their individual setup scripts, but then manually handles enabling them, leading to duplicate/conflicting logic

#### 4. Service Security Hardening

| Service | NoNewPrivileges | PrivateTmp | ProtectSystem | ProtectHome | Nice | IOScheduling |
|---------|-----------------|------------|---------------|-------------|------|--------------|
| slack-notifier | - | - | - | - | 10 | Yes |
| slack-receiver | Yes | Yes | - | - | - | - |
| context-sync | - | - | - | - | 10 | Yes |
| github-watcher | - | - | - | - | - | - |
| worktree-watcher | Yes | Yes | - | - | - | - |
| github-token-refresher | Yes | Yes | strict | read-only | 15 | Yes |
| conversation-analyzer | - | - | - | - | - | - |
| adr-researcher | - | - | - | - | - | - |

**Problems:**
- github-token-refresher has full security hardening, others don't
- No consistent security baseline across services

#### 5. Install Section WantedBy Target

| Service | WantedBy |
|---------|----------|
| slack-notifier | default.target |
| slack-receiver | default.target |
| context-sync | default.target |
| github-watcher | default.target |
| worktree-watcher | (missing [Install]) |
| github-token-refresher | default.target |
| conversation-analyzer | multi-user.target |

**Problems:**
- worktree-watcher.service has no [Install] section
- conversation-analyzer uses multi-user.target instead of default.target

#### 6. Documentation URL Paths

The timer files have hardcoded paths that are user-specific:
- `context-sync.timer`: `file:///home/jwies/khan/confluence-cursor-sync/README.md` (wrong repo!)
- `worktree-watcher.timer`: `file:///home/jwies/khan/james-in-a-box/host-services/worktree-watcher/README.md` (hardcoded user)

These should use `%h` specifier or relative paths.

## Decision

Establish the following standards for systemd services:

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
OnCalendar=<schedule>          # For scheduled tasks
# OR
OnBootSec=<time>               # For periodic tasks
OnUnitActiveSec=<interval>

# Always include:
Persistent=true
RandomizedDelaySec=<appropriate delay>

[Install]
WantedBy=timers.target
```

### Setup Scripts

All setup.sh scripts should:
1. Create systemd user directory
2. Symlink service (and timer if applicable)
3. Reload systemd daemon
4. Enable the service/timer
5. Start the service/timer (unless configuration is required first)

## Consequences

### Positive
- Predictable behavior across all services
- Easier troubleshooting
- Better security posture
- Cleaner codebase

### Negative
- Requires updating all existing service files
- May change behavior for users with existing installations (mitigated by `--update` mode)

## Implementation

See accompanying commits for fixes to:
1. Service file standardization
2. Timer file standardization
3. Setup script consistency
4. Documentation path fixes
