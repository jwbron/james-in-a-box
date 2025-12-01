# bin/

Convenient symlinks to commonly used commands.

## Commands

**Container:**
- `jib` - Start/manage jib container
- `docker-setup.py` - Container setup (runs automatically)
- `view-logs` - View container logs

**Documentation:**
- `generate-docs` - Generate documentation from code patterns
- `check-doc-drift` - Detect documentation drift from code
- `adr-researcher` - Research-based ADR workflow tool (Phase 6)
- `setup-doc-generator` - Install weekly doc generation timer

**Setup Scripts:**
- `setup-slack-notifier` - Install Slack notifier service
- `setup-slack-receiver` - Install Slack receiver service
- `setup-conversation-analyzer` - Install conversation analyzer timer

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
