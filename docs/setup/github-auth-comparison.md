# GitHub Authentication: App vs Personal Access Token

This document explains the differences between GitHub App authentication and Personal Access Tokens (PATs) for james-in-a-box.

## Summary

**Both GitHub App and PAT authentication are supported.** However, GitHub Apps are required for certain operations that PATs cannot perform.

## Authentication Methods

### Personal Access Token (PAT)

**What it is:** A user-level token that grants permissions based on your personal GitHub account.

**Supported operations:**
- ✅ Clone repositories
- ✅ Push commits
- ✅ Create pull requests
- ✅ Comment on PRs
- ✅ Trigger workflows
- ✅ Read repository contents
- ❌ **Cannot read PR check runs** (requires GitHub App)

**When to use:**
- Personal projects
- Simple setups
- You don't need PR check status monitoring

**Setup:**
1. Go to https://github.com/settings/tokens
2. Create a token with:
   - **Read/write repos:** `repo` (full scope), `workflow`
   - **Read-only repos:** `repo` (read-only)
3. Use token in setup: `GITHUB_TOKEN=ghp_...`

### GitHub App

**What it is:** An application-level token that grants permissions to specific repositories independent of user accounts.

**Supported operations:**
- ✅ All PAT operations (clone, push, PRs, comments, workflows)
- ✅ **Read PR check runs** (via GitHub Checks API)
- ✅ Team collaboration (not tied to a single user)
- ✅ Fine-grained repository permissions

**When to use:**
- Team projects
- You need token auto-refresh (github-token-refresher service)
- Fine-grained permission control
- Production deployments

**Setup:**
See [github-app-setup.md](github-app-setup.md) for detailed instructions.

## Authentication Usage Audit

### Where PATs are used:

1. **Container authentication** (`jib` script, `entrypoint.py`)
   - Sets `GITHUB_TOKEN` environment variable
   - Configures `gh` CLI
   - Configures git credential helper

2. **Read-only monitoring** (`github_readonly_token` in `host_config.py`)
   - For repositories where jib only watches but doesn't write
   - Falls back to `GITHUB_TOKEN` if not set

3. **All write operations** (PRs, commits, comments)
   - Uses `GITHUB_TOKEN` from environment or config

### Where GitHub Apps are required:

1. **Token auto-refresh** (`github-token-refresher.py`)
   - GitHub App tokens expire after 1 hour
   - Service auto-refreshes tokens every 45 minutes
   - Not needed for PATs (they don't expire automatically)

2. **Fine-grained repository permissions**
   - GitHub Apps can be installed on specific repositories
   - Better security model for team environments

## Recommendations

### For Personal Use
```bash
# Use PAT if you don't need PR check monitoring
GITHUB_TOKEN=ghp_... (read/write)
GITHUB_READONLY_TOKEN=ghp_... (optional, for external repos)
```

### For Team Use
```bash
# Use GitHub App for full functionality
# Configure via setup.py option 1
# Tokens auto-refresh via github-token-refresher service
```

### Hybrid Setup (Current Implementation)
```bash
# You can mix both:
# 1. GitHub App for repositories where you want check monitoring
# 2. PAT for repositories where you only need basic operations

# Both authentication methods work side-by-side
# The system will use GitHub App tokens when available,
# fall back to PAT otherwise
```

## Technical Details

### Token Precedence (in `host_config.py`)

Tokens are loaded in this order (first found wins):

1. `GITHUB_TOKEN` environment variable
2. `~/.config/jib/secrets.env` - `GITHUB_TOKEN`
3. `~/.config/jib/github-token` - Plain text file
4. `~/.jib-sharing/.github-token` - JSON from github-token-refresher (GitHub App)

### Why PATs Can't Access Check Runs

The GitHub Checks API requires:
- `checks:read` permission (only available to GitHub Apps)
- PATs use OAuth scopes which don't include check runs access

From GitHub's documentation:
> "The Checks API is only available to GitHub Apps. OAuth Apps and authenticated users cannot access this endpoint."

## Migration Path

If you're currently using PATs and want PR check monitoring:

1. Set up a GitHub App (see [github-app-setup.md](github-app-setup.md))
2. Configure App credentials in `~/.config/jib/`:
   - `github-app-id`
   - `github-app-installation-id`
   - `github-app-private-key.pem`
3. Enable `github-token-refresher` service: `./setup.py --enable jib-github-token-refresher.service`
4. Keep your PAT as `GITHUB_READONLY_TOKEN` for external repos (optional)

The system will automatically use the GitHub App for repositories where it's installed, and fall back to PAT for others.

## Related Documentation

- [GitHub App Setup](github-app-setup.md)
- [Host Configuration](../../config/README.md)
