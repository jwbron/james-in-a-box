# Container Infrastructure Features

Core jib container management, development environment, and analysis tasks.

## Overview

JIB runs in a sandboxed Docker container with:
- **Container Management**: `jib` command for lifecycle control
- **Development Environment**: Pre-configured tools and services
- **Task Processing**: Specialized processors for various workloads
- **Custom Commands**: Slash commands for common operations

## Features

### JIB Container Management System

**Purpose**: Primary interface for managing the sandboxed development environment.

**Location**: `jib-container/jib`

**Commands**:
```bash
# Start container (interactive)
jib

# Execute task in container
jib --exec <processor> --task <type> --context <json>

# View logs
bin/view-logs
# Or
jib-logs -n 100

# Container status
docker ps | grep jib
```

**Key Capabilities**:
- Container lifecycle management
- Worktree isolation (temporary branches)
- Host-to-container task execution
- Log streaming and viewing

### Docker Development Environment Setup

**Purpose**: Installs Khan Academy development tools in container.

**Location**: `jib-container/docker-setup.py`

**Installed Tools**:
| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11 | Primary language |
| Node.js | 20.x | JavaScript runtime |
| Go | Latest | Backend services |
| Java | 11 | Gradle/Maven builds |
| PostgreSQL | Latest | Database |
| Redis | Latest | Caching |

**Platform Support**:
- Ubuntu
- Fedora (ARM64)

**Invoked**: Automatically during container build

### Analysis Task Processor

**Purpose**: Routes analysis tasks to appropriate handlers.

**Location**: `jib-container/jib-tasks/analysis/analysis-processor.py`

**Task Types**:
```bash
# LLM prompt execution
jib --exec analysis-processor.py --task llm_prompt --context '{"prompt": "..."}'

# Documentation generation
jib --exec analysis-processor.py --task generate_adr_docs --context '{"adr_path": "..."}'

# Feature extraction
jib --exec analysis-processor.py --task extract_features --context '{"files": [...]}'

# PR creation
jib --exec analysis-processor.py --task create_pr --context '{"title": "...", "body": "..."}'
```

**Handler Modes**:
- Stdout mode: Returns result to stdout
- File mode: Writes JSON to file (for complex outputs)

### Claude Custom Commands

**Purpose**: Slash commands for common agent operations.

**Location**: `jib-container/.claude/commands/`

**Available Commands**:

| Command | Description |
|---------|-------------|
| `@load-context <name>` | Load knowledge from previous sessions |
| `@save-context <name>` | Save current session knowledge |
| `@create-pr [audit] [draft]` | Generate PR with smart description |
| `@beads-status` | Show current task status |
| `@beads-sync` | Commit and sync Beads state |
| `@update-confluence-doc <path>` | Prepare Confluence updates |
| `@show-metrics` | Generate monitoring reports |

**Usage Examples**:
```
@load-context webapp-auth
@save-context webapp-auth
@create-pr audit
@beads-status
```

### Session End Hook

**Purpose**: Automatic cleanup when Claude session ends.

**Location**: `jib-container/.claude/hooks/session-end.sh`

**Actions**:
- Warns about in-progress tasks
- Shows open tasks summary
- Syncs Beads database

### Container Directory Communication

**Purpose**: Shared directories for host-container communication.

**Directories**:
```
~/.jib-sharing/
├── notifications/     # Agent → Human (Slack notifications)
├── incoming/          # Human → Agent (Slack messages, tasks)
├── responses/         # Task responses
├── context/           # @save-context / @load-context data
├── logs/              # Container logs
├── traces/            # LLM trace data
├── github-token       # GitHub App token (auto-refreshed)
└── .env               # Configuration
```

**Access from Container**:
```
~/sharing/              # Symlink to ~/.jib-sharing
~/sharing/tmp/          # Scratch space
~/sharing/notifications/
~/sharing/incoming/
...
```

### Claude Agent Rules System

**Purpose**: Behavioral configuration for the Claude agent.

**Location**: `jib-container/.claude/rules/`

**Rule Files**:
| File | Purpose |
|------|---------|
| `mission.md` | Role, workflow, decision framework |
| `environment.md` | Sandbox constraints, GitHub setup |
| `beads-usage.md` | Task tracking commands |
| `context-tracking.md` | Persistent memory patterns |
| `khan-academy.md` | Tech stack, code standards |
| `test-workflow.md` | Test discovery and execution |
| `pr-descriptions.md` | PR format guidelines |
| `notification-template.md` | Async notification rules |

**Loaded**: Automatically by Claude Code on session start

### Test Discovery Tool

**Purpose**: Discovers test configurations in any codebase.

**Location**: `jib-container/scripts/discover-tests.py`

**Usage**:
```bash
# Discover tests
~/khan/james-in-a-box/jib-container/scripts/discover-tests.py

# In specific project
discover-tests.py ~/khan/webapp

# Get JSON output
discover-tests.py --json
```

**Supported Frameworks**:
- Python: pytest, unittest
- JavaScript: Jest, Mocha, Vitest, Playwright
- Go: go test
- Java: Gradle, Maven

### Worktree Watcher Service

**Purpose**: Cleans up orphaned git worktrees.

**Location**: `host-services/utilities/worktree-watcher/`

**Schedule**: Every 15 minutes via systemd timer

**Actions**:
- Finds orphaned worktrees from crashed containers
- Deletes temporary branches safely
- Saves disk space

**Service Management**:
```bash
systemctl --user status worktree-watcher.timer
```

### JIB Logs Viewer

**Purpose**: View container logs conveniently.

**Location**: `host-services/utilities/jib-logs/jib-logs`

**Usage**:
```bash
# Recent logs
jib-logs

# Last N lines
jib-logs -n 100

# Follow mode
jib-logs -f

# Filter by pattern
jib-logs | grep ERROR
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Host Machine                              │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              ~/.jib-sharing/                           │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │ │
│  │  │ incoming │ │ outgoing │ │ context  │ │  logs    │ │ │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │ │
│  └───────────────────────────────────────────────────────┘ │
│                          │                                  │
│                          │ mount                            │
│                          ▼                                  │
│  ┌───────────────────────────────────────────────────────┐ │
│  │              Docker Container (jib)                    │ │
│  │  ┌─────────────────────────────────────────────────┐ │ │
│  │  │              Claude Code                         │ │ │
│  │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐  │ │ │
│  │  │  │   Rules    │ │  Commands  │ │   Hooks    │  │ │ │
│  │  │  └────────────┘ └────────────┘ └────────────┘  │ │ │
│  │  └─────────────────────────────────────────────────┘ │ │
│  │                                                       │ │
│  │  ┌─────────────────────────────────────────────────┐ │ │
│  │  │           Task Processors                        │ │ │
│  │  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │ │ │
│  │  │  │ GitHub │ │ Slack  │ │Analysis│ │  JIRA  │  │ │ │
│  │  │  └────────┘ └────────┘ └────────┘ └────────┘  │ │ │
│  │  └─────────────────────────────────────────────────┘ │ │
│  │                                                       │ │
│  │  ┌─────────────────────────────────────────────────┐ │ │
│  │  │           Services                               │ │ │
│  │  │  ┌────────────┐ ┌────────────┐                 │ │ │
│  │  │  │ PostgreSQL │ │   Redis    │                 │ │ │
│  │  │  └────────────┘ └────────────┘                 │ │ │
│  │  └─────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Container won't start

1. Check Docker: `docker info`
2. Verify image exists: `docker images | grep jib`
3. Rebuild: `jib --rebuild`

### Task execution hangs

1. Check container logs: `jib-logs -f`
2. Verify Claude Code is responsive
3. Check for timeout issues

### Commands not recognized

1. Verify `.claude/commands/` directory exists
2. Check command file syntax
3. Restart Claude session

### Worktrees accumulating

1. Check watcher: `systemctl --user status worktree-watcher.timer`
2. Manual cleanup: `git worktree prune`
3. List worktrees: `git worktree list`

### Services not starting in container

1. Check PostgreSQL: `service postgresql status`
2. Check Redis: `service redis-server status`
3. Restart manually: `service postgresql start`

## Related Documentation

- [ADR: Autonomous Software Engineer](../adr/in-progress/ADR-Autonomous-Software-Engineer.md)
- [Architecture Overview](../architecture/README.md)
- [Project Structure](../development/STRUCTURE.md)
- [Environment Rules](../reference/environment.md)

## Source Files

| Component | Path |
|-----------|------|
| JIB Command | `jib-container/jib` |
| Docker Setup | `jib-container/docker-setup.py` |
| Analysis Processor | `jib-container/jib-tasks/analysis/analysis-processor.py` |
| Custom Commands | `jib-container/.claude/commands/` |
| Agent Rules | `jib-container/.claude/rules/` |
| Session Hook | `jib-container/.claude/hooks/session-end.sh` |
| Test Discovery | `jib-container/scripts/discover-tests.py` |
| Worktree Watcher | `host-services/utilities/worktree-watcher/` |
| JIB Logs | `host-services/utilities/jib-logs/jib-logs` |
| JIB Exec | `host-services/shared/jib_exec.py` |

---

*Auto-generated by Feature Analyzer*
