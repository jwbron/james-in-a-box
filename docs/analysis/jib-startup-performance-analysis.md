# Jib Startup Performance Analysis

**Date**: 2026-01-24
**Status**: Analysis Complete - Recommendations Pending Implementation

## Executive Summary

Container startup takes ~98 seconds total, with 70 seconds (72%) consumed by Docker overhead before the entrypoint even runs. This is caused primarily by SELinux relabeling of mounted volumes.

## Timing Breakdown

From actual timing data:

```
============================================================
STARTUP TIMING SUMMARY
============================================================
Phase                                     Time (ms)      %
------------------------------------------------------------
HOST:
  check_image                                   9.5   0.0%
  build_image                               25138.8  25.7% █████
  start_gateway                                 9.2   0.0%
  create_worktrees                           1704.6   1.7%
  configure_mounts                              0.7   0.0%
  cleanup_old_container                        13.0   0.0%
  build_docker_cmd                              1.8   0.0%
  (host total)                              26969.8

DOCKER:
  container_startup                         70161.7  71.8% ██████████████

CONTAINER:
  python_init                                  14.8   2.4%
  setup_user                                    0.8   0.1%
  setup_git                                    71.4  11.8% ██
  setup_sharing                                64.1  10.5% ██
  setup_claude                                 50.0   8.2% █
  setup_beads                                 399.7  65.8% █████████████
  (container total)                           607.7
------------------------------------------------------------
GRAND TOTAL                                 97739.2
============================================================
```

## Root Cause Analysis

### 1. Container Startup: 70 seconds (PRIMARY BOTTLENECK)

**What it measures**: Time between `docker run` command and Python entrypoint starting.

**Root cause**: SELinux relabeling via the `:z` mount option.

All volume mounts in `jib-container/jib` use `:rw,z`:

```python
# jib:2132
mount_args.extend(["-v", f"{worktree_path}:{container_path}:rw,z"])
```

The `:z` flag tells Docker to relabel mounted content with a shared SELinux label (`svirt_sandbox_file_t`). This requires Docker to:

1. Traverse every file in the mounted directory
2. Call `chcon` on each file to change SELinux context
3. Wait for all relabeling to complete before starting the container

For large git repositories with thousands of files, this is extremely slow.

**Evidence**: The host runs Fedora (`Linux 6.17.12-400.asahi.fc41`), which has SELinux enabled by default.

**Mounts affected** (from jib script):
- Worktree mounts for each repository
- Git metadata mounts (`.git` directories)
- Worktree base directory
- Sharing directory
- Claude config directory
- Claude.json file

### 2. Image Build: 25 seconds (25.7%)

**What it measures**: Time for `docker build` command.

**Root cause**: Docker layer cache invalidation or cold cache.

When layers are fully cached, this should be sub-second. The 25-second time suggests:
- Layers are being rebuilt due to cache invalidation
- First run after image changes
- Network fetching of base layers

### 3. Setup Beads: 400ms (66% of container phase)

**What it measures**: Beads initialization in container.

**Operations**:
1. `chown -R` on beads directory (line 1065)
2. `bd sync --import-only` subprocess (line 1076)

```python
# entrypoint.py:1064-1080
chown_recursive(config.beads_dir, config.runtime_uid, config.runtime_gid)
run_cmd(["bd", "sync", "--import-only"], ...)
```

### 4. Create Worktrees: 1.7 seconds

**What it measures**: Git worktree creation on host.

**Root cause**: For each configured repository, the host runs `git worktree add`.

## Recommendations

### High Impact: Disable SELinux Relabeling

**Expected improvement**: 70 seconds → ~2-5 seconds

**Option A: Disable per-container (Recommended)**

Add `--security-opt label=disable` to docker run:

```python
# jib:2211-2216
cmd = [
    "docker", "run",
    "--security-opt", "label=disable",  # NEW
    "--rm",
    "-it",
    ...
]
```

And remove `:z` from mount options:

```python
# Before
mount_args.extend(["-v", f"{worktree_path}:{container_path}:rw,z"])
# After
mount_args.extend(["-v", f"{worktree_path}:{container_path}:rw"])
```

**Trade-off**: Container cannot access files that have restrictive SELinux labels. This is acceptable for jib since it only accesses user-owned files.

**Option B: Use `:Z` instead of `:z`**

The `:Z` option (uppercase) applies a private label rather than shared. This can be faster but prevents sharing mounts between containers.

**Option C: Pre-label directories**

Run once on host for each mounted directory:
```bash
chcon -Rt svirt_sandbox_file_t ~/.jib-worktrees
chcon -Rt svirt_sandbox_file_t ~/.jib-sharing
```

Then remove `:z` from mounts. This requires user setup but preserves SELinux protection.

### Medium Impact: Eliminate Runtime UID/GID Adjustment

**Expected improvement**: Eliminates multiple `chown -R` operations

**Current behavior**: Container runs as root, adjusts jib user's UID/GID to match host, then runs `chown -R` on multiple directories.

**Proposed**: Build image with matching UID/GID or use `--user` flag with proper permissions.

The entrypoint runs these `chown -R` operations:
- `config.user_home` (line 408)
- `config.sharing_dir` (line 656)
- `config.claude_dir` (lines 816-818)
- `config.router_dir` (line 873)
- `config.beads_dir` (line 1065)

### Lower Impact: Async Beads Sync

**Expected improvement**: 200-300ms off critical path

Move `bd sync --import-only` to background after startup completes:

```python
# Start beads sync in background, don't wait
subprocess.Popen(
    ["bd", "sync", "--import-only"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
```

### Lower Impact: Cache Docker Build

Ensure `build_image` only runs when needed:
- Skip build if image exists and is up-to-date
- Use buildkit with better caching

## Implementation Priority

| Priority | Change | Impact | Effort |
|----------|--------|--------|--------|
| 1 | Disable SELinux relabeling | ~65 seconds saved | Low |
| 2 | Cache/skip image build | ~25 seconds saved | Low |
| 3 | Async beads sync | ~300ms saved | Low |
| 4 | Eliminate chown -R | ~100-500ms saved | Medium |

## Files to Modify

1. **`jib-container/jib`**
   - Add `--security-opt label=disable` to docker run command
   - Remove `:z` from all mount options

2. **`jib-container/entrypoint.py`**
   - Make beads sync async (optional)
   - Consider lazy chown (only when UID mismatch)

## Testing Plan

1. Run `jib --time` before changes to capture baseline
2. Apply SELinux fix
3. Run `jib --time` to measure improvement
4. Verify container can still access all mounted files
5. Test on both SELinux-enabled (Fedora) and SELinux-disabled (Ubuntu) systems

## References

- Docker SELinux documentation: https://docs.docker.com/storage/bind-mounts/#configure-the-selinux-label
- Timing instrumentation: `jib-container/jib` lines 41-113, `entrypoint.py` lines 39-163
- Mount configuration: `jib-container/jib` lines 2120-2199
