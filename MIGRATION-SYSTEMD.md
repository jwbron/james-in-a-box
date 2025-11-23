# Migration Guide: Systemd Service Management

The deprecated `*-ctl` control scripts have been removed. All host services are now managed exclusively via systemd.

## On Host Machine

### 1. Stop any running control scripts

If you have any `*-ctl` scripts running in the background, stop them:

```bash
# Check for any running processes (optional)
ps aux | grep -E "(host-notify-ctl|host-receive-ctl|analyzer-ctl)" | grep -v grep

# Kill if found (they'll be replaced by systemd services)
pkill -f "host-notify-ctl"
pkill -f "host-receive-ctl"
pkill -f "analyzer-ctl"
pkill -f "conversation-analyzer-ctl"
```

### 2. Install/Update systemd services

The services may already be installed. If not, install them:

```bash
cd ~/khan/james-in-a-box

# Install slack-receiver service (NEW)
cd components/slack-receiver
./setup.sh
cd ../..

# Verify all services are installed
ls ~/.config/systemd/user/*.service | grep -E "(slack|analyzer|service-failure)"
```

You should see:
- `slack-notifier.service`
- `slack-receiver.service` (newly added)
- `codebase-analyzer.service`
- `conversation-analyzer.service`
- `service-failure-notify@.service`

### 3. Restart services with new threading support

The slack-notifier and slack-receiver have been updated with threading support:

```bash
# Restart slack services to pick up threading changes
systemctl --user restart slack-notifier.service
systemctl --user restart slack-receiver.service

# Verify they're running
systemctl --user status slack-notifier.service
systemctl --user status slack-receiver.service
```

### 4. Verify all services are running

```bash
# Check all JIB services
systemctl --user status slack-notifier.service
systemctl --user status slack-receiver.service
systemctl --user status codebase-analyzer.service
systemctl --user status conversation-analyzer.service

# Check timers are active
systemctl --user list-timers | grep -E "(codebase|conversation)"
```

### 5. Remove old control script references (optional cleanup)

If you had any cron jobs or startup scripts calling the old `*-ctl` commands, remove them:

```bash
# Check crontab
crontab -l | grep -E "(host-notify-ctl|host-receive-ctl|analyzer-ctl)"

# If found, edit and remove
crontab -e
```

## New Service Management Commands

From now on, use these systemctl commands:

### Check Status
```bash
systemctl --user status slack-notifier.service
systemctl --user status slack-receiver.service
systemctl --user status codebase-analyzer.service
systemctl --user status conversation-analyzer.service
```

### Restart Services
```bash
systemctl --user restart slack-notifier.service
systemctl --user restart slack-receiver.service
```

### View Logs
```bash
# Follow live logs
journalctl --user -u slack-notifier.service -f

# View recent logs
journalctl --user -u slack-notifier.service -n 50

# All JIB services
journalctl --user -u slack-notifier.service -u slack-receiver.service -u codebase-analyzer.service -f
```

### Stop/Start Services
```bash
systemctl --user stop slack-notifier.service
systemctl --user start slack-notifier.service
```

### Enable/Disable Auto-start
```bash
# Enable (start on boot)
systemctl --user enable slack-notifier.service

# Disable
systemctl --user disable slack-notifier.service
```

## Verification Checklist

- [ ] Old `*-ctl` processes killed
- [ ] All systemd services installed (5 services)
- [ ] slack-notifier.service running
- [ ] slack-receiver.service running
- [ ] codebase-analyzer timer active
- [ ] conversation-analyzer timer active
- [ ] Logs show no errors: `journalctl --user -u slack-notifier.service -n 20`

## Troubleshooting

**Service won't start:**
```bash
# Check detailed status
systemctl --user status slack-notifier.service -l

# Check logs for errors
journalctl --user -u slack-notifier.service -n 50

# Reload systemd configuration
systemctl --user daemon-reload
systemctl --user restart slack-notifier.service
```

**Missing service file:**
```bash
# Reinstall from setup script
cd ~/khan/james-in-a-box/components/slack-notifier
./setup.sh
```

**Logs not showing:**
```bash
# Ensure service is using journal
systemctl --user cat slack-notifier.service | grep -E "(StandardOutput|StandardError)"
# Should show: StandardOutput=journal, StandardError=journal
```

## What Changed

1. **Removed**: All `*-ctl` control scripts (host-notify-ctl, host-receive-ctl, analyzer-ctl, conversation-analyzer-ctl)
2. **Added**: slack-receiver.service (previously only had control script)
3. **Updated**: Slack threading support in notifier and receiver
4. **Standardized**: All services use systemd exclusively

## Benefits

- **Consistent management**: All services managed the same way
- **Better logging**: Centralized logs via journalctl
- **Auto-restart**: Services automatically restart on failure
- **System integration**: Proper systemd service lifecycle management
