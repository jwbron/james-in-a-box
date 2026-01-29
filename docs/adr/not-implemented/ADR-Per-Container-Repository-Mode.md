# ADR: Per-Container Repository Mode Management

## Status

Proposed

## Context

The gateway sidecar currently supports two mutually exclusive repository visibility modes configured via environment variables at startup:

- **Private Repo Mode** (`PRIVATE_REPO_MODE=true`): Restrict operations to private repositories only
- **Public Repo Only Mode** (`PUBLIC_REPO_ONLY_MODE=true`): Restrict operations to public repositories only

This global configuration has limitations:

1. **No concurrent modes**: Cannot run containers with different modes simultaneously
2. **Sidecar restart required**: Changing modes requires restarting the gateway sidecar
3. **All-or-nothing mounting**: All configured repos are mounted regardless of mode; visibility is only enforced at operation time

### Requirements

The system should support:

| Mode | Private Repos | Public Repos |
|------|---------------|--------------|
| `private_repo_mode=true` | Mounted + git/gh remotes work | NOT mounted |
| `private_repo_mode=false` | NOT mounted | Mounted + git/gh remotes work |

**Note**: Repos of the "wrong" visibility are NOT mounted at all (not just blocked at operation time). This provides defense in depth and avoids user confusion from seeing repos they cannot interact with remotely.

Both git AND gh operations must respect the same mode restrictions.

## Threat Model

Before describing the solution, we explicitly state the threats we're defending against:

### Attackers and Trust Boundaries

| Entity | Trust Level | Capabilities |
|--------|-------------|--------------|
| Launcher (host process) | Fully trusted | Registers sessions, starts containers |
| Gateway sidecar | Fully trusted | Enforces all policies |
| jib container | Partially trusted | Can execute arbitrary code, but network-isolated |
| External attacker | Untrusted | Cannot reach gateway (not exposed outside Docker network) |

### Attack Scenarios

1. **Compromised container tries to access wrong-visibility repos**
   - Defense: Session mode is set by launcher before container starts; container cannot change it
   - Defense: Network-verified container identity (source IP on Docker network)

2. **Compromised container tries to claim another session**
   - Defense: Session-container binding verified via Docker network source IP
   - Defense: Session IDs are 256-bit random, infeasible to guess

3. **Compromised container tries to register a new session**
   - Defense: Session registration requires launcher secret, not gateway secret
   - Defense: Containers only receive per-session tokens, not registration credentials

4. **Container makes request without session header**
   - Defense: **Fail closed** - requests without valid session are denied when session mode is deployed

5. **Attacker enumerates session IDs**
   - Defense: Rate limiting on session lookups (10 failures per minute per source IP)
   - Defense: 256-bit session IDs make brute force infeasible

6. **Gateway restart invalidates sessions**
   - Defense: Session persistence to disk with atomic writes
   - Defense: Containers get 401/403 on invalid session; launcher must be restarted to recover

### Out of Scope

- **Kernel escapes**: Container escaping to host is out of scope (use other defenses)
- **Supply chain attacks**: Compromised dependencies in container images
- **Side channels**: Timing attacks on session validation (mitigated by constant-time comparison)

## Decision

Implement **per-container session management** where the launcher (not the container) registers mode at startup and the gateway enforces operations on a per-session basis.

### Architecture

```
                          ┌─────────────────┐
                          │    Launcher     │
                          │  (host process) │
                          └────────┬────────┘
                                   │ 1. Register session (launcher_secret)
                                   │    Returns: session_token
                                   ▼
┌─────────────────────┐     ┌─────────────────────┐
│  jib container A    │     │  jib container B    │
│  mode: private      │     │  mode: public       │
│  token: tok_abc123  │     │  token: tok_xyz789  │
│  IP: 172.18.0.3     │     │  IP: 172.18.0.4     │
└─────────┬───────────┘     └─────────┬───────────┘
          │ 2. Request with           │
          │    session_token          │
          ▼                           ▼
┌─────────────────────────────────────────────────┐
│              Gateway Sidecar                     │
│                                                  │
│  Sessions:                                       │
│    tok_abc123 -> {mode: private, ip: 172.18.0.3}│
│    tok_xyz789 -> {mode: public, ip: 172.18.0.4} │
│                                                  │
│  On each request:                                │
│    1. Validate session_token exists             │
│    2. Verify source IP matches session          │
│    3. Enforce mode for repository operation     │
└─────────────────────────────────────────────────┘
```

### Key Components

#### 1. Session Manager (NEW: `gateway-sidecar/session_manager.py`)

Thread-safe session storage with disk persistence:
- Session registration (launcher only) and unregistration
- Automatic expiry (24h TTL) with heartbeat renewal
- Container-to-session binding verified by source IP
- Disk persistence with atomic writes for gateway restart recovery

```python
@dataclass
class Session:
    session_token: str           # 256-bit random token for requests
    container_id: str            # Docker container ID for audit
    container_ip: str            # Expected source IP for verification
    mode: Literal["private", "public"]
    created_at: datetime
    last_seen: datetime
    expires_at: datetime

# Persistence: ~/.jib-gateway/sessions.json (atomic write via rename)
```

#### 2. Gateway Session Endpoints

```
POST /api/v1/sessions
  Auth: Bearer {launcher_secret}  # NOT gateway_secret - separate credential
  Body: {
    "container_id": "jib-xxx",
    "container_ip": "172.18.0.3",  # Expected source IP for verification
    "mode": "private"|"public"
  }
  Response: {"success": true, "session_token": "tok_..."}
  Rate limit: 10 registrations per minute per source IP

DELETE /api/v1/sessions/{session_token}
  Auth: Bearer {launcher_secret}  # Only launcher can delete sessions
  Response: {"success": true}
  Note: Containers CANNOT delete sessions - only the launcher can

POST /api/v1/sessions/{session_token}/heartbeat
  Auth: Bearer {session_token}
  Response: {"success": true, "expires_at": "..."}
  Purpose: Extend session TTL for long-running containers

GET /api/v1/repos/visibility
  Auth: Bearer {launcher_secret}  # Used by launcher during mount filtering
  Query: ?repos=owner/repo1,owner/repo2
  Response: {"owner/repo1": "public", "owner/repo2": "private"}
```

**Authentication hierarchy**:
- `launcher_secret`: Held by launcher only; can register/delete sessions, query visibility
- `session_token`: Per-container; can make git/gh requests, send heartbeats
- `gateway_secret`: Legacy; used for backwards-compatible non-session requests

#### 3. Per-Session Policy Enforcement

Modify `check_private_repo_access()` to require session when session mode is deployed:

```python
# Environment variable to enable session-based mode
REQUIRE_SESSION_AUTH = os.environ.get("REQUIRE_SESSION_AUTH", "false")

def check_private_repo_access(
    operation: str,
    session_token: str | None = None,
    source_ip: str | None = None,
    ...
) -> PrivateRepoPolicyResult:
    # FAIL CLOSED: If session mode is deployed, require valid session
    if REQUIRE_SESSION_AUTH == "true":
        if not session_token:
            return PrivateRepoPolicyResult(
                allowed=False,
                reason="Session authentication required but no session token provided",
            )
        session = session_manager.get_session(session_token)
        if not session:
            return PrivateRepoPolicyResult(
                allowed=False,
                reason="Invalid or expired session token",
            )
        if session.container_ip != source_ip:
            log.warning(f"Session IP mismatch: expected {session.container_ip}, got {source_ip}")
            return PrivateRepoPolicyResult(
                allowed=False,
                reason="Session-container binding verification failed",
            )
        session_mode = session.mode
    else:
        # Legacy mode: fall back to global env vars
        session_mode = None

    if session_mode == "private":
        # Only allow private/internal repos
    elif session_mode == "public":
        # Only allow public repos
    else:
        # Legacy: use global env vars (PRIVATE_REPO_MODE / PUBLIC_REPO_ONLY_MODE)
```

#### 4. Session Token in Requests

Container uses session token (not gateway secret) for authentication:

```python
# Container receives session_token via environment variable at startup
# This is set by the launcher AFTER session registration succeeds
headers = {
    "Authorization": f"Bearer {session_token}",
}
# No X-Jib-Session header needed - token IS the session identifier
```

**Security note**: Session token is passed via environment variable. To mitigate `/proc/*/environ` exposure:
- Container runs as non-root user (cannot read other containers' /proc)
- Gateway validates source IP matches registered container IP
- Token is per-container, limiting blast radius if exposed

#### 5. Launcher Registration and Mount Filtering

**Critical**: Session registration MUST happen before container starts. The AI cannot change mode at runtime.

Before starting a container, the launcher:
1. Queries repo visibility from gateway using `launcher_secret`
2. Filters repos based on mode:
   - Private mode: mount ONLY private repos
   - Public mode: mount ONLY public repos
3. Registers session with gateway (receives `session_token`)
4. Passes `session_token` to container via environment variable
5. Starts container with filtered mounts

```python
# Launcher sequence (MUST be atomic - session registration before container start)
def start_container(mode: str, repos: list[str]):
    # 1. Query visibility
    visibility = gateway.get_repos_visibility(repos, auth=launcher_secret)

    # 2. Filter repos by mode
    if mode == "private":
        mount_repos = [r for r in repos if visibility[r] in ("private", "internal")]
    else:
        mount_repos = [r for r in repos if visibility[r] == "public"]

    # 3. Get container IP (pre-allocate from Docker network)
    container_ip = docker.allocate_ip(network="jib-isolated")

    # 4. Register session BEFORE starting container
    response = gateway.register_session(
        container_id=container_id,
        container_ip=container_ip,
        mode=mode,
        auth=launcher_secret
    )
    session_token = response["session_token"]

    # 5. Start container with session token and filtered mounts
    docker.run(
        container_id=container_id,
        ip=container_ip,
        env={"JIB_SESSION_TOKEN": session_token},
        mounts=mount_repos,
    )
```

**Why registration must be pre-container**: If registration happened from within the container, a compromised AI could register with a different mode than intended. The launcher is trusted; the container is not.

#### 6. CLI Interface

```bash
# Default: public repos only (safe default)
jib

# Explicit modes
jib --public-repos
jib --private-repos

# For exec mode
jib --exec --private-repos "process this task"
```

#### 7. Session Lifecycle and Recovery

**Normal lifecycle**:
1. Launcher registers session (receives token)
2. Container starts with token
3. Container sends heartbeat every 6 hours (extends TTL)
4. Container exits → launcher deletes session

**Gateway restart recovery**:
- Sessions persisted to `~/.jib-gateway/sessions.json` with atomic writes
- On startup, gateway loads sessions from disk
- Sessions with expired TTL are pruned on load
- Running containers continue working after gateway restart

**Container restart (without gateway restart)**:
- Container cannot re-register (no launcher_secret)
- Launcher must restart to create new session
- This is intentional: prevents compromised container from changing mode

**Rate limiting**:
- Session registration: 10/minute per source IP
- Failed session lookups: 10/minute per source IP (prevents enumeration)
- Heartbeats: 100/hour per session (DoS protection)

#### 8. Audit Logging

All session events are logged with the following fields:

```json
{
  "event_type": "session_*",
  "timestamp": "ISO8601",
  "session_token_hash": "sha256(token)[:16]",  // NOT the full token
  "container_id": "jib-xxx",
  "container_ip": "172.18.0.3",
  "mode": "private|public",
  "outcome": "success|denied|error",
  "reason": "..."
}
```

Events logged:
- `session_registered`: New session created
- `session_deleted`: Session removed
- `session_expired`: Session TTL expired
- `session_auth_failed`: Invalid token presented
- `session_ip_mismatch`: Source IP doesn't match registered IP
- `session_rate_limited`: Rate limit exceeded

### Files to Modify

| File | Changes |
|------|---------|
| `gateway-sidecar/session_manager.py` | NEW: Session storage, persistence, rate limiting |
| `gateway-sidecar/gateway.py` | Add session endpoints, extract session+IP in all handlers |
| `gateway-sidecar/private_repo_policy.py` | Accept session_token, verify IP, fail-closed logic |
| `jib-launcher/launcher.py` | Session registration, mount filtering, cleanup |
| `jib-launcher/secrets.py` | NEW: Manage launcher_secret separate from gateway_secret |
| `jib-container/wrappers/git-wrapper.py` | Use session_token for auth |
| `jib-container/wrappers/gh-wrapper.py` | Use session_token for auth |
| `jib-container/jib` | Add CLI flags for mode selection (launcher interprets these) |

## Consequences

### Positive

- **Concurrent modes**: Multiple containers can run with different modes simultaneously
- **No sidecar restart**: Mode changes are per-container, sidecar stays running
- **Mount-time filtering**: Wrong-visibility repos not mounted at all (defense in depth)
- **Audit trail**: Session-container binding with IP verification enables tracking
- **Fail-closed security**: Invalid/missing sessions are denied when session mode is deployed
- **Gateway restart recovery**: Sessions persisted to disk

### Negative

- **Complexity**: Additional session management layer with persistence
- **Disk I/O**: Session persistence requires atomic file writes
- **API surface**: More endpoints to maintain
- **Launcher changes**: Significant changes to launcher for registration flow

### Neutral

- **Backwards compatible**: `REQUIRE_SESSION_AUTH=false` (default) uses legacy global env vars
- **Migration path**: Deploy with `REQUIRE_SESSION_AUTH=false` initially, enable after testing

## Security Considerations

1. **Session token generation**: Use `secrets.token_urlsafe(32)` - 256-bit entropy
2. **Session validation**: Constant-time comparison to prevent timing attacks
3. **Session expiry**: Auto-cleanup stale sessions (24h default, extendable via heartbeat)
4. **No session reuse**: Each container gets unique session token
5. **Session-container binding**: Token tied to container_id AND container_ip for verification
6. **Fail-closed behavior**: When `REQUIRE_SESSION_AUTH=true`, requests without valid session are DENIED
7. **IP verification**: Gateway verifies request source IP matches registered container IP
8. **Separate credentials**: Launcher uses `launcher_secret`; containers use per-session `session_token`
9. **Rate limiting**: Protects against enumeration and DoS attacks
10. **Audit logging**: All session events logged with hashed token (not plaintext)
11. **Session persistence**: Atomic writes to prevent corruption; sessions survive gateway restart

### Session Token vs Environment Variable Exposure

Session tokens are passed to containers via environment variables. Risks and mitigations:

| Risk | Mitigation |
|------|------------|
| `/proc/*/environ` readable | Containers run as non-root; can't read other containers |
| Token in error messages | Gateway never logs full tokens, only `sha256(token)[:16]` |
| Token in crash dumps | Container crashes don't expose host-level data |
| Token leaked via logging | Container wrappers don't log Authorization header |

The per-container, IP-verified token model limits blast radius: a leaked token only compromises one container's mode, and only from the expected IP.

## Testing Strategy

1. **Unit tests**:
   - Session registration, expiry, concurrent access
   - Rate limiting enforcement
   - IP verification logic
   - Persistence (write, read, atomic corruption recovery)

2. **Integration tests**:
   - Policy enforcement with session mode
   - Multiple containers with different modes simultaneously
   - Gateway restart with running containers (session persistence)
   - Fail-closed behavior when `REQUIRE_SESSION_AUTH=true`

3. **Security tests**:
   - Attempt to use session token from wrong IP
   - Attempt to register session without launcher_secret
   - Attempt to delete session from container (should fail)
   - Rate limit enforcement under load
   - Session enumeration resistance

4. **Manual verification**:
   - Container A (private) and B (public) with different access
   - Gateway restart while containers running
   - Mode restrictions enforced at both mount time and operation time

## Dependencies

- Gateway sidecar must be running
- Requires existing repo visibility checking infrastructure (`repo_visibility.py`)

## References

- Related PRs: #631 (CLI flags for network mode)
- Existing implementation: `private_repo_policy.py`, `repo_visibility.py`
