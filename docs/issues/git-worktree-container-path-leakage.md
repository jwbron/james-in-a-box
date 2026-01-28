# Issue: Git Worktree Container Path Leakage

**Status:** Open
**Severity:** High
**Affects:** Host git operations after container crash
**Related PRs:** #590, #592

## Summary

Container-internal paths (`/home/jib/...`) can leak into host git metadata files, breaking git operations on the host. This happens when a jib container exits abnormally (crash, kill, timeout) without running the cleanup handler.

## Symptoms

On the host, running `git pull` or other git operations fails with:

```
remote: Enumerating objects: 3, done.
remote: Counting objects: 100% (3/3), done.
remote: Compressing objects: 100% (3/3), done.
remote: Total 3 (delta 0), reused 0 (delta 0), pack-reused 0 (from 0)
Unpacking objects: 100% (3/3), 2.26 KiB | 2.26 MiB/s, done.
fatal: Invalid path '/home/jib': No such file or directory
error: github.com:jwbron/james-in-a-box.git did not send all necessary objects
```

The error persists even after deleting and re-cloning the repository.

## Root Cause

### How Container Path Leakage Occurs

The Container Worktree Isolation implementation (PR #590) modifies git metadata files during container startup to use container-internal paths:

1. **`entrypoint.py:setup_worktrees()`** rewrites:
   - `gitdir` file → `/home/jib/repos/{repo}` (line 625)
   - `commondir` file → `/home/jib/.git-common/{repo}` (line 642)

2. These files are in the **worktree admin directory**, which is bind-mounted from the host at:
   ```
   Host: ~/.git/james-in-a-box/worktrees/{worktree_name}/
   Container: /home/jib/.git-admin/james-in-a-box/
   ```

3. Original values are backed up to `*.host-backup` files.

4. **`cleanup_on_exit()`** (lines 1048-1114) restores the original files from backups.

### The Gap

The cleanup handler only runs on **clean** container exit (SIGTERM, SIGINT). If the container:
- Crashes
- Is killed with SIGKILL
- Times out
- Exits due to OOM

...the cleanup never runs, leaving the host metadata corrupted.

### Why Re-cloning Doesn't Fix It

The worktree admin directories are stored in the main git directory structure:
```
~/khan/james-in-a-box/.git/worktrees/james-in-a-box/
```

When the user deletes `~/khan/james-in-a-box` and clones fresh, the `.git/worktrees/` directory may not be fully recreated, but git still tries to process any worktree references found in the pack objects or refs.

Additionally, if the main git directory is at `~/.git/james-in-a-box/` (when using the separated git directory structure), deleting the working copy doesn't affect the worktree admin directories at all.

## Related Issue: Gateway Missing Mounts

A separate but related issue was discovered: the gateway sidecar container is missing mounts for `.git-admin` and `.git-common`, causing `git push` to fail with SSH URLs:

```
ERROR: Failed to get remote URL: fatal: not a git repository: /home/jib/.git-admin/james-in-a-box
```

The gateway's `start-gateway.sh` mounts:
- `~/.jib-worktrees` → `/home/jib/.jib-worktrees`
- `~/.git-main` → `/home/jib/.git-main`

But does NOT mount:
- `~/.git-admin` → `/home/jib/.git-admin` (needed for worktree git dirs)
- `~/.git-common` → `/home/jib/.git-common` (needed for shared git data)

## Immediate Workaround

Run on the host to fix corrupted worktree metadata:

```bash
# Check for container paths in worktree admin dirs
grep -r "/home/jib" ~/.git/*/worktrees/ 2>/dev/null
grep -r "/home/jib" ~/khan/*/.git/worktrees/ 2>/dev/null

# Option 1: Restore from backups (if they exist)
for dir in ~/khan/*/.git/worktrees/*/; do
  if [ -f "$dir/commondir.host-backup" ]; then
    cp "$dir/commondir.host-backup" "$dir/commondir"
    rm "$dir/commondir.host-backup"
    echo "Restored commondir in $dir"
  fi
  if [ -f "$dir/gitdir.host-backup" ]; then
    cp "$dir/gitdir.host-backup" "$dir/gitdir"
    rm "$dir/gitdir.host-backup"
    echo "Restored gitdir in $dir"
  fi
done

# Option 2: Remove stale worktree entries entirely
rm -rf ~/khan/*/.git/worktrees/*

# Clean up with git
cd ~/khan/james-in-a-box && git worktree prune -v
```

## Recommended Fixes

### Fix 1: Enhance `jib-cleanup-worktree` Script

The existing `scripts/jib-cleanup-worktree` script should be enhanced to:
1. Check for `*.host-backup` files in worktree admin directories
2. Restore `commondir` and `gitdir` from backups if found
3. Clean up the backup files after restoration

```bash
# In jib-cleanup-worktree
for admin_dir in ~/.git/*/worktrees/*/; do
  for backup in "$admin_dir"/*.host-backup; do
    [ -f "$backup" ] || continue
    original="${backup%.host-backup}"
    cp "$backup" "$original"
    rm "$backup"
  done
done
```

### Fix 2: Add Periodic Cleanup to Host Services

Add a systemd timer or cron job to periodically check for and fix corrupted worktree metadata:

```bash
# /etc/cron.hourly/jib-worktree-cleanup
#!/bin/bash
/path/to/jib-cleanup-worktree --restore-backups
```

### Fix 3: Add Missing Gateway Mounts

Update `gateway-sidecar/start-gateway.sh` to mount `.git-admin` and `.git-common`:

```bash
# Git admin directory - worktree-specific git dirs
GIT_ADMIN_DIR="$HOME_DIR/.git-admin"
if [ -d "$GIT_ADMIN_DIR" ]; then
    MOUNTS+=(-v "$GIT_ADMIN_DIR:$CONTAINER_HOME/.git-admin:z")
fi

# Git common directory - shared git data (config, refs, objects)
GIT_COMMON_DIR="$HOME_DIR/.git-common"
if [ -d "$GIT_COMMON_DIR" ]; then
    MOUNTS+=(-v "$GIT_COMMON_DIR:$CONTAINER_HOME/.git-common:z")
fi
```

### Fix 4: Use Relative Paths in commondir

Instead of absolute container paths, use relative paths in `commondir` that work in both contexts:

```
# Instead of: /home/jib/.git-common/james-in-a-box
# Use: ../../.git-common/james-in-a-box (relative from worktree admin)
```

This requires careful path calculation but would eliminate the path translation issue entirely.

## Test Plan

1. Start a container with worktree isolation
2. Kill the container with `docker kill` (no cleanup)
3. Verify host git operations fail with the expected error
4. Run the cleanup script
5. Verify host git operations work again
6. Test gateway push with SSH remote URL

## References

- ADR: Container Worktree Isolation (`docs/adr/implemented/ADR-Container-Worktree-Isolation.md`)
- PR #590: Implement git worktree isolation with mount structure
- PR #592: Fix git isolation issues (logs mount, gh auto-detect, SSH URL conversion)
- `jib-container/entrypoint.py`: Container startup and cleanup
- `gateway-sidecar/start-gateway.sh`: Gateway mount configuration

---

Authored-by: jib
