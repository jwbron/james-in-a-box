# Codebase Analyzer

Runs daily codebase analysis (Monday 11 AM PST) and sends reports via Slack.

**Status**: Operational
**Type**: Host-side systemd timer
**Purpose**: Automated code quality and pattern analysis

## Setup

```bash
cd ~/khan/james-in-a-box/components/codebase-analyzer
./setup.sh
```

This installs and enables the systemd timer.

## Management

```bash
# Check timer status
systemctl --user status codebase-analyzer.timer
systemctl --user list-timers | grep codebase

# Check service status
systemctl --user status codebase-analyzer.service

# Run manually (doesn't wait for timer)
systemctl --user start codebase-analyzer.service

# View logs
journalctl --user -u codebase-analyzer.service -f

# Enable/disable timer
systemctl --user enable codebase-analyzer.timer
systemctl --user disable codebase-analyzer.timer
```

## Files

- `codebase-analyzer.service` - Systemd service file
- `codebase-analyzer.timer` - Systemd timer (runs Monday 11 AM)
- `setup.sh` - Installation script
- `codebase-analyzer.py` - Analysis script

## Features

- Weekly codebase analysis
- Pattern detection and anti-pattern identification
- Sends reports to Slack (summary + threaded detail)
- Systemd timer integration

## Notification Format

Reports use the **summary + thread pattern** for mobile-first Slack experience:

**Summary (top-level message)**:
- Concise key metrics (3-5 lines)
- Priority indicator
- Quick stats (HIGH/MEDIUM issue counts, security rating)

**Detail (threaded reply)**:
- Full analysis report
- File-specific improvements
- Web research findings
- Strategic recommendations

This creates two files:
- `YYYYMMDD-HHMMSS-codebase-improvements.md` (summary)
- `RESPONSE-YYYYMMDD-HHMMSS-codebase-improvements.md` (detail)

See: `slack-notifier` component for threading implementation
