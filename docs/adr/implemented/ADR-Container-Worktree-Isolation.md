# ADR: Container Worktree Isolation

**Driver:** jib (autonomous agent)
**Approver:** James Wiesebron
**Contributors:** jib
**Informed:** Engineering teams
**Proposed:** January 2026
**Implemented:** January 2026 (partial), Revised January 2026
**Status:** Partially Implemented - Revised

## Revision History

| Date | Change | Reason |
|------|--------|--------|
| 2026-01-27 | Initial ADR merged | PR #571 |
| 2026-01-27 | Revised: Gateway-based commits | Security requirement - all git write operations must go through gateway |

## Revision Notice (2026-01-27)

**Important:** The original ADR proposed local commits with object sync. This has been revised to route ALL git write operations through the gateway for security enforcement.

**What changed:**
- Local commits are **no longer supported** - commits go through gateway
- Local object storage is **no longer needed** - gateway creates commits on host
- Object sync is **no longer needed** - objects are created directly in shared store

**Why:** Security requirement that all repository-modifying operations must go through the gateway for policy enforcement and audit trail. This aligns with the existing model where pushes already go through the gateway.

**See:** `docs/analysis/git-isolation-gaps-20260127.md` for full analysis.

---

## Table of Contents

- [Context](#context)
- [Problem Statement](#problem-statement)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
- [Recommended Approach](#recommended-approach)
  - [Mount Structure](#mount-structure)
  - [Container `.git` File Update](#container-git-file-update)
  - [Gateway Commit Endpoint](#gateway-commit-endpoint)
  - [Refs Strategy](#refs-strategy)
  - [commondir Configuration](#commondir-configuration)
  - [Gateway Sidecar Integration](#gateway-sidecar-integration)
- [Test Results](#test-results)
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
├── ~/.git-main/                    # Shared git directories (or ~/repos/repo/.git)
│   └── james-in-a-box/
│       ├── objects/                # Shared object database
│       ├── refs/                   # Branch references
│       └── worktrees/              # Worktree admin directories
│           ├── jib-container-1/    # Container 1's admin dir
│           └── jib-container-2/    # Container 2's admin dir
│
└── ~/.jib-worktrees/               # Container worktrees
    ├── jib-20260127-001/james-in-a-box/
    └── jib-20260127-002/james-in-a-box/
```

### The Incident

During a PR review session, Container A had a broken `.git` file pointing to a non-existent worktree admin directory. When attempting to fix this, the agent modified the `.git` file to point to Container B's worktree admin directory.

This caused Container A to:
- Operate on Container B's branch
- See Container B's staged changes and commit history
- Potentially commit to the wrong branch

### Current Access Model

Each container currently has read-write access to:
- `/home/jib/repos/` - Repository working copies (worktrees)
- `/home/jib/.git-main/` - **Full git directory structure including ALL worktree admin directories**
- `/home/jib/.jib-worktrees/` - All container worktree directories

**The core issue:** Containers can access and modify other containers' git state because the entire `.git` directory (including all worktree admin dirs) is mounted to each container.

## Problem Statement

Multiple jib container instances share access to `~/.git-main/` which contains worktree admin directories for all containers. A container can accidentally (or through prompt injection) modify another container's `.git` file and hijack its worktree, leading to:

1. **Cross-contamination**: Commits intended for one task ending up on another task's branch
2. **Data loss**: Overwriting another container's uncommitted changes
3. **Security breach**: Malicious prompt injection could deliberately target other containers

## Decision

Implement **Mount-Restriction Isolation with Gateway-Based Commits** - an approach that:
1. Restricts what each container can see (isolation via mounts)
2. Routes all git write operations through the gateway (security via centralized control)

## High-Level Design

### Security Model

All git operations fall into two categories:

| Operation Type | Examples | Where It Runs | Security |
|---------------|----------|---------------|----------|
| **Read** | status, log, diff, show | Container (local) | Safe - read-only access |
| **Write** | commit, reset, checkout | Gateway (host) | Policy enforced |

The gateway is the single control point for all repository-modifying operations.

### Adopted Approach: Mount-Restriction + Gateway Commits

Instead of allowing local commits with complex git configuration, route commit operations through the gateway:

**Container View (Read-Only Git State):**
```bash
# Container can read but not write git state
-v ~/.jib-worktrees/container-1/repo:/home/jib/repos/repo:rw          # Working dir (editable)
-v ~/.git/repo/worktrees/container-1:/home/jib/.git-admin/repo:ro     # Worktree admin (read-only)
-v ~/.git/repo/objects:/home/jib/.git-objects/repo:ro                  # Shared objects
-v ~/.git/repo/refs:/home/jib/.git-refs/repo:ro                        # Shared refs
-v ~/.git/repo:/home/jib/.git-common/repo:ro                           # Common git dir
```

**Commit Flow:**
```
Container                          Gateway                         Host
   |                                  |                              |
   |-- git add (local staging) ------>|                              |
   |                                  |                              |
   |-- git commit (intercepted) ----->|                              |
   |                                  |-- create commit on host ---->|
   |                                  |<-- commit SHA ---------------|
   |<-- commit SHA -------------------|                              |
```

**Advantages:**
- Single security boundary (gateway)
- No complex git configuration needed
- No object sync needed - commits created directly on host
- Audit trail for all write operations
- Each container can only see its own worktree admin directory

## Recommended Approach

### Mount Structure

For each repository, mount (all read-only except working directory):

1. **Worktree working directory** (rw) - Container's isolated working copy for editing files
2. **Worktree admin directory** (ro) - For git status/log operations
3. **Shared objects** (ro) - Read-only access to object database
4. **Shared refs** (ro) - Read-only access to branch references
5. **Shared git common dir** (ro) - For commondir resolution (config, hooks, etc.)

```bash
# Complete mount structure for a container
-v ~/.jib-worktrees/${CONTAINER}/repo:/home/jib/repos/repo:rw           # Working dir (rw for editing)
-v ~/.git/repo/worktrees/${WORKTREE}:/home/jib/.git-admin/repo:ro       # Worktree admin (ro)
-v ~/.git/repo/worktrees/${WORKTREE}/index:/home/jib/.git-admin/repo/index:rw  # Index (rw for staging)
-v ~/.git/repo/objects:/home/jib/.git-objects/repo:ro                    # Shared objects (ro)
-v ~/.git/repo/refs:/home/jib/.git-refs/repo:ro                          # Shared refs (ro)
-v ~/.git/repo:/home/jib/.git-common/repo:ro                             # Common dir (ro)
```

**Note:** Local object storage volumes are no longer needed since commits are created on the host.

### Staging (`git add`) with Read-Only Admin Mount

**Issue:** The index file lives in the worktree admin directory (`/home/jib/.git-admin/repo/index`). With the admin mount read-only, `git add` will fail.

**Solution:** Mount the index file separately as read-write:

```bash
# Index file mounted separately for staging
-v ~/.git/repo/worktrees/${WORKTREE}/index:/home/jib/.git-admin/repo/index:rw
```

This allows `git add` to work locally while keeping the rest of the admin directory read-only. The gateway reads this index when creating commits.

**Alternative considered:** Route `git add` through gateway. Rejected due to latency impact on staging operations (which are frequent during development).

### Container `.git` File Update

Each container's worktree `.git` file must be updated to point to the container's mount path:

```
gitdir: /home/jib/.git-admin/repo
```

This is done during container initialization. The path must use a format that doesn't leak back to the host (see [Host Path Leakage Fix](#host-path-leakage-fix)).

### Host Path Leakage Fix

**Problem:** Container writes container-specific paths to host worktree metadata, breaking git on the host after container exit.

**Solution:** Use relative paths in worktree metadata files:

| File | Use | Format |
|------|-----|--------|
| `commondir` | Points to main .git | `../..` (relative) |
| `gitdir` | Points to worktree .git file | Keep host path (don't modify) |

The container should NOT modify these files. Instead:
1. Make worktree admin directory read-only
2. Gateway handles any necessary metadata updates on the host side

### Gateway Commit Endpoint

New endpoint for commit operations:

**Request:**
```
POST /api/v1/git/commit
{
  "repo": "james-in-a-box",
  "worktree": "jib-20260127-001",
  "message": "Add feature X",
  "author": "jib <jib@example.com>"
}
```

**Gateway Actions:**
1. Validate request (policy check)
   - Reject `repo` or `worktree` containing path traversal sequences (`../`, absolute paths)
   - Verify worktree belongs to requesting container (via container ID mapping)
   - Sanitize commit message (escape shell metacharacters)
2. Navigate to container's worktree on host
3. Stage changes (git add) based on container's index
4. Create commit with provided message
5. Return commit SHA

**Response:**
```
{
  "sha": "abc123...",
  "branch": "feature-x"
}
```

### Git Wrapper Update

The git wrapper (`/usr/bin/git` symlink) intercepts commit commands:

```bash
# Pseudocode
if command == "commit":
    # Extract message and options
    # Send to gateway commit endpoint
    # Return result to caller
else:
    # Pass through to gateway for other operations
```

### Other Write Operations

Beyond `commit`, other git write operations are handled as follows:

| Operation | Handling | Rationale |
|-----------|----------|-----------|
| `git reset` | Route through gateway | Modifies refs and working tree |
| `git reset --soft` | Route through gateway | Modifies HEAD ref |
| `git checkout <branch>` | Route through gateway | Modifies HEAD and working tree |
| `git checkout <file>` | Allow local (read-only refs) | Only modifies working tree from existing refs |
| `git rebase` | Block | Requires interactive mode, complex ref manipulation |
| `git merge` | Route through gateway | Modifies refs and may create commits |
| `git stash` | Block | Creates refs, rarely needed in jib workflow |

**Implementation:** The git wrapper intercepts these commands and either routes them to appropriate gateway endpoints or returns a helpful error message directing users to the supported workflow.

### Refs Strategy

Refs are read-only from the container's perspective:

- **Reading refs**: Container reads from `/home/jib/.git-refs/repo` (read-only mount)
- **Updating refs**: Gateway updates refs on host after commit/push operations
- **Ref visibility**: Changes are immediately visible to containers via read-only mount

### commondir Configuration

Git worktrees use a `commondir` file to locate the shared git directory:

**Container's worktree admin dir (read-only):**
```
/home/jib/.git-admin/repo/
├── HEAD                 # Current branch reference (read via mount)
├── commondir            # Points to shared git components (relative path)
├── gitdir               # Path to worktree (host path, unchanged)
└── index                # Staging area (managed by gateway for commits)
```

**commondir contents (relative path):**
```
../..
```

Using relative paths ensures the file works from both container and host perspectives.

### Gateway Sidecar Integration

The gateway sidecar is extended with commit handling:

1. **New commit endpoint**: Handles commit requests from containers
2. **Index management**: Reads container's staged changes, applies to host worktree
3. **Commit creation**: Creates commit on host with proper attribution
4. **Policy enforcement**: Same rules as push (branch ownership, etc.)

**Existing functionality unchanged:**
- Push operations
- Fetch operations
- Authentication
- Policy enforcement

## Test Results

The mount-restriction approach was tested on 2026-01-26 with positive results for isolation.

### Test 1: Basic Git Operations

Created a simulated container view with restricted mounts. Read operations worked correctly:

```
✓ git status works
✓ git log works
✓ git diff works
```

### Test 2: Cross-Container Isolation

Created two simulated containers with separate restricted views:

```
✓ Container A can ONLY see its own admin dir
✓ Container B can ONLY see its own admin dir
```

### Key Findings

1. **Git path resolution works**: Git correctly resolves the `.git` file to the restructured mount paths
2. **Read operations work**: Status, log, diff all function correctly
3. **Isolation is effective**: Each container only sees its own worktree admin directory

### Additional Tests Needed

- [ ] Gateway commit endpoint functionality
- [ ] Index transfer from container to host
- [ ] Commit visibility across containers after gateway commit
- [ ] Git wrapper intercept for commit commands

## Implementation Plan

### Phase 1: Mount Configuration (Complete)
- [x] Modify `runtime.py` to mount individual git components
- [x] Mount only the container's specific worktree admin dir
- [x] Mount shared objects read-only
- [x] Mount shared refs read-only

### Phase 2: Host Path Leakage Fix
- [ ] Update worktree admin mount to read-only
- [ ] Use relative paths in commondir
- [ ] Test host git commands work after container exit

### Phase 3: Gateway Commit Endpoint
- [ ] Add `/api/v1/git/commit` endpoint to gateway
- [ ] Implement index reading from container worktree
- [ ] Implement commit creation on host
- [ ] Add policy enforcement for commits

### Phase 4: Git Wrapper Update
- [ ] Update git wrapper to intercept `commit` command
- [ ] Route commit to gateway endpoint
- [ ] Return commit result to caller

### Phase 5: Testing
- [ ] Add integration tests for gateway commits
- [ ] Test concurrent commits from multiple containers
- [ ] Test commit + push workflow
- [ ] Verify host git works after container exit

## Consequences

### Positive
- **Complete isolation**: Containers cannot access each other's git state
- **Security enforcement**: All writes go through gateway with policy checks
- **Audit trail**: Gateway logs all commit operations
- **Simpler architecture**: No local object storage or sync needed
- **No host corruption**: Read-only mounts prevent path leakage

### Negative
- **Network dependency**: Commits require gateway communication
- **Latency**: Commits are slower than local operations
- **Gateway complexity**: Additional endpoint and logic

### Neutral
- **Existing workflow mostly preserved**: Read operations unchanged
- **Push unchanged**: Already goes through gateway

## Alternatives Considered

### 1. Local Commits with Object Sync (Original ADR)
Allow local commits with container-specific object storage, sync to shared store after push.

**Rejected:** Complex git configuration needed; doesn't meet security requirement for gateway-controlled writes.

### 2. Behavioral Controls Only
Rely on CLAUDE.md instructions to tell agents not to modify other containers' files.

**Rejected:** Not enforceable. The incident that prompted this ADR happened despite instructions.

### 3. Read-Only Repository Mounts
Make all repo mounts read-only and route ALL operations through gateway.

**Rejected:** Too restrictive. File editing needs to be local for performance.

### 4. GitHub API for Commits
Use GitHub API directly for all commits (current workaround).

**Rejected:** Slow, can't batch, loses local workflow benefits. Acceptable as interim workaround only.

---

Authored-by: jib
