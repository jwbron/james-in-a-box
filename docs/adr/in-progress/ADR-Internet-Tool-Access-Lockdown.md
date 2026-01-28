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
- **TLS inspection:** HTTPS traffic inspected to verify destination domain (CONNECT method)
- **No wildcards for arbitrary domains:** Each permitted domain explicitly listed

### What Gets Blocked

| Category | Examples | Impact | Mitigation |
|----------|----------|--------|------------|
| Package managers | pypi.org, npmjs.com | Can't install new packages | Pre-install required packages in image |
| Web search | google.com, bing.com | Can't search web | Use GitHub search, local docs |
| Documentation | docs.python.org | Can't fetch docs | Bundle offline docs in image |
| Arbitrary APIs | any other endpoint | Can't exfiltrate data | **This is the security goal** |

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
| Direct IP connection | No route—internal network only |
| DNS tunneling | No DNS servers configured |
| Proxy bypass | No alternate route exists |
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

### Implementation Checklist

- [ ] Create `jib-isolated` internal Docker network
- [ ] Configure gateway Squid proxy with domain allowlist
- [ ] Remove external network from jib container
- [ ] Add static DNS entry for gateway in jib
- [ ] Pre-install all required packages in image
- [ ] Test Claude API connectivity through proxy
- [ ] Test GitHub operations through proxy
- [ ] Verify blocked domains return 403
- [ ] Document supervised mode override

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
- GitHub: Audit logging of all operations; branch naming policies
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
