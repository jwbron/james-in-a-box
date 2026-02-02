# Gateway Credential Injection with OAuth Support

**Status:** Proposed
**Date:** 2026-02-02
**Task:** beads-qvldc
**Related:** ADR-Git-Isolation-Architecture, egg extraction (beads-94eqz)

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

### Configuration

```yaml
# ~/.config/jib/secrets.yaml (gateway reads this)
secrets:
  anthropic:
    # ONE of these (not both):
    api_key: "sk-ant-xxxxxxxxxxxx"
    # OR
    oauth_token: "oauth-xxxxxxxxxxxx"  # From `claude setup-token`
```

### SSL Bump Configuration

Squid is configured to perform SSL bump (MITM) **only** for `api.anthropic.com`:

```
# squid.conf additions

# Generate CA certificate for MITM
ssl_bump bump anthropic_api
acl anthropic_api ssl::server_name api.anthropic.com

# All other HTTPS traffic passes through unchanged
ssl_bump splice all
```

The gateway generates a CA certificate that:
1. Is mounted into the sandbox container's trust store
2. Is used to sign the MITM certificate for `api.anthropic.com`
3. Is rotated periodically (e.g., on gateway restart)

### Header Injection

A Squid URL rewriter or ICAP service injects the authentication header:

```python
# gateway-sidecar/anthropic_auth_injector.py
"""Inject Anthropic authentication headers via Squid helper."""

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
    """Squid URL rewriter main loop."""
    header_name, header_value = get_anthropic_credentials()

    while True:
        line = sys.stdin.readline()
        if not line:
            break

        # Parse Squid rewriter input
        # Inject header for api.anthropic.com requests
        # Output modified request
        ...
```

Alternative: Use Squid's `request_header_add` directive if the helper approach is too complex.

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

### Phase 1: Squid SSL Bump Setup

1. Configure Squid for SSL bump on `api.anthropic.com` only
2. Generate gateway CA certificate
3. Mount CA cert into sandbox container trust store
4. Verify HTTPS interception works

### Phase 2: Header Injection

1. Implement credential loading from secrets.yaml
2. Implement Squid helper or ICAP service for header injection
3. Configure Squid to use the helper
4. Verify authentication works end-to-end

### Phase 3: Remove Direct Credentials

1. Remove `ANTHROPIC_API_KEY` from container environment
2. Remove `CLAUDE_CODE_OAUTH_TOKEN` from container environment
3. Remove `~/.claude` and `~/.claude.json` mounts
4. Test Claude Code works without direct credentials

### Phase 4: Audit Logging

1. Log all authenticated requests with correlation ID
2. Include request metadata (endpoint, method, response status)
3. Integrate with existing gateway audit logging

### Phase 5: Documentation

1. Update security documentation
2. Update setup guide for OAuth token configuration
3. **Update security proposal doc (ADR-Git-Isolation-Architecture)** to document Claude Code authentication strategy
4. Create troubleshooting guide for auth issues

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

## Open Questions

1. **Squid helper vs ICAP:** Which approach is simpler for header injection?
2. **CA cert rotation:** How often should we rotate? On every gateway restart?
3. **Multiple credentials:** Should we support multiple API keys for different containers?
4. **Rate limiting:** Should the gateway rate-limit API calls per container?

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
