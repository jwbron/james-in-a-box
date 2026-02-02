# Gateway Credential Injection with OAuth Support

**Status:** Proposed (Updated per review feedback)
**Date:** 2026-02-02
**Task:** beads-qvldc
**Related:** ADR-Git-Isolation-Architecture, egg extraction (beads-94eqz)

### Revision History

| Date | Change |
|------|--------|
| 2026-02-02 | Initial proposal |
| 2026-02-02 | Address PR #695 review feedback: Added Phase 0, CA key management, OAuth lifecycle, trust store mechanism, error handling, logging/testing/rollback considerations |

### Review Feedback Addressed

This revision addresses the following feedback from PR #695 review:

1. **Phase 0 added:** Claude Code behavior analysis now gates implementation (HIGH PRIORITY concern)
2. **CA key management:** Daily rotation strategy, key protection, rotation implementation
3. **Header injection mechanism:** Specified Squid `external_acl_type` approach with ICAP fallback
4. **OAuth token lifecycle:** Token expiration handling, user workflow for refresh
5. **Container trust store:** Specific volume mount + entrypoint mechanism
6. **Error handling:** Failure modes table, graceful degradation, startup validation
7. **Logging:** Explicit requirement to NOT log credentials, verification test
8. **Testing:** Mock API endpoint approach for CI/CD
9. **Rollback plan:** `JIB_DIRECT_ANTHROPIC_AUTH` feature flag, staged rollout

---

## Executive Summary

This proposal extends the gateway sidecar to inject Anthropic API credentials at the proxy layer, ensuring the sandbox container never has direct access to credentials. This supports both API keys and OAuth tokens (for Pro/Max subscribers).

**Key principle:** The sandbox container should have zero credential access. All authentication is handled by the gateway, not the container.

---

## Motivation

Currently, the sandbox container receives Anthropic credentials via:
- Environment variables (`ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`)
- Mounted config files (`~/.claude`, `~/.claude.json`)

This creates security risks:
1. **Credential exposure:** If the sandbox is compromised, credentials are immediately available
2. **Exfiltration risk:** Claude could inadvertently log or transmit credentials
3. **Inconsistent model:** Git credentials are isolated in the gateway, but API credentials are exposed

The gateway already handles all git/GitHub authentication. Extending this to Anthropic API authentication creates a consistent security model where **all credentials live in the gateway**.

---

## Design

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Sandbox Container                                │
│                                                                      │
│   Claude Code runs with NO credentials:                              │
│   - No ANTHROPIC_API_KEY                                             │
│   - No CLAUDE_CODE_OAUTH_TOKEN                                       │
│   - No ~/.claude or ~/.claude.json mounted                           │
│                                                                      │
│   Makes HTTPS requests to api.anthropic.com via proxy                │
│                                                                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               │ HTTPS via Squid proxy
                               │ (no auth headers)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Gateway Sidecar                                  │
│                                                                      │
│   Squid Proxy with SSL Bump for api.anthropic.com:                  │
│                                                                      │
│   1. Intercepts HTTPS connection                                     │
│   2. Terminates TLS (MITM for this domain only)                      │
│   3. Reads credentials from secrets config                           │
│   4. Injects authentication header:                                  │
│      - x-api-key: <api_key>           (for API users)                │
│      - Authorization: Bearer <token>   (for OAuth/Pro/Max)           │
│   5. Re-encrypts and forwards to Anthropic                           │
│                                                                      │
│   Audit log: Every authenticated request logged with correlation ID  │
│                                                                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               │ HTTPS with auth headers
                               ▼
                    ┌─────────────────────┐
                    │   api.anthropic.com │
                    └─────────────────────┘
```

### Authentication Types

| Type | Source | Header Injected | Use Case |
|------|--------|-----------------|----------|
| API Key | `secrets.yaml: anthropic.api_key` | `x-api-key: <key>` | Teams, Enterprise, API users |
| OAuth Token | `secrets.yaml: anthropic.oauth_token` | `Authorization: Bearer <token>` | Pro/Max subscribers |

**OAuth tokens:** Pro/Max users generate OAuth tokens by running `claude setup-token` locally. The token is then stored in the gateway's secrets config.

### OAuth Token Lifecycle

OAuth tokens have different characteristics than API keys and require lifecycle management:

**Token Characteristics:**
- OAuth tokens expire (unlike API keys which are long-lived)
- Token validity period varies by provider configuration
- Expired tokens return 401 Unauthorized responses

**Token Refresh Strategy:**

| Scenario | Detection | Action |
|----------|-----------|--------|
| Token works | 200 response | Continue normally |
| Token expired | 401 response | Log warning, return error to sandbox |
| Token invalid | 401/403 response | Log error, return error to sandbox |

**User Workflow for Token Refresh:**
1. User sees error in Claude Code: "Authentication failed - token may be expired"
2. User runs `claude setup-token` locally to generate new token
3. User runs `jib reconfigure` or restarts jib to reload secrets
4. Gateway picks up new token from secrets.yaml

**Future Enhancement (Out of Scope):**
Automatic token refresh could be implemented later if Anthropic's OAuth supports refresh tokens. This proposal intentionally defers this complexity.

**Error Messaging:**
Gateway should provide clear error messages distinguishing:
- Token expired (401 with specific error code) → "Please run `claude setup-token` to refresh"
- Invalid token format → "Token appears malformed, please regenerate"
- API error (5xx) → "Anthropic API temporarily unavailable"

**Proactive Credential Health Check:**
Add a gateway health endpoint that users can query to check credential status before hitting failures:

```
GET /api/v1/health/credentials
→ {"status": "valid", "type": "api_key", "format_valid": true}
→ {"status": "valid", "type": "oauth", "expires_in": "unknown"}
→ {"status": "expired", "type": "oauth", "message": "Run 'claude setup-token' to refresh"}
→ {"status": "missing", "message": "No Anthropic credentials configured"}
→ {"status": "invalid", "message": "Credential format appears malformed"}
```

This allows proactive monitoring without making actual API calls. The endpoint validates format only - it does not validate with Anthropic's servers.

### Configuration

```yaml
# ~/.config/jib/secrets.yaml (on host machine, mounted into gateway container)
secrets:
  anthropic:
    # ONE of these (not both):
    api_key: "sk-ant-xxxxxxxxxxxx"
    # OR
    oauth_token: "oauth-xxxxxxxxxxxx"  # From `claude setup-token`
```

**Docker Mount Configuration:**
The secrets file is stored on the host and mounted read-only into the gateway container:

```yaml
# docker-compose.yml
services:
  jib-gateway:
    volumes:
      # Mount host secrets into gateway (read-only)
      - ${HOME}/.config/jib/secrets.yaml:/home/gateway/.config/jib/secrets.yaml:ro
```

The gateway's helper script uses `Path.home() / ".config" / "jib" / "secrets.yaml"` which resolves to `/home/gateway/.config/jib/secrets.yaml` inside the container. This path receives the mounted host file.

### SSL Bump Configuration

Squid is configured to perform SSL bump (MITM) **only** for `api.anthropic.com`:

```
# squid.conf additions

# Enable host certificate generation (required for SSL bump)
# Note: Current config uses generate-host-certificates=off for peek/splice only
# This will change to on for SSL bump
https_port 3129 cert=/etc/squid/certs/gateway-ca.pem key=/etc/squid/certs/gateway-ca.key generate-host-certificates=on

# Generate CA certificate for MITM
ssl_bump bump anthropic_api
acl anthropic_api ssl::server_name api.anthropic.com

# All other HTTPS traffic passes through unchanged
ssl_bump splice all
```

### CA Key Management

The gateway CA certificate requires careful management to prevent MITM attacks:

**Generation:**
- CA certificate and private key generated on first gateway startup
- Stored in `/etc/squid/certs/` (gateway container only, not exposed to sandbox)

**Rotation Strategy:**
- **Daily rotation** (not on every restart to avoid breaking in-flight requests)
- Implemented via cron job in gateway container
- New CA cert pushed to sandbox containers via shared volume
- Old cert remains valid for grace period (1 hour) to handle in-flight requests

**Key Protection:**
- Private key file permissions: `0600`, owned by squid user
- Private key never leaves gateway container
- Not included in any logs or debugging output

**Rotation Implementation:**
```python
# gateway-sidecar/ca_manager.py
"""CA certificate management for SSL bump."""

from datetime import datetime, timedelta
from pathlib import Path
import subprocess

CA_CERT_PATH = Path("/etc/squid/certs/gateway-ca.pem")
CA_KEY_PATH = Path("/etc/squid/certs/gateway-ca.key")
CA_VALIDITY_DAYS = 1
CA_GRACE_PERIOD_HOURS = 1

def should_rotate_ca() -> bool:
    """Check if CA cert needs rotation (older than CA_VALIDITY_DAYS)."""
    if not CA_CERT_PATH.exists():
        return True
    cert_age = datetime.now() - datetime.fromtimestamp(CA_CERT_PATH.stat().st_mtime)
    return cert_age > timedelta(days=CA_VALIDITY_DAYS)

def rotate_ca() -> None:
    """Generate new CA certificate, keeping old for grace period."""
    # Implementation: generate new cert, archive old, update trust stores
    ...
```

### Container Trust Store Mechanism

The sandbox container must trust the gateway's CA certificate for SSL bump to work. Here's the specific implementation:

**Mechanism:** Volume mount with entrypoint update

**Implementation:**
```yaml
# docker-compose additions
services:
  jib-container:
    volumes:
      # Mount gateway CA cert into container
      - gateway-ca-cert:/usr/local/share/ca-certificates/gateway:ro
```

**Entrypoint Modification:**
```python
# jib-container/entrypoint.py additions

def update_ca_certificates():
    """Update container trust store with gateway CA cert."""
    gateway_ca_path = Path("/usr/local/share/ca-certificates/gateway/gateway-ca.crt")
    if gateway_ca_path.exists():
        # Debian/Ubuntu: update-ca-certificates
        subprocess.run(["update-ca-certificates"], check=True)
        logger.info("Gateway CA certificate added to trust store")
    else:
        logger.warning("Gateway CA certificate not found - SSL bump will fail")

# Called in entrypoint before starting Claude Code
update_ca_certificates()
```

**Alternative Approaches Considered:**
1. **Rebuild image with cert baked in:** Rejected - requires image rebuild on cert rotation
2. **Mount entire `/etc/ssl/certs/`:** Rejected - overwrites system certs
3. **Environment variable (SSL_CERT_FILE):** Could work for some tools but not all

**Verification:**
```bash
# In sandbox container
curl -v https://api.anthropic.com/health
# Should show: SSL certificate verify ok
# Should NOT show: self-signed certificate in certificate chain
```

### Header Injection

**Recommended Approach:** Squid `external_acl_type` with `request_header_add`

This is simpler than ICAP and provides the header injection capability we need.

**Squid Configuration:**
```
# squid.conf additions for header injection

# External ACL helper that returns the auth header value
external_acl_type anthropic_auth ttl=60 %URI /usr/local/bin/anthropic_auth_helper.py

# ACL that triggers the helper for Anthropic API requests
acl anthropic_api_auth external anthropic_auth

# Add header based on helper response
# The helper returns "OK header_value" or "ERR"
request_header_add x-api-key %{anthropic_auth:header_value} anthropic_api_auth
```

**Helper Script:**
```python
#!/usr/bin/env python3
# gateway-sidecar/anthropic_auth_helper.py
"""External ACL helper for Squid - returns Anthropic auth header value."""

import sys
from pathlib import Path
import yaml

def get_anthropic_credentials() -> tuple[str, str]:
    """Load Anthropic credentials from secrets.

    Returns:
        Tuple of (header_name, header_value)
    """
    secrets_path = Path.home() / ".config" / "jib" / "secrets.yaml"
    with open(secrets_path) as f:
        secrets = yaml.safe_load(f)

    anthropic = secrets.get("secrets", {}).get("anthropic", {})

    if "oauth_token" in anthropic:
        return ("Authorization", f"Bearer {anthropic['oauth_token']}")
    elif "api_key" in anthropic:
        return ("x-api-key", anthropic["api_key"])
    else:
        raise ValueError("No Anthropic credentials configured")

def main():
    """Squid external ACL helper main loop.

    Input: URI from Squid
    Output: OK header_value=<value> or ERR
    """
    try:
        header_name, header_value = get_anthropic_credentials()
    except Exception as e:
        # Log error, return ERR for all requests
        print(f"ERR message=Credential load failed: {e}", flush=True)
        return

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        # Check if this is an Anthropic API request
        if "api.anthropic.com" in line:
            # Return OK with header value
            # Squid will add: x-api-key: <header_value>
            print(f"OK header_value={header_value}", flush=True)
        else:
            # Non-Anthropic request - no header needed
            print("ERR", flush=True)

if __name__ == "__main__":
    main()
```

**Fallback to ICAP:**
If `external_acl_type` + `request_header_add` doesn't support the exact header manipulation needed (e.g., if we need `Authorization: Bearer` which has a space), we'll escalate to ICAP. Prototype both in Phase 2 before committing.

---

## Security Properties

### What This Achieves

1. **Zero credential exposure in sandbox:** Container has no env vars or files with credentials
2. **Single audit point:** All API authentication logged through gateway
3. **Credential rotation:** Gateway can rotate credentials without restarting containers
4. **Consistent model:** Same security model as git/GitHub authentication

### Trust Boundaries

| Component | Trust Level | Has Credentials |
|-----------|-------------|-----------------|
| Gateway Sidecar | Trusted | Yes (reads secrets.yaml) |
| Sandbox Container | Untrusted | No |
| Squid Proxy | Trusted (part of gateway) | Yes (injects headers) |

### Threat Mitigation

| Threat | Mitigation |
|--------|------------|
| Credential theft from container | Credentials don't exist in container |
| Claude logs credentials | No credentials to log |
| Prompt injection extracts key | No key accessible to Claude |
| Compromised container exfiltrates | Nothing to exfiltrate |

---

## Implementation Plan

### Phase 0: Claude Code Behavior Analysis (REQUIRED FIRST)

**Rationale:** Understanding exactly how Claude Code validates credentials at startup is critical. The "placeholder value" fallback could fail in multiple ways.

1. Run Claude Code with strace/network tracing to identify:
   - When credentials are validated (startup vs. first API call)
   - Whether key format is verified locally before use
   - Whether a test API call is made on startup
2. Test startup behavior with:
   - No credentials at all
   - Invalid format credentials
   - Valid format but invalid credentials
3. Document findings to inform Phase 3 implementation
4. **Gate:** Do not proceed to Phase 1 until behavior is fully understood

### Phase 1: Squid SSL Bump Setup

1. Configure Squid for SSL bump on `api.anthropic.com` only
2. Generate gateway CA certificate (see CA Key Management section)
3. Mount CA cert into sandbox container trust store (see Container Trust Store section)
4. Verify HTTPS interception works

### Phase 2: Header Injection

1. Implement credential loading from secrets.yaml
2. Implement Squid helper using `request_header_add` with `external_acl_type` (preferred)
3. If helper approach proves insufficient, escalate to ICAP
4. Configure Squid to use the helper
5. Verify authentication works end-to-end

### Phase 3: Remove Direct Credentials

1. Based on Phase 0 findings:
   - If Claude Code requires env var to start: set placeholder with recognizable pattern
   - If Claude Code can start without credentials: remove entirely
2. Remove `ANTHROPIC_API_KEY` from container environment (or set placeholder)
3. Remove `CLAUDE_CODE_OAUTH_TOKEN` from container environment (or set placeholder)
4. Remove `~/.claude` and `~/.claude.json` mounts
5. Test Claude Code works with proxy-injected credentials
6. **Keep env var support as fallback** controlled by `JIB_DIRECT_ANTHROPIC_AUTH=1` feature flag

### Phase 4: Audit Logging

1. Log all authenticated requests with correlation ID
2. Include request metadata (endpoint, method, response status)
3. Integrate with existing gateway audit logging
4. **Ensure API keys/tokens are NOT logged** (verify squid access log format)

### Phase 5: Documentation

1. Update security documentation
2. Update setup guide for OAuth token configuration
3. Create dedicated ADR section for Claude Code authentication:
   - Add new section to ADR-Git-Isolation-Architecture OR create new ADR-Claude-Authentication
   - Include threat model, implementation details, and operational procedures
   - This is a significant architectural component, not a minor addendum
4. Create troubleshooting guide for auth issues

---

## Error Handling and Fallback

This section specifies behavior for failure modes identified in review.

### Failure Modes

| Failure | Detection | Response | User Impact |
|---------|-----------|----------|-------------|
| Squid SSL bump fails | TLS handshake error | Pass through without MITM (splice) | Request fails with 401 (no auth header) |
| Credential file missing | FileNotFoundError on startup | Gateway refuses to start | User must configure credentials |
| Credential file malformed | YAML parse error | Gateway refuses to start | User must fix secrets.yaml |
| Gateway restart mid-request | Connection reset | Client retries | Brief interruption, recoverable |
| CA cert missing in container | SSL verify fails | Request fails with SSL error | User sees clear error message |
| Expired OAuth token | 401 from Anthropic | Return 401 to sandbox | User prompted to refresh token |

### Graceful Degradation

**Principle:** Fail closed. If credential injection cannot work, don't allow unauthenticated requests.

**No Fallback to Direct Auth by Default:**
When proxy injection is enabled, the sandbox has no credentials. If injection fails, requests fail. This is intentional - we don't want to silently fall back to less secure modes.

**Emergency Override (Rollback):**
For situations where proxy injection is broken and needs quick fix:

```bash
# Enable direct credentials temporarily
export JIB_DIRECT_ANTHROPIC_AUTH=1
jib start

# This re-enables:
# - ANTHROPIC_API_KEY environment variable in container
# - ~/.claude mount (if user has local config)
```

This flag should only be used for emergency rollback, not normal operation.

### Startup Validation

Gateway performs these checks before accepting requests:

```python
def validate_anthropic_config() -> None:
    """Validate Anthropic credential configuration on startup."""
    secrets_path = Path.home() / ".config" / "jib" / "secrets.yaml"

    # Check secrets file exists
    if not secrets_path.exists():
        raise ConfigurationError(
            "Missing secrets.yaml - run 'jib configure' to set up Anthropic credentials"
        )

    # Check secrets file is readable and valid YAML
    try:
        with open(secrets_path) as f:
            secrets = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid secrets.yaml: {e}")

    # Check Anthropic credentials present
    anthropic = secrets.get("secrets", {}).get("anthropic", {})
    if not anthropic.get("api_key") and not anthropic.get("oauth_token"):
        raise ConfigurationError(
            "No Anthropic credentials in secrets.yaml - "
            "add anthropic.api_key or anthropic.oauth_token"
        )

    # Check CA certificate exists (if SSL bump enabled)
    if not CA_CERT_PATH.exists():
        logger.warning("CA certificate missing - will generate on first request")
```

---

## Claude Code Compatibility

**Concern:** Claude Code expects `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` environment variable.

**Investigation needed:**
1. Does Claude Code fail to start without these vars?
2. Can we set a dummy value that Claude Code accepts but doesn't use?
3. Does Claude Code verify the key on startup vs. on first API call?

**Fallback:** If Claude Code requires the env var to start, we can set a placeholder value. The actual authentication happens at the proxy layer regardless of what the container thinks its credentials are.

---

## Testing Plan

### Unit Tests

- Credential loading from secrets.yaml
- Header injection for API key vs. OAuth token
- SSL bump configuration validation

### Integration Tests

```bash
# Test 1: API key authentication
# Configure gateway with API key, make request through container
curl -x http://gateway:3128 https://api.anthropic.com/v1/messages

# Test 2: OAuth token authentication
# Configure gateway with OAuth token, verify Bearer header injected

# Test 3: No credentials in container
# Verify container has no ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
docker exec sandbox env | grep -E "(ANTHROPIC|CLAUDE)" && exit 1

# Test 4: Claude Code works
# Run Claude Code in container, verify it can make API calls
```

### Security Tests

- Verify credentials not accessible from sandbox container
- Verify credentials not in container environment
- Verify credentials not in container filesystem
- Verify audit logging captures all authenticated requests

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `gateway-sidecar/anthropic_auth_injector.py` | CREATE | Header injection logic |
| `gateway-sidecar/squid.conf` | MODIFY | Add SSL bump for api.anthropic.com |
| `gateway-sidecar/squid-allow-all.conf` | MODIFY | Same SSL bump config |
| `gateway-sidecar/entrypoint.py` | MODIFY | Generate CA cert on startup |
| `gateway-sidecar/Dockerfile` | MODIFY | Install SSL bump dependencies |
| `jib-container/Dockerfile` | MODIFY | Trust gateway CA cert |
| `jib-container/entrypoint.py` | MODIFY | Remove credential env vars |
| `bin/jib` | MODIFY | Remove credential mounting |
| `docs/adr/implemented/ADR-Git-Isolation-Architecture.md` | MODIFY | Document Claude auth strategy |
| `docs/setup/anthropic-auth.md` | CREATE | Setup guide for OAuth tokens |

---

## Additional Considerations

### Logging Sensitive Headers

**Risk:** Squid access logs could capture API keys/tokens in request headers.

**Current State:** The existing `logformat squid_json` in squid.conf does not include request headers:
```
logformat squid_json {"time":"%tl","client":"%>a",...}
```

**Requirement:** Ensure no log format change introduces header logging. Add explicit documentation:
```
# squid.conf
# SECURITY: Do not add request headers to log format
# The x-api-key and Authorization headers contain secrets
logformat squid_json {"time":"%tl",...}  # No %>h or %{Header}i
```

**Verification Test:**
```bash
# After implementation, verify no credentials in logs
grep -E "(sk-ant|oauth-|Bearer)" /var/log/squid/access.log && echo "FAIL: credentials in logs"
```

### Testing Without Real Credentials

**Challenge:** CI/CD tests need to verify credential injection without real API keys.

**Solution:** Mock API endpoint for testing:

```python
# tests/mock_anthropic_api.py
"""Mock Anthropic API for testing credential injection."""

from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/v1/messages", methods=["POST"])
def messages():
    """Verify authentication header was injected."""
    auth_header = request.headers.get("x-api-key") or request.headers.get("Authorization")

    if not auth_header:
        return jsonify({"error": "No authentication"}), 401

    if auth_header == "test-api-key" or auth_header == "Bearer test-oauth-token":
        return jsonify({"id": "test", "content": "Mock response"}), 200

    return jsonify({"error": "Invalid credentials"}), 401
```

**Test Configuration:**
```yaml
# Test secrets.yaml
secrets:
  anthropic:
    api_key: "test-api-key"  # Mock endpoint accepts this

# Test squid.conf override
# Point api.anthropic.com to mock server via hosts file or DNS
```

### Rollback Plan

**Scenario:** Credential injection breaks Claude Code in production.

**Quick Rollback (< 1 minute):**
```bash
# Re-enable direct credentials
export JIB_DIRECT_ANTHROPIC_AUTH=1
jib restart
```

**Permanent Rollback (if needed):**
1. Revert Phase 3 changes (restore env var passing)
2. Keep SSL bump infrastructure for future use
3. Document lessons learned

**Feature Flag Implementation:**
```python
# bin/jib
def should_use_proxy_injection() -> bool:
    """Check if proxy credential injection is enabled."""
    # Emergency override
    if os.environ.get("JIB_DIRECT_ANTHROPIC_AUTH") == "1":
        return False

    # Default: use proxy injection
    return True
```

**Staged Rollout:**
1. **Alpha:** Enable for dev/testing only (`JIB_PROXY_AUTH=alpha`)
2. **Beta:** Enable by default with easy override
3. **GA:** Remove direct auth support (future, after proven stable)

---

## Open Questions

### Resolved

1. **Squid helper vs ICAP:** Start with Squid helper using `external_acl_type` + `request_header_add`. Only escalate to ICAP if that proves insufficient. (See Phase 2)

2. **CA cert rotation:** Daily rotation (not on every restart to avoid breaking in-flight requests). See CA Key Management section.

### Remaining

3. **Multiple credentials:** Should we support multiple API keys for different containers?
   - **Recommendation:** Not needed for Phase 1. Add later if multi-tenant use cases emerge.

4. **Rate limiting:** Should the gateway rate-limit API calls per container?
   - **Recommendation:** Out of scope for this proposal. Could be added as future enhancement.

---

## Success Criteria

1. Sandbox container has zero Anthropic credentials (env vars or files)
2. Claude Code functions normally (can make API calls)
3. All API calls authenticated via gateway proxy injection
4. Audit log captures all authenticated requests
5. Supports both API keys and OAuth tokens
6. Documentation updated

---

## Relationship to Egg Extraction

This feature is a **pre-work item** for the egg extraction (beads-94eqz). Once implemented in jib:

1. The credential injection logic will be extracted to egg
2. egg will use the same gateway proxy injection model
3. The security model will be consistent across jib and egg

---

## Next Steps

1. [ ] Approve this proposal
2. [ ] Investigate Claude Code env var requirements
3. [ ] Prototype Squid SSL bump configuration
4. [ ] Begin Phase 1 implementation

---

*This proposal establishes credential isolation for Claude Code, extending the existing gateway security model to cover Anthropic API authentication.*
