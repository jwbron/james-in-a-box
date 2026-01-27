# ADR: Container Worktree Isolation

**Driver:** jib (autonomous agent)
**Approver:** James Wiesebron
**Contributors:** jib
**Informed:** Engineering teams
**Proposed:** January 2026
**Status:** Proposed

## Table of Contents

- [Context](#context)
- [Problem Statement](#problem-statement)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
  - [Option A: Per-Container Git Directory Isolation](#option-a-per-container-git-directory-isolation)
  - [Option B: Read-Only Mounts with Gateway-Only Writes](#option-b-read-only-mounts-with-gateway-only-writes)
  - [Option C: UID Namespace Isolation](#option-c-uid-namespace-isolation)
- [Recommended Approach](#recommended-approach)
- [Implementation Plan](#implementation-plan)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)

## Context

### Background

The james-in-a-box system runs multiple container instances concurrently, each working on different tasks. Each container needs:
1. Access to repository source code for reading and editing
2. Ability to commit changes to isolated branches
3. Ability to push via the gateway sidecar

Currently, git worktrees are used to give each container an isolated branch while sharing the object database. The architecture involves:

```
Host Machine
├── ~/.git-main/                    # Shared git directories
│   └── james-in-a-box/
│       ├── objects/                # Shared object database
│       ├── refs/                   # Branch references
│       └── worktrees/              # Worktree admin directories
│           ├── james-in-a-box/     # Container 1's admin dir
│           └── james-in-a-box2/    # Container 2's admin dir
│
├── ~/repos/james-in-a-box/         # Host's working copy
│   └── .git → ~/.git-main/.../worktrees/james-in-a-box
│
└── ~/.jib-worktrees/               # Container worktrees
    ├── jib-20260127-001/james-in-a-box/
    └── jib-20260127-002/james-in-a-box/
```

### The Incident

During a PR review session, Container A had a broken `.git` file pointing to a non-existent worktree admin directory (`james-in-a-box2`). When attempting to fix this, the agent modified the `.git` file to point to Container B's worktree admin directory (`james-in-a-box`).

This caused Container A to:
- Operate on Container B's branch
- See Container B's staged changes and commit history
- Potentially commit to the wrong branch

### Current Access Model

Each container currently has read-write access to:
- `/home/jib/repos/` - Repository working copies
- `/home/jib/.git-main/` - Full git directory structure including ALL worktrees
- `/home/jib/.jib-worktrees/` - All container worktree directories

**The core issue:** Containers can access and modify other containers' git state.

## Problem Statement

Multiple jib container instances share access to `~/.git-main/` which contains worktree admin directories for all containers. A container can accidentally (or through prompt injection) modify another container's `.git` file and hijack its worktree, leading to:

1. **Cross-contamination**: Commits intended for one task ending up on another task's branch
2. **Data loss**: Overwriting another container's uncommitted changes
3. **Security breach**: Malicious prompt injection could deliberately target other containers

## Decision

Implement **Option A: Per-Container Git Directory Isolation** as the primary solution, with elements of Option B for defense-in-depth.

## High-Level Design

### Option A: Per-Container Git Directory Isolation

Create a separate, complete git directory for each container that shares objects via alternates but has isolated refs and worktree state.

```
Host Machine (After Implementation)
├── ~/.git-main/james-in-a-box/           # Master repository
│   ├── objects/                          # Authoritative object store
│   ├── refs/                             # Master refs
│   └── (no worktrees/ directory)
│
├── ~/.jib-containers/
│   ├── jib-20260127-001/
│   │   └── git/james-in-a-box/           # Container 1's isolated .git
│   │       ├── objects/info/alternates   # Points to master objects
│   │       ├── refs/                     # Container 1's refs only
│   │       └── HEAD                      # Container 1's HEAD
│   │
│   └── jib-20260127-002/
│       └── git/james-in-a-box/           # Container 2's isolated .git
│           ├── objects/info/alternates   # Points to master objects
│           ├── refs/                     # Container 2's refs only
│           └── HEAD                      # Container 2's HEAD
```

**Container Mount Strategy:**
```bash
# Container 1 only sees its own git directory
-v ~/.jib-containers/jib-001/git:/home/jib/.git-isolated:rw
-v ~/.git-main/james-in-a-box/objects:/home/jib/.git-objects:ro  # Shared objects (read-only)
-v ~/repos/james-in-a-box:/home/jib/repos/james-in-a-box:rw

# .git file in repo points to isolated directory
echo "gitdir: /home/jib/.git-isolated/james-in-a-box" > .git
```

**Advantages:**
- Complete isolation of git state between containers
- Shared object database reduces disk usage
- Read-only object mount prevents object corruption
- No worktree admin directory confusion

**Disadvantages:**
- More complex setup during container creation
- Need to sync refs from master when container starts
- Slightly more disk usage for per-container refs

### Option B: Read-Only Mounts with Gateway-Only Writes

Make repository mounts read-only and route ALL git write operations through the gateway.

```bash
# Repository is read-only
-v ~/repos/james-in-a-box:/home/jib/repos/james-in-a-box:ro

# Gateway handles all writes via API
POST /api/v1/git/stage    # Stage files
POST /api/v1/git/commit   # Create commits
POST /api/v1/git/push     # Push to remote
```

**Advantages:**
- Simpler mount structure
- All writes go through auditable gateway
- Easy to implement container-specific restrictions

**Disadvantages:**
- Significant gateway complexity increase
- Performance overhead for every git operation
- Need to handle all git commands (hundreds of subcommands)
- User experience impact (git commands become API calls)

### Option C: UID Namespace Isolation

Use different UIDs per container with filesystem permissions.

```bash
# Container 1 runs as UID 10001
# Container 2 runs as UID 10002

# Each container's git directory owned by its UID
chown -R 10001 ~/.jib-containers/jib-001/
chown -R 10002 ~/.jib-containers/jib-002/
```

**Advantages:**
- Kernel-enforced isolation
- No changes to git workflow

**Disadvantages:**
- Complex UID management
- Docker rootless mode complications
- Shared object store permissions become complex

## Recommended Approach

Implement **Option A** with the following modifications:

1. **Per-container git directories** with shared objects via alternates
2. **Read-only `.git` file** in the working copy (container cannot modify the gitdir pointer)
3. **Container-specific mount** of only that container's git directory

### Mount Structure

```bash
docker run \
  # Working copy - container can edit files
  -v ~/repos/james-in-a-box:/home/jib/repos/james-in-a-box:rw \

  # Container's isolated git directory
  -v ~/.jib-containers/${CONTAINER_ID}/git/james-in-a-box:/home/jib/.git-container/james-in-a-box:rw \

  # Shared objects (read-only to prevent corruption)
  -v ~/.git-main/james-in-a-box/objects:/home/jib/.git-shared-objects/james-in-a-box:ro \

  # NO mount of ~/.git-main/ or other containers' directories
```

### Initialization Flow

```python
def create_container_git(container_id: str, repo: str):
    """Create isolated git directory for container."""

    container_git = f"~/.jib-containers/{container_id}/git/{repo}"
    master_git = f"~/.git-main/{repo}"

    # 1. Create container's git directory structure
    os.makedirs(f"{container_git}/objects/info")
    os.makedirs(f"{container_git}/refs/heads")
    os.makedirs(f"{container_git}/refs/remotes/origin")

    # 2. Set up alternates to share objects
    with open(f"{container_git}/objects/info/alternates", "w") as f:
        f.write(f"{master_git}/objects\n")

    # 3. Copy essential config
    shutil.copy(f"{master_git}/config", container_git)

    # 4. Fetch latest refs from remote
    run(f"git --git-dir={container_git} fetch origin main")

    # 5. Create container's working branch
    branch = f"jib-temp-{container_id}"
    run(f"git --git-dir={container_git} branch {branch} origin/main")
    run(f"git --git-dir={container_git} symbolic-ref HEAD refs/heads/{branch}")

    # 6. Create .git file in working copy (will be read-only in container)
    with open(f"~/repos/{repo}/.git.{container_id}", "w") as f:
        f.write(f"gitdir: /home/jib/.git-container/{repo}\n")
```

### Gateway Sidecar Changes

The gateway already handles git push operations. Additional changes:

1. **Validate container identity**: Ensure push requests only affect the requesting container's branches
2. **Object sync**: When container pushes, sync new objects to master repository
3. **Ref sync**: Update master refs when container creates commits that should be visible

## Implementation Plan

### Phase 1: Infrastructure (PR 1)
- [ ] Create `~/.jib-containers/` directory structure
- [ ] Implement `create_container_git()` function in jib launcher
- [ ] Update mount configuration in `jib` script
- [ ] Add cleanup of container git directories on exit

### Phase 2: Gateway Integration (PR 2)
- [ ] Update gateway to sync objects from container git to master
- [ ] Add container identity validation to push endpoint
- [ ] Implement ref sync for pushed branches

### Phase 3: Migration (PR 3)
- [ ] Migrate existing worktree-based setup to new model
- [ ] Update worktree-watcher to clean up new directory structure
- [ ] Add migration script for existing containers

### Phase 4: Validation (PR 4)
- [ ] Add integration tests for container isolation
- [ ] Test concurrent container operations
- [ ] Test recovery from container crashes

## Consequences

### Positive
- **Complete isolation**: Containers cannot access each other's git state
- **Reduced accident risk**: No way to accidentally hijack another container's worktree
- **Security improvement**: Prompt injection cannot affect other containers' git state
- **Cleaner architecture**: No more worktree admin directory confusion

### Negative
- **Increased complexity**: More moving parts in container setup
- **Disk usage**: Small increase for per-container refs (negligible)
- **Object sync overhead**: Gateway needs to sync objects between container and master

### Neutral
- **Existing workflow preserved**: Git commands work the same from user perspective
- **Gateway role expanded**: Gateway becomes more central to git operations

## Alternatives Considered

### 1. Behavioral Controls Only
Rely on CLAUDE.md instructions to tell agents not to modify other containers' files.

**Rejected:** Not enforceable. The incident that prompted this ADR happened despite clear instructions.

### 2. Chroot/Jail per Container
Use Linux namespaces to create completely isolated filesystem views.

**Rejected:** Overly complex for this use case. Would require significant Docker configuration changes.

### 3. Separate Clones per Container
Give each container its own complete git clone.

**Rejected:** Excessive disk usage. A full clone of james-in-a-box is ~500MB. With 10 concurrent containers, that's 5GB.

### 4. Keep Current Architecture with Monitoring
Add monitoring to detect cross-container access and alert.

**Rejected:** Detection after the fact doesn't prevent the problem. Data loss or corruption may have already occurred.

---

Authored-by: jib
