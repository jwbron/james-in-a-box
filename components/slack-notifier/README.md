# Slack Notifier Component

Sends notifications from james-in-a-box to Slack.

## Overview

Watches `~/.jib-sharing/notifications/` and posts new files to Slack as formatted messages.

## Files

- `manage_notifier.sh` - Control script (deprecated, use `bin/host-notify-ctl`)
- `requirements.txt` - Python dependencies
- `slack-app-manifest.yaml` - Slack app configuration template

## Quick Start

1. **Set up Slack app**: See [Slack App Setup](../../docs/setup/slack-app-setup.md)
2. **Install service**: `bin/host-notify-ctl install`
3. **Start**: `bin/host-notify-ctl start`

## Configuration

Requires Slack bot token in one of:
- Environment: `export SLACK_TOKEN="xoxb-..."`
- Config file: `~/.jib-notify/config.json`

## How It Works

1. Watches: `~/.jib-sharing/notifications/`
2. Detects: New `.md` files
3. Formats: Converts markdown to Slack blocks
4. Posts: Sends to configured channel
5. Archives: Moves processed files

## See Also

- [Setup Guide](../../docs/setup/slack-quickstart.md)
- [Quick Reference](../../docs/reference/slack-quick-reference.md)
- [Systemd Service](../../systemd/slack-notifier/)
