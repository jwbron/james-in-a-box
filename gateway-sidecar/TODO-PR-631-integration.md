# TODO: PR #631 Integration for Allow All Network Mode

This document tracks the integration points needed between PR #633 (Network Lockdown)
and PR #631 (Private Repo Mode) when `ALLOW_ALL_NETWORK=true` is enabled.

## Background

PR #633 adds an "Allow All Network" mode that permits all network traffic through
the proxy. This is useful for scenarios requiring broad internet access (package
installation, web search, etc.) while still maintaining repository access control.

PR #631 implements Private Repo Mode which restricts git/gh operations to private
repositories only. For Allow All Network mode, we need the **inverse** behavior:
restrict to **public** repositories only.

## Required Changes in PR #631

### 1. Add `PUBLIC_REPO_ONLY_MODE` Environment Variable

**File:** `gateway-sidecar/private_repo_policy.py`

Add a new mode that inverts the visibility check:
- When `PUBLIC_REPO_ONLY_MODE=true`, allow only public repositories
- When `PRIVATE_REPO_MODE=true`, allow only private repositories (existing behavior)
- These modes are mutually exclusive

```python
PUBLIC_REPO_ONLY_MODE_VAR = "PUBLIC_REPO_ONLY_MODE"

def is_public_repo_only_mode_enabled() -> bool:
    value = os.environ.get(PUBLIC_REPO_ONLY_MODE_VAR, "false").lower().strip()
    return value in ("true", "1")
```

### 2. Update Policy Check Logic

**File:** `gateway-sidecar/private_repo_policy.py`

Modify `check_private_repo_access()` to handle public-repo-only mode:

```python
def check_repo_access(operation, owner, repo, for_write):
    if is_private_repo_mode_enabled():
        # Existing logic: only allow private repos
        return check_private_repo_access(...)
    elif is_public_repo_only_mode_enabled():
        # New logic: only allow public repos
        return check_public_repo_access(...)
    else:
        # No restrictions
        return allow()
```

### 3. Update Health Check Response

**File:** `gateway-sidecar/gateway.py`

Add `public_repo_only_mode` to health check:

```python
return jsonify({
    "status": "healthy",
    "private_repo_mode": is_private_repo_mode_enabled(),
    "public_repo_only_mode": is_public_repo_only_mode_enabled(),
})
```

### 4. Update entrypoint.sh Integration

**File:** `gateway-sidecar/entrypoint.sh`

The TODO comment in entrypoint.sh should be resolved to automatically enable
PUBLIC_REPO_ONLY_MODE when ALLOW_ALL_NETWORK is enabled:

```bash
if [ "$ALLOW_ALL_NETWORK" = "true" ]; then
    export PUBLIC_REPO_ONLY_MODE=true
fi
```

### 5. Update start-gateway.sh Integration

**File:** `gateway-sidecar/start-gateway.sh`

Pass PUBLIC_REPO_ONLY_MODE to the container when ALLOW_ALL_NETWORK is enabled:

```bash
if [ "${ALLOW_ALL_NETWORK:-false}" = "true" ]; then
    ENV_ARGS+=(-e "PUBLIC_REPO_ONLY_MODE=true")
fi
```

### 6. Update config_validator.py

**File:** `gateway-sidecar/config_validator.py`

Uncomment the validation check in `validate_allow_all_network_mode()` that verifies
PUBLIC_REPO_ONLY_MODE is set when ALLOW_ALL_NETWORK is enabled.

## Security Invariant

The key security invariant to maintain:

- **Network Lockdown (default)**: Restricted network + any repo access = secure
- **Allow All Network**: Open network + public repos only = secure
- **Open network + private repos**: NOT SECURE (data exfiltration risk)

The combination of `ALLOW_ALL_NETWORK=true` without `PUBLIC_REPO_ONLY_MODE=true`
should produce a warning or error, as it allows potential data exfiltration from
private repositories.

## Testing

1. Enable `ALLOW_ALL_NETWORK=true` + `PUBLIC_REPO_ONLY_MODE=true`
2. Verify public repo operations succeed
3. Verify private repo operations are blocked with clear error message
4. Verify health check shows both modes correctly
5. Verify web/package registry access works through proxy

## Files with TODO(PR-631) Comments

Search for `TODO(PR-631)` to find all integration points:

- `gateway-sidecar/entrypoint.sh`
- `gateway-sidecar/start-gateway.sh`
- `gateway-sidecar/config_validator.py`
- `gateway-sidecar/squid-allow-all.conf`
