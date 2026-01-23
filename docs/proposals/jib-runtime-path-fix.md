# Proposal: Fix jib Runtime Path References

**Status**: Proposed
**Author**: jib
**Date**: 2026-01-23

## Problem Statement

The jib container has two copies of runtime scripts:

1. **Baked into Docker image**: `/opt/jib-runtime/jib-container/`
   - Copied during `docker build` via `COPY . /opt/jib-runtime/`
   - Added to PATH: `/opt/jib-runtime/jib-container/bin`

2. **Mounted at runtime**: `~/repos/james-in-a-box/jib-container/`
   - Mounted from host filesystem
   - May be out of sync with container image

The container **should** primarily use `/opt/jib-runtime/` for:
- **Consistency**: Scripts match the container image version
- **Independence**: Container works even if `~/repos/james-in-a-box` isn't mounted or is incomplete
- **Security**: Prevents host file modifications from affecting container behavior during a session

However, several components currently reference `~/repos/james-in-a-box/` directly, creating a dependency on the mounted repository.

## Current Issues

### 1. Claude Hooks Hardcode Mounted Repo Path

In `jib-container/entrypoint.py`, the `setup_claude()` function (lines 573-599) creates Claude settings with hardcoded paths:

```python
trace_collector = (
    config.repos_dir / "james-in-a-box/host-services/analysis/trace-collector/hook_handler.py"
)
```

This references `~/repos/james-in-a-box/host-services/...` instead of the baked-in `/opt/jib-runtime/` version.

### 2. Documentation References Mounted Repo

Several files tell users to run scripts via the mounted repo path:

| File | Reference |
|------|-----------|
| `claude-rules/mission.md` | `~/repos/james-in-a-box/docs/index.md` |
| `claude-rules/beads-usage.md` | `~/repos/james-in-a-box/docs/reference/beads.md` |
| `claude-commands/show-metrics.md` | `python3 ~/repos/james-in-a-box/lib/python/jib_monitor.py` |
| `jib-tasks/github/README.md` | `python3 ~/repos/james-in-a-box/jib-container/jib-tasks/...` |

### 3. No Convenience Symlink

There's no `~/jib` symlink providing easy access to runtime scripts. Users and documentation must use either:
- Full path: `/opt/jib-runtime/jib-container/...`
- Mounted path: `~/repos/james-in-a-box/jib-container/...`

## Analysis of Each Category

### Paths That Should Use /opt/jib-runtime/

These are **executable scripts** that should be consistent with the container image:

1. **Claude hooks** (`hook_handler.py`)
   - Critical for tracing and session management
   - Should match container version

2. **Task processors** (`jib-tasks/github/*.py`)
   - Called via `jib --exec`
   - Should use PATH or /opt/jib-runtime

3. **Interactive tools** (`discover-tests`, `analyze-pr`, etc.)
   - Already in PATH via `/opt/jib-runtime/jib-container/bin`

### Paths That Correctly Use Mounted Repo

These are **documentation and generated content** that legitimately live in the mounted repo:

1. **Documentation Index**: `~/repos/james-in-a-box/docs/index.md`
   - This is the navigation hub for docs
   - Lives in the repo, not the container image
   - **Should remain as-is**

2. **Generated Indexes**: `~/repos/james-in-a-box/docs/generated/`
   - Created at container startup
   - Written to mounted repo for persistence
   - **Should remain as-is**

3. **Reference Docs**: `~/repos/james-in-a-box/docs/reference/`
   - Detailed documentation fetched on-demand
   - **Should remain as-is**

## Proposed Solution

### Phase 1: Add ~/jib Convenience Symlink

In `entrypoint.py`, add a setup step:

```python
def setup_jib_symlink(config: Config, logger: Logger) -> None:
    """Create ~/jib symlink to runtime scripts."""
    jib_link = config.user_home / "jib"
    if jib_link.is_symlink():
        jib_link.unlink()
    jib_link.symlink_to(Path("/opt/jib-runtime/jib-container"))
    os.lchown(jib_link, config.runtime_uid, config.runtime_gid)
    logger.success("Runtime symlink created: ~/jib -> /opt/jib-runtime/jib-container")
```

This provides:
- Easy access: `~/jib/bin/`, `~/jib/jib-tasks/`
- Consistent naming across containers
- Clear separation from the mounted repo

### Phase 2: Address Trace-Collector Location

The trace-collector is currently in `host-services/analysis/trace-collector/`, which is **not** copied to `/opt/jib-runtime/`. The Dockerfile only copies `jib-container/` contents.

However, the trace-collector is called FROM Claude Code INSIDE the container via hooks. This is a design inconsistency:

- `host-services/` = services that run on the host
- `jib-container/` = code that runs inside the container
- Trace-collector runs inside the container but lives in `host-services/`

**Options:**

1. **Move trace-collector to jib-container/** (recommended)
   - Move `host-services/analysis/trace-collector/` to `jib-container/trace-collector/`
   - Update Dockerfile to ensure it's included
   - Update entrypoint.py to reference `/opt/jib-runtime/jib-container/trace-collector/`

2. **Copy trace-collector during Docker build**
   - Add `COPY host-services/analysis/trace-collector /opt/jib-runtime/trace-collector`
   - Keeps code in `host-services/` but duplicates in image

3. **Keep using mounted repo path** (current behavior)
   - Works but creates dependency on mounted repo
   - Acceptable if we document this requirement

**Recommendation:** Option 1 - move trace-collector to `jib-container/` since it runs in the container. This requires a separate PR due to the scope.

### Phase 3: Update Documentation (Low Priority)

Update README files and commands to use:
- `~/jib/` for runtime scripts
- PATH commands when available (e.g., `discover-tests` instead of full path)

Documentation paths like `~/repos/james-in-a-box/docs/` should remain unchanged since they reference content in the mounted repo.

## Implementation Plan

1. **Add ~/jib symlink** (immediate)
   - Modify `entrypoint.py`
   - Test container startup

2. **Fix Claude hooks path** (immediate)
   - Update `setup_claude()` to use `/opt/jib-runtime/`
   - Verify trace-collector location

3. **Update task README files** (follow-up PR)
   - Change `python3 ~/repos/james-in-a-box/jib-container/jib-tasks/...` to `python3 ~/jib/jib-tasks/...`
   - Or better: add these to PATH and document the command names

4. **Update claude-commands** (follow-up PR)
   - Change `show-metrics.md` to use correct path

## Implementation Phases

### Immediate (This PR)
1. Add `~/jib` symlink in `entrypoint.py`
2. Document the issue and plan

### Follow-up PR: Move Trace-Collector
1. Move `host-services/analysis/trace-collector/` to `jib-container/trace-collector/`
2. Update `entrypoint.py` to reference `/opt/jib-runtime/jib-container/trace-collector/`
3. Update any other references

### Follow-up PR: Documentation Updates
1. Update `jib-container/jib-tasks/github/README.md` paths to `~/jib/`
2. Update `jib-container/.claude/commands/show-metrics.md` script path

## Files to Modify (This PR)

| File | Change |
|------|--------|
| `jib-container/entrypoint.py` | Add `setup_jib_symlink()` function |
| `docs/proposals/jib-runtime-path-fix.md` | This proposal document |

## Testing

1. Container starts successfully
2. `ls ~/jib/` shows symlink to `/opt/jib-runtime/jib-container`
3. Claude hooks work with updated paths
4. `discover-tests` and other PATH commands work
5. Documentation references are accessible

## Decision

Recommend proceeding with Phase 1 and Phase 2 immediately. Phase 3 can be done in follow-up PRs.

---

Authored-by: jib
