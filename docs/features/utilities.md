# Utility Features

Helper tools, maintenance scripts, and supporting services.

## Overview

Supporting tools and utilities:
- **Worktree Management**: Git worktree watcher for isolation
- **Test Discovery**: Finds test frameworks in codebases
- **Maintenance**: Various helper scripts

## Features

### Documentation Search Utility

**Purpose**: Provides local full-text search across all synced documentation with context and relevance ranking. Supports filtering by space, case-sensitive search, and statistics display.

**Location**: `host-services/sync/context-sync/utils/search.py`

### Sync Maintenance Tools

**Purpose**: Provides sync status monitoring showing statistics across spaces and pages, and cleanup utilities to find and remove orphaned files.

**Location**: `host-services/sync/context-sync/utils/maintenance.py`

### Symlink Management for Projects

**Purpose**: Tools to create and manage symlinks from other projects to synced documentation, making it available in multiple projects across your workspace.

**Location**:
- `host-services/sync/context-sync/utils/create_symlink.py`
- `host-services/sync/context-sync/utils/link_to_projects.py`

### Rate Limiting Handler

**Purpose**: Automatic rate limit detection and retry logic for both JIRA and Confluence APIs with Retry-After header respect and configurable delays.

**Location**:
- `host-services/sync/context-sync/connectors/jira/sync.py`
- `host-services/sync/context-sync/connectors/confluence/sync.py`

### Codebase Index Query Tool

**Purpose**: CLI tool for querying generated codebase indexes with subcommands for summaries, components, patterns, dependencies, structure, and search across all indexes.

**Location**: `host-services/analysis/index-generator/query-index.py`

### Worktree Watcher Service

**Purpose**: Automatically cleans up orphaned git worktrees and temporary branches from stopped/crashed jib containers every 15 minutes. Prevents accumulation, saves disk space, and safely deletes branches only when work is captured.

**Location**:
- `host-services/utilities/worktree-watcher/worktree-watcher.sh`
- `host-services/utilities/worktree-watcher/worktree-watcher.service`
- `host-services/utilities/worktree-watcher/worktree-watcher.timer`

### Test Discovery Tool

**Purpose**: Dynamically discovers test configurations and frameworks in any codebase. Supports Python (pytest/unittest), JavaScript (Jest/Mocha/Vitest/Playwright), Go, and Java (Gradle/Maven). Provides recommended test commands.

**Location**:
- `jib-container/scripts/discover-tests.py`
- `jib-container/jib-tools/discover-tests.py`

### GitHub Token Refresher Service

**Purpose**: Systemd daemon that automatically refreshes GitHub App installation tokens every 45 minutes before the 1-hour expiry. Writes tokens to a shared file accessible to containers for continuous GitHub authentication.

**Location**:
- `host-services/utilities/github-token-refresher/github-token-refresher.py`
- `host-services/utilities/github-token-refresher/github-token-refresher.service`
- `host-services/utilities/github-token-refresher/setup.sh`

### Master Setup System

**Purpose**: Comprehensive installation and configuration script for all james-in-a-box host components. Handles initial setup, updates, and force reinstalls with interactive prompts, dependency checking, service management, and configuration validation.

**Location**: `setup.sh`

**Components**:
- **Dependency Management** (`setup.sh`)
- **Systemd Service Management** (`setup.sh`)
- **Shared Directory Structure Setup** (`setup.sh`)
- **GitHub App Authentication Setup** (`setup.sh`)
- **Slack Integration Configuration** (`setup.sh`)
- **Docker Image Pre-Build** (`setup.sh`)

### Interactive Configuration Setup

**Purpose**: Interactive setup wizard for configuring connector credentials and settings with secure credential storage in environment files with proper permissions.

**Location**: `host-services/sync/context-sync/utils/setup.py`

### Claude Agent Rules System

**Purpose**: Core behavioral configuration defining the Claude agent's role, operating model, workflow patterns, decision frameworks, quality standards, and communication style for autonomous software engineering. --- This feature list is maintained by the Feature Analyzer tool. ```bash feature-analyzer full-repo --repo-root /path/to/repo feature-analyzer weekly-analyze --days 7 ```

**Location**:
- `jib-container/.claude/rules/mission.md`
- `jib-container/.claude/rules/environment.md`
- `jib-container/.claude/rules/beads-usage.md`
- `jib-container/.claude/rules/context-tracking.md`
- `jib-container/.claude/rules/coding-standards.md`

**Components**:
- **Agent Mission Rules** (`jib-container/.claude/rules/mission.md`)
- **Sandbox Environment Rules** (`jib-container/.claude/rules/environment.md`)
- **Coding Standards** (`jib-container/.claude/rules/coding-standards.md`)
- **PR Description Guidelines** (`jib-container/.claude/rules/pr-descriptions.md`)
- **Test Workflow Rules** (`jib-container/.claude/rules/test-workflow.md`)
- **Notification Guidelines** (`jib-container/.claude/rules/notification-template.md`)

## Source Files

| Component | Path |
|-----------|------|
| Documentation Search Utility | `host-services/sync/context-sync/utils/search.py` |
| Sync Maintenance Tools | `host-services/sync/context-sync/utils/maintenance.py` |
| Symlink Management for Projects | `host-services/sync/context-sync/utils/create_symlink.py` |
| Rate Limiting Handler | `host-services/sync/context-sync/connectors/jira/sync.py` |
| Codebase Index Query Tool | `host-services/analysis/index-generator/query-index.py` |
| Worktree Watcher Service | `host-services/utilities/worktree-watcher/worktree-watcher.sh` |
| Test Discovery Tool | `jib-container/scripts/discover-tests.py` |
| GitHub Token Refresher Service | `host-services/utilities/github-token-refresher/github-token-refresher.py` |
| Master Setup System | `setup.sh` |
| Interactive Configuration Setup | `host-services/sync/context-sync/utils/setup.py` |
| Claude Agent Rules System | `jib-container/.claude/rules/mission.md` |

---

*Auto-generated by Feature Analyzer*
