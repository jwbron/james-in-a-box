# Installation Scripts

Scripts for initial setup and configuration of james-in-a-box.

## Scripts

### setup-host-notifier.sh
Sets up the Slack notification system on the host machine.

**Usage:**
```bash
./install/setup-host-notifier.sh
```

**What it does:**
- Configures Slack API credentials
- Sets up systemd services for host-side Slack integration
- Creates necessary directories and persistent data structure
- Tests the connection
- Configures the conversation analyzer and context watcher services

**Prerequisites:**
- Slack app created with bot token and app token
- Docker installed
- Systemd available

**Components installed:**
- Host Slack notifier (outbound notifications)
- Host Slack receiver (inbound messages)
- Conversation analyzer (periodic analysis with Slack notifications)
- Context watcher (monitors conversation context files)

## See Also
- [Setup Guide](../docs/setup/slack-quickstart.md)
- [Slack App Setup](../docs/setup/slack-app-setup.md)
- [Host Slack Notifier Architecture](../docs/architecture/host-slack-notifier.md)
- [Integration Summary](../docs/architecture/integration-summary.md)
