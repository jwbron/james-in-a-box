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

### Phase 0: Remove PR #590/#592 Path Rewriting

**Goal**: Undo the path rewriting approach and remove obsolete worktree management code.

#### 0.1 Remove Path Rewriting from Container Entrypoint

**File**: `jib-container/entrypoint.py`

Remove the `setup_worktrees()` function (lines 557-696) which:
- Rewrites `.git` files to point to `.git-admin/<repo>`
- Backs up and rewrites `gitdir` file from host path to container path
- Backs up and rewrites `commondir` file to `.git-common/<repo>/`
- Sets `core.worktree` in git config

Remove the `cleanup_on_exit()` restoration logic (lines 1048-1121) which:
- Restores `gitdir` and `commondir` from `.host-backup` files
- This cleanup is only needed because of path rewriting

**Simplify to**: Container sees repos mounted at `/home/jib/repos/<repo>` with `.git` as read-only file. No path manipulation needed.

#### 0.2 Remove Host Worktree Management

**Files to remove/simplify**:

1. **`jib-container/jib_lib/worktrees.py`** - Remove entirely
   - `create_worktrees()` - No longer needed; gateway manages worktrees
   - `cleanup_worktrees()` - No longer needed; gateway handles cleanup
   - File-based locking (`_acquire_git_lock`, `_release_git_lock`) - Gateway serializes operations

2. **`host-services/utilities/worktree-watcher/`** - Remove entirely
   - `worktree-watcher.py` - No longer needed; gateway cleans up orphaned worktrees
   - `worktree-watcher.service` - Remove systemd service
   - `worktree-watcher.timer` - Remove systemd timer

3. **`scripts/jib-cleanup-worktree`** - Remove
   - Manual restoration script no longer needed

#### 0.3 Simplify jib Launcher

**Files**:
- `jib-container/jib_lib/runtime.py` - Update `run_claude()` and `exec_in_new_container()`
- `jib-container/jib_lib/docker.py` - Update mount configuration

Remove calls to:
- `create_worktrees(container_id)` on startup
- `cleanup_worktrees(container_id)` on shutdown

Replace with:
- Request worktree creation from gateway API on startup
- Request worktree deletion from gateway API on shutdown

#### 0.4 Remove Mount Complexity

**Files**: Docker run configuration, compose files

Remove mounts for:
- `~/.git-admin/<repo>` → `/home/jib/.git-admin/<repo>`
- `~/.git-common/<repo>` → `/home/jib/.git-common/<repo>`
- `~/.jib-local-objects/<id>/<repo>` → local objects

Simplify to:
- Gateway creates worktree at `/workspace/worktrees/<id>/<repo>`
- Container mounts only the working directory with `.git` read-only

#### 0.5 Remove Object Sync from Gateway

**File**: `gateway-sidecar/gateway.py`

Remove `sync_objects_after_push()` function (lines 122-274):
- This was needed because containers had local object stores
- With gateway-managed worktrees, objects are in the shared repo

### Phase 1: Extend Gateway API for Write Operations

**Goal**: Gateway handles all git write operations; container runs reads locally.

#### 1.1 Add Git Write Operation Endpoints

**File**: `gateway-sidecar/gateway.py`

Add new endpoints:

```python
POST /api/v1/git/add
    Request: {"repo_path": "...", "files": ["file1", "file2"] or ["."] for all}
    Response: {"success": true, "stdout": "...", "stderr": "..."}

POST /api/v1/git/commit
    Request: {"repo_path": "...", "message": "...", "author": "name <email>"}
    Response: {"success": true, "commit_sha": "abc123", "stdout": "..."}

POST /api/v1/git/checkout
    Request: {"repo_path": "...", "target": "branch-or-ref", "create": false}
    Response: {"success": true}

POST /api/v1/git/reset
    Request: {"repo_path": "...", "mode": "soft|mixed|hard", "target": "ref"}
    Policy: Block --hard unless explicitly confirmed
    Response: {"success": true}

POST /api/v1/git/stash
    Request: {"repo_path": "...", "action": "push|pop|list|drop", "message": "..."}
    Response: {"success": true, "stash_ref": "stash@{0}"}

POST /api/v1/git/branch
    Request: {"repo_path": "...", "action": "create|delete|rename", "name": "..."}
    Policy: Only jib-prefixed branches can be created/deleted
    Response: {"success": true}

POST /api/v1/git/merge
    Request: {"repo_path": "...", "branch": "...", "no_ff": false}
    Response: {"success": true, "merge_commit": "..."}

POST /api/v1/git/rebase
    Request: {"repo_path": "...", "onto": "...", "interactive": false}
    Policy: Block interactive rebase (requires TTY)
    Response: {"success": true}

POST /api/v1/git/cherry-pick
    Request: {"repo_path": "...", "commits": ["sha1", "sha2"]}
    Response: {"success": true}

POST /api/v1/git/revert
    Request: {"repo_path": "...", "commits": ["sha1"]}
    Response: {"success": true}

POST /api/v1/git/tag
    Request: {"repo_path": "...", "action": "create|delete", "name": "...", "message": "..."}
    Policy: Only jib-prefixed tags or with explicit permission
    Response: {"success": true}

POST /api/v1/git/clean
    Request: {"repo_path": "...", "force": true, "directories": true}
    Policy: Require confirmation for destructive operations
    Response: {"success": true, "removed_files": [...]}

POST /api/v1/git/config
    Request: {"repo_path": "...", "key": "...", "value": "...", "scope": "local"}
    Policy: Block certain config keys (credential.*, core.hooksPath)
    Response: {"success": true}
```

#### 1.2 Add Worktree Lifecycle Endpoints

**File**: `gateway-sidecar/gateway.py`

```python
POST /api/v1/worktree/create
    Request: {"repo": "repo-name", "container_id": "jib-xxx", "base_branch": "main"}
    Actions:
      1. git worktree add /workspace/worktrees/<id>/<repo> -b jib/<id>/work <base>
      2. Return worktree path for container to mount
    Response: {"success": true, "worktree_path": "/workspace/worktrees/..."}

DELETE /api/v1/worktree/<container_id>/<repo>
    Actions:
      1. git worktree remove /workspace/worktrees/<id>/<repo>
      2. Delete working directory
      3. Optionally delete branch if no unmerged commits
    Response: {"success": true}

GET /api/v1/worktree/list
    Response: {"worktrees": [{"container_id": "...", "repo": "...", "branch": "..."}]}
```

#### 1.3 Implement Path Mapping in Gateway

**File**: `gateway-sidecar/git_client.py`

Add worktree path resolution:

```python
import re

def validate_identifier(value: str, name: str) -> None:
    """Ensure identifier contains only safe characters.

    Prevents path traversal attacks via container_id or repo_name containing '../'.
    """
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$', value):
        raise ValueError(f"Invalid {name}: must be alphanumeric with ._- allowed")
    if '..' in value:
        raise ValueError(f"Invalid {name}: path traversal not allowed")

def resolve_worktree_paths(container_id: str, repo_name: str) -> tuple[str, str]:
    """Map container ID to worktree paths.

    Returns:
        (work_tree_path, git_dir_path) for use with git --work-tree and --git-dir

    Raises:
        ValueError: If container_id or repo_name contain unsafe characters
    """
    # Validate inputs to prevent path traversal
    validate_identifier(container_id, "container_id")
    validate_identifier(repo_name, "repo_name")

    work_tree = f"/workspace/worktrees/{container_id}/{repo_name}"
    git_dir = f"/workspace/repos/{repo_name}.git/worktrees/wt-{container_id}"
    return work_tree, git_dir
```

#### 1.4 Extend Allowlist Validation

**File**: `gateway-sidecar/git_client.py`

The gateway uses **explicit allowlists** for all git operations. Unknown flags are rejected by default—this is critical for security. Extend the existing `GIT_ALLOWED_COMMANDS` dictionary:

```python
# Existing global blocklist (already in git_client.py)
BLOCKED_GIT_FLAGS = [
    "--upload-pack",   # Can specify arbitrary command
    "--exec",          # Can specify arbitrary command
    "-c",              # Config override (could disable security)
    "--config",        # Config override
    "--receive-pack",  # Arbitrary command execution
]

# Extend the per-operation allowlist (add to existing GIT_ALLOWED_COMMANDS)
GIT_ALLOWED_COMMANDS = {
    # ... existing fetch, ls-remote, push entries ...

    "add": {
        "allowed_flags": [
            "--all", "-A",
            "--update", "-u",
            "--intent-to-add", "-N",
            "--force", "-f",
            "--verbose", "-v",
            "--dry-run", "-n",
            "--ignore-errors",
            "--",  # Separator for paths
        ],
    },
    "commit": {
        "allowed_flags": [
            "--message", "-m",
            "--amend",
            "--no-edit",
            "--allow-empty",
            "--allow-empty-message",
            "--author",
            "--date",
            "--signoff", "-s",
            "--no-verify", "-n",
            "--verbose", "-v",
            "--quiet", "-q",
        ],
    },
    "checkout": {
        "allowed_flags": [
            "--branch", "-b",
            "--force", "-f",
            "--track", "-t",
            "--no-track",
            "--quiet", "-q",
            "--",
        ],
    },
    "reset": {
        "allowed_flags": [
            "--soft",
            "--mixed",
            "--hard",      # Allowed but requires confirmation (see below)
            "--keep",
            "--quiet", "-q",
            "--",
        ],
        "requires_confirmation": ["--hard"],  # Extra validation
    },
    "stash": {
        "allowed_flags": [
            "push", "pop", "list", "show", "drop", "apply", "clear",
            "--message", "-m",
            "--keep-index", "-k",
            "--include-untracked", "-u",
            "--all", "-a",
            "--quiet", "-q",
            "--index",
        ],
    },
    "merge": {
        "allowed_flags": [
            "--no-ff",
            "--ff-only",
            "--squash",
            "--no-commit",
            "--message", "-m",
            "--verbose", "-v",
            "--quiet", "-q",
            "--abort",
            "--continue",
        ],
    },
    "rebase": {
        "allowed_flags": [
            "--onto",
            "--continue",
            "--abort",
            "--skip",
            "--quiet", "-q",
            "--verbose", "-v",
            # NOTE: -i/--interactive intentionally NOT allowed (requires TTY)
        ],
    },
    "cherry-pick": {
        "allowed_flags": [
            "--no-commit", "-n",
            "--mainline", "-m",
            "--continue",
            "--abort",
            "--skip",
            "--quiet",
        ],
    },
    "revert": {
        "allowed_flags": [
            "--no-commit", "-n",
            "--mainline", "-m",
            "--continue",
            "--abort",
            "--skip",
        ],
    },
    "branch": {
        "allowed_flags": [
            "--delete", "-d",
            "--force", "-D",  # -D = -d --force
            "--move", "-m",
            "--copy", "-c",
            "--list", "-l",
            "--verbose", "-v",
            "--quiet", "-q",
            "--track", "-t",
            "--no-track",
            "--set-upstream-to", "-u",
        ],
    },
    "tag": {
        "allowed_flags": [
            "--annotate", "-a",
            "--sign", "-s",
            "--message", "-m",
            "--force", "-f",
            "--delete", "-d",
            "--list", "-l",
            "--verify", "-v",
        ],
    },
    "clean": {
        "allowed_flags": [
            "--force", "-f",
            "--dry-run", "-n",
            "-d",  # Remove directories
            "-x",  # Remove ignored files too
            "--quiet", "-q",
        ],
        "requires_confirmation": ["-f", "--force", "-x"],  # Destructive
    },
    "config": {
        "allowed_flags": [
            "--local",
            "--get",
            "--get-all",
            "--list", "-l",
            "--unset",
            # NOTE: --global, --system intentionally NOT allowed
        ],
        "blocked_keys": [
            "credential.*",      # Don't let container modify credentials
            "core.hooksPath",    # Don't let container redirect hooks
            "core.gitProxy",     # Don't let container set proxies
            "http.proxy",
            "https.proxy",
        ],
    },
}
```

**Security properties maintained:**

1. **Unknown flags rejected by default** - `validate_git_args()` returns error for unlisted flags
2. **Global blocklist still applies** - `--upload-pack`, `--exec`, `-c` always blocked
3. **Per-operation allowlists** - Each operation has explicit list of permitted flags
4. **Confirmation for destructive ops** - `reset --hard`, `clean -f` require explicit confirmation
5. **Config key restrictions** - Block modification of credential and security-related config

### Phase 2: Update Git Wrapper

**Goal**: Container's git wrapper routes writes to gateway, runs reads locally.

#### 2.1 Modify Git Wrapper Script

**File**: `jib-container/scripts/git`

Replace current implementation with:

```bash
#!/bin/bash
# Git wrapper - routes write operations through gateway, reads run locally

REAL_GIT=/opt/.jib-internal/git
GATEWAY_URL="${GATEWAY_URL:-http://jib-gateway:9847}"

# Parse command
cmd=""
for arg in "$@"; do
    case "$arg" in
        -*) continue ;;
        *)
            cmd="$arg"
            break
            ;;
    esac
done

# Read-only operations run locally (fast path)
case "$cmd" in
    status|diff|log|show|blame|rev-parse|rev-list|\
    ls-files|ls-tree|cat-file|describe|shortlog|grep|bisect|reflog|\
    for-each-ref|name-rev|merge-base|symbolic-ref)
        exec "$REAL_GIT" "$@"
        ;;
esac

# Commands that need subcommand/flag awareness
case "$cmd" in
    branch)
        # git branch -d/-D/-m/-M/-c/-C are write operations
        case "$*" in
            *-d*|*-D*|*-m*|*-M*|*-c*|*-C*|*--delete*|*--move*|*--copy*|*--edit-description*)
                route_to_gateway "branch" "$@"
                ;;
            *)
                exec "$REAL_GIT" "$@"  # Read-only: list, show current
                ;;
        esac
        ;;
    tag)
        # git tag -d is a write operation; git tag (list) is read-only
        case "$*" in
            *-d*|*--delete*)
                route_to_gateway "tag" "$@"
                ;;
            *)
                # Creating tags also needs gateway (when args present beyond flags)
                if echo "$*" | grep -qE '^tag\s+(-[alnsf]|--)*\s*[^-]'; then
                    route_to_gateway "tag" "$@"
                else
                    exec "$REAL_GIT" "$@"  # Read-only: list tags
                fi
                ;;
        esac
        ;;
    stash)
        # git stash list/show are read-only
        subcmd="${2:-push}"  # Default stash action is push
        case "$subcmd" in
            list|show)
                exec "$REAL_GIT" "$@"
                ;;
            *)
                route_to_gateway "stash" "$@"
                ;;
        esac
        ;;
    remote)
        # Check subcommand
        subcmd=$(get_remote_subcommand "$@")
        case "$subcmd" in
            add|remove|rm|rename|set-url|set-head|set-branches|prune)
                echo "ERROR: Remote modification blocked" >&2
                exit 1
                ;;
            *)
                exec "$REAL_GIT" "$@"
                ;;
        esac
        ;;
esac

# Write operations go through gateway
case "$cmd" in
    add|commit|checkout|reset|merge|rebase|cherry-pick|revert|\
    clean|config|rm|mv|restore|switch)
        route_to_gateway "$cmd" "$@"
        ;;
    push|fetch|pull|ls-remote)
        # Already handled by existing gateway routing
        # (keep existing implementation)
        ;;
    *)
        # Unknown command - allow through but log for visibility
        logger -t jib-git "Unknown git command passed through: $cmd" 2>/dev/null || true
        exec "$REAL_GIT" "$@"
        ;;
esac
```

#### 2.2 Add Gateway Routing Function

**File**: `jib-container/scripts/git`

```bash
route_to_gateway() {
    local operation="$1"
    shift

    local repo_path
    repo_path=$(translate_path_for_gateway "$(pwd)")

    local secret
    secret=$(get_gateway_secret)
    if [ -z "$secret" ]; then
        echo "ERROR: Gateway secret not available" >&2
        return 1
    fi

    # Build args array as JSON
    local args_json
    args_json=$(printf '%s\n' "$@" | python3 -c "
import sys, json
args = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(args))
")

    local payload
    payload=$(python3 -c "
import json
print(json.dumps({
    'repo_path': '$repo_path',
    'operation': '$operation',
    'args': $args_json,
    'cwd': '$(pwd)'
}))
")

    # Call gateway with timeout and error handling
    local response
    local curl_exit_code
    response=$(curl -s --connect-timeout 5 --max-time 60 -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $secret" \
        -d "$payload" \
        "${GATEWAY_URL}/api/v1/git/${operation}" 2>&1)
    curl_exit_code=$?

    # Handle network failures
    if [ $curl_exit_code -ne 0 ]; then
        echo "ERROR: Gateway unavailable at ${GATEWAY_URL} (curl exit code: $curl_exit_code)" >&2
        echo "Ensure the gateway sidecar is running: curl ${GATEWAY_URL}/api/v1/health" >&2
        return 1
    fi

    # Handle empty response
    if [ -z "$response" ]; then
        echo "ERROR: Empty response from gateway" >&2
        return 1
    fi

    # Parse and display response
    local success
    success=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('success',False))" 2>/dev/null)

    if [ "$success" = "True" ]; then
        echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('stdout',''))" 2>/dev/null
        echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('stderr',''))" >&2 2>/dev/null
        return 0
    else
        local message
        message=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('message','Unknown error'))" 2>/dev/null)
        if [ -z "$message" ]; then
            echo "ERROR: Invalid response from gateway: $response" >&2
        else
            echo "ERROR: $message" >&2
        fi
        return 1
    fi
}
```

### Phase 3: Gateway-Managed Worktree Lifecycle

**Goal**: Gateway creates/manages worktrees; containers only mount working directories.

#### 3.1 Worktree Manager Module

**New file**: `gateway-sidecar/worktree_manager.py`

```python
"""Manages git worktrees for container isolation."""

import os
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

WORKSPACE_ROOT = Path("/workspace")
REPOS_DIR = WORKSPACE_ROOT / "repos"
WORKTREES_DIR = WORKSPACE_ROOT / "worktrees"


@dataclass
class WorktreeInfo:
    container_id: str
    repo_name: str
    branch: str
    worktree_path: Path
    git_dir: Path


class WorktreeManager:
    def __init__(self):
        WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
        self._active_worktrees: dict[str, list[WorktreeInfo]] = {}

    def create_worktree(
        self,
        repo_name: str,
        container_id: str,
        base_branch: str = "main"
    ) -> WorktreeInfo:
        """Create an isolated worktree for a container."""
        # Validate inputs to prevent path traversal
        validate_identifier(container_id, "container_id")
        validate_identifier(repo_name, "repo_name")

        repo_git = REPOS_DIR / f"{repo_name}.git"
        if not repo_git.exists():
            raise ValueError(f"Repository not found: {repo_name}")

        worktree_path = WORKTREES_DIR / container_id / repo_name
        branch_name = f"jib/{container_id}/work"

        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if branch already exists (from crashed session)
        branch_exists = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=repo_git,
            capture_output=True,
        ).returncode == 0

        if branch_exists:
            # Use existing branch instead of creating new one
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), branch_name],
                cwd=repo_git,
                capture_output=True,
                text=True,
            )
        else:
            # Create new branch from base
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "-b", branch_name, base_branch],
                cwd=repo_git,
                capture_output=True,
                text=True,
            )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        info = WorktreeInfo(
            container_id=container_id,
            repo_name=repo_name,
            branch=branch_name,
            worktree_path=worktree_path,
            git_dir=repo_git / "worktrees" / f"wt-{container_id}",
        )

        if container_id not in self._active_worktrees:
            self._active_worktrees[container_id] = []
        self._active_worktrees[container_id].append(info)

        return info

    def remove_worktree(
        self,
        container_id: str,
        repo_name: str,
        force: bool = False
    ) -> dict:
        """Remove a container's worktree.

        Args:
            container_id: Container identifier
            repo_name: Repository name
            force: If True, remove even with uncommitted changes

        Returns:
            dict with 'success', 'uncommitted_changes', 'warning' keys
        """
        worktree_path = WORKTREES_DIR / container_id / repo_name
        repo_git = REPOS_DIR / f"{repo_name}.git"
        result = {"success": False, "uncommitted_changes": False, "warning": None}

        if not worktree_path.exists():
            result["success"] = True
            return result

        # Check for uncommitted changes
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        has_changes = bool(status.stdout.strip())

        if has_changes and not force:
            result["uncommitted_changes"] = True
            result["warning"] = (
                f"Worktree has uncommitted changes. "
                f"Use force=True to remove anyway, or commit/stash changes first."
            )
            # Leave worktree intact - user must explicitly force or handle changes
            return result

        if has_changes:
            # Log warning but proceed with removal
            logger.warning(
                "Removing worktree with uncommitted changes",
                container_id=container_id,
                repo=repo_name,
            )
            result["warning"] = "Worktree removed with uncommitted changes"

        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path), "--force"],
            cwd=repo_git,
            capture_output=True,
        )

        # Clean up container directory if empty
        container_dir = WORKTREES_DIR / container_id
        if container_dir.exists() and not any(container_dir.iterdir()):
            container_dir.rmdir()

        result["success"] = True
        return result

    def cleanup_orphaned_worktrees(self, active_containers: set[str]) -> int:
        """Remove worktrees for containers that no longer exist."""
        removed = 0
        for container_dir in WORKTREES_DIR.glob("jib-*"):
            if not container_dir.is_dir():
                continue
            container_id = container_dir.name
            if container_id not in active_containers:
                for worktree in container_dir.iterdir():
                    if worktree.is_dir():
                        self.remove_worktree(container_id, worktree.name)
                        removed += 1
                shutil.rmtree(container_dir, ignore_errors=True)
        return removed
```

#### 3.2 Integrate Cleanup on Gateway Startup

**File**: `gateway-sidecar/gateway.py`

```python
def startup_cleanup():
    """Clean up orphaned worktrees on gateway startup."""
    from worktree_manager import WorktreeManager

    manager = WorktreeManager()

    # Get active containers from Docker
    result = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    active_containers = set(result.stdout.strip().split("\n")) - {""}

    removed = manager.cleanup_orphaned_worktrees(active_containers)
    if removed > 0:
        logger.info(f"Cleaned up {removed} orphaned worktree(s)")

# Call on startup
startup_cleanup()
```

#### 3.3 Update jib Launcher Integration

**Files** (new code to add):
- `jib-container/jib_lib/runtime.py` - Add gateway worktree API calls
- `jib-container/jib_lib/docker.py` - Update mount configuration for worktree paths

On container start:
```python
# Request worktree creation from gateway
response = requests.post(f"{gateway_url}/api/v1/worktree/create", json={
    "repo": repo_name,
    "container_id": container_id,
    "base_branch": "main"
})
worktree_path = response.json()["worktree_path"]

# Mount worktree into container
docker_args.extend([
    "-v", f"{worktree_path}:/home/jib/repos/{repo_name}:rw",
    "-v", f"{worktree_path}/.git:/home/jib/repos/{repo_name}/.git:ro",
])
```

On container stop:
```python
# Request worktree cleanup from gateway
requests.delete(f"{gateway_url}/api/v1/worktree/{container_id}/{repo_name}")
```

### Phase 4: Testing

**Goal**: Comprehensive testing of the new architecture.

#### 4.1 Unit Tests for Gateway Git Operations

**New file**: `gateway-sidecar/tests/test_git_operations.py`

```python
def test_git_add_single_file():
    """Test adding a single file via gateway."""

def test_git_add_all():
    """Test adding all files via gateway."""

def test_git_commit_with_message():
    """Test creating a commit."""

def test_git_commit_author_attribution():
    """Verify commits are attributed to jib."""

def test_git_checkout_branch():
    """Test switching branches."""

def test_git_checkout_create_branch():
    """Test creating and switching to new branch."""

def test_git_reset_soft():
    """Test soft reset."""

def test_git_reset_hard_blocked():
    """Verify hard reset requires confirmation."""

def test_git_stash_push_pop():
    """Test stash operations."""
```

#### 4.2 Unit Tests for Worktree Manager

**New file**: `gateway-sidecar/tests/test_worktree_manager.py`

```python
def test_create_worktree():
    """Test worktree creation."""

def test_create_worktree_idempotent():
    """Creating same worktree twice should fail gracefully."""

def test_remove_worktree():
    """Test worktree removal."""

def test_cleanup_orphaned_worktrees():
    """Test orphaned worktree cleanup."""

def test_worktree_isolation():
    """Verify changes in one worktree don't affect others."""
```

#### 4.3 Integration Tests

**New file**: `gateway-sidecar/tests/test_integration.py`

```python
def test_container_git_workflow():
    """Test complete workflow: clone, edit, add, commit, push."""

def test_multi_container_isolation():
    """Test two containers working on same repo don't interfere."""

def test_container_crash_recovery():
    """Test worktree cleanup after container crash."""

def test_read_operations_local():
    """Verify status/diff/log run locally (check latency)."""

def test_write_operations_gateway():
    """Verify add/commit route through gateway."""
```

#### 4.4 Performance Benchmarks

**New file**: `gateway-sidecar/tests/test_performance.py`

```python
def benchmark_git_status_local():
    """Benchmark local git status latency."""

def benchmark_git_commit_gateway():
    """Benchmark commit via gateway."""

def benchmark_worktree_creation():
    """Benchmark worktree creation time (target: <100ms)."""

def compare_local_vs_gateway():
    """Compare latency of local vs gateway operations."""
```

### Migration Checklist

1. **Preparation**
   - [ ] Ensure all active containers are stopped
   - [ ] Back up any work on jib-temp-* branches
   - [ ] Stop worktree-watcher systemd timer

2. **Phase 0: Remove old code**
   - [ ] Remove `setup_worktrees()` from entrypoint.py
   - [ ] Remove `cleanup_on_exit()` restoration logic
   - [ ] Remove `jib_lib/worktrees.py`
   - [ ] Remove `host-services/utilities/worktree-watcher/`
   - [ ] Remove `scripts/jib-cleanup-worktree`
   - [ ] Remove `sync_objects_after_push()` from gateway.py
   - [ ] Update docker mounts to remove .git-admin, .git-common

3. **Phase 1: Deploy gateway updates**
   - [ ] Add new git operation endpoints
   - [ ] Add worktree lifecycle endpoints
   - [ ] Add path mapping logic
   - [ ] Deploy and test gateway

4. **Phase 2: Update container**
   - [ ] Update git wrapper script
   - [ ] Rebuild container image
   - [ ] Test read operations run locally
   - [ ] Test write operations route to gateway

5. **Phase 3: Enable worktree management**
   - [ ] Update jib launcher to use gateway worktree API
   - [ ] Test worktree creation/deletion
   - [ ] Test orphaned worktree cleanup

6. **Phase 4: Validation**
   - [ ] Run all unit tests
   - [ ] Run integration tests
   - [ ] Run performance benchmarks
   - [ ] Test multi-container scenarios

---

## Design Decisions

### Uncommitted Changes on Container Exit

When a container exits, the worktree may contain uncommitted changes. The gateway handles this as follows:

1. **Normal exit**: Gateway checks for uncommitted changes before removing worktree
   - If changes exist, worktree is preserved and warning is logged
   - User can reconnect or manually handle the changes
   - Use `force=True` in delete API to remove anyway

2. **Crash/force exit**: Orphaned worktrees are cleaned up on next gateway startup
   - Uncommitted changes are logged as warnings before removal
   - Branch remains (commits are preserved), only working directory is removed

3. **Explicit cleanup**: User can call `DELETE /api/v1/worktree/{id}/{repo}?force=true`

**Rationale**: Preserving uncommitted work by default prevents data loss. Orphaned cleanup uses force because there's no user session to prompt.

### Multi-Repository Scenarios

When a container works with multiple repositories, the gateway determines the target repo from the `repo_path` in the request:

1. **Git wrapper** derives `repo_path` from `pwd` (current working directory)
2. **Gateway** extracts repo name from the path: `/home/jib/repos/{repo_name}/...`
3. **Path mapping** resolves to the correct worktree: `/workspace/worktrees/{container_id}/{repo_name}`

Each repository has its own worktree, and commands are always executed in the context of the repo containing the current directory. The git wrapper automatically handles this—no special configuration needed for multi-repo containers.

### Large File Handling

For repositories with large files (or Git LFS):

1. **`git add` of large files**: The gateway receives the file paths, not the file contents. Git reads files directly from the worktree filesystem (shared between container and gateway via volume mount).

2. **No HTTP transfer of file contents**: Files are never sent over HTTP. The gateway executes `git add` which reads from the shared filesystem.

3. **LFS support**: Git LFS operations that require network access (push/pull of LFS objects) go through the gateway for authentication, same as regular push/fetch.

**Performance implication**: Large file `git add` has the same performance as local git—the gateway just orchestrates the command.

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
