# User-Facing CLI Tools

This directory contains all user-facing command-line tools for james-in-a-box.

## Available Commands

### analyzer-ctl
Manage the codebase analyzer systemd service.
```bash
bin/analyzer-ctl check          # Check requirements
bin/analyzer-ctl install        # Install service
bin/analyzer-ctl enable         # Enable and start
bin/analyzer-ctl status         # Check status
```

### conversation-analyzer-ctl
Manage the conversation analyzer systemd service.
```bash
bin/conversation-analyzer-ctl check    # Check requirements
bin/conversation-analyzer-ctl install  # Install service
bin/conversation-analyzer-ctl enable   # Enable and start
```

### context-watcher-ctl
Manage the context watcher service.
```bash
bin/context-watcher-ctl start   # Start watcher
bin/context-watcher-ctl stop    # Stop watcher
bin/context-watcher-ctl status  # Check status
```

### host-notify-ctl
Manage the Slack notification service.
```bash
bin/host-notify-ctl start    # Start notifier
bin/host-notify-ctl stop     # Stop notifier
bin/host-notify-ctl status   # Check status
```

### host-receive-ctl
Manage the Slack message receiver service.
```bash
bin/host-receive-ctl start   # Start receiver
bin/host-receive-ctl stop    # Stop receiver
bin/host-receive-ctl status  # Check status
```

### view-logs
View logs from various james-in-a-box components.
```bash
bin/view-logs               # Interactive log viewer
bin/view-logs tracking      # View tracking logs
bin/view-logs conversations # View conversation logs
```

## See Also
- [Installation Guide](../docs/setup/)
- [User Guide](../docs/user-guide/)
- [Systemd Services](../systemd/)
