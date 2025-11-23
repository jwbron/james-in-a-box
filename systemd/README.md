# Systemd Services

All systemd service and timer units for james-in-a-box.

## Organization

Services are organized by component:

- **analyzers/** - Automated code analysis services
- **slack-notifier/** - Slack integration services  
- **context-watcher/** - File watching and context management

## Installing Services

Each subdirectory has its own README with specific installation instructions.

General pattern:
```bash
# Copy service files
cp systemd/component/*.service ~/.config/systemd/user/
cp systemd/component/*.timer ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable and start
systemctl --user enable --now service-name.timer
```

## Managing Services

### Check Status
```bash
systemctl --user status service-name
systemctl --user list-timers  # See all timers
```

### View Logs
```bash
journalctl --user -u service-name -f
```

### Start/Stop
```bash
systemctl --user start service-name
systemctl --user stop service-name
systemctl --user restart service-name
```

## Available Services

See subdirectory READMEs for details:
- [Analyzers](analyzers/README.md)
- [Slack Notifier](slack-notifier/README.md)
- [Context Watcher](context-watcher/README.md)
