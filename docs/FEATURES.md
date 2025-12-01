# Features - Source Mapping

This document maps high-level features to their implementation locations in the codebase. It serves as a navigation aid for understanding what capabilities exist and where they're implemented.

## Status Flags

Features are tagged with status flags matching ADR lifecycle:

- **[not-implemented]** - Planned but not yet built (ADR in `docs/adr/not-implemented/`)
- **[in-progress]** - Currently being developed (ADR in `docs/adr/in-progress/`)
- **[implemented]** - Fully implemented and merged (ADR in `docs/adr/implemented/`)

## Features by Category

### Analysis & Documentation

#### LLM Documentation Index **[implemented]**
- **Description**: Structured documentation index following llms.txt standard for efficient LLM navigation
- **ADR**: [ADR-LLM-Documentation-Index-Strategy](adr/implemented/ADR-LLM-Documentation-Index-Strategy.md)
- **Implementation**:
  - `docs/index.md` - Main documentation index
  - `host-services/analysis/index-generator/` - Index generation service
  - `host-services/analysis/doc-generator/` - Documentation generator
- **Tests**: `tests/analysis/test_index_generator.py`

#### ADR Researcher **[implemented]**
- **Description**: Automated research tool for gathering context when writing ADRs
- **ADR**: [ADR-LLM-Documentation-Index-Strategy](adr/implemented/ADR-LLM-Documentation-Index-Strategy.md)
- **Implementation**:
  - `host-services/analysis/adr-researcher/` - Research service
- **Tests**: `tests/analysis/test_adr_researcher.py`

#### PR Analyzer **[implemented]**
- **Description**: Analyzes pull requests to generate summaries and documentation
- **Implementation**:
  - `host-services/analysis/analyze-pr/` - PR analysis service
- **Tests**: `tests/analysis/test_analyze_pr.py`

#### Feature Analyzer **[implemented]**
- **Description**: Automated feature detection and documentation sync workflow
- **ADR**: [ADR-Feature-Analyzer-Documentation-Sync](adr/in-progress/ADR-Feature-Analyzer-Documentation-Sync.md)
- **Current Status**:
  - ✅ Phase 1: Manual CLI tool (`feature-analyzer sync-docs`)
  - ✅ Phase 2: Automated ADR detection via systemd timer (15min interval)
  - ✅ Phase 3: Multi-doc updates, LLM content generation, PR creation
  - ✅ Phase 4: Full validation suite (6 checks), HTML metadata injection, git tagging, rollback tooling
  - ✅ Phase 5: Weekly code analysis for FEATURES.md updates
- **Implementation**:
  - `host-services/analysis/feature-analyzer/feature-analyzer.py` - Main CLI tool
  - `host-services/analysis/feature-analyzer/adr_watcher.py` - Automated watcher
  - `host-services/analysis/feature-analyzer/doc_generator.py` - LLM-powered doc generation
  - `host-services/analysis/feature-analyzer/pr_creator.py` - Automated PR creation
  - `host-services/analysis/feature-analyzer/rollback.py` - Rollback utilities (Phase 4)
  - `host-services/analysis/feature-analyzer/weekly_analyzer.py` - Weekly code analysis (Phase 5)
  - `host-services/analysis/feature-analyzer/feature-analyzer-watcher.service` - Systemd service (ADR watcher)
  - `host-services/analysis/feature-analyzer/feature-analyzer-watcher.timer` - 15-min timer (ADR watcher)
  - `host-services/analysis/feature-analyzer/feature-analyzer-weekly.service` - Systemd service (Weekly analysis)
  - `host-services/analysis/feature-analyzer/feature-analyzer-weekly.timer` - Weekly timer (Mondays 11am)
  - `~/.local/share/feature-analyzer/state.json` - State persistence

### Context Sync

#### Confluence/JIRA Sync **[implemented]**
- **Description**: Synchronizes Confluence and JIRA content to local filesystem for LLM access
- **ADR**: [ADR-Context-Sync-Strategy-Custom-vs-MCP](adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)
- **Implementation**:
  - `host-services/sync/context-sync/` - Main sync service
  - `~/context-sync/confluence/` - Synced Confluence content (read-only in container)
  - `~/context-sync/jira/` - Synced JIRA tickets (read-only in container)
- **Tests**: `tests/sync/test_context_sync.py`

### Slack Integration

#### Slack Notifier **[implemented]**
- **Description**: Sends notifications from container to Slack DM via file-based queue
- **ADR**: [ADR-Slack-Integration-Strategy-MCP-vs-Custom](adr/not-implemented/ADR-Slack-Integration-Strategy-MCP-vs-Custom.md)
- **Implementation**:
  - `host-services/slack/slack-notifier/` - Notification sender service
  - `jib-container/shared/notifications.py` - Python library for container use
  - `~/sharing/notifications/` - Notification queue directory
- **Tests**: `tests/slack/test_slack_notifier.py`

#### Slack Receiver **[implemented]**
- **Description**: Receives Slack messages and delivers them to container as task files
- **ADR**: [ADR-Slack-Integration-Strategy-MCP-vs-Custom](adr/not-implemented/ADR-Slack-Integration-Strategy-MCP-vs-Custom.md)
- **Implementation**:
  - `host-services/slack/slack-receiver/` - Message receiver service
  - `~/sharing/incoming/` - Incoming task directory
- **Tests**: `tests/slack/test_slack_receiver.py`

### Task Tracking

#### Beads Task Tracker **[implemented]**
- **Description**: Persistent task tracking system across container restarts
- **Implementation**:
  - `jib-container/scripts/bd` - CLI tool
  - `~/beads/` - Task database directory
- **Reference**: `docs/reference/beads.md`

### Git & GitHub Integration

#### GitHub Token Refresher **[implemented]**
- **Description**: Manages GitHub App token lifecycle and authentication
- **Implementation**:
  - `host-services/utilities/github-token-refresher/` - Token refresh service
- **Tests**: `tests/utilities/test_github_token_refresher.py`

#### Worktree Watcher **[implemented]**
- **Description**: Monitors git worktrees and manages cleanup
- **Implementation**:
  - `host-services/utilities/worktree-watcher/` - Watcher service
- **Tests**: `tests/utilities/test_worktree_watcher.py`

#### GitHub MCP Server **[implemented]**
- **Description**: MCP server integration for GitHub API operations (PRs, issues, comments)
- **ADR**: Referenced in CLAUDE.md environment section
- **Implementation**:
  - Configured at container startup via `claude mcp add`
  - Uses GitHub Copilot API endpoint
  - Available MCP tools: create_pull_request, get_pull_request, add_issue_comment, etc.
- **Usage**: See `docs/environment.md`

### Container Infrastructure

#### JiB Container **[implemented]**
- **Description**: Sandboxed Docker environment for autonomous software engineering
- **Implementation**:
  - `jib-container/` - Container configuration and scripts
  - `jib-container/Dockerfile` - Container image
  - `jib-container/scripts/` - Container utilities
  - `jib-container/shared/` - Shared libraries
- **Reference**: `docs/setup/README.md`

#### Test Discovery **[implemented]**
- **Description**: Automatically discovers and runs test frameworks in any codebase
- **Implementation**:
  - `jib-container/scripts/discover-tests.py` - Test discovery tool
- **Reference**: `docs/testing.md`

### Utilities

#### Spec Enricher **[implemented]**
- **Description**: Enriches specification documents with additional context
- **Implementation**:
  - `host-services/analysis/spec-enricher/` - Enrichment service
- **Tests**: `tests/analysis/test_spec_enricher.py`

#### Trace Collector **[implemented]**
- **Description**: Collects and analyzes execution traces
- **Implementation**:
  - `host-services/analysis/trace-collector/` - Trace collection service
- **Tests**: `tests/analysis/test_trace_collector.py`

## Feature Lifecycle

When ADR status changes, corresponding feature entries should be updated:

1. **ADR Proposed** → Feature entry created with `[not-implemented]` status
2. **ADR Approved & Work Begins** → Status updated to `[in-progress]`
3. **Implementation Merged** → Status updated to `[implemented]`
4. **Feature Deprecated** → Status updated to `[deprecated]` with sunset date

## Updating This File

**Manual Updates:**
- Add new features when ADRs are proposed
- Update status when ADR directory changes
- Remove deprecated features after sunset

**Automated Updates (Phase 5 - Implemented):**
- Weekly code analysis detects new features every Monday and proposes updates
- Feature analyzer syncs statuses with ADR lifecycle
- All updates proposed via PR for human review
- Run manually with: `feature-analyzer weekly-analyze`

---

**Last Updated**: 2025-12-01
**Maintained By**: Feature Analyzer (Phase 5 implemented) + Manual updates
