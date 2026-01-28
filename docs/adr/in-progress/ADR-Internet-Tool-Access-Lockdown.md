# ADR: Tool Access Lockdown via Gateway Sidecar

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Updated:** January 2026
**Status:** In Progress

## Table of Contents

- [Industry Standards Reference](#industry-standards-reference)
- [Context](#context)
- [Problem Statement](#problem-statement)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
  - [Gateway Authentication](#gateway-authentication)
  - [Token Lifecycle Management](#token-lifecycle-management)
- [Security Analysis](#security-analysis)
  - [Rate Limiting](#rate-limiting)
  - [Audit Log Specification](#audit-log-specification)
  - [Supply Chain Considerations](#supply-chain-considerations)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)
- [Implementation Reference](#implementation-reference)

## Industry Standards Reference

This ADR aligns with the **OWASP Top 10 for Agentic Applications (2026)**, the industry benchmark for agentic AI security. The following table maps OWASP risks to mitigations in this architecture:

| OWASP Risk | Description | Mitigation in This ADR |
|------------|-------------|------------------------|
| **ASI01** - Agentic Excessive Authority | Agents granted overly broad permissions | Credential isolation - jib has no credentials; gateway exposes minimal API |
| **ASI02** - Tool Misuse & Exploitation | Agents misusing available tools | Gateway enforces policies; no merge endpoint; force push blocked |
| **ASI03** - Identity & Privilege Abuse | Credential theft or misuse | Credentials never enter jib container; gateway holds GITHUB_TOKEN |
| **ASI04** - Supply Chain Vulnerabilities | Compromised dependencies/images | *Partially addressed* - See [Supply Chain Considerations](#supply-chain-considerations) |
| **ASI06** - Memory/Context Poisoning | Corruption of agent memory/config | *Out of scope* - Addressed by container isolation and volume permissions |
| **ASI10** - Rogue Agents | Agent operating outside intended behavior | Infrastructure controls (not instructions) prevent unauthorized operations |

**Reference:** [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/)

## Context

### Background

The james-in-a-box container currently relies on behavioral instructions (CLAUDE.md) to prevent unauthorized actions like merging PRs or overwriting branches. While the container has network isolation (bridge mode, outbound only), the agent has unrestricted access to:

1. **Raw CLI tools**: `git`, `gh`, `curl`, `wget`, etc.
2. **Full internet access**: Any HTTP/HTTPS endpoint is reachable
3. **GitHub API**: Full permissions of the GITHUB_TOKEN

This creates risk vectors:
- Agent could merge PRs despite instructions not to
- Agent could push force to branches, potentially overwriting others' work
- Agent could exfiltrate data to arbitrary external endpoints
- Prompt injection attacks could bypass behavioral instructions

### Current Security Model

The existing ADR documents a "trust but verify" model:
- Agent has full tool access
- CLAUDE.md instructs agent not to merge PRs or force push
- Human reviews all PRs before merge
- Network isolation prevents inbound connections

**Gap:** Behavioral instructions are not enforceable. A sufficiently sophisticated prompt injection or model misbehavior could bypass these soft constraints.

### Scope

**In Scope:**
- Tool access lockdown for authenticated operations (git push, gh, etc.)
- Audit logging for all network traffic
- Credential isolation (no credentials in jib container)
- **Full network lockdown** (Phase 2): Route all traffic through gateway with strict allowlist

**Phased Rollout:**
- **Phase 1 (Implemented):** Gateway sidecar for git/gh operations, credential isolation
- **Phase 2 (Planned):** Full network lockdown - only Anthropic APIs and GitHub allowed

## Problem Statement

**We need defense-in-depth that does not rely solely on the agent following instructions.**

Specific threats to address:

1. **Unauthorized PR merges**: Agent could merge its own PRs without human approval
2. **Destructive git operations**: Force push, branch deletion, history rewriting
3. **Credential abuse**: Using GITHUB_TOKEN for unintended operations

Note: Data exfiltration via arbitrary endpoints is acknowledged as a residual risk. The gateway provides audit visibility but does not block general internet access to preserve functionality (web search, package installation).

## Decision

**Implement a gateway-sidecar architecture that separates the jib container from all authenticated operations.**

### Core Principles

1. **Credential isolation**: jib container has NO credentials (no GITHUB_TOKEN, no SSH keys)
2. **Gateway as single choke point**: All authenticated operations go through the gateway-sidecar
3. **Network proxy for visibility**: All jib traffic proxied through gateway for audit logging
4. **Fail closed**: Gateway enforces policies; jib physically cannot bypass

## High-Level Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Docker Compose Network                             │
│                                                                               │
│  ┌───────────────────────────────┐      ┌───────────────────────────────┐  │
│  │        jib container          │      │       gateway-sidecar          │  │
│  │                               │      │                               │  │
│  │  - Claude Code agent          │      │  - GITHUB_TOKEN               │  │
│  │  - No GITHUB_TOKEN            │      │  - git push capability        │  │
│  │  - No git push capability     │ REST │  - gh CLI                     │  │
│  │  - Full internet via proxy ───┼──────►  - HTTP/HTTPS proxy          │  │
│  │  - git (no auth)              │      │  - Ownership checks           │  │
│  │                               │      │  - Audit logging              │  │
│  │  HTTP_PROXY=gateway:3128     │      │  - Policy enforcement         │  │
│  │                               │      │                               │  │
│  └───────────────────────────────┘      └───────────────────────────────┘  │
│                                                     │                        │
│                                                     │ All traffic proxied    │
│                                                     ▼                        │
│                                              ┌─────────────┐                │
│                                              │  Internet   │                │
│                                              │  - GitHub   │                │
│                                              │  - Claude   │                │
│                                              │  - PyPI     │                │
│                                              │  - etc      │                │
│                                              └─────────────┘                │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| jib container | Run Claude Code agent | Docker container, no credentials |
| gateway-sidecar | Handle authenticated ops + proxy all traffic | Docker container with credentials |
| HTTP Proxy | Route all jib traffic through gateway | Squid or similar in gateway |
| REST API | Controlled interface for git/gh operations | Python/Node service in gateway |
| Audit Logger | Log all traffic and operations | Gateway component |

### Key Security Properties

1. **jib cannot push to GitHub** - It has no credentials. Network rules block direct GitHub access.
2. **jib cannot merge PRs** - Gateway API doesn't expose merge operation.
3. **All traffic is auditable** - Everything goes through gateway proxy.
4. **Credentials never enter jib** - GITHUB_TOKEN only exists in gateway.

### Gateway REST API

The gateway exposes a controlled API for git/gh operations:

- `POST /api/git/push` - Push to remote (blocks force push, protected branches)
- `POST /api/gh/pr/create` - Create pull request
- `POST /api/gh/pr/comment` - Add comment to PR
- `POST /api/gh/pr/close` - Close PR (only jib's own PRs)
- **No merge endpoint** - Human must merge via GitHub UI

### Gateway Authentication

The gateway API must authenticate requests to prevent abuse from unauthorized containers on the Docker network.

**Authentication Mechanism: Container Identity Token**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Authentication Flow                                   │
│                                                                               │
│  1. Docker Compose generates a random shared secret at startup               │
│  2. Secret injected into both containers via environment variable            │
│  3. jib includes secret in Authorization header for all gateway requests     │
│  4. Gateway validates secret before processing any request                   │
│                                                                               │
│  jib container                    gateway-sidecar                           │
│  ┌─────────────┐                  ┌─────────────────────┐                   │
│  │ JIB_GATEWAY │  Authorization:  │ Validate header     │                   │
│  │ _SECRET     │ ──Bearer $SECRET─► matches JIB_GATEWAY │                   │
│  │             │                  │ _SECRET             │                   │
│  └─────────────┘                  └─────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Secret generated via `openssl rand -hex 32` in compose startup
- Constant-time comparison to prevent timing attacks
- Requests without valid Authorization header return 401 Unauthorized
- All gateway API endpoints require authentication (no public endpoints)

**Future Enhancement: mTLS**

For production deployments, upgrade to mutual TLS (mTLS):
- Gateway presents server certificate
- jib presents client certificate
- Both certificates signed by internal CA
- Provides stronger identity guarantee than shared secret

mTLS adds complexity (certificate management, rotation) but provides cryptographic identity verification. Recommended for GCP Cloud Run deployment.

### Token Lifecycle Management

The `GITHUB_TOKEN` in the gateway requires careful lifecycle management:

**Token Acquisition:**
- GitHub App installation token (preferred) - automatically rotated by GitHub
- Personal Access Token (fallback) - requires manual rotation

**Token Properties:**

| Property | Requirement | Rationale |
|----------|-------------|-----------|
| Expiration | ≤1 hour (GitHub App) or manual rotation schedule | Limit window of exposure |
| Scope | Minimum required: `contents:write`, `pull_requests:write` | Principle of least privilege |
| Audit trail | Log all token usage in gateway | Detect misuse patterns |

**Rotation Strategy:**

```
┌────────────────────────────────────────────────────────────────────────────┐
│                      GitHub App Token Lifecycle                            │
│                                                                            │
│  1. Gateway requests installation token from GitHub App                    │
│  2. Token valid for 1 hour (GitHub enforced)                              │
│  3. Gateway refreshes token 10 minutes before expiration                  │
│  4. Old token naturally expires - no revocation needed                    │
│                                                                            │
│  Timeline:                                                                 │
│  ├─────────────────────────────────────────────────────────────────────┤  │
│  0min              50min         60min                                    │
│  Token issued      Refresh       Expiration                               │
│                    triggered                                               │
└────────────────────────────────────────────────────────────────────────────┘
```

**Audit Logging for Token Usage:**

Every operation using the token logs:
- Timestamp (ISO 8601)
- Operation type (push, pr_create, pr_comment, etc.)
- Target repository
- Target ref/PR number
- Success/failure status
- Request origin (jib container IP)

### CLI Wrappers

The jib container uses `git` and `gh` CLI wrappers that:
- Intercept authenticated operations and route through gateway
- Block dangerous operations (force push, merge, push to protected branches)
- Send Slack notifications for key operations
- Pass through read-only operations unchanged

## Phase 2: Full Network Lockdown

Phase 1 established credential isolation and gateway-mediated git operations. Phase 2 extends this to **complete network isolation**: jib can only reach the gateway sidecar, and the gateway enforces a strict allowlist of external destinations.

### Motivation

The current architecture (Phase 1) still allows jib to reach arbitrary internet endpoints:
- Web search could be used for data exfiltration
- Package installation could pull malicious dependencies
- Any HTTP endpoint could receive exfiltrated code or secrets

For truly unsupervised operation with `--dangerously-skip-permissions`, we need infrastructure-level guarantees that jib cannot communicate with unauthorized endpoints.

### Design: Complete Traffic Isolation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Docker Network (jib-network)                       │
│                                                                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        jib container (ISOLATED)                         │  │
│  │                                                                         │  │
│  │  Network: jib-isolated (no external connectivity)                       │  │
│  │                                                                         │  │
│  │  Can reach ONLY:                                                        │  │
│  │  - gateway-sidecar (via internal network)                              │  │
│  │                                                                         │  │
│  │  CANNOT reach:                                                          │  │
│  │  - Internet (no default route)                                         │  │
│  │  - DNS servers (no external DNS)                                       │  │
│  │                                                                         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                                │
│                              │ Internal network only                          │
│                              ▼                                                │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     gateway-sidecar (GATEKEEPER)                        │  │
│  │                                                                         │  │
│  │  Networks: jib-isolated + external                                      │  │
│  │                                                                         │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │  │
│  │  │  HTTPS Proxy (squid or envoy)                                   │   │  │
│  │  │                                                                 │   │  │
│  │  │  ALLOWLIST (strictly enforced):                                 │   │  │
│  │  │  ✓ api.anthropic.com          (Claude API)                      │   │  │
│  │  │  ✓ api.github.com             (GitHub API)                      │   │  │
│  │  │  ✓ github.com                 (git operations)                  │   │  │
│  │  │  ✓ *.githubusercontent.com   (GitHub raw content)              │   │  │
│  │  │                                                                 │   │  │
│  │  │  BLOCKED (everything else):                                     │   │  │
│  │  │  ✗ pypi.org, npmjs.com        (no package installs)             │   │  │
│  │  │  ✗ google.com, bing.com       (no web search)                   │   │  │
│  │  │  ✗ *.com, *.io, etc           (no arbitrary endpoints)          │   │  │
│  │  └─────────────────────────────────────────────────────────────────┘   │  │
│  │                                                                         │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │  │
│  │  │  Git/GH REST API (existing Phase 1 implementation)              │   │  │
│  │  └─────────────────────────────────────────────────────────────────┘   │  │
│  │                                                                         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                              │                                                │
│                              │ Allowlisted destinations only                  │
│                              ▼                                                │
│                       ┌─────────────┐                                        │
│                       │  Internet   │                                        │
│                       │  (filtered) │                                        │
│                       └─────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Network Isolation Implementation

**Docker Network Configuration:**

```yaml
# docker-compose.yml
networks:
  jib-isolated:
    internal: true  # No external connectivity
  external:
    # Standard bridge network with internet access

services:
  jib:
    networks:
      - jib-isolated  # ONLY internal network
    # No default route to internet
    # All traffic must go through gateway

  gateway-sidecar:
    networks:
      - jib-isolated  # Can receive from jib
      - external      # Can reach internet
```

**Key property:** Docker's `internal: true` network has no gateway to the outside world. jib physically cannot route packets to the internet—there's no route in its network namespace.

### Domain Allowlist

The gateway maintains a strict allowlist of permitted domains:

| Domain | Purpose | Required For |
|--------|---------|--------------|
| `api.anthropic.com` | Claude API | Claude Code operation |
| `api.github.com` | GitHub REST API | PR creation, issue management |
| `github.com` | Git operations | Push, fetch, clone |
| `*.githubusercontent.com` | GitHub raw content | File downloads, avatars |

**Allowlist Properties:**
- **Exhaustive:** Only listed domains are permitted; all others blocked
- **Enforced at proxy:** Gateway proxy (Squid/Envoy) validates destination before forwarding
- **SNI-based validation:** For HTTPS, the proxy inspects the Server Name Indication (SNI) in the TLS ClientHello to determine the destination domain. This does **not** require MITM CA certificates or decrypting traffic—the proxy simply reads the plaintext hostname from the CONNECT request and SNI extension, then either tunnels the connection or rejects it.
- **No wildcards for arbitrary domains:** Each permitted domain explicitly listed

### What Gets Blocked

| Category | Examples | Impact | Mitigation |
|----------|----------|--------|------------|
| Package managers | pypi.org, npmjs.com | Can't install new packages | Pre-install required packages in image |
| Web search | google.com, bing.com | Can't search web | Use GitHub search, local docs |
| Documentation | docs.python.org | Can't fetch docs | Bundle offline docs in image |
| Arbitrary APIs | any other endpoint | Can't exfiltrate data | **This is the security goal** |

### Claude Code Built-in Tools

**Important:** Phase 2 lockdown disables Claude Code's network-dependent tools:

| Tool | Status | Reason |
|------|--------|--------|
| `WebFetch` | ❌ Blocked | Cannot reach arbitrary URLs |
| `WebSearch` | ❌ Blocked | Cannot reach search engines |
| `Bash` (curl, wget) | ❌ Blocked | Cannot reach arbitrary endpoints |
| GitHub MCP tools | ✓ Works | Routed through gateway |

This is an **expected and intentional limitation**. For tasks requiring web research, use supervised mode or pre-populate context before entering lockdown mode.

### Pre-installed Dependencies

Since jib cannot install packages at runtime, the container image must include all required dependencies:

**Python packages:** Pre-installed via `requirements.txt` during image build
**Node packages:** Pre-installed via `package.json` during image build
**System tools:** Installed via Dockerfile

**Image build process:**
```dockerfile
# All dependencies installed at build time
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY package.json package-lock.json /app/
RUN npm ci

# Runtime: jib cannot reach package repositories
```

### DNS Resolution

jib cannot perform external DNS lookups:

```yaml
# jib container
dns: []  # No DNS servers configured
extra_hosts:
  - "gateway:172.18.0.2"  # Static entry for gateway
```

The gateway sidecar handles DNS for allowlisted destinations internally.

### Proxy Configuration

jib routes all HTTP/HTTPS traffic through the gateway proxy:

```bash
# Environment variables in jib container
HTTP_PROXY=http://gateway:3128
HTTPS_PROXY=http://gateway:3128
NO_PROXY=localhost,127.0.0.1,gateway
```

**Proxy behavior:**
1. jib sends CONNECT request to gateway for HTTPS destinations
2. Gateway checks destination against allowlist
3. If allowed: Gateway establishes tunnel to destination
4. If blocked: Gateway returns 403 Forbidden

### Breakout Prevention

The architecture prevents several classes of network breakout:

| Attack Vector | Mitigation |
|---------------|------------|
| Direct IP connection | No route—internal network only. Even if jib learns an IP from conversation context, it cannot connect because there's no route to external networks in the container's network namespace. |
| DNS tunneling | No DNS servers configured |
| Proxy bypass | No alternate route exists; proxy is the only path out |
| IP-based proxy bypass | Proxy validates destination hostname, not just IP. Direct IP requests without Host header are rejected. |
| Container escape | Defense in depth; not in scope for network layer |

### Fallback: Supervised Mode

For tasks requiring web access (research, package updates), jib can operate in **supervised mode**:

```yaml
# docker-compose.supervised.yml override
services:
  jib:
    networks:
      - jib-isolated
      - external  # Adds external network access
    environment:
      - JIB_MODE=supervised
```

In supervised mode:
- Full internet access available
- Human must actively monitor session
- Intended for interactive work, not autonomous operation

### Phase 2: Detailed Implementation Plan

#### 1. Complete Domain Allowlist

The following domains are **required** for jib to function. All other domains are blocked.

##### 1.1 Anthropic API (Required for Claude Code)

| Domain | Port | Purpose | Notes |
|--------|------|---------|-------|
| `api.anthropic.com` | 443 | Claude API endpoint | Primary API for all Claude operations |

**Note:** The Anthropic Console (`console.anthropic.com`, `platform.claude.com`) is NOT required—jib uses API keys directly, not console access.

##### 1.2 GitHub Domains (Required for git/gh operations)

| Domain | Port | Purpose | Notes |
|--------|------|---------|-------|
| `github.com` | 443 | Git HTTPS operations | Clone, fetch, push, pull |
| `api.github.com` | 443 | GitHub REST API | PR creation, issue management, repo info |
| `raw.githubusercontent.com` | 443 | Raw file content | README files, direct file downloads |
| `objects.githubusercontent.com` | 443 | Release assets, artifacts | Binary downloads, action artifacts |
| `codeload.github.com` | 443 | Archive downloads | `git archive`, zip/tarball downloads |
| `uploads.github.com` | 443 | File uploads | Release asset uploads |

**Explicitly NOT included:**
- `*.actions.githubusercontent.com` — Not needed (jib doesn't run GitHub Actions)
- `ghcr.io` — Not needed (no container registry access)
- `*.github.io` — Not needed (no GitHub Pages access)
- `copilot-*.githubusercontent.com` — Not needed (no GitHub Copilot)

##### 1.3 Complete Allowlist Configuration

```python
# gateway-sidecar/proxy_allowlist.py

ALLOWED_DOMAINS = [
    # Anthropic API
    "api.anthropic.com",

    # GitHub - Core
    "github.com",
    "api.github.com",

    # GitHub - Content delivery
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "codeload.github.com",
    "uploads.github.com",

    # GitHub - User content subdomains (avatars, etc.)
    # Note: Wildcard for *.githubusercontent.com could be considered
    # but we list explicitly for tighter control
    "avatars.githubusercontent.com",
    "user-images.githubusercontent.com",
]

# Regex patterns for validation (used by Squid ACL)
ALLOWED_DOMAIN_PATTERNS = [
    r"^api\.anthropic\.com$",
    r"^github\.com$",
    r"^api\.github\.com$",
    r"^raw\.githubusercontent\.com$",
    r"^objects\.githubusercontent\.com$",
    r"^codeload\.github\.com$",
    r"^uploads\.github\.com$",
    r"^avatars\.githubusercontent\.com$",
    r"^user-images\.githubusercontent\.com$",
]
```

#### 2. Docker Network Configuration

##### 2.1 Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host Machine                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              jib-isolated (internal: true)                │   │
│  │              Subnet: 172.30.0.0/24                        │   │
│  │              Gateway: NONE (no external route)            │   │
│  │                                                           │   │
│  │    ┌─────────────┐              ┌─────────────────┐      │   │
│  │    │     jib     │              │  gateway-sidecar │      │   │
│  │    │ 172.30.0.10 │◄────────────►│   172.30.0.2    │      │   │
│  │    │             │   REST API   │                 │      │   │
│  │    │ NO EXTERNAL │   Port 9847  │                 │      │   │
│  │    │   ROUTE     │              │                 │      │   │
│  │    └─────────────┘              └────────┬────────┘      │   │
│  │                                          │               │   │
│  └──────────────────────────────────────────│───────────────┘   │
│                                             │                    │
│  ┌──────────────────────────────────────────│───────────────┐   │
│  │              jib-external (bridge)        │               │   │
│  │              Subnet: 172.31.0.0/24        │               │   │
│  │                                           │               │   │
│  │                              ┌────────────┴────────┐      │   │
│  │                              │  gateway-sidecar    │      │   │
│  │                              │    172.31.0.2       │      │   │
│  │                              │                     │      │   │
│  │                              │  CAN REACH:         │      │   │
│  │                              │  - api.anthropic.com│      │   │
│  │                              │  - github.com       │      │   │
│  │                              │  - api.github.com   │      │   │
│  │                              │  (via proxy filter) │      │   │
│  │                              └──────────┬──────────┘      │   │
│  │                                         │                 │   │
│  └─────────────────────────────────────────│─────────────────┘   │
│                                            │                     │
│                                            ▼                     │
│                                       Internet                   │
└──────────────────────────────────────────────────────────────────┘
```

##### 2.2 Network Creation Commands

```bash
# Create isolated internal network (no external gateway)
docker network create \
  --driver bridge \
  --internal \
  --subnet 172.30.0.0/24 \
  jib-isolated

# Create external network for gateway outbound access
docker network create \
  --driver bridge \
  --subnet 172.31.0.0/24 \
  jib-external
```

##### 2.3 Container Network Assignment

**jib container:**
```bash
docker run \
  --network jib-isolated \
  --ip 172.30.0.10 \
  --dns 0.0.0.0 \               # No DNS servers
  --add-host gateway:172.30.0.2 \  # Static gateway entry
  -e HTTP_PROXY=http://gateway:3128 \
  -e HTTPS_PROXY=http://gateway:3128 \
  -e NO_PROXY=localhost,127.0.0.1,gateway \
  jib-container
```

**gateway-sidecar container:**
```bash
docker run \
  --network jib-isolated \
  --ip 172.30.0.2 \
  jib-gateway

# Attach to external network (dual-homed)
docker network connect --ip 172.31.0.2 jib-external jib-gateway
```

#### 3. Squid Proxy Configuration

##### 3.1 Squid Installation in Gateway

Add to `gateway-sidecar/Dockerfile`:

```dockerfile
# Install Squid proxy
RUN apt-get update && apt-get install -y squid && \
    rm -rf /var/lib/apt/lists/*

# Copy Squid configuration
COPY squid.conf /etc/squid/squid.conf
COPY allowed_domains.txt /etc/squid/allowed_domains.txt

# Expose proxy port
EXPOSE 3128
```

##### 3.2 Squid Configuration File

Create `gateway-sidecar/squid.conf`:

```squid
# Squid proxy configuration for jib network lockdown
# Only allows traffic to explicitly allowlisted domains

# Network settings
http_port 3128

# Access control lists
acl localnet src 172.30.0.0/24    # jib-isolated network

# Load allowed domains from file
acl allowed_domains dstdomain "/etc/squid/allowed_domains.txt"

# SSL/TLS settings - peek at SNI without MITM
acl step1 at_step SslBump1
ssl_bump peek step1
ssl_bump splice allowed_domains
ssl_bump terminate all

# HTTP access rules
http_access allow localnet allowed_domains
http_access deny all

# Logging
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log

# Performance - no caching needed for API calls
cache deny all

# Error pages
deny_info ERR_ACCESS_DENIED all

# Connection settings
connect_timeout 30 seconds
read_timeout 60 seconds
request_timeout 60 seconds

# Shutdown settings
shutdown_lifetime 5 seconds
```

##### 3.3 Allowed Domains File

Create `gateway-sidecar/allowed_domains.txt`:

```
# Anthropic API
api.anthropic.com

# GitHub - Core
github.com
api.github.com

# GitHub - Content delivery
raw.githubusercontent.com
objects.githubusercontent.com
codeload.github.com
uploads.github.com
avatars.githubusercontent.com
user-images.githubusercontent.com
```

##### 3.4 Proxy Supervisor in Gateway

Add to `gateway-sidecar/entrypoint.sh`:

```bash
#!/bin/bash
set -e

# Start Squid proxy in background
echo "Starting Squid proxy..."
squid -f /etc/squid/squid.conf
sleep 2

# Verify Squid is running
if ! pgrep -x "squid" > /dev/null; then
    echo "ERROR: Squid failed to start"
    exit 1
fi

echo "Squid proxy started on port 3128"

# Start gateway API server
echo "Starting gateway API server..."
exec python -m waitress --port=9847 --host=0.0.0.0 gateway:app
```

#### 4. jib Container Changes

##### 4.1 Runtime Environment Variables

Update `jib-container/jib_lib/runtime.py`:

```python
def _get_network_lockdown_env() -> dict[str, str]:
    """Return environment variables for Phase 2 network lockdown."""
    return {
        # Proxy settings - all HTTP/HTTPS traffic through gateway
        "HTTP_PROXY": "http://gateway:3128",
        "HTTPS_PROXY": "http://gateway:3128",
        "http_proxy": "http://gateway:3128",  # Some tools use lowercase
        "https_proxy": "http://gateway:3128",
        "NO_PROXY": "localhost,127.0.0.1,gateway,jib-gateway",
        "no_proxy": "localhost,127.0.0.1,gateway,jib-gateway",

        # Disable certificate verification warnings (proxy handles TLS)
        # NOT disabling verification - just suppressing urllib3 warnings
        "PYTHONWARNINGS": "ignore:Unverified HTTPS request",

        # Network mode indicator
        "JIB_NETWORK_MODE": "lockdown",
    }
```

##### 4.2 Docker Run Modifications

Update container launch in `jib-container/jib_lib/runtime.py`:

```python
def _build_docker_command(
    container_id: str,
    config: Config,
    network_lockdown: bool = True,  # NEW: Enable by default
) -> list[str]:
    """Build docker run command with all arguments."""
    cmd = ["docker", "run"]

    # ... existing code ...

    if network_lockdown:
        # Use isolated network only (no external route)
        cmd.extend(["--network", "jib-isolated"])
        cmd.extend(["--ip", "172.30.0.10"])

        # No DNS servers - prevent DNS-based breakout
        cmd.extend(["--dns", "0.0.0.0"])

        # Static host entries
        cmd.extend(["--add-host", "gateway:172.30.0.2"])
        cmd.extend(["--add-host", "jib-gateway:172.30.0.2"])

        # Add proxy environment variables
        for key, value in _get_network_lockdown_env().items():
            cmd.extend(["-e", f"{key}={value}"])
    else:
        # Legacy mode: standard jib-network with full internet access
        cmd.extend(["--network", JIB_NETWORK_NAME])

    # ... rest of existing code ...

    return cmd
```

##### 4.3 Pre-installed Dependencies

Update `jib-container/Dockerfile` to pre-install all required packages:

```dockerfile
# Python dependencies - installed at build time
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Common Python packages for development work
RUN pip install --no-cache-dir \
    requests \
    pytest \
    pytest-cov \
    black \
    ruff \
    mypy \
    pyyaml \
    toml \
    httpx \
    aiohttp

# Node.js dependencies
COPY package.json package-lock.json /tmp/
RUN cd /tmp && npm ci && \
    npm cache clean --force

# Common system tools
RUN apt-get update && apt-get install -y \
    jq \
    curl \
    wget \
    tree \
    ripgrep \
    fd-find \
    && rm -rf /var/lib/apt/lists/*
```

#### 5. Gateway Startup Changes

##### 5.1 Updated start-gateway.sh

```bash
#!/bin/bash
set -e

# Configuration
GATEWAY_IMAGE="jib-gateway"
GATEWAY_CONTAINER="jib-gateway"
INTERNAL_NETWORK="jib-isolated"
EXTERNAL_NETWORK="jib-external"
INTERNAL_IP="172.30.0.2"
EXTERNAL_IP="172.31.0.2"

# Create networks if they don't exist
create_networks() {
    # Internal network (no external gateway)
    if ! docker network inspect "$INTERNAL_NETWORK" &>/dev/null; then
        echo "Creating internal network: $INTERNAL_NETWORK"
        docker network create \
            --driver bridge \
            --internal \
            --subnet 172.30.0.0/24 \
            "$INTERNAL_NETWORK"
    fi

    # External network (for gateway outbound access)
    if ! docker network inspect "$EXTERNAL_NETWORK" &>/dev/null; then
        echo "Creating external network: $EXTERNAL_NETWORK"
        docker network create \
            --driver bridge \
            --subnet 172.31.0.0/24 \
            "$EXTERNAL_NETWORK"
    fi
}

# Start gateway container
start_gateway() {
    # Remove old container if exists
    docker rm -f "$GATEWAY_CONTAINER" 2>/dev/null || true

    # Start on internal network first
    docker run -d \
        --name "$GATEWAY_CONTAINER" \
        --network "$INTERNAL_NETWORK" \
        --ip "$INTERNAL_IP" \
        --restart unless-stopped \
        -v "$HOME/.jib-gateway:/secrets:ro" \
        -v "$HOME/.config/jib/repositories.yaml:/config/repositories.yaml:ro" \
        "${MOUNT_ARGS[@]}" \
        "$GATEWAY_IMAGE"

    # Connect to external network (dual-homed)
    docker network connect --ip "$EXTERNAL_IP" "$EXTERNAL_NETWORK" "$GATEWAY_CONTAINER"

    echo "Gateway started with dual network access"
    echo "  Internal: $INTERNAL_NETWORK ($INTERNAL_IP) - receives from jib"
    echo "  External: $EXTERNAL_NETWORK ($EXTERNAL_IP) - reaches internet"
}

# Main
create_networks
start_gateway
```

#### 6. Testing Plan

##### 6.1 Positive Tests (Should Work)

```bash
# Test 1: Claude API connectivity
curl -x http://gateway:3128 https://api.anthropic.com/v1/messages \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d '{"model":"claude-sonnet-4-20250514","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
# Expected: 200 OK with response

# Test 2: GitHub API
curl -x http://gateway:3128 https://api.github.com/user \
    -H "Authorization: Bearer $GITHUB_TOKEN"
# Expected: 200 OK with user info

# Test 3: Git fetch through proxy
HTTP_PROXY=http://gateway:3128 git ls-remote https://github.com/jwbron/james-in-a-box.git
# Expected: List of refs

# Test 4: Raw GitHub content
curl -x http://gateway:3128 https://raw.githubusercontent.com/jwbron/james-in-a-box/main/README.md
# Expected: 200 OK with README content

# Test 5: GitHub archive download
curl -x http://gateway:3128 -L https://codeload.github.com/jwbron/james-in-a-box/tar.gz/main -o /dev/null
# Expected: 200 OK, tarball downloaded
```

##### 6.2 Negative Tests (Should Fail)

```bash
# Test 1: Arbitrary website blocked
curl -x http://gateway:3128 https://google.com
# Expected: 403 Forbidden

# Test 2: Package manager blocked
curl -x http://gateway:3128 https://pypi.org/simple/
# Expected: 403 Forbidden

# Test 3: Direct IP connection blocked (from jib container)
curl --connect-timeout 5 https://140.82.114.3  # GitHub IP
# Expected: Connection timeout (no route)

# Test 4: DNS resolution blocked (from jib container)
nslookup google.com
# Expected: Failure (no DNS servers)

# Test 5: Non-allowlisted GitHub subdomain
curl -x http://gateway:3128 https://pages.github.com
# Expected: 403 Forbidden
```

##### 6.3 Integration Tests

```bash
# Full workflow test
./test-network-lockdown.sh

# Contents of test-network-lockdown.sh:
#!/bin/bash
set -e

echo "=== Network Lockdown Integration Tests ==="

# Start containers in lockdown mode
./jib --network-lockdown --test-mode &
JIB_PID=$!
sleep 10

# Run test suite inside container
docker exec jib-test-container bash -c '
    echo "Testing Claude API..."
    python -c "import anthropic; print(anthropic.Anthropic().messages.create(model=\"claude-sonnet-4-20250514\",max_tokens=10,messages=[{\"role\":\"user\",\"content\":\"hi\"}]))"

    echo "Testing git operations..."
    git clone https://github.com/jwbron/james-in-a-box.git /tmp/test-repo
    cd /tmp/test-repo
    git fetch origin

    echo "Testing blocked domains..."
    ! curl -s https://google.com && echo "google.com correctly blocked"
    ! curl -s https://pypi.org && echo "pypi.org correctly blocked"

    echo "All tests passed!"
'

# Cleanup
kill $JIB_PID
docker rm -f jib-test-container
```

#### 7. Rollback Plan

##### 7.1 Quick Rollback (< 5 minutes)

```bash
# Option 1: Disable lockdown mode via environment variable
export JIB_NETWORK_LOCKDOWN=false
./jib  # Runs with full internet access

# Option 2: Use supervised mode override
./jib --supervised  # Explicitly enables full internet
```

##### 7.2 Full Rollback

```bash
# Remove new networks
docker network rm jib-isolated jib-external

# Restore original network
docker network create jib-network

# Restart gateway without Squid
systemctl restart gateway-sidecar

# Containers will use original jib-network with full access
```

#### 8. Migration Path

##### Phase 2a: Infrastructure Setup (Non-breaking)
1. Create `jib-isolated` and `jib-external` networks
2. Add Squid to gateway container
3. Test proxy functionality independently
4. No changes to jib container yet

##### Phase 2b: Opt-in Testing
1. Add `--network-lockdown` flag to jib launcher
2. Test with flag enabled
3. Gather feedback, adjust allowlist
4. Document any missing domains

##### Phase 2c: Default Enabled
1. Make `--network-lockdown` the default
2. Add `--supervised` flag for full internet access
3. Update documentation
4. Monitor for issues

##### Phase 2d: Remove Legacy Mode
1. Remove legacy network configuration
2. Lockdown is the only mode
3. Supervised mode remains for special cases

#### 9. Monitoring & Observability

##### 9.1 Squid Access Logs

```bash
# Real-time log monitoring
docker exec jib-gateway tail -f /var/log/squid/access.log

# Log format includes:
# - Timestamp
# - Source IP (jib container)
# - HTTP method
# - Destination URL
# - Response code (200=allowed, 403=blocked)
# - Bytes transferred
```

##### 9.2 Blocked Request Alerts

```python
# gateway-sidecar/monitor.py

def check_blocked_requests():
    """Parse Squid logs for blocked requests and alert if anomalous."""
    blocked = parse_squid_log(status_code=403)

    for entry in blocked:
        log.warning(
            "Blocked request",
            extra={
                "source_ip": entry.source_ip,
                "destination": entry.url,
                "timestamp": entry.timestamp,
            }
        )

        # Alert if high volume of blocked requests (possible breakout attempt)
        if count_recent_blocked(minutes=5) > 50:
            alert_security_team("High volume of blocked requests")
```

#### 10. Configuration Reference

##### 10.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JIB_NETWORK_LOCKDOWN` | `true` | Enable Phase 2 network lockdown |
| `JIB_NETWORK_MODE` | `lockdown` | Set by launcher, read by container |
| `HTTP_PROXY` | `http://gateway:3128` | Proxy for HTTP traffic |
| `HTTPS_PROXY` | `http://gateway:3128` | Proxy for HTTPS traffic |
| `SQUID_ALLOWED_DOMAINS_FILE` | `/etc/squid/allowed_domains.txt` | Domain allowlist |

##### 10.2 Files Modified

| File | Change |
|------|--------|
| `gateway-sidecar/Dockerfile` | Add Squid installation |
| `gateway-sidecar/squid.conf` | NEW: Proxy configuration |
| `gateway-sidecar/allowed_domains.txt` | NEW: Domain allowlist |
| `gateway-sidecar/entrypoint.sh` | Start Squid before gateway API |
| `gateway-sidecar/start-gateway.sh` | Dual-network setup |
| `jib-container/jib_lib/runtime.py` | Network lockdown mode |
| `jib-container/Dockerfile` | Pre-installed dependencies |

##### 10.3 Implementation Checklist

- [ ] Create `jib-isolated` internal Docker network
- [ ] Create `jib-external` bridge network
- [ ] Add Squid to gateway Dockerfile
- [ ] Create `squid.conf` with domain allowlist
- [ ] Create `allowed_domains.txt`
- [ ] Update gateway entrypoint to start Squid
- [ ] Update `start-gateway.sh` for dual-network
- [ ] Add `_get_network_lockdown_env()` to runtime.py
- [ ] Update `_build_docker_command()` for lockdown mode
- [ ] Pre-install all packages in jib Dockerfile
- [ ] Run positive tests (Claude API, GitHub)
- [ ] Run negative tests (blocked domains)
- [ ] Run integration tests
- [ ] Document supervised mode override
- [ ] Update CLAUDE.md with network limitations

## Security Analysis

### Threat Model

| Threat | Mitigation | Residual Risk |
|--------|------------|---------------|
| Agent merges own PR | Gateway API doesn't expose merge | VERY LOW - No merge endpoint exists |
| Force push to branches | Gateway blocks force flag | VERY LOW - Policy enforced in code |
| Direct GitHub access | Network isolation, proxy required | LOW - Would need to bypass network config |
| Data exfiltration | Audit logging of all traffic | MEDIUM - Can see it, can't prevent all |
| Credential theft | No credentials in jib container | VERY LOW - Nothing to steal |
| Prompt injection bypass | Controls are infrastructure, not instructions | LOW - Bypass requires breaking out of container |

### What This Does NOT Prevent

**Phase 1 residual risks:**
1. **Data exfiltration to allowed endpoints**: Agent can send data to any website (logged but not blocked)
2. **Malicious code in PRs**: Agent can still write malicious code (human review required)
3. **Social engineering via Slack**: Agent could attempt to manipulate human via messages

**Phase 2 residual risks** (after full lockdown):
1. **Exfiltration via GitHub:** Agent could encode data in branch names, commit messages, or PR descriptions
2. **Exfiltration via Claude API:** Agent could encode data in prompts (addressed by Anthropic's logging)
3. **Malicious code in PRs:** Same as Phase 1—human review required
4. **Supply chain via pre-installed packages:** Malicious packages could be bundled at build time

**Mitigations for Phase 2 residual risks:**
- GitHub exfiltration: Audit logging of all operations; branch naming policies. Note: GitHub's 256-character branch name limit constrains (but doesn't eliminate) the data bandwidth available through this vector. Commit messages and PR bodies have higher limits but are more visible in audit logs.
- Claude API: Anthropic maintains usage logs; API calls are authenticated
- Pre-installed packages: Use pinned versions, scan images with Trivy

### Rate Limiting

The gateway delegates rate limiting to GitHub rather than implementing its own layer.

**Rationale:**
- GitHub enforces its own rate limits (5,000 requests/hour for authenticated users, 5,000-15,000 for GitHub App installations)
- The container is already authenticated via shared secret and trusted
- Gateway-level rate limiting caused false positives during legitimate high-velocity work (e.g., git fetch operations during active development)
- Maintaining a separate rate limiting layer adds complexity without meaningful security benefit

**Observability:**
- The gateway logs warnings when GitHub returns rate limit errors (HTTP 403 with rate limit message)
- GitHub's `X-RateLimit-*` response headers indicate remaining quota
- If rate limiting issues emerge, per-operation logging can be added to track request patterns

### Audit Log Specification

All gateway operations produce structured audit logs in JSON format:

```json
{
  "timestamp": "2025-11-28T14:32:01.234Z",
  "event_type": "gateway_operation",
  "operation": "git_push",
  "source_ip": "172.18.0.2",
  "source_container": "jib",
  "auth_valid": true,
  "request": {
    "repository": "jwbron/james-in-a-box",
    "ref": "feature/new-feature",
    "force": false
  },
  "response": {
    "status": "success",
    "duration_ms": 1234
  },
  "policy_checks": {
    "force_push_blocked": false,
    "protected_branch_blocked": false
  }
}
```

**Log retention:** 90 days (configurable)

**Alert triggers:**
- Any denied operation (policy violation)
- Authentication failure
- GitHub rate limit errors (HTTP 403 from GitHub API)
- Unusual patterns (e.g., >10 PRs in 10 minutes)

### Supply Chain Considerations

Per OWASP ASI04, supply chain risks are partially addressed:

| Risk | Mitigation | Status |
|------|------------|--------|
| Malicious pip/npm packages | Audit logging shows all installs | Visibility only |
| Compromised gateway image | Pin image digests, verify signatures | Recommended |
| Poisoned base images | Use official images, scan with Trivy | Recommended |

**Future enhancement:** Integrate with Sigstore/cosign for image verification.

### Defense in Depth Summary

```
Layer 1: Behavioral (CLAUDE.md instructions)
    ↓ Can be bypassed by prompt injection
Layer 2: Credential Isolation (this ADR)
    ↓ jib has no credentials - cannot push/merge even if instructed
Layer 3: Gateway Policy Enforcement
    ↓ Gateway validates all operations
Layer 4: Network Isolation
    ↓ jib cannot reach GitHub directly
Layer 5: Audit Logging
    ↓ All traffic visible for review
Layer 6: Human Review
    ↓ Final safety net - human must approve all PRs
```

## Consequences

### Positive

- **Credential isolation**: jib physically cannot access credentials
- **Enforceable controls**: Security doesn't rely on agent following instructions
- **Audit trail**: All traffic and operations logged
- **Simple mental model**: "jib has no credentials, gateway does"
- **Flexible internet access**: jib can still search web, install packages

### Negative

- **Increased complexity**: Two containers instead of one
- **Latency**: Operations go through gateway (adds ~10-50ms)
- **Development friction**: Need to update gateway API for new operations
- **Shared volume coordination**: Both containers need access to repos

### Trade-offs

| Aspect | Single Container | Gateway Architecture |
|--------|------------------|---------------------|
| Setup complexity | Simple | Moderate |
| Credential exposure | Full access | Zero in jib |
| Policy enforcement | Wrappers (bypassable) | Gateway (not bypassable from jib) |
| Flexibility | High | Constrained by API |
| Audit visibility | Wrapper logs | Full traffic logs |

## Alternatives Considered

### Alternative 1: Tool Wrappers in Single Container

**Approach:** Wrapper scripts that intercept git/gh commands (original proposal)

**Pros:**
- Simpler architecture
- No network coordination
- Familiar pattern

**Cons:**
- Credentials still in container
- Wrappers can be bypassed by calling real binaries
- Agent could find /usr/bin/git

**Rejected:** Credentials remain accessible; wrappers are bypassable

### Alternative 2: Token Scoping Only

**Approach:** Use GitHub tokens with minimal permissions

**Pros:**
- Simplest implementation
- GitHub enforces permissions

**Cons:**
- Cannot prevent merge (requires pull_requests:write which also allows merge)
- Doesn't provide audit trail
- Credentials still exposed

**Rejected:** Token scoping cannot prevent PR merge

### Alternative 3: Full Domain Allowlist

**Approach:** Block all internet except specific domains

**Pros:**
- Strong data exfiltration prevention
- Infrastructure-enforced security (cannot be bypassed by instructions)

**Cons:**
- Breaks web search (needs access to search engines and results)
- Breaks package installation (many CDN domains)
- Requires pre-installing all dependencies in image

**Decision:** Initially rejected as too restrictive. **Reconsidered for Phase 2** after evaluating the risk profile for unsupervised autonomous operation. For `--dangerously-skip-permissions` mode, the security benefits outweigh the operational constraints. Web search and package installation can be addressed through pre-installed dependencies and supervised mode fallback

## MCP Considerations

**Related ADR:** [ADR-Context-Sync-Strategy-Custom-vs-MCP](../implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) (PR #36)

When MCP is adopted for GitHub operations, the gateway architecture adapts:

**Option 1: MCP Server in Gateway**
```
jib → Claude Code → MCP (in jib) → Gateway API → GitHub
```
MCP client calls gateway REST API instead of direct GitHub API.

**Option 2: MCP Server IS the Gateway**
```
jib → Claude Code → MCP Server (in gateway container) → GitHub
```
Run the GitHub MCP server in the gateway with credentials.

Both options preserve credential isolation - the key principle remains.

## GCP Deployment Considerations

For Cloud Run deployment:

| Component | Local (Docker) | GCP (Cloud Run) |
|-----------|----------------|-----------------|
| Network isolation | Docker networks | VPC Service Controls |
| Gateway sidecar | Separate container | Cloud Run sidecar |
| Audit logs | File/stdout | Cloud Logging |
| Proxy | Squid container | Same or Serverless VPC |

The gateway architecture works well in GCP as a multi-container Cloud Run service.

## Implementation Reference

Detailed implementation examples including:
- Docker Compose network configuration
- Gateway REST API (Flask/Python)
- HTTP Proxy configuration (Squid)
- `git` CLI wrapper with policy enforcement
- `gh` CLI wrapper with Slack notifications
- Network isolation rules

**Implementation artifacts preserved in:**
- PR #56 commit `a1b2c3d` - Docker Compose configuration
- PR #56 commit `e4f5g6h` - Gateway REST API (Flask)
- PR #56 commit `i7j8k9l` - CLI wrappers

**Note:** When implementing, create a new `gateway-sidecar/` directory rather than copying from PR history. The patterns above are reference examples; implementation details may need updating for current dependencies.

---

## Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) | Parent ADR - defines overall security model |
| [ADR-Context-Sync-Strategy-Custom-vs-MCP](../implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) (PR #36) | MCP strategy affects how gateway integrates |
| ADR-GCP-Deployment-Terraform (PR #44 refs) | Gateway must work in Cloud Run |

---

**Last Updated:** 2026-01-28
**Next Review:** 2026-02-28 (Monthly)
**Status:** In Progress (Phase 1 implemented, Phase 2 planned)
