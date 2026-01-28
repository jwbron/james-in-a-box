# GitHub Processors

Container-side component that provides GitHub PR automation via Slack commands.

**Type**: Exec-based analysis (triggered via `jib --exec`)
**Capabilities**:
- **Code Review**: Generate comprehensive on-demand PR reviews
- **PR Analysis**: Analyze PR content, changes, and context

## Overview

GitHub Processors run inside the jib container and handle GitHub-related tasks triggered via Slack commands. Scripts are triggered via `jib --exec` from the slack-receiver service.

## Components

### GitHub Processor (`github-processor.py`)

Main processor that handles GitHub-related tasks triggered by Slack commands. Analyzes PRs, handles review requests, and provides PR context.

**Usage:**
```bash
# Run via slack command (normal flow)
# User sends "review PR 123" via Slack → slack-receiver → jib --exec

# Run manually
jib --exec python3 ~/repos/james-in-a-box/jib-container/jib-tasks/github/github-processor.py
```

### Command Handler (`command-handler.py`)

Routes user commands received via Slack for GitHub operations like 'review PR 123' or '/pr review 123 webapp'. Parses commands and delegates to appropriate handlers.

**Supported Commands:**
- `review PR 123` - Review PR #123 (auto-detects repository)
- `review PR 123 in webapp` - Review PR #123 in specific repo
- `/pr review 123` - Alternative syntax
- `/pr review 123 webapp` - Alternative with repo

## PR Code Review (On-Demand)

Request on-demand code reviews for any PR via Slack:

```
User sends via Slack: "review PR 123" or "review PR 123 in webapp"
        ↓
Message appears in ~/sharing/incoming/
        ↓
Command Handler (runs via jib --exec)
        ↓
Parses command: PR #123, repo: webapp
        ↓
Analyzes:
    - Diff content and file changes
    - Code quality patterns
    - Security concerns (eval, SQL injection, XSS)
    - Performance issues
    - Best practice violations
    - Testing coverage
        ↓
Creates Beads task: "Review PR #123: {title}"
        ↓
Generates comprehensive review
        ↓
Sends Slack notification with full review
```

**Review Coverage:**
- **Code Quality**: Console logs, TODOs, hardcoded values, code smells
- **Security**: eval/exec usage, SQL injection risks, XSS vulnerabilities
- **Python**: Bare exceptions, print statements, string formatting
- **JavaScript**: var keyword, == vs ===, dangerouslySetInnerHTML
- **Performance**: Potential performance bottlenecks
- **Testing**: Missing test coverage for new code

## Integration with Beads

PR-related tasks create Beads tasks for tracking:

```bash
bd create "Review PR #123: title" \
  --label pr-123 --label webapp --label review
```

This enables:
- Tracking work across sessions
- Resuming work after interruptions
- Coordinating with other work

## Running Scripts Manually

All scripts should be run via `jib --exec`:

```bash
# Run github processor manually
jib --exec python3 ~/repos/james-in-a-box/jib-container/jib-tasks/github/github-processor.py

# Run command handler
jib --exec python3 ~/repos/james-in-a-box/jib-container/jib-tasks/github/command-handler.py
```
