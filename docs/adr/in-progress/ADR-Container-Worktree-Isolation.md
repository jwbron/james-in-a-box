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
- [Recommended Approach](#recommended-approach)
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

Implement **Mount-Restriction Isolation** - a simpler approach that preserves the existing worktree architecture but restricts what each container can see.

## High-Level Design

### Original Option A: Per-Container Git Directory Isolation (Rejected)

The original proposal created separate, complete git directories for each container with shared objects via alternates. This was rejected because:

1. **Working copy inconsistency**: The ADR showed shared `~/repos/` mount but worktrees use isolated directories
2. **`.git.{container_id}` naming bug**: Git only recognizes `.git`, not custom variants
3. **Object sync complexity**: Requires non-trivial sync between container and master objects
4. **Unnecessary complexity**: The simpler mount-restriction approach achieves the same isolation

### Adopted Approach: Mount-Restriction Isolation

Instead of creating new per-container git directories, restrict what the existing `.git` directory mounts to each container:

**Current (Problematic):**
```bash
# Mounts ENTIRE .git directory - all containers see all worktree admin dirs
-v ~/.git/repo:/home/jib/.git-main/repo:rw
```

**Proposed (Isolated):**
```bash
# Container 1 only sees its own worktree admin dir
-v ~/.jib-worktrees/container-1/repo:/home/jib/repos/repo:rw          # Worktree working dir
-v ~/.git/repo/worktrees/container-1:/home/jib/.git-admin/repo:rw     # ONLY this container's admin
-v ~/.git/repo/objects:/home/jib/.git-objects/repo:ro                  # Shared objects (read-only)
-v ~/.git/repo/refs:/home/jib/.git-refs/repo:ro                        # Shared refs (read-only)
```

**Advantages:**
- Preserves existing worktree architecture
- Zero new directory structures
- Zero object sync mechanisms
- Simpler implementation
- Each container can only see its own worktree admin directory

## Recommended Approach

### Mount Structure

For each repository, mount:

1. **Worktree working directory** (rw) - Container's isolated working copy
2. **Worktree admin directory ONLY** (rw) - Just this container's admin dir, not all worktrees
3. **Shared objects** (ro) - Read-only access to object database
4. **Shared refs** (ro) - Read-only access to branch references
5. **Essential config files** - Copy of git config

### Container `.git` File Update

Each container's worktree `.git` file must be updated to point to the container's mount path:

```
gitdir: /home/jib/.git-admin/repo
```

This is done during container initialization.

## Test Results

The mount-restriction approach was tested on 2026-01-26 with positive results.

### Test 1: Basic Git Operations

Created a simulated container view with restricted mounts. All git operations worked correctly:

```
Test directory: /tmp/git-isolation-test-*
✓ Created main repo
✓ Created worktree
✓ Created container-view mount structure
✓ Updated .git file to point to restricted mount

=== Testing git operations in container-view ===
✓ git status works
✓ git log works
✓ git add works (staging)
✓ git commit works
✓ Commit visible in main repo
```

### Test 2: Cross-Container Isolation

Created two simulated containers with separate restricted views:

```
=== Test 1: Both containers can work independently ===
✓ Container A committed
✓ Container B committed

=== Test 2: Commits visible from main repo ===
✓ Container A's commit visible
✓ Container B's commit visible

=== Test 3: Cross-container isolation ===
  Container A sees worktree admins: ['myrepo']      # ONLY its own
  Container B sees worktree admins: ['myrepo1']     # ONLY its own
✓ Container A can ONLY see its own admin dir
✓ Container B can ONLY see its own admin dir

Summary:
- Each container can only see its own worktree admin directory
- Objects and refs are shared (commits visible across containers)
- Container A cannot access Container B's git state
```

### Key Findings

1. **Git path resolution works**: Git correctly resolves the `.git` file to the restructured mount paths
2. **Objects remain shared**: The alternates mechanism works - commits from one container are visible to others
3. **Isolation is effective**: Each container only sees its own worktree admin directory
4. **No new mechanisms needed**: The existing worktree architecture is preserved

## Implementation Plan

### Phase 1: Update Mount Configuration
- [ ] Modify `runtime.py` to mount individual git components instead of entire `.git` directory
- [ ] Mount only the container's specific worktree admin dir
- [ ] Mount shared objects read-only
- [ ] Mount shared refs read-only
- [ ] Copy essential config files

### Phase 2: Container Initialization
- [ ] Update worktree `.git` file to point to container mount paths during initialization
- [ ] Ensure `commondir` resolution works with new paths

### Phase 3: Testing
- [ ] Add integration tests for container isolation
- [ ] Test concurrent container operations
- [ ] Test cleanup still works correctly

## Consequences

### Positive
- **Complete isolation**: Containers cannot access each other's git state
- **Simple implementation**: Uses existing architecture with restricted mounts
- **No object sync needed**: Shared object store continues to work
- **Reduced accident risk**: No way to accidentally hijack another container's worktree

### Negative
- **More mount points**: Each repo needs 4-5 mounts instead of 2
- **Path translation**: Container paths differ from host paths (already the case)

### Neutral
- **Existing workflow preserved**: Git commands work the same from user perspective
- **Worktree cleanup unchanged**: Existing cleanup mechanisms still work

## Alternatives Considered

### 1. Per-Container Git Directories (Original Option A)
Create complete isolated git directories per container with alternates.

**Rejected:** Unnecessarily complex. Mount-restriction achieves the same isolation with less code.

### 2. Behavioral Controls Only
Rely on CLAUDE.md instructions to tell agents not to modify other containers' files.

**Rejected:** Not enforceable. The incident that prompted this ADR happened despite instructions.

### 3. Read-Only Repository Mounts
Make all repo mounts read-only and route writes through gateway.

**Rejected:** Significant gateway complexity. Performance overhead for every git operation.

### 4. Keep Current Architecture with Monitoring
Add monitoring to detect cross-container access and alert.

**Rejected:** Detection after the fact doesn't prevent data loss or corruption.

---

Authored-by: jib
