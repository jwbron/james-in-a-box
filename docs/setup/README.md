# Setup Guides

Installation and configuration documentation.

## Quick Start

Run the main setup script to configure everything:

```bash
cd ~/khan/james-in-a-box
./setup.sh
```

This single command handles:
- Host service installation (Slack, GitHub watcher, context sync, etc.)
- Configuration validation (Slack tokens, GitHub auth)
- Docker image building
- All component setup

**Important:** `./setup.sh` is the primary and only setup command you need. The `jib --setup` command only handles Docker mounts and is called automatically by setup.sh.

## Setup Requirements

Before running setup, you'll need:

1. **Slack App** (required for notifications)
   - See [Slack App Setup](slack-app-setup.md) for instructions
   - You'll need: Bot Token (xoxb-...) and App Token (xapp-...)

2. **GitHub App** (required for PR creation)
   - See [GitHub App Setup](github-app-setup.md) for instructions
   - Alternative: Personal Access Token (PAT)

3. **Prerequisites**
   - Docker installed and running
   - Python 3 installed
   - Go installed (for beads task tracker)

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

1. **Create Slack App** - [Slack app setup](slack-app-setup.md) (get tokens first)
2. **Run Setup** - `./setup.sh` (interactive, validates and installs everything)
3. **Verify** - Check services with `systemctl --user status slack-notifier slack-receiver`

## Configuration Location

All configuration is stored in `~/.config/jib/`:

| File | Purpose |
|------|---------|
| `secrets.env` | Slack tokens, GitHub PAT, API keys |
| `github-app-id` | GitHub App ID |
| `github-app-installation-id` | GitHub App Installation ID |
| `github-app.pem` | GitHub App private key |
| `repositories.yaml` | Repository access configuration |

## Service Overview

| Service | Purpose | Setup |
|---------|---------|-------|
| slack-notifier | Claude → You notifications | Included in main setup |
| slack-receiver | You → Claude messages | Included in main setup |
| context-sync | Confluence/JIRA sync | Included in main setup |
| github-watcher | GitHub PR/issue monitoring | Included in main setup |
| github-token-refresher | Auto-refresh GitHub App tokens | Included in main setup |
| worktree-watcher | Cleanup orphaned worktrees | Included in main setup |
| conversation-analyzer | Daily conversation analysis | Included in main setup |
| doc-generator | Weekly documentation updates | Included (optional enable) |
| index-generator | Codebase indexing | Included (optional enable) |

## Updating jib

To update after code changes:

```bash
./setup.sh --update
```

This reloads all service configurations and restarts services.

## Troubleshooting

### Setup fails with missing Slack tokens
1. Create a Slack app at https://api.slack.com/apps
2. Follow [Slack App Setup](slack-app-setup.md)
3. Add tokens to `~/.config/jib/secrets.env`
4. Run `./setup.sh` again

### Services not starting
```bash
# Check service status
systemctl --user status slack-notifier slack-receiver

# View logs
journalctl --user -u slack-notifier.service -f
```

### Docker image build fails
```bash
# Try building manually
bin/jib --setup

# Or reset and rebuild
bin/jib --reset
./setup.sh
```

## See Also

- [Main README](../../README.md) - Project overview and quick start
- [Architecture](../architecture/) - System design
- [Reference](../reference/) - Quick reference guides
