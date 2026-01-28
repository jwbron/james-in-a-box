# Implementation Plan: Git Worktree Path Leakage Fixes

**PR:** #594
**Status:** Addressing review feedback
**Priority:** Critical (Fix 1) + High (Fix 3)

---

## Summary

PR #594 documents a real issue where container-internal paths (`/home/jib/...`) leak into host git metadata when containers exit abnormally. The reviewer verified all claims and recommends shipping fixes rather than documentation alone.

This plan addresses the two recommended fixes:
1. **Fix 1 (Critical)**: Create `jib-cleanup-worktree` script for crash recovery
2. **Fix 3 (High)**: Add missing gateway mounts for `.git-admin` and `.git-common`

---

## Fix 1: Create `jib-cleanup-worktree` Script

### Purpose

Provide a host-side script that restores git metadata from backups after container crashes. This enables both manual recovery and automated periodic cleanup.

### Location

```
host-services/utilities/worktree-cleanup/
├── jib-cleanup-worktree.py          # Main cleanup script
├── jib-cleanup-worktree.service     # Systemd oneshot service
├── jib-cleanup-worktree.timer       # Periodic execution (every 15 min)
├── setup.sh                         # Installation script
└── README.md                        # Documentation
```

### Script Behavior

The `jib-cleanup-worktree.py` script will:

1. **Scan for backup files** in known worktree admin directories:
   - `~/.git-admin/*/` (new isolated worktree structure)
   - `~/khan/*/.git/worktrees/*/` (legacy structure)
   - `~/.git/*/worktrees/*/` (alternative legacy)

2. **For each `*.host-backup` file found**:
   - Read the backup file content
   - Validate it doesn't contain `/home/jib` (container paths)
   - Restore the original file (`gitdir` or `commondir`)
   - Remove the backup file
   - Log the restoration

3. **Safety checks**:
   - Skip if backup contains container paths (corrupted backup)
   - Skip if container is currently running (check via `docker ps`)
   - Dry-run mode (`--dry-run`) for testing

4. **Exit codes**:
   - 0: Success (files restored or nothing to do)
   - 1: Errors occurred during restoration

### Implementation Details

```python
#!/usr/bin/env python3
"""
jib-cleanup-worktree - Restore git metadata after container crash

Scans for *.host-backup files left by abnormally terminated containers
and restores the original host paths to gitdir/commondir files.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def is_container_running() -> bool:
    """Check if any jib container is currently running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=jib-", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True
        )
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def find_backup_files(home: Path) -> list[Path]:
    """Find all *.host-backup files in worktree admin directories."""
    backup_files = []

    # New isolated structure: ~/.git-admin/{repo}/
    git_admin = home / ".git-admin"
    if git_admin.exists():
        backup_files.extend(git_admin.glob("*/*.host-backup"))

    # Legacy structures
    for pattern in [
        home / "khan" / "*" / ".git" / "worktrees" / "*" / "*.host-backup",
        home / ".git" / "*" / "worktrees" / "*" / "*.host-backup",
    ]:
        backup_files.extend(Path("/").glob(str(pattern).lstrip("/")))

    return backup_files


def restore_backup(backup_path: Path, dry_run: bool = False) -> bool:
    """Restore a single backup file."""
    original_path = backup_path.with_suffix("")  # Remove .host-backup

    # Read backup content
    backup_content = backup_path.read_text().strip()

    # Safety: skip if backup contains container paths
    if "/home/jib" in backup_content:
        print(f"  SKIP: Backup contains container path: {backup_path}")
        return False

    if dry_run:
        print(f"  WOULD restore: {original_path.name} in {backup_path.parent}")
        return True

    # Restore
    shutil.copy2(backup_path, original_path)
    backup_path.unlink()
    print(f"  Restored: {original_path.name} in {backup_path.parent}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Restore git metadata after container crash"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be restored without making changes")
    parser.add_argument("--force", action="store_true",
                        help="Run even if a jib container is active")
    args = parser.parse_args()

    home = Path.home()

    # Safety check: don't run while container is active
    if not args.force and is_container_running():
        print("Skipping: jib container is currently running")
        print("Use --force to override")
        return 0

    backup_files = find_backup_files(home)

    if not backup_files:
        print("No backup files found - nothing to restore")
        return 0

    print(f"Found {len(backup_files)} backup file(s)")

    restored = 0
    errors = 0

    for backup_path in backup_files:
        try:
            if restore_backup(backup_path, args.dry_run):
                restored += 1
        except Exception as e:
            print(f"  ERROR: {backup_path}: {e}")
            errors += 1

    if args.dry_run:
        print(f"\nDry run: would restore {restored} file(s)")
    else:
        print(f"\nRestored {restored} file(s), {errors} error(s)")

    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
```

### Systemd Integration

**jib-cleanup-worktree.service:**
```ini
[Unit]
Description=JIB Worktree Cleanup - Restore git metadata after container crash
Documentation=file://%h/repos/james-in-a-box/host-services/utilities/worktree-cleanup/README.md
OnFailure=service-failure-notify@%n.service

[Service]
Type=oneshot
ExecStart=%h/repos/james-in-a-box/host-services/utilities/worktree-cleanup/jib-cleanup-worktree.py
StandardOutput=journal
StandardError=journal
SyslogIdentifier=jib-cleanup-worktree
PrivateTmp=yes
NoNewPrivileges=yes

[Install]
WantedBy=default.target
```

**jib-cleanup-worktree.timer:**
```ini
[Unit]
Description=JIB Worktree Cleanup Timer - Periodic recovery from container crashes
Documentation=file://%h/repos/james-in-a-box/host-services/utilities/worktree-cleanup/README.md

[Timer]
# Run every 15 minutes
OnUnitActiveSec=15min
# Also run 1 minute after boot (catch crashes from last session)
OnBootSec=1min

[Install]
WantedBy=timers.target
```

---

## Fix 3: Add Missing Gateway Mounts

### Purpose

Enable `git push` from the gateway sidecar when using worktree isolation by mounting `.git-admin` and `.git-common` directories.

### Location

```
gateway-sidecar/start-gateway.sh
```

### Changes Required

Add two new mount blocks after the existing `.git-main` mount (around line 71):

```bash
# Git admin directory - worktree-specific git dirs (for worktree isolation)
GIT_ADMIN_DIR="$HOME_DIR/.git-admin"
if [ -d "$GIT_ADMIN_DIR" ]; then
    MOUNTS+=(-v "$GIT_ADMIN_DIR:$CONTAINER_HOME/.git-admin:z")
fi

# Git common directory - shared git data for worktree isolation (objects, refs, config)
GIT_COMMON_DIR="$HOME_DIR/.git-common"
if [ -d "$GIT_COMMON_DIR" ]; then
    MOUNTS+=(-v "$GIT_COMMON_DIR:$CONTAINER_HOME/.git-common:z")
fi
```

### Context

Current mounts in `start-gateway.sh`:
- `~/.jib-worktrees` → `/home/jib/.jib-worktrees` (line 64)
- `~/.git-main` → `/home/jib/.git-main` (line 70)
- `~/.jib-local-objects` → `/home/jib/.jib-local-objects:ro` (line 76)

Missing mounts needed for worktree isolation:
- `~/.git-admin` → `/home/jib/.git-admin` (worktree admin dirs with gitdir/commondir)
- `~/.git-common` → `/home/jib/.git-common` (shared objects, refs, config)

Without these mounts, the gateway cannot resolve worktree paths when pushing.

---

## Implementation Order

### Step 1: Create worktree-cleanup utility (Fix 1)

1. Create directory: `host-services/utilities/worktree-cleanup/`
2. Create `jib-cleanup-worktree.py` with the implementation above
3. Create `jib-cleanup-worktree.service` systemd unit
4. Create `jib-cleanup-worktree.timer` for periodic execution
5. Create `setup.sh` installation script (following worktree-watcher pattern)
6. Create `README.md` with usage documentation

### Step 2: Add gateway mounts (Fix 3)

1. Edit `gateway-sidecar/start-gateway.sh`
2. Add `.git-admin` mount after line 71
3. Add `.git-common` mount after the `.git-admin` mount

### Step 3: Update documentation

1. Update `docs/issues/git-worktree-container-path-leakage.md`:
   - Add "Status: Fixed" header
   - Update Fix 1 section to reference the new script
   - Update Fix 3 section to note it's implemented
   - Add note that Fix 2 (cron) is now handled by systemd timer
   - Keep Fix 4 (relative paths) as future improvement

### Step 4: Testing

1. **Manual cleanup test:**
   ```bash
   # Create simulated backup files
   mkdir -p ~/.git-admin/test-repo
   echo "/home/user/repos/test-repo" > ~/.git-admin/test-repo/gitdir.host-backup
   echo "/home/user/.git/test-repo" > ~/.git-admin/test-repo/commondir.host-backup

   # Run cleanup in dry-run mode
   ./jib-cleanup-worktree.py --dry-run

   # Run actual cleanup
   ./jib-cleanup-worktree.py

   # Verify files restored
   cat ~/.git-admin/test-repo/gitdir
   ls ~/.git-admin/test-repo/*.host-backup  # Should be gone
   ```

2. **Gateway mount test:**
   ```bash
   # Restart gateway
   systemctl --user restart jib-gateway

   # Check mounts
   docker inspect jib-gateway | jq '.[0].Mounts'

   # Test push from container
   jib
   cd ~/repos/james-in-a-box
   git push origin test-branch
   ```

3. **End-to-end crash recovery test:**
   ```bash
   # Start container with worktree isolation
   jib

   # From another terminal, kill container
   docker kill jib-main

   # Check for backup files
   ls ~/.git-admin/*/*.host-backup

   # Run cleanup
   ~/repos/james-in-a-box/host-services/utilities/worktree-cleanup/jib-cleanup-worktree.py

   # Verify git works
   cd ~/khan/james-in-a-box
   git status
   ```

---

## Files to Create/Modify

### New Files

| File | Description |
|------|-------------|
| `host-services/utilities/worktree-cleanup/jib-cleanup-worktree.py` | Main cleanup script |
| `host-services/utilities/worktree-cleanup/jib-cleanup-worktree.service` | Systemd service |
| `host-services/utilities/worktree-cleanup/jib-cleanup-worktree.timer` | Systemd timer |
| `host-services/utilities/worktree-cleanup/setup.sh` | Installation script |
| `host-services/utilities/worktree-cleanup/README.md` | Documentation |

### Modified Files

| File | Change |
|------|--------|
| `gateway-sidecar/start-gateway.sh` | Add `.git-admin` and `.git-common` mounts |
| `docs/issues/git-worktree-container-path-leakage.md` | Update status to "Fixed" |

---

## Rollback Plan

If issues arise:

1. **Cleanup script:** Remove systemd timer/service, delete utility directory
2. **Gateway mounts:** Remove the two new mount blocks from `start-gateway.sh`, restart gateway

Both changes are additive and don't modify existing behavior - they only add new functionality.

---

## Future Improvements (Not in Scope)

- **Fix 4: Relative paths** - Use relative paths in `commondir` to eliminate path translation entirely. More complex, requires changes to `entrypoint.py:setup_worktrees()`.

---

Authored-by: jib
