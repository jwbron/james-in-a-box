# ADR: Git Isolation Architecture for Autonomous AI Agents

**Status:** Implemented (core), Binary Removal proposed
**Date:** 2026-01-27 (core), 2026-01-28 (Binary Removal)
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

## Implementation Status

- [x] Gateway-managed worktree creation/deletion
- [x] Git command routing through gateway API
- [x] Operation and flag allowlist validation
- [x] Branch ownership policy enforcement
- [x] Orphaned worktree cleanup on startup
- [x] tmpfs mount shadowing for .git
- [ ] Batch operation endpoint (optimization)
- [ ] Cloud Run checkpoint/restore
- [ ] Full git/gh binary removal from container (proposed, see below)

---

## Proposed Enhancement: Full Binary Removal

**Status:** Proposed (implementation plan complete, pending execution)

### Motivation

The current architecture relocates the real `git` and `gh` binaries to `/opt/.jib-internal/` and uses wrapper scripts at `/usr/bin/`. While effective, an attacker who gains code execution could potentially:

1. Call the relocated binaries directly at `/opt/.jib-internal/git`
2. Bypass the wrappers via environment manipulation (e.g., `LD_PRELOAD`)
3. Use the binaries to perform unauthorized operations

Fully removing the binaries from the container eliminates these attack vectors entirely.

### Current State

```
Container:
  /usr/bin/git  →  symlink to wrapper script (/opt/jib-runtime/jib-container/scripts/git)
  /usr/bin/gh   →  symlink to wrapper script (/opt/jib-runtime/jib-container/scripts/gh)
  /opt/.jib-internal/git  ←  Real git binary (~3.5MB) - retained
  /opt/.jib-internal/gh   ←  Real gh binary (~35MB) - retained
```

### Proposed State

```
Container:
  /usr/bin/git  →  wrapper script (pure HTTP client, no git binary dependency)
  /usr/bin/gh   →  wrapper script (pure HTTP client, no gh binary dependency)
  (No real git/gh binaries exist in the container)
```

### Code Analysis

#### gh Binary (Line 15 of `jib-container/scripts/gh`)

**Current code:**
```bash
REAL_GH=/opt/.jib-internal/gh
```

**Usage in wrapper:** The `REAL_GH` variable is **declared but never used**. All `gh` commands are routed through `execute_via_gateway()` which makes HTTP calls to the gateway sidecar. The gh wrapper is already a pure HTTP client.

**Verdict:** ✅ gh binary can be removed with zero code changes (only cosmetic cleanup to remove the unused variable)

#### git Binary (Lines 17, 674 of `jib-container/scripts/git`)

**Current code:**
```bash
REAL_GIT=/opt/.jib-internal/git  # Line 17
```

**Usage in wrapper (Line 674):**
```bash
if $is_global; then
    # Global config operations don't need gateway - use real git
    # These operate on ~/.gitconfig, not on any repo
    exec "$REAL_GIT" config "${extra_args[@]}"
```

**Analysis:** The only use of the real git binary is for `git config --global` operations. This handles commands like:
- `git config --global user.name "Name"`
- `git config --global user.email "email@example.com"`
- `git config --global core.editor "vim"`

**Verdict:** ✅ git binary can be removed with minor changes to handle global config differently

### Security Benefits

1. **Defense in depth:** Even if wrappers are bypassed, there's literally no binary to exploit
2. **Reduced attack surface:** Eliminates ~40MB of potentially exploitable binaries
3. **Smaller container image:** Reduces image size by ~40MB
4. **Clearer security audit:** "No git binary exists" is easier to verify than "git is shadowed"
5. **Principle of least privilege:** Container truly cannot perform direct git operations

### Implementation Plan

#### Phase 1: Remove gh Binary (Zero Risk)

**Files to modify:**

1. `jib-container/Dockerfile` (lines 33-38, 104-111):
   - Remove gh installation OR
   - Keep installation but don't relocate (wrapper doesn't need it)

   **Recommended approach:** Keep gh installed (some tools check for `gh --version`) but remove the relocation step. The wrapper intercepts all calls anyway.

2. `jib-container/scripts/gh` (line 15):
   - Remove unused `REAL_GH=/opt/.jib-internal/gh` declaration (cosmetic)

**Testing:**
- Run full test suite
- Verify `gh pr create`, `gh pr view`, `gh api` work correctly
- Verify `gh --version` returns meaningful response (wrapper can synthesize this)

**Risk:** None - the variable is already unused

#### Phase 2: Remove git Binary (Low Risk)

**Files to modify:**

1. `jib-container/scripts/git` (lines 17, 658-679):
   - Remove `REAL_GIT` declaration
   - Modify `git config --global` handling

**Global config handling options:**

| Option | Pros | Cons | Recommended |
|--------|------|------|-------------|
| **A. Edit ~/.gitconfig directly** | Simple, no gateway changes | Requires Python/sed in wrapper | ✅ Yes |
| **B. Route through gateway** | Centralizes all git | Gateway complexity, overkill | No |
| **C. Pre-configure in Dockerfile** | Zero runtime handling | Not flexible | Partial |
| **D. Block global config** | Simplest | May break some tools | No |

**Recommended approach: Option A + C combined**

Pre-configure common settings in Dockerfile:
```dockerfile
# Pre-configure git globals (no git binary needed at runtime)
RUN git config --system init.defaultBranch main && \
    git config --system core.editor "nano" && \
    git config --system color.ui auto
```

Handle remaining global config in wrapper by editing `~/.gitconfig` directly:
```bash
handle_global_config() {
    local args=("$@")

    # Parse: git config --global [--get|--unset|key] [value]
    local operation="set"
    local key=""
    local value=""

    for arg in "${args[@]}"; do
        case "$arg" in
            --global) continue ;;
            --get) operation="get" ;;
            --unset) operation="unset" ;;
            --list) operation="list" ;;
            -*)  ;;
            *)
                if [ -z "$key" ]; then
                    key="$arg"
                else
                    value="$arg"
                fi
                ;;
        esac
    done

    local config_file="$HOME/.gitconfig"

    case "$operation" in
        list)
            [ -f "$config_file" ] && cat "$config_file"
            ;;
        get)
            # Use Python to parse INI-style config
            python3 -c "
import configparser
import sys
c = configparser.ConfigParser()
c.read('$config_file')
section, key = '$key'.rsplit('.', 1)
try:
    print(c.get(section, key))
except:
    sys.exit(1)
"
            ;;
        set)
            # Use Python to write INI-style config
            python3 -c "
import configparser
import os
c = configparser.ConfigParser()
c.read('$config_file')
section, key = '$key'.rsplit('.', 1)
if section not in c:
    c.add_section(section)
c.set(section, key, '$value')
with open('$config_file', 'w') as f:
    c.write(f)
"
            ;;
        unset)
            python3 -c "
import configparser
c = configparser.ConfigParser()
c.read('$config_file')
section, key = '$key'.rsplit('.', 1)
try:
    c.remove_option(section, key)
    with open('$config_file', 'w') as f:
        c.write(f)
except:
    pass
"
            ;;
    esac
}
```

2. `jib-container/Dockerfile` (lines 104-111):
   - Remove git binary relocation step

**Testing:**
- Run full test suite
- Test `git config --global user.name "Test"`
- Test `git config --global --get user.name`
- Test `git config --global --list`
- Verify Claude Code works correctly (extensive git user)

**Risk:** Low - only affects global config operations

#### Phase 3: Clean Dockerfile (Optional)

**Alternative approach:** Instead of installing git/gh and relocating, don't install them at all in the container. Only install the minimal dependencies for the wrapper scripts (curl, python3).

**Considerations:**
- Some tools probe for `git` existence via `which git` - wrapper handles this
- `git --version` needs synthetic response - add to wrapper
- Tab completion would break - acceptable for non-interactive containers

**Dockerfile changes:**
```dockerfile
# DON'T install git/gh binaries - all operations via gateway
# RUN apt-get install -y git  # REMOVED
# RUN apt-get install -y gh   # REMOVED

# Instead, just ensure wrapper scripts are in place
COPY scripts/git /usr/bin/git
COPY scripts/gh /usr/bin/gh
RUN chmod +x /usr/bin/git /usr/bin/gh
```

**Risk:** Medium - requires thorough testing with all tools

### Compatibility Considerations

| Concern | Impact | Mitigation |
|---------|--------|------------|
| Tools checking `which git` | Low | Wrapper exists at `/usr/bin/git`, resolves correctly |
| Tools checking `git --version` | Low | Add synthetic version response to wrapper |
| Tab completion | None | Non-interactive containers don't need completion |
| Claude Code | Low | Already works with wrapper; extensive testing confirms |
| Git subcommands via alias | None | Aliases would call wrapper anyway |

### Rollback Plan

If issues arise post-deployment:

1. Revert Dockerfile changes to restore binary relocation
2. Push hotfix to container registry
3. Restart affected containers

No data loss possible - all git state is in gateway-managed worktrees.

### Implementation Checklist

#### Phase 1: gh Binary Removal
- [ ] Update Dockerfile to skip gh binary relocation
- [ ] Remove `REAL_GH` declaration from `jib-container/scripts/gh`
- [ ] Add `gh --version` synthetic response to wrapper
- [ ] Run test suite
- [ ] Manual testing of gh commands
- [ ] Deploy to staging environment
- [ ] Monitor for 24 hours
- [ ] Deploy to production

#### Phase 2: git Binary Removal
- [ ] Update `jib-container/scripts/git` to handle global config via direct file editing
- [ ] Pre-configure common git settings in Dockerfile
- [ ] Update Dockerfile to skip git binary relocation
- [ ] Add `git --version` synthetic response to wrapper
- [ ] Run test suite (including Claude Code integration)
- [ ] Manual testing of git config commands
- [ ] Deploy to staging environment
- [ ] Monitor for 48 hours (longer due to higher risk)
- [ ] Deploy to production

#### Phase 3: Full Removal (Optional)
- [ ] Modify Dockerfile to not install git/gh at all
- [ ] Ensure wrapper scripts are self-contained
- [ ] Update base image selection if needed
- [ ] Full regression testing
- [ ] Deploy with canary rollout

### Files to Modify Summary

| File | Phase | Changes |
|------|-------|---------|
| `jib-container/Dockerfile` | 1, 2, 3 | Remove binary relocation, optionally remove installation |
| `jib-container/scripts/gh` | 1 | Remove unused REAL_GH, add version response |
| `jib-container/scripts/git` | 2 | Replace global config handling, add version response |

### Security Audit Points

After implementation, verify:

1. ✅ No git binary at `/opt/.jib-internal/git`
2. ✅ No gh binary at `/opt/.jib-internal/gh`
3. ✅ `which git` returns `/usr/bin/git` (the wrapper)
4. ✅ `ldd /usr/bin/git` fails (it's a script, not binary)
5. ✅ `find / -name "git" -type f -executable 2>/dev/null` returns nothing except wrapper
6. ✅ All git operations still route through gateway correctly
7. ✅ Gateway audit logs show all operations

---

## References

- [Git Worktrees Documentation](https://git-scm.com/docs/git-worktree)
- [Docker Bind Mounts](https://docs.docker.com/storage/bind-mounts/)
- [Cloud Run Multi-Container](https://cloud.google.com/run/docs/deploying#sidecars)

---

*This document describes the git isolation architecture for the james-in-a-box autonomous agent system. For questions or contributions, see the project repository.*
