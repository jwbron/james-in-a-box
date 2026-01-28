# Hot-Reload for jib Configuration

**Status**: Proposed
**Author**: jib
**Date**: 2026-01-28
**Related**: PR #528 (config modernization - phases 4-5 deferred)

## Summary

Add hot-reload capability for jib configuration without requiring gateway restart. Focus on:
1. Repository access configuration (repositories.yaml)
2. Authentication settings (secrets.env, tokens)
3. Gateway sidecar policy configuration (trusted users, caches)

## Motivation

Currently, changes to configuration require restarting the gateway sidecar container. This is disruptive and slow. The config modernization framework (PR #523) deferred hot-reload as "Phase 4" - this proposal implements that deferred work.

**Use cases:**
- Adding a new trusted user without gateway restart
- Updating authentication tokens
- Clearing stale policy caches after repo access changes

## Current State

| Component | Current Behavior | Problem |
|-----------|------------------|---------|
| `HostConfig` | Singleton, loads secrets once | Changes require restart |
| `TRUSTED_BRANCH_OWNERS` | Module-level frozenset at import | Changes require gateway restart |
| `PolicyEngine` caches | Bounded caches (5min/2min TTL) | No manual invalidation |
| `repo_config` | Fresh read on each call | Already hot-reloadable |
| GitHub tokens | TTL-based with expiry check | Works but no forced refresh |

## Architecture

**Approach**: Hybrid TTL + Signal + REST API

```
Config Files (~/.config/jib/)
        |
        v
+------------------+    SIGHUP     +------------------+
| Manual Trigger   | ------------> | ConfigWatcher    |
| (docker kill)    |               | - TTL-based      |
+------------------+               | - mtime tracking |
        |                          +------------------+
        v POST /api/v1/reload              |
+------------------+                       v
| Gateway REST API | ------------> Subscribers:
|                  |               - HostConfig.reload()
+------------------+               - PolicyEngine.clear_caches()
                                   - TrustedUsers.reload()
```

## Implementation Phases

### Phase 1: HostConfig Hot-Reload

**File**: `config/host_config.py`

Add reload capability to the singleton:

```python
class HostConfig:
    def __init__(self):
        self._loaded_at: float = 0
        self._config_version: int = 0
        self._load()

    def _load(self) -> None:
        self._secrets.clear()  # Security: clear stale creds
        self._load_config()
        self._load_secrets()
        self._loaded_at = time.time()
        self._config_version += 1

    def reload(self) -> None:
        self._load()
        logger.info("HostConfig reloaded", version=self._config_version)

    def is_stale(self, ttl: float = 300.0) -> bool:
        return (time.time() - self._loaded_at) > ttl

def get_config(refresh_if_stale: bool = True, ttl: float = 300.0) -> HostConfig:
    if not hasattr(get_config, "_instance"):
        get_config._instance = HostConfig()
    elif refresh_if_stale and get_config._instance.is_stale(ttl):
        get_config._instance.reload()
    return get_config._instance
```

### Phase 2: Trusted Users Registry

**File**: `gateway-sidecar/policy.py`

Convert module-level `TRUSTED_BRANCH_OWNERS` to refreshable class:

```python
class TrustedUserRegistry:
    def __init__(self):
        self._users: frozenset[str] = frozenset()
        self._reload()

    def _reload(self) -> None:
        env_value = os.environ.get("GATEWAY_TRUSTED_USERS", "")
        self._users = frozenset(
            u.strip().lower() for u in env_value.split(",") if u.strip()
        ) if env_value.strip() else frozenset()

    def reload(self) -> None:
        self._reload()
        logger.info("Trusted users reloaded", count=len(self._users))

    def __contains__(self, user: str) -> bool:
        return user.lower() in self._users

_trusted_users = TrustedUserRegistry()
```

Update `_is_trusted_author()` to use `_trusted_users` instead of `TRUSTED_BRANCH_OWNERS`.

### Phase 3: PolicyEngine Cache Invalidation

**File**: `gateway-sidecar/policy.py`

Add cache clearing methods:

```python
class PolicyEngine:
    def clear_caches(self) -> None:
        self._pr_cache.clear()
        self._branch_pr_cache.clear()
        logger.info("Policy caches cleared")

def reload_policy_engine() -> None:
    global _engine
    _trusted_users.reload()
    if _engine is not None:
        _engine.clear_caches()
```

### Phase 4: Gateway Reload Endpoint

**File**: `gateway-sidecar/gateway.py`

Add REST endpoint:

```python
@app.route("/api/v1/reload", methods=["POST"])
@require_auth
def reload_config():
    """Trigger configuration reload."""
    data = request.get_json() or {}
    components = data.get("components", ["all"])
    results = {"reloaded": []}

    if "all" in components or "policy" in components:
        reload_policy_engine()
        results["reloaded"].append("policy")

    if "all" in components or "trusted_users" in components:
        _trusted_users.reload()
        results["reloaded"].append("trusted_users")

    if "all" in components or "tokens" in components:
        # Invalidate token caches
        for mode in ["bot", "incognito"]:
            client = get_github_client(mode)
            client._cached_token = None
        results["reloaded"].append("tokens")

    return make_success("Configuration reloaded", results)
```

### Phase 5: SIGHUP Signal Handler

**File**: `gateway-sidecar/gateway.py`

```python
import signal

def setup_signal_handlers():
    def handle_sighup(signum, frame):
        logger.info("Received SIGHUP, reloading configuration")
        reload_policy_engine()
        # Clear token caches
        for mode in ["bot", "incognito"]:
            client = get_github_client(mode)
            client._cached_token = None

    signal.signal(signal.SIGHUP, handle_sighup)
```

## Critical Files

| File | Changes |
|------|---------|
| `config/host_config.py` | Add `reload()`, `is_stale()`, update `get_config()` |
| `gateway-sidecar/policy.py` | Add `TrustedUserRegistry`, `clear_caches()`, `reload_policy_engine()` |
| `gateway-sidecar/gateway.py` | Add `/api/v1/reload` endpoint, SIGHUP handler |
| `gateway-sidecar/github_client.py` | Expose token cache invalidation |

## Security Considerations

1. **Credential clearing**: `_secrets.clear()` before reload to prevent stale creds persisting in memory
2. **Auth required**: `/api/v1/reload` requires `@require_auth` decorator
3. **No token logging**: Don't log token values during reload operations
4. **Rate limiting**: Consider adding rate limit to reload endpoint to prevent DoS

## Usage

**REST API:**
```bash
curl -X POST http://jib-gateway:9847/api/v1/reload \
  -H "Authorization: Bearer $JIB_GATEWAY_SECRET" \
  -d '{"components": ["all"]}'
```

**Signal (Docker):**
```bash
docker kill --signal=HUP jib-gateway
```

**Selective reload:**
```bash
# Only trusted users
curl -X POST .../reload -d '{"components": ["trusted_users"]}'
# Only policy caches
curl -X POST .../reload -d '{"components": ["policy"]}'
```

## Verification

1. **Unit tests**: Test `TrustedUserRegistry.reload()`, `PolicyEngine.clear_caches()`, `HostConfig.reload()`
2. **Integration test**: Update `GATEWAY_TRUSTED_USERS`, call reload endpoint, verify new user is recognized
3. **Signal test**: Send SIGHUP to gateway container, verify logs show reload
4. **Cache test**: Populate policy cache, trigger reload, verify cache is empty
5. **Security test**: Verify stale secrets are cleared after reload

## Optional Enhancements (Deferred)

- File watcher (watchdog) for automatic reload on file change
- Atomic config writes utility
- Aggregated health endpoint showing config version
- Periodic background polling (if needed)

---

Authored-by: jib
