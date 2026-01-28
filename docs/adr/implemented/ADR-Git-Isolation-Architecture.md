# ADR: Git Isolation Architecture for Autonomous AI Agents

**Status:** Implemented (core), Private Repo Mode proposed
**Date:** 2026-01-27 (core), 2026-01-28 (Private Repo Mode)
**Supersedes:** ADR-Container-Worktree-Isolation

---

## Executive Summary

This document describes how we safely allow multiple AI agent containers to work on the same git repositories simultaneously, without risking cross-contamination or unauthorized access.

**The core security guarantee**: An AI agent can only see and modify its own isolated workspace. It cannot access other agents' work, cannot directly push to remote repositories, and cannot see credentials. All git operations that touch the network or affect shared state go through a trusted gateway that enforces access policies.

**Key properties:**
- **Complete isolation**: Each agent gets its own branch and working directory
- **No credential exposure**: Agents never see GitHub tokens or SSH keys
- **Enforced code review**: Agents cannot merge their own PRs—humans must review and merge
- **Crash-safe**: System recovers cleanly if an agent container crashes
- **Private Repo Mode** (optional): Restricts agent to private repositories only

---

## Motivation

This document implements the git-specific aspects of [ADR-Internet-Tool-Access-Lockdown](../in-progress/ADR-Internet-Tool-Access-Lockdown.md), which establishes the core principle: **behavioral controls are insufficient for AI agent security**. Instructions can be bypassed by prompt injection, model drift, or adversarial inputs. Security must be enforced at the infrastructure level.

For git operations, this means:
- **Credential isolation**: Agents cannot push directly—no credentials exist in the container
- **Filesystem isolation**: Agents cannot access other agents' workspaces—they don't exist in the container's view
- **Gateway enforcement**: All git operations go through a policy-enforcing gateway

This document focuses on the specific challenge of **multi-agent git isolation**: how multiple agents can work on the same repository simultaneously without cross-contamination.

---

## Threat Model

### Threats Addressed

| Threat | Mitigation |
|--------|------------|
| Agent accesses another agent's workspace | Filesystem isolation—other workspaces don't exist in container's view |
| Agent pushes to unauthorized branches | Gateway enforces branch ownership policy |
| Agent pushes malicious code directly to main | Gateway blocks direct pushes to protected branches; PRs require human review |
| Agent discovers or exfiltrates credentials | Credentials only exist in gateway; container never sees them |
| Agent modifies git config to bypass security | Container has no access to git metadata; config is gateway-controlled |
| Agent escapes via git hooks or filters | No hooks/filters in container; only gateway executes git commands |
| Crashed container corrupts shared state | Gateway cleans up orphaned workspaces on startup |

### Explicit Non-Goals

This architecture does **not** protect against:
- Malicious agents with root access to the container (defense in depth via container sandboxing)
- Network-level attacks between containers (addressed by network policies)
- Compromise of the gateway itself (gateway runs with minimal attack surface)

---

## Security Model

### Principle: Complete Metadata Isolation

The fundamental security property is that **agents never touch git metadata**. The container mounts only the working directory (source files), with the `.git` path shadowed by an empty tmpfs:

```
Container filesystem view:
/home/jib/repos/my-repo/
├── src/                 ← Agent can edit these files
├── tests/               ← Agent can edit these files
├── README.md            ← Agent can edit this file
└── .git/                ← Empty directory (tmpfs shadow)
```

Without git metadata, the agent cannot:
- Discover where the repository came from
- See commit history directly
- Modify the staging area directly
- Change branch pointers
- Execute git hooks
- Access other worktrees

### Principle: Gateway as Security Boundary

All git operations that require metadata access go through the gateway:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Container (Untrusted)                  │
│                                                                 │
│   The agent runs 'git status', which invokes the git wrapper    │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Git Wrapper Script                                     │   │
│   │  - Intercepts all git commands                          │   │
│   │  - Cannot bypass (no git metadata = native git fails)   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
└──────────────────────────────│───────────────────────────────────┘
                               │ HTTP API call
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Gateway Sidecar (Trusted)                    │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Request Validation                                     │   │
│   │  - Verify container identity                            │   │
│   │  - Check operation against allowlist                    │   │
│   │  - Validate flags (block dangerous options)             │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Policy Enforcement                                     │   │
│   │  - Branch ownership: only push to agent's own branches  │   │
│   │  - Protected branches: block direct push to main        │   │
│   │  - Merge blocking: agents cannot merge PRs              │   │
│   └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Git Execution                                          │   │
│   │  - Execute in correct worktree context                  │   │
│   │  - Inject credentials for network operations            │   │
│   │  - Return sanitized output to container                 │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Security Properties

1. **Filesystem isolation**: Containers cannot see other containers' working directories
2. **Metadata isolation**: Containers have no access to git metadata (`.git/` contents)
3. **Credential isolation**: GitHub tokens exist only in the gateway, never in containers
4. **Operation allowlist**: Gateway only permits known-safe git operations and flags
5. **Branch ownership**: Containers can only push to branches they created
6. **Merge prevention**: Containers cannot merge PRs—humans must review and merge
7. **Audit trail**: All git operations are logged through the gateway

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Shared Storage                                │
│                                                                          │
│  /repos/                              ← Main repositories                │
│  └── my-repo/                         ← Standard git repo                │
│      └── .git/                                                           │
│          ├── objects/                 ← Shared objects (all worktrees)   │
│          ├── refs/                    ← Shared refs                      │
│          └── worktrees/               ← Worktree metadata (gateway only) │
│              ├── agent-abc123/        ← Metadata for agent abc123        │
│              └── agent-def456/        ← Metadata for agent def456        │
│                                                                          │
│  /worktrees/                          ← Working directories              │
│      ├── agent-abc123/                                                   │
│      │   └── my-repo/                 ← Agent abc123's working dir       │
│      └── agent-def456/                                                   │
│          └── my-repo/                 ← Agent def456's working dir       │
└─────────────────────────────────────────────────────────────────────────┘
                    │                              │
                    ▼                              ▼
     ┌──────────────────────────┐    ┌──────────────────────────┐
     │   Agent Container        │    │   Gateway Sidecar        │
     │                          │    │                          │
     │  Mounts ONLY:            │    │  Has access to:          │
     │  /worktrees/abc123/      │    │  /repos/                 │
     │    my-repo/              │    │  /worktrees/             │
     │  → /home/jib/repos/      │    │                          │
     │                          │    │  Manages:                │
     │  Can do:                 │    │  - Worktree lifecycle    │
     │  - Edit source files     │    │  - All git operations    │
     │                          │    │  - Push/fetch to GitHub  │
     │  Cannot do:              │    │  - Policy enforcement    │
     │  - See other worktrees   │    │                          │
     │  - Access .git metadata  │    │                          │
     │  - See credentials       │    │                          │
     └──────────────────────────┘    └──────────────────────────┘
                    │                              ▲
                    │           HTTP API           │
                    └──────────────────────────────┘
```

### Container Lifecycle

```
1. Agent Startup
   ┌──────────────────────────────────────────────────────────────────┐
   │  Gateway receives request to create workspace for agent-abc123   │
   │                              │                                   │
   │                              ▼                                   │
   │  git worktree add /worktrees/abc123/my-repo -b agent/abc123/work │
   │                              │                                   │
   │                              ▼                                   │
   │  Return worktree path to orchestrator                            │
   └──────────────────────────────────────────────────────────────────┘

2. Container Launch
   ┌──────────────────────────────────────────────────────────────────┐
   │  docker run                                                      │
   │    -v /worktrees/abc123/my-repo:/home/jib/repos/my-repo:rw      │
   │    --mount type=tmpfs,destination=/home/jib/repos/my-repo/.git   │
   │    -e CONTAINER_ID=abc123                                        │
   │    agent-image                                                   │
   │                                                                  │
   │  The tmpfs mount shadows .git, giving agent no git metadata      │
   └──────────────────────────────────────────────────────────────────┘

3. Normal Operation
   ┌──────────────────────────────────────────────────────────────────┐
   │  Agent edits files directly in /home/jib/repos/my-repo/         │
   │  Agent runs 'git add', 'git commit' → routed through gateway    │
   │  Agent runs 'git push' → gateway authenticates and pushes       │
   │  Agent runs 'gh pr create' → gateway handles API call           │
   └──────────────────────────────────────────────────────────────────┘

4. Container Shutdown
   ┌──────────────────────────────────────────────────────────────────┐
   │  Gateway receives cleanup request                                │
   │                              │                                   │
   │                              ▼                                   │
   │  Check for uncommitted changes (warn if present)                 │
   │                              │                                   │
   │                              ▼                                   │
   │  git worktree remove /worktrees/abc123/my-repo                  │
   └──────────────────────────────────────────────────────────────────┘
```

### Multi-Agent Isolation

Each agent works on its own isolated branch with its own staging area:

| Agent | Working Directory | Branch | Index (Staging) |
|-------|-------------------|--------|-----------------|
| abc123 | `/worktrees/abc123/my-repo/` | `agent/abc123/work` | Isolated |
| def456 | `/worktrees/def456/my-repo/` | `agent/def456/work` | Isolated |

**Guarantees:**
- Agents cannot see each other's uncommitted changes
- Agents can work on different branches simultaneously
- All agents share commit history and git objects (efficient storage)
- Gateway manages worktree metadata—agents never touch it

---

## Gateway Operations

### Allowed Git Operations

The gateway implements an explicit allowlist. Operations not on this list are rejected.

| Category | Operations | Notes |
|----------|------------|-------|
| Read | `status`, `diff`, `log`, `show`, `blame`, `branch --list` | Informational only |
| Stage | `add`, `reset` (non-destructive modes) | Modify staging area |
| Commit | `commit` | Create commits |
| Branch | `checkout`, `switch`, `branch` (create/delete own branches) | Branch management |
| Network | `push`, `fetch`, `pull` | Credentials injected by gateway |
| GitHub | `gh pr create`, `gh pr comment`, `gh issue` | API calls via gateway |

### Blocked Operations

| Operation | Why Blocked |
|-----------|-------------|
| `git merge` to protected branches | Must go through PR review |
| `gh pr merge` | Human must review and merge |
| `git push --force` to others' branches | Could destroy others' work |
| `git config --global` | Could affect other agents |
| `git remote add/remove` | Could redirect pushes |

### Blocked Flags

The gateway blocks dangerous flags across all operations:

| Flag | Risk |
|------|------|
| `--exec`, `-c` | Command injection via config/scripts |
| `--upload-pack`, `--receive-pack` | Arbitrary command execution on fetch/push |
| `--config`, `-c` | Runtime config override |
| `--no-verify` | Skip hooks (defense in depth) |
| `--git-dir`, `--work-tree` | Path traversal outside sandbox |

### Flag Validation

Each operation has an explicit allowlist of permitted flags. Unknown flags are rejected:

```python
# Example: 'git commit' allowed flags
"commit": {
    "allowed_flags": [
        "--message", "-m",
        "--amend",          # Only own recent commits
        "--allow-empty",
        "--author",
        "--signoff", "-s",
        "--verbose", "-v",
        "--quiet", "-q",
    ],
}
```

---

## Deployment Scenarios

The architecture works identically across deployment environments:

| Aspect | Local (Docker) | Cloud (Cloud Run) |
|--------|----------------|-------------------|
| Shared storage | Docker bind mounts | emptyDir or GCS FUSE |
| Gateway communication | Docker network | localhost (sidecar) |
| Container startup | Gateway creates worktree | Same |
| Credential storage | Local files | Secret Manager |
| Persistence | Host filesystem | GCS checkpoint (optional) |

### Cloud Run Specifics

On Cloud Run, containers are stateless and can be preempted. Additional considerations:

1. **Git state checkpointing**: Periodically save git bundles to Cloud Storage
2. **Session affinity**: Route requests for one session to the same instance
3. **Startup recovery**: Restore from checkpoint if container was preempted

---

## Crash Recovery

If an agent container crashes without cleanup:

1. **On next gateway startup**: Gateway scans for orphaned worktrees
2. **Orphan detection**: Compare worktree list against active containers
3. **Cleanup**: Remove worktrees for containers that no longer exist
4. **Branch preservation**: Committed work is preserved; only working directory removed

```python
def cleanup_orphaned_worktrees():
    """Remove worktrees for containers that no longer exist."""
    worktrees = list_all_worktrees()
    active_containers = get_active_containers()

    for worktree in worktrees:
        container_id = extract_container_id(worktree.path)
        if container_id not in active_containers:
            # Log warning if uncommitted changes
            if has_uncommitted_changes(worktree.path):
                log.warning(f"Removing worktree with uncommitted changes: {container_id}")
            remove_worktree(worktree.path, force=True)
```

---

## Performance Considerations

**Concern:** All git operations go over HTTP—is this slow?

**Analysis:**
- Local HTTP latency: ~0.1-1ms per request
- Typical `git status`: 10-100ms (I/O bound)
- HTTP overhead: <10% for most operations

**Benchmarks (estimated):**

| Operation | Direct Git | Via Gateway | Overhead |
|-----------|-----------|-------------|----------|
| git status | 50ms | 55ms | ~10% |
| git diff | 30ms | 35ms | ~17% |
| git commit | 100ms | 110ms | ~10% |

The overhead is acceptable given the security benefits. Optimizations (batching, caching) can be added if needed.

---

## Why This Design?

### Alternatives Considered

**1. Behavioral controls only**
- Rely on instructions telling agents not to access other workspaces
- **Rejected:** The security incident proved this insufficient

**2. Mount restriction isolation (previous approach)**
- Each container mounts only its own worktree admin directory
- Local git operations run in container
- **Rejected:** Required complex path rewriting; host git broken while containers run

**3. Overlayfs isolation**
- Each container gets copy-on-write view via overlayfs
- **Rejected:** Doesn't work on Cloud Run; different architecture per environment

**4. Full clone per container**
- Each container gets complete independent clone
- **Rejected:** Wasteful storage; complex sync requirements

### Why Gateway-Managed Worktrees?

The chosen approach provides:
- **Uniform architecture** across local and cloud deployments
- **Simple security model** (no git metadata in container = no git-based attacks)
- **Efficient storage** (worktrees share git objects)
- **Fast workspace creation** (O(1) via git worktree)
- **Clean crash recovery** (gateway manages all state)

---

## Private Repo Mode

**Status:** Proposed extension

Private Repo Mode restricts jib to only interact with **private** GitHub repositories, preventing any interaction with public repositories.

### Motivation

When operating on sensitive codebases, there's risk of:
1. **Accidental code sharing:** Agent might reference or copy code to a public repository
2. **Data leakage via forks:** Agent could fork a private repo to a public destination
3. **Cross-contamination:** Agent might mix private code with public dependencies

Private Repo Mode addresses these risks by ensuring jib can only see and modify private repositories.

### Design

The gateway enforces repository visibility at the policy layer:

```python
# Gateway policy check for all git operations
def validate_repository_access(repo: str, operation: str) -> bool:
    """
    In Private Repo Mode, only allow access to private repositories.
    """
    if not PRIVATE_REPO_MODE_ENABLED:
        return True  # Standard mode: all repos allowed

    visibility = get_repo_visibility(repo)  # GitHub API call, cached

    if visibility == "public":
        log.warning(f"Blocked {operation} on public repo: {repo}")
        return False

    return True  # private or internal repos allowed
```

### Enforced Restrictions

| Operation | Public Repo | Private Repo |
|-----------|-------------|--------------|
| `git clone` | ❌ Blocked | ✓ Allowed |
| `git fetch` | ❌ Blocked | ✓ Allowed |
| `git push` | ❌ Blocked | ✓ Allowed |
| `gh pr create` | ❌ Blocked | ✓ Allowed |
| `gh issue view` | ❌ Blocked | ✓ Allowed |
| `gh repo fork` | ❌ Blocked (either direction) | ✓ Allowed (to private only) |

### Configuration

Private Repo Mode is enabled via environment variable in the gateway:

```yaml
# docker-compose.yml
services:
  gateway-sidecar:
    environment:
      - PRIVATE_REPO_MODE=true
```

### Edge Cases

**Forking:**
- Fork from private → private: ✓ Allowed
- Fork from private → public: ❌ Blocked
- Fork from public → anywhere: ❌ Blocked

**Upstream references:**
- If a private repo has a public upstream, fetch from upstream is blocked
- Agent must work only with the private fork

**Organization visibility:**
- GitHub "internal" repositories (visible within org) are treated as private
- Only "public" visibility is blocked

### Implementation Checklist

- [ ] Add `PRIVATE_REPO_MODE` environment variable
- [ ] Add `get_repo_visibility()` function with caching
- [ ] Add policy check to all repository operations
- [ ] Add audit logging for blocked public repo access
- [ ] Test with mixed public/private repo scenarios
- [ ] Document supervised mode override for public repo access

---

## Implementation Status

- [x] Gateway-managed worktree creation/deletion
- [x] Git command routing through gateway API
- [x] Operation and flag allowlist validation
- [x] Branch ownership policy enforcement
- [x] Orphaned worktree cleanup on startup
- [x] tmpfs mount shadowing for .git
- [ ] Batch operation endpoint (optimization)
- [ ] Cloud Run checkpoint/restore

---

## References

- [Git Worktrees Documentation](https://git-scm.com/docs/git-worktree)
- [Docker Bind Mounts](https://docs.docker.com/storage/bind-mounts/)
- [Cloud Run Multi-Container](https://cloud.google.com/run/docs/deploying#sidecars)

---

*This document describes the git isolation architecture for the james-in-a-box autonomous agent system. For questions or contributions, see the project repository.*
