# Configuration

Configuration for james-in-a-box (jib). There are two types of config:

1. **In-repo configs** (this directory) - Version-controlled, non-secret settings
2. **Host configs** (`~/.config/jib/`) - User-specific settings and secrets

## Host Configuration (Consolidated)

All host-side configuration is consolidated under `~/.config/jib/`:

```
~/.config/jib/
├── config.yaml        # Non-secret settings (Slack channel, sync intervals, etc.)
├── secrets.env        # All secrets (Slack, GitHub, Confluence, JIRA tokens)
├── github-token       # GitHub token (dedicated file)
└── repositories.yaml  # Repository access configuration (copied from repo)
```

**Migration from legacy locations:**
Run manual migration if you have existing configs:
```bash
python3 config/host_config.py --migrate
```

This migrates from:
- `~/.config/jib-notifier/config.json` → `~/.config/jib/`
- `~/.config/context-sync/.env` → `~/.config/jib/secrets.env`

**Usage:**
```python
from config.host_config import HostConfig

config = HostConfig()
slack_token = config.get_secret('SLACK_TOKEN')
slack_channel = config.get('slack_channel')
```

**CLI:**
```bash
python config/host_config.py                   # Show config status
python config/host_config.py --list            # Show non-secret config
python config/host_config.py --list-secrets    # Show secret keys (values hidden)
python config/host_config.py --migrate         # Migrate from legacy locations
```

**Templates:**
- `config/host-config.template.yaml` - Non-secret settings template
- `config/secrets.template.env` - Secrets template

## repositories.yaml (Source of Truth for Repo Access)

**Single source of truth** for which GitHub repositories jib has read/write access to.

This file is copied to `~/.config/jib/repositories.yaml` during setup.

This file controls:
- Which repos jib can respond to comments on
- Which repos jib can push changes to
- Which repos jib can create PRs in
- Default reviewer for PRs
- GitHub sync configuration

**Usage:**
- Python: `from config.repo_config import get_writable_repos, is_writable_repo`
- CLI: `python config/repo_config.py --list-writable`

**To add a new repo with write access:**
1. Edit `repositories.yaml` and add to `writable_repos` list
2. Reload github-sync service: `systemctl --user daemon-reload && systemctl --user restart github-sync.timer`

## context-filters.yaml

Controls which Confluence spaces, JIRA projects, and repositories are synced.

**Phase 1 (Current)**: MEDIUM risk - Human review + filtering
**Phase 3 (Target)**: LOW risk - DLP scanning + output monitoring

See file for detailed allowlists and blocked patterns.
