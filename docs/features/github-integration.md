# GitHub Integration Features

Automated PR monitoring, code reviews, and CI/CD failure handling.

## Overview

JIB monitors GitHub repositories for events and responds autonomously:
- **PR Monitoring**: Detects check failures, comments, merge conflicts
- **Auto-Review**: Reviews PRs from other developers
- **Comment Response**: Responds to comments on your PRs
- **CI/CD Fixes**: Automatically fixes failing tests and builds

## Repository Access Levels

JIB supports two access levels for repositories:

### Writable Repos (Full Access)
Repositories where jib has write access via GitHub App:
- Creates PRs, pushes fixes, posts comments
- Automatically fixes CI/CD failures
- Responds to PR comments directly on GitHub
- Resolves merge conflicts

### Read-Only Repos (PAT Access)
Repositories where jib only has read access via Personal Access Token (PAT):
- Monitors PRs for events (failures, comments, conflicts)
- Sends Slack notifications with analysis and feedback
- Cannot push code, create PRs, or post comments
- Useful for external repos or repos without GitHub App integration

## Authentication

JIB supports **separate tokens** for writable and readable repositories, providing
security through the principle of least privilege.

### Token Configuration

Configure tokens in `~/.config/jib/secrets.env`:

```bash
# For writable repos: Use GitHub App (recommended) or PAT with write access
# GitHub App is auto-configured via setup - see docs/setup/github-app-setup.md
GITHUB_TOKEN="ghp_your_write_token_here"

# For read-only repos: Separate PAT with only read permissions (optional)
# Falls back to GITHUB_TOKEN if not set
GITHUB_READONLY_TOKEN="ghp_your_readonly_token_here"
```

### Why Separate Tokens?

1. **Principle of Least Privilege**: Read-only repos don't need write-capable tokens
2. **Different Organizations**: Your GitHub App may only be installed on your personal
   repos, while you want to monitor repos from other orgs
3. **Security Isolation**: If the read-only token is compromised, it can't modify repos

### Creating a Read-Only Token

1. Go to https://github.com/settings/tokens?type=beta
2. Click "Generate new token"
3. Set **Repository access** to "Only select repositories"
4. Select the repos you want to monitor
5. Grant these permissions (all read-only):
   - **Contents**: Read-only
   - **Pull requests**: Read-only
   - **Commit statuses**: Read-only

### Token Selection Logic

When accessing a repository, JIB automatically selects the appropriate token:

| Repo Type | Token Used |
|-----------|------------|
| Writable repo | `GITHUB_TOKEN` (or GitHub App token) |
| Readable repo | `GITHUB_READONLY_TOKEN` (falls back to `GITHUB_TOKEN`) |
| Unknown repo | `GITHUB_TOKEN` |

Configure access levels in `config/repositories.yaml`:
```yaml
# Full access repos (GitHub App)
writable_repos:
  - owner/repo-name

# Read-only repos (PAT only)
readable_repos:
  - external/repo-name
```

**Note**: If a repo appears in both lists, it's treated as writable.

## Features

### GitHub Watcher Service

**Purpose**: Host-side systemd timer service that monitors GitHub repositories every 5 minutes for PR events including check failures, new comments, merge conflicts, and review requests. For writable repos, automatically triggers jib container analysis via jib --exec. For read-only repos, sends Slack notifications with event details instead.

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

### PR Review Response System

**Purpose**: Automatically responds to PR reviews on jib's own PRs. When someone reviews a PR created by jib, this system:
- Analyzes review feedback (APPROVED, CHANGES_REQUESTED, COMMENTED)
- Addresses requested changes by implementing fixes
- Responds to inline review comments
- Tracks iteration count to prevent infinite loops (max 5 iterations)
- Stops when a clean approval is received (no caveats like "LGTM but...")

**Components**:
- **Review Detection** (`host-services/analysis/github-watcher/github-watcher.py`) - Detects reviews on bot PRs
- **Review Response Handler** (`jib-container/jib-tasks/github/github-processor.py`) - Processes reviews and takes action
- **Iteration Tracking** - Uses Beads to track review iterations across container sessions
- **Approval Detection** - Determines when a full approval without caveats has been received

**Location**:
- `host-services/analysis/github-watcher/github-watcher.py` - `check_pr_for_review_response()`
- `jib-container/jib-tasks/github/github-processor.py` - `handle_pr_review_response()`

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

**Purpose**: Generates short-lived (1 hour) GitHub App installation access tokens from stored credentials. Used by jib launcher to authenticate gh CLI and git operations without SSH keys.

**Location**: `jib-container/jib-tools/github-app-token.py`

## Related Documentation

- [GitHub App Setup](../setup/github-app-setup.md)
- [PR Context Manager](workflow-context.md)

## Source Files

| Component | Path |
|-----------|------|
| GitHub Watcher Service | `host-services/analysis/github-watcher/github-watcher.py` |
| GitHub CI/CD Failure Processor | `jib-container/jib-tasks/github/github-processor.py` |
| PR Auto-Review System | `jib-container/jib-tasks/github/pr-reviewer.py` |
| PR Comment Auto-Responder | `jib-container/jib-tasks/github/comment-responder.py` |
| PR Review Response System | `jib-container/jib-tasks/github/github-processor.py` |
| PR Analyzer Tool | `host-services/analysis/analyze-pr/analyze-pr.py` |
| GitHub Command Handler | `jib-container/jib-tasks/github/command-handler.py` |
| GitHub App Token Generator | `jib-container/jib-tools/github-app-token.py` |

---

*Auto-generated by Feature Analyzer*
