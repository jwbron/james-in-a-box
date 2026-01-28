# ADR: Git Isolation Architecture

**Status:** Proposed
**Date:** 2026-01-27
**Supersedes:** ADR-Container-Worktree-Isolation
**Related PRs:** #590, #592, #594

---

## Context

### The Original Problem

PR #590 implemented git worktree isolation to allow multiple jib containers to work on the same repository without affecting each other. The implementation modified git metadata files (`gitdir`, `commondir`) in shared bind-mounted directories to use container-internal paths (e.g., `/home/jib/.git-admin/repo`).

This approach had fundamental problems discovered in PR #594:

1. **Host git operations break** while any container is running - host sees container paths that don't exist
2. **Crash recovery required** - if container exits abnormally, corrupted paths persist on host
3. **Complex mount structure** - required `.git-admin`, `.git-common`, and multiple bind mounts
4. **Path conflicts are inherent** - container paths and host paths cannot both be valid simultaneously

### Requirements Evolution

Initial requirements:
- Multiple containers can work on the same repo without affecting each other
- Gateway sidecar can access repos for push/fetch operations

Additional requirements discovered during analysis:
- **Host git must work** while containers are running
- **Same architecture** for local and Cloud Run deployments
- **Fast workspace creation** for new containers/requests (milliseconds, not file copies)
- **Single repo** with isolated workspaces, not full clones per container

### Approaches Considered

**1. Overlayfs isolation (local only)**
- Each container gets copy-on-write view of repo via overlayfs
- Host sees base layer, container sees modifications in upper layer
- Problem: Doesn't work on Cloud Run (no overlayfs), requires different architecture per environment

**2. Git bundle checkpointing (Cloud Run)**
- Store git state as bundles in Cloud Storage
- Download/restore on container start, checkpoint periodically
- Problem: Different architecture from local, adds complexity and latency

**3. Cleanup scripts for crash recovery**
- Run scripts to restore host paths from backups after container crash
- Problem: Doesn't solve the fundamental issue - host git still broken while container runs

**4. Gateway-managed git (all operations via HTTP)**
- Route ALL git operations through gateway sidecar
- Container only edits files, never touches git metadata
- Initially rejected in PR #590 for performance concerns (~10% HTTP overhead)
- Reconsidered: overhead is negligible, and it eliminates all path conflict issues

**5. Gateway-managed worktrees (chosen approach)**
- Combine worktrees (fast creation, shared objects) with gateway management
- Gateway creates/manages worktrees, handles all git operations
- Container mounts only working directory with `.git` read-only
- Same architecture works on local, VM, and Cloud Run

### Why Gateway-Managed Worktrees?

The key insight: **use git's native worktree feature for isolation, but have the gateway manage it**.

- Worktrees provide fast workspace creation (O(1) - just metadata)
- Worktrees share git objects (efficient storage)
- Gateway managing worktrees means containers never touch git metadata
- No path rewriting needed - gateway controls all paths internally
- Same architecture works everywhere - only the volume backend changes

---

## Decision

Adopt **gateway-managed worktrees** as the git isolation architecture:

1. **Gateway manages worktree lifecycle** - creates, deletes, and operates on worktrees
2. **All git operations go through gateway** - container's git wrapper routes to gateway API
3. **Container mounts only working directory** - with `.git` file as read-only
4. **Worktree admin directories not exposed** - gateway manages internally
5. **Same architecture for all deployments** - local, VM, Cloud Run

This approach:
- Eliminates path conflicts (container never sees git metadata paths)
- Allows host git to work while containers run
- Provides fast workspace creation via worktrees
- Simplifies the mount structure (one directory per container)
- Works identically across deployment environments

---

# Implementation: Gateway-Managed Worktrees

The simplest architecture: gateway manages git worktrees, containers only see their working directory.

## Key Design Goals

1. **Fast workspace creation** - New container/request gets isolated workspace in milliseconds
2. **Efficient storage** - All worktrees share git objects (no file duplication)
3. **True isolation** - Containers can't see or affect each other
4. **No path conflicts** - Containers never touch git metadata
5. **Same architecture everywhere** - Works on local, VM, and Cloud Run

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Shared Volume                                 │
│                                                                          │
│  /workspace/                                                             │
│  ├── repos/                                                              │
│  │   └── my-repo.git/              ← Main repo (bare or .git directory) │
│  │       ├── objects/               ← Shared objects (all worktrees)    │
│  │       ├── refs/                  ← Shared refs                       │
│  │       └── worktrees/             ← Worktree admin (gateway-managed)  │
│  │           ├── wt-abc123/         ← Metadata for worktree abc123      │
│  │           └── wt-def456/         ← Metadata for worktree def456      │
│  │                                                                       │
│  └── worktrees/                     ← Working directories                │
│      ├── abc123/                                                         │
│      │   └── my-repo/               ← Container abc123's working dir    │
│      └── def456/                                                         │
│          └── my-repo/               ← Container def456's working dir    │
└─────────────────────────────────────────────────────────────────────────┘
                    │                              │
                    ▼                              ▼
     ┌──────────────────────────┐    ┌──────────────────────────┐
     │     jib container        │    │    gateway sidecar       │
     │                          │    │                          │
     │  Mounts ONLY:            │    │  Mounts ALL:             │
     │  /workspace/worktrees/   │    │  /workspace/             │
     │    {id}/my-repo/         │    │                          │
     │                          │    │  Manages:                │
     │  Can do:                 │    │  - Worktree lifecycle    │
     │  - Edit source files     │    │  - All git operations    │
     │                          │    │  - Push/fetch to GitHub  │
     │  Cannot do:              │    │                          │
     │  - See other worktrees   │    │                          │
     │  - Access .git metadata  │    │                          │
     └──────────────────────────┘    └──────────────────────────┘
                    │                              ▲
                    │           HTTP API           │
                    └──────────────────────────────┘
```

## How It Works

### Worktree Lifecycle (Gateway-Managed)

```
Container Request                    Gateway
       │                                │
       │  POST /api/v1/worktree/create  │
       │  {repo: "my-repo", id: "abc"}  │
       │───────────────────────────────►│
       │                                │
       │                    ┌───────────┴───────────┐
       │                    │ git worktree add      │
       │                    │   /workspace/worktrees│
       │                    │   /abc/my-repo        │
       │                    │   -b jib/abc/work     │
       │                    └───────────┬───────────┘
       │                                │
       │  {path: "/workspace/worktrees/ │
       │   abc/my-repo", branch: "..."}│
       │◄───────────────────────────────│
       │                                │
      ... container does work ...       │
       │                                │
       │  POST /api/v1/worktree/delete  │
       │  {id: "abc"}                   │
       │───────────────────────────────►│
       │                                │
       │                    ┌───────────┴───────────┐
       │                    │ git worktree remove   │
       │                    │   /workspace/worktrees│
       │                    │   /abc/my-repo        │
       │                    └───────────┬───────────┘
       │                                │
```

**Worktree creation is fast** because:
- No file copying - git just creates metadata + checks out files
- Objects are shared via hardlinks/reflinks when possible
- Branch creation is O(1)

### Container Setup
1. Request arrives, gateway creates worktree: `git worktree add /workspace/worktrees/{id}/repo -b jib/{id}/work`
2. Container mounts the working directory with `.git` as read-only:
   ```bash
   docker run \
     -v /workspace/worktrees/{id}/repo:/home/jib/repo:rw \
     -v /workspace/worktrees/{id}/repo/.git:/home/jib/repo/.git:ro \
     ...
   ```
3. Container can freely edit source files, but cannot modify `.git`
4. All git operations go through gateway API

### Why .git is Read-Only

The worktree's `.git` is a file (not directory) containing:
```
gitdir: /workspace/repos/my-repo.git/worktrees/wt-{id}
```

**Security considerations:**
- Container cannot modify `.git` to point elsewhere
- The gitdir path points to worktree admin, which isn't mounted in container anyway
- Even if container could read the path, it can't access it
- Git wrapper ignores local `.git` entirely - routes all commands to gateway

**Defense in depth:**
- Read-only `.git` mount prevents tampering
- Git wrapper doesn't use local git at all
- Worktree admin directory not accessible to container

### Git Operations

| Operation | Where it runs | How |
|-----------|---------------|-----|
| Edit files | Container | Direct filesystem access |
| `git status` | Gateway | `POST /api/v1/git/status` |
| `git diff` | Gateway | `POST /api/v1/git/diff` |
| `git add` | Gateway | `POST /api/v1/git/add` |
| `git commit` | Gateway | `POST /api/v1/git/commit` |
| `git log` | Gateway | `POST /api/v1/git/log` |
| `git push` | Gateway | `POST /api/v1/git/push` (existing) |
| `git fetch` | Gateway | `POST /api/v1/git/fetch` (existing) |
| `gh` commands | Gateway | `POST /api/v1/gh/*` (existing) |

### Git Wrapper in Container

The existing git wrapper is extended to route ALL operations:

```bash
#!/bin/bash
# /usr/bin/git wrapper in container

curl -s -X POST http://gateway:9847/api/v1/git \
  --json "{
    \"container_id\": \"$CONTAINER_ID\",
    \"args\": $(printf '%s\n' "$@" | jq -R . | jq -s .),
    \"cwd\": \"$(pwd)\"
  }"
```

### Gateway Git Execution

Gateway receives git commands and executes them with proper context:

```python
@app.route("/api/v1/git", methods=["POST"])
def git_operation():
    data = request.json
    container_id = data["container_id"]
    args = data["args"]

    # Map container path to gateway's view
    work_tree = f"/workspace/{container_id}/repo"
    git_dir = "/workspace/git-data/repo.git"

    # Execute with explicit paths
    result = subprocess.run(
        ["git", f"--work-tree={work_tree}", f"--git-dir={git_dir}"] + args,
        capture_output=True, text=True
    )

    return jsonify({
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    })
```

## Multi-Container Isolation

Each container gets its own git worktree, sharing the object store:

```
/workspace/
├── repos/
│   └── my-repo.git/
│       ├── objects/          # Shared across ALL worktrees
│       ├── refs/             # Shared refs
│       ├── HEAD              # Main repo HEAD
│       └── worktrees/        # Worktree admin directories
│           ├── wt-abc123/
│           │   ├── HEAD      # abc123's HEAD (jib/abc123/work)
│           │   ├── index     # abc123's staging area
│           │   └── gitdir    # Points to working dir
│           └── wt-def456/
│               ├── HEAD      # def456's HEAD (jib/def456/work)
│               ├── index     # def456's staging area
│               └── gitdir
│
└── worktrees/                # Working directories (what containers see)
    ├── abc123/
    │   └── my-repo/          # Container abc123 mounts THIS
    │       ├── src/
    │       └── .git          # File pointing to worktree admin
    └── def456/
        └── my-repo/          # Container def456 mounts THIS
            ├── src/
            └── .git
```

**Isolation guarantees:**
- Each worktree has its own HEAD, index (staging area), and working directory
- Containers can't see each other's uncommitted changes
- Containers can work on different branches simultaneously
- All containers share commit history and objects (efficient storage)
- Gateway manages worktree admin directories - containers never touch them

**Branch management:**
- Worktree creation automatically creates a branch: `jib/{id}/work`
- Gateway enforces one worktree per branch (git requirement)
- Merges happen through PRs (human review)

**Why this avoids PR #590's problems:**
- Container only mounts the working directory, not the worktree admin
- Gateway manages gitdir/commondir paths - they're never exposed to container
- No path rewriting needed - gateway controls all paths
- Host can run git operations on main repo while containers use worktrees

## Deployment: Local vs Cloud Run

The architecture is **identical** for both:

| Aspect | Local | Cloud Run |
|--------|-------|-----------|
| Shared volume | Docker bind mounts | emptyDir or GCS FUSE |
| Gateway communication | localhost / Docker network | localhost (sidecar) |
| Container startup | Clone once, reuse | Clone or restore checkpoint |
| Persistence | Host filesystem | GCS checkpoint (optional) |

### Local Deployment

```bash
# Start gateway
docker run -d --name gateway \
  -v ~/workspace:/workspace \
  jib-gateway

# Start jib container
docker run -it --name jib-abc123 \
  -v ~/workspace/abc123/repo:/home/jib/repo \
  -e CONTAINER_ID=abc123 \
  -e GATEWAY_URL=http://gateway:9847 \
  --network jib-network \
  jib
```

### Cloud Run Deployment

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
spec:
  template:
    spec:
      containers:
        - name: jib
          image: jib:latest
          volumeMounts:
            - name: workspace
              mountPath: /home/jib/repo
              subPath: "$(CONTAINER_ID)/repo"
        - name: gateway
          image: jib-gateway:latest
          volumeMounts:
            - name: workspace
              mountPath: /workspace
      volumes:
        - name: workspace
          emptyDir: {}
```

## Advantages Over Previous Approaches

| Issue | Worktree approach (PR #590) | Gateway-managed |
|-------|----------------------------|-----------------|
| Host git breaks | Yes (path rewriting) | No (host not affected) |
| Crash recovery | Cleanup script needed | Nothing to clean up |
| Multi-container | Complex worktree setup | Simple directory per container |
| Cloud deployment | Needs different architecture | Same architecture |
| Implementation | Complex entrypoint logic | Simple wrapper + gateway routes |

## Performance Considerations

**Concern**: Every git command goes over HTTP - is this slow?

**Analysis**:
- Local HTTP latency: ~0.1-1ms
- Typical `git status`: 10-100ms (I/O bound)
- Overhead: <10% for most operations

**Optimizations if needed**:
1. Batch operations: `POST /api/v1/git/batch` for multiple commands
2. Caching: Gateway caches status/diff for rapid re-queries
3. Streaming: Large outputs (log, diff) streamed back

**Benchmark** (to be validated):
| Operation | Direct git | Via gateway | Overhead |
|-----------|-----------|-------------|----------|
| git status | 50ms | 55ms | 10% |
| git diff | 30ms | 35ms | 17% |
| git commit | 100ms | 110ms | 10% |
| git log -10 | 20ms | 25ms | 25% |

## Implementation Plan

### Phase 1: Extend Gateway API (Week 1)
1. Add routes for: status, diff, add, commit, log, show, blame
2. Implement container-id to path mapping
3. Add request validation and error handling

### Phase 2: Update Git Wrapper (Week 1)
1. Modify container's git wrapper to route all commands
2. Handle streaming output for large responses
3. Add local caching for repeated reads

### Phase 3: Multi-Container Support (Week 2)
1. Implement per-container working directories
2. Add container registration/cleanup in gateway
3. Branch ownership enforcement

### Phase 4: Testing (Week 2)
1. Unit tests for all gateway git routes
2. Integration tests with multiple containers
3. Performance benchmarks

### Phase 5: Cloud Run Deployment (Week 3)
1. Create Cloud Run service configuration
2. Implement checkpoint/restore for persistence
3. End-to-end testing on Cloud Run

## Migration from Current Architecture

1. Deploy new gateway with extended git API
2. Update container git wrapper to use new API
3. Remove worktree path rewriting from entrypoint
4. Remove .git-admin, .git-common mount complexity
5. Simplify cleanup (just delete container directories)

---

# Option 2: Overlayfs Isolation (Local-only Alternative)

For local deployments where overlayfs is available and maximum git performance is required.

## Context

PR #590 implemented git worktree isolation to allow multiple jib containers to work on the same repository without affecting each other. The implementation modifies git metadata files (`gitdir`, `commondir`) in shared bind-mounted directories to use container-internal paths.

This approach has fundamental limitations discovered in PR #594:

1. **Host git operations break** while any container is running (paths like `/home/jib/...` don't exist on host)
2. **Crash recovery required** - if a container exits abnormally, host git operations remain broken until manual cleanup
3. **Gateway complexity** - the gateway sidecar needs additional mounts to access the rewritten paths

## Requirements

The git isolation solution must support:

1. **N containers simultaneously** - arbitrary number of jib containers on the same repos
2. **Container isolation** - modifications in one container don't affect others
3. **Host isolation** - container modifications don't affect host git operations
4. **Gateway access** - sidecar can perform git/gh operations for any container
5. **No cleanup required** - host should work correctly regardless of container state

## Problem Analysis

### Why Path Rewriting Fails

Git stores paths in metadata files that must resolve correctly for whoever reads them:

| File | Container writes | Host expects |
|------|-----------------|--------------|
| `gitdir` | `/home/jib/repos/{repo}` | `/home/user/khan/{repo}` |
| `commondir` | `/home/jib/.git-common/{repo}` | `/home/user/.git/{repo}` |

With different mount namespaces, the same absolute path cannot work for both host and container. The current approach of rewriting paths creates a mutually exclusive situation: either host works OR container works, not both.

### Alternatives Considered

| Approach | Why it doesn't work |
|----------|---------------------|
| Relative paths | Mount structures differ; relative paths resolve to different locations |
| Environment variables | `GIT_COMMON_DIR` exists but `gitdir` has no env var equivalent |
| Host-side symlinks | Requires root, path mapping per-repo, potential user conflicts |
| Cleanup scripts | Only helps after container exits; doesn't solve simultaneous access |

## Proposed Solution: Overlayfs Isolation

Use overlayfs to give each container a copy-on-write view of repositories and git data.

### Architecture

```
Host filesystem (always untouched):
├── ~/khan/{repo}/                    # Working directories
└── ~/.git/{repo}/                    # Git data (objects, refs, config, etc.)

Per-container overlay:
├── ~/.jib-overlays/{container-id}/
│   ├── upper/                        # Container's writes land here
│   │   ├── repos/{repo}/             # Modified working files
│   │   └── git/{repo}/               # Modified git metadata
│   └── work/                         # Overlayfs workdir (required)

Container mount structure:
└── /home/jib/
    ├── repos/{repo}                  # overlayfs: lower=host repo, upper=container-specific
    └── .git/{repo}                   # overlayfs: lower=host git, upper=container-specific
```

### How It Works

1. **Container startup**: Create overlayfs mounts combining host directories (lower/read-only) with container-specific upper directories
2. **Container reads**: Served from host filesystem (lower layer)
3. **Container writes**: Go to container's upper layer only
4. **Host operations**: Always see the original files (lower layer)
5. **Other containers**: Each has its own upper layer, isolated from others
6. **Container exit**: Discard upper layer (or optionally merge changes back)

### Gateway Access

The gateway sidecar needs to access container-created git objects for push operations. Options:

**Option A: Mount container overlays in gateway**
- Gateway mounts each active container's merged overlayfs view
- Can read new commits/refs directly
- Requires dynamic mount management as containers start/stop

**Option B: Shared objects staging area**
- Containers write new git objects to a shared staging directory
- Gateway reads from staging, pushes to remote
- Simpler mount structure, but requires object copying

**Option C: Container packages objects in push request**
- Container bundles new objects (e.g., via `git bundle`) when requesting push
- Gateway receives objects directly, no special mounts needed
- Higher latency for large pushes

**Recommendation**: Option A for simplicity and performance. Gateway can use a configuration file or API to discover active container overlays.

### Mount Configuration

Container startup would use mounts like:

```bash
# Create overlay directories
mkdir -p ~/.jib-overlays/${CONTAINER_ID}/{upper/repos,upper/git,work}

# For each repo:
mount -t overlay overlay \
  -o lowerdir=${HOME}/khan/${repo},upperdir=${OVERLAY}/upper/repos/${repo},workdir=${OVERLAY}/work/repos/${repo} \
  /home/jib/repos/${repo}

mount -t overlay overlay \
  -o lowerdir=${HOME}/.git/${repo},upperdir=${OVERLAY}/upper/git/${repo},workdir=${OVERLAY}/work/git/${repo} \
  /home/jib/.git/${repo}
```

Note: This requires either:
- Running container setup with privileges to create overlay mounts, OR
- Pre-creating overlays on host before container start (preferred for security)

### Container Exit Handling

| Scenario | Action |
|----------|--------|
| Clean exit, no changes to keep | Delete upper layer directory |
| Clean exit, want to persist changes | Merge upper layer to host (explicit command) |
| Crash/kill | Upper layer remains; can be inspected or deleted |
| Host cleanup | Simply `rm -rf ~/.jib-overlays/{container-id}` |

No git metadata corruption possible since host files are never modified.

## Comparison with Current Approach

| Aspect | Current (PR #590) | Overlayfs |
|--------|-------------------|-----------|
| Host git while container runs | Broken | Works |
| Multi-container isolation | Partial (worktrees) | Complete (separate overlays) |
| Crash recovery | Manual script needed | Delete directory |
| Implementation complexity | Medium | Higher (overlay setup) |
| Disk usage | Low (shared objects) | Medium (CoW, mostly shared) |
| Gateway access | Needs path translation | Mount merged view |
| Privilege requirements | None | Overlay mount (can be pre-created) |

## Implementation Plan

### Phase 1: Core Overlay Infrastructure
1. Create overlay mount helper script for host
2. Modify `jib` launcher to set up overlays before container start
3. Update container entrypoint to expect overlay mounts (remove path rewriting)
4. Test basic git operations in container

### Phase 2: Gateway Integration
1. Implement container overlay discovery in gateway
2. Mount active container overlays in gateway container
3. Update push/fetch to use overlay paths
4. Test multi-container scenarios

### Phase 3: Lifecycle Management
1. Implement overlay cleanup on container exit
2. Add optional "persist changes" command
3. Add host-side cleanup utility for orphaned overlays
4. Update documentation

## Migration

The overlayfs approach can coexist with the current worktree approach during transition:

1. New containers use overlayfs
2. Existing worktree-based sessions continue to work
3. Eventually deprecate worktree path rewriting

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Overlayfs not available | Check kernel support; fall back to current approach |
| Privilege escalation via overlay | Pre-create overlays on host with correct permissions |
| Disk space from many overlays | Implement aggressive cleanup; monitor usage |
| Performance overhead | CoW is generally fast; benchmark critical paths |

## Decision

Adopt overlayfs-based isolation to replace the path-rewriting approach from PR #590. This provides true isolation between containers and host while maintaining gateway access for remote operations.

---

# Appendix: Cloud Deployment (Cloud Run)

The overlayfs approach works for local/VM deployments where we control the host. Cloud Run (and similar serverless platforms) requires a different architecture due to fundamental constraints.

## Cloud Run Constraints

| Constraint | Impact |
|------------|--------|
| No overlayfs | Can't use kernel-level CoW isolation |
| Stateless containers | No persistent local disk; containers killed anytime |
| Restricted privileges | Can't mount filesystems, limited syscalls |
| Auto-scaling | Multiple instances may work on same repo |
| Cold starts | Need fast startup; can't clone large repos each time |
| Max request timeout | 60 min (configurable); long tasks may be interrupted |

## Architecture for Cloud Run

### Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cloud Run Service                         │
│  ┌─────────────────────┐      ┌─────────────────────────────┐   │
│  │    jib container    │      │    gateway sidecar          │   │
│  │                     │      │                             │   │
│  │  - Claude Code      │◄────►│  - Git push/fetch           │   │
│  │  - Local git ops    │ HTTP │  - GitHub API (gh)          │   │
│  │  - Work on /workspace      │  - Credential management    │   │
│  │                     │      │                             │   │
│  └─────────┬───────────┘      └──────────────┬──────────────┘   │
│            │                                  │                  │
│            ▼                                  ▼                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Shared Volume (in-memory or GCS FUSE)          ││
│  │                        /workspace                            ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     External Storage                             │
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │  Cloud Storage  │    │     GitHub      │    │Secret Manager│ │
│  │                 │    │                 │    │              │ │
│  │  - Git bundles  │    │  - Source of    │    │  - GitHub    │ │
│  │  - Checkpoints  │    │    truth        │    │    tokens    │ │
│  │  - Work state   │    │  - Push target  │    │  - API keys  │ │
│  └─────────────────┘    └─────────────────┘    └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Git State Management

Since Cloud Run lacks persistent local storage, git state must be externalized:

**Option A: Clone-on-demand (Simple but slow)**
```
Startup:
1. Clone repo from GitHub (shallow for speed)
2. Work in /workspace

Shutdown/Push:
1. Gateway pushes to GitHub
2. State lost on container termination
```

Pros: Simple, always fresh
Cons: Slow cold start, work lost if container dies before push

**Option B: Git Bundle Checkpointing (Recommended)**
```
Startup:
1. Check Cloud Storage for existing bundle for this session
2. If exists: download and unbundle
3. If not: shallow clone from GitHub
4. Create initial checkpoint

During work:
1. Periodic checkpoints: create bundle, upload to GCS
2. Checkpoint on every commit (or batch of commits)

Push:
1. Gateway creates bundle of unpushed commits
2. Pushes to GitHub
3. Updates checkpoint in GCS

Recovery (new instance for same session):
1. Download latest bundle from GCS
2. Unbundle and continue
```

Pros: Durable, fast recovery, handles container preemption
Cons: Checkpoint overhead, GCS costs

**Option C: Persistent Volume (If available)**
```
Cloud Run now supports:
- Cloud Storage FUSE (GCS mounted as filesystem)
- Filestore (NFS)

Mount persistent volume at /workspace:
1. Git repo lives on persistent storage
2. Multiple instances need locking (see Multi-Instance section)
```

Pros: Simpler mental model, persistent
Cons: GCS FUSE has performance limitations for git; Filestore is expensive

### Sidecar Communication

Cloud Run multi-container pods share:
- Network namespace (localhost works)
- Mounted volumes

```yaml
# cloud-run-service.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: jib-worker
spec:
  template:
    spec:
      containers:
        # Main jib container
        - name: jib
          image: gcr.io/project/jib:latest
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: workspace
              mountPath: /workspace
          env:
            - name: GATEWAY_URL
              value: "http://localhost:9847"

        # Gateway sidecar
        - name: gateway
          image: gcr.io/project/jib-gateway:latest
          ports:
            - containerPort: 9847
          volumeMounts:
            - name: workspace
              mountPath: /workspace
          env:
            - name: GITHUB_TOKEN
              valueFrom:
                secretKeyRef:
                  name: github-token
                  key: token

      volumes:
        - name: workspace
          emptyDir:
            medium: Memory  # Or use GCS FUSE
            sizeLimit: 2Gi
```

### Push/Fetch Flow

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│     jib     │         │   gateway   │         │   GitHub    │
└──────┬──────┘         └──────┬──────┘         └──────┬──────┘
       │                       │                       │
       │  POST /git/push       │                       │
       │  {repo_path, branch}  │                       │
       │──────────────────────►│                       │
       │                       │                       │
       │                       │  Read git objects     │
       │                       │  from /workspace      │
       │                       │◄─────────────────────►│
       │                       │                       │
       │                       │  git push (HTTPS)     │
       │                       │──────────────────────►│
       │                       │                       │
       │                       │  Create checkpoint    │
       │                       │  bundle, upload GCS   │
       │                       │─────────────┐         │
       │                       │             │         │
       │                       │◄────────────┘         │
       │                       │                       │
       │  {success, sha}       │                       │
       │◄──────────────────────│                       │
       │                       │                       │
```

### Multi-Instance Coordination

If auto-scaling creates multiple instances for the same session:

**Problem**: Two instances modifying same repo = corruption

**Solutions**:

1. **Session affinity**: Route all requests for a session to same instance
   ```yaml
   sessionAffinity: true  # Cloud Run supports this
   ```

2. **Distributed locking**: Use Cloud Storage or Firestore for locks
   ```
   Before git operation:
   1. Acquire lock: gs://jib-locks/{session-id}/{repo}
   2. Perform operation
   3. Release lock
   ```

3. **Single instance mode**: Set max instances to 1 for jib workers
   ```yaml
   autoscaling.knative.dev/maxScale: "1"
   ```

**Recommendation**: Start with single instance mode; add locking if scale needed.

### Secrets Management

```
┌─────────────────────────────────────────────┐
│              Secret Manager                  │
│                                             │
│  github-token     → Gateway env             │
│  anthropic-key    → jib container env       │
│  gateway-secret   → Shared for auth         │
└─────────────────────────────────────────────┘
```

Cloud Run natively integrates with Secret Manager:
```yaml
env:
  - name: GITHUB_TOKEN
    valueFrom:
      secretKeyRef:
        name: github-token
        key: latest
```

### Container Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    Cloud Run Instance Lifecycle                  │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  COLD    │───►│  INIT    │───►│  RUNNING │───►│ SHUTDOWN │  │
│  │  START   │    │          │    │          │    │          │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │              │                │               │         │
│       ▼              ▼                ▼               ▼         │
│  Check for      Download         Normal ops      Checkpoint     │
│  existing       bundle or        + periodic      + cleanup      │
│  session        clone repo       checkpoints                    │
│                                                                  │
│  PREEMPTION (can happen anytime):                               │
│  - Container killed without shutdown signal                      │
│  - Recovery: next instance loads from last checkpoint           │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation Changes for Cloud Run

| Component | Local/VM | Cloud Run |
|-----------|----------|-----------|
| Git storage | Overlayfs on host | GCS bundles + emptyDir |
| Gateway communication | Unix socket or localhost | localhost (shared network) |
| Secrets | Local files | Secret Manager |
| Persistence | Host filesystem | GCS checkpoints |
| Multi-container | Separate Docker containers | Sidecar in same pod |
| Startup | Mount overlays | Download/clone |
| Cleanup | Delete overlay dir | Delete GCS checkpoint |

### Cost Considerations

| Resource | Estimate |
|----------|----------|
| Cloud Run (CPU/memory) | ~$0.00002/vCPU-second |
| Cloud Storage | ~$0.02/GB/month + operations |
| Secret Manager | ~$0.03/10k access operations |
| Egress | ~$0.12/GB (after free tier) |

For a typical session (1 hour, 2 vCPU, 4GB RAM):
- Compute: ~$0.15
- Storage: negligible
- Total: ~$0.15-0.20/session

### Hybrid Architecture

For organizations with both local and cloud deployments:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Unified jib Architecture                     │
│                                                                  │
│  ┌─────────────────────────────┐  ┌───────────────────────────┐ │
│  │      Local Deployment       │  │    Cloud Run Deployment   │ │
│  │                             │  │                           │ │
│  │  - Overlayfs isolation      │  │  - GCS bundle isolation   │ │
│  │  - Host gateway sidecar     │  │  - Pod gateway sidecar    │ │
│  │  - Systemd lifecycle        │  │  - Knative lifecycle      │ │
│  │                             │  │                           │ │
│  └──────────────┬──────────────┘  └─────────────┬─────────────┘ │
│                 │                               │               │
│                 ▼                               ▼               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              Common Gateway API + Protocol                  ││
│  │                                                             ││
│  │  POST /api/v1/git/push                                      ││
│  │  POST /api/v1/git/fetch                                     ││
│  │  POST /api/v1/gh/*                                          ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

The gateway API remains the same; only the isolation mechanism differs.

## References

- PR #590: Original worktree isolation implementation
- PR #592: Fixes for #590 (logs mount, SSH URLs)
- PR #594: Documents path leakage issues
- [Overlayfs documentation](https://docs.kernel.org/filesystems/overlayfs.html)
