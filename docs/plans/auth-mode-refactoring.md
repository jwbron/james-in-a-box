# Auth Mode Refactoring Plan

## Summary

This document proposes refactoring the authentication mode configuration from the confusing "incognito mode" terminology to explicit "user mode" vs "bot mode", and fixing a critical bug where visibility checks fail for repos configured with incognito mode.

## Current Issue (Bug)

The gateway-sidecar is failing to check visibility for repos like `Khan/webapp` and `Khan/culture-cron`:

```
Repository not found or inaccessible [/app/repo_visibility.py:233]
  owner=Khan
  repo=webapp
  status_code=404
Unknown visibility for repo, excluding [/app/gateway.py:2034]
  repo=Khan/webapp
  mode=private
```

**Root cause**: `RepoVisibilityChecker` always uses the bot token (GitHub App installation token `ghs_...`) for visibility checks. When a repo is configured with `auth_mode: incognito`, the actual operations use `GITHUB_INCOGNITO_TOKEN`, but visibility checks still use the bot token. If the GitHub App doesn't have the repo in its installation, it gets 404.

**Affected files:**
- `gateway-sidecar/repo_visibility.py:118-141` - `_get_token()` only checks `GITHUB_TOKEN` env var and token file

## Proposed Changes

### Phase 1: Fix Visibility Check Bug (Immediate)

**Problem**: Visibility checker uses bot token even when the repo uses incognito mode.

**Solution**: Pass auth mode context to visibility checker so it can use the appropriate token.

```python
# repo_visibility.py - Add method to use specific token
def get_visibility_with_token(
    self,
    owner: str,
    repo: str,
    token: str,
    for_write: bool = False,
) -> VisibilityType | None:
    """Get visibility using a specific token."""
    ...
```

**Alternative**: Query visibility using BOTH tokens and union the results. If either token can see the repo, we know its visibility.

### Phase 2: Rename "Incognito Mode" to "User Mode"

The term "incognito" is confusing - it implies hiding something, when really it just means "operations attributed to a user PAT instead of the bot".

**Changes:**

| Current | Proposed |
|---------|----------|
| `auth_mode: "incognito"` | `auth_mode: "user"` |
| `GITHUB_INCOGNITO_TOKEN` | `GITHUB_USER_TOKEN` |
| `incognito:` config section | `user_mode:` config section |
| `get_incognito_token()` | `get_user_token()` |
| `validate_incognito_config()` | `validate_user_mode_config()` |

**Backwards compatibility**: Accept both old and new config values during a transition period, with deprecation warnings.

**Files to update:**
- `gateway-sidecar/github_client.py` - Token env var and methods
- `gateway-sidecar/git_client.py` - Token selection
- `gateway-sidecar/gateway.py` - Auth mode checks
- `gateway-sidecar/policy.py` - Policy comments
- `config/repo_config.py` - Config parsing
- `shared/jib_config/configs/github.py` - Token loading
- `docs/setup/github-auth-comparison.md` - Documentation

### Phase 3: Move Token Refresh to Gateway Sidecar

Currently, the token refresher runs as a separate host-side systemd service. This is unnecessary complexity.

**Current architecture:**
```
[host] github-token-refresher.py (systemd service)
       └── Writes to ~/.jib-gateway/.github-token every 45 min
           └── Gateway and containers read from file
```

**Proposed architecture:**
```
[gateway-sidecar] TokenRefresher class
                  └── In-memory token with auto-refresh
                  └── No file I/O needed
```

**Benefits:**
1. Simpler deployment (no separate systemd service)
2. Better security (tokens in memory, not on disk)
3. Reduced complexity (one less component to manage)
4. Cleaner architecture (gateway manages its own auth)

**Implementation:**

```python
# gateway-sidecar/token_refresher.py (new file)
class TokenRefresher:
    """Manages GitHub App token refresh in-memory."""

    def __init__(self, app_id: str, private_key_path: Path, installation_id: int):
        self._app_id = app_id
        self._private_key = private_key_path.read_text()
        self._installation_id = installation_id
        self._token: str | None = None
        self._expires_at: datetime | None = None
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Get a valid token, refreshing if needed."""
        with self._lock:
            if self._needs_refresh():
                self._refresh()
            return self._token

    def _needs_refresh(self) -> bool:
        """Check if token needs refresh (15 min before expiry)."""
        if not self._token or not self._expires_at:
            return True
        return datetime.now(UTC) > (self._expires_at - timedelta(minutes=15))

    def _refresh(self) -> None:
        """Generate new installation token."""
        jwt = self._create_jwt()
        self._token, self._expires_at = self._get_installation_token(jwt)
```

### Phase 4: Simplify Gateway Auth (Already Planned)

Per `docs/plans/simplify-gateway-auth.md`, reduce from 3 auth mechanisms to 2:

| Current | Purpose | Keep? |
|---------|---------|-------|
| Gateway Secret | Legacy | **Remove** |
| Launcher Secret | Launcher-to-gateway | **Keep** |
| Session Tokens | Container-to-gateway | **Keep** |

This is already planned and documented.

## Summary of Auth Mode Terminology

**Before:**
- "bot" mode (default) - Operations use GitHub App token
- "incognito" mode - Operations use user PAT

**After:**
- "bot" mode (default) - Operations use GitHub App token, attributed to bot
- "user" mode - Operations use user PAT, attributed to user

## Implementation Order

1. **Immediate (bug fix)**: Fix visibility checker to use appropriate token per auth mode
2. **Phase 2**: Rename incognito → user with backwards compat
3. **Phase 3**: Move token refresh into gateway sidecar
4. **Phase 4**: Remove gateway secret (per existing plan)

## Questions for Review

1. Should we keep backwards compatibility with `auth_mode: "incognito"` indefinitely, or deprecate after a version?
2. For the visibility check fix, should we use both tokens (union approach) or pass auth mode context?
3. Is there a use case for the host-side token refresher that the gateway-side approach doesn't cover?
4. Should the user PAT support token refresh (if using a GitHub App for user auth instead of PAT)?

## Files Changed in This PR

This PR only contains this planning document. Implementation will be in follow-up PRs.
