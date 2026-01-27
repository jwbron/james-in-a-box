# Git Worktree Isolation: Implementation Gap Assessment

**Date:** 2026-01-27
**Updated:** 2026-01-27 (implemented)
**Related PRs:** #590 (this revision), #571 (original ADR), #588 (dockerignore fix)
**Status:** ✅ Implemented

## Executive Summary

The Container Worktree Isolation architecture (ADR in PR #571) needs revision. The original approach over-complicated the solution by routing local git operations through the gateway.

**Simplified approach:**
- All **local** git operations (commit, add, status, etc.) happen **in the container**
- Only **remote** operations (push, fetch, pull) go through the **gateway sidecar**
- **Isolation** is achieved through mount structure - each container only sees its own worktree

## Current Implementation State

The mount isolation is **partially implemented** in `jib-container/jib_lib/runtime.py` (`_setup_git_isolation_mounts()` function, lines 38-141). However, it has issues:

| Component | Current State | Target State | Status |
|-----------|--------------|--------------|--------|
| Worktree admin mount | Mounted as rw | rw | ✅ Done |
| Objects mount | Mounted as **ro** via alternates | **rw** direct mount | ❌ Needs change |
| Refs mount | Mounted as **ro** | **rw** | ❌ Needs change |
| packed-refs mount | **Not mounted** | rw | ❌ Missing |
| Config/hooks mount | Mounted as ro | ro | ✅ Done |
| Local objects + alternates | Implemented | **Remove** (unnecessary complexity) | ❌ Needs removal |

**Key decision:** Remove the alternates approach. The current code creates a local objects directory with alternates pointing to shared objects (ro). This adds complexity without security benefit since objects are content-addressed. We'll mount shared objects directly as rw instead.

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
-v ~/.jib-worktrees/${CONTAINER}/${REPO}:/home/jib/repos/${REPO}:rw

# Worktree admin (rw) - ONLY this container's worktree
-v ~/.git/${REPO}/worktrees/${WORKTREE}:/home/jib/.git-admin/${REPO}:rw

# Shared objects (rw) - for creating commits
-v ~/.git/${REPO}/objects:/home/jib/.git-common/${REPO}/objects:rw

# Shared refs (rw) - for updating branch pointers
-v ~/.git/${REPO}/refs:/home/jib/.git-common/${REPO}/refs:rw

# Packed refs (rw) - git stores refs both as loose files and packed-refs
-v ~/.git/${REPO}/packed-refs:/home/jib/.git-common/${REPO}/packed-refs:rw

# Config and hooks (ro) - shared configuration
-v ~/.git/${REPO}/config:/home/jib/.git-common/${REPO}/config:ro
-v ~/.git/${REPO}/hooks:/home/jib/.git-common/${REPO}/hooks:ro
```

**Path convention:** Worktree admin is mounted at `.git-admin/{repo}/`. Shared git components are mounted under `.git-common/{repo}/` to support multiple repositories. The `commondir` file uses an absolute path `/home/jib/.git-common/{repo}`.

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

**Goal:** Isolate containers from each other and enable local commits

**File to modify:** `jib-container/jib_lib/runtime.py`

**Changes to `_setup_git_isolation_mounts()` function:**

1. **Change objects mount from ro to rw** (line ~127):
   ```python
   # Current:
   ["-v", f"{shared_objects_path}:/home/jib/.git-objects/{repo_name}:ro"]
   # Change to:
   ["-v", f"{shared_objects_path}:/home/jib/.git-admin/objects:rw"]
   ```

2. **Change refs mount from ro to rw** (line ~135):
   ```python
   # Current:
   ["-v", f"{shared_refs_path}:/home/jib/.git-refs/{repo_name}:ro"]
   # Change to:
   ["-v", f"{shared_refs_path}:/home/jib/.git-admin/refs:rw"]
   ```

3. **Add packed-refs mount** (new, after refs mount):
   ```python
   packed_refs_path = main_git_path / "packed-refs"
   if packed_refs_path.exists():
       mount_args.extend(
           ["-v", f"{packed_refs_path}:/home/jib/.git-admin/packed-refs:rw"]
       )
   ```

4. **Remove local objects directory and alternates setup** (lines ~114-120):
   - Remove `Config.LOCAL_OBJECTS_BASE` directory creation
   - Remove local objects mount
   - This simplifies the architecture (alternates no longer needed)

5. **Update mount paths for consistency**:
   - All shared git dirs mount under `/home/jib/.git-admin/` (not `.git-objects/`, `.git-refs/`)
   - This matches `commondir` resolution (`../..` from `/home/jib/.git-admin/repo`)

**Validation:**
- Container can't see other worktrees
- Container can't navigate to `../other-worktree`
- Local git operations (commit, add, etc.) work

### Phase 2: Host Path Handling

**Goal:** Prevent container paths from corrupting host git state

**File to modify:** `jib-container/entrypoint.py`

**Changes to `setup_worktrees()` function:**

1. **Remove alternates setup** (lines ~630-637):
   - Delete code that creates alternates file pointing to shared objects
   - Delete `Config.git_local_objects_dir` usage
   - No longer needed since we mount objects directly as rw

2. **Set `commondir` to relative path**:
   ```python
   # In worktree admin dir, write:
   commondir_file.write_text("../..\n")
   ```
   This resolves to `/home/jib/.git-admin` where objects/refs are mounted.

3. **Implement gitdir backup/restore**:
   ```python
   # On container startup (in setup_worktrees):
   gitdir_file = target_path / "gitdir"
   gitdir_backup = target_path / "gitdir.host-backup"

   # Backup original host path
   if gitdir_file.exists() and not gitdir_backup.exists():
       shutil.copy2(gitdir_file, gitdir_backup)

   # Write container-internal path
   gitdir_file.write_text(f"/home/jib/repos/{repo_name}\n")
   ```

4. **Restore gitdir on exit** (in `cleanup_on_exit()`):
   ```python
   # For each worktree admin dir:
   gitdir_backup = admin_path / "gitdir.host-backup"
   gitdir_file = admin_path / "gitdir"
   if gitdir_backup.exists():
       shutil.copy2(gitdir_backup, gitdir_file)
       gitdir_backup.unlink()
   ```

**New file:** `bin/jib-cleanup-worktree`

Cleanup script for crashed containers that didn't restore gitdir:

```bash
#!/bin/bash
# Restore gitdir files from backups after container crash
# Usage: jib-cleanup-worktree [container-id]

for backup in ~/.git/*/worktrees/*/gitdir.host-backup; do
    if [[ -f "$backup" ]]; then
        gitdir="${backup%.host-backup}"
        echo "Restoring: $gitdir"
        cp "$backup" "$gitdir"
        rm "$backup"
    fi
done
```

**Validation:**
- Host git commands work after container exit
- `gitdir` file contains host path after container exit
- `gitdir.host-backup` cleaned up after normal exit
- No `/home/jib/...` paths in host metadata after container exit

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
- [ ] Host `git status` works on worktree after container exit
- [ ] Host `git log` works on worktree after container exit
- [ ] Verify `gitdir` file restored to host path after container exit
- [ ] Verify `gitdir.host-backup` cleaned up after normal exit
- [ ] Test recovery from crashed container (manual `gitdir` restore)
- [ ] No container paths in host metadata (except during container runtime)

### Concurrency Tests
- [ ] Two containers commit simultaneously - both succeed without corruption
- [ ] Verify git ref locking works across Docker bind mount boundaries
- [ ] Verify no data loss when containers write to shared objects/ concurrently
- [ ] Concurrent `git add` operations don't corrupt index files (each container has own index)

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

### No Alternates for Objects

Current implementation uses local objects directory with alternates to shared objects (ro). We're removing this because:
- Adds complexity (alternates file setup, local objects dir management)
- No security benefit (objects are content-addressed, corruption is detectable)
- Direct rw mount is simpler and works correctly

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Container corrupts shared refs (e.g., `refs/heads/main`) | Medium | Low | Gateway blocks unauthorized push; `git fetch origin main:refs/heads/main` recovers; remote is source of truth |
| Container corrupts shared objects | Low | Very Low | Content-addressed (SHA-1); corruption detectable via hash mismatch; `git fetch` recovers |
| gitdir not restored after crash | Medium | Low | `bin/jib-cleanup-worktree` script; backup file makes recovery trivial |
| Concurrent commits race condition | Low | Low | Git's native `.lock` files work correctly across Docker bind mounts |
| Container paths leak to host metadata | Medium | Medium | gitdir backup/restore; relative paths in commondir; cleanup on exit |

**Accepted risks:**
- Containers have rw access to shared refs and objects
- A malicious container could corrupt local git state for other containers
- This is acceptable because: (1) gateway enforces push policy, (2) remote is source of truth, (3) recovery is straightforward via fetch

## References

- ADR: `docs/adr/implemented/ADR-Container-Worktree-Isolation.md`
- PR #571: Container Worktree Isolation ADR (merged)
- PR #588: Dockerignore fix (merged)

---
Authored-by: jib
