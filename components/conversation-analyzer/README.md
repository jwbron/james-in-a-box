# Conversation Analyzer

Analyzes Claude Code conversations daily (2 AM PST) for quality, tone, and cultural alignment.

**Status**: Operational
**Type**: Host-side systemd timer
**Purpose**: Monitor agent behavior and cultural fit

## Setup

```bash
cd ~/khan/james-in-a-box/components/conversation-analyzer
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

# Run manually
systemctl --user start conversation-analyzer.service

# View logs
journalctl --user -u conversation-analyzer.service -f

# Enable/disable timer
systemctl --user enable conversation-analyzer.timer
systemctl --user disable conversation-analyzer.timer
```

## Files

- `conversation-analyzer.service` - Systemd service file
- `conversation-analyzer.timer` - Systemd timer (runs daily 2 AM)
- `setup.sh` - Installation script
- `conversation-analyzer.py` - Analysis script

## Features

- Daily conversation analysis
- Cultural alignment evaluation (Khan Academy L3-L4 standards)
- Tone and communication quality assessment
- Sends reports to Slack
- Systemd timer integration
