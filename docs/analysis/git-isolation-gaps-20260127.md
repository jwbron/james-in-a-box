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
| `/home/jib/.git-admin/X/index` | `~/.git/X/worktrees/<id>/index` | (part of above) | **rw** (separate mount) |
| `/home/jib/.git-local-objects/X` | Docker volume | rw | **remove** |
| `/home/jib/.git-objects/X` | `~/.git/X/objects` | ro | ro (unchanged) |
| `/home/jib/.git-refs/X` | `~/.git/X/refs` | ro | ro (unchanged) |
| `/home/jib/.git-common/X` | `~/.git/X` | ro | ro (unchanged) |

**Note:** The index file is mounted separately as rw to allow `git add` to work locally while keeping the rest of the admin directory read-only.

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
| `git add` | Container (local) | Index file mounted rw separately |
| `git commit` | Gateway | Intercepted by git wrapper |
| `git reset` | Gateway | Intercepted, routes to gateway |
| `git checkout <branch>` | Gateway | Intercepted, routes to gateway |
| `git checkout <file>` | Container (local) | Allowed - only modifies working tree |
| `git rebase` | Blocked | Returns error with guidance |
| `git merge` | Gateway | Intercepted, routes to gateway |
| `git stash` | Blocked | Returns error with guidance |
| `git push` | Gateway | Already implemented |
| `git fetch` | Gateway | Already implemented |

## Implementation Plan

**Note:** Phase numbering aligns with the ADR. Phase 1 (Mount Configuration) is already complete.

### Phase 2: Fix Host Path Leakage (Immediate)
**Goal:** Stop containers from corrupting host git state

1. Change worktree admin mount from `rw` to `ro` (except index file)
2. Mount index file separately as `rw` for staging operations
3. Use relative paths in `commondir` file (`../..` instead of absolute)
4. Remove container path writes from `entrypoint.py`

**Files to modify:**
- `jib-container/runtime.py` - mount mode change, add index mount
- `jib-container/entrypoint.py` - remove worktree metadata writes

**Validation:**
- Host git commands work after container exit
- Container git read operations still work
- `git add` works in container (index is rw)

### Phase 3: Gateway Commit Endpoint (Core Feature)
**Goal:** Enable commits from containers

1. Add `POST /api/v1/git/commit` endpoint
2. Input validation:
   - Reject repo/worktree containing path traversal sequences (`../`, absolute paths)
   - Verify worktree belongs to requesting container (via container ID mapping)
   - Sanitize commit message for shell safety
3. Read index from container's worktree
4. Create commit on host using index
5. Return commit SHA to container

**Files to modify:**
- `gateway-sidecar/main.go` - add endpoint
- `gateway-sidecar/git.go` - commit logic with input validation

**Validation:**
- Commit from container creates proper commit on host
- Commit visible in git log
- Commit can be pushed
- Path traversal attempts are rejected
- Cross-container commit attempts are rejected

### Phase 4: Git Wrapper Update
**Goal:** Intercept `git commit` and route to gateway

1. Update git wrapper to detect commit commands
2. Extract message, author, and options
3. Call gateway commit endpoint
4. Return result to caller
5. Add handling for other write operations (reset, checkout, rebase, merge, stash)

**Files to modify:**
- `gateway-sidecar/wrappers/git-wrapper.sh` (or equivalent)

**Validation:**
- `git commit -m "msg"` works from container
- Commit options (--amend, etc.) handled appropriately
- Blocked operations return helpful error messages

### Phase 5: Cleanup & Testing
**Goal:** Remove unused infrastructure and verify end-to-end

1. Remove local object volume provisioning
2. Add integration tests for all phases
3. Update ADR with final implementation status
4. Close related beads

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

### Phase 2 Tests (Host Path Leakage Fix)
- [ ] Host `git status` works after container exit
- [ ] Host `git log` works after container exit
- [ ] Container `git status` works (read-only admin)
- [ ] Container `git log` works (read-only admin)
- [ ] Container `git add` works (rw index mount)

### Phase 3 Tests (Gateway Commit Endpoint)
- [ ] Gateway commit creates valid commit object
- [ ] Commit author is set correctly
- [ ] Commit message is preserved
- [ ] Staged files are included in commit
- [ ] Unstaged files are not included
- [ ] Path traversal in repo param rejected (`../other-repo`)
- [ ] Path traversal in worktree param rejected (`../other-container`)
- [ ] Absolute paths rejected
- [ ] Cross-container commit attempts rejected (container A can't commit to container B's worktree)
- [ ] Commit message with shell metacharacters handled safely

### Phase 4 Tests (Git Wrapper Update)
- [ ] `git commit -m "msg"` routes to gateway
- [ ] `git commit` (interactive) returns helpful error
- [ ] `git reset --hard` routes to gateway
- [ ] `git checkout <branch>` routes to gateway
- [ ] `git checkout <file>` works locally
- [ ] `git rebase` returns blocked error with guidance
- [ ] `git merge` routes to gateway
- [ ] `git stash` returns blocked error with guidance
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
