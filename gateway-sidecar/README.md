# Gateway Sidecar

Policy enforcement gateway for git/gh operations in jib containers.

## Overview

The gateway sidecar holds GitHub credentials and validates all GitHub operations against ownership and approval rules. Containers no longer have direct access to `GITHUB_TOKEN`; instead, they route requests through this gateway.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              HOST                                        │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │              Gateway Sidecar (systemd service)                      │ │
│  │  ┌─────────────┐  ┌─────────────────┐  ┌────────────────────────┐ │ │
│  │  │ REST API    │  │ Policy Engine   │  │ GitHub Client          │ │ │
│  │  │ :9847       │  │ - PR ownership  │  │ - GITHUB_TOKEN holder  │ │ │
│  │  │             │  │ - Branch owner  │  │ - gh CLI executor      │ │ │
│  │  │             │  │ - Approval check│  │                        │ │ │
│  │  └──────┬──────┘  └────────┬────────┘  └────────────┬───────────┘ │ │
│  └─────────┼──────────────────┼────────────────────────┼──────────────┘ │
│            │ HTTP (Docker network)                     │                │
│  ┌─────────▼──────────────────────────────────────────────────────────┐ │
│  │                    jib container(s)                                 │ │
│  │  ┌─────────────┐   ┌─────────────┐                                 │ │
│  │  │ git wrapper │   │ gh wrapper  │   NO GITHUB_TOKEN               │ │
│  │  │ calls API   │   │ calls API   │   Wrappers route to gateway     │ │
│  │  └─────────────┘   └─────────────┘                                 │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

## Policy Rules

| Operation | Policy | Check |
|-----------|--------|-------|
| `git push` | Branch ownership | Branch has open PR authored by jib, OR branch starts with `jib-` or `jib/` |
| `gh pr create` | Always allowed | jib can create PRs on any branch it can push to |
| `gh pr comment` | PR ownership | PR must be authored by jib |
| `gh pr merge` | **BLOCKED** | No merge endpoint - human must merge via GitHub UI |
| `gh pr edit` | PR ownership | PR must be authored by jib |
| `gh pr close` | PR ownership | PR must be authored by jib |

**Bot variants for ownership check**: `jib`, `jib[bot]`, `app/jib`, `apps/jib`, `james-in-a-box`, `james-in-a-box[bot]`, `app/james-in-a-box`, `apps/james-in-a-box`

**Branch ownership definition**:
- Branch has an open PR where author is a jib variant, OR
- Branch name starts with `jib-` or `jib/` (allows new branches before PR exists)

## API Endpoints

```
POST /api/v1/git/push
  Request: {repo_path, remote, refspec, force}
  Policy: branch_ownership

POST /api/v1/git/fetch
  Request: {repo_path, remote, operation, args[]}
  Policy: none (read operations)
  Operations: "fetch", "ls-remote"

POST /api/v1/gh/pr/create
  Request: {repo, title, body, base, head}
  Policy: none (always allowed)

POST /api/v1/gh/pr/comment
  Request: {repo, pr_number, body}
  Policy: pr_ownership

POST /api/v1/gh/pr/edit
  Request: {repo, pr_number, title?, body?}
  Policy: pr_ownership

POST /api/v1/gh/pr/close
  Request: {repo, pr_number}
  Policy: pr_ownership

POST /api/v1/gh/execute
  Request: {args[], require_auth}
  Policy: filtered passthrough for read operations

GET /api/v1/health
  Response: {status, github_token_valid}
```

## Files

```
host-services/gateway-sidecar/
├── gateway.py              # Flask REST API server
├── policy.py               # Policy enforcement logic
├── github_client.py        # Wraps gh CLI with token
├── git_client.py           # Git path/arg validation, credential helpers
├── setup.sh                # Installation script
├── gateway-sidecar.service # Systemd unit file
├── tests/                  # Unit tests
│   ├── test_policy.py
│   └── test_gateway.py
└── README.md               # This file
```

## Implementation Phases

### Phase 1: Gateway Service (Foundation)
- [x] Create directory structure
- [x] Implement `gateway.py` - Flask app with REST endpoints
- [x] Implement `github_client.py` - wraps `gh` CLI, reads token from github-token-refresher
- [x] Create systemd service file
- [x] Add health check endpoint

### Phase 2: Policy Engine
- [x] Implement `policy.py` with:
  - `check_pr_ownership(repo, pr_number)` - verify jib is author
  - `check_branch_ownership(repo, branch)` - verify branch tied to jib's PR or jib-prefixed
- [x] Add PR info caching to reduce GitHub API calls
- [x] Write tests for policy logic

### Phase 3: Wrapper Modifications
- [x] Modify `jib-container/scripts/git` to call gateway for push
- [x] Modify `jib-container/scripts/gh` to route commands through gateway
- [x] Update `jib-container/jib` to:
  - Add `--add-host=host.docker.internal:host-gateway` for Linux
  - Set `GATEWAY_URL` environment variable

### Phase 4: Integration
- [x] Test full workflow: container -> gateway -> GitHub
- [x] Add audit logging for all policy decisions
- [x] Update CLAUDE.md rules about merge capability

## Design Decisions

1. **No merge capability**: Gateway does not expose a merge endpoint. Human must merge via GitHub UI. This maintains the existing safety model.

2. **Branch ownership**: Branch has an open jib-authored PR OR starts with `jib-` or `jib/`. This allows pushing to new branches before a PR exists.

3. **Token source**: Reads token from `~/.jib-sharing/.github-token` (same as github-token-refresher).

## Testing

```bash
# Unit tests
pytest host-services/gateway-sidecar/tests/

# Manual test - push (should succeed for jib's branch)
git push origin jib-test-branch

# Manual test - push (should fail for main)
git push origin main  # ERROR: branch not owned by jib

# Manual test - PR comment (should succeed for jib's PR)
gh pr comment 123 --body "test"

# Manual test - merge blocked
gh pr merge 123  # ERROR: merge not supported
```

## Installation

```bash
./host-services/gateway-sidecar/setup.sh
systemctl --user enable --now gateway-sidecar
```

## Troubleshooting

### Permission denied on .git/objects

**Symptom:**
```
error: insufficient permission for adding an object to repository database .git/objects
fatal: failed to write object
fatal: unpack-objects failed
```

**Cause:**
The gateway-sidecar ran as root instead of your user. When this happens, git objects are created with `root:root` ownership, which prevents your user from writing to the repository.

**Fix:**

1. **Fix file ownership** - restore ownership of affected .git directories:
   ```bash
   sudo chown -R $(id -u):$(id -g) ~/repos/*/.git
   ```

2. **Verify/fix the service file** - ensure the ExecStart path in `gateway-sidecar.service` points to the correct `gateway.py` location. A common issue is the path becoming stale after updates:
   ```bash
   cat ~/.config/systemd/user/gateway-sidecar.service | grep ExecStart
   # Should show the correct path to gateway.py
   ```

3. **Restart the service**:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart gateway-sidecar
   ```

4. **Verify the gateway is running as your user** (not root):
   ```bash
   ps aux | grep gateway
   # Should show your username, not root
   ```

**Prevention:**
The gateway now includes a startup check that refuses to run as root and displays a helpful error message. If you see this error at startup, follow the steps above to fix the service configuration.
