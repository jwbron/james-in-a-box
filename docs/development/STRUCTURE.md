# Project Structure Guidelines

This document describes the directory structure conventions for james-in-a-box.

## Top-Level Structure

```
james-in-a-box/
├── bin/                    # CLI symlinks (points to actual implementations)
├── config/                 # Central configuration (repos, filters)
├── docs/                   # Cross-cutting documentation
├── host-services/          # Host-side systemd services
├── jib-container/          # Container-side code and config
├── setup.sh                # Master setup script
└── README.md               # Main documentation
```

## Directory Naming Conventions

| Directory | Purpose | Runs On |
|-----------|---------|---------|
| `host-services/slack/` | Slack communication services | Host |
| `host-services/sync/` | Data synchronization services | Host |
| `host-services/analysis/` | Code/conversation analysis and PR tools | Host |
| `host-services/utilities/` | Utility services (cleanup) | Host |
| `jib-container/jib-tasks/` | Scripts called via `jib --exec` from host services | Container (via jib --exec) |
| `jib-container/jib-tools/` | Interactive tools used inside the container | Container |
| `jib-container/.claude/` | Claude Code configuration (rules, commands) | Container |

## Host Service Structure

Services in `host-services/` are organized by category:

```
host-services/
├── slack/                     # Slack communication
│   ├── slack-notifier/        # Outgoing notifications
│   └── slack-receiver/        # Incoming messages
├── sync/                      # Data synchronization
│   ├── github-sync/           # GitHub PR sync
│   └── context-sync/          # Confluence/JIRA sync
├── analysis/                  # Analysis services and tools
│   ├── codebase-analyzer/     # Code review automation
│   ├── conversation-analyzer/ # Quality analysis
│   └── analyze-pr/            # PR analysis CLI tool
└── utilities/                 # Utility services
    └── worktree-watcher/      # Git worktree cleanup
```

Each service directory should contain:

```
<service-name>/
├── README.md              # Required: Purpose, setup, usage
├── setup.sh               # Required: Installation script (for systemd services)
├── <service-name>.py      # Main implementation (if Python)
├── <service-name>.sh      # Main implementation (if shell)
├── <service-name>.service # Systemd service unit (if daemon)
├── <service-name>.timer   # Systemd timer (if timer-based)
└── requirements.txt       # Python dependencies (even if empty)
```

### When to Use Subdirectories

Most services should be **flat** (all files at root level). Use subdirectories only when:

1. **Multiple subsystems**: Service has 2+ distinct functional areas (e.g., Confluence connector + JIRA connector)
2. **10+ files**: Service complexity warrants organization
3. **Shared utilities**: Multiple scripts share common code

Example of justified subdirectory usage (`context-sync/`):
```
context-sync/
├── connectors/         # Pluggable data source connectors
│   ├── confluence/     # Confluence-specific code
│   └── jira/           # JIRA-specific code
├── docs/               # Extended documentation (8+ files)
├── utils/              # Shared utilities
├── README.md
├── setup.sh
├── requirements.txt
├── context-sync.service
└── context-sync.timer
```

## Container Task Structure

Tasks in `jib-container/jib-tasks/` are organized by product/service:

```
jib-container/jib-tasks/
├── github/                    # GitHub-related tasks
│   ├── README.md
│   ├── github-processor.py    # Analyzes CI failures
│   ├── pr-reviewer.py         # Auto-reviews PRs
│   ├── comment-responder.py   # Responds to PR comments
│   └── pr-analyzer.py         # Analyzes PR context
├── jira/                      # JIRA-related tasks
│   ├── README.md
│   ├── jira-processor.py      # Analyzes JIRA tickets
│   └── analyze-sprint.py      # Sprint analysis
├── confluence/                # Confluence-related tasks
│   ├── README.md
│   └── confluence-processor.py # Analyzes docs
└── slack/                     # Slack-related tasks
    ├── README.md
    └── incoming-processor.py  # Processes incoming messages
```

These are called via `jib --exec` from host-side systemd services (no background processes).

## File Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Python scripts | kebab-case | `codebase-analyzer.py` |
| Shell scripts | kebab-case | `setup.sh`, `manage-scheduler.sh` |
| Systemd files | `<service-name>.service`, `<service-name>.timer` | `slack-notifier.service` |
| Config files | `.yaml` (not `.yml`) | `repositories.yaml` |
| Documentation | UPPERCASE.md for guides, lowercase.md for READMEs | `SCHEDULING.md`, `README.md` |

## Symlink Strategy

The `bin/` directory contains symlinks for convenient CLI access:

```
bin/
├── jib -> ../jib-container/jib
├── analyze-pr -> ../host-services/analysis/analyze-pr/analyze-pr
├── setup-slack-notifier -> ../host-services/slack/slack-notifier/setup.sh
└── ...
```

**Benefits**:
- Single location for common commands
- Actual code stays with its service
- Easy discovery of available tools

## Configuration Organization

```
config/                        # Global configuration
├── repositories.yaml          # GitHub repo permissions (source of truth)
├── context-filters.yaml       # Content filtering rules
└── repo_config.py             # Python API for repo access

host-services/<service>/       # Service-specific config
└── requirements.txt           # Python dependencies

~/.config/jib-notifier/        # Runtime user config (not in repo)
└── config.json                # Slack tokens, user preferences
```

## Documentation Organization

```
docs/
├── README.md                  # Documentation index
├── adr/                       # Architecture Decision Records
├── architecture/              # System design docs
├── development/               # Developer guides (like this file)
├── reference/                 # Quick reference guides
├── setup/                     # Setup instructions
└── user-guide/                # End-user documentation

host-services/<service>/       # Component-specific docs
└── README.md                  # Service documentation

host-services/<service>/docs/  # Extended docs (only if needed)
└── TOPIC.md                   # Detailed topic guides
```

**Rule**: Documentation should live close to code. Only cross-cutting docs belong in the central `docs/` directory.

## Adding a New Host Service

1. Create directory: `host-services/<service-name>/`
2. Add required files:
   - `README.md` - Document purpose and usage
   - `setup.sh` - Installation script
   - `<service-name>.service` - Systemd unit
   - `requirements.txt` - Dependencies (even if empty)
3. Add symlink to `bin/` if user-facing
4. Update main `README.md` architecture section
5. Add to `setup.sh` components array

## Adding a New Container Task

1. Identify the product/service category (github, jira, confluence, slack, or new)
2. Add script to appropriate directory: `jib-container/jib-tasks/<product>/`
3. Add required files:
   - `README.md` - Document purpose and usage (one per product directory)
   - Main implementation (`.py`)
4. Update the host-side systemd service to call via `jib --exec`
5. Update main `README.md` container components section

## Adding a New Container Tool

1. Add script to `jib-container/jib-tools/`
2. Document in the directory's `README.md`
3. Tools are interactive utilities used inside the container (not called via jib --exec)
