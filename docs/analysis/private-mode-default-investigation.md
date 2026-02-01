# PRIVATE_MODE Default Investigation

**Date**: 2026-01-31
**Related**: beads-z3iv5, PR #672, PR #668

## Summary

Investigation of reported bug where `PRIVATE_MODE` defaults to `true` instead of `false` when running `jib` without `--public` or `--private` flags.

## Findings

### Issue 1: PRIVATE_MODE Default Value

**Status: FIXED** (PR #672, #668)

The code now correctly defaults `PRIVATE_MODE` to `false` at all layers:

1. **gateway-sidecar/start-gateway.sh:139**
   ```bash
   ENV_ARGS+=(-e "PRIVATE_MODE=${PRIVATE_MODE:-false}")
   ```
   Always passes PRIVATE_MODE explicitly to the container with `false` as default.

2. **gateway-sidecar/entrypoint.sh:20**
   ```bash
   PRIVATE_MODE="${PRIVATE_MODE:-false}"
   ```
   Container entrypoint defaults to `false` if env var is unset.

3. **gateway-sidecar/private_repo_policy.py:118**
   ```python
   value = os.environ.get(PRIVATE_MODE_VAR, "false").lower().strip()
   return value in ("true", "1", "yes")
   ```
   Python policy code defaults to `false` when reading the env var.

4. **gateway-sidecar/gateway.py:373**
   Health endpoint uses `is_private_mode_enabled()` which correctly reads the defaulted value.

### Issue 2: Repo Filtering by Visibility

**Status: FIXED**

Repository filtering based on mode is handled in `gateway.py:session_create()`:

1. **Visibility Query** (lines 2012-2025): Queries GitHub API for each repo's visibility
2. **Mode-Based Filtering** (lines 2030-2062):
   - Private mode: Includes only `private` and `internal` repos
   - Public mode: Includes only `public` repos
3. **Worktree Creation** (lines 2064-2099): Creates worktrees only for filtered repos
4. **Session Registration** (lines 2101-2107): Registers session with the filtered repo list

Note: `parse-git-mounts.py` mounts all git directories for the gateway container itself (it needs access to all repos to serve sessions with different modes), but the actual container access is controlled through session-based worktree creation.

## Code Flow

```
User runs: jib (no flags)
    |
    v
~/.config/jib/network.env does not exist
    |
    v
start-gateway.sh: PRIVATE_MODE unset
    |
    v
Line 139: PRIVATE_MODE=${PRIVATE_MODE:-false} = "false"
    |
    v
Container gets: PRIVATE_MODE=false
    |
    v
entrypoint.sh confirms: PRIVATE_MODE=false
    |
    v
Uses squid-allow-all.conf (full internet)
    |
    v
Health shows: "private_mode": false
```

## Verification Steps

To verify the fix is working:

```bash
# 1. Ensure no network.env exists
rm -f ~/.config/jib/network.env

# 2. Restart gateway
systemctl --user restart gateway-sidecar

# 3. Check health endpoint
curl -s http://localhost:9847/api/v1/health | jq .private_mode
# Expected: false

# 4. Run jib without flags
jib

# 5. From inside container, verify mode
curl -s http://jib-gateway:9847/api/v1/health | jq .
# Expected: "private_mode": false
```

## Root Cause of Original Bug

The original bug was caused by the gateway container not receiving an explicit `PRIVATE_MODE` value when the env var was unset on the host. The container's internal default (or lack thereof) resulted in `true`.

PR #672 fixed this by always passing `PRIVATE_MODE` explicitly with a default of `false`:
```bash
# Before (broken):
if [ -n "${PRIVATE_MODE:-}" ]; then
    ENV_ARGS+=(-e "PRIVATE_MODE=$PRIVATE_MODE")
fi

# After (fixed):
ENV_ARGS+=(-e "PRIVATE_MODE=${PRIVATE_MODE:-false}")
```

## Conclusion

The bug described in `bug-private-mode-default.md` has been fully addressed by PRs #672 and #668. The implementation now correctly:

1. Defaults to public mode (PRIVATE_MODE=false) when no flags are specified
2. Filters repositories by visibility during session creation
3. Uses the appropriate Squid configuration (allow-all vs locked-down)
4. Reports accurate mode in the health endpoint

No further code changes are required. This document serves as verification that the fix is in place.
