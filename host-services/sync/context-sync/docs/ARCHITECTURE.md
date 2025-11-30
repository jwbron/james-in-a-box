# Context-Sync Architecture

## Overview

Context-sync is a multi-connector architecture for syncing external documentation and context into local directories for use with AI coding assistants like Cursor.

## Directory Structure

### Code Repository
```
confluence-cursor-sync/           # This codebase (connectors live here)
├── connectors/                  # All connectors organized here
│   ├── __init__.py
│   ├── base.py                  # BaseConnector class
│   └── confluence/              # Confluence connector
│       ├── __init__.py
│       ├── connector.py         # ConfluenceConnector
│       ├── sync.py              # Main sync logic
│       └── config.py            # ConfluenceConfig
├── utils/                       # Shared utilities
│   ├── __init__.py
│   ├── search.py                # Search functionality
│   ├── setup.py                 # Interactive setup
│   ├── maintenance.py           # Maintenance utilities
│   └── (other utils)
├── docs/                        # Documentation
│   ├── README.md
│   ├── ARCHITECTURE.md
│   ├── MIGRATION.md
│   └── (other docs)
├── systemd/                     # Systemd service files
│   ├── context-sync.service
│   ├── context-sync.timer
│   └── README.md
├── sync_all.py                  # Main orchestrator script
├── manage_scheduler.sh          # Systemd scheduler management
├── Makefile                     # Build commands
└── requirements.txt             # Dependencies

~/context-sync/                  # Output directory (synced content)
├── confluence/                  # Confluence connector output
│   ├── SPACE1/
│   ├── SPACE2/
│   └── .sync_state
├── logs/                        # Sync logs
│   └── sync_YYYYMMDD.log
└── (future connectors like github/, slack/, etc.)
```

## Architecture Principles

### 1. Connector-Based Design

Each connector is a self-contained module that:
- Inherits from `BaseConnector`
- Manages its own configuration validation
- Handles its own sync logic
- Outputs to its own subdirectory in `~/context-sync/`
- Maintains its own sync state for incremental updates

### 2. Separation of Code and Data

- **Code location**: `/home/jwies/workspace/confluence-cursor-sync/`
  - All connector implementations
  - Configuration management
  - Orchestration scripts
  
- **Data location**: `~/context-sync/<connector-name>/`
  - Synced content from each connector
  - Sync state files
  - Output logs

### 3. Incremental Sync

Connectors maintain sync state to avoid re-downloading unchanged content:
- State stored in `.sync_state` file in each connector's output directory
- Uses content hashes to detect changes
- Falls back to full sync if state is corrupted

### 4. Scheduled Execution

- Uses systemd user timers for reliable scheduling
- Runs hourly by default (configurable)
- Logs to systemd journal and file logs
- Low priority (nice=10) to avoid impacting development work

## Connector Interface

All connectors must implement the `BaseConnector` interface:

```python
class BaseConnector(ABC):
    def validate_config(self) -> bool:
        """Validate connector configuration."""
        
    def sync(self, incremental: bool = True) -> bool:
        """Run the sync operation."""
        
    def get_sync_metadata(self) -> Dict:
        """Get metadata about the last sync."""
        
    def cleanup(self, dry_run: bool = True) -> Dict:
        """Clean up old or orphaned files."""
```

## Adding New Connectors

To add a new connector (e.g., GitHub, Slack, JIRA):

1. **Create connector directory**:
   ```bash
   mkdir -p connectors/github
   touch connectors/github/__init__.py
   ```

2. **Create connector class** in `connectors/github/connector.py`:
   ```python
   from connectors.base import BaseConnector
   from pathlib import Path
   
   class GitHubConnector(BaseConnector):
       def __init__(self, output_dir: Path = None):
           if output_dir is None:
               output_dir = Path.home() / "context-sync" / "github"
           super().__init__("github", output_dir)
       
       def validate_config(self) -> bool:
           # Check for required env vars, API tokens, etc.
           pass
       
       def sync(self, incremental: bool = True) -> bool:
           # Implement sync logic
           pass
   ```

3. **Create config** in `connectors/github/config.py`:
   ```python
   import os
   
   class GitHubConfig:
       TOKEN = os.getenv("GITHUB_TOKEN", "")
       REPOS = os.getenv("GITHUB_REPOS", "")
       # ...
   ```

4. **Add to orchestrator** in `sync_all.py`:
   ```python
   from connectors.github.connector import GitHubConnector
   
   def get_all_connectors():
       connectors = []
       
       # ... existing connectors ...
       
       try:
           connector = GitHubConnector()
           if connector.validate_config():
               connectors.append(connector)
       except Exception as e:
           logger.error(f"Failed to initialize GitHub connector: {e}")
       
       return connectors
   ```

3. **Add configuration** (usually via environment variables):
   ```bash
   export GITHUB_TOKEN=your_token
   export GITHUB_REPOS=org/repo1,org/repo2
   ```

4. **Test the connector**:
   ```bash
   python -m sync.github_connector  # If implementing standalone main()
   # or
   ./sync_all.py  # Run all connectors
   ```

## Configuration Management

### Environment Variables

Connectors use environment variables for configuration:
- Load from `.env` file in the repository root
- Can be overridden via shell environment
- Each connector has its own namespace (e.g., `CONFLUENCE_*`, `GITHUB_*`)

### Output Directory

Each connector outputs to:
```
~/context-sync/<connector-name>/
```

This can be overridden per-connector via environment variables or constructor arguments.

## Logging

### Systemd Journal

When run via systemd timer:
```bash
journalctl --user -u context-sync.service
```

### File Logs

Detailed logs in:
```
~/context-sync/logs/sync_YYYYMMDD.log
```

## Sync State Management

Each connector maintains state in:
```
~/context-sync/<connector-name>/.sync_state
```

This is a pickled Python dictionary containing:
- Content hashes for change detection
- Last sync timestamps
- Connector-specific metadata

To force a full re-sync, delete this file:
```bash
rm ~/context-sync/confluence/.sync_state
```

## Error Handling

The orchestrator continues running even if individual connectors fail:
- Each connector's sync operation is wrapped in try/except
- Failures are logged but don't abort the entire sync
- Exit code reflects overall success/failure count

## Performance Considerations

- **Nice level**: Runs at low priority (nice=10) to avoid impacting dev work
- **IO scheduling**: Uses best-effort IO scheduling (class 2, priority 7)
- **Rate limiting**: Connectors implement delays to avoid API rate limits
- **Incremental sync**: Only fetches changed content to minimize network usage

## Future Enhancements

Potential connector additions:
- **GitHub**: Sync README files, wiki pages, discussion threads
- **Slack**: Sync important channel discussions, pinned messages
- **JIRA**: Sync epic descriptions, stories, technical specs
- **Google Docs**: Sync technical documentation
- **Notion**: Sync team wiki pages
- **Linear**: Sync project briefs and technical specs

