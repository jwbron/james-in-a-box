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
| `private_repo_mode=true` | Mounted + git/gh remotes work | Mounted (read code) but git/gh remotes BLOCKED |
| `private_repo_mode=false` | NOT mounted | Mounted + git/gh remotes work |

Both git AND gh operations must respect the same mode restrictions.

## Decision

Implement **per-container session management** where each container registers its mode at startup and the gateway enforces operations on a per-session basis.

### Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│  jib container A    │     │  jib container B    │
│  mode: private      │     │  mode: public       │
│  session: abc123    │     │  session: xyz789    │
└─────────┬───────────┘     └─────────┬───────────┘
          │                           │
          ▼                           ▼
┌─────────────────────────────────────────────────┐
│              Gateway Sidecar                     │
│  Sessions:                                       │
│    abc123 -> {mode: private, container_id: ...} │
│    xyz789 -> {mode: public, container_id: ...}  │
│                                                  │
│  On each request: validate mode for session     │
└─────────────────────────────────────────────────┘
```

### Key Components

#### 1. Session Manager (NEW: `gateway-sidecar/session_manager.py`)

Thread-safe in-memory session storage with:
- Session registration/unregistration
- Automatic expiry (24h TTL)
- Container-to-session binding

```python
@dataclass
class Session:
    session_id: str
    container_id: str
    mode: Literal["private", "public"]
    created_at: datetime
    last_seen: datetime
```

#### 2. Gateway Session Endpoints

```
POST /api/v1/sessions
  Body: {"session_id": "uuid", "container_id": "jib-xxx", "mode": "private"|"public"}
  Response: {"success": true}

DELETE /api/v1/sessions/{session_id}
  Response: {"success": true}

GET /api/v1/repos/visibility
  Query: ?repos=owner/repo1,owner/repo2
  Response: {"owner/repo1": "public", "owner/repo2": "private"}
```

#### 3. Per-Session Policy Enforcement

Modify `check_private_repo_access()` to accept session mode:

```python
def check_private_repo_access(
    operation: str,
    session_mode: str | None = None,  # "private" | "public" | None
    ...
) -> PrivateRepoPolicyResult:
    if session_mode == "private":
        # Only allow private/internal repos
    elif session_mode == "public":
        # Only allow public repos
    else:
        # Fall back to global env vars
```

#### 4. Session Header in Requests

Container includes session ID in all gateway requests:

```python
headers = {
    "Authorization": f"Bearer {gateway_secret}",
    "X-Jib-Session": session_id,
}
```

#### 5. Launcher Mount Filtering

Before starting a container, the launcher:
1. Queries repo visibility from gateway
2. Filters repos based on mode (don't mount private repos in public mode)
3. Registers session with gateway
4. Passes session ID to container via environment variable

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

### Files to Modify

| File | Changes |
|------|---------|
| `gateway-sidecar/session_manager.py` | NEW: Session storage and management |
| `gateway-sidecar/gateway.py` | Add session endpoints, extract session in all handlers |
| `gateway-sidecar/private_repo_policy.py` | Accept session_mode parameter |
| `jib-container/jib_lib/gateway.py` | Add session registration and visibility API |
| `jib-container/jib_lib/runtime.py` | Session lifecycle, mount filtering |
| `jib-container/jib` | Add CLI flags for mode selection |
| `jib-container/wrappers/git-wrapper.py` | Include session header |
| `jib-container/wrappers/gh-wrapper.py` | Include session header |

## Consequences

### Positive

- **Concurrent modes**: Multiple containers can run with different modes simultaneously
- **No sidecar restart**: Mode changes are per-container, sidecar stays running
- **Mount-time filtering**: Private repos not mounted in public mode (defense in depth)
- **Audit trail**: Session-container binding enables tracking

### Negative

- **Complexity**: Additional session management layer
- **Memory usage**: In-memory session storage (mitigated by TTL expiry)
- **API surface**: More endpoints to maintain

### Neutral

- **Backwards compatible**: Falls back to global env vars if no session provided
- **Security model unchanged**: Same policy enforcement, just per-session instead of global

## Security Considerations

1. **Session ID**: Use `secrets.token_urlsafe(32)` - 256-bit entropy
2. **Session validation**: Constant-time comparison
3. **Session expiry**: Auto-cleanup stale sessions (24h default)
4. **No session reuse**: Each container gets unique session ID
5. **Session-container binding**: Session ID tied to container_id for audit

## Testing Strategy

1. **Unit tests**: Session registration, expiry, concurrent access
2. **Integration tests**: Policy enforcement with session mode, multiple containers
3. **Manual verification**: Container A (private) and B (public) with different access

## Dependencies

- Gateway sidecar must be running
- Requires existing repo visibility checking infrastructure (`repo_visibility.py`)

## References

- Related PRs: #631 (CLI flags for network mode)
- Existing implementation: `private_repo_policy.py`, `repo_visibility.py`
