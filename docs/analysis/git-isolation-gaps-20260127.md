# Git Worktree Isolation: Implementation Gap Assessment

**Date:** 2026-01-27
**Related PRs:** #571 (ADR), #588 (dockerignore fix)
**Status:** Investigation

## Executive Summary

The Container Worktree Isolation architecture (ADR in PR #571) is partially implemented. The mount structure is in place, but critical git configuration inside containers is missing, preventing local commits. Additionally, container path writes leak back to the host, breaking git commands on the host after containers exit. This document identifies the gaps and proposes solutions.

## Observed Behavior

When attempting to commit in a container:

```
$ git commit -m "test"
fatal: cannot lock ref 'HEAD': Unable to create 
'/home/jib/.git-common/james-in-a-box/refs/heads/fix-host-services-venv-setup.lock': 
Read-only file system
```

**Root Cause:** Git attempts to write ref locks to the read-only `.git-common` mount instead of the writable worktree admin directory.

When running git commands on the host after a container has run:

```
$ git branch
fatal: Invalid path '/home/jib': No such file or directory
```

**Root Cause:** Container writes container-specific paths (`/home/jib/...`) to the host's worktree metadata files, which persist after container exit.

## Current Mount Structure (Working)

The mounts are correctly configured:

| Mount Path | Source | Mode | Purpose |
|------------|--------|------|---------|
| `/home/jib/repos/X` | `~/.jib-worktrees/<id>/X` | rw | Working directory |
| `/home/jib/.git-admin/X` | `~/.git/X/worktrees/<id>` | rw | Worktree admin |
| `/home/jib/.git-local-objects/X` | Docker volume | rw | Local objects |
| `/home/jib/.git-objects/X` | `~/.git/X/objects` | ro | Shared objects |
| `/home/jib/.git-refs/X` | `~/.git/X/refs` | ro | Shared refs |
| `/home/jib/.git-common/X` | `~/.git/X` | ro | Common git dir |

## Missing Configuration (Not Working)

### 1. Git Object Directory Not Configured

**ADR Says:**
> "Container's git config is updated: `objects = /home/jib/.git-local-objects/repo`"

**Reality:**
```
$ git config --list | grep objects
(no output)
```

The alternates file exists and points to the shared objects, but git doesn't know to use the local objects directory for writes. Manual workaround requires:
```bash
export GIT_OBJECT_DIRECTORY=/home/jib/.git-local-objects/james-in-a-box
export GIT_ALTERNATE_OBJECT_DIRECTORIES=/home/jib/.git-common/james-in-a-box/objects
```

### 2. Ref Updates Not Redirected

**ADR Says:**
> "Git updates the ref (in the container's view, this writes to a path that maps back to the host)"

**Reality:** No mechanism exists to redirect ref writes. Git attempts to write to `/home/jib/.git-common/X/refs/` which is read-only.

The ADR's description of how this should work is incomplete:
- Worktree HEAD is in `.git-admin` (writable) ✓
- Branch locks are in worktree admin dir ✗ (git tries `.git-common/refs/`)
- No ref redirection mechanism implemented

### 3. Host-Side Path Leakage (Breaks Host Git)

**Problem:** After a container runs, git commands fail on the host:

```
$ git branch
fatal: Invalid path '/home/jib': No such file or directory
```

**Root Cause:** The container's `entrypoint.py` (`setup_worktrees()` function, lines 564-694) writes container paths to the host's worktree metadata files. These files are in `.git/worktrees/<name>/` which is mounted read-write from the host.

The following files get corrupted with container paths:

| File | Container writes | Should be |
|------|------------------|-----------|
| `commondir` | `/home/jib/.git-common/repo` | `../..` or absolute host path |
| `config` | `worktree = /home/jib/repos/repo` | Host worktree path |
| `gitdir` | `/home/jib/.git-admin/repo` | Host `.git` file path |

**Why this persists:** The worktree admin directory is mounted `rw` so the container can update `HEAD`, `index`, etc. But the path updates leak back to the host and persist after the container exits.

**Workaround:** Remove the corrupted worktree metadata:
```bash
rm -rf .git/worktrees/<worktree-name>
```

**Fix Options:**
1. **Make worktree admin read-only** - but this breaks legitimate writes (HEAD, index)
2. **Use relative paths** - `commondir: ../..` works from both perspectives
3. **Restore paths on container exit** - add cleanup in signal handler
4. **Copy instead of mount** - fully isolate the worktree admin directory

### 4. Implementation Plan Unchecked

The ADR's implementation plan shows all tasks unchecked:

- [ ] Phase 1: Mount Configuration (mounts exist but not all config)
- [ ] Phase 2: Container Initialization (git config for local objects)
- [ ] Phase 3: Gateway Updates (object sync after push)
- [ ] Phase 4: Cleanup Verification
- [ ] Phase 5: Testing

Yet the ADR status says "Implemented".

## Consequences

1. **Containers cannot make local commits** - all commits must go through GitHub API
2. **Workaround required** - using `gh api` contents endpoint works but is slow
3. **Gateway push won't work** - even if we could commit locally, push would fail without object sync
4. **Host git breaks after container runs** - container paths leak into host worktree metadata, requiring manual cleanup

## Proposed Solutions

### Option A: Complete the ADR Implementation

1. **Add git config during container initialization:**
   ```bash
   git config --local core.worktree /home/jib/repos/X
   git config --local core.repositoryformatversion 1
   git config --local extensions.worktreeConfig true
   # Enable per-worktree config for objects
   ```

2. **Implement ref redirection:**
   - Git worktrees normally update refs in the main `.git/refs/`
   - Need to investigate if `extensions.refStorage` or similar can redirect
   - May need gateway-based ref updates (like current push model)

3. **Add gateway object sync:**
   - After successful push, copy new objects from container volume to shared store
   - This is documented in the ADR but not implemented

### Option B: Gateway-Based Commits

Route all commits through the gateway, similar to push:

1. Container stages changes locally (git add works)
2. Container sends commit request to gateway
3. Gateway creates commit on host using container's staged changes
4. Gateway returns commit SHA to container
5. Container can then push normally

**Pros:** Avoids complex git configuration, single source of truth
**Cons:** More gateway code, slower commits, network dependency

### Option C: Accept API-Based Workflow

Document that containers should use GitHub API for commits:

1. Stage changes locally (for review)
2. Use `gh api repos/.../contents/...` to push file changes
3. GitHub creates commits server-side

**Pros:** Already working (used in PR #589)
**Cons:** Slow, can't batch commits, loses local git history benefits

## Recommendation

**Short term:** Document Option C as current workaround
**Medium term:** Implement Option B (gateway commits) for better UX
**Long term:** Complete Option A if git configuration proves feasible

## Test Cases Needed

1. [ ] Local commit with proper git config (Option A)
2. [ ] Gateway commit endpoint (Option B)
3. [ ] Object visibility after gateway sync
4. [ ] Concurrent commits from multiple containers
5. [ ] Push after local commit
6. [ ] Host git commands work after container exit (no path leakage)

## References

- ADR: `docs/adr/implemented/ADR-Container-Worktree-Isolation.md`
- PR #571: Container Worktree Isolation ADR
- PR #588: Dockerignore fix (symptom of #571)
- PR #589: Example of API workaround

---
Authored-by: jib
