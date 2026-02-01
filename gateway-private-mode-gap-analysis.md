# Gateway Private Mode Policy Gap Analysis

**Date**: 2026-02-01
**Discovered by**: jib (during routine access verification)
**Severity**: Medium (policy enforcement gap, not a security breach)

## Summary

The gateway sidecar's `private_mode=true` setting does not restrict GitHub API read operations to private repositories only. The `gh` CLI wrapper allows read access to any repository (public or private) regardless of the private mode setting.

## Expected Behavior (Per Documentation)

From `CLAUDE.md`:

> ### Private Mode (`PRIVATE_MODE=true`)
> Network locked down (Anthropic API only) + private repos only.
>
> In this mode:
> - Only `api.anthropic.com` (Claude API) is allowed through the proxy
> - You CANNOT access PyPI, npm, or any package registry
> - You CANNOT use web search or fetch arbitrary URLs
> - You CAN access private repositories
> - **You CANNOT access public repositories**

## Actual Behavior

| Component | Expected | Actual |
|-----------|----------|--------|
| Proxy (curl to pypi.org) | Blocked | Blocked (exit 60) |
| Proxy (curl to google.com) | Blocked | Blocked (exit 60) |
| Proxy (curl to api.github.com) | Blocked | Blocked (exit 60) |
| `gh repo view` (private repo) | Allowed | Allowed |
| `gh repo view` (public repo) | **Blocked** | **Allowed** |
| `gh api /repos/:owner/:repo` (public) | **Blocked** | **Allowed** |

## Reproduction Steps

```bash
# 1. Verify private mode is enabled
curl -s http://jib-gateway:9847/api/v1/health | jq .private_mode
# Returns: true

# 2. Verify proxy blocks direct internet access (correct)
curl -s --max-time 5 -w "%{http_code}" -o /dev/null https://pypi.org/simple/
# Returns: 000 (connection refused/blocked)

# 3. Attempt to access public repository via gh (should fail, but doesn't)
gh repo view jwbron/james-in-a-box --json name,visibility
# Returns: {"name":"james-in-a-box","visibility":"PUBLIC"}

# 4. Access completely unrelated public repository (should fail, but doesn't)
gh api /repos/torvalds/linux --jq '.name'
# Returns: linux
```

## Root Cause Analysis

The `gh` wrapper script (`/opt/jib-runtime/jib-container/bin/gh`) routes commands through the gateway sidecar. Based on the wrapper code:

```bash
# Read-only operations are passed through
```

The gateway enforces:
- **Write policies**: Merge blocking, branch ownership for push, PR authorship for edits
- **Authentication**: GitHub token held by gateway, not container

The gateway does **not** enforce:
- **Visibility filtering**: No check whether a repo is public/private before allowing read access

## Impact Assessment

**What this means:**
- In private mode, the agent can read metadata, issues, PRs, and code from ANY public repository
- This contradicts the documented security model
- Sensitive private repos remain protected (require GitHub App installation)

**What this does NOT mean:**
- This is not a data exfiltration risk (agent can't send data out)
- Private repos without GitHub App access remain inaccessible
- Write operations are still properly restricted

## Recommendations

### Option A: Enforce at Gateway (Recommended)
Add visibility check to the gateway's GitHub API proxy:
1. For each `gh` request, extract owner/repo from the request
2. Check repository visibility via GitHub API
3. In private mode, reject requests to public repositories with HTTP 403

### Option B: Enforce at Wrapper
Modify the `gh` wrapper script to:
1. Pre-flight check repository visibility before forwarding
2. Block requests to public repos when `PRIVATE_MODE=true`

### Option C: Document as Intended Behavior
If read access to public repos is acceptable in private mode:
1. Update CLAUDE.md to clarify that only **write** operations are restricted
2. Rename "private mode" to something clearer (e.g., "network-restricted mode")

## Affected Components

- `/opt/jib-runtime/jib-container/bin/gh` (wrapper script)
- Gateway sidecar API proxy logic
- Documentation: `~/CLAUDE.md`, `~/repos/CLAUDE.md`

## Related Files

- Gateway health endpoint: `http://jib-gateway:9847/api/v1/health`
- Wrapper script: `/opt/jib-runtime/jib-container/bin/gh`

---

## Implementation Plan

Based on the analysis above, we recommend **Option A: Enforce at Gateway**. This centralizes policy enforcement in a single location and avoids duplicating logic in wrapper scripts.

### Phase 1: Gateway GitHub Proxy Enhancement

**Files to modify:**
- `gateway/src/github_proxy.py` (or equivalent proxy handler)

**Changes:**
1. Add a visibility cache (TTL ~5 minutes) to avoid repeated API calls
2. Before proxying any GitHub API request in private mode:
   - Extract `owner/repo` from the request path (e.g., `/repos/owner/repo/...`)
   - Check cache for visibility; if miss, call `GET /repos/{owner}/{repo}` and cache result
   - If `visibility == "public"` and `private_mode == true`, return HTTP 403 with clear error message
3. Handle edge cases:
   - Non-repo endpoints (e.g., `/user`, `/rate_limit`) - allow through
   - Org-level endpoints - apply same logic if repo context is present
   - Search endpoints - more complex; consider blocking entirely in private mode

### Phase 2: Error Messaging

**Improve user experience when blocked:**
- Return a clear JSON error: `{"error": "public_repo_blocked", "message": "Access to public repositories is not allowed in private mode"}`
- Log blocked requests for audit purposes

### Phase 3: Wrapper Script Updates (Required)

**Files to modify:**
- `/opt/jib-runtime/jib-container/bin/gh`

**Changes:**
- Add client-side visibility check before forwarding to gateway
- When `PRIVATE_MODE=true`, pre-flight check repository visibility
- Block requests to public repos at the wrapper level (defense-in-depth)
- Improve error message handling when blocked locally or when gateway returns 403

**Rationale:** Enforcing at both gateway and wrapper provides defense-in-depth. The wrapper check gives faster feedback to users and reduces unnecessary gateway traffic for blocked requests.

### Phase 4: Documentation

**Files to update:**
- `CLAUDE.md` - Verify existing documentation is accurate after fix
- Add integration test covering this scenario

### Testing Checklist

- [ ] Private mode + private repo read → Allowed
- [ ] Private mode + public repo read → Blocked (403)
- [ ] Private mode + write to authorized repo → Allowed (existing behavior)
- [ ] Non-private mode + public repo read → Allowed
- [ ] Cache invalidation works correctly
- [ ] Error messages are user-friendly

### Estimated Scope

- Gateway changes: ~100-150 lines
- Wrapper script: ~20 lines (optional)
- Tests: ~50-100 lines
- Documentation: Minor updates

---

*Authored by jib*
