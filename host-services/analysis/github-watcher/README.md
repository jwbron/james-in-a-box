# GitHub Watcher

Host-side service that monitors GitHub repositories and triggers jib container analysis.

**Status**: Replaces deprecated `github-sync` service
**Type**: Host-side systemd timer service
**Purpose**: Event-driven GitHub monitoring following ADR-Context-Sync-Strategy-Custom-vs-MCP

## Architecture

Following ADR Section 4 "Option B: Scheduled Analysis with MCP":

```
Scheduled job (every 5 min) - HOST SIDE
    |
    v
Query GitHub via CLI for events since last run:
- Open PRs with check failures
- PRs with new comments (since last check)
- New PRs from others for review (created since last check)
    |
    v
Trigger jib container via `jib --exec` for analysis
    |
    v
Container analyzes and takes action via GitHub CLI/MCP
```

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
# Run watcher manually
systemctl --user start github-watcher.service

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

## What It Does

For each configured repository, the watcher:

1. **Detects Check Failures**
   - Queries `gh pr checks` for each open PR authored by @me
   - If failures found, invokes `jib --exec github-processor.py --task check_failure`
   - Container dispatches to issue-fixer for analysis and fixes

2. **Monitors PR Comments** (your PRs only)
   - Queries `gh pr view --json comments` for your PRs
   - If new comments from others, invokes `jib --exec github-processor.py --task comment`
   - Container dispatches to comment-responder for response

3. **Reviews New PRs** (others' PRs)
   - Identifies new PRs from other authors
   - Invokes `jib --exec github-processor.py --task review_request`
   - Container dispatches to pr-reviewer for code review

## Configuration

Repositories are configured in `config/repositories.yaml`:

```yaml
writable_repos:
  - jwbron/james-in-a-box
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

## Migration from github-sync

This service replaces the deprecated `github-sync` which:
- Synced PR data to `~/context-sync/github/` files
- Required container scripts to read from files

The new approach:
- Queries GitHub directly via CLI
- No intermediate file sync needed
- Real-time data, not stale files
- Tracks last run time to catch up after downtime
- Simpler architecture

To migrate:
1. Disable old service: `systemctl --user disable github-sync.timer`
2. Enable new service: `systemctl --user enable --now github-watcher.timer`

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

**Container analysis fails**:
```bash
# Check container logs
journalctl --user -u github-watcher.service -f
# Test container manually
jib --exec python3 -c "print('hello')"
```
