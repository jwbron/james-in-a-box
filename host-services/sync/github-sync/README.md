# GitHub Sync

Syncs GitHub PR data to `~/context-sync/github/` for jib consumption.

**Status**: Operational
**Type**: Host-side systemd timer service
**Purpose**: Enable jib to monitor PR issues and provide automated assistance

**Scope**: Configurable via command-line flags.
- Your open PRs (default: `--author @me`)
- All PRs in a specific repo (`--repo <owner/repo> --all-prs`)
- PRs from others for auto-review

## Overview

GitHub Sync fetches PR data and stores it locally as markdown and JSON. This enables jib to:
- Detect and fix PR issues (check failures, merge conflicts)
- Let Claude analyze issues and determine appropriate fixes
- Track PR comments and discussions
- **Auto-review PRs from others** (when using `--all-prs`)
- **Respond to comments on your PRs**

## How It Fits Into jib

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
├── checks/
│   ├── webapp-PR-123-checks.json    # Check status + full logs for failures
│   └── frontend-PR-456-checks.json
└── comments/
    └── webapp-PR-123-comments.json  # PR comments for response tracking
        ↓
github-sync.service completes → Triggers analysis via `jib --exec`:
  1. issue-fixer.py      - Detect issues, let Claude determine and apply fixes
  2. pr-reviewer.py      - Auto-review new PRs from others
  3. comment-responder.py - Detect comments needing responses
        ↓
jib Container (one-time analysis per script)
~/context-sync/github/ → Script analyzes data → Creates notifications → exits
        ↓
Proactive analysis + Slack notifications
```

## Setup

```bash
cd ~/khan/james-in-a-box/host-services/sync/github-sync
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

## Command-Line Options

```bash
# Default: Sync only your PRs
python3 sync.py

# Sync all PRs in a specific repo (enables auto-review of others' PRs)
python3 sync.py --repo jwiesebron/james-in-a-box --all-prs

# Sync to custom output directory
python3 sync.py --output /path/to/output
```

**Flags:**
- `--repo, -r` - Specific repository to sync (e.g., `owner/repo`)
- `--all-prs, -a` - Sync ALL open PRs in repo, not just yours
- `--output, -o` - Output directory (default: `~/context-sync/github`)

**Systemd Configuration:**
The default systemd service is configured to sync all PRs in `jwiesebron/james-in-a-box`:
```ini
ExecStart=sync.py --repo jwiesebron/james-in-a-box --all-prs
```

## What Gets Synced

For each **open PR** (filtered by flags):

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

## jib Integration

After each sync, the github-sync service automatically triggers three analysis scripts via `jib --exec`:

### 1. Issue Fixer (`issue-fixer.py`)
- **Detects** check failures and merge conflicts
- **Delegates** to Claude to analyze and determine the fix strategy
- **Implements** appropriate fixes based on Claude's judgment
- **Sends** Slack notification with analysis and next steps

This approach is intentionally simple: the script detects issues and provides
context, then Claude decides how to fix them based on the specific situation
rather than using hardcoded fix strategies.

### 2. PR Reviewer (`pr-reviewer.py --watch`)
- **Scans** for new PRs that haven't been reviewed
- **Skips** your own PRs (no self-review)
- **Analyzes** code quality, security, performance patterns
- **Creates** review notification with findings
- **Tracks** reviewed PRs to avoid duplicate reviews

### 3. Comment Responder (`comment-responder.py`)
- **Detects** new comments on your PRs
- **Classifies** comment type (question, change request, concern, etc.)
- **Generates** contextual response suggestions
- **Creates** Beads task for tracking
- **Sends** notification with suggested response

This exec-based pattern ensures analysis only runs when new data is available (after sync completes).

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
- jib container has **read-only** access
- No GitHub write access from jib container

## Future Enhancements

- ~~Support for PRs you're reviewing (not just authored)~~ Done (`--all-prs` flag)
- ~~Filter by repository~~ Done (`--repo` flag)
- Webhook-based real-time updates
- GitHub Actions log streaming
