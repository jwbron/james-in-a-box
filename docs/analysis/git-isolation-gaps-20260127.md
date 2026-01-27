# Git Worktree Isolation: Implementation Gap Assessment

**Date:** 2026-01-27
**Related PRs:** #571 (ADR), #588 (dockerignore fix)
**Status:** Decision Made - Gateway-Based Commits

## Executive Summary

The Container Worktree Isolation architecture (ADR in PR #571) is partially implemented. The mount structure is in place, but local commits don't work and container path writes leak back to the host.

**Decision:** Route all git write operations through the gateway. This aligns with the security requirement that all repository-modifying operations must go through a controlled, auditable channel.

## Observed Behavior

When attempting to commit in a container:

```
$ git commit -m "test"
fatal: cannot lock ref 'HEAD': Unable to create
'/home/jib/.git-common/james-in-a-box/refs/heads/fix-host-services-venv-setup.lock':
Read-only file system
```

**Root Cause:** Git attempts to write ref locks to the read-only `.git-common` mount.

When running git commands on the host after a container has run:

```
$ git branch
fatal: Invalid path '/home/jib': No such file or directory
```

**Root Cause:** Container writes container-specific paths (`/home/jib/...`) to the host's worktree metadata files, which persist after container exit.

## Current Mount Structure

The mounts are configured but allow too much write access:

| Mount Path | Source | Current Mode | Target Mode |
|------------|--------|--------------|-------------|
| `/home/jib/repos/X` | `~/.jib-worktrees/<id>/X` | rw | rw (unchanged) |
| `/home/jib/.git-admin/X` | `~/.git/X/worktrees/<id>` | rw | **ro** |
| `/home/jib/.git-local-objects/X` | Docker volume | rw | **remove** |
| `/home/jib/.git-objects/X` | `~/.git/X/objects` | ro | ro (unchanged) |
| `/home/jib/.git-refs/X` | `~/.git/X/refs` | ro | ro (unchanged) |
| `/home/jib/.git-common/X` | `~/.git/X` | ro | ro (unchanged) |

## Issues Identified

### 1. Local Commits Don't Work

The original ADR assumed local commits would work with proper git configuration. Reality:
- Ref locks can't be created (read-only mount)
- Git configuration for local objects was never implemented
- Ref redirection mechanism doesn't exist in git

**Resolution:** Don't fix - route commits through gateway instead.

### 2. Host Path Leakage

Container writes `/home/jib/...` paths to host worktree metadata, breaking host git after container exit.

**Resolution:** Make worktree admin mount read-only. Container doesn't need to write to it since commits go through gateway.

### 3. Local Object Storage Unused

Docker volumes for local objects were provisioned but never used (git config not set up).

**Resolution:** Remove local object storage. Not needed with gateway commits.

### 4. ADR Status Incorrect

ADR says "Implemented" but implementation tasks are unchecked.

**Resolution:** Update ADR with revision notice and correct status.

## Decision: Gateway-Based Commits

**Security Requirement:** All git write operations must go through the gateway for policy enforcement and audit trail.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Container                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Edit files   │    │ git add      │    │ git commit   │      │
│  │ (local rw)   │    │ (local)      │    │ (intercepted)│      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│                                                  │               │
└──────────────────────────────────────────────────┼───────────────┘
                                                   │
                                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Gateway                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ POST /api/v1/git/commit                                   │  │
│  │ - Policy check                                            │  │
│  │ - Read staged changes from container worktree             │  │
│  │ - Create commit on host                                   │  │
│  │ - Return SHA                                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Host                                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Worktree     │    │ Objects      │    │ Refs         │      │
│  │ (shared)     │    │ (shared)     │    │ (shared)     │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

### Operations Matrix

| Operation | Location | Notes |
|-----------|----------|-------|
| File editing | Container (local) | Working directory is rw |
| `git status` | Container (local) | Read-only, works |
| `git diff` | Container (local) | Read-only, works |
| `git log` | Container (local) | Read-only, works |
| `git add` | Container (local) | Updates index in working dir |
| `git commit` | Gateway | Intercepted by git wrapper |
| `git push` | Gateway | Already implemented |
| `git fetch` | Gateway | Already implemented |

## Implementation Plan

### Phase 1: Fix Host Path Leakage (Immediate)
**Goal:** Stop containers from corrupting host git state

1. Change worktree admin mount from `rw` to `ro`
2. Use relative paths in `commondir` file (`../..` instead of absolute)
3. Remove container path writes from `entrypoint.py`

**Files to modify:**
- `jib-container/runtime.py` - mount mode change
- `jib-container/entrypoint.py` - remove worktree metadata writes

**Validation:**
- Host git commands work after container exit
- Container git read operations still work

### Phase 2: Gateway Commit Endpoint (Core Feature)
**Goal:** Enable commits from containers

1. Add `POST /api/v1/git/commit` endpoint
2. Read index from container's worktree
3. Create commit on host using index
4. Return commit SHA to container

**Files to modify:**
- `gateway-sidecar/main.go` - add endpoint
- `gateway-sidecar/git.go` - commit logic

**Validation:**
- Commit from container creates proper commit on host
- Commit visible in git log
- Commit can be pushed

### Phase 3: Git Wrapper Update
**Goal:** Intercept `git commit` and route to gateway

1. Update git wrapper to detect commit commands
2. Extract message, author, and options
3. Call gateway commit endpoint
4. Return result to caller

**Files to modify:**
- `gateway-sidecar/wrappers/git-wrapper.sh` (or equivalent)

**Validation:**
- `git commit -m "msg"` works from container
- Commit options (--amend, etc.) handled appropriately

### Phase 4: Cleanup
**Goal:** Remove unused infrastructure

1. Remove local object volume provisioning
2. Update ADR with final implementation status
3. Close related beads

**Files to modify:**
- `jib-container/runtime.py` - remove volume creation
- `docs/adr/implemented/ADR-Container-Worktree-Isolation.md` - update status

## Current Workaround

Until gateway commits are implemented, use GitHub API:

```bash
# Stage changes (for review)
git add file.txt

# View what would be committed
git diff --cached

# Commit via GitHub API
gh api repos/OWNER/REPO/contents/path/to/file.txt \
  -X PUT \
  -f message="Commit message" \
  -f content="$(base64 < file.txt)" \
  -f sha="$(git rev-parse HEAD:path/to/file.txt)"
```

**Limitations:**
- One file per API call
- No batched commits
- Slower than local commits

## Test Cases

### Phase 1 Tests
- [ ] Host `git status` works after container exit
- [ ] Host `git log` works after container exit
- [ ] Container `git status` works (read-only)
- [ ] Container `git log` works (read-only)

### Phase 2 Tests
- [ ] Gateway commit creates valid commit object
- [ ] Commit author is set correctly
- [ ] Commit message is preserved
- [ ] Staged files are included in commit
- [ ] Unstaged files are not included

### Phase 3 Tests
- [ ] `git commit -m "msg"` routes to gateway
- [ ] `git commit` (interactive) handled gracefully
- [ ] Error messages propagate to container

### Integration Tests
- [ ] Full workflow: edit -> add -> commit -> push
- [ ] Concurrent commits from multiple containers
- [ ] Commit visibility across containers

## References

- ADR: `docs/adr/implemented/ADR-Container-Worktree-Isolation.md`
- PR #571: Container Worktree Isolation ADR (merged)
- PR #588: Dockerignore fix (merged)
- PR #589: Example of API workaround

---
Authored-by: jib
