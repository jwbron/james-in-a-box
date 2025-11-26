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

### 5. git CLI Wrapper

Similar to the gh wrapper, provide a **`git` CLI wrapper** that:
1. Forwards most git commands directly to the real binary (clone, checkout, commit, branch, log, diff, status, etc.)
2. Intercepts `git push` to route through the gateway and send Slack notifications
3. Blocks force pushes (`--force`, `-f`, `--force-with-lease`, `--force-if-includes`) entirely
4. Blocks pushes to protected branches (main, master)

This approach provides the same interface jib is accustomed to while enforcing policies at the wrapper level.

#### Wrapper Design

The wrapper is placed in PATH before the real `git` binary:

```python
#!/usr/bin/env python3
# /jib/wrappers/git
"""
git wrapper - provides same interface as git CLI with added features:
- Policy enforcement (no force push, no push to protected branches)
- Slack notifications on push
- Gateway routing for authenticated operations
"""
import sys
import subprocess
import os
from pathlib import Path

# Add shared directory for notifications
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from notifications import get_slack_service

REAL_GIT = "/usr/bin/git"
GATEWAY_URL = os.environ.get("GATEWAY_API_URL", "http://gateway:8080")
PROTECTED_BRANCHES = {"main", "master"}


class GitWrapper:
    def __init__(self):
        self.slack = get_slack_service()
        self.repo_name = self._get_repo_name()

    def _get_repo_name(self) -> str:
        """Get owner/repo from git remote."""
        try:
            result = subprocess.run(
                [REAL_GIT, "remote", "get-url", "origin"],
                capture_output=True, text=True, check=True
            )
            url = result.stdout.strip()
            if "github.com" in url:
                if ":" in url and "@" in url:
                    return url.split(":")[-1].replace(".git", "")
                return url.split("github.com/")[-1].replace(".git", "")
        except subprocess.CalledProcessError:
            pass
        return ""

    def run(self, args: list[str]) -> int:
        """Main entry point - parse and dispatch commands."""
        if not args:
            return self._passthrough([])

        cmd = args[0]
        if cmd == "push":
            return self._handle_push(args[1:])
        else:
            # All other commands pass through unchanged
            return self._passthrough(args)

    def _passthrough(self, args: list[str]) -> int:
        """Pass command through to real git."""
        return subprocess.run([REAL_GIT] + args).returncode

    def _handle_push(self, args: list[str]) -> int:
        """Handle git push with policy enforcement and notifications."""
        # Check for force push flags
        force_flags = {"-f", "--force", "--force-with-lease", "--force-if-includes"}
        if any(arg in force_flags for arg in args):
            print("ERROR: Force push is not allowed.", file=sys.stderr)
            print("This policy protects against accidental history overwrites.",
                  file=sys.stderr)
            return 1

        # Parse remote and branch
        remote, branch = self._parse_push_args(args)

        # Check for protected branches
        if branch in PROTECTED_BRANCHES:
            print(f"ERROR: Push to protected branch '{branch}' is not allowed.",
                  file=sys.stderr)
            return 1

        # Route through gateway if available, otherwise passthrough with notification
        if os.environ.get("USE_GATEWAY"):
            return self._push_via_gateway(remote, branch, args)
        else:
            return self._push_direct_with_notification(remote, branch, args)

    def _parse_push_args(self, args: list[str]) -> tuple[str, str]:
        """Parse remote and branch from push args."""
        remote = "origin"
        branch = self._get_current_branch()

        # Simple parsing: git push [remote] [branch]
        positional = [a for a in args if not a.startswith("-")]
        if len(positional) >= 1:
            remote = positional[0]
        if len(positional) >= 2:
            branch = positional[1].split(":")[-1]  # Handle refspec

        return remote, branch

    def _get_current_branch(self) -> str:
        """Get current branch name."""
        result = subprocess.run(
            [REAL_GIT, "branch", "--show-current"],
            capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    def _push_direct_with_notification(self, remote: str, branch: str,
                                       args: list[str]) -> int:
        """Push directly (Phase 1) with Slack notification."""
        result = subprocess.run(
            [REAL_GIT, "push"] + args,
            capture_output=True, text=True
        )

        if result.returncode == 0:
            self.slack.notify_info(
                title="Branch Pushed",
                body=f"**Repository**: {self.repo_name}\n"
                     f"**Branch**: {branch}\n"
                     f"**Remote**: {remote}"
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        else:
            print(result.stderr, file=sys.stderr)

        return result.returncode

    def _push_via_gateway(self, remote: str, branch: str, args: list[str]) -> int:
        """Push via gateway sidecar (Phase 2)."""
        import requests

        try:
            response = requests.post(
                f"{GATEWAY_URL}/api/git/push",
                json={
                    "repo_path": os.getcwd(),
                    "remote": remote,
                    "branch": branch,
                    "force": False  # Never allow force
                },
                timeout=60
            )

            result = response.json()
            if result.get("success"):
                self.slack.notify_info(
                    title="Branch Pushed",
                    body=f"**Repository**: {self.repo_name}\n"
                         f"**Branch**: {branch}\n"
                         f"**Remote**: {remote}"
                )
                print(result.get("stdout", ""))
                return 0
            else:
                print(f"Error: {result.get('error')}", file=sys.stderr)
                return 1

        except requests.exceptions.RequestException as e:
            print(f"Gateway error: {e}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    wrapper = GitWrapper()
    sys.exit(wrapper.run(sys.argv[1:]))
```

#### Command Behaviors

| Command | Behavior |
|---------|----------|
| `git push` | Routes through gateway (or direct with notification), sends Slack notification on success |
| `git push --force` | **BLOCKED** - Force push not allowed |
| `git push -f` | **BLOCKED** - Force push not allowed |
| `git push --force-with-lease` | **BLOCKED** - Force push not allowed |
| `git push origin main` | **BLOCKED** - Protected branch |
| `git push origin master` | **BLOCKED** - Protected branch |
| `git push -u origin feature-branch` | Allowed, sends Slack notification |
| All other git commands | Pass-through to real git (clone, checkout, commit, branch, log, diff, status, fetch, pull, merge, rebase, stash, etc.) |

#### Slack Notification on Push

```
📤 Branch Pushed

Repository: owner/repo
Branch: jib-temp-feature-xyz
Remote: origin
```

#### Integration with Gateway

Same phased approach as gh wrapper:
1. **Phase 1**: Wrapper enforces policies locally, sends notifications, uses real git for push (with existing auth)
2. **Phase 2**: Wrapper routes push through gateway for full credential isolation

### 6. gh CLI Wrapper

Rather than a Python client library, provide a **`gh` CLI wrapper** that:
1. Maintains the same interface as the real `gh` CLI (existing commands work unchanged)
2. Enforces security policies (no merge, ownership checks)
3. Sends Slack notifications for key operations (PR create, PR comment)
4. Handles writable vs non-writable repos appropriately

This approach is preferred because:
- Agent and existing scripts can continue using familiar `gh` syntax
- No code changes needed for basic operations
- Wrapper intercepts and enhances behavior transparently
- Consolidates behavior currently split across `create-pr-helper.py` and `comment-pr-helper.py`

#### Wrapper Design

The wrapper is placed in PATH before the real `gh` binary:

```python
#!/usr/bin/env python3
# /jib/wrappers/gh
"""
gh wrapper - provides same interface as gh CLI with added features:
- Policy enforcement (no merge, ownership checks)
- Slack notifications (PR create, comments)
- Write-only vs read-write repo handling
"""
import sys
import subprocess
import os
from pathlib import Path

# Add shared directory for notifications
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
from notifications import get_slack_service
from config.repo_config import is_writable_repo, get_writable_repos

REAL_GH = "/usr/bin/gh"
GATEWAY_URL = os.environ.get("GATEWAY_API_URL", "http://gateway:8080")

class GhWrapper:
    def __init__(self):
        self.slack = get_slack_service()
        self.repo_name = self._get_repo_name()
        self.is_writable = is_writable_repo(self.repo_name) if self.repo_name else False

    def _get_repo_name(self) -> str:
        """Get owner/repo from git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, check=True
            )
            url = result.stdout.strip()
            if "github.com" in url:
                if ":" in url and "@" in url:
                    return url.split(":")[-1].replace(".git", "")
                return url.split("github.com/")[-1].replace(".git", "")
        except subprocess.CalledProcessError:
            pass
        return ""

    def run(self, args: list[str]) -> int:
        """Main entry point - parse and dispatch commands."""
        if not args:
            return self._passthrough([])

        cmd = args[0]
        if cmd == "pr":
            return self._handle_pr(args[1:])
        else:
            return self._passthrough(args)

    def _passthrough(self, args: list[str]) -> int:
        """Pass command through to real gh."""
        return subprocess.run([REAL_GH] + args).returncode

    def _handle_pr(self, args: list[str]) -> int:
        """Handle pr subcommands with policy enforcement."""
        if not args:
            return self._passthrough(["pr"])

        subcmd = args[0]
        rest = args[1:]

        if subcmd == "merge":
            # BLOCKED: Never allow merge
            print("ERROR: PR merge is not allowed. Human must merge via GitHub UI.",
                  file=sys.stderr)
            return 1

        elif subcmd == "create":
            return self._pr_create(rest)

        elif subcmd == "comment":
            return self._pr_comment(rest)

        elif subcmd in ("close", "edit"):
            return self._pr_modify(subcmd, rest)

        else:
            # Pass through: view, list, checkout, etc.
            return self._passthrough(["pr", subcmd] + rest)

    def _pr_create(self, args: list[str]) -> int:
        """Create PR with Slack notification."""
        if not self.is_writable:
            return self._notify_manual_pr_needed(args)

        result = subprocess.run(
            [REAL_GH, "pr", "create"] + args,
            capture_output=True, text=True
        )

        if result.returncode == 0:
            pr_url = result.stdout.strip()
            title = self._extract_arg(args, "--title", "-t") or "New PR"
            self.slack.notify_success(
                title="Pull Request Created",
                body=f"**URL**: {pr_url}\n**Repository**: {self.repo_name}\n**Title**: {title}"
            )
            print(pr_url)
        else:
            print(result.stderr, file=sys.stderr)

        return result.returncode

    def _pr_comment(self, args: list[str]) -> int:
        """Add PR comment with Slack notification."""
        pr_num = self._extract_pr_number(args)
        body = self._extract_arg(args, "--body", "-b")

        if not self.is_writable:
            self.slack.notify_action_required(
                title=f"PR Comment Needed (#{pr_num})",
                body=f"**Repository**: {self.repo_name}\n**PR**: #{pr_num}\n\n"
                     f"**Comment to post:**\n\n{body}"
            )
            print(f"Comment sent via Slack for manual posting to PR #{pr_num}")
            return 0

        result = subprocess.run(
            [REAL_GH, "pr", "comment"] + args,
            capture_output=True, text=True
        )

        if result.returncode == 0:
            self.slack.notify_info(
                title=f"PR Comment Added (#{pr_num})",
                body=f"**Repository**: {self.repo_name}\n**PR**: #{pr_num}\n\n"
                     f"{body[:200]}..."
            )
            print(result.stdout)
        else:
            print(result.stderr, file=sys.stderr)

        return result.returncode

    def _pr_modify(self, subcmd: str, args: list[str]) -> int:
        """Handle close/edit with ownership check."""
        pr_num = self._extract_pr_number(args)
        owner = self._get_pr_owner(pr_num)
        jib_user = os.environ.get("JIB_GITHUB_USERNAME", "jwbron")

        if owner != jib_user:
            print(f"ERROR: Cannot {subcmd} PR #{pr_num} - owned by {owner}, not {jib_user}",
                  file=sys.stderr)
            return 1

        return self._passthrough(["pr", subcmd] + args)

    def _notify_manual_pr_needed(self, args: list[str]) -> int:
        """Send Slack notification for non-writable repos."""
        title = self._extract_arg(args, "--title", "-t") or "New PR"
        body = self._extract_arg(args, "--body", "-b") or ""
        branch = self._get_current_branch()

        self.slack.notify_action_required(
            title="PR Creation Needed (Non-Writable Repo)",
            body=f"**Repository**: {self.repo_name}\n**Branch**: {branch}\n"
                 f"**Title**: {title}\n\n**Description:**\n{body[:500]}...\n\n"
                 "Please create this PR manually from the host machine."
        )
        print(f"PR details sent via Slack. Please create manually for {self.repo_name}")
        return 0

    # Helper methods for arg parsing
    def _extract_arg(self, args: list[str], *flags) -> str:
        for i, arg in enumerate(args):
            for flag in flags:
                if arg == flag and i + 1 < len(args):
                    return args[i + 1]
                if arg.startswith(f"{flag}="):
                    return arg.split("=", 1)[1]
        return ""

    def _extract_pr_number(self, args: list[str]) -> str:
        for arg in args:
            if arg.isdigit():
                return arg
        return "unknown"

    def _get_current_branch(self) -> str:
        result = subprocess.run(
            ["git", "branch", "--show-current"], capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    def _get_pr_owner(self, pr_num: str) -> str:
        result = subprocess.run(
            [REAL_GH, "pr", "view", pr_num, "--json", "author", "--jq", ".author.login"],
            capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else ""


if __name__ == "__main__":
    wrapper = GhWrapper()
    sys.exit(wrapper.run(sys.argv[1:]))
```

#### Command Behaviors by Repo Type

| Command | Writable Repo | Non-Writable Repo |
|---------|---------------|-------------------|
| `gh pr create` | Creates PR + Slack notification | Sends Slack notification for manual creation |
| `gh pr comment` | Posts comment + Slack notification | Sends comment via Slack for manual posting |
| `gh pr close` | Closes (jib's PRs only) | Sends Slack notification for manual close |
| `gh pr edit` | Edits (jib's PRs only) | Sends Slack notification for manual edit |
| `gh pr merge` | **BLOCKED** | **BLOCKED** |
| `gh pr view/list/checkout` | Pass-through | Pass-through |
| Other `gh` commands | Pass-through | Pass-through |

#### Slack Notification Examples

**PR Created (writable repo):**
```
🎉 Pull Request Created

URL: https://github.com/owner/repo/pull/123
Repository: owner/repo
Title: Add new feature
```

**PR Comment Added:**
```
💬 PR Comment Added (#123)

Repository: owner/repo
PR: #123

First 200 chars of comment...
```

**Non-Writable Repo - Manual Action Required:**
```
⚠️ PR Creation Needed (Non-Writable Repo)

Repository: owner/external-repo
Branch: jib-temp-feature-xyz
Title: Fix critical bug

Description:
[First 500 chars of body]

Please create this PR manually from the host machine.
```

#### Integration with Gateway

When the gateway-sidecar architecture is fully deployed, the wrapper routes authenticated operations through the gateway API instead of calling the real `gh` directly:

```python
def _pr_create_via_gateway(self, args):
    """Route PR creation through gateway sidecar."""
    import requests

    response = requests.post(f"{GATEWAY_URL}/api/gh/pr/create", json={
        "repo_path": os.getcwd(),
        "title": self._extract_arg(args, "--title"),
        "body": self._extract_arg(args, "--body"),
        "base": self._extract_arg(args, "--base") or "main"
    })

    result = response.json()
    if result.get("success"):
        self._send_slack_notification("PR Created", result)
        print(result.get("url"))
        return 0
    else:
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1
```

This allows a phased rollout:
1. **Phase 1**: Wrapper with direct `gh` calls + Slack notifications (no gateway yet)
2. **Phase 2**: Wrapper routes through gateway for full credential isolation

### 7. Network Rules for GitHub Blocking

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
2. Install git wrapper in jib container (in PATH before /usr/bin/git)
3. Install gh wrapper in jib container (in PATH before /usr/bin/gh)
4. Migrate from create-pr-helper.py / comment-pr-helper.py to gh wrapper
5. Test full workflow with both wrappers

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
