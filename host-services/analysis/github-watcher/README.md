# GitHub Watcher

Host-side service that monitors GitHub repositories and triggers jib container analysis.

**Status**: Refactored from monolithic `github-watcher.py` to three focused services
**Type**: Host-side systemd timer service
**Purpose**: Event-driven GitHub monitoring following ADR-Context-Sync-Strategy-Custom-vs-MCP

## Architecture

The watcher is split into three focused services, coordinated by a dispatcher:

```
Scheduled job (every 5 min) - HOST SIDE
    |
    v
dispatcher.py orchestrates three services:
    |
    +-> ci_fixer.py - Fix check failures & merge conflicts
    |
    +-> comment_responder.py - Respond to PR comments
    |
    +-> pr_reviewer.py - Review PRs (opt-in via assignment/tagging)
    |
    v
Each service queries GitHub, detects relevant events,
and triggers jib container via `jib --exec`
```

### Service Details

| Service | Purpose | Trigger Condition |
|---------|---------|-------------------|
| **CI Fixer** | Fix check failures and merge conflicts | User's PRs + Bot's PRs (automatic) |
| **Comment Responder** | Respond to comments and review feedback | PRs where jib is assigned, tagged, or author |
| **PR Reviewer** | Review PRs using collaborative development | PRs where jib is explicitly assigned/tagged (opt-in) |

**Key changes from previous version:**
- PR review is now opt-in (must be assigned/tagged) instead of proactive
- Modular architecture enables independent testing and maintenance
- Services share state via `gwlib/state.py` to avoid duplicate processing

### Shared Library (gwlib/)

Common functionality extracted into `gwlib/`:
- `github_api.py` - gh CLI wrappers with rate limiting
- `state.py` - Thread-safe state management
- `tasks.py` - Task execution with parallel support
- `config.py` - Configuration loading
- `detection.py` - PR event detection logic

**Note:** The watcher tracks when it last ran. If your machine is off for a period,
the first run after boot will pull all GitHub events since it last ran, ensuring
nothing is missed.

**Key principle**: The container should ONLY be called via `jib --exec`.
No watching/polling logic lives in the container.

## Setup

```bash
cd ~/khan/james-in-a-box/host-services/analysis/github-watcher
./setup.sh
```

This will:
- Create systemd user service and timer
- Enable timer for automated monitoring

## Prerequisites

**GitHub CLI (gh)** must be installed and authenticated:

```bash
gh auth status
```

## Usage

### Manual Run

```bash
# Run all services manually
systemctl --user start github-watcher.service

# Run a specific service
python3 dispatcher.py --service ci-fixer
python3 dispatcher.py --service comment-responder
python3 dispatcher.py --service pr-reviewer

# Watch progress
journalctl --user -u github-watcher.service -f
```

### Enable Automated Monitoring

```bash
# Start automated monitoring (every 5 minutes)
systemctl --user enable --now github-watcher.timer

# Check timer status
systemctl --user status github-watcher.timer
```

## What Each Service Does

### CI Fixer (Automatic)

Monitors PRs authored by jib or the configured user:

- **Check Failures**: Detects failing CI checks, invokes jib to analyze logs and fix code
- **Merge Conflicts**: Detects PRs with conflicts, invokes jib to resolve

### Comment Responder (On Engaged PRs)

Monitors PRs where jib is engaged (assigned, tagged, or author):

- **Comments**: Responds to new comments on PRs
- **Review Feedback**: Addresses review feedback on bot's PRs

### PR Reviewer (Opt-In)

Reviews PRs only when explicitly requested:

- **Review Requests**: Reviews PRs where jib is assigned as reviewer or tagged
- **For read-only repos**: Outputs review to Slack instead of GitHub

**Note:** This is a change from previous behavior which proactively reviewed ALL PRs.

## Configuration

Repositories are configured in `config/repositories.yaml`:

```yaml
github_username: jwbron
bot_username: james-in-a-box

# Full access - jib can push, comment, fix issues
writable_repos:
  - jwbron/james-in-a-box

# Read-only - jib sends Slack notifications only
readable_repos:
  - Khan/webapp
```

## State Tracking

The watcher maintains state in `~/.local/share/github-watcher/state.json` to avoid duplicate processing and track the last run time. State includes:

- `last_run`: ISO timestamp of when the watcher last ran (used to filter events)
- `processed_failures`: Check failure signatures already handled
- `processed_comments`: Comment threads already responded to
- `processed_reviews`: PRs already reviewed

When the watcher runs, it filters comments and new PRs to only those created after
`last_run`. This means if your machine was off for hours/days, the first run will
catch up on everything that happened since the last successful run.

## Troubleshooting

**GitHub CLI errors**:
```bash
gh auth status
gh auth login  # Re-authenticate if needed
```

**jib not found**:
```bash
# Ensure jib is in PATH
which jib
# Or use full path
~/khan/james-in-a-box/bin/jib --help
```

**Service analysis fails**:
```bash
# Check service logs
journalctl --user -u github-watcher.service -f
# Test container manually
jib --exec python3 -c "print('hello')"
```

**Run single service for debugging**:
```bash
cd ~/khan/james-in-a-box/host-services/analysis/github-watcher
python3 dispatcher.py --service ci-fixer
```
