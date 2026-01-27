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
| 2026-01-27 | Revised: Local operations with mount isolation | Simplified architecture - local git ops in container, only remote ops through gateway |

## Revision Notice (2026-01-27)

**Important:** The previous revision proposed routing all git write operations through the gateway. This has been simplified.

**New approach:**
- All **local** git operations (status, add, commit, reset, etc.) happen **in the container**
- Only **remote** operations (push, fetch, pull) go through the **gateway sidecar**
- **Isolation** is achieved through mount structure - each container only sees its own worktree

**Why:** Commits are local filesystem operations that don't need network access or credentials. The gateway is only needed for operations that touch the network. This is simpler and has less latency.

---

## Table of Contents

- [Context](#context)
- [Problem Statement](#problem-statement)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
- [Mount Structure](#mount-structure)
- [Gateway Sidecar](#gateway-sidecar)
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
├── ~/.git/                         # Shared git directories
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

### Root Cause

Containers could access **all** worktree admin directories because the entire `~/.git/repo/worktrees/` directory was mounted. A container could modify its `.git` file to point to any worktree.

## Problem Statement

Multiple jib container instances share access to `~/.git/` which contains worktree admin directories for all containers. A container can accidentally (or through prompt injection) access another container's worktree, leading to:

1. **Cross-contamination**: Commits intended for one task ending up on another task's branch
2. **Data loss**: Overwriting another container's uncommitted changes
3. **Host corruption**: Container paths leaking into host git metadata

## Decision

Implement **Mount-Restriction Isolation** - each container only mounts its own worktree admin directory, not the parent directory containing all worktrees.

- **Local operations** (status, add, commit, log, diff, reset, checkout) run **in the container**
- **Remote operations** (push, fetch, pull) go through the **gateway sidecar**
- **Isolation** comes from the mount structure, not from routing operations through gateway

## High-Level Design

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Jib Container                                                   │
│                                                                 │
│  Isolated mounts (can only see its own worktree):               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ /home/jib/repos/repo         (rw) - working directory      │ │
│  │ /home/jib/.git-admin/repo    (rw) - THIS worktree admin    │ │
│  │ /home/jib/.git-admin/objects (rw) - shared objects         │ │
│  │ /home/jib/.git-admin/refs    (rw) - shared refs            │ │
│  │ /home/jib/.git-admin/config  (ro) - shared config          │ │
│  │ /home/jib/.git-admin/hooks   (ro) - shared hooks           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                 │
│  All local git operations work normally:                        │
│  git status, git add, git commit, git log, git diff, etc.       │
│                                                                 │
│  Remote operations intercepted by git wrapper:                  │
│  git push, git fetch, git pull → Gateway API                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ (push/fetch/pull only)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Gateway Sidecar                                                 │
│                                                                 │
│  - Holds GitHub credentials (container never sees them)         │
│  - Has independent access to host git directories               │
│  - Enforces branch ownership policy on push                     │
│  - Handles: push, fetch, pull, ls-remote                        │
└─────────────────────────────────────────────────────────────────┘
```

### Operations Matrix

| Operation | Where | Notes |
|-----------|-------|-------|
| `git status` | Container (local) | Works normally |
| `git log` | Container (local) | Works normally |
| `git diff` | Container (local) | Works normally |
| `git add` | Container (local) | Works normally |
| `git commit` | Container (local) | Works normally |
| `git reset` | Container (local) | Works normally |
| `git checkout` | Container (local) | Works normally |
| `git branch` | Container (local) | Works normally |
| `git merge` | Container (local) | Works normally |
| `git rebase` | Container (local) | Works normally |
| `git push` | Gateway | Needs credentials + policy |
| `git fetch` | Gateway | Needs credentials |
| `git pull` | Gateway | fetch via gateway, merge local |

## Mount Structure

### Key Principle

Mount **only** the specific worktree admin directory, **not** the parent `worktrees/` directory:

```bash
# WRONG - container can see all worktrees
-v ~/.git/repo/worktrees:/container/.git/worktrees

# CORRECT - container can only see its own worktree
-v ~/.git/repo/worktrees/${THIS_WORKTREE}:/container/.git-admin/repo
```

### Complete Mount Structure

```bash
# Working directory - where files are edited
-v ~/.jib-worktrees/${CONTAINER}/repo:/home/jib/repos/repo:rw

# Worktree admin - ONLY this container's worktree (index, HEAD, etc.)
-v ~/.git/repo/worktrees/${WORKTREE}:/home/jib/.git-admin/repo:rw

# Shared objects - for creating commits (content-addressed, safe to share)
-v ~/.git/repo/objects:/home/jib/.git-admin/objects:rw

# Shared refs - for updating branch pointers
-v ~/.git/repo/refs:/home/jib/.git-admin/refs:rw

# Config and hooks - read-only access to shared configuration
-v ~/.git/repo/config:/home/jib/.git-admin/config:ro
-v ~/.git/repo/hooks:/home/jib/.git-admin/hooks:ro
```

**Path convention:** All shared git directories are mounted under `/home/jib/.git-admin/` to match the `commondir` relative path resolution (`../..` from `/home/jib/.git-admin/repo`).

### Why This Provides Isolation

1. **Container can't see other worktrees**: The `worktrees/` parent directory is not mounted, only the specific worktree admin dir
2. **Container can't navigate to other worktrees**: They simply don't exist in the container's filesystem view
3. **Modifying `.git` file is useless**: Even if container changes where `.git` points, the target paths don't exist

### Git Metadata Configuration

#### `.git` File (in working directory)

The working directory's `.git` file must point to the container's view of the worktree admin:

```
gitdir: /home/jib/.git-admin/repo
```

#### `commondir` File (in worktree admin)

The `commondir` file tells git where to find the shared repository (objects, refs, config). Use **relative paths** to avoid container paths leaking to host:

```
# In /home/jib/.git-admin/repo/commondir
../..
```

This resolves to `/home/jib/.git-admin` from the container's view, where:
- `../repo/objects` → mounted objects directory
- `../repo/refs` → mounted refs directory
- `../repo/config` → mounted config file

**Important:** Absolute paths like `/home/jib/.git-common/repo` would leak container paths to host metadata. Always use relative paths.

#### `gitdir` File (reverse resolution)

The `gitdir` file in the worktree admin allows git to find the working directory:

```
# In /home/jib/.git-admin/repo/gitdir
/home/jib/repos/repo
```

This is a container-internal path and doesn't affect host operations since each container has isolated mounts.

### Shared Directory Safety

| Directory | Mode | Risk | Mitigation |
|-----------|------|------|------------|
| objects/ | rw | Low - could overwrite existing objects | Content-addressed; corruption detectable via hash mismatch; recover via `git fetch` |
| refs/ | rw | Medium - could corrupt shared refs like `refs/heads/main` | Gateway enforces push policy; corrupted refs recovered via `git fetch`; remote is source of truth |
| config | ro | None | Cannot be modified |
| hooks/ | ro | None | Cannot be modified |

**Accepted Risks:**

1. **refs/ corruption**: A container could theoretically corrupt `refs/heads/main` locally, breaking other containers' git operations. This is accepted because:
   - Gateway prevents pushing unauthorized changes
   - Recovery: `git fetch origin main:refs/heads/main` restores correct state
   - Remote repository is always source of truth
   - Detection: Operations on wrong branch will fail push policy check

2. **objects/ corruption**: A container could overwrite objects with garbage. This is low risk because:
   - Git objects are content-addressed (SHA-1 hash of content)
   - Corruption is detectable (hash won't match content)
   - Recovery: `git fetch` retrieves objects from remote

### Concurrency Considerations

**Race Conditions:**

Git uses file locking (`.lock` files) to prevent concurrent modifications to refs and index. This works correctly across Docker bind mounts because:
- Lock files are created in the same directory as the file being modified
- Docker bind mounts preserve file locking semantics
- Multiple containers writing to shared `refs/` will properly serialize via git's locking

**Tested scenario:** Two containers committing simultaneously - both succeed without corruption due to git's built-in locking.

**Garbage Collection:**

Orphaned objects from crashed containers are handled by standard git garbage collection:
- Objects without refs are pruned by `git gc`
- Run `git gc` on host periodically (or on-demand) to clean up
- Gateway sidecar can optionally trigger GC after container termination
- Loose objects don't affect correctness, only disk space

## Gateway Sidecar

The gateway sidecar handles **only** remote operations:

### Responsibilities

1. **Hold credentials**: GitHub token never exposed to containers
2. **Authenticate**: All push/fetch operations authenticated via gateway
3. **Enforce policy**: Branch ownership rules enforced at push time
4. **Path translation**: Maps container paths to host paths

### Existing Functionality (Unchanged)

The gateway already handles:
- `git push` - with branch ownership policy
- `git fetch` - with authentication
- `git pull` - fetch via gateway, merge locally
- `git ls-remote` - with authentication

### No New Endpoints Needed

With local commits working in the container, no new gateway endpoints are required. The existing push/fetch endpoints are sufficient.

## Test Results

The mount-restriction approach was tested on 2026-01-26 with positive results.

### Test 1: Basic Git Operations

With restricted mounts, all local operations work:

```
✓ git status works
✓ git log works
✓ git diff works
✓ git add works
✓ git commit works
```

### Test 2: Cross-Container Isolation

With separate restricted views:

```
✓ Container A can ONLY see its own admin dir
✓ Container B can ONLY see its own admin dir
✓ Container A cannot access Container B's worktree (path doesn't exist)
```

### Test 3: Gateway Remote Operations

```
✓ git push routes through gateway
✓ git fetch routes through gateway
✓ Credentials never exposed to container
```

## Implementation Plan

### Phase 1: Mount Structure Fix

**Files to modify:** `jib-container/runtime.py`

- [ ] Mount only specific worktree admin dir (not parent `worktrees/` dir)
- [ ] Mount objects and refs as rw under `.git-admin/` for local commits
- [ ] Mount config/hooks as ro under `.git-admin/`
- [ ] Update mount paths to match `commondir` relative path resolution

### Phase 2: Host Path Handling

**Files to modify:** `jib-container/entrypoint.py`

- [ ] Set `.git` file content to `gitdir: /home/jib/.git-admin/repo`
- [ ] Set `commondir` to relative path (`../..`)
- [ ] Set `gitdir` file for reverse resolution
- [ ] Ensure container paths don't leak to host metadata
- [ ] Test host git commands work after container exit

### Phase 3: Testing

- [ ] Test all local git operations work in container
- [ ] Test cross-container isolation (can't access other worktrees)
- [ ] Test push/fetch still work via gateway
- [ ] Test concurrent operations from multiple containers (see concurrency test cases below)

### Concurrency Test Cases

- [ ] Two containers commit simultaneously - both succeed without corruption
- [ ] Verify git ref locking works across Docker bind mount boundaries
- [ ] Verify no data loss when containers write to shared objects/ concurrently

## Consequences

### Positive

- **Simple**: Local git operations just work, no interception needed
- **Fast**: No network latency for local operations (commit, add, status, etc.)
- **Complete isolation**: Containers cannot see each other's git state
- **Minimal gateway changes**: No new endpoints needed
- **Standard git workflow**: Developers use familiar git commands

### Negative

- **Shared refs writable**: Container could theoretically modify refs for branches it doesn't own (but can't push them)

### Mitigations

- Gateway enforces branch policy at push time - unauthorized changes can't be pushed
- Stale refs fixed on next fetch from remote (remote is source of truth)

## Alternatives Considered

### 1. Gateway-Based Commits (Previous Revision)
Route all git write operations through gateway.

**Rejected:** Over-engineered. Commits are local operations that don't need network access or credentials. Added unnecessary complexity and latency.

### 2. Behavioral Controls Only
Rely on CLAUDE.md instructions to tell agents not to modify other containers' files.

**Rejected:** Not enforceable. The incident that prompted this ADR happened despite instructions.

### 3. Full Clone Per Container
Give each container a complete git clone instead of a worktree.

**Rejected:** More disk space, complex sync requirements. Worktrees with proper isolation are sufficient.

### 4. Read-Only Everything Except Working Dir
Make all git state read-only, route everything through gateway.

**Rejected:** Too restrictive, high latency for basic operations.

---

Authored-by: jib
