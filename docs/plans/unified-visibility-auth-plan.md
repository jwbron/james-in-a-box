# Unified Plan: Visibility Checking & Auth Mode Fixes

**Date**: 2026-02-01
**Related PRs**: #673, #674, #675
**Status**: Proposed

## Executive Summary

This plan consolidates three analysis PRs into a cohesive implementation strategy. These PRs contain investigations and proposed fixes—they are not documentation to be merged, but analyses that guide our implementation work.

| PR | Analysis | Finding | Action Required |
|----|----------|---------|-----------------|
| #675 | PRIVATE_MODE defaulting investigation | Bug already fixed in #672, #668 | Verify fix, close PR |
| #674 | Private mode gap for `gh` reads | Policy gap exists | Implement enforcement |
| #673 | Visibility checker token selection | Wrong token used for incognito repos | Fix token selection + cleanup |

**Key insight**: PR #673's visibility checker bug must be fixed first, because PR #674's private mode enforcement depends on accurate visibility checks. If visibility checks fail for incognito-mode repos (returning 404), we can't enforce private mode on them.

---

## Changeset A: Verify PRIVATE_MODE Fix (from PR #675 analysis)

**Effort**: Verification only
**Dependencies**: None

PR #675's analysis confirms the PRIVATE_MODE default bug was fixed in PRs #672 and #668.

**Action**:
1. Run the verification steps from the analysis to confirm the fix is working
2. Close PR #675 (analysis complete, no further action needed)

**Verification steps** (from #675):
```bash
# Ensure no network.env exists
rm -f ~/.config/jib/network.env

# Restart gateway and check health
systemctl --user restart gateway-sidecar
curl -s http://localhost:9847/api/v1/health | jq .private_mode
# Expected: false
```

---

## Changeset B: Fix Visibility Checker Token Selection (from PR #673 analysis)

**Effort**: ~100-150 lines
**Dependencies**: None
**Priority**: High (blocks Changeset C)

### Problem

`RepoVisibilityChecker` in `repo_visibility.py` is a **singleton** initialized at startup. It only uses the bot token (`GITHUB_TOKEN` or `/secrets/.github-token`) for visibility checks. When a repository is configured with `auth_mode: incognito`, the bot token may not have access (GitHub App not installed on that repo), causing 404 errors:

```
Repository not found or inaccessible
  owner=Khan repo=webapp status_code=404
```

The visibility checker cannot know which token to use because:
1. It's a singleton with no per-request context
2. The `auth_mode` is per-repository (from config), not passed to visibility checks
3. Different repos in the same request batch may need different tokens

### Solution: Multi-Token Query with Sequential Fallback

Query visibility using both available tokens, bot first then user. Return the first successful result.

**Rationale for sequential (not parallel)**:
- Bot token is used for ~90% of repos, so try it first
- Avoids doubling API calls for the common case
- Simpler error handling
- Rate limiting is per-token, so parallel wouldn't help there

### Files to Modify

**`gateway-sidecar/repo_visibility.py`**

### Implementation

```python
# repo_visibility.py - Replace _get_token with _get_tokens and update _fetch_visibility

def _get_tokens(self) -> list[tuple[str, str]]:
    """
    Get all available tokens for visibility queries.

    Returns:
        List of (token, source_name) tuples, ordered by preference.
        Bot token first (most commonly used), then user token.
    """
    tokens = []

    # 1. Bot token (GitHub App) - try first, most common
    bot_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not bot_token and self._token_file.exists():
        try:
            import json
            data = json.loads(self._token_file.read_text())
            bot_token = data.get("token", "")
        except (json.JSONDecodeError, OSError):
            pass
    if bot_token:
        tokens.append((bot_token, "bot"))

    # 2. User token (incognito/user mode) - fallback
    user_token = os.environ.get("GITHUB_INCOGNITO_TOKEN", "").strip()
    if user_token:
        tokens.append((user_token, "user"))

    return tokens


def _fetch_visibility_with_token(
    self, owner: str, repo: str, token: str, source: str
) -> VisibilityType | None:
    """
    Fetch repository visibility using a specific token.

    Args:
        owner: Repository owner
        repo: Repository name
        token: GitHub token to use
        source: Token source name for logging ("bot" or "user")

    Returns:
        'public', 'private', 'internal', or None on error
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            visibility = data.get("visibility", "public")

            # Validate visibility value to prevent cache poisoning
            if visibility not in VALID_VISIBILITIES:
                logger.warning(
                    "Invalid visibility value from GitHub API",
                    owner=owner, repo=repo, visibility=visibility,
                    token_source=source,
                )
                return None

            logger.debug(
                "Fetched repository visibility",
                owner=owner, repo=repo, visibility=visibility,
                token_source=source,
            )
            return visibility

        elif response.status_code == 404:
            # Token doesn't have access - try next token
            logger.debug(
                "Token cannot access repository (404)",
                owner=owner, repo=repo, token_source=source,
            )
            return None

        elif response.status_code == 403:
            # Rate limited or forbidden
            logger.warning(
                "GitHub API forbidden/rate-limited",
                owner=owner, repo=repo, status_code=403,
                token_source=source,
            )
            return None

        else:
            logger.warning(
                "GitHub API unexpected status",
                owner=owner, repo=repo, status_code=response.status_code,
                token_source=source,
            )
            return None

    except requests.Timeout:
        logger.warning("GitHub API timeout", owner=owner, repo=repo, token_source=source)
        return None
    except requests.RequestException as e:
        logger.warning(
            "GitHub API request failed",
            owner=owner, repo=repo, error=str(e), token_source=source,
        )
        return None


def _fetch_visibility(self, owner: str, repo: str) -> VisibilityType | None:
    """
    Fetch repository visibility, trying all available tokens.

    Tries tokens in order (bot first, then user) and returns the first
    successful result. This handles repos where the bot token doesn't
    have access but the user token does (incognito mode repos).

    Args:
        owner: Repository owner
        repo: Repository name

    Returns:
        'public', 'private', 'internal', or None if all tokens fail
    """
    tokens = self._get_tokens()

    if not tokens:
        logger.warning("No GitHub tokens available for visibility check")
        return None

    for token, source in tokens:
        visibility = self._fetch_visibility_with_token(owner, repo, token, source)
        if visibility is not None:
            return visibility

    # All tokens failed - log summary
    logger.warning(
        "All tokens failed visibility check",
        owner=owner, repo=repo,
        tokens_tried=[source for _, source in tokens],
    )
    return None
```

### Behavior Changes

| Scenario | Before | After |
|----------|--------|-------|
| Bot-mode repo, bot token works | Success | Success (no change) |
| Incognito-mode repo, bot 404 | **Fail (404)** | **Success (user token)** |
| Repo accessible by neither | Fail | Fail (no change) |
| Only user token configured | Success if exists | Success (no change) |

### Rate Limiting Considerations

- Worst case: 2x API calls per visibility check (if bot token always 404s)
- Mitigation: 60-second cache means repeated checks don't hit API
- For writes: TTL=0 means 2x calls, but writes are less frequent
- Monitoring: Log which token succeeded to detect patterns

### Testing

```python
# tests/test_repo_visibility.py

def test_visibility_bot_token_success():
    """Bot token works, user token not tried."""
    # Setup: mock bot token to return "private"
    # Assert: only bot token endpoint called

def test_visibility_bot_404_user_success():
    """Bot token 404, fall back to user token."""
    # Setup: mock bot token to 404, user token to return "private"
    # Assert: both endpoints called, returns "private"

def test_visibility_both_fail():
    """Both tokens fail, return None (fail closed)."""
    # Setup: mock both tokens to 404
    # Assert: returns None

def test_visibility_only_user_token():
    """Only user token configured."""
    # Setup: no bot token, user token returns "public"
    # Assert: returns "public"

def test_visibility_caching_prevents_duplicate_calls():
    """Successful result is cached, no repeat API calls."""
    # Setup: first call succeeds
    # Assert: second call uses cache, no API call
```

---

## Changeset C: Enforce Private Mode on GH Operations (from PR #674 analysis)

**Effort**: ~150-200 lines
**Dependencies**: Changeset B (visibility checker must work correctly first)
**Priority**: High

### Problem

The `gh/execute` endpoint in `gateway.py:1496-1633` has private mode enforcement, but only when `repo` is successfully extracted. Current repo extraction only handles:
- `--repo`/`-R` flags (lines 1569-1573)
- `payload_repo` from container (lines 1576-1577)

**Missing cases** (from security review):

| Command Pattern | Current Status | Gap |
|----------------|----------------|-----|
| `gh pr view 123 -R owner/repo` | Caught | None |
| `gh repo view owner/repo` | **MISSED** | Positional arg |
| `gh repo clone owner/repo` | **MISSED** | Positional arg |
| `gh api /repos/owner/repo/issues` | Path validated but not for private mode | Separate logic |
| `gh search repos` | Allowed | Too broad |

### Solution: Comprehensive Repo Extraction

Add a new function to extract repo from all gh command patterns, then ensure private mode enforcement uses it.

### Files to Modify

**`gateway-sidecar/github_client.py`** - Add `extract_repo_from_gh_command()`
**`gateway-sidecar/gateway.py`** - Update `gh_execute()` to use new extractor

### Implementation

#### Part 1: New Repo Extractor (`github_client.py`)

```python
# github_client.py - Add after parse_gh_api_args

def extract_repo_from_gh_api_path(api_path: str) -> str | None:
    """
    Extract owner/repo from a gh api path.

    Examples:
        "repos/owner/repo/pulls" -> "owner/repo"
        "repos/owner/repo" -> "owner/repo"
        "/repos/owner/repo/issues/123" -> "owner/repo"
        "user" -> None
        "orgs/myorg/repos" -> None

    Args:
        api_path: The API path (with or without leading slash)

    Returns:
        "owner/repo" string or None if not a repo-scoped path
    """
    path = api_path.lstrip("/")

    # Must start with "repos/"
    if not path.startswith("repos/"):
        return None

    # Split and extract owner/repo
    parts = path.split("/")
    if len(parts) >= 3:
        owner, repo = parts[1], parts[2]
        # Validate they look like valid GitHub identifiers
        if owner and repo and not owner.startswith("-") and not repo.startswith("-"):
            return f"{owner}/{repo}"

    return None


def extract_repo_from_gh_command(args: list[str]) -> str | None:
    """
    Extract target repository from any gh command.

    Handles multiple patterns:
    1. --repo/-R flag: gh pr view 123 -R owner/repo
    2. gh repo commands: gh repo view owner/repo
    3. gh api paths: gh api /repos/owner/repo/issues

    Args:
        args: Command arguments (after 'gh')

    Returns:
        "owner/repo" string or None if not determinable
    """
    if not args:
        return None

    # Pattern 1: --repo or -R flag (highest priority)
    for i, arg in enumerate(args):
        if arg in ("--repo", "-R") and i + 1 < len(args):
            return args[i + 1]

    # Pattern 2: gh repo <subcommand> <owner/repo>
    # Subcommands that take repo as first positional arg:
    # view, clone, fork, edit, delete, archive, rename, sync
    if args[0] == "repo" and len(args) >= 3:
        subcommand = args[1]
        repo_arg = args[2]

        # These subcommands take owner/repo as positional argument
        positional_repo_subcommands = {
            "view", "clone", "fork", "edit", "delete",
            "archive", "rename", "sync", "set-default"
        }

        if subcommand in positional_repo_subcommands:
            # Validate it looks like owner/repo (not a flag)
            if "/" in repo_arg and not repo_arg.startswith("-"):
                return repo_arg

    # Pattern 3: gh api /repos/owner/repo/...
    if args[0] == "api" and len(args) > 1:
        api_path, _ = parse_gh_api_args(args[1:])
        if api_path:
            return extract_repo_from_gh_api_path(api_path)

    return None


# Commands that should be blocked entirely in private mode
# These are too broad to filter by repository
GH_COMMANDS_BLOCKED_IN_PRIVATE_MODE = frozenset({
    "search",  # gh search repos/issues/prs/commits - too broad
})
```

#### Part 2: Update `gh_execute()` (`gateway.py`)

```python
# gateway.py - Replace lines 1565-1586 in gh_execute()

@app.route("/api/v1/gh/execute", methods=["POST"])
@require_session_auth
def gh_execute():
    """Execute a generic gh command with private mode enforcement."""
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    args = data.get("args", [])
    cwd = data.get("cwd")
    payload_repo = data.get("repo")

    if not args:
        return make_error("Missing args")

    # Get session mode from request context
    session_mode = getattr(g, "session_mode", None)

    # Check for commands blocked entirely in private mode
    if session_mode == "private" and args:
        if args[0] in GH_COMMANDS_BLOCKED_IN_PRIVATE_MODE:
            audit_log(
                "gh_command_blocked_private_mode",
                "gh_execute",
                success=False,
                details={
                    "command": args[0],
                    "reason": "Command blocked in private mode (too broad)",
                },
            )
            return make_error(
                f"Command 'gh {args[0]}' is not allowed in private mode",
                status_code=403,
                details={"command": args[0], "session_mode": "private"},
            )

    # Check for blocked commands (existing logic)
    cmd_str = " ".join(args[:2]) if len(args) >= 2 else args[0] if args else ""
    for blocked in BLOCKED_GH_COMMANDS:
        if cmd_str.startswith(blocked):
            audit_log(
                "blocked_command", "gh_execute", success=False,
                details={"command_args": args, "blocked_command": blocked},
            )
            return make_error(
                f"Command '{blocked}' is not allowed through the gateway.",
                status_code=403,
            )

    # For 'gh api' commands, validate the path against allowlist
    if args and args[0] == "api" and len(args) > 1:
        api_path, method = parse_gh_api_args(args[1:])
        if api_path is None:
            return make_error("No API path provided in gh api command", status_code=400)

        path_valid, path_error = validate_gh_api_path(api_path, method)
        if not path_valid:
            audit_log(
                "api_path_blocked", "gh_execute", success=False,
                details={"api_path": api_path, "method": method, "reason": path_error},
            )
            return make_error(path_error, status_code=403)

    # Extract repo using comprehensive extractor
    repo = extract_repo_from_gh_command(args)

    # Fall back to payload_repo if command doesn't contain repo
    if not repo and payload_repo:
        repo = payload_repo
        # Inject --repo for commands that need it (not gh repo * commands)
        if args and args[0] != "repo":
            args = ["--repo", payload_repo] + list(args)

    # Determine auth mode
    auth_mode = get_auth_mode(repo) if repo else "bot"

    # Check Private Repo Mode policy
    if repo:
        repo_info = parse_owner_repo(repo)
        if repo_info:
            priv_result = check_private_repo_access(
                operation="gh_execute",
                owner=repo_info.owner,
                repo=repo_info.repo,
                for_write=False,
                session_mode=session_mode,
            )
            if not priv_result.allowed:
                audit_log(
                    "gh_execute_denied_private_mode",
                    "gh_execute",
                    success=False,
                    details={
                        "repo": repo,
                        "command_args": args[:3] if len(args) > 3 else args,
                        "reason": priv_result.reason,
                        "visibility": priv_result.visibility,
                    },
                )
                return make_error(
                    priv_result.reason,
                    status_code=403,
                    details=priv_result.to_dict(),
                )

    # Execute the command
    github = get_github_client(mode=auth_mode)
    result = github.execute(args, timeout=60, cwd=cwd, mode=auth_mode)

    if result.success:
        response_data = result.to_dict()
        response_data["auth_mode"] = auth_mode
        return make_success("Command executed", response_data)
    else:
        return make_error(
            f"Command failed: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )
```

### Behavior Changes

| Command | Session Mode | Before | After |
|---------|--------------|--------|-------|
| `gh repo view torvalds/linux` | private | **Allowed** | **Blocked (403)** |
| `gh repo clone owner/public-repo` | private | **Allowed** | **Blocked (403)** |
| `gh api /repos/public/repo/issues` | private | **Allowed** | **Blocked (403)** |
| `gh search repos query` | private | **Allowed** | **Blocked (403)** |
| `gh pr view 123 -R private/repo` | private | Allowed | Allowed |
| `gh repo view owner/repo` | public | Allowed | Allowed |

### Edge Cases

1. **No repo determinable**: Commands like `gh auth status` or `gh api /rate_limit` have no repo context - allow through (no visibility to check)

2. **Repo in payload but not args**: Container-detected repo is used - inject `--repo` flag for non-`gh repo` commands

3. **gh search blocked entirely**: Too broad to filter by visibility - block in private mode

### Testing

```python
# tests/test_gh_execute_private_mode.py

def test_gh_repo_view_public_in_private_mode():
    """gh repo view public-repo blocked in private mode."""
    # Setup: session_mode="private", visibility returns "public"
    # Assert: 403 response

def test_gh_repo_view_private_in_private_mode():
    """gh repo view private-repo allowed in private mode."""
    # Setup: session_mode="private", visibility returns "private"
    # Assert: success

def test_gh_api_repos_path_private_mode():
    """gh api /repos/owner/repo/... checked against private mode."""
    # Setup: session_mode="private", public repo
    # Assert: 403 response

def test_gh_search_blocked_private_mode():
    """gh search completely blocked in private mode."""
    # Setup: session_mode="private"
    # Assert: 403 response

def test_gh_api_non_repo_path_allowed():
    """gh api /rate_limit allowed (no repo context)."""
    # Setup: session_mode="private"
    # Assert: success (no visibility check needed)

def test_payload_repo_used_when_no_args_repo():
    """Payload repo used for visibility check when not in args."""
    # Setup: payload contains repo, args don't
    # Assert: visibility checked against payload repo

def test_gh_repo_clone_positional():
    """gh repo clone owner/repo extracts repo correctly."""
    # Setup: args = ["repo", "clone", "owner/repo"]
    # Assert: extract_repo_from_gh_command returns "owner/repo"
```

---

## Changeset D: Auth Mode Cleanup (from PR #673 analysis, Phases 2-4)

**Effort**: ~200-300 lines
**Dependencies**: Changesets B and C
**Priority**: Medium (cleanup, not bug fix)

This is follow-up work after critical bugs are fixed.

### Phase D1: Rename "incognito" → "user"

**Rationale**: "Incognito" implies hiding something. The actual meaning is "operations attributed to a user's PAT instead of the bot".

| Current | Proposed |
|---------|----------|
| `auth_mode: "incognito"` | `auth_mode: "user"` |
| `GITHUB_INCOGNITO_TOKEN` | `GITHUB_USER_TOKEN` |
| `get_incognito_token()` | `get_user_token()` |

**Backwards compatibility**: Accept both config values with deprecation warning for 6 months (until 2026-08-01).

```python
# config/repo_config.py
def get_auth_mode(repo: str) -> str:
    auth_mode = get_repo_setting(repo, "auth_mode", "bot")

    # Backwards compatibility: accept "incognito" with deprecation warning
    if auth_mode == "incognito":
        logger.warning(
            "Deprecation: auth_mode 'incognito' is deprecated, use 'user' instead",
            repo=repo,
            deprecated_value="incognito",
            replacement="user",
            removal_date="2026-08-01",
        )
        return "user"

    if auth_mode not in ("bot", "user"):
        return "bot"
    return auth_mode
```

**Files to update**:
- `gateway-sidecar/github_client.py` - Token env var reading
- `gateway-sidecar/git_client.py` - Token selection
- `gateway-sidecar/gateway.py` - Auth mode checks
- `gateway-sidecar/policy.py` - Policy comments
- `config/repo_config.py` - Config parsing with deprecation
- `shared/jib_config/configs/github.py` - Token loading
- Documentation files

### Phase D2: Move Token Refresh to Gateway Sidecar

**Current architecture**:
```
[host] github-token-refresher.py (systemd service)
       └── Writes to ~/.jib-gateway/.github-token every 45 min
           └── Gateway reads from file
```

**Proposed architecture**:
```
[gateway-sidecar] TokenRefresher class
                  └── In-memory token with auto-refresh
                  └── No file I/O needed
```

**Implementation**:

```python
# gateway-sidecar/token_refresher.py (new file)

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import requests

from jib_logging import get_logger

logger = get_logger("gateway-sidecar.token-refresher")


class TokenRefresher:
    """
    Manages GitHub App installation token refresh in-memory.

    Tokens are refreshed automatically when they're within 15 minutes
    of expiry. On failure, the last valid token is returned with a
    warning logged.
    """

    def __init__(
        self,
        app_id: str,
        private_key_path: Path,
        installation_id: int,
        refresh_margin_minutes: int = 15,
    ):
        self._app_id = app_id
        self._private_key = private_key_path.read_text()
        self._installation_id = installation_id
        self._refresh_margin = timedelta(minutes=refresh_margin_minutes)

        self._token: str | None = None
        self._expires_at: datetime | None = None
        self._lock = threading.Lock()
        self._consecutive_failures = 0
        self._max_failures = 3

    def get_token(self) -> str | None:
        """
        Get a valid token, refreshing if needed.

        Returns:
            Valid token or None if refresh fails and no cached token.
        """
        with self._lock:
            if self._needs_refresh():
                try:
                    self._refresh()
                    self._consecutive_failures = 0
                except Exception as e:
                    self._consecutive_failures += 1
                    logger.error(
                        "Token refresh failed",
                        error=str(e),
                        consecutive_failures=self._consecutive_failures,
                        has_cached_token=self._token is not None,
                    )

                    # If we have a cached token, use it with warning
                    if self._token and self._consecutive_failures < self._max_failures:
                        logger.warning(
                            "Using cached token after refresh failure",
                            expires_at=self._expires_at.isoformat() if self._expires_at else None,
                        )
                    elif self._consecutive_failures >= self._max_failures:
                        logger.error(
                            "Max refresh failures reached, clearing cached token",
                            max_failures=self._max_failures,
                        )
                        self._token = None
                        self._expires_at = None

            return self._token

    def _needs_refresh(self) -> bool:
        """Check if token needs refresh."""
        if not self._token or not self._expires_at:
            return True
        return datetime.now(UTC) > (self._expires_at - self._refresh_margin)

    def _refresh(self) -> None:
        """Generate new installation token."""
        # Create JWT
        now = datetime.now(UTC)
        payload = {
            "iat": int(now.timestamp()) - 60,  # 1 min in past for clock skew
            "exp": int((now + timedelta(minutes=10)).timestamp()),
            "iss": self._app_id,
        }
        jwt_token = jwt.encode(payload, self._private_key, algorithm="RS256")

        # Get installation token
        response = requests.post(
            f"https://api.github.com/app/installations/{self._installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        self._token = data["token"]
        self._expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))

        logger.info(
            "Token refreshed successfully",
            expires_at=self._expires_at.isoformat(),
        )


# Startup behavior for gateway
def initialize_token_refresher() -> TokenRefresher | None:
    """
    Initialize token refresher from environment.

    Returns None if required config is missing (falls back to file-based tokens).
    """
    app_id = os.environ.get("GITHUB_APP_ID")
    installation_id = os.environ.get("GITHUB_INSTALLATION_ID")
    private_key_path = os.environ.get("GITHUB_PRIVATE_KEY_PATH")

    if not all([app_id, installation_id, private_key_path]):
        logger.info("Token refresher not configured, using file-based tokens")
        return None

    try:
        refresher = TokenRefresher(
            app_id=app_id,
            private_key_path=Path(private_key_path),
            installation_id=int(installation_id),
        )
        # Verify we can get a token on startup
        token = refresher.get_token()
        if token:
            logger.info("Token refresher initialized successfully")
            return refresher
        else:
            logger.error("Token refresher failed to get initial token")
            return None
    except Exception as e:
        logger.error("Failed to initialize token refresher", error=str(e))
        return None
```

**Failure behavior**:
- On refresh failure: Use cached token if available (up to 3 consecutive failures)
- On 3+ consecutive failures: Clear cached token, fail closed
- On startup: If initial token fetch fails, fall back to file-based tokens

### Phase D3: Remove Gateway Secret

Per existing plan in `docs/plans/simplify-gateway-auth.md`:
- Remove: Gateway Secret (legacy)
- Keep: Launcher Secret, Session Tokens

---

## Summary: Implementation Order

| Changeset | Analysis PR | Scope | Dependencies | Effort |
|-----------|-------------|-------|--------------|--------|
| **A** | #675 | Verify fix, close PR | None | Verification |
| **B** | #673 Phase 1 | Multi-token visibility | None | ~100 lines |
| **C** | #674 | gh repo/api extraction + enforcement | B | ~150 lines |
| **D** | #673 Phases 2-4 | Cleanup & refactoring | B, C | ~250 lines |

**Recommended approach**: Implement B and C together in a single PR since they're tightly coupled. D can follow as a separate cleanup PR.

## PR Disposition

All three analysis PRs should be **closed** after this plan is approved:
- **#675**: Analysis complete, bug already fixed - verify and close
- **#674**: Analysis complete, implementation tracked in Changeset C - close
- **#673**: Analysis complete, implementation tracked in Changesets B+D - close

Implementation work will be done in new PRs that reference this unified plan.

## Files Changed Summary

### Changeset B
- `gateway-sidecar/repo_visibility.py` - Multi-token support

### Changeset C
- `gateway-sidecar/github_client.py` - `extract_repo_from_gh_command()`, `extract_repo_from_gh_api_path()`
- `gateway-sidecar/gateway.py` - Updated `gh_execute()` with comprehensive enforcement

### Changeset D
- `gateway-sidecar/token_refresher.py` - New file
- `gateway-sidecar/github_client.py` - Rename incognito → user
- `gateway-sidecar/gateway.py` - Use token refresher
- `config/repo_config.py` - Deprecation handling
- Multiple documentation files
