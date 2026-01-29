# Sandbox Security Proposal: LLM Agent Isolation Architecture

**Document Status:** Proposal for Security Review
**Version:** 1.0
**Date:** 2026-01-29
**Authors:** James Wiesebron, jib (AI Pair Programming)
**Audience:** Security Team, Engineering Leadership

## Executive Summary

This document proposes a comprehensive security architecture for operating autonomous LLM-powered agents (Claude Code) in sensitive codebases without human supervision. The architecture provides **defense-in-depth through infrastructure controls**, ensuring that even if behavioral instructions are bypassed via prompt injection, model drift, or adversarial inputs, the agent cannot perform unauthorized operations.

### Core Security Guarantee

> **An AI agent cannot access credentials, merge code, or exfiltrate data to unauthorized endpoints—regardless of what it is instructed to do.**

This guarantee is achieved through:
1. **Credential Isolation**: Tokens never enter the agent container
2. **Network Lockdown**: Only Anthropic API and GitHub reachable
3. **Gateway Enforcement**: All privileged operations validated by a trusted sidecar
4. **Filesystem Isolation**: Agent cannot access other agents' workspaces or sensitive files
5. **Human-in-the-Loop**: All code merges require human approval

### Document Scope

This proposal consolidates security controls across four core domains:

| Domain | ADR/Document | Status |
|--------|--------------|--------|
| **Internet Access** | ADR-Internet-Tool-Access-Lockdown | Implemented (Phase 1), Phase 2 Proposed |
| **Git Operations** | ADR-Git-Isolation-Architecture | Implemented |
| **Private Repo Mode** | ADR-Git-Isolation-Architecture (extension) | Proposed |
| **Audit Logging** | ADR-Standardized-Logging-Interface | Implemented |

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
10. [Appendix: OWASP Alignment](#appendix-owasp-alignment)

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
│                            UNTRUSTED ZONE                                    │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        jib Container (Agent)                            │ │
│  │                                                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │ │
│  │  │ Claude Code │  │ Code Files  │  │ Context     │  │ Beads       │   │ │
│  │  │ Agent       │  │ (workspace) │  │ (read-only) │  │ (task mem)  │   │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │ │
│  │                                                                         │ │
│  │  NO: GitHub tokens, SSH keys, cloud credentials                        │ │
│  │  NO: Direct network access (proxy required)                            │ │
│  │  NO: Git metadata (.git directory shadowed by tmpfs)                   │ │
│  │  NO: Other agents' workspaces                                          │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    │ HTTP API (authenticated)                │
│                                    ▼                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                            TRUSTED ZONE                                      │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     Gateway Sidecar (Policy Enforcer)                   │ │
│  │                                                                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │ │
│  │  │ GITHUB_     │  │ HTTPS       │  │ Policy      │                    │ │
│  │  │ TOKEN       │  │ Proxy       │  │ Engine      │                    │ │
│  │  │ (secure)    │  │ (filtered)  │  │ (validates) │                    │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                    │ │
│  │                                                                         │ │
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
│                              Host Machine                                    │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    jib-isolated Network (internal: true)              │   │
│  │                    Subnet: 172.30.0.0/24                              │   │
│  │                    Gateway: NONE (no external route)                  │   │
│  │                                                                       │   │
│  │    ┌─────────────────┐                  ┌─────────────────────┐      │   │
│  │    │   jib Container │                  │   Gateway Sidecar   │      │   │
│  │    │   172.30.0.10   │◄────REST API────►│     172.30.0.2      │      │   │
│  │    │                 │    Port 9847     │                     │      │   │
│  │    │ Claude Code     │                  │ GITHUB_TOKEN        │      │   │
│  │    │ git/gh wrappers │◄────HTTPS Proxy──│ Squid (filtered)    │      │   │
│  │    │ NO credentials  │    Port 3128     │ Policy Engine       │      │   │
│  │    │                 │                  │                     │      │   │
│  │    └─────────────────┘                  └──────────┬──────────┘      │   │
│  │                                                    │                 │   │
│  └────────────────────────────────────────────────────│─────────────────┘   │
│                                                       │                      │
│  ┌────────────────────────────────────────────────────│─────────────────┐   │
│  │                    jib-external Network (bridge)   │                  │   │
│  │                                                    │                  │   │
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
│  └───────────────────────────────────────────────────│──────────────────┘   │
│                                                      │                       │
│                                                      ▼                       │
│                                                 Internet                     │
│                                           (allowlisted only)                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Security Properties Summary

| Property | Implementation | Verification |
|----------|----------------|--------------|
| **Credential Isolation** | Tokens exist only in gateway sidecar | Container has no env vars or files with tokens |
| **Network Isolation** | Internal Docker network with no external route | `docker network inspect jib-isolated` shows `internal: true` |
| **Domain Allowlist** | Squid proxy with SNI-based filtering | Blocked requests return HTTP 403 |
| **Git Metadata Isolation** | `.git` directories shadowed by tmpfs | Agent cannot read or modify git refs directly |
| **Branch Ownership** | Gateway validates push requests | Only jib-prefixed branches or branches with open PRs |
| **Merge Blocking** | Gateway has no merge endpoint | `gh pr merge` commands fail at gateway level |
| **Audit Logging** | All operations logged with correlation IDs | Structured JSON to journalctl and Cloud Logging |

---

## 3. Network Lockdown

**Reference:** [ADR-Internet-Tool-Access-Lockdown](../adr/in-progress/ADR-Internet-Tool-Access-Lockdown.md)

### 3.1 Phase 1: Gateway Sidecar (Implemented)

All git and gh operations route through the gateway sidecar. The jib container has no direct GitHub access.

```
jib container                    gateway-sidecar
┌─────────────┐                  ┌─────────────────────┐
│ git push    │──HTTP API──────►│ Validate request    │
│ (wrapper)   │                  │ Apply policy        │
│             │                  │ Execute with token  │
└─────────────┘                  └─────────────────────┘
```

**Status:** ✅ Implemented

### 3.2 Phase 2: Full Network Lockdown (Proposed)

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
| `WebFetch` | ❌ Blocked | Cannot reach arbitrary URLs |
| `WebSearch` | ❌ Blocked | Cannot reach search engines |
| GitHub MCP tools | ✅ Works | Routed through gateway |
| `claude --print` | ✅ Works | api.anthropic.com allowed |

**Expected behavior:** When blocked tools are invoked, Claude receives HTTP 403 and adapts by using local resources.

**Status:** 🔄 Proposed (Phase 2)

### 3.3 Implementation Details

**Docker Network Configuration:**
```yaml
networks:
  jib-isolated:
    internal: true  # No external connectivity
  jib-external:
    # Standard bridge network for gateway outbound

services:
  jib:
    networks:
      - jib-isolated  # ONLY internal network
    dns: []  # No DNS servers (prevents DNS tunneling)

  gateway-sidecar:
    networks:
      - jib-isolated  # Can receive from jib
      - jib-external  # Can reach internet
```

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

---

## 4. Credential Isolation

**Reference:** [ADR-Internet-Tool-Access-Lockdown](../adr/in-progress/ADR-Internet-Tool-Access-Lockdown.md)

### 4.1 Credentials Inventory

| Credential | Location | Container Access |
|------------|----------|------------------|
| `GITHUB_TOKEN` | Gateway sidecar only | ❌ Never |
| `ANTHROPIC_API_KEY` | Container environment | ✅ Required for operation |
| SSH keys | None | ❌ Not present |
| Cloud credentials | None | ❌ Not present |

### 4.2 Token Lifecycle

GitHub App tokens are used (preferred) with automatic rotation:

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
└────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Gateway Authentication

The jib container authenticates to the gateway using a shared secret:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Authentication Flow                                   │
│                                                                               │
│  1. Docker Compose generates random shared secret at startup                 │
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

**Future:** mTLS for production Cloud Run deployment.

---

## 5. Git and GitHub Lockdown

**Reference:** [ADR-Git-Isolation-Architecture](../adr/implemented/ADR-Git-Isolation-Architecture.md)

### 5.1 Git Metadata Isolation

The jib container cannot access git metadata:

```
Container filesystem view:
/home/jib/repos/my-repo/
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
| **Branch ownership** | Only push to branches matching `jib/*` or branches with agent's open PR |
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
| ~~`POST /api/v1/gh/pr/merge`~~ | ~~Merge PR~~ | **Does not exist** |

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

**Status:** ✅ Implemented

---

## 6. Private Repository Mode

**Reference:** [ADR-Git-Isolation-Architecture](../adr/implemented/ADR-Git-Isolation-Architecture.md) (Private Repo Mode extension)

### 6.1 Purpose

Private Repo Mode restricts jib to only interact with **private** GitHub repositories, preventing any interaction with public repositories.

### 6.2 Motivation

When operating on sensitive codebases:
1. **Accidental code sharing:** Agent might reference or copy code to a public repository
2. **Data leakage via forks:** Agent could fork a private repo to a public destination
3. **Cross-contamination:** Agent might mix private code with public dependencies

### 6.3 Enforcement

The gateway checks repository visibility via GitHub API:

| Operation | Public Repo | Private Repo |
|-----------|-------------|--------------|
| `git clone` | ❌ Blocked | ✅ Allowed |
| `git fetch` | ❌ Blocked | ✅ Allowed |
| `git push` | ❌ Blocked | ✅ Allowed |
| `gh pr create` | ❌ Blocked | ✅ Allowed |
| `gh repo fork` | ❌ Blocked (either direction) | ✅ Allowed (to private only) |

### 6.4 Visibility Cache

| Operation Type | TTL | Rationale |
|----------------|-----|-----------|
| Read operations (fetch, clone) | 60 seconds | Lower risk; brief window acceptable |
| Write operations (push, PR create) | 0 seconds | Higher risk; always verify before writes |

**Error handling:** If GitHub API unavailable, fail closed (treat as private, allow operation).

### 6.5 Configuration

```yaml
# docker-compose.yml
services:
  gateway-sidecar:
    environment:
      - PRIVATE_REPO_MODE=true
```

**Status:** 🔄 Proposed

---

## 7. Audit Logging

**Reference:** [ADR-Standardized-Logging-Interface](../adr/in-progress/ADR-Standardized-Logging-Interface.md)

### 7.1 Log Format

All operations produce structured JSON logs:

```json
{
  "timestamp": "2026-01-29T14:32:01.234Z",
  "severity": "INFO",
  "message": "Git push completed",
  "traceId": "0af7651916cd43dd8448eb211c80319c",
  "spanId": "b7ad6b7169203331",
  "service": "gateway-sidecar",
  "operation": "git_push",
  "source_ip": "172.30.0.10",
  "source_container": "jib-abc123",
  "auth_valid": true,
  "request": {
    "repository": "owner/repo",
    "ref": "jib/feature-branch",
    "force": false
  },
  "response": {
    "status": "success",
    "duration_ms": 1234
  },
  "policy_checks": {
    "branch_ownership": "passed",
    "protected_branch": "passed",
    "force_push_blocked": false
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

- **Journalctl:** 90 days default (configurable via `/etc/systemd/journald.conf`)
- **Model output:** Daily directories with index files
- **GCP Cloud Logging:** Native support when deployed to Cloud Run

**Status:** ✅ Implemented

---

## 8. Remaining Gaps and Concerns

### 8.1 Known Residual Risks

| Risk | Severity | Mitigation | Status |
|------|----------|------------|--------|
| **Data exfiltration via GitHub** | Medium | Commit messages/PR descriptions reviewed by human; private repos only | Acknowledged |
| **Data exfiltration via Claude API** | Low | Anthropic doesn't train on API data; API calls logged | Acknowledged |
| **Claude API key exposure** | Low | Required for operation; scoped to single use case | Accepted |

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

**Risk Assessment:** LOW - Key can only be used for its intended purpose due to network lockdown.

### 8.4 Gaps Not Yet Addressed

| Gap | Description | Proposed Solution | Priority |
|-----|-------------|-------------------|----------|
| **Multi-agent isolation** | Agents could theoretically access each other's beads | Per-container beads isolation | Medium |
| **Container escape** | Defense in depth, not primary threat model | Keep Docker updated; consider gVisor | Low |
| **Host compromise** | Out of scope; host is trusted | Physical security, OS hardening | N/A |

---

## 9. Recommendations

### 9.1 For Immediate Approval (Phase 1)

The following are already implemented and ready for security review:

1. ✅ **Gateway Sidecar Architecture** - All git/gh operations through policy-enforcing gateway
2. ✅ **Credential Isolation** - Tokens never enter agent container
3. ✅ **Git Metadata Isolation** - `.git` directories shadowed
4. ✅ **Branch Ownership Enforcement** - Only push to jib-owned branches
5. ✅ **Merge Blocking** - Agent cannot merge PRs
6. ✅ **Structured Audit Logging** - All operations logged with correlation

### 9.2 For Phase 2 Approval

The following are proposed and require implementation:

1. 🔄 **Full Network Lockdown** - Only Anthropic + GitHub allowed (ADR-Internet-Tool-Access-Lockdown Phase 2)
2. 🔄 **Private Repo Mode** - Restrict to private repositories only

### 9.3 Recommended Operating Configuration

For maximum security with unsupervised operation:

```bash
# Maximum security configuration
export JIB_NETWORK_LOCKDOWN=true      # Phase 2 network isolation
export PRIVATE_REPO_MODE=true          # Private repos only
./jib --dangerously-skip-permissions   # Autonomous operation
```

### 9.4 Security Review Checklist

- [ ] Review credential isolation implementation
- [ ] Verify network lockdown configuration
- [ ] Test branch ownership enforcement
- [ ] Confirm merge blocking works
- [ ] Review audit log format and coverage
- [ ] Validate proxy allowlist completeness
- [ ] Assess residual exfiltration risks
- [ ] Approve Private Repo Mode proposal

---

## Appendix: OWASP Alignment

This architecture aligns with the **OWASP Top 10 for Agentic Applications (2026)**:

| OWASP Risk | Description | Mitigation |
|------------|-------------|------------|
| **ASI01** - Agentic Excessive Authority | Agents granted overly broad permissions | Credential isolation; gateway exposes minimal API; no merge endpoint |
| **ASI02** - Tool Misuse & Exploitation | Agents misusing available tools | Gateway enforces policies; force push blocked; domain allowlist |
| **ASI03** - Identity & Privilege Abuse | Credential theft or misuse | Credentials never enter container; gateway holds all tokens |
| **ASI04** - Supply Chain Vulnerabilities | Compromised dependencies | Pre-installed packages; image scanning; no runtime installs |
| **ASI06** - Memory/Context Poisoning | Corruption of agent memory | Container isolation; read-only context mounts |
| **ASI10** - Rogue Agents | Agent operating outside intended behavior | Infrastructure controls (not instructions) prevent unauthorized operations |

**Reference:** [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/)

---

## Appendix: Related Documents

| Document | Location | Description |
|----------|----------|-------------|
| ADR-Internet-Tool-Access-Lockdown | `docs/adr/in-progress/` | Network and credential lockdown |
| ADR-Git-Isolation-Architecture | `docs/adr/implemented/` | Git worktree and gateway design |
| ADR-Standardized-Logging-Interface | `docs/adr/in-progress/` | Audit logging specification |
| ADR-Autonomous-Software-Engineer | `docs/adr/in-progress/` | Overall system architecture |

---

**Document Revision History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-29 | jwiesebron, jib | Initial proposal |
