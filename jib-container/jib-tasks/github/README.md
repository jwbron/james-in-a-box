# GitHub Processors

Container-side component that provides comprehensive GitHub PR automation.

**Type**: Exec-based analysis (triggered by github-sync.service via `jib --exec`)
**Capabilities**:
- **Failure Monitoring**: Detect CI/CD failures, analyze logs, auto-implement fixes
- **Auto-Review**: Automatically review new PRs from others (`--watch` mode)
- **Code Review**: Generate comprehensive on-demand PR reviews
- **Comment Response**: Automatically suggest responses to PR comments

## Overview

GitHub Processors run inside the jib container and analyze `~/context-sync/github/` (synced by the host-side github-sync component). Scripts are triggered via `jib --exec` after each github-sync run and provide three main capabilities:

1. **GitHub Processor** - Detects CI/CD failures and suggests/implements fixes
2. **PR Reviewer** - Auto-reviews new PRs from others (watch mode)
3. **Comment Responder** - Suggests responses to comments on your PRs

## Execution Model

All scripts are invoked via `jib --exec`:

```
github-sync.service completes
        ↓
Triggers via ExecStartPost:
  jib --exec python3 github-processor.py
  jib --exec python3 pr-reviewer.py --watch
  jib --exec python3 comment-responder.py
        ↓
Each script runs in ephemeral container, analyzes data, exits
        ↓
Notifications sent to ~/sharing/notifications/ → Slack
```

**No background processes** - Each script runs once, performs analysis, creates notifications, and exits.

## GitHub Processor (`github-processor.py`)

Analyzes CI/CD check failures and suggests or implements fixes.

```
~/context-sync/github/checks/repo-PR-123-checks.json
        ↓
github-processor.py (runs via jib --exec after github-sync)
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
Creates Slack notification with analysis and suggested actions
```

**Usage:**
```bash
# Run manually (normally triggered automatically)
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/github-processor.py
```

## PR Auto-Review (`pr-reviewer.py --watch`)

Automatically reviews new PRs from others when running in watch mode.

```
~/context-sync/github/prs/*.md (all synced PRs)
        ↓
pr-reviewer.py --watch (runs via jib --exec after github-sync)
        ↓
Scans for new PRs not yet reviewed
        ↓
Skips your own PRs (no self-review)
        ↓
For each new PR from others:
    - Analyzes diff content and patterns
    - Checks for security concerns
    - Reviews code quality
    - Identifies performance issues
        ↓
Creates review notification with findings
        ↓
Marks PR as reviewed (tracks in state file)
```

**State Tracking:**
- State file: `~/sharing/tracking/pr-reviewer-state.json`
- Tracks which PRs have been reviewed to avoid duplicates
- Persists across container restarts

**Usage:**
```bash
# Watch mode (scan and review new PRs) - normally triggered automatically
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/pr-reviewer.py --watch

# Review specific PR
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/pr-reviewer.py 123

# Review specific PR in repo
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/pr-reviewer.py 123 repo-name
```

## PR Code Review (On-Demand)

In addition to automatic failure monitoring, you can request on-demand code reviews for any PR:

```
User sends via Slack: "review PR 123" or "review PR 123 in webapp"
        ↓
Message appears in ~/sharing/incoming/
        ↓
Command Handler (runs via jib --exec)
        ↓
Parses command: PR #123, repo: webapp
        ↓
PR Reviewer analyzes:
    - Diff content and file changes
    - Code quality patterns
    - Security concerns (eval, SQL injection, XSS)
    - Performance issues
    - Best practice violations
    - Testing coverage
        ↓
Creates Beads task: "Review PR #123: {title}"
        ↓
Generates comprehensive review:
    - Overall assessment
    - File-by-file analysis
    - Security/performance concerns
    - Testing gaps
    - Prioritized suggestions
        ↓
Sends Slack notification with full review
```

**Supported Commands:**
- `review PR 123` - Review PR #123 (auto-detects repository)
- `review PR 123 in webapp` - Review PR #123 in specific repo
- `/pr review 123` - Alternative syntax
- `/pr review 123 webapp` - Alternative with repo

**Review Coverage:**
- **Code Quality**: Console logs, TODOs, hardcoded values, code smells
- **Security**: eval/exec usage, SQL injection risks, XSS vulnerabilities
- **Python**: Bare exceptions, print statements, string formatting
- **JavaScript**: var keyword, == vs ===, dangerouslySetInnerHTML
- **Performance**: Potential performance bottlenecks
- **Testing**: Missing test coverage for new code

## Comment Response (Automatic)

Automatically detects new PR comments on **your PRs** and generates suggested responses:

**Scope**: Only processes:
- PRs you've opened (`--author @me`)
- Comments from others (skips your own comments and bots)
- Future expansion: PRs you're tagged on for review

```
Host syncs PR comments every 15 min
        ↓
~/context-sync/github/comments/
    repo-PR-123-comments.json
        ↓
Comment Responder (runs via jib --exec)
        ↓
Detects new comment (not previously seen)
        ↓
Analyzes comment type:
    - Question (?, "why", "how", "what about")
    - Change request ("fix", "update", "change to")
    - Concern ("worried", "concern", "might")
    - Positive feedback ("LGTM", "looks good")
        ↓
Creates Beads task: "Respond to {author}'s comment on PR #{num}"
        ↓
Generates contextual response:
    - Based on comment type
    - PR context and description
    - Appropriate tone and detail level
        ↓
Sends Slack notification:
    - Original comment
    - Suggested response (with placeholders if needed)
    - Type and confidence level
    - Next steps for customization
        ↓
User reviews, customizes, and posts response
```

**Comment Types and Responses:**

**Question** - User asking "why" or "how":
```
Original: "Why did you use Redis here instead of direct DB queries?"
Suggested: "Good question! The reasoning behind this approach is [EXPLAIN DECISION].
This allows us to [BENEFIT], though I'm open to alternative approaches if you have suggestions."
Type: question, Confidence: medium
```

**Change Request** - User requesting specific changes:
```
Original: "Please change the timeout from 30s to 60s"
Suggested: "Good catch! I'll update this. Let me make that change and push an update."
Type: change_request, Confidence: high, Action required: YES
```

**Concern** - User expressing worry:
```
Original: "I'm concerned this might cause issues with concurrent requests"
Suggested: "That's a valid concern. [EXPLAIN HOW CURRENT APPROACH ADDRESSES THIS].
Would that address your concern?"
Type: concern, Confidence: medium
```

**Positive** - LGTM or approval:
```
Original: "Looks good to me!"
Suggested: "Thanks @reviewer!"
Type: positive, Confidence: high
```

**Features:**
- Automatic detection of comment type
- Context-aware response generation
- Placeholder markers for customization needs
- Action flags for change requests
- Beads task tracking

## Automatic Fix Examples

### Linting Failures (IMPLEMENTED)
```
Detected: ESLint failures in PR #123
Analysis: Code style violations
Auto-fix: YES

Automatic Action:
  1. Checkout PR branch
  2. Create fix branch: fix/pr-123-autofix-YYYYMMDD
  3. Run: eslint --fix (or black for Python)
  4. Commit changes with descriptive message
  5. Update Beads task with fix details
  6. Notify user with branch name and commit hash

Result:
  - Branch: fix/pr-123-autofix-20251124
  - Commit: a3f8e2d
  - Files changed: 5 files fixed
  - Status: Ready for review and push
```

### Missing Import (NOT AUTO-FIXED)
```
Detected: ImportError in tests
Analysis: Missing dependency in requirements.txt
Auto-fix: NO (requires human judgment)

Action:
  1. Create Beads task
  2. Analyze error to identify missing package
  3. Notify user with suggested dependency
  4. Wait for human to review and add dependency
```

### Complex Test Failure (NOT AUTO-FIXED)
```
Detected: Test assertion failures
Analysis: Logic error in new code
Auto-fix: NO

Action:
  1. Create Beads task
  2. Extract relevant log excerpts
  3. Provide root cause analysis
  4. Suggest debugging steps
  5. Send notification with analysis
  6. Wait for human investigation
```

## Monitored Check Types

- **pytest**, **jest**, **mocha** (test frameworks)
- **eslint**, **pylint**, **flake8** (linters)
- **typescript**, **mypy** (type checkers)
- **build**, **compile** (build systems)
- **coverage** (code coverage)

## State Management

Tracks which failures have been notified to avoid spam:

**State file**: `~/sharing/tracking/github-processor-state.json`

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
bd create "Fix PR #123 check failures: eslint, pytest" \
  --label pr-123 --label ci-failure --label webapp --label urgent
```

This enables:
- Tracking fixes across sessions
- Resuming work after interruptions
- Coordinating with other work

## Running Scripts Manually

All scripts should be run via `jib --exec`:

```bash
# Run github processor manually
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/github-processor.py

# Run PR reviewer in watch mode
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/pr-reviewer.py --watch

# Run comment responder
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/comment-responder.py

# Run command handler
jib --exec python3 ~/workspace/james-in-a-box/jib-container/jib-tasks/github/command-handler.py
```

## Configuration

No configuration needed - automatically discovers PRs from synced data.

**Sync interval**: Every 15 minutes (host-side github-sync.timer)
**Analysis trigger**: Immediately after sync completes (via ExecStartPost)

Detection timing:
- Check failures: Within 15 minutes of failure occurring
- New PRs to review: Within 15 minutes of PR creation
- New comments: Within 15 minutes of comment posting
