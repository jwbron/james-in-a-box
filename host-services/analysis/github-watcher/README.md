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
- Open PRs with check failures (writable repos only)
- PRs with new comments (since last check)
- PRs with merge conflicts (writable repos only)
- PRs where user is requested as reviewer
    |
    v
For writable repos: Trigger jib container via `jib --exec` for analysis
For read-only repos: Send Slack notification for user review
    |
    v
Writable: Container analyzes and takes action via GitHub CLI/MCP
Read-only: User reviews notification and responds manually
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

The watcher handles writable and read-only repos differently:

### Writable Repos (Full Functionality)

For repositories in `writable_repos`, jib has full access and can:

1. **Fix Check Failures**
   - Detects failing CI checks on your PRs and bot's PRs
   - Invokes `jib --exec github-processor.py --task check_failure`
   - Container analyzes logs, fixes code, pushes commits

2. **Resolve Merge Conflicts**
   - Detects PRs with merge conflicts
   - Invokes `jib --exec github-processor.py --task merge_conflict`
   - Container resolves conflicts and pushes

3. **Respond to PR Comments**
   - Monitors comments on your PRs and bot's PRs
   - Invokes `jib --exec github-processor.py --task comment`
   - Container posts responses directly to GitHub

4. **Review Other Authors' PRs**
   - Proactively reviews ALL PRs from other authors
   - Invokes `jib --exec github-processor.py --task review_request`
   - Container posts review comments to GitHub

### Read-Only Repos (Notification Only)

For repositories in `readable_repos`, jib cannot push/comment directly:

1. **Monitor PR Comments** (your PRs only)
   - Detects new comments on PRs you authored
   - Sends Slack notification with comment details
   - You formulate response and post manually

2. **Review Requested PRs** (directly tagged only)
   - Only PRs where you are DIRECTLY requested as reviewer (not via team)
   - Sends Slack notification with PR details for review
   - You review and respond manually on GitHub

**NOT monitored for read-only repos:**
- Check failures (can't fix without write access)
- Merge conflicts (can't resolve without write access)

## Configuration

Repositories are configured in `config/repositories.yaml`:

```yaml
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
