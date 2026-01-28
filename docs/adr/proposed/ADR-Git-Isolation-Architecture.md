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
   **Note on mount order**: Docker processes `-v` flags left-to-right. The parent directory must be mounted first, then the more specific `.git` mount overlays it. This order ensures `.git` ends up read-only within the read-write parent.
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
- Git wrapper routes write operations to gateway; read-only operations use local `.git`

**Defense in depth:**
- Read-only `.git` mount prevents tampering
- Git wrapper routes write operations through gateway
- Worktree admin directory not accessible to container

### Git Operations

| Operation | Where it runs | How |
|-----------|---------------|-----|
| Edit files | Container | Direct filesystem access |
| `git status` | Container (local) | Read-only, low latency |
| `git diff` | Container (local) | Read-only, low latency |
| `git log` | Container (local) | Read-only, low latency |
| `git add` | Gateway | `POST /api/v1/git/add` |
| `git commit` | Gateway | `POST /api/v1/git/commit` |
| `git push` | Gateway | `POST /api/v1/git/push` (existing) |
| `git fetch` | Gateway | `POST /api/v1/git/fetch` (existing) |
| `gh` commands | Gateway | `POST /api/v1/gh/*` (existing) |

**Local read-only optimization**: High-frequency operations (`status`, `diff`, `log`) run locally in the container for lower latency. The container has read-only access to `.git`, which is sufficient for these operations. Only write operations (`add`, `commit`, `push`) are routed through the gateway.

### Git Wrapper in Container

The git wrapper routes write operations through the gateway while allowing read-only operations locally:

```bash
#!/bin/bash
# /usr/bin/git wrapper in container

# Read-only operations run locally for low latency
case "$1" in
  status|diff|log|show|blame|branch|tag)
    exec /usr/bin/git.real "$@"
    ;;
esac

# Write operations go through gateway
curl -s -X POST http://gateway:9847/api/v1/git \
  --json "{
    \"container_id\": \"$CONTAINER_ID\",
    \"args\": $(printf '%s\n' "$@" | jq -R . | jq -s .),
    \"cwd\": \"$(pwd)\"
  }"
```

### Gateway Git Execution

Gateway receives git commands and executes them in the correct worktree context:

```python
@app.route("/api/v1/git", methods=["POST"])
def git_operation():
    data = request.json
    container_id = data["container_id"]
    args = data["args"]
    repo_name = data.get("repo", "my-repo")

    # Map container ID to worktree paths
    # Container's working dir: /workspace/worktrees/{id}/{repo}/
    # Worktree's git admin:    /workspace/repos/{repo}.git/worktrees/wt-{id}/
    work_tree = f"/workspace/worktrees/{container_id}/{repo_name}"
    git_dir = f"/workspace/repos/{repo_name}.git/worktrees/wt-{container_id}"

    # Verify worktree exists (security check)
    if not os.path.isdir(git_dir):
        return jsonify({"error": f"No worktree for container {container_id}"}), 404

    # Execute git command in worktree context
    result = subprocess.run(
        ["git", f"--work-tree={work_tree}", f"--git-dir={git_dir}"] + args,
        capture_output=True,
        text=True,
        cwd=work_tree
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
| Crash recovery | Cleanup script needed | Periodic worktree cleanup |
| Multi-container | Complex worktree setup | Simple directory per container |
| Cloud deployment | Needs different architecture | Same architecture |
| Implementation | Complex entrypoint logic | Simple wrapper + gateway routes |

## Gateway Crash Recovery

If the gateway crashes or restarts, orphaned worktrees may accumulate. The gateway implements cleanup on startup:

```python
def cleanup_orphaned_worktrees():
    """Remove worktrees for containers that no longer exist."""
    worktrees = list_worktrees()  # git worktree list
    active_containers = get_active_containers()  # From container runtime

    for wt in worktrees:
        container_id = extract_container_id(wt.path)
        if container_id and container_id not in active_containers:
            git_worktree_remove(wt.path, force=True)
            shutil.rmtree(wt.path, ignore_errors=True)
```

This runs:
- On gateway startup
- Periodically (e.g., every hour)
- When container count drops (scale-down event)

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

**Estimated benchmarks** (to be validated with actual measurements):
| Operation | Direct git | Via gateway | Overhead | Notes |
|-----------|-----------|-------------|----------|-------|
| git status | 50ms | 50ms | 0% | Runs locally |
| git diff | 30ms | 30ms | 0% | Runs locally |
| git log -10 | 20ms | 20ms | 0% | Runs locally |
| git commit | 100ms | 110ms | ~10% | Via gateway |
| git add | 40ms | 45ms | ~12% | Via gateway |

## Implementation Plan

### Phase 1: Extend Gateway API
1. Add routes for: add, commit, checkout, reset, stash
2. Implement container-id to worktree path mapping
3. Add request validation and error handling

### Phase 2: Update Git Wrapper
1. Modify container's git wrapper to route write operations to gateway
2. Allow read-only operations (status, diff, log) to run locally
3. Handle streaming output for large responses

### Phase 3: Multi-Container Support
1. Implement per-container working directories via worktrees
2. Add container registration/cleanup in gateway
3. Branch ownership enforcement
4. Orphaned worktree cleanup on gateway startup

### Phase 4: Testing
1. Unit tests for all gateway git routes
2. Integration tests with multiple containers
3. Performance benchmarks comparing local vs gateway operations

### Phase 5: Cloud Run Deployment
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

# Appendix A: Alternatives Considered

## Overlayfs Isolation (Rejected)

**Concept**: Use overlayfs to give each container a copy-on-write view of repositories. Host sees base layer, container sees modifications in upper layer.

**Why rejected**:
- Doesn't work on Cloud Run (no overlayfs support)
- Requires different architecture per environment
- Needs privileged container setup or pre-created overlays on host
- More complex gateway integration (dynamic overlay mounts)

**When it might be useful**: Local-only deployments requiring maximum git performance where the gateway HTTP overhead is unacceptable. Could be implemented as an optional optimization.

## Git Bundle Checkpointing (Rejected)

**Concept**: Store git state as bundles in Cloud Storage, download/restore on container start.

**Why rejected**:
- Different architecture from local deployment
- Adds latency on startup and during checkpoints
- Complex state synchronization

## Path Rewriting (PR #590) (Rejected)

**Concept**: Rewrite git metadata paths (`gitdir`, `commondir`) to container-internal paths.

**Why rejected**:
- Host git operations break while containers run
- Crash recovery requires cleanup scripts
- Path conflicts are inherent—container and host paths cannot both be valid

---

# Appendix B: Cloud Deployment (Cloud Run)

Gateway-managed worktrees work on Cloud Run with the same architecture. The only difference is the volume backend.

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
