# Setup Guides

Installation and configuration documentation.

## Quick Start

Run the main setup script to configure everything:

```bash
cd ~/khan/james-in-a-box
./setup.sh
```

This installs all host services including Slack integration.

## Available Guides

### [GitHub App Setup](github-app-setup.md)
GitHub App configuration for automated PR creation:
- Required permissions (read-only and read-write)
- Installation steps
- Token configuration
- Troubleshooting common permission errors

### [Slack Quickstart](slack-quickstart.md)
Fast setup for Slack integration. Get notifications working in 10 minutes.

### [Slack App Setup](slack-app-setup.md)
Detailed Slack app configuration including:
- Creating the Slack app
- Configuring OAuth scopes
- Setting up Socket Mode
- Getting required tokens

### [Slack Bidirectional](slack-bidirectional.md)
Setting up two-way Slack communication:
- Sending notifications to Slack
- Receiving messages from Slack
- Thread-based conversations

## Setup Order

1. **Initial Setup** - Run `./setup.sh` (handles most configuration)
2. **Slack App** - [Create Slack app](slack-app-setup.md) if not done
3. **Configure Tokens** - Add tokens to `~/.config/jib-notifier/config.json`
4. **Verify** - Check services with `systemctl --user status slack-notifier slack-receiver`

## Service Overview

| Service | Purpose | Setup |
|---------|---------|-------|
| slack-notifier | Claude → You notifications | Included in main setup |
| slack-receiver | You → Claude messages | Included in main setup |
| context-sync | Confluence/JIRA sync | Included in main setup |
| github-sync | GitHub PR data sync | Included in main setup |
| codebase-analyzer | Weekly code analysis | Included in main setup |
| conversation-analyzer | Daily conversation analysis | Included in main setup |

## See Also

- [Main README](../../README.md) - Project overview and quick start
- [Architecture](../architecture/) - System design
- [Reference](../reference/) - Quick reference guides
