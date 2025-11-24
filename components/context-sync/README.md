# Context Sync

Syncs documentation and context from multiple sources (Confluence, JIRA, etc.) to `~/context-sync/` for AI agent access.

**Status**: Operational
**Type**: Host-side systemd timer service
**Purpose**: Provide Claude with current project context (docs, tickets, ADRs)

## Overview

Context Sync is a multi-connector tool that automatically syncs external knowledge sources into a local directory that jib containers can access read-only. This gives Claude access to:

- **Confluence**: ADRs, runbooks, best practices, team documentation
- **JIRA**: Your assigned tickets, project context, requirements
- **(Planned)** GitHub PRs, Slack threads, email chains

## How It Fits Into jib

```
Confluence/JIRA (remote)
        ↓
Context Sync (host systemd timer, runs hourly)
        ↓
~/context-sync/               # Synced markdown files
├── confluence/
│   ├── ENG/                  # Engineering docs
│   ├── INFRA/                # Infrastructure docs
│   └── PRODUCT/              # Product docs
└── jira/
    ├── ASSIGNED/             # Your tickets
    └── WATCHING/             # Watched tickets
        ↓
jib Container (read-only mount)
~/context-sync/ -> Claude can read these docs
```

**Benefits:**
- Claude has access to latest ADRs, runbooks, and team practices
- Tickets are available for context when implementing features
- Content is synced automatically (hourly) - always fresh
- Fully offline after sync - works without network in container

## Setup

```bash
cd ~/khan/james-in-a-box/components/context-sync
./setup.sh
```

This will:
- Create Python virtual environment
- Install dependencies
- Set up systemd timer for hourly syncing
- Enable the service

## Configuration

Create `~/.config/context-sync/.env` with your credentials:

```bash
# Confluence
CONFLUENCE_URL=https://khanacademy.atlassian.net/wiki
CONFLUENCE_USERNAME=your-email@khanacademy.org
CONFLUENCE_API_TOKEN=your-token

# JIRA
JIRA_URL=https://khanacademy.atlassian.net
JIRA_USERNAME=your-email@khanacademy.org
JIRA_API_TOKEN=your-token
```

**Getting API tokens:**
- Confluence/JIRA: https://id.atlassian.com/manage-profile/security/api-tokens

## Usage

### Initial Sync

```bash
# Run first sync (may take a few minutes)
systemctl --user start context-sync.service

# Watch progress
journalctl --user -u context-sync.service -f
```

### Enable Automated Syncing

```bash
# Start hourly automated syncing
systemctl --user start context-sync.timer

# Check timer status
systemctl --user status context-sync.timer
```

### Manual Sync

```bash
# Trigger sync manually
systemctl --user start context-sync.service
```

## Management

```bash
# Check timer status
systemctl --user status context-sync.timer

# Check last sync
systemctl --user status context-sync.service

# View logs
journalctl --user -u context-sync.service -n 50

# Stop automated syncing
systemctl --user stop context-sync.timer
```

## Documentation

See detailed documentation in [`docs/`](docs/README.md):

- Full configuration options
- Architecture and design
- Advanced features (search, customization)
- Troubleshooting guide

## Integration with jib

jib containers mount `~/context-sync/` as read-only. Claude can:

- Read ADRs before making architectural decisions
- Check runbooks before operational changes
- Review JIRA tickets for requirements
- Follow team best practices from Confluence

This gives Claude the same context you'd have when making decisions!
