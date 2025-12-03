# Context Management Features

External knowledge synchronization and persistent task tracking.

## Overview

JIB maintains context through multiple systems:
- **External Sync**: Confluence docs and JIRA tickets synced locally
- **Task Tracking**: Beads system for persistent memory across restarts
- **PR Context**: Manages PR lifecycle state in Beads

## Features

### Context Sync Service

**Purpose**: Multi-connector tool that automatically syncs external knowledge sources (Confluence, JIRA) to ~/context-sync/ for AI agent access. Runs hourly via systemd timer, supports incremental sync, and provides search functionality.

**Location**:
- `host-services/sync/context-sync/sync_all.py`
- `host-services/sync/context-sync/manage_scheduler.sh`
- `host-services/sync/context-sync/context-sync.service`
- `host-services/sync/context-sync/setup.sh`

**Components**:
- **Base Connector Framework** (`host-services/sync/context-sync/connectors/base.py`)
- **Systemd Timer Scheduler** (`host-services/sync/context-sync/systemd/context-sync.service`)

### Confluence Connector

**Purpose**: Syncs Confluence documentation including ADRs, runbooks, and team docs to local markdown files. Preserves page hierarchy, includes comments, creates hierarchical navigation indexes, and supports incremental sync.

**Location**:
- `host-services/sync/context-sync/connectors/confluence/connector.py`
- `host-services/sync/context-sync/connectors/confluence/sync.py`
- `host-services/sync/context-sync/connectors/confluence/config.py`

**Components**:
- **Confluence Page Comments Sync** (`host-services/sync/context-sync/connectors/confluence/sync.py`)
- **Hierarchical Directory Index Generation** (`host-services/sync/context-sync/connectors/confluence/sync.py`)
- **Incremental Sync State Management** (`host-services/sync/context-sync/connectors/confluence/sync.py`)
- **Single Page Sync** (`host-services/sync/context-sync/connectors/confluence/sync.py`)
- **Confluence Space Discovery** (`host-services/sync/context-sync/utils/list_spaces.py`)
- **HTML to Markdown Converter** (`host-services/sync/context-sync/connectors/confluence/sync.py`)

### JIRA Connector

**Purpose**: Syncs JIRA tickets to local markdown files based on configurable JQL queries. Includes ticket comments, attachment metadata, work logs, and converts Atlassian Document Format to clean markdown with incremental sync support.

**Location**:
- `host-services/sync/context-sync/connectors/jira/connector.py`
- `host-services/sync/context-sync/connectors/jira/sync.py`
- `host-services/sync/context-sync/connectors/jira/config.py`

**Components**:
- **Atlassian Document Format Converter** (`host-services/sync/context-sync/connectors/jira/sync.py`)
- **JIRA Incremental Sync** (`host-services/sync/context-sync/connectors/jira/sync.py`)

### Beads Task Tracking System

**Purpose**: Persistent task tracking system that enables memory across container restarts. Provides commands for creating, updating, and completing tasks with status values, labeling conventions, and workflow patterns for ephemeral containers.

**Location**:
- `jib-container/.claude/rules/beads-usage.md`
- `jib-container/.claude/rules/context-tracking.md`

### JIRA Ticket Processor

**Purpose**: Monitors and analyzes JIRA tickets assigned to the user, using Claude to parse requirements, extract action items, assess scope, and send proactive Slack notifications. Creates Beads tasks for new tickets.

**Location**: `jib-container/jib-tasks/jira/jira-processor.py`

### Sprint Ticket Analyzer

**Purpose**: Analyzes tickets in the active sprint to provide actionable recommendations including next steps and suggestions for backlog tickets to pull in. Generates grouped Slack notifications.

**Location**: `jib-container/jib-tasks/jira/analyze-sprint.py`

### PR Context Manager

**Purpose**: Manages persistent PR context in Beads task tracking system, enabling memory across container restarts. Each PR gets a unique task tracking its lifecycle including comments, CI failures, and review feedback.

**Location**:
- `jib-container/jib-tasks/github/comment-responder.py`
- `jib-container/jib-tasks/github/pr-reviewer.py`
- `jib-container/jib-tasks/github/github-processor.py`

### Beads Task Memory Initialization

**Purpose**: Sets up the Beads persistent task tracking system in the shared directory for task creation, progress tracking, and cross-session context.

**Location**: `setup.sh`

## Related Documentation

- [Context Sync ADR](../adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)
- [Beads Reference](../reference/beads.md)

## Source Files

| Component | Path |
|-----------|------|
| Context Sync Service | `host-services/sync/context-sync/sync_all.py` |
| Confluence Connector | `host-services/sync/context-sync/connectors/confluence/connector.py` |
| JIRA Connector | `host-services/sync/context-sync/connectors/jira/connector.py` |
| Beads Task Tracking System | `jib-container/.claude/rules/beads-usage.md` |
| JIRA Ticket Processor | `jib-container/jib-tasks/jira/jira-processor.py` |
| Sprint Ticket Analyzer | `jib-container/jib-tasks/jira/analyze-sprint.py` |
| PR Context Manager | `jib-container/jib-tasks/github/comment-responder.py` |
| Beads Task Memory Initialization | `setup.sh` |

---

*Auto-generated by Feature Analyzer*
