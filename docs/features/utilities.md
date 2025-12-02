# Utility Features

Helper tools, maintenance scripts, and supporting services.

## Overview

JIB includes various utility tools for:
- **Search and Maintenance**: Documentation search, sync cleanup
- **Symlink Management**: Project linking for shared access
- **Rate Limiting**: API call protection
- **Security**: Token management and refresh

## Features

### Documentation Search Utility

**Purpose**: Full-text search across all synced documentation.

**Location**: `host-services/sync/context-sync/utils/search.py`

**Usage**:
```bash
# Basic search
python host-services/sync/context-sync/utils/search.py "search term"

# Filter by space
python host-services/sync/context-sync/utils/search.py "term" --space SPACE1

# Case-sensitive search
python host-services/sync/context-sync/utils/search.py "Term" --case-sensitive

# Show statistics
python host-services/sync/context-sync/utils/search.py --stats
```

**Features**:
- Context snippets around matches
- Relevance ranking
- Space filtering
- Match highlighting

### Sync Maintenance Tools

**Purpose**: Monitor sync status and clean up orphaned files.

**Location**: `host-services/sync/context-sync/utils/maintenance.py`

**Usage**:
```bash
# Check sync status
python maintenance.py status

# Find orphaned files (synced files no longer in source)
python maintenance.py orphans

# Cleanup orphans
python maintenance.py cleanup

# Statistics across spaces
python maintenance.py stats
```

**Output Example**:
```
Sync Status:
  Confluence: 245 pages, last sync: 2025-12-02 10:30
  JIRA: 42 tickets, last sync: 2025-12-02 10:35

Orphaned files: 3
  - confluence/OLD_SPACE/deleted_page.md
  - confluence/SPACE1/removed_section.md
  - jira/PROJ-OLD-123.md
```

### Symlink Management

**Purpose**: Create symlinks from other projects to synced documentation.

**Location**: `host-services/sync/context-sync/utils/`

**Scripts**:
```bash
# Create symlink in any project
python create_symlink.py ~/khan/webapp

# Link to Khan Academy projects specifically
python link_to_khan_projects.py
```

**Use Case**: Make synced Confluence/JIRA docs available in multiple workspaces.

### Rate Limiting Handler

**Purpose**: Automatic rate limit detection and retry for APIs.

**Location**: Built into connectors:
- `host-services/sync/context-sync/connectors/jira/sync.py`
- `host-services/sync/context-sync/connectors/confluence/sync.py`

**Behavior**:
- Detects 429 responses
- Respects `Retry-After` header
- Exponential backoff
- Configurable delays

**Configuration** (in connector):
```python
RATE_LIMIT_DELAY = 60  # seconds
MAX_RETRIES = 3
BACKOFF_MULTIPLIER = 2
```

### Codebase Index Query Tool

**Purpose**: Query generated codebase indexes.

**Location**: `host-services/analysis/index-generator/query-index.py`

**Usage**:
```bash
# Summary of codebase
python query-index.py summary

# List components
python query-index.py components

# Show patterns
python query-index.py patterns

# Dependencies
python query-index.py dependencies

# Structure overview
python query-index.py structure

# Search across indexes
python query-index.py search "pattern"
```

**Index Files**:
- `docs/generated/codebase.json`
- `docs/generated/patterns.json`
- `docs/generated/dependencies.json`

### GitHub Token Refresher Service

**Purpose**: Automatically refreshes GitHub App tokens before expiry.

**Location**: `host-services/utilities/github-token-refresher/`

**Schedule**: Every 45 minutes (tokens expire after 1 hour)

**Service Management**:
```bash
# Setup
./host-services/utilities/github-token-refresher/setup.sh

# Status
systemctl --user status github-token-refresher.service

# Manual refresh
python host-services/utilities/github-token-refresher/github-token-refresher.py
```

**Token Location**: `~/.jib-sharing/github-token`

**Credentials Required**:
- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `~/.jib-sharing/github-app-private-key.pem`

### Interactive Configuration Setup

**Purpose**: Wizard for configuring connector credentials.

**Location**: `host-services/sync/context-sync/utils/setup.py`

**Usage**:
```bash
python setup.py

# Prompts for:
# - Confluence URL, username, API token
# - JIRA URL, username, API token
# - Spaces to sync
# - JQL queries
```

**Output**: Creates/updates `~/.jib-sharing/.env` with proper permissions (600)

### Confluence Space Discovery

**Purpose**: List available Confluence spaces for configuration.

**Location**: `host-services/sync/context-sync/utils/list_spaces.py`

**Usage**:
```bash
python list_spaces.py

# Output:
# Available spaces:
#   SPACE1 - Engineering Documentation
#   SPACE2 - Product Requirements
#   ADR - Architecture Decision Records
```

### Master Setup System

**Purpose**: Comprehensive installation for all JIB components.

**Location**: `setup.sh`

**Usage**:
```bash
# Initial setup
./setup.sh

# Update existing installation
./setup.sh --update

# Force reinstall
./setup.sh --force
```

**Components Installed**:
- Python dependencies (via uv)
- Go tools (Beads)
- Docker image
- Systemd services
- Configuration validation

**Interactive Prompts**:
- GitHub App credentials
- Slack tokens
- Confluence/JIRA settings

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Utility Layer                             │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Search    │  │ Maintenance │  │   Symlink   │         │
│  │   Utility   │  │   Tools     │  │  Management │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Index Query │  │   Token     │  │   Config    │         │
│  │    Tool     │  │  Refresher  │  │   Setup     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                              │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            │ Supports
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Services                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Context  │ │  GitHub  │ │  Slack   │ │  Docs    │       │
│  │  Sync    │ │ Watcher  │ │ Services │ │ System   │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Search not finding results

1. Check sync status: `python maintenance.py status`
2. Verify space is synced
3. Try broader search terms

### Token refresh failing

1. Verify credentials in `.env`
2. Check private key exists and has correct permissions
3. Test manually: `python github-token-refresher.py`

### Symlinks broken after move

1. Delete old symlink
2. Re-run `create_symlink.py`
3. Verify paths are absolute

### Rate limiting despite handler

1. Check for concurrent processes
2. Increase `RATE_LIMIT_DELAY`
3. Verify API quotas haven't changed

### Setup wizard errors

1. Check network connectivity
2. Verify API credentials are valid
3. Run with `--verbose` for details

## Related Documentation

- [Setup Overview](../setup/README.md)
- [Context Sync ADR](../adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)
- [GitHub App Setup](../setup/github-app-setup.md)

## Source Files

| Component | Path |
|-----------|------|
| Doc Search | `host-services/sync/context-sync/utils/search.py` |
| Maintenance | `host-services/sync/context-sync/utils/maintenance.py` |
| Symlink Creator | `host-services/sync/context-sync/utils/create_symlink.py` |
| Index Query | `host-services/analysis/index-generator/query-index.py` |
| Token Refresher | `host-services/utilities/github-token-refresher/` |
| Config Setup | `host-services/sync/context-sync/utils/setup.py` |
| Space Discovery | `host-services/sync/context-sync/utils/list_spaces.py` |
| Master Setup | `setup.sh` |

---

*Auto-generated by Feature Analyzer*
