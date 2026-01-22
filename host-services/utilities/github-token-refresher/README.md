# GitHub Token Refresher

Automatically refreshes GitHub App installation tokens for jib containers.

## Problem

GitHub App installation tokens expire after 1 hour. Long-running containers that rely on
the token passed at startup will fail GitHub operations after the token expires.

## Solution

This timer-triggered service runs on the **host** and:
1. Generates a fresh token every 30 minutes (before the 1-hour expiry)
2. Writes the token to `~/.jib-gateway/.github-token` (accessible only to the gateway sidecar)
3. The gateway sidecar provides tokens to containers on-demand via authenticated API
4. Uses systemd timer with `Persistent=true` to handle system suspend/hibernate correctly

## Token File Format

The token file (`~/.jib-gateway/.github-token`) is JSON:

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
cd ~/khan/james-in-a-box/host-services/utilities/github-token-refresher
./setup.sh
```

## Prerequisites

GitHub App credentials must be configured in `~/.config/jib/`:
- `github-app-id` - Numeric App ID
- `github-app-installation-id` - Numeric Installation ID
- `github-app.pem` - Private key file

See `docs/setup/github-app-setup.md` for instructions.

## Container Integration

Both `git` and `gh` use wrapper scripts that read the fresh token from the shared file:

### Git Credential Helper

The git credential helper (`jib-container/scripts/git-credential-github-token`) reads
from the token file first, falling back to the `GITHUB_TOKEN` env var:

```bash
# Priority:
# 1. ~/sharing/.github-token file (refreshed by this service)
# 2. GITHUB_TOKEN environment variable (set at container start)
```

### gh CLI Wrapper

The gh wrapper (`jib-container/scripts/gh`) sets `GH_TOKEN` from the token file:

```bash
# Priority:
# 1. ~/sharing/.github-token file (refreshed by this service)
# 2. GITHUB_TOKEN environment variable (set at container start)
```

Both wrappers are installed via symlinks in `/opt/jib-runtime/jib-container/bin/`
which is on the PATH before `/usr/bin/`, so they intercept the real commands.

## Manual Operations

```bash
# Check timer status
systemctl --user status github-token-refresher.timer

# See when next run is scheduled
systemctl --user list-timers github-token-refresher.timer

# View logs
journalctl --user -u github-token-refresher -f

# Force immediate refresh
systemctl --user start github-token-refresher.service

# View current token info (without exposing the token)
cat ~/.jib-gateway/.github-token | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Expires: {d[\"expires_at\"]}')"
```

## Architecture

```
Host                                 Container
┌─────────────────────────┐         ┌─────────────────────────┐
│ github-token-refresher  │         │                         │
│ (systemd timer)         │         │  git/gh wrappers call   │
│                         │         │  gateway sidecar API    │
│ Every 30 min:           │         │                         │
│ 1. Generate token       │         │                         │
│ 2. Write to gateway dir │         │                         │
│                         │         │                         │
│ ~/.jib-gateway/         │         │                         │
│   .github-token         │         │                         │
└──────────┬──────────────┘         └───────────┬─────────────┘
           │                                    │
           │    ┌─────────────────────────┐     │
           └────│    gateway-sidecar      │─────┘
                │                         │
                │ Reads token from file   │
                │ Serves to containers    │
                │ via authenticated API   │
                └─────────────────────────┘
```

The timer uses `Persistent=true` to ensure missed runs (e.g., during suspend)
are executed immediately on resume.
