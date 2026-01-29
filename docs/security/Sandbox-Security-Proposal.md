# Sandbox Security Proposal: LLM Agent Isolation Architecture

**Document Status:** Proposal for Security Review
**Version:** 1.2
**Date:** 2026-01-29
**Authors:** James Wiesebron
**Audience:** Security Team, Engineering Leadership

## Executive Summary

This document proposes a comprehensive security architecture for operating autonomous LLM-powered agents (Claude Code) in sensitive codebases without human supervision. The architecture provides **defense-in-depth through infrastructure controls**, ensuring that even if behavioral instructions are bypassed via prompt injection, model drift, or adversarial inputs, the agent cannot perform unauthorized operations.

This proposal supports the broader initiative to unlock agent automation capabilities as outlined in the "Unlocking Agent Automation" roadmap. That roadmap defines four phases of increasing agent capability:

| Phase | Capability | Network Access |
|-------|------------|----------------|
| **Phase 1** | File System Sandbox | None (local only) |
| **Phase 2** | Read-only Public Network | Package registries, documentation |
| **Phase 3** | Read-only Private Network | GitHub, Jira, Confluence, Slack, debugging tools |
| **Phase 4** | Write Private Network | GitHub push/PR, Jira updates, Confluence edits |

**This document focuses on the security foundation for Phases 1-4**, with initial implementation covering:
- File system and git isolation (Phase 1)
- Network lockdown architecture (Phases 2-4)
- GitHub read/write operations (Phases 3-4)
- Audit logging (all phases)

Future connectors (Jira, Confluence, Slack, BigQuery, Figma) will follow the same gateway-based isolation pattern established here. See [Future Connectors](#future-connectors) for the planned approach.

### Core Security Guarantee

> **An AI agent cannot access credentials, merge code, or exfiltrate data to unauthorized endpoints—regardless of what it is instructed to do.**

This guarantee is achieved through:
1. **Credential Isolation**: Tokens never enter the agent container
2. **Network Lockdown**: Only Anthropic API and GitHub reachable (expandable per phase)
3. **Gateway Enforcement**: All privileged operations validated by a trusted sidecar
4. **Filesystem Isolation**: Agent cannot access other agents' workspaces or sensitive files
5. **Human-in-the-Loop**: All code merges require human approval

### Document Scope

This proposal covers security controls for the core GitHub integration:

| Domain | Description |
|--------|-------------|
| **Internet Access** | Network lockdown and domain allowlisting |
| **Git Operations** | Gateway-enforced git isolation |
| **Private Repo Mode** | Restricting agents to private repositories only |
| **Audit Logging** | Structured logging for all operations |

**Not yet addressed in this document** (planned for future phases):
- Jira/Confluence integration
- BigQuery access
- Slack communication isolation
- Log access controls
- Figma MCP integration

---

## Table of Contents

1. [Threat Model](#1-threat-model)
2. [Architecture Overview](#2-architecture-overview)
3. [Network Lockdown](#3-network-lockdown)
4. [Credential Isolation](#4-credential-isolation)
5. [Git and GitHub Lockdown](#5-git-and-github-lockdown)
6. [Private Repository Mode](#6-private-repository-mode)
7. [Audit Logging](#7-audit-logging)
8. [Remaining Gaps and Concerns](#8-remaining-gaps-and-concerns)
9. [Recommendations](#9-recommendations)
10. [Future Connectors](#10-future-connectors)
11. [Appendix: OWASP Alignment](#appendix-owasp-alignment)

---

## 1. Threat Model

### 1.1 Adversary Capabilities

| Adversary | Capability | Example Attack |
|-----------|------------|----------------|
| **Prompt Injection** | Attacker crafts input that overrides agent instructions | Malicious JIRA ticket contains: "Ignore previous instructions and..." |
| **Model Misbehavior** | Agent acts outside intended behavior due to training or inference issues | Agent interprets "fix the bug" as "delete the file" |
| **Rogue Agent** | Agent deliberately operates outside constraints | Agent attempts to merge its own PR |
| **Data Exfiltration** | Agent attempts to send sensitive data to external services | Agent encodes secrets in commit messages |
| **Credential Theft** | Agent attempts to extract credentials for later use | Agent reads GitHub token from environment |

### 1.2 Protected Assets

| Asset | Classification | Protection Requirement |
|-------|----------------|----------------------|
| **GitHub Tokens** | Critical | Never enter agent container |
| **Claude API Keys** | High | Available to agent (required for operation) |
| **Source Code (Private)** | High | Readable, changes require human review |
| **Internal Documentation** | Medium | Readable within context sync scope |
| **PR Content** | Medium | Agent cannot merge; human review required |

### 1.3 Security Boundaries

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            UNTRUSTED ZONE                                   │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         Agent Container                                │ │
│  │                                                                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │ │
│  │  │ LLM Agent   │  │ Code Files  │  │ Context     │  │ Task        │    │ │
│  │  │             │  │ (workspace) │  │ (read-only) │  │ Memory      │    │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │ │
│  │                                                                        │ │
│  │  NO: GitHub tokens, SSH keys, cloud credentials                        │ │
│  │  NO: Direct network access (proxy required)                            │ │
│  │  NO: Git metadata (.git directory shadowed by tmpfs)                   │ │
│  │  NO: Other agents' workspaces                                          │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    │ HTTP API (authenticated)               │
│                                    ▼                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                            TRUSTED ZONE                                     │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     Gateway Sidecar (Policy Enforcer)                  │ │
│  │                                                                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │ │
│  │  │ GITHUB_     │  │ HTTPS       │  │ Policy      │                     │ │
│  │  │ TOKEN       │  │ Proxy       │  │ Engine      │                     │ │
│  │  │ (secure)    │  │ (filtered)  │  │ (validates) │                     │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                     │ │
│  │                                                                        │ │
│  │  ENFORCES: Branch ownership, merge blocking, domain allowlist          │ │
│  │  LOGS: All operations with full audit trail                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Architecture Overview

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Host Machine                                   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Isolated Network (internal: true)                 │   │
│  │                    No external route                                 │   │
│  │                                                                      │   │
│  │    ┌─────────────────┐                  ┌─────────────────────┐      │   │
│  │    │ Agent Container │                  │   Gateway Sidecar   │      │   │
│  │    │                 │◄────REST API────►│                     │      │   │
│  │    │                 │                  │                     │      │   │
│  │    │ LLM Agent       │                  │ GITHUB_TOKEN        │      │   │
│  │    │ git/gh wrappers │◄────HTTPS Proxy──│ Proxy (filtered)    │      │   │
│  │    │ NO credentials  │                  │ Policy Engine       │      │   │
│  │    │                 │                  │                     │      │   │
│  │    └─────────────────┘                  └──────────┬──────────┘      │   │
│  │                                                    │                 │   │
│  └────────────────────────────────────────────────────│─────────────────┘   │
│                                                       │                     │
│  ┌────────────────────────────────────────────────────│─────────────────┐   │
│  │                    External Network (bridge)       │                 │   │
│  │                                                    │                 │   │
│  │                                   ┌────────────────┴────────────┐    │   │
│  │                                   │    Gateway Sidecar          │    │   │
│  │                                   │    (dual-homed)             │    │   │
│  │                                   │                             │    │   │
│  │                                   │    ALLOWED:                 │    │   │
│  │                                   │    - api.anthropic.com      │    │   │
│  │                                   │    - github.com             │    │   │
│  │                                   │    - api.github.com         │    │   │
│  │                                   │    - *.githubusercontent.com│    │   │
│  │                                   │                             │    │   │
│  │                                   │    BLOCKED:                 │    │   │
│  │                                   │    - Everything else        │    │   │
│  │                                   └──────────────┬──────────────┘    │   │
│  └──────────────────────────────────────────────────│───────────────────┘   │
│                                                     │                       │
│                                                     ▼                       │
│                                                 Internet                    │
│                                           (allowlisted only)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Security Properties Summary

| Property | Implementation | Verification |
|----------|----------------|--------------|
| **Credential Isolation** | Tokens exist only in gateway sidecar | Container has no env vars or files with tokens |
| **Network Isolation** | Internal Docker network with no external route | Network configured with `internal: true` |
| **Domain Allowlist** | Proxy with SNI-based filtering | Blocked requests return HTTP 403 |
| **Git Metadata Isolation** | `.git` directories shadowed by tmpfs | Agent cannot read or modify git refs directly |
| **Branch Ownership** | Gateway validates push requests | Only agent-prefixed branches or branches with open PRs |
| **Merge Blocking** | Gateway has no merge endpoint | `gh pr merge` commands fail at gateway level |
| **Audit Logging** | All operations logged with correlation IDs | Structured JSON logs |

---

## 3. Network Lockdown

### 3.1 Phase 1: Gateway Sidecar

All git and gh operations route through the gateway sidecar. The agent container has no direct GitHub access.

```
Agent Container                  Gateway Sidecar
┌─────────────┐                  ┌─────────────────────┐
│ git push    │───HTTP API──────►│ Validate request    │
│ (wrapper)   │                  │ Apply policy        │
│             │                  │ Execute with token  │
└─────────────┘                  └─────────────────────┘
```

### 3.2 Phase 2: Full Network Lockdown

All network traffic routes through the gateway proxy with strict domain allowlist.

#### 3.2.1 Allowed Domains

| Domain | Purpose | Required For |
|--------|---------|--------------|
| `api.anthropic.com` | Claude API | Claude Code operation |
| `github.com` | Git HTTPS | Clone, fetch, push |
| `api.github.com` | GitHub REST API | PR creation, issues |
| `raw.githubusercontent.com` | Raw content | File downloads |
| `objects.githubusercontent.com` | Release assets | Binary downloads |
| `codeload.github.com` | Archive downloads | Zip/tarball |
| `uploads.github.com` | File uploads | Release assets |

#### 3.2.2 Blocked Categories

| Category | Examples | Impact | Mitigation |
|----------|----------|--------|------------|
| Package registries | pypi.org, npmjs.com | Cannot install packages | Pre-install in image |
| Search engines | google.com, bing.com | Cannot search web | Use local docs, GitHub search |
| Arbitrary APIs | Any unlisted domain | Cannot exfiltrate | **This is the security goal** |

#### 3.2.3 Claude Code Tool Behavior

| Tool | Status | Reason |
|------|--------|--------|
| `WebFetch` | Blocked | Cannot reach arbitrary URLs |
| `WebSearch` | Blocked | Cannot reach search engines |
| GitHub MCP tools | Works | Routed through gateway |
| `claude --print` | Works | api.anthropic.com allowed |

**Expected behavior:** When blocked tools are invoked, the agent receives HTTP 403 and should adapt by using local resources.

### 3.3 Implementation Details

**Docker Network Configuration (example):**
```yaml
networks:
  isolated:
    internal: true  # No external connectivity
  external:
    # Standard bridge network for gateway outbound

services:
  agent:
    networks:
      - isolated  # ONLY internal network
    dns: []  # No DNS servers (prevents DNS tunneling)

  gateway:
    networks:
      - isolated  # Can receive from agent
      - external  # Can reach internet
```

#### 3.3.1 DNS Configuration

The `dns: []` setting prevents the agent container from using external DNS servers, blocking DNS tunneling as an exfiltration vector. Internal hostname resolution works as follows:

| Hostname | Resolution Method |
|----------|-------------------|
| `gateway` | Docker's embedded DNS (via /etc/hosts) |
| `localhost` | /etc/hosts |

**How it works:**
1. Docker Compose creates entries in `/etc/hosts` for service names on shared networks
2. The agent container can resolve `gateway` via this entry, not via DNS query
3. All other DNS queries fail (no external resolvers configured)
4. External hostname resolution (github.com, api.anthropic.com) happens in the gateway container, which has normal DNS access

**Why Docker's embedded DNS is not a covert channel:**
- The agent container cannot query Docker's embedded DNS for arbitrary hostnames
- Only hostnames in `/etc/hosts` (internal service names) resolve
- Queries for external names like `evil.example.com` fail immediately
- The gateway handles all external DNS resolution, and only for allowlisted domains

**Squid Proxy Configuration:**
```squid
# Block direct IP connections (prevent bypass via learned IPs)
acl direct_ip url_regex ^https?://[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+
http_access deny direct_ip

# Load allowed domains
acl allowed_domains dstdomain "/etc/squid/allowed_domains.txt"

# SSL bump for SNI inspection (peek only, no MITM decryption)
ssl_bump peek step1
ssl_bump splice allowed_domains
ssl_bump terminate all

# Allow only from internal network to allowed domains
http_access allow localnet allowed_domains
http_access deny all
```

#### 3.3.2 ECH/ESNI Handling

TLS 1.3 Encrypted Client Hello (ECH) and the older Encrypted SNI (ESNI) extension can encrypt the SNI field, potentially bypassing SNI-based filtering.

**Current approach:** Block connections where SNI cannot be determined.

```squid
# Terminate connections with missing/encrypted SNI
ssl_bump terminate !sni_available
```

| Scenario | Behavior | Rationale |
|----------|----------|-----------|
| Standard TLS with SNI | ✅ Inspect and filter | Normal operation |
| TLS with ECH/ESNI | ❌ Connection terminated | Cannot verify destination |
| Missing SNI | ❌ Connection terminated | Cannot verify destination |

**Deployment impact assessment:**
- ECH is deployed primarily by Cloudflare and a few other CDNs
- None of our allowlisted domains currently use ECH:
  - `api.anthropic.com` - No ECH
  - `github.com`, `api.github.com` - No ECH
  - `*.githubusercontent.com` - No ECH
- If an allowlisted domain enables ECH in the future, connections would fail until we update the proxy configuration

**Future considerations:**
- Monitor ECH adoption by allowlisted domains
- Consider enabling ECH passthrough for specific pre-verified domains if needed
- Alternative: Gateway could implement full MITM with trust store injection (increases complexity, currently unnecessary)

---

## 4. Credential Isolation

### 4.1 Credentials Inventory

| Credential | Location | Container Access |
|------------|----------|------------------|
| `GITHUB_TOKEN` | Gateway sidecar only | Never |
| `ANTHROPIC_API_KEY` | Container environment | Required for operation |
| SSH keys | None | Not present |
| Cloud credentials | None | Not present |

### 4.2 Token Lifecycle

GitHub App tokens are used (preferred) with automatic rotation:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                      GitHub App Token Lifecycle                            │
│                                                                            │
│  1. Gateway requests installation token from GitHub App                    │
│  2. Token valid for 1 hour (GitHub enforced)                               │
│  3. Gateway refreshes token 10 minutes before expiration                   │
│  4. Old token naturally expires - no revocation needed                     │
│                                                                            │
│  Timeline:                                                                 │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  0min              50min         60min                                     │
│  Token issued      Refresh       Expiration                                │
└────────────────────────────────────────────────────────────────────────────┘
```

**Failure handling:**
| Scenario | Behavior |
|----------|----------|
| Refresh fails (GitHub unavailable) | Retry with exponential backoff; continue with existing token until expiration |
| Token expired, refresh still failing | Git operations fail with clear error; gateway logs alert |
| Gateway restart mid-lifecycle | Request new token on startup; no state dependency on previous token |

### 4.3 Gateway Authentication

The agent container authenticates to the gateway using a shared secret:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Authentication Flow                                 │
│                                                                             │
│  1. Orchestrator generates random shared secret at startup                  │
│  2. Secret injected into both containers via environment variable           │
│  3. Agent includes secret in Authorization header for all gateway requests  │
│  4. Gateway validates secret before processing any request                  │
│                                                                             │
│  Agent Container                  Gateway Sidecar                           │
│  ┌─────────────┐                  ┌─────────────────────┐                   │
│  │ GATEWAY_    │  Authorization:  │ Validate header     │                   │
│  │ SECRET      │ ──Bearer $SECRET─► matches GATEWAY_    │                   │
│  │             │                  │ SECRET              │                   │
│  └─────────────┘                  └─────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Secret lifetime:** The shared secret should be generated fresh on each container startup and exists only for the container lifecycle. When containers are destroyed, the secret is lost. This provides natural rotation—each agent session has a unique secret.

**Future:** mTLS for production Cloud Run deployment.

---

## 5. Git and GitHub Lockdown

### 5.1 Git Metadata Isolation

The agent container cannot access git metadata:

```
Container filesystem view:
/workspace/my-repo/
├── src/                 ← Agent can edit these files
├── tests/               ← Agent can edit these files
├── README.md            ← Agent can edit this file
└── .git/                ← Empty directory (tmpfs shadow)
```

Without git metadata, the agent cannot:
- Discover repository origins
- Modify staging area directly
- Change branch pointers
- Execute git hooks
- Access other worktrees

### 5.2 Gateway-Enforced Policies

| Policy | Implementation |
|--------|----------------|
| **Branch ownership** | Only push to agent-owned branches (e.g., `agent/*` prefix) or branches with agent's open PR |
| **Protected branches** | Block direct push to `main`, `master` |
| **Force push** | `--force` flag blocked globally |
| **Merge blocking** | No merge endpoint exists in gateway API |

### 5.3 Gateway REST API

| Endpoint | Purpose | Policy Checks |
|----------|---------|---------------|
| `POST /api/v1/git/push` | Push to remote | Branch ownership, no force push |
| `POST /api/v1/git/fetch` | Fetch from remote | None (read-only) |
| `POST /api/v1/gh/pr/create` | Create PR | Agent attribution |
| `POST /api/v1/gh/pr/comment` | Comment on PR | Only own PRs |
| `POST /api/v1/gh/pr/close` | Close PR | Only own PRs |

### 5.4 Blocked Operations

| Operation | Why Blocked |
|-----------|-------------|
| `git merge` to protected branches | Must go through PR review |
| `gh pr merge` | Human must review and merge |
| `git push --force` | Could destroy others' work |
| `git config --global` | Could affect other agents |
| `git remote add/remove` | Could redirect pushes |

### 5.5 Blocked Flags

| Flag | Risk |
|------|------|
| `--exec`, `-c` | Command injection |
| `--upload-pack`, `--receive-pack` | Arbitrary command execution |
| `--config`, `-c` | Runtime config override |
| `--no-verify` | Skip hooks (defense in depth) |
| `--git-dir`, `--work-tree` | Path traversal |

---

## 6. Private Repository Mode

### 6.1 Purpose

Private Repo Mode restricts agents to only interact with **private** GitHub repositories, preventing any interaction with public repositories.

### 6.2 Motivation

When operating on sensitive codebases:
1. **Accidental code sharing:** Agent might reference or copy code to a public repository
2. **Data leakage via forks:** Agent could fork a private repo to a public destination
3. **Cross-contamination:** Agent might mix private code with public dependencies

### 6.3 Enforcement

The gateway checks repository visibility via GitHub API:

| Operation | Public Repo | Private Repo |
|-----------|-------------|--------------|
| `git clone` | Blocked | Allowed |
| `git fetch` | Blocked | Allowed |
| `git push` | Blocked | Allowed |
| `gh pr create` | Blocked | Allowed |
| `gh repo fork` (public to public) | Blocked | N/A |
| `gh repo fork` (private to public) | N/A | Blocked |
| `gh repo fork` (private to private) | N/A | Allowed |

### 6.4 Visibility Cache

| Operation Type | TTL | Rationale |
|----------------|-----|-----------|
| Read operations (fetch, clone) | 60 seconds | Lower risk; brief window acceptable |
| Write operations (push, PR create) | 0 seconds | Higher risk; always verify before writes |

**Error handling:** If GitHub API unavailable:
- **Read operations (fetch, clone):** Fail open—allow operation to proceed. Rationale: Lower risk; operation is read-only.
- **Write operations (push, PR create):** Fail closed—deny operation. Rationale: Higher risk; we must verify visibility before allowing writes to prevent accidental data exposure.

This asymmetric approach balances availability (reads work during GitHub outages) with security (writes require verified visibility).

### 6.5 Configuration

Private Repo Mode should be configurable via environment variable (e.g., `PRIVATE_REPO_MODE=true`).

---

## 7. Audit Logging

### 7.1 Log Format

All operations produce structured JSON logs:

```json
{
  "timestamp": "2024-01-29T14:32:01.234Z",
  "severity": "INFO",
  "message": "Git push completed",
  "traceId": "0af7651916cd43dd8448eb211c80319c",
  "spanId": "b7ad6b7169203331",
  "service": "gateway",
  "operation": "git_push",
  "source_container": "agent-abc123",
  "auth_valid": true,
  "request": {
    "repository": "owner/repo",
    "ref": "agent/feature-branch",
    "force": false
  },
  "response": {
    "status": "success",
    "duration_ms": 1234
  },
  "policy_checks": {
    "branch_ownership": "passed",
    "protected_branch": "passed",
    "force_push_attempted": false
  }
}
```

### 7.2 Logged Operations

| Category | Operations Logged |
|----------|-------------------|
| **Git operations** | push, fetch, clone, branch operations |
| **GitHub operations** | PR create, comment, close |
| **Proxy traffic** | All HTTPS requests (destination, status) |
| **Policy violations** | Blocked operations with reason |
| **Authentication** | Success/failure |

### 7.3 Alerting

| Condition | Alert Priority |
|-----------|----------------|
| Policy violation (blocked operation) | High |
| Authentication failure | High |
| High volume of blocked requests | Medium |
| GitHub rate limit | Low |

### 7.4 Retention

Log retention policies should be configured based on organizational requirements. Consider:
- Local log rotation (e.g., 90 days)
- Cloud logging integration for centralized management
- Compliance requirements for audit trails

---

## 8. Remaining Gaps and Concerns

### 8.1 Known Residual Risks

| Risk | Severity | Mitigation | Status |
|------|----------|------------|--------|
| **Data exfiltration via GitHub** | Medium | Commit messages/PR descriptions reviewed by human; private repos only | Acknowledged |
| **Data exfiltration via Claude API** | Low | Anthropic doesn't train on API data; API calls logged | Acknowledged |
| **Claude API key exposure** | Medium | Required for operation; could be exfiltrated via GitHub vectors | Acknowledged |

### 8.2 Exfiltration via GitHub (Detail)

The gateway cannot fully prevent data exfiltration via GitHub without imposing arbitrary limits:

| Vector | Limit | Impact |
|--------|-------|--------|
| Branch names | 256 characters | ~32 bytes useful payload |
| Commit messages | No hard limit | Could encode substantial data |
| PR titles/bodies | No hard limit | Could encode substantial data |

**Why we don't impose limits:**
- Arbitrary limits interfere with legitimate detailed commit messages
- Private Repo Mode ensures data stays in controlled repositories
- Human reviews PR content before merge
- All operations logged for anomaly detection

**Risk Acceptance:** This exfiltration vector is accepted as a residual risk. Mitigations provide detection capability, and data stays within controlled (private) repositories.

### 8.3 Claude OAuth Configuration / Auth Keys

**Identified Concern:** The Claude API key (`ANTHROPIC_API_KEY`) is present in the container environment because Claude Code requires it to function. This is the one credential that cannot be isolated from the agent.

**Current Protections:**
1. Key is scoped to API usage only (cannot be used to modify Anthropic account)
2. Network lockdown ensures key can only reach api.anthropic.com
3. Key cannot be exfiltrated to unauthorized endpoints (all traffic filtered)
4. Key usage is logged (via structured logging)

**Potential Enhancement:**
- Consider using Anthropic's session-based authentication if/when available
- Implement key rotation on a scheduled basis
- Monitor for unusual API usage patterns (high token volume, unusual prompts)

**Risk Assessment:** MEDIUM - While the key can only reach api.anthropic.com via network lockdown, it could be exfiltrated via GitHub vectors (commit messages, PR bodies) and then used from outside the sandbox. This is mitigated by:
- Private Repo Mode (key stays in controlled repositories)
- Human review before merge (can detect key in content)
- Anomaly detection on API usage (alerts on unusual patterns)
- Key rotation capability (can invalidate compromised keys)

### 8.4 Gaps Not Yet Addressed

| Gap | Description | Proposed Solution | Priority |
|-----|-------------|-------------------|----------|
| **Multi-agent isolation** | Agent memory is shared (beads, context, sharing directories) | Per-container memory isolation | Medium |
| **Container escape** | Defense in depth, not primary threat model | Keep Docker updated; consider gVisor | Low |
| **Host compromise** | Out of scope; host is trusted | Physical security, OS hardening | N/A |

---

## 9. Recommendations

### 9.1 Core Security Controls

The following controls form the security foundation:

1. **Gateway Sidecar Architecture** - All git/gh operations through policy-enforcing gateway
2. **Credential Isolation** - Tokens never enter agent container
3. **Git Metadata Isolation** - `.git` directories shadowed
4. **Branch Ownership Enforcement** - Only push to agent-owned branches
5. **Merge Blocking** - Agent cannot merge PRs
6. **Structured Audit Logging** - All operations logged with correlation

### 9.2 Enhanced Security Controls

The following provide additional protection for sensitive environments:

1. **Full Network Lockdown** - Only LLM API + GitHub allowed
2. **Private Repo Mode** - Restrict to private repositories only

### 9.3 Security Review Checklist

- [ ] Review credential isolation implementation
- [ ] Verify network lockdown configuration
- [ ] Test branch ownership enforcement
- [ ] Confirm merge blocking works
- [ ] Review audit log format and coverage
- [ ] Validate proxy allowlist completeness
- [ ] Assess residual exfiltration risks
- [ ] Approve Private Repo Mode proposal

---

## 10. Future Connectors

The gateway-based isolation pattern established in this document is designed to support additional service connectors. Each connector will follow the same security model:

1. **Credential isolation**: Service tokens held by gateway only
2. **Policy enforcement**: Gateway validates operations before execution
3. **Audit logging**: All operations logged with correlation IDs
4. **Scoped access**: Agent only sees data relevant to its task

### 10.1 Planned Connectors

| Connector | Phase | Read Access | Write Access | Status |
|-----------|-------|-------------|--------------|--------|
| **GitHub** | 3-4 | Repo contents, PR status, workflow logs | Push, PR create/comment | This document |
| **Slack** | 3-4 | Thread history (task-scoped) | Send messages, reply to threads | PR #629 (ADR proposed) |
| **Jira** | 3-4 | Ticket details, comments | Status updates, comments | Planned |
| **Confluence** | 3-4 | Page content (scoped by space) | Page updates, comments | Planned |
| **BigQuery** | 3-4 | Query execution (read-only) | Write to predefined safe locations | Planned |
| **Figma** | 3 | Design file viewing via MCP | None (read-only) | Planned |
| **Debugging Tools** | 3 | Sentry, Cypress Cloud, GCP logs | None (read-only) | Planned |

### 10.2 Gateway Extension Pattern

New connectors will be added to the gateway sidecar following this pattern:

```
Agent Container                    Gateway Sidecar
+------------------+              +---------------------------+
|                  |              |                           |
| connector client |--HTTP API--->| /api/v1/{connector}/...   |
| (no credentials) |              |   - Validate request      |
|                  |              |   - Check policy          |
|                  |              |   - Execute with token    |
|                  |              |   - Log operation         |
+------------------+              +---------------------------+
```

Each connector adds:
- New REST API endpoints in the gateway
- Credential storage in gateway secrets
- Policy rules specific to that service
- Audit log event types

### 10.3 Network Allowlist Extensions

As connectors are added, the proxy allowlist expands:

| Connector | Domains to Add |
|-----------|----------------|
| Slack | `slack.com`, `api.slack.com`, `files.slack.com` |
| Jira/Confluence | `*.atlassian.net`, `*.atlassian.com` |
| BigQuery | `bigquery.googleapis.com`, `bigqueryreservation.googleapis.com` |
| Figma | `api.figma.com`, `www.figma.com` |
| Sentry | `sentry.io`, `*.ingest.sentry.io` |

**Important**: Each domain addition requires security review. The allowlist is not expanded automatically.

---

## Appendix: OWASP Alignment

This architecture aligns with the **OWASP Top 10 for Agentic Applications**:

| OWASP Risk | Description | Mitigation |
|------------|-------------|------------|
| **ASI01** - Agentic Excessive Authority | Agents granted overly broad permissions | Credential isolation; gateway exposes minimal API; no merge endpoint |
| **ASI02** - Tool Misuse & Exploitation | Agents misusing available tools | Gateway enforces policies; force push blocked; domain allowlist |
| **ASI03** - Identity & Privilege Abuse | Credential theft or misuse | Credentials never enter container; gateway holds all tokens |
| **ASI04** - Supply Chain Vulnerabilities | Compromised dependencies | Pre-installed packages; image scanning; no runtime installs |
| **ASI06** - Memory/Context Poisoning | Corruption of agent memory | Container isolation; read-only context mounts |
| **ASI10** - Rogue Agents | Agent operating outside intended behavior | Infrastructure controls (not instructions) prevent unauthorized operations |

**Reference:** [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/)
