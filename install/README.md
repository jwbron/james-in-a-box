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
- Sets up systemd service
- Creates necessary directories
- Tests the connection

**Prerequisites:**
- Slack app created with bot token
- Docker installed
- Systemd available

### fix-host-credentials.sh
Fixes credential-related issues with Slack integration.

**Usage:**
```bash
./install/fix-host-credentials.sh
```

**What it does:**
- Validates Slack credentials
- Repairs configuration files
- Resets permissions
- Restarts services if needed

## See Also
- [Setup Guide](../docs/setup/slack-quickstart.md)
- [Slack App Setup](../docs/setup/slack-app-setup.md)
- [Troubleshooting](../docs/reference/)
