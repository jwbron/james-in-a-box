# GitHub Auth in Long-Running Containers

## Problem Statement

Long-running containers may lose GitHub access after approximately 1 hour. Users see errors like:
- `HTTP 401: Bad credentials`
- `403 Resource not accessible by integration`

## Root Cause Analysis

### Token Lifecycle

1. **Token Generation**: The `jib` launcher generates a GitHub App installation token at container startup
2. **Token Validity**: GitHub App installation tokens expire after **1 hour**
3. **Token Storage**: Token is written to `~/sharing/.github-token` (JSON format)
4. **GitHub Access**: The `gh` CLI and `git push` use the `GITHUB_TOKEN` environment variable

### The Problem

The container starts with a `GITHUB_TOKEN` environment variable. When this token expires after 1 hour, GitHub operations fail unless they read the refreshed token.

### Existing Infrastructure

| Component | Location | Purpose | Status |
|-----------|----------|---------|--------|
| `github-token-refresher` | Host service | Refreshes token every 45 min | Installed via `setup.sh` |
| Token file | `~/sharing/.github-token` | Shared token storage | Updated by host service |
| `git` wrapper | Container script | Reads fresh token for git push | Auto-installed |
| `gh` wrapper | Container script | Reads fresh token for gh CLI | Auto-installed |

### Token Consumption

Both `git` and `gh` use wrapper scripts that read the token file:
- **git push**: Uses `git-credential-github-token` helper which reads from token file
- **gh CLI**: Uses `gh` wrapper which sets `GH_TOKEN` from token file

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

### 3. Test GitHub Token Directly

```bash
# In container - read fresh token from file
TOKEN=$(cat ~/sharing/.github-token | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
curl -s -H "Authorization: Bearer $TOKEN" https://api.github.com/installation/repositories | head -10
```

### 4. Refresh GITHUB_TOKEN from File

```bash
# In container - update environment variable from token file
export GITHUB_TOKEN=$(cat ~/sharing/.github-token | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
```

## Solutions

### Immediate Fix (Manual)

If you're experiencing auth issues in a running container:

```bash
# Reload token from file into environment
export GITHUB_TOKEN=$(cat ~/sharing/.github-token | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")

# Verify it works
gh auth status
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
   cd ~/repos/james-in-a-box
   ./setup.sh --update
   ```

## Architecture Diagram

```
+-----------------------------------------------------------------+
|                           HOST                                   |
+-----------------------------------------------------------------+
|  github-token-refresher (systemd service)                        |
|  +- Runs every 45 minutes                                        |
|  +- Generates new GitHub App installation token                  |
|  +- Writes to ~/.jib-sharing/.github-token                       |
+-----------------------------------------------------------------+
                              |
                              | Mounted as ~/sharing/
                              v
+-----------------------------------------------------------------+
|                         CONTAINER                                |
+-----------------------------------------------------------------+
|  GITHUB_TOKEN env var set at container start                     |
|  ~/sharing/.github-token contains fresh token (updated by host)  |
|                                                                  |
|  For long sessions: re-read token from file as needed            |
+-----------------------------------------------------------------+
```

## Known Limitations

### GitHub App Token Limitations

GitHub App installation tokens have limited scope:
- `/user` endpoint returns `403 Resource not accessible by integration` (this is expected)
- Token only has access to repositories where the App is installed
- Use `/installation/repositories` to verify token validity

## See Also

- `docs/setup/github-app-setup.md` - GitHub App configuration
- `host-services/utilities/github-token-refresher/README.md` - Token refresher documentation
