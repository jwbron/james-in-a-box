# bin/

Convenient symlinks to commonly used commands.

## Commands

**Container:**
- `jib` - Start/manage JIB container
- `docker-setup.py` - Container setup
- `view-logs` - View container logs

**Host Services:**
- `host-notify-ctl` - Slack notifier control
- `host-receive-ctl` - Slack receiver control
- `analyzer-ctl` - Codebase analyzer control
- `conversation-analyzer-ctl` - Conversation analyzer control

**Setup:**
- `setup-slack-notifier` - Install Slack notifier
- `setup-slack-receiver` - Install Slack receiver
- `setup-service-monitor` - Install service monitor
- `setup-codebase-analyzer` - Install codebase analyzer

## Note

These are symlinks to the actual files in `components/` and `jib-container/`.
The real files live with their components for better organization.

## Service Management

All host services are managed via systemd. Use `systemctl --user` commands:

```bash
# Check status of any service
systemctl --user status slack-notifier.service
systemctl --user status slack-receiver.service

# Restart a service
systemctl --user restart slack-notifier.service

# View logs
journalctl --user -u slack-notifier.service -f
```

The `*-ctl` scripts are legacy and deprecated. Use systemctl instead.
