# Conversation Analyzer

Analyzes jib's Slack threads and GitHub PRs weekly for quality, efficiency, and communication patterns.

**Status**: Operational
**Type**: Host-side systemd timer
**Purpose**: Monitor agent communication quality and effectiveness

## Data Sources

| Source | What's Analyzed | Key Metrics |
|--------|-----------------|-------------|
| **Slack** | Threads where jib participated | Resolution rate, message count, duration |
| **GitHub** | PRs with jib commits/comments | Merge rate, iterations, lines changed |

## Schedule

- **Weekly**: Mondays at 11:00 AM (local time)
- **On boot**: 10 minutes after system startup (if not run in last 7 days)
- **Deduplication**: Automatically skips if already run within 7 days

Use `--force` to override the deduplication check:
```bash
python3 conversation-analyzer.py --force
```

## Setup

### Prerequisites

1. **Slack Token** with these scopes:
   - `channels:history` - Read channel messages
   - `channels:read` - Access channel info
   - `users:read` - Get user display names

2. **GitHub Token** with:
   - `repo` scope (for private repos) or public access for public repos

### Configuration

Add credentials to `~/.config/jib/secrets.env`:
```bash
SLACK_TOKEN=xoxb-your-slack-bot-token
GITHUB_TOKEN=ghp_your-github-token
```

Add settings to `~/.config/jib/config.yaml`:
```yaml
slack_channel: C123456789  # Channel ID to analyze
github_repos:
  - owner/repo1
  - owner/repo2
```

### Install

```bash
cd ~/khan/james-in-a-box/host-services/analysis/conversation-analyzer
./setup.sh
```

This installs and enables the systemd timer.

## Management

```bash
# Check timer status
systemctl --user status conversation-analyzer.timer
systemctl --user list-timers | grep conversation

# Check service status
systemctl --user status conversation-analyzer.service

# Run manually (respects 7-day deduplication)
systemctl --user start conversation-analyzer.service

# Force run (ignores deduplication)
python3 ~/khan/james-in-a-box/host-services/analysis/conversation-analyzer/conversation-analyzer.py --force

# View logs
journalctl --user -u conversation-analyzer.service -f

# Enable/disable timer
systemctl --user enable conversation-analyzer.timer
systemctl --user disable conversation-analyzer.timer
```

## Files

| File | Purpose |
|------|---------|
| `conversation-analyzer.py` | Main analysis script |
| `conversation-analyzer.service` | Systemd service file |
| `conversation-analyzer.timer` | Systemd timer (weekly Monday 11 AM) |
| `setup.sh` | Installation script |
| `requirements.txt` | Python dependencies |

## Report Contents

### Slack Thread Analysis
- Total threads with jib participation
- Resolution rate (resolved/pending/escalated)
- Average messages per thread
- Average thread duration
- Thread summaries (last 10)

### GitHub PR Analysis
- Total PRs with jib contribution
- Merge rate and first-try success rate
- Average iterations per PR
- Average lines/files changed
- PR summaries with links

### Identified Patterns
- **Strengths**: What's working well
- **Areas for Improvement**: What needs attention
- **Efficiency Patterns**: Size/scope observations

### Recommendations
Prioritized (HIGH/MEDIUM/LOW) action items with specific suggestions.

## Output

Reports are saved to `~/sharing/analysis/`:

| File | Content |
|------|---------|
| `analysis-YYYYMMDD-HHMMSS.md` | Full markdown report |
| `metrics-YYYYMMDD-HHMMSS.json` | Structured metrics data |
| `latest-report.md` | Symlink to most recent report |
| `latest-metrics.json` | Symlink to most recent metrics |

## Notification Format

Reports use the **summary + thread pattern** for mobile-first Slack experience:

**Summary (top-level message)**:
- Concise key metrics (3-5 lines)
- Priority indicator based on recommendations
- Quick stats (resolution rate, merge rate)

**Detail (threaded reply)**:
- Full analysis report
- All metrics and breakdowns
- Recommendations and patterns

## Example Output

```
# jib Communication Analysis Report
Generated: 2025-11-26 12:00:00
Period: Last 7 days

## Executive Summary

| Source | Total | Success Rate |
|--------|-------|--------------|
| Slack Threads | 15 | 80.0% resolved |
| GitHub PRs | 8 | 87.5% merged |

## Slack Thread Analysis
- Total Threads: 15
- Resolved: 12 | Pending: 2 | Escalated: 1
- Resolution Rate: 80.0%
...
```

## Customization

### Analyze Different Time Periods
```bash
# Last 30 days
python3 conversation-analyzer.py --days 30

# Last 14 days with custom output
python3 conversation-analyzer.py --days 14 --output ~/sharing/analysis/biweekly
```

### Print to Stdout
```bash
python3 conversation-analyzer.py --force --print
```

## Troubleshooting

**"SLACK_TOKEN not configured"**
- Add token to `~/.config/jib/secrets.env`
- Or set environment variable: `export SLACK_TOKEN=xoxb-...`

**"SLACK_CHANNEL not configured"**
- Add `slack_channel: C...` to `~/.config/jib/config.yaml`
- Find channel ID: Right-click channel in Slack → View channel details → scroll to bottom

**"GITHUB_TOKEN not configured"**
- Create token at: https://github.com/settings/tokens
- Add to `~/.config/jib/secrets.env`

**"No data found for analysis"**
- Verify jib has participated in threads/PRs in the time period
- Check that tokens have correct permissions
- Try with `--days 30` for a longer time window
