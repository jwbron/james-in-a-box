# ADR: Git Isolation via Overlayfs

**Status:** Proposed
**Date:** 2026-01-27
**Supersedes:** ADR-Container-Worktree-Isolation (partial)
**Related PRs:** #590, #592, #594

## Context

PR #590 implemented git worktree isolation to allow multiple jib containers to work on the same repository without affecting each other. The implementation modifies git metadata files (`gitdir`, `commondir`) in shared bind-mounted directories to use container-internal paths.

This approach has fundamental limitations discovered in PR #594:

1. **Host git operations break** while any container is running (paths like `/home/jib/...` don't exist on host)
2. **Crash recovery required** - if a container exits abnormally, host git operations remain broken until manual cleanup
3. **Gateway complexity** - the gateway sidecar needs additional mounts to access the rewritten paths

## Requirements

The git isolation solution must support:

1. **N containers simultaneously** - arbitrary number of jib containers on the same repos
2. **Container isolation** - modifications in one container don't affect others
3. **Host isolation** - container modifications don't affect host git operations
4. **Gateway access** - sidecar can perform git/gh operations for any container
5. **No cleanup required** - host should work correctly regardless of container state

## Problem Analysis

### Why Path Rewriting Fails

Git stores paths in metadata files that must resolve correctly for whoever reads them:

| File | Container writes | Host expects |
|------|-----------------|--------------|
| `gitdir` | `/home/jib/repos/{repo}` | `/home/user/khan/{repo}` |
| `commondir` | `/home/jib/.git-common/{repo}` | `/home/user/.git/{repo}` |

With different mount namespaces, the same absolute path cannot work for both host and container. The current approach of rewriting paths creates a mutually exclusive situation: either host works OR container works, not both.

### Alternatives Considered

| Approach | Why it doesn't work |
|----------|---------------------|
| Relative paths | Mount structures differ; relative paths resolve to different locations |
| Environment variables | `GIT_COMMON_DIR` exists but `gitdir` has no env var equivalent |
| Host-side symlinks | Requires root, path mapping per-repo, potential user conflicts |
| Cleanup scripts | Only helps after container exits; doesn't solve simultaneous access |

## Proposed Solution: Overlayfs Isolation

Use overlayfs to give each container a copy-on-write view of repositories and git data.

### Architecture

```
Host filesystem (always untouched):
├── ~/khan/{repo}/                    # Working directories
└── ~/.git/{repo}/                    # Git data (objects, refs, config, etc.)

Per-container overlay:
├── ~/.jib-overlays/{container-id}/
│   ├── upper/                        # Container's writes land here
│   │   ├── repos/{repo}/             # Modified working files
│   │   └── git/{repo}/               # Modified git metadata
│   └── work/                         # Overlayfs workdir (required)

Container mount structure:
└── /home/jib/
    ├── repos/{repo}                  # overlayfs: lower=host repo, upper=container-specific
    └── .git/{repo}                   # overlayfs: lower=host git, upper=container-specific
```

### How It Works

1. **Container startup**: Create overlayfs mounts combining host directories (lower/read-only) with container-specific upper directories
2. **Container reads**: Served from host filesystem (lower layer)
3. **Container writes**: Go to container's upper layer only
4. **Host operations**: Always see the original files (lower layer)
5. **Other containers**: Each has its own upper layer, isolated from others
6. **Container exit**: Discard upper layer (or optionally merge changes back)

### Gateway Access

The gateway sidecar needs to access container-created git objects for push operations. Options:

**Option A: Mount container overlays in gateway**
- Gateway mounts each active container's merged overlayfs view
- Can read new commits/refs directly
- Requires dynamic mount management as containers start/stop

**Option B: Shared objects staging area**
- Containers write new git objects to a shared staging directory
- Gateway reads from staging, pushes to remote
- Simpler mount structure, but requires object copying

**Option C: Container packages objects in push request**
- Container bundles new objects (e.g., via `git bundle`) when requesting push
- Gateway receives objects directly, no special mounts needed
- Higher latency for large pushes

**Recommendation**: Option A for simplicity and performance. Gateway can use a configuration file or API to discover active container overlays.

### Mount Configuration

Container startup would use mounts like:

```bash
# Create overlay directories
mkdir -p ~/.jib-overlays/${CONTAINER_ID}/{upper/repos,upper/git,work}

# For each repo:
mount -t overlay overlay \
  -o lowerdir=${HOME}/khan/${repo},upperdir=${OVERLAY}/upper/repos/${repo},workdir=${OVERLAY}/work/repos/${repo} \
  /home/jib/repos/${repo}

mount -t overlay overlay \
  -o lowerdir=${HOME}/.git/${repo},upperdir=${OVERLAY}/upper/git/${repo},workdir=${OVERLAY}/work/git/${repo} \
  /home/jib/.git/${repo}
```

Note: This requires either:
- Running container setup with privileges to create overlay mounts, OR
- Pre-creating overlays on host before container start (preferred for security)

### Container Exit Handling

| Scenario | Action |
|----------|--------|
| Clean exit, no changes to keep | Delete upper layer directory |
| Clean exit, want to persist changes | Merge upper layer to host (explicit command) |
| Crash/kill | Upper layer remains; can be inspected or deleted |
| Host cleanup | Simply `rm -rf ~/.jib-overlays/{container-id}` |

No git metadata corruption possible since host files are never modified.

## Comparison with Current Approach

| Aspect | Current (PR #590) | Overlayfs |
|--------|-------------------|-----------|
| Host git while container runs | Broken | Works |
| Multi-container isolation | Partial (worktrees) | Complete (separate overlays) |
| Crash recovery | Manual script needed | Delete directory |
| Implementation complexity | Medium | Higher (overlay setup) |
| Disk usage | Low (shared objects) | Medium (CoW, mostly shared) |
| Gateway access | Needs path translation | Mount merged view |
| Privilege requirements | None | Overlay mount (can be pre-created) |

## Implementation Plan

### Phase 1: Core Overlay Infrastructure
1. Create overlay mount helper script for host
2. Modify `jib` launcher to set up overlays before container start
3. Update container entrypoint to expect overlay mounts (remove path rewriting)
4. Test basic git operations in container

### Phase 2: Gateway Integration
1. Implement container overlay discovery in gateway
2. Mount active container overlays in gateway container
3. Update push/fetch to use overlay paths
4. Test multi-container scenarios

### Phase 3: Lifecycle Management
1. Implement overlay cleanup on container exit
2. Add optional "persist changes" command
3. Add host-side cleanup utility for orphaned overlays
4. Update documentation

## Migration

The overlayfs approach can coexist with the current worktree approach during transition:

1. New containers use overlayfs
2. Existing worktree-based sessions continue to work
3. Eventually deprecate worktree path rewriting

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Overlayfs not available | Check kernel support; fall back to current approach |
| Privilege escalation via overlay | Pre-create overlays on host with correct permissions |
| Disk space from many overlays | Implement aggressive cleanup; monitor usage |
| Performance overhead | CoW is generally fast; benchmark critical paths |

## Decision

Adopt overlayfs-based isolation to replace the path-rewriting approach from PR #590. This provides true isolation between containers and host while maintaining gateway access for remote operations.

## References

- PR #590: Original worktree isolation implementation
- PR #592: Fixes for #590 (logs mount, SSH URLs)
- PR #594: Documents path leakage issues
- [Overlayfs documentation](https://docs.kernel.org/filesystems/overlayfs.html)
