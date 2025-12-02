# Context Management Features

External knowledge synchronization and persistent task tracking.

## Overview

JIB maintains context across container restarts and external systems through:
- **Context Sync**: Automated syncing of Confluence, JIRA, and other knowledge sources
- **Beads**: Persistent task tracking system for memory across sessions
- **PR Context**: Lifecycle tracking for GitHub PRs

## Features

### Context Sync Service

**Purpose**: Syncs external knowledge sources (Confluence, JIRA) to local files for agent access.

**Location**: `host-services/sync/context-sync/`

**Helper Scripts**:
```bash
# Manual sync
python host-services/sync/context-sync/sync_all.py

# Search synced docs
python host-services/sync/context-sync/utils/search.py "search term"

# Check sync status
python host-services/sync/context-sync/utils/maintenance.py status
```

**Service Management**:
```bash
systemctl --user status context-sync.service
systemctl --user start context-sync.timer  # Enable hourly sync
journalctl --user -u context-sync.service -f
```

**Configuration**: `~/.jib-sharing/.env`
```bash
# Confluence
CONFLUENCE_URL=https://your-domain.atlassian.net
CONFLUENCE_USER=email@example.com
CONFLUENCE_TOKEN=api_token
CONFLUENCE_SPACES=SPACE1,SPACE2

# JIRA
JIRA_URL=https://your-domain.atlassian.net
JIRA_USER=email@example.com
JIRA_TOKEN=api_token
JIRA_JQL="project = PROJ AND assignee = currentUser()"
```

**Key Capabilities**:
- Incremental sync with change detection
- HTML to Markdown conversion
- Hierarchical directory structure
- Comment synchronization

### Confluence Connector

**Purpose**: Syncs Confluence pages including ADRs, runbooks, and team docs.

**Location**: `host-services/sync/context-sync/connectors/confluence/`

**Synced Data**:
```
~/context-sync/confluence/
├── SPACE1/
│   ├── README.md      # Space index
│   ├── page1.md
│   └── subdirectory/
│       └── page2.md
└── SPACE2/
    └── ...
```

**Commands**:
```bash
# Sync specific space
python -c "from connectors.confluence import sync; sync.sync_space('SPACE1')"

# Sync single page by ID
python -c "from connectors.confluence import sync; sync.sync_page('12345')"

# List available spaces
python host-services/sync/context-sync/utils/list_spaces.py
```

### JIRA Connector

**Purpose**: Syncs JIRA tickets to local markdown files.

**Location**: `host-services/sync/context-sync/connectors/jira/`

**Synced Data**:
```
~/context-sync/jira/
├── README.md          # Query summary
├── PROJ-123.md        # Individual tickets
├── PROJ-124.md
└── ...
```

**Ticket Format**:
```markdown
# PROJ-123: Ticket Title

**Status**: In Progress
**Assignee**: user@example.com
**Priority**: High

## Description
[Ticket description converted from ADF]

## Comments
### Comment by user (2025-12-01)
[Comment text]
```

### Beads Task Tracking

**Purpose**: Persistent task memory across container restarts.

**Location**: `~/beads/` (shared directory)

**Commands**:
```bash
# Always use --allow-stale in ephemeral containers
cd ~/beads

# List tasks
bd --allow-stale list --status in_progress
bd --allow-stale list --label "slack-thread"

# Create task
bd --allow-stale create "Task description" --labels feature,jira-1234

# Update task
bd --allow-stale update bd-xxxx --status in_progress
bd --allow-stale update bd-xxxx --notes "Progress: completed step 1"
bd --allow-stale update bd-xxxx --status closed --notes "Done. PR #42 created."

# Search (title/description only)
bd --allow-stale search "keyword"

# Show task details
bd --allow-stale show bd-xxxx

# Find ready work
bd --allow-stale ready
```

**Status Values**:
- `open`: Task created, not started
- `in_progress`: Actively working
- `blocked`: Waiting on external dependency
- `closed`: Work complete

**Common Labels**:
- Source: `slack`, `slack-thread`, `jira-XXXX`, `github-pr-XX`
- Type: `feature`, `bug`, `refactor`, `docs`, `test`
- Priority: `urgent`, `important`

### JIRA Ticket Processor

**Purpose**: Monitors and analyzes assigned JIRA tickets.

**Location**: `jib-container/jib-tasks/jira/jira-processor.py`

**Invoked by**: Scheduled jobs or manual trigger

**Key Capabilities**:
- Parses requirements from ticket descriptions
- Extracts action items
- Assesses scope and complexity
- Creates Beads tasks for tracking
- Sends proactive Slack notifications

### Sprint Ticket Analyzer

**Purpose**: Analyzes active sprint tickets for recommendations.

**Location**: `jib-container/jib-tasks/jira/analyze-sprint.py`

**Output**: Grouped Slack notifications with:
- Next steps for each ticket
- Suggestions for backlog tickets to pull in
- Risk identification

### PR Context Manager

**Purpose**: Tracks PR lifecycle in Beads for persistent memory.

**Location**: `jib-container/jib-tasks/github/`

**Key Capabilities**:
- Unique task per PR
- Tracks comments, CI failures, reviews
- Enables context continuity across sessions

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  External Sources                     │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐            │
│  │Confluence│   │  JIRA   │   │ GitHub  │            │
│  └────┬────┘   └────┬────┘   └────┬────┘            │
│       │             │             │                  │
└───────┼─────────────┼─────────────┼──────────────────┘
        │             │             │
        ▼             ▼             ▼
┌──────────────────────────────────────────────────────┐
│              Context Sync Service                     │
│  ┌─────────────┐  ┌─────────────┐                   │
│  │  Confluence │  │    JIRA     │                   │
│  │  Connector  │  │  Connector  │                   │
│  └──────┬──────┘  └──────┬──────┘                   │
│         │                │                           │
│         ▼                ▼                           │
│  ~/context-sync/confluence/  ~/context-sync/jira/   │
└──────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│                Container Access                       │
│  ┌─────────────────────────────────────────┐        │
│  │      ~/context-sync/ (read-only)         │        │
│  │      ~/beads/ (read-write)               │        │
│  └─────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────┘
```

## Troubleshooting

### Context sync not running

1. Check timer: `systemctl --user status context-sync.timer`
2. Check service: `systemctl --user status context-sync.service`
3. Manual run: `python host-services/sync/context-sync/sync_all.py`

### Confluence pages missing

1. Verify space is in `CONFLUENCE_SPACES`
2. Check permissions for API token
3. Run: `python host-services/sync/context-sync/utils/list_spaces.py`

### Beads commands failing

1. Always use `--allow-stale` in containers
2. Ensure `cd ~/beads` before commands
3. Check `~/beads/.git` exists

### JIRA tickets not syncing

1. Verify JQL query syntax
2. Check API token permissions
3. Test query in JIRA web UI first

## Related Documentation

- [Beads Task Tracking Reference](../reference/beads.md)
- [Beads Integration Guide](../development/beads-integration.md)
- [Context Sync ADR](../adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)

## Source Files

| Component | Path |
|-----------|------|
| Context Sync Service | `host-services/sync/context-sync/sync_all.py` |
| Confluence Connector | `host-services/sync/context-sync/connectors/confluence/` |
| JIRA Connector | `host-services/sync/context-sync/connectors/jira/` |
| Beads Rules | `jib-container/.claude/rules/beads-usage.md` |
| JIRA Processor | `jib-container/jib-tasks/jira/jira-processor.py` |
| Sprint Analyzer | `jib-container/jib-tasks/jira/analyze-sprint.py` |

---

*Auto-generated by Feature Analyzer*
