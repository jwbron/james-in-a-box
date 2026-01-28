# GitHub Integration Features

GitHub integration for command handling and PR workflows.

## Overview

JIB supports GitHub operations through:
- **Command handling**: Process GitHub commands from Slack
- **Token management**: Secure GitHub App authentication
- **PR workflows**: Create and manage pull requests

## Repository Access Levels

JIB supports two access levels for repositories:

### Writable Repos (Full Access)
Repositories where jib has write access via GitHub App:
- Creates PRs, pushes fixes, posts comments
- Full git operations through gateway sidecar

### Read-Only Repos (PAT Access)
Repositories where jib only has read access via Personal Access Token (PAT):
- Can read code and PRs
- Cannot push code, create PRs, or post comments

## Authentication

JIB supports **separate tokens** for writable and readable repositories, providing
security through the principle of least privilege.

### Token Configuration

Configure tokens in `~/.config/jib/secrets.env`:

```bash
# For writable repos: Use GitHub App (recommended) or PAT with write access
# GitHub App is auto-configured via setup - see docs/setup/github-app-setup.md
GITHUB_TOKEN="ghp_your_write_token_here"

# For read-only repos: Separate PAT with only read permissions (optional)
# Falls back to GITHUB_TOKEN if not set
GITHUB_READONLY_TOKEN="ghp_your_readonly_token_here"
```

### Token Selection Logic

When accessing a repository, JIB automatically selects the appropriate token:

| Repo Type | Token Used |
|-----------|------------|
| Writable repo | `GITHUB_TOKEN` (or GitHub App token) |
| Readable repo | `GITHUB_READONLY_TOKEN` (falls back to `GITHUB_TOKEN`) |
| Unknown repo | `GITHUB_TOKEN` |

Configure access levels in `config/repositories.yaml`:
```yaml
# Full access repos (GitHub App)
writable_repos:
  - owner/repo-name

# Read-only repos (PAT only)
readable_repos:
  - external/repo-name
```

**Note**: If a repo appears in both lists, it's treated as writable.

## Features

### GitHub Command Handler

**Purpose**: Processes user commands received via Slack for GitHub operations like 'review PR 123' or '/pr review 123 webapp'. Parses commands and delegates to appropriate handlers.

**Location**:
- `jib-container/jib-tasks/github/command-handler.py`
- `jib-container/jib-tasks/github/README.md`

### GitHub Processor

**Purpose**: Container-side processor for GitHub-related tasks triggered via Slack commands.

**Location**:
- `jib-container/jib-tasks/github/github-processor.py`
- `jib-container/jib-tasks/github/README.md`

### GitHub App Token Generator

**Purpose**: Generates short-lived (1 hour) GitHub App installation access tokens from stored credentials. Used by jib launcher to authenticate gh CLI and git operations without SSH keys.

**Location**: `jib-container/jib-tools/github-app-token.py`

## Related Documentation

- [GitHub App Setup](../setup/github-app-setup.md)
- [Gateway Sidecar](../../gateway-sidecar/README.md)

## Source Files

| Component | Path |
|-----------|------|
| GitHub Command Handler | `jib-container/jib-tasks/github/command-handler.py` |
| GitHub Processor | `jib-container/jib-tasks/github/github-processor.py` |
| GitHub App Token Generator | `jib-container/jib-tools/github-app-token.py` |

---

*Last updated: 2026-01-28*
