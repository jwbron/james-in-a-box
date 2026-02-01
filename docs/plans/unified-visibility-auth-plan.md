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

## Proposed Implementation Order

### Changeset A: Verify PRIVATE_MODE Fix (from PR #675 analysis)

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

### Changeset B: Fix Visibility Checker Token Selection (from PR #673 analysis)

**Effort**: ~50-100 lines
**Dependencies**: None
**Priority**: High (blocks Changeset C)

**Problem**: `RepoVisibilityChecker` in `repo_visibility.py` always uses the bot token (`GITHUB_TOKEN` or `/secrets/.github-token`). When a repository is configured with `auth_mode: incognito`, the bot token may not have access (GitHub App not installed), causing 404 errors:

```
Repository not found or inaccessible
  owner=Khan repo=webapp status_code=404
```

**Solution**: Query visibility using both available tokens and union the results.

**Files to modify**:
- `gateway-sidecar/repo_visibility.py`

**Implementation**:

```python
# repo_visibility.py - Add multi-token support

def _get_tokens(self) -> list[str]:
    """Get all available tokens for visibility queries."""
    tokens = []

    # Bot token (GitHub App)
    bot_token = os.environ.get("GITHUB_TOKEN")
    if not bot_token:
        token_file = Path("/secrets/.github-token")
        if token_file.exists():
            bot_token = token_file.read_text().strip()
    if bot_token:
        tokens.append(bot_token)

    # User token (incognito/user mode)
    user_token = os.environ.get("GITHUB_INCOGNITO_TOKEN")
    if user_token:
        tokens.append(user_token)

    return tokens

def get_repo_visibility(
    self, owner: str, repo: str, for_write: bool = False
) -> VisibilityType | None:
    """Get visibility using all available tokens."""
    # Check cache first
    cached = self._get_cached(owner, repo, for_write)
    if cached:
        return cached

    # Try each token until one succeeds
    tokens = self._get_tokens()
    for token in tokens:
        visibility = self._query_visibility(owner, repo, token)
        if visibility is not None:
            self._cache_result(owner, repo, visibility, for_write)
            return visibility

    # All tokens failed - fail closed
    return None
```

**Testing**:
- [ ] Bot-mode repo visibility check → Uses bot token, succeeds
- [ ] Incognito-mode repo visibility check → Falls back to user token, succeeds
- [ ] Repo accessible by neither token → Returns None (fail closed)
- [ ] Cache populated on success

---

### Changeset C: Enforce Private Mode on GH Operations (from PR #674 analysis)

**Effort**: ~100-150 lines
**Dependencies**: Changeset B (visibility checker must work correctly first)
**Priority**: High

**Problem**: The `gh/execute` passthrough endpoint does not call `check_private_repo_access()`. In private mode, agents can read any public repository via `gh repo view` or `gh api`:

```bash
# Should fail in private mode, but succeeds
gh repo view torvalds/linux --json name,visibility
# Returns: {"name":"linux","visibility":"PUBLIC"}
```

**Root cause**: Looking at `gateway.py`, the `/api/v1/gh/execute` endpoint passes commands through without visibility filtering. Only specific endpoints like `gh/pr/create` and `gh/pr/comment` check `check_private_repo_access()`.

**Solution**: Add visibility enforcement to the `gh/execute` endpoint.

**Files to modify**:
- `gateway-sidecar/gateway.py` - Add policy check to `/api/v1/gh/execute`
- `gateway-sidecar/private_repo_policy.py` - Ensure "gh_read" operation type exists

**Implementation approach**:

1. **Extract owner/repo from gh commands**: Parse the command to identify target repository
   - `gh repo view owner/repo` → owner/repo
   - `gh api /repos/owner/repo/...` → owner/repo
   - `gh pr list -R owner/repo` → owner/repo
   - `gh issue view 123 -R owner/repo` → owner/repo

2. **Add policy check before execution**:
```python
@app.route("/api/v1/gh/execute", methods=["POST"])
@require_session_auth
def gh_execute():
    command = request.json.get("command", [])

    # Extract target repo from command
    owner, repo = extract_repo_from_gh_command(command)

    if owner and repo:
        # Check visibility policy
        result = check_private_repo_access(
            operation="gh_read",
            owner=owner,
            repo=repo,
            for_write=False,
            session_mode=g.session_mode,
        )
        if not result.allowed:
            return jsonify({"error": result.reason}), 403

    # Continue with execution...
```

3. **Handle non-repo commands**: Commands like `gh auth status` or `gh api /rate_limit` don't target a specific repo and should pass through.

**Edge cases**:
- Search endpoints (`gh search repos`) - Block entirely in private mode (too permissive)
- User endpoints (`gh api /user`) - Allow (no repo context)
- Org endpoints (`gh api /orgs/...`) - Allow (no specific repo)

**Testing**:
- [ ] Private mode + `gh repo view` private repo → Allowed
- [ ] Private mode + `gh repo view` public repo → Blocked (403)
- [ ] Private mode + `gh api /repos/public/repo` → Blocked (403)
- [ ] Private mode + `gh api /rate_limit` → Allowed (no repo context)
- [ ] Public mode + `gh repo view` public repo → Allowed
- [ ] Public mode + `gh repo view` private repo → Blocked (403)

---

### Changeset D: Auth Mode Cleanup (from PR #673 analysis, Phases 2-4)

**Effort**: ~200-300 lines
**Dependencies**: Changesets B and C
**Priority**: Medium (cleanup, not bug fix)

This is follow-up work that can be done after the critical bugs are fixed.

#### Phase D1: Rename "incognito" → "user"

**Rationale**: "Incognito" implies hiding something. The actual meaning is "operations attributed to a user's PAT instead of the bot".

| Current | Proposed |
|---------|----------|
| `auth_mode: "incognito"` | `auth_mode: "user"` |
| `GITHUB_INCOGNITO_TOKEN` | `GITHUB_USER_TOKEN` |
| `get_incognito_token()` | `get_user_token()` |

**Backwards compatibility**: Accept both during transition with deprecation warning.

**Files to update**:
- `gateway-sidecar/github_client.py`
- `gateway-sidecar/git_client.py`
- `gateway-sidecar/gateway.py`
- `gateway-sidecar/policy.py`
- `config/repo_config.py`
- `shared/jib_config/configs/github.py`
- Documentation files

#### Phase D2: Move Token Refresh to Gateway Sidecar

**Current**: Separate `github-token-refresher.py` systemd service writes to `~/.jib-gateway/.github-token` every 45 min.

**Proposed**: In-memory token refresh within gateway sidecar.

**Benefits**:
- Simpler deployment (fewer systemd services)
- Better security (tokens in memory, not on disk)
- Cleaner architecture

**New file**: `gateway-sidecar/token_refresher.py`

#### Phase D3: Remove Gateway Secret

Per existing plan in `docs/plans/simplify-gateway-auth.md`, reduce auth mechanisms:
- Remove: Gateway Secret (legacy)
- Keep: Launcher Secret, Session Tokens

---

## Summary: Recommended Approach

| Changeset | Analysis PR | Scope | Order |
|-----------|-------------|-------|-------|
| **A** | #675 | Verify fix, close analysis PR | 1 (immediate) |
| **B** | #673 Phase 1 | Fix visibility token selection | 2 |
| **C** | #674 | Add gh/execute policy enforcement | 3 (depends on B) |
| **D** | #673 Phases 2-4 | Cleanup & refactoring | 4 (after B+C stable) |

**Alternative**: Changesets B and C could be combined into a single implementation PR if preferred, since they're tightly related. However, keeping them separate allows for easier review and rollback.

## PR Disposition

All three analysis PRs should be **closed** after this plan is approved:
- **#675**: Analysis complete, bug already fixed in #672/#668 - verify and close
- **#674**: Analysis complete, implementation tracked in Changeset C - close
- **#673**: Analysis complete, implementation tracked in Changesets B+D - close

Implementation work will be done in new PRs that reference this unified plan.

## Open Questions

1. **For Changeset B**: Should we query both tokens in parallel (faster) or sequentially (simpler)?
   - Recommendation: Sequential, bot token first (it's more commonly used)

2. **For Changeset C**: How should we handle `gh search` commands?
   - Recommendation: Block entirely in private mode (too broad to filter)

3. **For Changeset D**: How long should we maintain backwards compatibility for `auth_mode: "incognito"`?
   - Recommendation: At least 2 major versions with deprecation warnings

## Files Changed in This PR

This PR contains only this planning document. Implementation will be in follow-up PRs per the changeset breakdown above.
