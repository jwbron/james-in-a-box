# Container Infrastructure Features

Core jib container management and development environment.

## Overview

The jib container provides a sandboxed development environment:
- **Container Management**: Build, run, exec operations
- **Custom Commands**: Slash commands for common operations

## Features

### Claude Custom Commands

**Purpose**: Slash command system for common agent operations including context management, PR creation, task status, and metrics display.

**Location**: `jib-container/.claude/commands/README.md`

**Components**:
- **Load Context Command** (`jib-container/.claude/commands/load-context.md`)
- **Save Context Command** (`jib-container/.claude/commands/save-context.md`)
- **Create PR Command** (`jib-container/.claude/commands/create-pr.md`)
- **Beads Status Command** (`jib-container/.claude/commands/beads-status.md`)
- **Beads Sync Command** (`jib-container/.claude/commands/beads-sync.md`)
- **Update Confluence Doc Command** (`jib-container/.claude/commands/update-confluence-doc.md`)
- **Show Metrics Command** (`jib-container/.claude/commands/show-metrics.md`)

### JIB Container Management System

**Purpose**: The core 'jib' command provides the primary interface for starting, managing, and interacting with the sandboxed Docker development environment. Includes container lifecycle management and log viewing.

**Location**:
- `bin/jib`
- `host-services/shared/jib_exec.py`
- `host-services/shared/__init__.py`

**Components**:
- **JIB Execution Wrapper** (`host-services/shared/jib_exec.py`)

### Docker Development Environment Setup

**Purpose**: Automates complete installation of development tools in the Docker container, including Python 3.11, Node.js 20.x, Go, Java 11, PostgreSQL, Redis, and various development utilities with cross-platform support for Ubuntu and Fedora.

**Location**: `bin/docker-setup.py`

### Container Directory Communication System

**Purpose**: Shared directory structure enabling communication between container and host including notifications (agent -> human), incoming (human -> agent), responses, and context directories.

**Location**: `jib-container/README.md`

## Related Documentation

- [Environment Reference](../../jib-container/.claude/rules/environment.md)
- [Mission Guide](../../jib-container/.claude/rules/mission.md)

## Source Files

| Component | Path |
|-----------|------|
| Claude Custom Commands | `jib-container/.claude/commands/README.md` |
| JIB Container Management System | `bin/jib` |
| Docker Development Environment Setup | `bin/docker-setup.py` |
| Container Directory Communication System | `jib-container/README.md` |
