# GitHub Auth in Long-Running Containers

## Problem Statement

Long-running containers lose GitHub access after approximately 1 hour. Users see errors like:
- `Incompatible auth server: does not support dynamic client registration`
- `HTTP 401: Bad credentials`
- `403 Resource not accessible by integration`

## Root Cause Analysis

### Token Lifecycle

1. **Token Generation**: The `jib` launcher generates a GitHub App installation token at container startup
2. **Token Validity**: GitHub App installation tokens expire after **1 hour**
3. **Token Storage**: Token is written to `~/sharing/.github-token` (JSON format)
4. **MCP Configuration**: The GitHub MCP server is configured with the initial token

### The Problem

The MCP server is configured at container startup with the initial `GITHUB_TOKEN` environment variable. When this token expires, the MCP server continues using the stale token, causing auth failures.

### Existing Infrastructure

The system has infrastructure to handle token refresh, but there are gaps:

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| `github-token-refresher` | Host service | Refreshes token every 45 min | Installed via `setup.sh` |
| `mcp-token-watcher` | Container script | Watches token file, reconfigures MCP | Runs in background |
| Token file | `~/sharing/.github-token` | Shared token storage | Updated by host service |

### Identified Issues

#### Issue 1: Hash Algorithm Mismatch

The entrypoint script (Dockerfile) uses **md5sum** for token hash caching:
```bash
TOKEN_HASH=$(echo -n "${CURRENT_TOKEN}" | md5sum | cut -d' ' -f1)
```

But `mcp-token-watcher.py` uses **sha256** truncated to 16 characters:
```python
return hashlib.sha256(token_data["token"].encode()).hexdigest()[:16]
```

This means the cache comparison never matches correctly.

#### Issue 2: MCP Token Watcher Not Running in `jib --exec` Containers

The MCP token watcher daemon only starts in interactive containers (when launched with no arguments). Containers started via `jib --exec` don't run the watcher daemon.

PR #271 added a call to `mcp-token-watcher.py --once` in `incoming-processor.py`, but this only helps Slack message processing, not other `jib --exec` use cases.

#### Issue 3: Host Service May Not Be Running

The `github-token-refresher` service on the host needs to be running for the token file to stay fresh. If it's not running, the token file gets stale.

## Diagnosis Steps

### 1. Check Token File Validity

```bash
# In container
cat ~/sharing/.github-token | python3 -c "
import json,sys
from datetime import datetime, timezone
d = json.load(sys.stdin)
now = datetime.now(timezone.utc).timestamp()
expires = d['expires_at_unix']
print(f'Token expires: {d[\"expires_at\"]}')
print(f'Time until expiry: {(expires - now)/60:.1f} minutes')
print('STATUS: ' + ('VALID' if now < expires else 'EXPIRED'))
"
```

### 2. Check Host Service Status

```bash
# On host (not in container)
systemctl --user status github-token-refresher
journalctl --user -u github-token-refresher -f
```

### 3. Manually Refresh MCP Token

```bash
# In container
python3 ~/khan/james-in-a-box/jib-container/scripts/mcp-token-watcher.py --once -v
```

### 4. Test GitHub Token Directly

```bash
# In container
TOKEN=$(cat ~/sharing/.github-token | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/installation/repositories | head -10
```

## Solutions

### Immediate Fix (Manual)

If you're experiencing auth issues in a running container:

```bash
python3 ~/khan/james-in-a-box/jib-container/scripts/mcp-token-watcher.py --force
```

### Permanent Fix

1. **Ensure host service is running**:
   ```bash
   # On host
   systemctl --user enable github-token-refresher
   systemctl --user start github-token-refresher
   ```

2. **Re-run setup.sh** if the service isn't installed:
   ```bash
   cd ~/khan/james-in-a-box
   ./setup.sh --update
   ```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                           HOST                                   │
├─────────────────────────────────────────────────────────────────┤
│  github-token-refresher (systemd service)                        │
│  ├─ Runs every 45 minutes                                       │
│  ├─ Generates new GitHub App installation token                 │
│  └─ Writes to ~/.jib-sharing/.github-token                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Mounted as ~/sharing/
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         CONTAINER                                │
├─────────────────────────────────────────────────────────────────┤
│  1. Entrypoint reads token file or $GITHUB_TOKEN env var        │
│  2. Configures GitHub MCP server with token                     │
│  3. mcp-token-watcher daemon monitors token file (if running)   │
│  4. When token changes, watcher reconfigures MCP                │
│                                                                  │
│  Problem: If watcher isn't running, MCP uses stale token        │
└─────────────────────────────────────────────────────────────────┘
```

## Known Limitations

### GitHub App Token Limitations

GitHub App installation tokens have limited scope:
- `/user` endpoint returns `403 Resource not accessible by integration` (this is expected)
- Token only has access to repositories where the App is installed
- Use `/installation/repositories` to verify token validity

### MCP `get_me` Function

The GitHub MCP server's `get_me` function calls `/user`, which fails with App tokens. This is expected behavior, not an auth failure. Use other endpoints like `list_pull_requests` to verify auth.

## Related PRs

- PR #271: "fix: Auto-refresh GitHub tokens in long-running containers"
- PR #147: "feat: Add automated GitHub token refresher for long-running containers"

## See Also

- `docs/setup/github-app-setup.md` - GitHub App configuration
- `host-services/utilities/github-token-refresher/README.md` - Token refresher documentation
- `jib-container/scripts/mcp-token-watcher.py` - Token watcher script
