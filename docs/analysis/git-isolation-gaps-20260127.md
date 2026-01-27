# Git Worktree Isolation: Implementation Gap Assessment

**Date:** 2026-01-27
**Related PRs:** #571 (ADR), #588 (dockerignore fix)
**Status:** Decision Made - Local Operations with Mount Isolation

## Executive Summary

The Container Worktree Isolation architecture (ADR in PR #571) needs revision. The original approach over-complicated the solution by routing local git operations through the gateway.

**Simplified approach:**
- All **local** git operations (commit, add, status, etc.) happen **in the container**
- Only **remote** operations (push, fetch, pull) go through the **gateway sidecar**
- **Isolation** is achieved through mount structure - each container only sees its own worktree

## The Problem

### What Happened

Container A accessed Container B's worktree admin directory and operated on the wrong branch.

### Root Cause

The entire `~/.git/repo/worktrees/` directory was mounted to each container. Containers could see all worktrees and modify their `.git` file to point to any of them.

### What We Need to Prevent

1. Container A accessing Container B's worktree
2. Containers corrupting host git state
3. Container paths leaking into host metadata

## The Solution: Mount Isolation

### Key Insight

Mount **only** the specific worktree admin directory, not the parent directory:

```bash
# BEFORE (problematic) - container sees ALL worktrees
-v ~/.git/repo/worktrees:/home/jib/.git/worktrees

# AFTER (isolated) - container sees ONLY its own worktree
-v ~/.git/repo/worktrees/${THIS_WORKTREE}:/home/jib/.git-admin/repo
```

### Complete Mount Structure

```bash
# Working directory (rw) - where files are edited
-v ~/.jib-worktrees/${CONTAINER}/repo:/home/jib/repos/repo:rw

# Worktree admin (rw) - ONLY this container's worktree
-v ~/.git/repo/worktrees/${WORKTREE}:/home/jib/.git-admin/repo:rw

# Shared objects (rw) - for creating commits
-v ~/.git/repo/objects:/home/jib/.git-objects/repo:rw

# Shared refs (rw) - for updating branch pointers
-v ~/.git/repo/refs:/home/jib/.git-refs/repo:rw

# Config and hooks (ro) - shared configuration
-v ~/.git/repo/config:/home/jib/.git-common/repo/config:ro
-v ~/.git/repo/hooks:/home/jib/.git-common/repo/hooks:ro
```

### Why This Works

1. **Isolation**: Container can't see other worktrees (they're not mounted)
2. **Local commits work**: Container has rw access to objects and refs
3. **No gateway complexity**: No need to route local operations through gateway
4. **Gateway unchanged**: Still handles push/fetch with credentials

## Operations Matrix

| Operation | Where | Why |
|-----------|-------|-----|
| `git status` | Container | Local read operation |
| `git log` | Container | Local read operation |
| `git diff` | Container | Local read operation |
| `git add` | Container | Updates local index |
| `git commit` | Container | Creates local objects + updates refs |
| `git reset` | Container | Modifies local state |
| `git checkout` | Container | Modifies local state |
| `git branch` | Container | Modifies local refs |
| `git merge` | Container | Local operation |
| `git rebase` | Container | Local operation |
| `git push` | Gateway | Needs credentials + policy enforcement |
| `git fetch` | Gateway | Needs credentials |
| `git pull` | Gateway (fetch) + Container (merge) | Fetch needs credentials |

## Implementation Plan

### Phase 1: Mount Structure Fix

**Goal:** Isolate containers from each other

1. Change mount from `worktrees/` directory to specific `worktrees/${WORKTREE}` directory
2. Mount objects and refs as rw (needed for local commits)
3. Mount config/hooks as ro

**Files to modify:**
- `jib-container/runtime.py` - mount structure

**Validation:**
- Container can't see other worktrees
- Container can't navigate to `../other-worktree`
- Local git operations (commit, add, etc.) work

### Phase 2: Host Path Handling

**Goal:** Prevent container paths from corrupting host git state

1. Use relative paths in `commondir` file (`../..` instead of absolute)
2. Ensure `.git` file uses paths that work from container's view
3. Don't modify host worktree metadata from container

**Files to modify:**
- `jib-container/entrypoint.py` - path handling

**Validation:**
- Host git commands work after container exit
- No `/home/jib/...` paths in host metadata

### Phase 3: Testing

**Goal:** Verify isolation and functionality

1. Test all local git operations work in container
2. Test cross-container isolation
3. Test push/fetch via gateway
4. Test concurrent operations

## Test Cases

### Isolation Tests
- [ ] Container A cannot see Container B's worktree admin dir
- [ ] Container cannot `ls` or `cd` to other worktrees
- [ ] Modifying `.git` to point elsewhere fails (target doesn't exist)

### Local Operation Tests
- [ ] `git status` works
- [ ] `git add` works
- [ ] `git commit` works
- [ ] `git log` works
- [ ] `git diff` works
- [ ] `git reset` works
- [ ] `git checkout` works
- [ ] `git branch` works

### Remote Operation Tests
- [ ] `git push` routes through gateway
- [ ] `git fetch` routes through gateway
- [ ] `git pull` works (fetch via gateway, merge local)
- [ ] Credentials never exposed to container

### Host Protection Tests
- [ ] Host `git status` works after container exit
- [ ] Host `git log` works after container exit
- [ ] No container paths in host metadata

## What We're NOT Doing

### No Gateway Commit Endpoint

Previous revision proposed routing commits through gateway. This is unnecessary because:
- Commits are local filesystem operations
- Don't need network access or credentials
- Adds latency and complexity for no security benefit

### No Git Wrapper Changes for Local Operations

Previous revision proposed intercepting `git commit`, `git reset`, etc. This is unnecessary because:
- Mount isolation provides the security boundary
- Local operations should just work normally
- Simpler = better

### No Complex Index Mounting

Previous revision proposed separate rw mount for index file. This is unnecessary because:
- Entire worktree admin dir can be rw
- It's isolated to this container anyway

## References

- ADR: `docs/adr/implemented/ADR-Container-Worktree-Isolation.md`
- PR #571: Container Worktree Isolation ADR (merged)
- PR #588: Dockerignore fix (merged)

---
Authored-by: jib
