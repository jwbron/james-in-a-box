# GitHub Integration Features

Automated PR monitoring, code reviews, and CI/CD failure handling.

## Overview

JIB monitors GitHub repositories for events and responds autonomously:
- **PR Monitoring**: Detects check failures, comments, merge conflicts
- **Auto-Review**: Reviews PRs from other developers
- **Comment Response**: Responds to comments on your PRs
- **CI/CD Fixes**: Automatically fixes failing tests and builds

## Features

### GitHub Watcher Service

**Purpose**: Host-side systemd timer service that monitors GitHub repositories every 5 minutes for PR events including check failures, new comments, merge conflicts, and review requests. Automatically triggers jib container analysis via jib --exec when events are detected.

**Location**:
- `host-services/analysis/github-watcher/github-watcher.py`
- `host-services/analysis/github-watcher/setup.sh`
- `host-services/analysis/github-watcher/README.md`
- `host-services/analysis/github-watcher/github-watcher.service`
- `host-services/analysis/github-watcher/github-watcher.timer`

**Components**:
- **PR Check Failure Detection** (`host-services/analysis/github-watcher/github-watcher.py`)
- **PR Comment Monitoring** (`host-services/analysis/github-watcher/github-watcher.py`)
- **Merge Conflict Detection** (`host-services/analysis/github-watcher/github-watcher.py`)
- **PR Review Request Handling** (`host-services/analysis/github-watcher/github-watcher.py`)
- **Failed Task Retry System** (`host-services/analysis/github-watcher/github-watcher.py`)
- **Parallel Task Execution** (`host-services/analysis/github-watcher/github-watcher.py`)
- **GitHub API Rate Limiting** (`host-services/analysis/github-watcher/github-watcher.py`)
- **Persistent State Tracking** (`host-services/analysis/github-watcher/github-watcher.py`)

### GitHub CI/CD Failure Processor

**Purpose**: Container-side processor that automatically analyzes CI/CD check failures on PRs. Detects test failures, linting errors, and build failures, creates Beads tasks, and can auto-fix certain issues. Triggered by GitHub Watcher.

**Location**:
- `jib-container/jib-tasks/github/github-processor.py`
- `jib-container/jib-tasks/github/README.md`

**Components**:
- **Merge Conflict Resolution Handler** (`jib-container/jib-tasks/github/github-processor.py`)

### PR Auto-Review System

**Purpose**: Automatically reviews new PRs from others, analyzing diffs for code quality, security concerns (eval/exec, SQL injection, XSS), performance issues, and best practices. Generates comprehensive file-by-file reviews.

**Location**:
- `jib-container/jib-tasks/github/pr-reviewer.py`
- `jib-container/jib-tasks/github/README.md`

### PR Comment Auto-Responder

**Purpose**: Monitors comments on your own PRs and uses Claude to generate contextual responses. Handles questions, change requests, concerns, and positive feedback. Can make code changes for writable repos.

**Location**:
- `jib-container/jib-tasks/github/comment-responder.py`
- `jib-container/jib-tasks/github/README.md`

### PR Analyzer Tool

**Purpose**: Analyzes GitHub Pull Requests by fetching comprehensive context (metadata, diff, comments, reviews, CI status, failed check logs) and uses Claude to analyze issues and suggest solutions. Supports analysis-only, fix mode, interactive sessions, and context-only modes.

**Location**:
- `host-services/analysis/analyze-pr/analyze-pr.py`
- `host-services/analysis/analyze-pr/README.md`
- `jib-container/jib-tasks/github/pr-analyzer.py`

### GitHub Command Handler

**Purpose**: Processes user commands received via Slack for GitHub operations like 'review PR 123' or '/pr review 123 webapp'. Parses commands and delegates to appropriate handlers.

**Location**:
- `jib-container/jib-tasks/github/command-handler.py`
- `jib-container/jib-tasks/github/README.md`

### GitHub App Token Generator

**Purpose**: Generates short-lived (1 hour) GitHub App installation access tokens from stored credentials. Used by jib launcher to authenticate MCP server and git operations without SSH keys.

**Location**: `jib-container/jib-tools/github-app-token.py`

### MCP Token Watcher

**Purpose**: Daemon that monitors the shared GitHub token file and automatically reconfigures the GitHub MCP server when the token changes. Ensures MCP server always uses valid tokens.

**Location**: `jib-container/scripts/mcp-token-watcher.py`

## Related Documentation

- [GitHub App Setup](../setup/github-app-setup.md)
- [PR Context Manager](workflow-context.md)
- [GitHub MCP Environment](../reference/environment.md)

## Source Files

| Component | Path |
|-----------|------|
| GitHub Watcher Service | `host-services/analysis/github-watcher/github-watcher.py` |
| GitHub CI/CD Failure Processor | `jib-container/jib-tasks/github/github-processor.py` |
| PR Auto-Review System | `jib-container/jib-tasks/github/pr-reviewer.py` |
| PR Comment Auto-Responder | `jib-container/jib-tasks/github/comment-responder.py` |
| PR Analyzer Tool | `host-services/analysis/analyze-pr/analyze-pr.py` |
| GitHub Command Handler | `jib-container/jib-tasks/github/command-handler.py` |
| GitHub App Token Generator | `jib-container/jib-tools/github-app-token.py` |
| MCP Token Watcher | `jib-container/scripts/mcp-token-watcher.py` |

---

*Auto-generated by Feature Analyzer*
