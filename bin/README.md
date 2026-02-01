# bin/

Convenient symlinks to commonly used commands.

## Commands

### Container

- `jib` - Start/manage jib container
- `docker-setup.py` - Container setup (runs automatically)
- `jib-logs` - View container logs

### Setup Scripts

Install services/timers with these scripts:

- `setup-gateway-sidecar` - Install gateway sidecar service
- `setup-slack-notifier` - Install Slack notifier service
- `setup-slack-receiver` - Install Slack receiver service

### Utilities

- `discover-tests` - Discover test frameworks and commands in a codebase

## Note

These are symlinks to the actual files in `host-services/` and `jib-container/`.
The real files live with their respective services for better organization.

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
