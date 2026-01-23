# Gateway Sidecar: Read-only File System Error on Git Push

## Problem

After a successful `git push`, users may see this error:

```
error: update_ref failed for ref 'refs/remotes/origin/<branch>': cannot lock ref
'refs/remotes/origin/<branch>': Unable to create '/home/<user>/.git-main/<repo>/
refs/remotes/origin/<branch>.lock': Read-only file system
```

**Important:** The push succeeds - commits reach the remote. This error only affects local tracking ref updates.

## Root Cause

The error stems from an interaction between three components:

### 1. Jib Container Worktree Setup

The jib container entrypoint (`jib-container/entrypoint.py:336-344`) rewrites worktree `.git` files to use container-internal paths:

```python
# Original: gitdir: /home/user/repo/.git/worktrees/name
# Rewritten to: gitdir: /home/user/.git-main/repo/worktrees/name
target_path = config.git_main_dir / repo_name / "worktrees" / worktree_admin
git_file.write_text(f"gitdir: {target_path}\n")
```

This is necessary because the host's `.git` directory is mounted at a different path inside the container (`~/.git-main/<repo>/`).

### 2. Gateway Sidecar Git Operations

The gateway sidecar runs in its own container and executes git commands from the host worktree path (`~/.jib-worktrees/<container-id>/<repo>/`). When git reads the `.git` file, it sees the container-rewritten path pointing to `~/.git-main/...`.

### 3. Gateway Mounts Are Read-Only

The gateway setup (`gateway-sidecar/setup.sh:160-162`) mounts `.git` directories as **read-only**:

```bash
GIT_MOUNTS="${GIT_MOUNTS} -v ${git_dir}:${HOME}/.git-main/${repo_name}:ro,z"
```

This was likely intentional for security - the gateway only needs to push, not modify local state.

### The Conflict

1. Push operation succeeds (writes to remote)
2. Git attempts to update local tracking refs (`refs/remotes/origin/<branch>`)
3. Ref update requires writing to `.git-main/` which is mounted read-only
4. Error is emitted, but the important operation (push) already completed

## Impact

- **Functional impact:** None. Pushes work correctly.
- **User experience:** Confusing error message after successful operations.
- **Local state:** Remote tracking refs become stale in the gateway's view (acceptable since gateway is ephemeral).

## Proposed Solutions

### Option A: Change Gateway Mounts to Read-Write (Recommended)

**Change:** In `gateway-sidecar/setup.sh`, change `:ro,z` to `:rw,z` for GIT_MOUNTS.

**Pros:**
- Eliminates the error completely
- Local refs stay in sync
- Simple one-line fix

**Cons:**
- Gateway container gains write access to `.git` directories
- Slightly larger attack surface if gateway is compromised

**Security consideration:** The gateway already has write access to GitHub via the token. Local `.git` write access doesn't significantly increase risk since an attacker with gateway access could already push malicious code.

### Option B: Suppress the Error in Git Wrapper

**Change:** Modify the git wrapper to filter out this specific error from stderr.

**Pros:**
- No change to security posture
- Gateway stays read-only

**Cons:**
- Masks the error rather than fixing it
- More complex implementation
- Could accidentally suppress legitimate errors

### Option C: Use Separate Worktrees for Gateway

**Change:** Have the gateway create its own worktrees that don't share the rewritten `.git` files.

**Pros:**
- Clean separation between container and gateway
- Each has correct paths for its context

**Cons:**
- Significant architectural change
- More disk usage (duplicate worktrees)
- Complex synchronization

### Option D: Document as Expected Behavior

**Change:** Add documentation explaining the error is benign.

**Pros:**
- No code changes
- Zero risk

**Cons:**
- Users still see confusing errors
- Doesn't fix the underlying issue

## Recommendation

**Option A (read-write mounts)** is recommended because:
1. It's a simple, targeted fix
2. The security impact is minimal (gateway already has GitHub push access)
3. It provides the best user experience
4. It keeps local state consistent

## Implementation

```diff
# gateway-sidecar/setup.sh, line 162
-GIT_MOUNTS="${GIT_MOUNTS} -v ${git_dir}:${HOME}/.git-main/${repo_name}:ro,z"
+GIT_MOUNTS="${GIT_MOUNTS} -v ${git_dir}:${HOME}/.git-main/${repo_name}:rw,z"
```

After changing, users need to re-run gateway setup:
```bash
./gateway-sidecar/setup.sh
```
