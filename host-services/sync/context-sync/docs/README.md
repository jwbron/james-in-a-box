# Context-Sync: Multi-Connector Documentation Sync

A multi-connector tool to sync documentation and context from multiple sources (Confluence, GitHub, Slack, etc.) to your local development environment for optimal AI-assisted development with Cursor and other LLM tools.

**Current connectors:**
- ✅ Confluence (full support)
- ✅ JIRA (full support)
- 🚧 GitHub (planned)
- 🚧 Slack (planned)

## Features

### Core Features
- **Multi-connector architecture** - easily add new data sources (Confluence, GitHub, Slack, etc.)
- **Automated scheduling** - systemd timer for hourly syncing
- **Incremental sync** - only download changed content
- **Centralized output** - all connectors sync to `~/context-sync/<connector-name>/`
- **Environment-based configuration** - secure credential management
- **LLM-optimized** - structured for AI agents and Cursor integration

### Confluence Connector
- **View-formatted content** - stores content in readable HTML format for optimal readability
- **Hierarchical directory structure** - preserves Confluence page hierarchy
- **Space-based organization** - each Confluence space becomes a directory
- **Comments included** - all page comments with timestamps and authors
- **Automatic indexing** - creates README files with hierarchical navigation
- **Search documentation** locally with context and relevance ranking
- **Maintenance tools** - status monitoring and cleanup utilities
- **Symlink management** - automatically create symlinks in other projects

### JIRA Connector
- **Ticket syncing** - syncs your assigned tickets with all details
- **Comments included** - all comments with timestamps and authors
- **Markdown format** - converts Atlassian Document Format to clean markdown
- **Attachment metadata** - lists attachments (files not downloaded)
- **Work logs** - optional inclusion of work log entries
- **JQL customization** - filter tickets with custom JQL queries
- **Incremental sync** - only updates changed tickets

## Quick Start

### For Khan Academy Users (Recommended)

```bash
# One-time setup
make docs-bootstrap

# Enable automated hourly syncing
./manage_scheduler.sh enable
```

The bootstrap command will:
1. Set up your Confluence configuration (if needed)
2. Run a full sync of all documentation to `~/context-sync/confluence/`
3. Create symlinks in all Khan Academy projects
4. Make everything ready for Cursor to index

The scheduler will automatically sync every hour in the background.

### Manual Setup

#### 1. Setup Configuration

```bash
make docs-setup
```

This will prompt you for:
- Your Confluence instance URL
- Your username (email)
- Your API token
- Space keys to sync

#### 2. Test Connection

```bash
make docs-test
```

This verifies your configuration and tests access to your Confluence spaces.

#### 3. Sync Documentation

```bash
make docs-sync
```

This downloads all pages from your configured Confluence spaces (no page limit by default).

#### 4. Search Documentation

```bash
make docs-search QUERY="API documentation"
```

Search across all synced documentation with context.

## Available Commands

```bash
make docs-setup      # Interactive configuration setup
make docs-test       # Test Confluence connection
make docs-sync       # Sync documentation from Confluence (incremental)
make docs-sync-full  # Full sync (clean + sync all pages)
make docs-sync-limited # Sync with 100 page limit (for testing)
make docs-search QUERY="term" # Search synced documentation
make docs-search --stats # Show documentation statistics
make docs-list-spaces # List available spaces
make docs-status      # Show sync status and statistics
make docs-cleanup     # Find orphaned files (dry run)
make docs-cleanup-execute # Remove orphaned files
make docs-clean       # Clean all synced documentation
make docs-link PROJECT="/path" # Create symlink in another project
make docs-list-links  # List projects with symlinks
make docs-link-khan   # Create symlinks in all Khan Academy projects (dry run)
make docs-link-khan-execute # Create symlinks in all Khan Academy projects
make docs-list-khan-links # List Khan Academy projects with symlinks
make docs-setup-cursor   # Set up Cursor rules and guidance for confluence-docs
make help             # Show all available commands
```

## Configuration

### Environment Variables

The sync tool uses these environment variables. Configuration is stored in `~/.config/context-sync/.env` with secure permissions (600).

**Confluence Variables:**

| Variable | Description | Required |
|----------|-------------|----------|
| `CONFLUENCE_BASE_URL` | Your Confluence instance URL | Yes |
| `CONFLUENCE_USERNAME` | Your Confluence username (email) | Yes |
| `CONFLUENCE_API_TOKEN` | Your Confluence API token | Yes |
| `CONFLUENCE_SPACE_KEYS` | Comma-separated space keys | Yes |
| `CONFLUENCE_MAX_PAGES` | Maximum pages per space (default: unlimited) | No |
| `CONFLUENCE_INCLUDE_ATTACHMENTS` | Include attachments (default: false) | No |

**JIRA Variables:**

| Variable | Description | Required |
|----------|-------------|----------|
| `JIRA_BASE_URL` | Your JIRA instance URL | Yes |
| `JIRA_USERNAME` | Your JIRA username (email) | Yes |
| `JIRA_API_TOKEN` | Your JIRA API token | Yes |
| `JIRA_JQL_QUERY` | JQL query to filter tickets (default: your open tickets) | No |
| `JIRA_MAX_TICKETS` | Maximum tickets to sync (default: unlimited) | No |
| `JIRA_INCLUDE_COMMENTS` | Include ticket comments (default: true) | No |
| `JIRA_INCLUDE_ATTACHMENTS` | Include attachment metadata (default: true) | No |
| `JIRA_INCLUDE_WORKLOGS` | Include work logs (default: false) | No |

The configuration file is stored at: `~/.config/context-sync/.env`

You can also export them in your shell:

```bash
export CONFLUENCE_BASE_URL=https://yourcompany.atlassian.net
export CONFLUENCE_USERNAME=your.email@company.com
export CONFLUENCE_API_TOKEN=your_api_token
export CONFLUENCE_SPACE_KEYS=TEAM,DEV,ARCH
```

### Getting Your API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Give it a name like "Documentation Sync"
4. Copy the token and use it in your configuration

## Usage

### Advanced Search

You can also use the search script directly for more options:

```bash
# Search in specific space
python -m sync.search "query" --space SPACE_KEY

# Case sensitive search
python -m sync.search "Query" --case-sensitive

# Search without context
python -m sync.search "query" --no-context

# List available spaces
python -m sync.search --list-spaces
```

### Symlink Management

For Khan Academy projects, you can automatically create symlinks:

```bash
# Create symlinks in all Khan Academy projects
make docs-link-khan-execute

# List projects with symlinks
make docs-list-khan-links

# Create symlink in a specific project
make docs-link PROJECT="/path/to/project"
```

## Directory Structure

### Code Repository
```
confluence-cursor-sync/          # This codebase
├── README.md                    # This file
├── ARCHITECTURE.md              # System architecture
├── MIGRATION.md                 # Migration guide
├── requirements.txt             # Python dependencies
├── Makefile                     # Build and sync commands
├── sync_all.py                  # Main orchestrator (runs all connectors)
├── manage_scheduler.sh          # Systemd scheduler management
├── sync/                        # Connector implementations
│   ├── base_connector.py        # Base class for connectors
│   ├── confluence_connector.py  # Confluence connector
│   ├── confluence_sync.py       # Confluence sync logic
│   ├── config.py                # Configuration management
│   ├── search.py                # Search functionality
│   └── ...
├── context-sync.service         # Systemd service definition
└── context-sync.timer           # Hourly timer
```

### Output Directory
```
~/context-sync/                  # Synced content (separate from code)
├── confluence/                  # Confluence connector output
│   ├── SPACE1/
│   │   ├── README.md            # Index of all pages
│   │   └── Page_Title.html
│   ├── SPACE2/
│   └── .sync_state              # Incremental sync state
├── logs/                        # Sync logs
│   └── sync_20241121.log
└── (future connectors like github/, slack/, etc.)
```

After syncing, your documentation will be organized hierarchically based on Confluence page structure:

```
~/context-sync/confluence/
├── INFRA/
│   ├── README.md              # Index of INFRA section
│   ├── Jenkins/
│   │   ├── README.md          # Jenkins subsection index
│   │   ├── Jenkins Architecture.html
│   │   └── Jenkins Setup.html
│   ├── Deployment/
│   │   ├── README.md
│   │   └── Deployment Guide.html
│   └── Infrastructure Overview.html
├── DEV/
│   ├── README.md              # Index of DEV section
│   ├── API/
│   │   ├── README.md
│   │   ├── API Guidelines.html
│   │   └── Authentication.html
│   └── Development Standards.html
└── README.md                  # Main space index
```

**Note**: Content files have `.html` extensions and contain view-formatted HTML content optimized for both human readability and LLM processing. The view format preserves all visual formatting (tables, lists, headings, etc.) while being clean and readable. Directory indexes remain as `.md` files for better navigation.

## Integration with Cursor & LLM Indexing

Once synced, your documentation is optimized for AI assistance:

1. **Search documentation**: Use `make docs-search` for quick searches with context
2. **Human-readable content**: Files contain view-formatted HTML content that's both readable and LLM-friendly
3. **Hierarchical organization**: Directory structure mirrors Confluence page hierarchy for better AI understanding
4. **AI guidance**: Cursor automatically references your internal documentation with optimal readability
5. **Create symlinks**: Make documentation available in other projects with `make docs-link-khan-execute`

The confluence-docs directories are:
- **Human and LLM optimized** with view-formatted content for maximum readability and context
- **Hierarchically structured** for better AI understanding of document relationships
- **Indexed** for AI reference and decision making
- **Guided** by Cursor rules that prioritize internal company documentation

### Cursor Rules

The tool automatically sets up Cursor rules to:
- **Guide AI behavior** when working with confluence-docs directories
- **Prioritize internal company documentation** for decision making and best practices
- **Reference specific documentation** when making architectural or technology recommendations
- **Follow established patterns** and guidelines from your internal documentation

You can manually set up Cursor rules with:
```bash
make docs-setup-cursor
```

The rule provides guidance for:
- Architectural decisions
- Technology choices  
- Coding standards and conventions
- Deployment procedures
- Operational practices
- Company-specific patterns and guidelines

## Multi-Connector Architecture

This project now supports multiple connectors for syncing content from different sources. See `ARCHITECTURE.md` for full details on:
- Adding new connectors
- Connector interface
- Configuration management
- Performance considerations

### Current Connectors
- **Confluence**: Fully implemented (see above)
- **JIRA**: Fully implemented (see above)

### Planned Connectors
- **GitHub**: Sync README files, wikis, discussions
- **Slack**: Sync important channel discussions, pinned messages
- **Google Docs**: Sync technical documentation
- **Notion**: Sync team wiki pages

### Running All Connectors

```bash
# Run all configured connectors
./sync_all.py

# Run with full (non-incremental) sync
./sync_all.py --full
```

## Migrating from Old Version

If you're upgrading from the single-purpose Confluence sync, see `MIGRATION.md` for:
- What changed
- Step-by-step migration instructions
- Backwards compatibility information
- Rollback procedures

## Copying to Another Project

This entire directory is self-contained and can be copied to any other project. Simply:

1. Copy this directory to your new project
2. Run `make docs-setup` to configure your Confluence connection
3. Start syncing and searching documentation
4. Optionally enable the scheduler with `./manage_scheduler.sh enable`

## Troubleshooting

### Common Issues

**"Missing required environment variables"**
- Run `make docs-setup` to configure your settings
- Or set the environment variables manually

**"Connection failed"**
- Verify your Confluence URL is correct
- Check your username and API token
- Ensure you have access to the specified spaces

**"No spaces found"**
- Run `make docs-sync` first to download documentation
- Check that your space keys are correct

**"Failed to get page"**
- Some pages may be restricted or deleted
- The sync will continue with other pages

### Getting Help

1. Check the configuration with `make docs-test`
2. Verify your API token has the correct permissions
3. Ensure you have access to the Confluence spaces you're trying to sync

## Security Notes

- API tokens are stored in environment variables or `.env` files
- Never commit `.env` files to version control
- The `.env` file is already in `.gitignore`
- Consider using your system's keychain for production use

## Customization

### Adding More Spaces

Edit your `.env` file and add more space keys:

```bash
CONFLUENCE_SPACE_KEYS=TEAM,DEV,ARCH,PRODUCT,SUPPORT
```

### Customizing Output

You can modify the sync script to:
- Add custom metadata to files
- Filter pages by content or hierarchy
- Customize directory organization
- Include attachments

### Scheduling Syncs

This project includes systemd integration for automated syncing with configurable frequency:

```bash
# Enable hourly syncing (default)
./manage_scheduler.sh enable

# Enable with custom frequency
./manage_scheduler.sh enable 15min   # Every 15 minutes
./manage_scheduler.sh enable 30min   # Every 30 minutes
./manage_scheduler.sh enable hourly  # Every hour (default)
./manage_scheduler.sh enable daily   # Daily at midnight

# Change frequency of existing timer
./manage_scheduler.sh set-frequency 30min

# Check scheduler status
./manage_scheduler.sh status

# View sync logs
./manage_scheduler.sh logs

# Manually run a sync now
./manage_scheduler.sh start

# Disable automated syncing
./manage_scheduler.sh disable
```

**Frequency Options:**
- `15min` - Sync every 15 minutes (frequent updates)
- `30min` - Sync every 30 minutes
- `hourly` - Sync every hour (recommended default)
- `daily` - Sync once per day at midnight

See `docs/SCHEDULING.md` for more details on scheduler configuration. 