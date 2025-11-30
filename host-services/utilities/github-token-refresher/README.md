# GitHub Token Refresher

Automatically refreshes GitHub App installation tokens for jib containers.

## Problem

GitHub App installation tokens expire after 1 hour. Long-running containers that rely on
the token passed at startup will fail GitHub operations after the token expires.

## Solution

This service runs on the **host** and:
1. Generates a fresh token every 45 minutes (before the 1-hour expiry)
2. Writes the token to `~/.jib-sharing/.github-token` (a shared file accessible to containers)
3. Containers read from this file instead of relying on the initial env var

## Token File Format

The token file (`~/.jib-sharing/.github-token`) is JSON:

```json
{
  "token": "ghs_...",
  "generated_at": "2024-01-15T10:30:00+00:00",
  "expires_at_unix": 1705315800,
  "expires_at": "2024-01-15T11:30:00+00:00",
  "generated_by": "github-token-refresher",
  "validity_seconds": 3600
}
```

## Installation

```bash
cd ~/workspace/james-in-a-box/host-services/utilities/github-token-refresher
./setup.sh
```

## Prerequisites

GitHub App credentials must be configured in `~/.config/jib/`:
- `github-app-id` - Numeric App ID
- `github-app-installation-id` - Numeric Installation ID
- `github-app.pem` - Private key file

See `docs/setup/github-app-setup.md` for instructions.

## Container Integration

### Git Credential Helper

The git credential helper (`jib-container/scripts/git-credential-github-token`) reads
from the token file first, falling back to the `GITHUB_TOKEN` env var:

```bash
# Priority:
# 1. ~/sharing/.github-token file (refreshed by this service)
# 2. GITHUB_TOKEN environment variable (set at container start)
```

### MCP Server

The container includes a token watcher script that:
1. Monitors `~/sharing/.github-token` for changes
2. Reconfigures the GitHub MCP server with the new token
3. Runs automatically in the background

## Manual Operations

```bash
# Check service status
systemctl --user status github-token-refresher

# View logs
journalctl --user -u github-token-refresher -f

# Force immediate refresh
~/.jib-sharing/.github-token-refresher/github-token-refresher.py --once

# View current token info (without exposing the token)
cat ~/.jib-sharing/.github-token | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Expires: {d[\"expires_at\"]}')"
```

## Architecture

```
Host                                 Container
┌─────────────────────────┐         ┌─────────────────────────┐
│ github-token-refresher  │         │                         │
│                         │         │  git credential helper  │
│ Every 45 min:           │         │  reads from:            │
│ 1. Generate token       │         │  1. ~/sharing/.github-  │
│ 2. Write to shared file │─────────│     token (preferred)   │
│                         │         │  2. $GITHUB_TOKEN       │
│ ~/.jib-sharing/         │         │     (fallback)          │
│   .github-token         │         │                         │
└─────────────────────────┘         │  MCP token watcher      │
                                    │  reconfigures MCP when  │
                                    │  token file changes     │
                                    └─────────────────────────┘
```
