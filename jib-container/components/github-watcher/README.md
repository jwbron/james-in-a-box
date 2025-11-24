# GitHub Watcher

Container-side component that monitors GitHub PR check failures and triggers proactive analysis.

**Type**: Container background service
**Purpose**: Detect CI/CD failures, analyze logs, suggest/implement fixes automatically

## Overview

GitHub Watcher runs inside the JIB container and monitors `~/context-sync/github/` (synced by the host-side github-sync component) for PR check failures. When detected, it:

1. **Detects** new check failures
2. **Creates Beads task** for tracking the fix
3. **Analyzes** failure logs to determine root cause
4. **Determines** if fix is obvious and can be automated
5. **Sends Slack notification** with analysis and suggested actions
6. **Implements fix** automatically if obvious (in separate branch)

## How It Works

```
Host syncs PR data every 15 min
        ↓
~/context-sync/github/checks/
    repo-PR-123-checks.json (includes full logs for failures)
        ↓
GitHub Watcher (runs every 5 min in container)
        ↓
Detects new failure (not previously notified)
        ↓
Creates Beads task (bd-a3f8: "Fix PR #123 check failures")
        ↓
Analyzes logs for patterns:
    - Test failures (ImportError, AssertionError, etc.)
    - Linting failures (ESLint, PyLint)
    - Build failures
        ↓
Determines if auto-fixable:
    - Linting: YES (run linter --fix)
    - Simple test fixes: MAYBE
    - Complex failures: NO (human needed)
        ↓
Creates Slack notification:
    - Failure summary
    - Log excerpts
    - Root cause analysis
    - Suggested actions
    - "Implement fix" button if auto-fixable
        ↓
User replies via Slack or JIB acts automatically
```

## Automatic Fix Examples

### Linting Failures
```
Detected: ESLint failures in PR #123
Analysis: Code style violations
Auto-fix: YES
Action:
  1. Create branch: fix/pr-123-linting
  2. Run: eslint --fix
  3. Commit changes
  4. Notify user with branch name
```

### Missing Import
```
Detected: ImportError in tests
Analysis: Missing dependency in requirements.txt
Auto-fix: MAYBE (if dependency is obvious)
Action:
  1. Identify missing package from error
  2. Add to requirements.txt
  3. Create branch and commit
  4. Notify user for review
```

### Complex Test Failure
```
Detected: Test assertion failures
Analysis: Logic error in new code
Auto-fix: NO
Action:
  1. Create Beads task
  2. Provide detailed log analysis
  3. Suggest debugging steps
  4. Wait for human investigation
```

## Monitored Check Types

- **pytest**, **jest**, **mocha** (test frameworks)
- **eslint**, **pylint**, **flake8** (linters)
- **typescript**, **mypy** (type checkers)
- **build**, **compile** (build systems)
- **coverage** (code coverage)

## State Management

Tracks which failures have been notified to avoid spam:

**State file**: `~/sharing/tracking/github-watcher-state.json`

```json
{
  "notified": {
    "org/repo-123:eslint,pytest": "2025-01-20T14:30:00Z",
    "org/repo-456:build": "2025-01-20T15:00:00Z"
  }
}
```

Only notifies once per unique combination of (PR + failed check names).

## Integration with Beads

Every PR check failure creates a Beads task:

```bash
beads add "Fix PR #123 check failures: eslint, pytest" \
  --tags pr-123,ci-failure,webapp,urgent \
  --notes "PR #123 in org/webapp
Failed checks: eslint, pytest
URL: https://github.com/org/webapp/pull/123"
```

This enables:
- Tracking fixes across sessions
- Resuming work after interruptions
- Coordinating with other work

## Logs

**Location**: `~/sharing/tracking/github-watcher.log`

```bash
# View logs
tail -f ~/sharing/tracking/github-watcher.log

# Recent activity
tail -n 50 ~/sharing/tracking/github-watcher.log
```

## Control

```bash
# Start watcher
~/khan/james-in-a-box/jib-container/components/github-watcher/github-watcher-ctl start

# Stop watcher
~/khan/james-in-a-box/jib-container/components/github-watcher/github-watcher-ctl stop

# Check status
~/khan/james-in-a-box/jib-container/components/github-watcher/github-watcher-ctl status

# Restart
~/khan/james-in-a-box/jib-container/components/github-watcher/github-watcher-ctl restart
```

## Startup

GitHub Watcher starts automatically when the JIB container starts (via Docker entrypoint script).

## Configuration

No configuration needed - automatically discovers PRs from synced data.

**Check interval**: Every 5 minutes (inside container)
**Host sync interval**: Every 15 minutes

This means failures are detected within 5-20 minutes:
- Best case: 5 min (just after host sync)
- Worst case: 20 min (just before host sync)
