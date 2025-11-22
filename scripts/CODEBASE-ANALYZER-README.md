# Codebase Improvement Analyzer

Automated daily analysis of the james-in-a-box codebase to identify potential improvements, security issues, and technology updates.

## Overview

The Codebase Analyzer:
- **Analyzes files** in the james-in-a-box project for code quality, security, and best practices
- **Searches the web** for new technologies and improvements relevant to the project
- **Sends Slack notifications** with findings via the existing notification system
- **Runs automatically** daily at 11am PST and 5 minutes after system startup

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Systemd Timer (11am daily + 5min after boot)           │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  codebase-analyzer.py                                    │
│  ┌──────────────────────────────────────────────────┐   │
│  │  1. Scan ~/khan/james-in-a-box files           │   │
│  │  2. Analyze each file with Claude API            │   │
│  │  3. Search web for improvements                  │   │
│  │  4. Generate findings report                     │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  Notification File                                       │
│  ~/.jib-sharing/notifications/               │
│  └── YYYYMMDD-HHMMSS-codebase-improvements.md          │
└─────────────────┬───────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│  Slack Notification (via host-notify-slack.py)          │
│  → DM sent to you with analysis results                 │
└─────────────────────────────────────────────────────────┘
```

## Features

### File Analysis
- **Security**: Identifies vulnerabilities, auth issues, credential exposure
- **Performance**: Finds optimization opportunities
- **Maintainability**: Suggests code improvements and refactoring
- **Error Handling**: Points out missing or inadequate error handling
- **Documentation**: Identifies documentation gaps
- **Modern Practices**: Suggests updates to use current best practices

### Web Research
Searches for:
- Docker sandbox best practices
- Claude Code CLI improvements
- Python systemd integration patterns
- Slack bot security
- File watching alternatives and improvements

### Smart Filtering
- Only analyzes relevant file types (.py, .sh, .md, .yml, Dockerfile)
- Skips large files (>100KB)
- Limits analysis to avoid excessive API costs (~20 files per run)
- Reports only HIGH and MEDIUM priority findings

## Installation

### Prerequisites

1. **Python packages**:
   ```bash
   pip install anthropic requests
   ```

2. **Anthropic API Key**:
   Set in environment:
   ```bash
   export ANTHROPIC_API_KEY='your-key-here'
   ```

   Or create `~/.config/environment.d/anthropic.conf`:
   ```
   ANTHROPIC_API_KEY=your-key-here
   ```

3. **Slack notification system**:
   Ensure `host-notify-slack.py` is running (watches `~/.jib-sharing/notifications/`)

### Setup

```bash
cd ~/khan/james-in-a-box/scripts

# Check requirements
./analyzer-ctl.sh check

# Install systemd service
./analyzer-ctl.sh install

# Enable and start timer
./analyzer-ctl.sh enable

# Check status
./analyzer-ctl.sh status
```

## Usage

### Control Script

```bash
# Check requirements and configuration
./analyzer-ctl.sh check

# Install service
./analyzer-ctl.sh install

# Enable timer (start automatic runs)
./analyzer-ctl.sh enable

# Disable timer (stop automatic runs)
./analyzer-ctl.sh disable

# Run analyzer once (manual)
./analyzer-ctl.sh start

# Check service status
./analyzer-ctl.sh status

# View logs
./analyzer-ctl.sh logs

# Test run (direct execution)
./analyzer-ctl.sh test

# Uninstall service
./analyzer-ctl.sh uninstall
```

### Manual Execution

```bash
cd ~/khan/james-in-a-box/scripts
python3 ./codebase-analyzer.py
```

### Check Scheduled Runs

```bash
systemctl --user list-timers codebase-analyzer.timer
```

## Schedule

The analyzer runs:

1. **Daily at 11:00 AM** (system local time - set to America/Los_Angeles for PST)
2. **5 minutes after boot** (ensures analysis runs even if system was off at 11am)

## Output

### Notification Format

Notifications are created in `~/.jib-sharing/notifications/` with format:

```markdown
# 🔍 Codebase Improvement Analysis

**Generated**: YYYY-MM-DD HH:MM:SS
**Project**: james-in-a-box

## 📊 Summary
- Files Analyzed: X
- Web Research Findings: Y
- Priority Breakdown: HIGH/MEDIUM counts

## 🔧 File-Specific Improvements
### ⚠️ HIGH Priority
[Critical issues requiring immediate attention]

### 📋 MEDIUM Priority
[Important improvements to consider]

## 🌐 Technology & Best Practice Research
[Web search findings about new tech/practices]

## 🎯 Next Steps
[Recommended actions]
```

### Slack Message

The notification file triggers a Slack DM via the host notification system within ~30 seconds.

## Configuration

### Adjust Analysis Scope

Edit `codebase-analyzer.py`:

```python
# Number of files to analyze per run (default: 20)
max_files_to_analyze = 20

# File size limit (default: 100KB)
if file_path.stat().st_size > 100_000:

# Web search queries
search_queries = [
    "Your custom searches...",
]
```

### Adjust Schedule

Edit `codebase-analyzer.timer`:

```ini
# Change daily run time
OnCalendar=*-*-* 11:00:00

# Change boot delay
OnBootSec=5min
```

Then reload:
```bash
./analyzer-ctl.sh install  # Reinstall
systemctl --user daemon-reload
```

## Troubleshooting

### Service won't start

```bash
# Check logs
journalctl --user -u codebase-analyzer.service -n 50

# Check API key
echo $ANTHROPIC_API_KEY

# Test manually
python3 ./codebase-analyzer.py
```

### No notifications received

1. Check analyzer ran:
   ```bash
   systemctl --user status codebase-analyzer.service
   ```

2. Check notification file created:
   ```bash
   ls -lt ~/.jib-sharing/notifications/ | head
   ```

3. Check Slack notifier running:
   ```bash
   systemctl --user status slack-notifier.service
   ```

### API rate limits

If hitting rate limits, adjust in `codebase-analyzer.py`:
- Reduce `max_files_to_analyze`
- Remove some web search queries
- Add delays between API calls

## Cost Estimation

Per daily run (approximate):
- **File analysis**: ~20 files × 1,500 tokens each = ~30K tokens
- **Web search**: ~5 queries × 800 tokens each = ~4K tokens
- **Total**: ~34K tokens/day (~1M tokens/month)

At Claude API pricing (~$3 per million tokens for Sonnet):
- **Monthly cost**: ~$3

## Integration with Development Workflow

1. **Morning Review**: Check Slack notification at 11am PST
2. **Prioritize**: Review HIGH priority findings first
3. **Create Tasks**: Add approved improvements to JIRA
4. **Implement**: Schedule fixes in sprint planning
5. **Track**: Use context documents to track improvements over time

## Files

```
james-in-a-box/scripts/
├── codebase-analyzer.py           # Main analyzer script
├── codebase-analyzer.service      # Systemd service file
├── codebase-analyzer.timer        # Systemd timer file
├── analyzer-ctl.sh                # Control script
└── CODEBASE-ANALYZER-README.md    # This file
```

## Security Considerations

- **API Key**: Stored in environment, not in code
- **Read-only**: Analyzer only reads codebase, never modifies
- **Sandboxing**: Runs with limited permissions (ProtectSystem=strict)
- **Network**: Only outbound HTTPS (Claude API, web search)
- **Notifications**: Use existing trusted Slack notification system

## Future Enhancements

Potential improvements:
- [ ] Track improvements over time (trend analysis)
- [ ] Integration with JIRA (auto-create tickets)
- [ ] Customizable analysis rules per file type
- [ ] Comparison with industry benchmarks
- [ ] Integration with GitHub (comment on PRs)
- [ ] Cost tracking and optimization
- [ ] Summary reports (weekly/monthly rollup)

## License

Part of the james-in-a-box project.

## Support

For issues or questions:
1. Check logs: `./analyzer-ctl.sh logs`
2. Test manually: `./analyzer-ctl.sh test`
3. Review this README
4. Check james-in-a-box main documentation
