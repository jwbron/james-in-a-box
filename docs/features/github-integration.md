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

**Purpose**: Monitors GitHub repositories for PR events every 5 minutes.

**Location**: `host-services/analysis/github-watcher/`

**Helper Scripts**:
```bash
# Setup
./host-services/analysis/github-watcher/setup.sh

# Service management
systemctl --user status github-watcher.service
systemctl --user start github-watcher.timer
journalctl --user -u github-watcher.service -f

# Manual run
python host-services/analysis/github-watcher/github-watcher.py
```

**Configuration**: `~/.jib-sharing/.env`
```bash
GITHUB_APP_ID=12345
GITHUB_INSTALLATION_ID=67890
GITHUB_REPOS=owner/repo1,owner/repo2
```

**Monitored Events**:
- CI check failures (failed, cancelled, timed out)
- New comments on PRs
- Merge conflicts detected
- Review requests from others

**Key Capabilities**:
- Parallel task execution
- Rate limit handling with backoff
- Persistent state tracking
- Failed task retry system

### GitHub CI/CD Failure Processor

**Purpose**: Analyzes and fixes CI/CD check failures.

**Location**: `jib-container/jib-tasks/github/github-processor.py`

**Invoked by**: GitHub watcher via `jib --exec`

**Supported Failures**:
- Test failures (pytest, jest, etc.)
- Linting errors (eslint, ruff, mypy)
- Build failures (webpack, tsc)
- Type checking errors

**Workflow**:
1. Detect failure type from check name
2. Fetch failure logs
3. Analyze with Claude
4. Apply fixes
5. Push changes
6. Post comment with summary

### PR Auto-Review System

**Purpose**: Automatically reviews PRs from other developers.

**Location**: `jib-container/jib-tasks/github/pr-reviewer.py`

**Review Checks**:
- Code quality issues
- Security concerns (eval, SQL injection, XSS)
- Performance issues
- Best practice violations

**Output Format**:
```markdown
## Code Review Summary

### Security
- [file.py:42] Potential SQL injection vulnerability

### Performance
- [utils.js:15] Consider memoizing expensive calculation

### Suggestions
- [api.ts:100] Add error handling for edge case
```

### PR Comment Auto-Responder

**Purpose**: Responds to comments on your own PRs.

**Location**: `jib-container/jib-tasks/github/comment-responder.py`

**Response Types**:
- **Questions**: Provides explanations
- **Change requests**: Makes code changes
- **Concerns**: Addresses or escalates
- **Positive feedback**: Acknowledges

**Example Interaction**:
```
Human: "Can you add error handling here?"
Agent: [Makes code changes, pushes]
       "Added error handling with try/catch block.
        See commit abc1234."
```

### PR Analyzer Tool

**Purpose**: Comprehensive PR analysis with fix suggestions.

**Location**:
- Host: `host-services/analysis/analyze-pr/analyze-pr.py`
- Container: `jib-container/jib-tasks/github/pr-analyzer.py`

**Commands**:
```bash
# Analysis only (host-side)
bin/analyze-pr owner/repo 123

# With fix mode (via container)
bin/analyze-pr owner/repo 123 --fix

# Context only (dump PR info)
bin/analyze-pr owner/repo 123 --context-only
```

**Analysis Includes**:
- PR metadata and diff
- Comments and reviews
- CI status and logs
- Fix suggestions

### Merge Conflict Resolution

**Purpose**: Automatically resolves merge conflicts.

**Location**: `jib-container/jib-tasks/github/github-processor.py`

**Workflow**:
1. Checkout PR branch
2. Merge base branch
3. Identify conflict markers
4. Use Claude to resolve intelligently
5. Push resolution

**Supported Conflict Types**:
- Code conflicts
- Import statement conflicts
- JSON/YAML conflicts

### GitHub App Token Generator

**Purpose**: Generates short-lived (1 hour) GitHub App installation tokens.

**Location**: `jib-container/jib-tools/github-app-token.py`

**Used By**:
- jib launcher (MCP server auth)
- git operations (push/pull)

**Credentials**:
```
~/.jib-sharing/github-app-private-key.pem
```

### MCP Token Watcher

**Purpose**: Automatically refreshes MCP server when token changes.

**Location**: `jib-container/scripts/mcp-token-watcher.py`

**Monitors**: `~/.jib-sharing/github-token`

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        GitHub                                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │  PRs    │  │ Checks  │  │Comments │  │ Reviews │        │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘        │
└───────┼────────────┼────────────┼────────────┼──────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────┐
│              GitHub Watcher (Host-Side)                      │
│              Polls every 5 minutes                           │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Detects: failures, comments, conflicts, reviews     │    │
│  └────────────────────────────────────────────────────┘    │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    jib --exec                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Failure  │  │ Comment  │  │ Conflict │  │ Review   │   │
│  │ Processor│  │ Responder│  │ Resolver │  │ Generator│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   GitHub MCP Server                          │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Actions: push, comment, review, merge              │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### GitHub watcher not running

1. Check timer: `systemctl --user status github-watcher.timer`
2. Verify credentials: Check `GITHUB_APP_ID`, `GITHUB_INSTALLATION_ID`
3. Check repos: Verify `GITHUB_REPOS` list

### Token authentication fails

1. Refresh token: `systemctl --user restart github-token-refresher.service`
2. Verify private key: `~/.jib-sharing/github-app-private-key.pem`
3. Check installation: Verify app is installed on target repos

### PRs not being reviewed

1. Check watcher logs for the repo
2. Verify PR author is not you (only reviews others' PRs)
3. Check for rate limiting

### CI fix not pushing

1. Verify branch is writable
2. Check git remote is HTTPS (not SSH)
3. Review container logs: `jib-logs -n 100`

## Related Documentation

- [GitHub App Setup](../setup/github-app-setup.md)
- [PR Context Manager](workflow-context.md)
- [GitHub MCP Environment](../reference/environment.md)

## Source Files

| Component | Path |
|-----------|------|
| GitHub Watcher | `host-services/analysis/github-watcher/github-watcher.py` |
| GitHub Processor | `jib-container/jib-tasks/github/github-processor.py` |
| PR Reviewer | `jib-container/jib-tasks/github/pr-reviewer.py` |
| Comment Responder | `jib-container/jib-tasks/github/comment-responder.py` |
| PR Analyzer (host) | `host-services/analysis/analyze-pr/analyze-pr.py` |
| PR Analyzer (container) | `jib-container/jib-tasks/github/pr-analyzer.py` |
| Token Generator | `jib-container/jib-tools/github-app-token.py` |
| Token Refresher | `host-services/utilities/github-token-refresher/` |

---

*Auto-generated by Feature Analyzer*
