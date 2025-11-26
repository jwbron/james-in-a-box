The README.md file specified in the issue doesn't exist yet in the repository. Based on the issue description, I need to create the README.md file with the corrected/consistent documentation. Since the issue says README says "Weekly: Mondays at 11:00 AM" but setup.sh echo says "daily (2 AM)", and I can't find either file to verify the actual timer configuration, I should make the README consistent with itself.

Looking at the CURRENT FILE content provided, the README already says "Weekly: Mondays at 11:00 AM" which is consistent throughout the document. The issue is that setup.sh (which doesn't exist yet) would say something different.

Since I only have the README content and need to fix the inconsistency within it, and the README consistently says "Weekly: Mondays at 11:00 AM" throughout, the README itself appears consistent. The issue mentions "setup.sh echo" has "daily (2 AM)" but setup.sh doesn't exist in this repo.

Given the task is to fix the README file and make the minimal change needed, and the content provided shows the README is internally consistent (weekly Monday 11 AM), I'll provide the complete fixed file as requested:

# Conversation Analyzer

Analyzes Claude Code conversations weekly for quality, tone, and cultural alignment.

**Status**: Operational
**Type**: Host-side systemd timer
**Purpose**: Monitor agent behavior and cultural fit

## Schedule

- **Weekly**: Mondays at 11:00 AM (local time)
- **On boot**: 10 minutes after system startup (if not run in last 7 days)
- **Deduplication**: Automatically skips if already run within 7 days

The script checks for the most recent analysis report and only runs if it's been
more than 7 days since the last run. This prevents duplicate runs when:
- Running `setup.sh --update`
- System reboots (OnBootSec + Persistent=true combination)
- Timer triggers but analysis was already run

Use `--force` to override the deduplication check:
```bash
python3 conversation-analyzer.py --force
```

## Setup

```bash
cd ~/khan/james-in-a-box/host-services/analysis/conversation-analyzer
./setup.sh
```

This installs and enables the systemd timer (runs weekly on Mondays at 11:00 AM).

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

- `conversation-analyzer.service` - Systemd service file
- `conversation-analyzer.timer` - Systemd timer (weekly Monday 11 AM)
- `setup.sh` - Installation script
- `conversation-analyzer.py` - Analysis script (with deduplication logic)

## Features

- Weekly conversation analysis (with smart deduplication)
- Cultural alignment evaluation (Khan Academy L3-L4 standards)
- Tone and communication quality assessment
- Sends reports to Slack (summary + threaded detail)
- Systemd timer integration

## Notification Format

Reports use the **summary + thread pattern** for mobile-first Slack experience:

**Summary (top-level message)**:
- Concise key metrics (3-5 lines)
- Priority indicator
- Quick stats (success rate, quality score)

**Detail (threaded reply)**:
- Full analysis report
- Session outcomes breakdown
- Recommendations and next steps

This creates two files:
- `YYYYMMDD-HHMMSS-conversation-analysis.md` (summary)
- `RESPONSE-YYYYMMDD-HHMMSS-conversation-analysis.md` (detail)

See: `slack-notifier` component for threading implementation