# Configuration

Configuration files for james-in-a-box security, filtering, and monitoring.

## repositories.yaml (NEW - Source of Truth for Repo Access)

**Single source of truth** for which GitHub repositories jib has read/write access to.

This file controls:
- Which repos jib can respond to comments on
- Which repos jib can push changes to
- Which repos jib can create PRs in
- Default reviewer for PRs
- GitHub sync configuration

**Usage:**
- Python: `from config.repo_config import get_writable_repos, is_writable_repo`
- CLI: `python config/repo_config.py --list-writable`
- PR Helper: `create-pr-helper.py --list-writable`

**To add a new repo with write access:**
1. Edit `repositories.yaml` and add to `writable_repos` list
2. Reload github-sync service: `systemctl --user daemon-reload && systemctl --user restart github-sync.timer`

## context-filters.yaml

Controls which Confluence spaces, JIRA projects, and repositories are synced.

**Phase 1 (Current)**: MEDIUM risk - Human review + filtering
**Phase 3 (Target)**: LOW risk - DLP scanning + output monitoring

See file for detailed allowlists and blocked patterns.
