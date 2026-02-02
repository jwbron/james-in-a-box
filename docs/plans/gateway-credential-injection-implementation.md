# Gateway Credential Injection: Implementation Plan

**Status:** Implementation Ready
**Proposal:** PR #695 (`docs/plans/gateway-credential-injection.md`)
**Task:** beads-qvldc
**Date:** 2026-02-02

This document provides a detailed, step-by-step implementation plan for the gateway credential injection proposal. Each phase includes specific file changes, code snippets, dependencies, testing requirements, and success criteria.

**Scope Exclusions:** Rate limiting and multiple credentials are out of scope per proposal requirements.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 0: Claude Code Behavior Analysis](#phase-0-claude-code-behavior-analysis)
3. [Phase 1: Squid SSL Bump Setup](#phase-1-squid-ssl-bump-setup)
4. [Phase 2: Header Injection](#phase-2-header-injection)
5. [Phase 3: Remove Direct Credentials](#phase-3-remove-direct-credentials)
6. [Phase 4: Audit Logging](#phase-4-audit-logging)
7. [Phase 5: Documentation](#phase-5-documentation)
8. [Rollback Procedures](#rollback-procedures)
9. [Testing Matrix](#testing-matrix)
10. [File Change Summary](#file-change-summary)

---

## Prerequisites

Before beginning implementation, ensure the following are in place:

### Environment Requirements

| Requirement | Current State | Action Needed |
|-------------|---------------|---------------|
| Squid with SSL support | `squid-openssl` package installed | None |
| Python 3.11+ in gateway | Confirmed in Dockerfile | None |
| `~/.config/jib/secrets.yaml` support | Not yet implemented | Add in Phase 2 |
| Certificate generation tools | OpenSSL available | None |

### Knowledge Requirements

1. Understanding of Squid SSL bump modes (peek/splice vs. bump)
2. Understanding of gateway.py request flow
3. Understanding of jib-container startup sequence (entrypoint.py)

---

## Phase 0: Claude Code Behavior Analysis

**Goal:** Understand exactly how Claude Code validates credentials at startup to prevent implementation failures.

**Duration Estimate:** Investigation only, no code changes.

### Step 0.1: Prepare Analysis Environment

Create a test script to trace Claude Code's credential handling:

**File:** `gateway-sidecar/scripts/analyze-claude-credentials.sh` (temporary)

```bash
#!/bin/bash
# Analyze Claude Code credential validation behavior

set -euo pipefail

OUTPUT_DIR="/tmp/claude-analysis-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "=== Claude Code Credential Analysis ==="
echo "Output directory: $OUTPUT_DIR"

# Test 1: No credentials at all
echo ""
echo "Test 1: Starting Claude Code with NO credentials..."
unset ANTHROPIC_API_KEY
unset CLAUDE_CODE_OAUTH_TOKEN
timeout 30 strace -f -e trace=network,open,openat,read,write \
    -o "$OUTPUT_DIR/test1-no-creds.strace" \
    claude --help 2>&1 | tee "$OUTPUT_DIR/test1-no-creds.stdout" || true

# Test 2: Invalid format credentials
echo ""
echo "Test 2: Starting Claude Code with INVALID format credentials..."
export ANTHROPIC_API_KEY="invalid-not-a-real-key"
timeout 30 strace -f -e trace=network,open,openat,read,write \
    -o "$OUTPUT_DIR/test2-invalid-format.strace" \
    claude --help 2>&1 | tee "$OUTPUT_DIR/test2-invalid-format.stdout" || true

# Test 3: Valid format but non-working credentials
echo ""
echo "Test 3: Starting Claude Code with VALID FORMAT but fake credentials..."
export ANTHROPIC_API_KEY="sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
timeout 30 strace -f -e trace=network,open,openat,read,write \
    -o "$OUTPUT_DIR/test3-valid-format-fake.strace" \
    claude --help 2>&1 | tee "$OUTPUT_DIR/test3-valid-format-fake.stdout" || true

# Test 4: Network trace for API validation
echo ""
echo "Test 4: Network trace of credential validation..."
export ANTHROPIC_API_KEY="sk-ant-api03-test-key-for-network-analysis"
tcpdump -i any -w "$OUTPUT_DIR/test4-network.pcap" &
TCPDUMP_PID=$!
sleep 2
timeout 30 claude --help 2>&1 | tee "$OUTPUT_DIR/test4-network.stdout" || true
kill $TCPDUMP_PID 2>/dev/null || true

echo ""
echo "=== Analysis Complete ==="
echo "Review output in: $OUTPUT_DIR"
echo ""
echo "Key questions to answer:"
echo "1. Does Claude Code fail to start without ANTHROPIC_API_KEY?"
echo "2. Is the key format validated locally?"
echo "3. Is there a startup API call to validate credentials?"
echo "4. What error messages are shown for each failure mode?"
```

### Step 0.2: Document Findings

Create findings document based on analysis:

**File:** `docs/analysis/claude-code-credential-behavior.md` (new)

Template:
```markdown
# Claude Code Credential Behavior Analysis

**Date:** 2026-02-XX
**Analyst:** jib

## Summary

[Summary of findings]

## Test Results

### Test 1: No Credentials
- **Startup behavior:** [pass/fail]
- **Error message:** [exact message]
- **API calls made:** [yes/no]
- **Files accessed:** [list]

### Test 2: Invalid Format
- **Startup behavior:** [pass/fail]
- **Local validation:** [yes/no]
- **Error message:** [exact message]

### Test 3: Valid Format, Invalid Key
- **Startup behavior:** [pass/fail]
- **When validation occurs:** [startup/first-api-call]
- **API endpoint called:** [if any]

## Implications for Implementation

### Required Environment Variables
- `ANTHROPIC_API_KEY`: [required/optional]
- Format validation: [yes/no, what format]

### Recommended Approach
[Based on findings, which approach from the proposal to use]

## Credential Placeholder Strategy
If a placeholder is needed:
- Format: `[specific format based on findings]`
- Value: `[recommended placeholder]`
```

### Step 0.3: Gate Decision

**Success Criteria for Phase 0:**
- [ ] All 4 test scenarios executed
- [ ] Findings document completed
- [ ] Clear answer to: "Can Claude Code start without credentials?"
- [ ] Clear answer to: "What format must placeholder credentials have?"
- [ ] Recommended implementation approach documented

**Gate:** Do not proceed to Phase 1 until findings are reviewed.

---

## Phase 1: Squid SSL Bump Setup

**Goal:** Configure Squid to perform SSL bump (MITM) only for `api.anthropic.com`.

**Dependencies:** Phase 0 complete (findings inform trust store setup).

### Step 1.1: Create CA Certificate Generation Script

**File:** `gateway-sidecar/scripts/generate-ca-cert.sh` (new)

```bash
#!/bin/bash
# Generate CA certificate for SSL bump
# Called by entrypoint.sh on gateway startup

set -euo pipefail

CA_CERT_DIR="/etc/squid/certs"
CA_CERT="${CA_CERT_DIR}/gateway-ca.pem"
CA_KEY="${CA_CERT_DIR}/gateway-ca.key"
CA_VALIDITY_DAYS=1  # Daily rotation

mkdir -p "$CA_CERT_DIR"

# Check if cert exists and is still valid
if [[ -f "$CA_CERT" && -f "$CA_KEY" ]]; then
    # Check if cert expires within 2 hours
    if openssl x509 -checkend 7200 -noout -in "$CA_CERT" 2>/dev/null; then
        echo "CA certificate still valid, skipping generation"
        exit 0
    fi
    echo "CA certificate expiring soon, regenerating..."
fi

echo "Generating new CA certificate..."

# Generate CA private key (ECDSA for performance)
openssl ecparam -genkey -name prime256v1 -out "$CA_KEY"

# Generate self-signed CA certificate
openssl req -new -x509 -sha256 \
    -key "$CA_KEY" \
    -out "$CA_CERT" \
    -days "$CA_VALIDITY_DAYS" \
    -subj "/CN=jib-gateway-ca/O=jib/OU=credential-injection" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"

# Set restrictive permissions
chmod 600 "$CA_KEY"
chmod 644 "$CA_CERT"

# Export public cert for container trust store (separate file)
cp "$CA_CERT" "${CA_CERT_DIR}/gateway-ca.crt"

echo "CA certificate generated: $CA_CERT"
echo "Valid for $CA_VALIDITY_DAYS day(s)"
```

### Step 1.2: Update Squid Configuration

**File:** `gateway-sidecar/squid.conf` (modify)

Add the following sections. Changes are marked with `# NEW:` comments:

```conf
# ==============================================================================
# Port Configuration
# ==============================================================================

# HTTP/HTTPS proxy port with SSL bump for SNI inspection
# NEW: Enable host certificate generation for api.anthropic.com MITM
http_port 3128 ssl-bump \
    cert=/etc/squid/certs/gateway-ca.pem \
    key=/etc/squid/certs/gateway-ca.key \
    generate-host-certificates=on \
    dynamic_cert_mem_cache_size=16MB \
    tls-dh=prime256v1:/etc/squid/certs/dhparam.pem

# NEW: Initialize SSL certificate database (required for generate-host-certificates=on)
# This stores dynamically generated certificates for bumped connections
sslcrtd_program /usr/lib/squid/security_file_certgen -s /var/lib/squid/ssl_db -M 16MB

# ==============================================================================
# Access Control Lists
# ==============================================================================

# Define local network (jib-isolated subnet)
acl localnet src 172.30.0.0/24

# Load allowed domains from external file
acl allowed_domains dstdomain "/etc/squid/allowed_domains.txt"

# NEW: Anthropic API domain for SSL bump (credential injection)
acl anthropic_api ssl::server_name api.anthropic.com
acl anthropic_api_dst dstdomain api.anthropic.com

# Block direct IP connections (bypass attempts)
# [existing ACLs unchanged...]
acl direct_ipv4 url_regex ^https?://[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+
acl direct_ipv6 url_regex ^https?://\[
acl direct_ip_octal url_regex ^https?://0[0-7]+\.
acl direct_ip_hex url_regex ^https?://0x[0-9a-fA-F]+
acl direct_ip_int url_regex ^https?://[0-9]{9,10}(/|$|:)

# CONNECT method (used for HTTPS tunneling)
acl CONNECT method CONNECT

# ==============================================================================
# SSL Bump Rules (SNI Inspection + Selective MITM)
# ==============================================================================

# Step 1: Peek at the TLS ClientHello to read SNI
acl step1 at_step SslBump1

# NEW: SSL bump decision flow:
# 1. Peek at SNI first (all connections)
# 2. Bump api.anthropic.com for credential injection
# 3. Splice other allowed domains (no MITM)
# 4. Terminate non-allowed domains

ssl_bump peek step1
ssl_bump bump anthropic_api        # NEW: Full MITM for Anthropic API
ssl_bump splice allowed_domains    # Pass-through for other allowed domains
ssl_bump terminate all             # Block everything else

# ==============================================================================
# HTTP Access Rules
# ==============================================================================

# [existing rules unchanged...]
http_access deny direct_ipv4
http_access deny direct_ipv6
http_access deny direct_ip_octal
http_access deny direct_ip_hex
http_access deny direct_ip_int

# Allow CONNECT to allowed domains (HTTPS tunneling)
http_access allow CONNECT localnet allowed_domains

# Allow HTTP to allowed domains
http_access allow localnet allowed_domains

# Deny everything else
http_access deny all

# [rest of config unchanged...]
```

### Step 1.3: Create DH Parameters File

**File:** `gateway-sidecar/scripts/generate-dhparam.sh` (new)

```bash
#!/bin/bash
# Generate DH parameters for SSL bump (one-time, at build time)

set -euo pipefail

DH_FILE="/etc/squid/certs/dhparam.pem"

if [[ -f "$DH_FILE" ]]; then
    echo "DH parameters already exist"
    exit 0
fi

mkdir -p "$(dirname "$DH_FILE")"

echo "Generating DH parameters (this takes a while)..."
# Using 2048-bit DH params as a balance between security and build time:
# - 2048-bit: ~30 seconds to generate, NIST-approved through 2030
# - 4096-bit: ~5-10 minutes to generate, marginally more secure
# For ephemeral key exchange in a local proxy, 2048-bit provides adequate security.
# The connection between sandbox and gateway is already on a private network.
openssl dhparam -out "$DH_FILE" 2048

chmod 644 "$DH_FILE"
echo "DH parameters generated: $DH_FILE"
```

### Step 1.4: Update Gateway Dockerfile

**File:** `gateway-sidecar/Dockerfile` (modify)

Add after existing installations:

```dockerfile
# NEW: Create directories for SSL bump certificates
RUN mkdir -p /etc/squid/certs /var/lib/squid/ssl_db && \
    chown -R proxy:proxy /etc/squid/certs /var/lib/squid/ssl_db

# NEW: Copy certificate generation scripts
COPY scripts/generate-ca-cert.sh /usr/local/bin/
COPY scripts/generate-dhparam.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/generate-*.sh

# NEW: Generate DH parameters at build time (slow, do once)
RUN /usr/local/bin/generate-dhparam.sh

# NEW: Initialize SSL certificate database
RUN /usr/lib/squid/security_file_certgen -c -s /var/lib/squid/ssl_db -M 16MB && \
    chown -R proxy:proxy /var/lib/squid/ssl_db
```

### Step 1.5: Update Gateway Entrypoint

**File:** `gateway-sidecar/entrypoint.sh` (modify)

Add before Squid startup:

```bash
# === Existing content above ===

# NEW: Generate/rotate CA certificate for SSL bump
echo "Checking CA certificate..."
/usr/local/bin/generate-ca-cert.sh

# NEW: Copy CA cert to shared volume for container trust store
if [[ -d "/shared/certs" ]]; then
    cp /etc/squid/certs/gateway-ca.crt /shared/certs/
    echo "CA certificate copied to shared volume"
fi

# Start squid
# [existing squid startup code...]
```

### Step 1.6: Update Container Trust Store

**File:** `jib-container/entrypoint.py` (modify)

Add new function and call it in startup sequence:

```python
def setup_gateway_ca(config: Config, logger: Logger) -> None:
    """Add gateway CA certificate to container trust store for SSL bump."""
    gateway_ca_src = Path("/shared/certs/gateway-ca.crt")
    gateway_ca_dst = Path("/usr/local/share/ca-certificates/gateway-ca.crt")

    if not gateway_ca_src.exists():
        logger.warn("Gateway CA certificate not found - SSL bump may fail")
        return

    # Copy cert to ca-certificates directory
    shutil.copy(gateway_ca_src, gateway_ca_dst)

    # Update system trust store
    result = run_cmd(["update-ca-certificates"], check=False, capture=True)
    if result.returncode == 0:
        logger.success("Gateway CA certificate added to trust store")
    else:
        logger.warn(f"Failed to update CA certificates: {result.stderr}")
```

Add to startup sequence (in `main()`, after `setup_environment`):

```python
with _startup_timer.phase("setup_gateway_ca"):
    setup_gateway_ca(config, logger)
```

**Note on Idempotency:** The `update-ca-certificates` command is idempotent - it can be called multiple times safely. This is important because:
1. The CA cert may be rotated while Claude Code is running
2. Python's `ssl` module caches certificates on startup but Node.js (used by Claude Code) typically re-reads the trust store
3. If the cert changes mid-session, Claude Code should pick up the new cert on next API call

### Step 1.7: Update Docker Compose for Shared Volume

**File:** `docker-compose.yml` or equivalent (modify)

Add shared volume for CA certificate:

```yaml
services:
  jib-gateway:
    volumes:
      - gateway-certs:/shared/certs
      # ... existing volumes

  jib-container:
    volumes:
      - gateway-certs:/shared/certs:ro
      # ... existing volumes

volumes:
  gateway-certs:
```

### Phase 1 Testing

**Test 1.1: CA Certificate Generation**
```bash
# In gateway container
/usr/local/bin/generate-ca-cert.sh
ls -la /etc/squid/certs/
openssl x509 -in /etc/squid/certs/gateway-ca.pem -text -noout
```

**Test 1.2: SSL Bump Verification**
```bash
# In sandbox container, with gateway running
curl -v --proxy http://jib-gateway:3128 https://api.anthropic.com/
# Should see: SSL certificate verify ok
# Should see: issuer: CN=jib-gateway-ca (our CA)
```

**Test 1.3: Other Domains Not Bumped**
```bash
# Verify google.com uses its real certificate (spliced, not bumped)
# This test assumes google.com is in allowed_domains for testing
curl -v --proxy http://jib-gateway:3128 https://www.google.com/
# Should see: issuer: CN=GTS CA (Google's CA, not ours)
```

**Success Criteria for Phase 1:**
- [ ] CA certificate generates on gateway startup
- [ ] CA certificate copies to shared volume
- [ ] Container trusts gateway CA
- [ ] `api.anthropic.com` connections are bumped (show jib-gateway-ca issuer)
- [ ] Other HTTPS connections are spliced (show original issuer)
- [ ] Squid starts without errors

---

## Phase 2: Header Injection

**Goal:** Inject authentication headers into bumped `api.anthropic.com` requests.

**Dependencies:** Phase 1 complete.

### Step 2.1: Create Secrets Configuration Handler

**File:** `gateway-sidecar/anthropic_credentials.py` (new)

```python
"""Anthropic credential management for header injection."""

import logging
import os
from pathlib import Path
from typing import NamedTuple, Optional

import yaml

log = logging.getLogger(__name__)


class AnthropicCredential(NamedTuple):
    """Anthropic API credential."""
    header_name: str   # "x-api-key" or "Authorization"
    header_value: str  # The actual credential value


# Default secrets path
SECRETS_PATH = Path(os.environ.get(
    "JIB_SECRETS_PATH",
    str(Path.home() / ".config" / "jib" / "secrets.yaml")
))


def load_anthropic_credential() -> Optional[AnthropicCredential]:
    """Load Anthropic credentials from secrets file.

    Supports both API keys and OAuth tokens:
    - api_key: Injected as "x-api-key: <value>"
    - oauth_token: Injected as "Authorization: Bearer <value>"

    Returns:
        AnthropicCredential or None if not configured
    """
    if not SECRETS_PATH.exists():
        log.warning(f"Secrets file not found: {SECRETS_PATH}")
        return None

    try:
        with open(SECRETS_PATH) as f:
            secrets = yaml.safe_load(f)
    except yaml.YAMLError as e:
        log.error(f"Failed to parse secrets file: {e}")
        return None

    anthropic = secrets.get("secrets", {}).get("anthropic", {})

    # Check for OAuth token first (takes precedence)
    if oauth_token := anthropic.get("oauth_token"):
        log.info("Loaded Anthropic OAuth token from secrets")
        return AnthropicCredential(
            header_name="Authorization",
            header_value=f"Bearer {oauth_token}"
        )

    # Fall back to API key
    if api_key := anthropic.get("api_key"):
        log.info("Loaded Anthropic API key from secrets")
        return AnthropicCredential(
            header_name="x-api-key",
            header_value=api_key
        )

    log.warning("No Anthropic credentials found in secrets")
    return None


def validate_credential_format(credential: AnthropicCredential) -> tuple[bool, str]:
    """Validate credential format.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if credential.header_name == "x-api-key":
        # API keys should start with "sk-ant-"
        if not credential.header_value.startswith("sk-ant-"):
            return False, "API key should start with 'sk-ant-'"
        if len(credential.header_value) < 50:
            return False, "API key appears too short"

    elif credential.header_name == "Authorization":
        if not credential.header_value.startswith("Bearer "):
            return False, "OAuth token must be prefixed with 'Bearer '"
        token = credential.header_value[7:]  # Remove "Bearer "
        if len(token) < 20:
            return False, "OAuth token appears too short"

    return True, ""


def get_credential_for_injection() -> Optional[AnthropicCredential]:
    """Get validated credential ready for header injection.

    Returns:
        AnthropicCredential if valid, None otherwise
    """
    credential = load_anthropic_credential()
    if credential is None:
        return None

    is_valid, error = validate_credential_format(credential)
    if not is_valid:
        log.error(f"Invalid credential format: {error}")
        return None

    return credential
```

### Step 2.2: Create Squid External ACL Helper

**File:** `gateway-sidecar/anthropic_auth_helper.py` (new)

```python
#!/usr/bin/env python3
"""Squid external ACL helper for Anthropic API authentication.

This helper is called by Squid for each request to api.anthropic.com.
It returns the authentication header value to inject.

Protocol:
- Input: One line per request with channel ID and URL
- Output: "OK header_name=<name> header_value=<value>" or "ERR message=<msg>"
"""

import logging
import sys
from pathlib import Path

# Add gateway-sidecar to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from anthropic_credentials import get_credential_for_injection

# Configure logging (to stderr, stdout is for Squid protocol)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s anthropic_auth_helper %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)


def main() -> None:
    """Main helper loop - reads requests from stdin, writes responses to stdout."""
    log.info("Anthropic auth helper starting")

    # Load credential once at startup
    credential = get_credential_for_injection()

    if credential is None:
        log.error("No valid Anthropic credentials - all requests will fail")
        # Still enter the loop to respond with errors
    else:
        log.info(f"Credential loaded: {credential.header_name}")

    # Process requests
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                log.info("EOF received, exiting")
                break

            line = line.strip()
            if not line:
                continue

            # Parse request: "channel_id url" or just "url"
            parts = line.split(None, 1)
            channel_id = parts[0] if len(parts) > 1 else "0"
            url = parts[-1]

            log.debug(f"Request: channel={channel_id} url={url}")

            # Only inject for Anthropic API
            if "api.anthropic.com" not in url:
                print(f"{channel_id} ERR message=not_anthropic_api", flush=True)
                continue

            if credential is None:
                print(f"{channel_id} ERR message=no_credentials_configured", flush=True)
                continue

            # Return credential for injection
            # Squid will use adaptation_access to add the header
            # Format: channel_id OK header_name=<name> header_value=<value>
            # Note: Spaces in header_value need URL encoding
            encoded_value = credential.header_value.replace(" ", "%20")
            print(
                f"{channel_id} OK "
                f"header_name={credential.header_name} "
                f"header_value={encoded_value}",
                flush=True
            )
            log.debug(f"Injecting {credential.header_name} header")

        except Exception as e:
            log.exception(f"Error processing request: {e}")
            print(f"0 ERR message=internal_error", flush=True)


if __name__ == "__main__":
    main()
```

### Step 2.3: Alternative - ICAP Server Implementation

If the external ACL helper approach doesn't support the header manipulation needed, implement ICAP:

**File:** `gateway-sidecar/icap_server.py` (new, fallback option)

```python
#!/usr/bin/env python3
"""ICAP server for Anthropic API header injection.

ICAP (Internet Content Adaptation Protocol) allows modifying HTTP requests
as they pass through the proxy. This is more powerful than external ACL
helpers but adds complexity.

Only implement if external_acl_type approach fails for Authorization header.
"""

import logging
import socket
import sys
from pathlib import Path
from threading import Thread
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from anthropic_credentials import get_credential_for_injection, AnthropicCredential

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s icap_server %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

ICAP_PORT = 1344
ICAP_SERVICE = "/anthropic-auth"


class ICAPHandler:
    """Handle ICAP requests for Anthropic API authentication."""

    def __init__(self, credential: Optional[AnthropicCredential]):
        self.credential = credential

    def handle_reqmod(self, request: bytes) -> bytes:
        """Modify request to add authentication header."""
        # Parse ICAP request
        # [ICAP parsing logic]

        if self.credential is None:
            # Return unmodified
            return self._make_icap_response(request, modified=False)

        # Check if this is an Anthropic API request
        if b"api.anthropic.com" not in request:
            return self._make_icap_response(request, modified=False)

        # Inject authentication header
        # Find end of headers, insert before
        # [Header injection logic]

        return self._make_icap_response(modified_request, modified=True)

    def _make_icap_response(self, body: bytes, modified: bool) -> bytes:
        """Construct ICAP response."""
        # [ICAP response construction]
        pass


def run_icap_server():
    """Run the ICAP server."""
    credential = get_credential_for_injection()
    handler = ICAPHandler(credential)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", ICAP_PORT))
    server.listen(5)

    log.info(f"ICAP server listening on port {ICAP_PORT}")

    while True:
        client, addr = server.accept()
        Thread(target=handle_client, args=(client, handler)).start()


if __name__ == "__main__":
    run_icap_server()
```

### Step 2.4: Prototype Both Approaches (REQUIRED)

**Rationale:** The Squid documentation on `request_header_add` with external ACL variables is sparse. Both approaches should be prototyped early in Phase 2 before committing to one.

#### Approach A: External ACL Helper (Primary)

**File:** `gateway-sidecar/squid.conf` (modify)

Add after SSL bump rules:

```conf
# ==============================================================================
# Header Injection for Anthropic API (Credential Injection)
# ==============================================================================

# External ACL helper for Anthropic authentication
# This helper returns the header name and value to inject
external_acl_type anthropic_auth_helper ttl=300 negative_ttl=10 \
    children-max=2 children-startup=1 \
    %URI \
    /opt/gateway/anthropic_auth_helper.py

# ACL that triggers credential injection for Anthropic API
acl anthropic_needs_auth external anthropic_auth_helper

# Inject authentication header based on helper response
# The helper returns: header_name=x-api-key header_value=sk-ant-xxx
# or: header_name=Authorization header_value=Bearer%20xxx
request_header_add x-api-key %{anthropic_auth_helper:header_value} anthropic_needs_auth
```

#### Approach B: ICAP Server (Fallback)

If external ACL approach proves insufficient (e.g., doesn't support `Authorization: Bearer` header with space):

```conf
# ICAP configuration for header injection
# Uses standard ICAP port 1344 - verified no conflicts with other gateway services
icap_enable on
icap_service anthropic_auth reqmod_precache icap://127.0.0.1:1344/anthropic-auth
adaptation_access anthropic_auth allow anthropic_api_dst
```

**Note on ICAP Port:** Port 1344 is the standard ICAP port. This has been verified to not conflict with any other services running on the gateway container.

#### Prototype Testing Checklist

Before committing to either approach, verify:

- [ ] API key injection works (`x-api-key: sk-ant-xxx`)
- [ ] OAuth token injection works (`Authorization: Bearer xxx`)
- [ ] Header value with space handled correctly
- [ ] Performance acceptable (< 10ms added latency)
- [ ] Error handling works (invalid credentials, missing secrets)

### Step 2.5: Create Secrets File Template

**File:** `config-templates/secrets.yaml.example` (new)

```yaml
# JIB Secrets Configuration
# Location: ~/.config/jib/secrets.yaml
# Permissions: 0600 (owner read/write only)

secrets:
  anthropic:
    # Use ONE of the following (not both):

    # Option 1: API Key (for API users, Teams, Enterprise)
    api_key: "sk-ant-api03-your-key-here"

    # Option 2: OAuth Token (for Pro/Max subscribers via `claude setup-token`)
    # oauth_token: "oauth-token-from-claude-setup-token"
```

### Step 2.6: Update Gateway Startup Validation

**File:** `gateway-sidecar/gateway.py` (modify)

Add startup validation:

```python
from anthropic_credentials import get_credential_for_injection, validate_credential_format

def validate_anthropic_config() -> bool:
    """Validate Anthropic credential configuration on startup.

    Returns:
        True if valid, False otherwise (gateway should not start)
    """
    credential = get_credential_for_injection()

    if credential is None:
        log.error(
            "Anthropic credentials not configured. "
            "Create ~/.config/jib/secrets.yaml with anthropic.api_key or anthropic.oauth_token"
        )
        return False

    is_valid, error = validate_credential_format(credential)
    if not is_valid:
        log.error(f"Invalid Anthropic credentials: {error}")
        return False

    log.info(f"Anthropic credentials validated: {credential.header_name}")
    return True


# In main() or initialization:
if not validate_anthropic_config():
    log.error("Gateway startup blocked: invalid Anthropic configuration")
    sys.exit(1)
```

### Phase 2 Testing

**Test 2.1: Credential Loading**
```python
# In gateway container
from anthropic_credentials import get_credential_for_injection
cred = get_credential_for_injection()
print(f"Header: {cred.header_name}")
print(f"Value starts with: {cred.header_value[:20]}...")
```

**Test 2.2: Helper Standalone Test**
```bash
# Test the helper directly
echo "https://api.anthropic.com/v1/messages" | python3 /opt/gateway/anthropic_auth_helper.py
# Should output: 0 OK header_name=x-api-key header_value=sk-ant-xxx...
```

**Test 2.3: End-to-End Header Injection**
```bash
# In sandbox container (with gateway proxy)
# Use curl verbose to see request headers
curl -v --proxy http://jib-gateway:3128 \
    -X POST https://api.anthropic.com/v1/messages \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-3-5-sonnet-20241022","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'

# Verify request succeeds (200) and response includes Claude's reply
# If 401, header injection is not working
```

**Test 2.4: No Credentials in Request**
```bash
# Verify the original request had no credentials
# (We're testing that injection works, not that creds were already there)
tcpdump -i any -A port 3128 | grep -i "x-api-key\|authorization"
# Should NOT see credentials in traffic TO the proxy
# Should see credentials in traffic FROM proxy TO Anthropic (after bump)
```

**Success Criteria for Phase 2:**
- [ ] Secrets file parsed correctly
- [ ] Helper returns correct header format
- [ ] Headers injected into Anthropic API requests
- [ ] API calls succeed with injected credentials
- [ ] Credentials not visible in container or logged

---

## Phase 3: Remove Direct Credentials

**Goal:** Remove credential exposure from sandbox container.

**Dependencies:** Phase 0 findings, Phase 2 complete.

### Step 3.1: Update Container Environment

**File:** `jib-container/entrypoint.py` (modify)

Based on Phase 0 findings, implement one of these approaches:

**Option A: If Claude Code can start without credentials:**

```python
def setup_claude(config: Config, logger: Logger) -> None:
    """Configure Claude Code without exposing credentials."""
    # Remove any leaked credentials from environment
    for var in ["ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"]:
        if var in os.environ:
            logger.info(f"Removing {var} from environment (handled by gateway)")
            del os.environ[var]

    # Set proxy configuration for API calls
    os.environ["HTTP_PROXY"] = "http://jib-gateway:3128"
    os.environ["HTTPS_PROXY"] = "http://jib-gateway:3128"

    # Inform Claude Code that auth is proxy-handled
    os.environ["ANTHROPIC_AUTH_MODE"] = "proxy"
```

**Option B: If Claude Code requires credential env var to start:**

```python
# Placeholder credential (based on Phase 0 format findings)
# Using obviously fake format for easier debugging if it accidentally gets sent
# This format is clearly a placeholder, not a real key that "almost" works
CREDENTIAL_PLACEHOLDER = "sk-ant-PLACEHOLDER-proxy-injected-do-not-use-directly"

def setup_claude(config: Config, logger: Logger) -> None:
    """Configure Claude Code with placeholder credentials."""
    # Set placeholder that passes format validation but isn't used
    if "ANTHROPIC_API_KEY" not in os.environ:
        os.environ["ANTHROPIC_API_KEY"] = CREDENTIAL_PLACEHOLDER
        logger.info("Set placeholder ANTHROPIC_API_KEY (actual auth via gateway)")

    # Set proxy configuration
    os.environ["HTTP_PROXY"] = "http://jib-gateway:3128"
    os.environ["HTTPS_PROXY"] = "http://jib-gateway:3128"
```

### Step 3.2: Update bin/jib Script

**File:** `bin/jib` (modify)

Remove credential mounting:

```bash
# BEFORE (remove these):
# -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
# -v "$HOME/.claude:/home/jib/.claude:ro" \
# -v "$HOME/.claude.json:/home/jib/.claude.json:ro" \

# AFTER: Don't pass credentials to container
# Credentials are injected at the proxy layer

# Add feature flag for emergency rollback
if [[ "${JIB_DIRECT_ANTHROPIC_AUTH:-0}" == "1" ]]; then
    echo "WARNING: Direct Anthropic auth enabled (bypassing proxy injection)"
    ANTHROPIC_ARGS="-e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY"
else
    ANTHROPIC_ARGS=""
fi

docker run \
    $ANTHROPIC_ARGS \
    # ... rest of docker run args
```

### Step 3.3: Add Rollback Feature Flag

**File:** `gateway-sidecar/gateway.py` (modify)

```python
# Feature flag for emergency rollback
DIRECT_ANTHROPIC_AUTH = os.environ.get("JIB_DIRECT_ANTHROPIC_AUTH", "0") == "1"

if DIRECT_ANTHROPIC_AUTH:
    log.warning(
        "JIB_DIRECT_ANTHROPIC_AUTH=1: Proxy credential injection DISABLED. "
        "Container will use direct credentials. This is for emergency rollback only."
    )
```

### Phase 3 Testing

**Test 3.1: Verify No Credentials in Container**
```bash
# In sandbox container
env | grep -iE "anthropic|claude"
# Should NOT show actual API keys
# May show placeholder or ANTHROPIC_AUTH_MODE=proxy

cat ~/.claude.json 2>/dev/null
# Should not exist or contain real credentials

find /home/jib -name "*.json" -exec grep -l "sk-ant" {} \;
# Should return nothing
```

**Test 3.2: Claude Code Functions**
```bash
# In sandbox container
claude --version
claude "Say 'credential injection working' and nothing else"
# Should respond successfully
```

**Test 3.3: Rollback Works**
```bash
# On host, test rollback
export JIB_DIRECT_ANTHROPIC_AUTH=1
export ANTHROPIC_API_KEY="sk-ant-real-key"
jib
# Container should have credentials directly
# Claude should still work
```

**Success Criteria for Phase 3:**
- [ ] Container has no real credentials in environment
- [ ] Container has no credential files mounted
- [ ] Claude Code starts and functions normally
- [ ] API calls succeed through proxy injection
- [ ] Rollback flag enables direct credentials

---

## Phase 4: Audit Logging

**Goal:** Log all authenticated API requests for security audit.

**Dependencies:** Phase 2 complete.

### Step 4.1: Create Audit Logger Module

**File:** `gateway-sidecar/anthropic_audit.py` (new)

```python
"""Audit logging for Anthropic API requests."""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Audit log location
AUDIT_LOG_PATH = Path(os.environ.get(
    "ANTHROPIC_AUDIT_LOG",
    "/var/log/gateway/anthropic-audit.jsonl"
))


def log_anthropic_request(
    method: str,
    path: str,
    status_code: int,
    container_id: Optional[str] = None,
    session_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    request_size: Optional[int] = None,
    response_size: Optional[int] = None,
) -> str:
    """Log an authenticated Anthropic API request.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., /v1/messages)
        status_code: Response status code
        container_id: Container that made the request
        session_id: Session ID for correlation
        duration_ms: Request duration in milliseconds
        request_size: Request body size in bytes
        response_size: Response body size in bytes

    Returns:
        Correlation ID for this request
    """
    correlation_id = str(uuid.uuid4())[:8]

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": correlation_id,
        "service": "anthropic_api",
        "method": method,
        "path": path,
        "status_code": status_code,
        "container_id": container_id,
        "session_id": session_id,
        "duration_ms": duration_ms,
        "request_size_bytes": request_size,
        "response_size_bytes": response_size,
        # SECURITY: Never log credentials
        # header_value is explicitly NOT included
    }

    # Remove None values for cleaner logs
    entry = {k: v for k, v in entry.items() if v is not None}

    # Write to audit log
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Also log to standard logger
    log.info(
        "anthropic_api_request",
        extra=entry
    )

    return correlation_id


def verify_no_credentials_in_logs() -> tuple[bool, str]:
    """Verify audit logs don't contain credentials.

    Returns:
        Tuple of (is_safe, message)
    """
    if not AUDIT_LOG_PATH.exists():
        return True, "No audit log file exists yet"

    credential_patterns = [
        "sk-ant-",
        "oauth-",
        "Bearer ",
        "x-api-key",
    ]

    with open(AUDIT_LOG_PATH) as f:
        for line_num, line in enumerate(f, 1):
            for pattern in credential_patterns:
                if pattern.lower() in line.lower():
                    return False, f"Potential credential leak at line {line_num}: pattern '{pattern}' found"

    return True, "No credential patterns found in logs"
```

### Step 4.2: Integrate Audit Logging with Squid

**File:** `gateway-sidecar/squid.conf` (modify)

Add custom log format for Anthropic requests:

```conf
# ==============================================================================
# Audit Logging for Anthropic API
# ==============================================================================

# Custom format for Anthropic API audit (no credentials!)
# SECURITY: Do not add request headers (%{>h}, %{Header}i) - they contain secrets
logformat anthropic_audit {"timestamp":"%{%Y-%m-%dT%H:%M:%S}tl.%03tu","type":"anthropic_api","method":"%rm","path":"%rp","status":%>Hs,"duration_ms":%tr,"client_ip":"%>a","bytes_sent":%<st,"bytes_received":%>st}

# Log Anthropic API requests to separate audit file
acl anthropic_api_log dstdomain api.anthropic.com
access_log /var/log/squid/anthropic-audit.log anthropic_audit anthropic_api_log
```

### Step 4.3: Add Log Verification Test

**File:** `gateway-sidecar/tests/test_audit_logging.py` (new)

```python
"""Tests for audit logging security."""

import pytest
from pathlib import Path
import tempfile
import json

from anthropic_audit import log_anthropic_request, verify_no_credentials_in_logs


class TestAuditLogging:
    """Test audit logging doesn't leak credentials."""

    def test_log_entry_has_no_credentials(self, tmp_path):
        """Verify log entries don't contain credential data."""
        import anthropic_audit

        # Override log path for test
        test_log = tmp_path / "test-audit.jsonl"
        anthropic_audit.AUDIT_LOG_PATH = test_log

        # Log a request
        log_anthropic_request(
            method="POST",
            path="/v1/messages",
            status_code=200,
            container_id="test-123",
        )

        # Read and verify
        with open(test_log) as f:
            entry = json.loads(f.readline())

        # Should not contain credential fields
        assert "header_value" not in entry
        assert "api_key" not in entry
        assert "oauth_token" not in entry
        assert "authorization" not in entry.keys()

        # Should not contain credential values
        content = test_log.read_text()
        assert "sk-ant-" not in content
        assert "Bearer" not in content

    def test_verify_catches_leaked_credentials(self, tmp_path):
        """Verify the verification function catches leaks."""
        import anthropic_audit

        test_log = tmp_path / "test-audit.jsonl"
        anthropic_audit.AUDIT_LOG_PATH = test_log

        # Write a log with a "leaked" credential
        with open(test_log, "w") as f:
            f.write('{"api_key":"sk-ant-leaked-key"}\n')

        is_safe, msg = verify_no_credentials_in_logs()
        assert not is_safe
        assert "sk-ant-" in msg
```

### Phase 4 Testing

**Test 4.1: Verify Audit Logs Written**
```bash
# Make some API calls, then check logs
cat /var/log/squid/anthropic-audit.log | jq .
# Should show structured entries with method, path, status
```

**Test 4.2: Verify No Credentials in Logs**
```bash
# Security check - no credentials should be logged
grep -riE "sk-ant|oauth-|Bearer" /var/log/squid/
grep -riE "sk-ant|oauth-|Bearer" /var/log/gateway/
# Should return nothing
```

**Success Criteria for Phase 4:**
- [ ] Anthropic API requests logged to audit file
- [ ] Log entries contain correlation ID, method, path, status
- [ ] Log entries do NOT contain credentials
- [ ] Verification test passes

---

## Phase 5: Documentation

**Goal:** Document the new authentication architecture.

### Step 5.1: Update ADR

**File:** `docs/adr/implemented/ADR-Git-Isolation-Architecture.md` (modify)

Add new section:

```markdown
## Claude Code Authentication (Credential Injection)

**Status:** Implemented
**Date:** 2026-02-XX

### Overview

Anthropic API credentials are injected at the gateway proxy layer, ensuring the sandbox container has zero credential access. This extends the git isolation security model to cover API authentication.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Sandbox Container                            │
│                                                                  │
│   Claude Code runs with NO credentials:                          │
│   - No ANTHROPIC_API_KEY environment variable                    │
│   - No ~/.claude or ~/.claude.json mounted                       │
│                                                                  │
│   Makes HTTPS requests to api.anthropic.com via proxy            │
│                                                                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTPS via proxy (no auth headers)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Gateway Sidecar                              │
│                                                                  │
│   Squid Proxy with SSL Bump for api.anthropic.com:              │
│   1. Terminates TLS (MITM for this domain only)                  │
│   2. Reads credentials from secrets.yaml                         │
│   3. Injects x-api-key or Authorization header                   │
│   4. Re-encrypts and forwards to Anthropic                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Security Properties

1. **Credential isolation:** Container never has credentials
2. **Single audit point:** All API auth logged through gateway
3. **Consistent model:** Same security as git credential isolation

### Configuration

Credentials are stored in `~/.config/jib/secrets.yaml`:

```yaml
secrets:
  anthropic:
    api_key: "sk-ant-xxx"      # OR
    oauth_token: "oauth-xxx"   # For Pro/Max via claude setup-token
```

### Rollback

Emergency override: `export JIB_DIRECT_ANTHROPIC_AUTH=1`
```

### Step 5.2: Create Setup Guide

**File:** `docs/setup/anthropic-auth.md` (new)

```markdown
# Configuring Anthropic API Authentication

This guide explains how to configure Anthropic API credentials for jib.

## Overview

Jib uses proxy-based credential injection for security. Your API credentials are stored on the host and injected at the network layer - the sandbox container never has direct access to them.

## Setup

### Option 1: API Key (Recommended for most users)

1. Get your API key from [console.anthropic.com](https://console.anthropic.com)

2. Create the secrets file:
   ```bash
   mkdir -p ~/.config/jib
   cat > ~/.config/jib/secrets.yaml << 'EOF'
   secrets:
     anthropic:
       api_key: "sk-ant-api03-your-key-here"
   EOF
   chmod 600 ~/.config/jib/secrets.yaml
   ```

3. Restart jib to apply changes

### Option 2: OAuth Token (Pro/Max Subscribers)

1. Run `claude setup-token` on your local machine
2. Copy the generated token
3. Add to secrets:
   ```yaml
   secrets:
     anthropic:
       oauth_token: "your-oauth-token"
   ```

## Verification

```bash
# Start jib and verify authentication
jib
claude "Say 'auth working' if you can read this"
```

## Troubleshooting

### "Authentication failed" errors

1. Check secrets file exists and has correct permissions:
   ```bash
   ls -la ~/.config/jib/secrets.yaml
   # Should be: -rw------- (0600)
   ```

2. Verify credentials are valid:
   ```bash
   # Test API key directly (outside jib)
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: YOUR_KEY" \
     -H "content-type: application/json" \
     -d '{"model":"claude-3-5-sonnet-20241022","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
   ```

### Token Expired (OAuth)

OAuth tokens can expire. Regenerate with:
```bash
claude setup-token
# Then update ~/.config/jib/secrets.yaml
```

## Security Notes

- Credentials are never visible inside the container
- All API requests are logged for audit (without credentials)
- Emergency override: `JIB_DIRECT_ANTHROPIC_AUTH=1` (not recommended)
```

### Step 5.3: Update CLAUDE.md

**File:** `CLAUDE.md` (modify)

Add to the "Sandboxed Environment" section:

```markdown
## Anthropic API Authentication

Your API credentials are managed by the gateway sidecar and injected at the proxy layer. The container has no direct access to credentials.

**Configuration:** `~/.config/jib/secrets.yaml` on the host

**Supported methods:**
- `api_key`: Standard Anthropic API key
- `oauth_token`: OAuth token from `claude setup-token` (Pro/Max users)
```

**Success Criteria for Phase 5:**
- [ ] ADR updated with credential injection architecture
- [ ] Setup guide created
- [ ] CLAUDE.md updated
- [ ] All documentation reviewed for accuracy

---

## Rollback Procedures

### Quick Rollback (No Code Changes)

If credential injection breaks Claude Code:

```bash
# On host
export JIB_DIRECT_ANTHROPIC_AUTH=1
export ANTHROPIC_API_KEY="your-real-api-key"
jib restart

# Container will receive credentials directly
```

### Full Rollback (Revert Code Changes)

1. Revert squid.conf to peek/splice only (no bump)
2. Revert entrypoint.py to pass credentials
3. Revert bin/jib to mount credential files

---

## Testing Matrix

| Test | Phase | Command | Expected Result |
|------|-------|---------|-----------------|
| CA cert generation | 1 | `generate-ca-cert.sh` | Cert created in /etc/squid/certs |
| SSL bump works | 1 | `curl -v --proxy ... https://api.anthropic.com` | Shows jib-gateway-ca issuer |
| Other domains not bumped | 1 | `curl -v --proxy ... https://google.com` | Shows Google's CA |
| Credential loading | 2 | Python: `get_credential_for_injection()` | Returns credential tuple |
| Helper standalone | 2 | `echo url | anthropic_auth_helper.py` | Returns OK with header |
| E2E API call | 2 | `claude "test"` | Works through proxy |
| **Gateway down (negative)** | 2 | Stop gateway, then `claude "test"` | Connection error (not 401 auth error) |
| No creds in container | 3 | `env | grep ANTHROPIC` | Empty or placeholder |
| Rollback works | 3 | `JIB_DIRECT_ANTHROPIC_AUTH=1` | Direct creds work |
| Audit logs written | 4 | `cat anthropic-audit.log` | Shows API requests |
| No creds in logs | 4 | `grep sk-ant /var/log/*` | No matches |

### Negative Test: Gateway Down

**Purpose:** Verify that when the gateway is unavailable, the sandbox fails with a connection error (not an authentication error). This confirms credentials are truly proxy-injected, not embedded in the container.

**Test Steps:**
```bash
# 1. Stop gateway
docker stop jib-gateway

# 2. In sandbox, attempt API call
claude "test"

# 3. Expected: Connection refused / proxy unavailable error
# NOT expected: 401 Unauthorized (would indicate creds are in container)

# 4. Restart gateway
docker start jib-gateway
```

**Why This Matters:** If the sandbox has embedded credentials, it might bypass the proxy and connect directly to Anthropic. This test confirms the security model is working correctly.

---

## File Change Summary

### New Files

| File | Phase | Description |
|------|-------|-------------|
| `gateway-sidecar/scripts/generate-ca-cert.sh` | 1 | CA certificate generation |
| `gateway-sidecar/scripts/generate-dhparam.sh` | 1 | DH parameters generation |
| `gateway-sidecar/anthropic_credentials.py` | 2 | Credential loading module |
| `gateway-sidecar/anthropic_auth_helper.py` | 2 | Squid external ACL helper |
| `gateway-sidecar/icap_server.py` | 2 | ICAP fallback (if needed) |
| `gateway-sidecar/anthropic_audit.py` | 4 | Audit logging module |
| `config-templates/secrets.yaml.example` | 2 | Secrets file template |
| `docs/setup/anthropic-auth.md` | 5 | Setup documentation |
| `docs/analysis/claude-code-credential-behavior.md` | 0 | Investigation findings |

### Modified Files

| File | Phase | Changes |
|------|-------|---------|
| `gateway-sidecar/squid.conf` | 1, 2, 4 | SSL bump, header injection, audit logging |
| `gateway-sidecar/Dockerfile` | 1 | Certificate directories, scripts |
| `gateway-sidecar/entrypoint.sh` | 1 | CA cert generation call |
| `gateway-sidecar/gateway.py` | 2, 3 | Startup validation, feature flag |
| `jib-container/entrypoint.py` | 1, 3 | Trust store setup, credential removal |
| `bin/jib` | 3 | Remove credential mounting |
| `docker-compose.yml` | 1 | Shared volume for CA cert |
| `CLAUDE.md` | 5 | Auth documentation |
| `docs/adr/implemented/ADR-Git-Isolation-Architecture.md` | 5 | Credential injection section |

---

## Success Metrics

After full implementation:

1. **Security:** Container has zero credential exposure
2. **Functionality:** Claude Code works normally
3. **Auditability:** All API requests logged with correlation IDs
4. **Operability:** Setup documented, rollback available
5. **Maintainability:** Code modular, testable, documented

---

*Implementation plan created for PR #695. For questions, reference beads-qvldc.*
