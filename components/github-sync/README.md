# GitHub Sync

Syncs GitHub PR data to `~/context-sync/github/` for JIB consumption.

**Status**: Operational
**Type**: Host-side systemd timer service
**Purpose**: Enable JIB to monitor PR check failures and provide automated assistance

## Overview

GitHub Sync fetches data for all open PRs you've authored and stores it locally as markdown and JSON. This enables JIB to:
- Monitor CI/CD check failures proactively
- Analyze failed test logs and suggest fixes
- Automatically implement obvious fixes in separate branches
- Track PR comments and discussions

## How It Fits Into JIB

```
GitHub (remote PRs)
        ↓
GitHub Sync (host systemd timer, runs every 15 min)
        ↓
~/context-sync/github/           # Synced PR data
├── index.json                   # Quick lookup
├── prs/
│   ├── webapp-PR-123.md         # PR metadata, description, comments
│   ├── webapp-PR-123.diff       # Full diff
│   └── frontend-PR-456.md
└── checks/
    ├── webapp-PR-123-checks.json    # Check status + full logs for failures
    └── frontend-PR-456-checks.json
        ↓
JIB Container (read-only mount)
~/context-sync/github/ → github-watcher monitors for failures
        ↓
Proactive analysis + Slack notification
```

## Setup

```bash
cd ~/khan/james-in-a-box/components/github-sync
./setup.sh
```

This will:
- Create systemd service and timer
- Set up sync directory structure
- Enable timer for automated syncing

## Prerequisites

**GitHub CLI (gh)** must be installed and authenticated:

```bash
# Check if installed
gh --version

# Install if needed
# macOS:
brew install gh

# Linux (Fedora/RHEL):
sudo dnf install gh

# Linux (Ubuntu/Debian):
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh

# Authenticate
gh auth login
```

## Usage

### Initial Sync

```bash
# Run first sync
systemctl --user start github-sync.service

# Watch progress
journalctl --user -u github-sync.service -f
```

### Enable Automated Syncing

```bash
# Start automated syncing (every 15 minutes)
systemctl --user start github-sync.timer

# Check timer status
systemctl --user status github-sync.timer
```

### Manual Sync

```bash
# Trigger sync manually
systemctl --user start github-sync.service
```

## What Gets Synced

For each **open PR you've authored**:

1. **PR Metadata** (`~/context-sync/github/prs/<repo>-PR-<number>.md`):
   - Title, description, author
   - Files changed with line counts
   - All comments and discussions
   - Branch information

2. **Full Diff** (`~/context-sync/github/prs/<repo>-PR-<number>.diff`):
   - Complete unified diff of all changes

3. **Check Status** (`~/context-sync/github/checks/<repo>-PR-<number>-checks.json`):
   - Status of all CI/CD checks
   - **Full logs for any failed checks** (critical for analysis)
   - Check timestamps and URLs

## Sync Frequency

**Every 15 minutes** (configurable in `systemd/github-sync.timer`)

Why 15 minutes:
- Fast enough to detect failures quickly
- Slow enough to avoid API rate limits
- Balances freshness with resource usage

## JIB Integration

JIB's `github-watcher` component monitors the synced data and:

1. **Detects new check failures**
2. **Analyzes failure logs** (full logs available for user's PRs)
3. **Determines root cause** and suggests fixes
4. **Implements obvious fixes** in a separate branch automatically
5. **Sends Slack notification** with analysis and next steps

## Management

```bash
# Check timer status
systemctl --user status github-sync.timer

# Check last sync
systemctl --user status github-sync.service

# View logs
journalctl --user -u github-sync.service -n 50

# Manual sync
systemctl --user start github-sync.service

# Stop automated syncing
systemctl --user stop github-sync.timer

# Restart timer (e.g., after changes)
systemctl --user restart github-sync.timer
```

## Troubleshooting

### "gh not found"
Install GitHub CLI (see Prerequisites above)

### "gh authentication required"
```bash
gh auth login
# Follow prompts to authenticate
```

### "No PRs synced"
Check that you have open PRs:
```bash
gh pr list --author @me --state open
```

### Sync not running
```bash
# Check timer is enabled and active
systemctl --user status github-sync.timer

# Check service logs for errors
journalctl --user -u github-sync.service --no-pager
```

### API rate limits
GitHub has API rate limits (5000 requests/hour for authenticated users). With 15-minute sync intervals, you should stay well under limits.

## Data Storage

- **Location**: `~/context-sync/github/`
- **Format**: Markdown (PRs), JSON (checks), diff files
- **Cleanup**: Automatically removes data for closed PRs
- **Size**: Varies with PR count and diff size (typically <10MB per PR)

## Security

- Requires GitHub authentication (via `gh auth`)
- Only syncs **your** PRs (not all org PRs)
- Data stored locally (not shared)
- JIB container has **read-only** access
- No GitHub write access from JIB container

## Future Enhancements

- Support for PRs you're reviewing (not just authored)
- Filter by repository
- Webhook-based real-time updates
- GitHub Actions log streaming
