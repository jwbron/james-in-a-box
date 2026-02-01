# Plan: Simplify Gateway Authentication

## Current State

The gateway has three authentication mechanisms:
1. **Gateway secret** (`@require_auth`) - General auth, used only for session heartbeat
2. **Launcher secret** (`@require_launcher_auth`) - For session management
3. **Session tokens** (`@require_session_auth`) - For container operations

## Goal

Simplify to two mechanisms:
1. **Launcher secret** - For all launcher-to-gateway operations
2. **Session tokens** - For all container-to-gateway operations

## Changes Required

### 1. Gateway Sidecar (`gateway-sidecar/`)

#### gateway.py
- [ ] Remove `check_auth()` function (lines ~205-227)
- [ ] Remove `require_auth()` decorator (lines ~230-246)
- [ ] Change `@require_auth` to `@require_launcher_auth` on heartbeat endpoint (line 2267)
- [ ] Change `@require_session_auth` to `@require_launcher_auth` on worktree endpoints:
  - `/api/v1/worktree/create` (line 1705)
  - `/api/v1/worktree/delete` (line 1811)
  - `/api/v1/worktree/status` (line 1905)
- [ ] Remove `JIB_GATEWAY_SECRET` env var reading

#### entrypoint.sh
- [ ] Remove gateway secret loading/export (if present)

#### setup.sh
- [ ] Remove gateway secret generation (look for gateway-secret file creation)

### 2. Jib Container (`jib-container/`)

#### jib_lib/gateway.py
- [ ] Remove `GATEWAY_SECRET_FILE` constant
- [ ] Remove `get_gateway_secret()` function
- [ ] Update `gateway_api_call()` to use launcher secret for launcher-side calls
- [ ] Add `get_session_token()` function that reads `JIB_SESSION_TOKEN` env var
- [ ] Container-side calls should use session token (but these go through git/gh wrappers anyway)

#### jib_lib/config.py
- [ ] Remove any gateway secret file references

### 3. Host Services (`host-services/`)

#### Check for gateway secret usage
- [ ] Search for `gateway-secret` file references
- [ ] Update any services that use gateway secret to use launcher secret

### 4. Tests

#### gateway-sidecar/tests/
- [ ] Update test fixtures that mock gateway secret auth
- [ ] Update tests for worktree endpoints to use launcher auth

#### tests/jib/
- [ ] Update any tests that reference gateway secret

### 5. Documentation

- [ ] Update `docs/adr/` files that reference gateway secret
- [ ] Update `jib-container/.claude/rules/environment.md` if it mentions gateway secret

## Testing

1. Run gateway-sidecar tests: `cd gateway-sidecar && pytest tests/`
2. Run jib tests: `pytest tests/jib/`
3. Manual test: Start jib container and verify git operations work

## Migration Notes

- No backwards compatibility needed (single user)
- Gateway secret files can be deleted after migration
- Launcher secret already exists and is used for session management

## Files Summary

**Remove gateway secret from:**
- `gateway-sidecar/gateway.py`
- `gateway-sidecar/setup.sh`
- `jib-container/jib_lib/gateway.py`
- `~/.jib-gateway/gateway-secret` (runtime file)

**Change auth decorator:**
- Worktree endpoints: `@require_session_auth` → `@require_launcher_auth`
- Heartbeat endpoint: `@require_auth` → `@require_launcher_auth`
