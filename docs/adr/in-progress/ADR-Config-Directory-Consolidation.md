# ADR: Configuration Directory Consolidation

**Status**: In Progress (Phase 1, 2 & 4 Complete)
**Date**: 2026-01-23
**Author**: jib

## Context

jib currently has configuration scattered across multiple directories under `~/`:

| Directory | Purpose | Status |
|-----------|---------|--------|
| `~/.config/jib/` | Host-side config (secrets, settings, repos) | **Primary** - keep |
| `~/.cache/jib/` | Docker staging directory | **Cache** - migrated from `~/.jib/` |
| `~/.jib-sharing/` | Host-container shared data | **Runtime** - keep |
| `~/.jib-worktrees/` | Git worktrees for isolated development | **Runtime** - keep |
| `~/.config/jib-notifier/` | Legacy Slack notifier config | **Removed** - cleanup manually |
| `~/.config/context-sync/` | Legacy context-sync config | **Removed** - cleanup manually |

This fragmentation causes:
1. Confusion about where to put/find configuration
2. Multiple places to check when debugging
3. Inconsistent migration state across installations

## Audit Results

### 1. `~/.config/jib/` (Keep - Primary Config Location)

This is the **intended consolidated location** per `config/README.md`. Contains:
- `config.yaml` - Non-secret settings
- `secrets.env` - All secrets
- `github-token` - Dedicated GitHub token file
- `repositories.yaml` - Repository access config
- `github-app-*.pem` - GitHub App credentials

**Recommendation**: Keep as-is. This is the target.

### 2. `~/.cache/jib/` (Migrated from `~/.jib/`)

Now referenced in `jib-container/jib` as `CACHE_DIR = XDG_CACHE_HOME / "jib"` (defaults to `~/.cache/jib/`).

Used for:
- Docker staging during container builds
- Temporary/derived files

**Status**: Migration complete. The `jib` script now uses XDG-compliant cache location.

### 3. `~/.jib-sharing/` (Keep - Runtime Data)

Shared volume between host and container. Contains:
- `notifications/` - Outgoing Slack notifications
- `incoming/` - Incoming tasks from Slack
- `responses/` - Task responses
- `context/` - Context data
- `beads/` - Task memory (mapped to `~/beads/` inside container via symlink)
- `logs/` - Application logs
- `container-logs/` - Container log persistence
- `.github-token` - JSON from github-token-refresher

**Recommendation**: Keep at `~/` rather than moving to `~/.local/share/jib/`.

**Rationale for `~/` location**: While XDG spec suggests `$XDG_DATA_HOME` (`~/.local/share/`) for runtime data, we deliberately keep these at `~/` for:
1. **Visibility**: Users frequently inspect `~/sharing/incoming/` and `~/sharing/notifications/` for debugging
2. **Docker volume simplicity**: Shorter paths are easier to mount and reference in container configs
3. **Consistency**: The `jib-` prefix already namespaces these directories clearly
4. **Discoverability**: New users can `ls ~` and immediately see jib-related directories

### 4. `~/.jib-worktrees/` (Keep - Runtime Data)

Git worktree base directory for isolated development.

**Recommendation**: Keep at `~/` for the same visibility/simplicity rationale as `~/.jib-sharing/`.

### 5. `~/.config/jib-notifier/` (Removed)

Legacy directory from before config consolidation. Contained:
- `config.json` - Old Slack token config

**Status**: Migration code removed. Users should manually clean up if present.

### 6. `~/.config/context-sync/` (Removed)

Legacy directory. Contained:
- `.env` - Old Confluence/JIRA credentials

**Status**: Migration code removed. Users should manually clean up if present.

## Decision

### Consolidation Plan

#### Phase 1: Migrate `~/.jib/` to `~/.cache/jib/`

Based on the audit above, `~/.jib/` is used for Docker staging (not configuration).
This phase implements the migration:

1. Update `jib-container/jib` to use `~/.cache/jib/` instead of `~/.jib/`
2. Add migration logic to move existing `~/.jib/` contents to `~/.cache/jib/`
3. Update any other references in the codebase
4. Add backward compatibility: check old location if new doesn't exist (with deprecation warning)

#### Phase 2: Update Documentation

1. Create single source of truth for config locations
2. Document the purpose of each directory
3. Update all references in docs to point to consolidated locations

#### Phase 3: Add Migration Warnings (Skipped)

Skipped - user has migrated. Proceeding directly to cleanup.

#### Phase 4: Clean Up ✓

1. ✓ Remove legacy config loading paths from `jib-container/jib`
2. ✓ Remove migration code from `config/host_config.py`
3. ✓ Remove legacy tests from `tests/jib/test_jib.py`

## Directory Structure After Consolidation

```
~/.config/jib/                    # All persistent configuration
├── config.yaml                   # Non-secret settings
├── secrets.env                   # All secrets (Slack, GitHub, Confluence, JIRA)
├── repositories.yaml             # Repository access config
├── github-token                  # Dedicated GitHub token file
├── github-app-id                 # GitHub App ID
├── github-app-installation-id    # GitHub App Installation ID
└── github-app-private-key.pem    # GitHub App private key

~/.cache/jib/                     # Temporary/staging files (XDG-compliant)
├── docker/                       # Docker build staging
└── temp/                         # Other temporary files

~/.jib-sharing/                   # Runtime shared data (host <-> container)
├── notifications/                # Outgoing notifications
├── incoming/                     # Incoming tasks
├── responses/                    # Task responses
├── context/                      # Saved context
├── beads/                        # Task memory (→ ~/beads/ in container)
├── logs/                         # Application logs
├── container-logs/               # Container log persistence
└── .github-token                 # Auto-refreshed token (JSON)

# Container path mappings:
#   Host ~/.jib-sharing/       → Container ~/sharing/
#   Host ~/.jib-sharing/beads/ → Container ~/beads/ (symlink)
#   Host ~/.jib-worktrees/X/   → Container ~/repos/

~/.jib-worktrees/                 # Git worktrees (runtime)
└── jib-<timestamp>-<pid>/        # Isolated worktree per session
```

## Files to Update

### Priority 1 (Core)
- [x] `jib-container/jib` - Change `CONFIG_DIR` from `~/.jib` to `~/.cache/jib`
- [x] `tests/jib/test_jib.py` - Update tests for new path structure
- [x] `config/host_config.py` - Remove legacy migration code
- [ ] `setup.py` - Ensure only consolidated structure is created

### Priority 2 (Documentation)
- [x] `config/README.md` - Document final structure
- [x] `docs/setup/README.md` - Update setup instructions
- [x] `README.md` - Update config locations table
- [x] `docs/setup/slack-quickstart.md` - Update config references
- [x] `docs/setup/slack-bidirectional.md` - Update config references
- [x] `docs/setup/slack-app-setup.md` - Update config references
- [x] `docs/reference/slack-quick-reference.md` - Update config references
- [x] `docs/architecture/slack-integration.md` - Update config references

### Priority 3 (Services)
- [ ] `host-services/slack/slack-notifier/` - Verify uses consolidated config
- [ ] `host-services/slack/slack-receiver/` - Verify uses consolidated config
- [ ] `host-services/utilities/github-token-refresher/` - Update token location docs

## Migration Path

Migration has been completed. Legacy migration scripts have been removed.

For new installations, configuration should be placed directly in `~/.config/jib/`.

## Backward Compatibility

Legacy support has been removed. The consolidated directory structure is now the only supported configuration.

## Consequences

### Positive
- Single location for all config (`~/.config/jib/`)
- XDG-compliant directory structure
- Clear separation: config vs runtime vs staging
- Simpler troubleshooting
- No legacy code maintenance burden

### Negative
- Existing installations required one-time migration (completed)

## Related

- PR #523 - Configuration Modernization Framework
- PR #549 - This consolidation work
- `config/host_config.py` - Host configuration loader
- `setup.py` - Setup script that creates config structure
