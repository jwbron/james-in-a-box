# ADR: Tool Access Lockdown via Gateway Sidecar

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Draft

## Table of Contents

- [Context](#context)
- [Problem Statement](#problem-statement)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
- [Implementation Details](#implementation-details)
- [Security Analysis](#security-analysis)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)
- [Migration Plan](#migration-plan)

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

**Out of Scope:**
- Internet domain allowlisting/blocking (too difficult to maintain while allowing web search and package installation)
- DNS-level filtering (can revisit if threat model changes)

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

## Implementation Details

### 1. Network Isolation

Configure Docker networking so jib can ONLY reach the gateway:

```yaml
# docker-compose.yml
version: '3.8'

networks:
  jib-internal:
    internal: true  # No external access
  gateway-external:
    # Gateway can reach internet

services:
  jib:
    build: ./jib-container
    networks:
      - jib-internal  # Only internal network
    environment:
      - HTTP_PROXY=http://gateway:3128
      - HTTPS_PROXY=http://gateway:3128
      - NO_PROXY=gateway
      - GATEWAY_API_URL=http://gateway:8080
    depends_on:
      - gateway

  gateway:
    build: ./gateway-sidecar
    networks:
      - jib-internal   # Reachable by jib
      - gateway-external  # Can reach internet
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - JIB_GITHUB_USERNAME=jwbron
    ports:
      - "3128:3128"  # HTTP proxy
      - "8080:8080"  # REST API
```

### 2. Gateway REST API

**Communication Protocol Decision:**
- **Primary:** REST over HTTP (synchronous)
- **Rationale:** Simple, well-understood, easy to debug, good tooling support
- **Sync vs Async:** Synchronous - jib waits for operation result before proceeding

**Alternative Protocols (for reference):**
| Protocol | Pros | Cons | When to Consider |
|----------|------|------|------------------|
| REST | Simple, debuggable, HTTP tooling | Per-request overhead | Default choice |
| gRPC | Binary efficiency, streaming, strong typing | More complex setup, protobuf required | High-throughput scenarios |
| Unix Socket | Lowest latency, no network stack | Docker volume mount complexity | Performance-critical operations |
| Message Queue | Decoupled, retry semantics | Adds complexity, async-by-default | Batch operations, fire-and-forget |

We start with REST for its simplicity. If performance becomes a concern, gRPC is the natural evolution. Unix sockets could be considered for extremely latency-sensitive operations.

The gateway exposes a controlled API for git/gh operations:

```python
# gateway-sidecar/api.py
from flask import Flask, request, jsonify
import subprocess
import logging

app = Flask(__name__)
logger = logging.getLogger('gateway-audit')

JIB_USERNAME = os.environ.get('JIB_GITHUB_USERNAME', 'jwbron')

def audit_log(operation, details, allowed):
    logger.info(f"{'ALLOWED' if allowed else 'BLOCKED'}: {operation} - {details}")

@app.route('/api/git/push', methods=['POST'])
def git_push():
    """Handle git push requests from jib"""
    data = request.json
    repo_path = data.get('repo_path')
    branch = data.get('branch')
    remote = data.get('remote', 'origin')
    force = data.get('force', False)

    # BLOCK: Force push
    if force:
        audit_log('git-push', f'force push to {branch}', allowed=False)
        return jsonify({'error': 'Force push not allowed'}), 403

    # BLOCK: Push to main/master
    if branch in ('main', 'master'):
        audit_log('git-push', f'push to protected branch {branch}', allowed=False)
        return jsonify({'error': f'Push to {branch} not allowed'}), 403

    # Execute push
    audit_log('git-push', f'{remote} {branch}', allowed=True)
    result = subprocess.run(
        ['git', '-C', repo_path, 'push', remote, branch],
        capture_output=True, text=True
    )

    return jsonify({
        'success': result.returncode == 0,
        'stdout': result.stdout,
        'stderr': result.stderr
    })

@app.route('/api/gh/pr/create', methods=['POST'])
def pr_create():
    """Create a pull request"""
    data = request.json
    audit_log('gh-pr-create', f"title: {data.get('title')}", allowed=True)

    # Forward to gh CLI
    result = subprocess.run(
        ['gh', 'pr', 'create',
         '--title', data.get('title'),
         '--body', data.get('body'),
         '--base', data.get('base', 'main')],
        capture_output=True, text=True,
        cwd=data.get('repo_path')
    )

    return jsonify({
        'success': result.returncode == 0,
        'stdout': result.stdout,
        'stderr': result.stderr
    })

@app.route('/api/gh/pr/comment', methods=['POST'])
def pr_comment():
    """Add a comment to a PR"""
    data = request.json
    pr_number = data.get('pr_number')
    body = data.get('body')

    audit_log('gh-pr-comment', f"PR #{pr_number}", allowed=True)

    result = subprocess.run(
        ['gh', 'pr', 'comment', str(pr_number), '--body', body],
        capture_output=True, text=True,
        cwd=data.get('repo_path')
    )

    return jsonify({
        'success': result.returncode == 0,
        'stdout': result.stdout,
        'stderr': result.stderr
    })

# NOTE: No /api/gh/pr/merge endpoint - merge is not exposed
# Human must merge via GitHub UI or direct gh command

@app.route('/api/gh/pr/close', methods=['POST'])
def pr_close():
    """Close a PR - only jib's own PRs"""
    data = request.json
    pr_number = data.get('pr_number')
    repo = data.get('repo')

    # Check ownership
    result = subprocess.run(
        ['gh', 'pr', 'view', str(pr_number), '--json', 'author', '--jq', '.author.login'],
        capture_output=True, text=True,
        cwd=data.get('repo_path')
    )
    author = result.stdout.strip()

    if author != JIB_USERNAME:
        audit_log('gh-pr-close', f"PR #{pr_number} owned by {author}", allowed=False)
        return jsonify({'error': f'Can only close own PRs (owner: {author})'}), 403

    audit_log('gh-pr-close', f"PR #{pr_number}", allowed=True)

    result = subprocess.run(
        ['gh', 'pr', 'close', str(pr_number)],
        capture_output=True, text=True,
        cwd=data.get('repo_path')
    )

    return jsonify({
        'success': result.returncode == 0,
        'stdout': result.stdout,
        'stderr': result.stderr
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### 3. HTTP Proxy with Audit Logging

The gateway runs a proxy that logs all traffic:

```
# gateway-sidecar/squid.conf
# Allow all traffic but log everything

# Logging format for audit
logformat audit %ts.%03tu %6tr %>a %Ss/%03>Hs %<st %rm %ru %un %Sh/%<a %mt

# Log to stdout for container logging
access_log stdio:/dev/stdout audit

# ACL for internal network
acl jib_network src 172.16.0.0/12

# Allow all HTTP/HTTPS traffic from jib
http_access allow jib_network
http_access deny all

# SSL bump for HTTPS visibility (optional - requires cert management)
# For now, just log CONNECT requests
ssl_bump peek all
ssl_bump bump all
```

### 4. Future: LLM-Based Traffic Analysis

A future enhancement could add intelligent traffic analysis:

```
jib container → gateway proxy → traffic analyzer → internet
                                      ↓
                              (optional) secondary LLM
                              or pattern-based detector
```

The analyzer could:
- Flag unusual destinations or patterns
- Detect potential data exfiltration (large payloads to unknown hosts)
- Rate-limit suspicious traffic
- Start as logging-only, graduate to blocking based on confidence

**Implementation options:**
1. **Pattern-based rules**: Simple regex/heuristics for known bad patterns
2. **Lightweight LLM**: Smaller model evaluating request/response pairs
3. **Secondary jib instance**: Full Claude instance reviewing traffic samples

This is marked as "future consideration" to avoid over-engineering the initial implementation.

### 5. jib-Side Client Library

Provide a simple client for jib to call gateway APIs:

```python
# jib-container/shared/gateway_client.py
import os
import requests

GATEWAY_URL = os.environ.get('GATEWAY_API_URL', 'http://gateway:8080')

class GatewayClient:
    def __init__(self):
        self.base_url = GATEWAY_URL

    def git_push(self, repo_path, branch, remote='origin'):
        """Push via gateway (no force push, no main/master)"""
        response = requests.post(f'{self.base_url}/api/git/push', json={
            'repo_path': repo_path,
            'branch': branch,
            'remote': remote
        })
        return response.json()

    def pr_create(self, repo_path, title, body, base='main'):
        """Create a PR via gateway"""
        response = requests.post(f'{self.base_url}/api/gh/pr/create', json={
            'repo_path': repo_path,
            'title': title,
            'body': body,
            'base': base
        })
        return response.json()

    def pr_comment(self, repo_path, pr_number, body):
        """Add a comment to a PR via gateway"""
        response = requests.post(f'{self.base_url}/api/gh/pr/comment', json={
            'repo_path': repo_path,
            'pr_number': pr_number,
            'body': body
        })
        return response.json()
```

### 6. Network Rules for GitHub Blocking

Ensure jib cannot reach GitHub directly (must use gateway proxy):

```yaml
# docker-compose.yml network configuration
services:
  jib:
    networks:
      jib-internal:
        # This internal network has no external route
        # All traffic must go through the proxy
    dns:
      - 8.8.8.8  # Standard DNS (gateway handles routing)
```

Additional iptables rules in gateway (if needed):
```bash
# Block jib from reaching GitHub directly (failsafe)
iptables -A FORWARD -s jib -d github.com -j DROP
iptables -A FORWARD -s jib -d api.github.com -j DROP
```

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

1. **Data exfiltration to allowed endpoints**: Agent can send data to any website (logged but not blocked)
2. **Malicious code in PRs**: Agent can still write malicious code (human review required)
3. **Social engineering via Slack**: Agent could attempt to manipulate human via messages

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

**Cons:**
- Breaks web search (needs access to search engines and results)
- Breaks package installation (many CDN domains)
- Constant maintenance as services change

**Rejected:** Too restrictive for practical use; jib needs web access

## MCP Considerations

**Related ADR:** [ADR-Context-Sync-Strategy-Custom-vs-MCP](./ADR-Context-Sync-Strategy-Custom-vs-MCP.md) (PR #36)

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

## Migration Plan

### Phase 1: Build Gateway

1. Create gateway-sidecar container with REST API
2. Implement core operations: push, pr create, pr comment, pr close
3. Add HTTP proxy with logging
4. Test in isolation

### Phase 2: Integration

1. Update docker-compose with network isolation
2. Modify jib startup to use gateway client
3. Update create-pr-helper.py to use gateway
4. Test full workflow

### Phase 3: Deployment

1. Deploy to staging/dev environment
2. Monitor audit logs
3. Tune API as needed
4. Document any workflow changes

### Rollback Plan

If gateway causes issues:
1. Add GITHUB_TOKEN back to jib container
2. Remove network isolation
3. Restore direct gh/git usage
4. Keep gateway running for logging only

---

## Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Autonomous-Software-Engineer](./ADR-Autonomous-Software-Engineer.md) | Parent ADR - defines overall security model |
| [ADR-Context-Sync-Strategy-Custom-vs-MCP](./ADR-Context-Sync-Strategy-Custom-vs-MCP.md) (PR #36) | MCP strategy affects how gateway integrates |
| ADR-GCP-Deployment-Terraform (PR #44 refs) | Gateway must work in Cloud Run |

---

**Last Updated:** 2025-11-25
**Status:** Draft - Awaiting Review
