# bin/

Convenient symlinks to commonly used commands.

## Maintaining Symlinks

Run `maintain-bin-symlinks` to automatically create/update all symlinks:

```bash
./maintain-bin-symlinks           # Apply changes
./maintain-bin-symlinks --dry-run # Preview changes
./maintain-bin-symlinks --verbose # Show all symlinks
```

Add new commands by editing the `SYMLINKS` array in `maintain-bin-symlinks`.

## Commands

### Container

- `jib` - Start/manage jib container
- `docker-setup.py` - Container setup (runs automatically)
- `jib-logs` - View container logs

### Analysis Tools

- `adr-researcher` - Research-based ADR workflow tool
- `analyze-pr` - Analyze pull requests
- `beads-analyzer` - Analyze beads task tracking metrics
- `check-doc-drift` - Detect documentation drift from code
- `feature-analyzer` - Sync documentation with implemented ADRs
- `fix-doc-links` - Fix broken documentation links
- `generate-docs` - Generate documentation from code patterns
- `github-watcher` - Monitor GitHub for PR/issue activity
- `index-generator` - Generate machine-readable codebase indexes
- `inefficiency-report` - Generate weekly inefficiency reports
- `query-index` - Query codebase indexes
- `spec-enricher` - Enrich task specs with documentation links

### Setup Scripts

Install services/timers with these scripts:

- `setup-beads-analyzer` - Install beads analyzer timer
- `setup-doc-generator` - Install weekly doc generation timer
- `setup-feature-analyzer` - Install feature analyzer watcher/timer
- `setup-github-token-refresher` - Install GitHub token refresh service
- `setup-github-watcher` - Install GitHub watcher timer
- `setup-index-generator` - Install index generator timer
- `setup-inefficiency-detector` - Install inefficiency reporter timer
- `setup-slack-notifier` - Install Slack notifier service
- `setup-slack-receiver` - Install Slack receiver service
- `setup-spec-enricher` - Install spec enricher
- `setup-trace-collector` - Install trace collector hooks
- `setup-worktree-watcher` - Install worktree cleanup timer

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
