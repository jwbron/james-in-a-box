# ADR: Configuration Directory Consolidation

**Status**: In Progress
**Date**: 2026-01-23
**Author**: jib

## Context

jib currently has configuration scattered across multiple directories under `~/`:

| Directory | Purpose | Status |
|-----------|---------|--------|
| `~/.config/jib/` | Host-side config (secrets, settings, repos) | **Primary** - keep |
| `~/.jib/` | Docker staging directory | **Unclear** - audit needed |
| `~/.jib-sharing/` | Host-container shared data | **Runtime** - keep |
| `~/.jib-worktrees/` | Git worktrees for isolated development | **Runtime** - keep |
| `~/.config/jib-notifier/` | Legacy Slack notifier config | **Legacy** - migrate |
| `~/.config/context-sync/` | Legacy context-sync config | **Legacy** - migrate |

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

### 2. `~/.jib/` (Consolidate)

Referenced in `jib-container/jib` as `CONFIG_DIR = Path.home() / ".jib"` (line 237).

Used for:
- Docker staging during container builds
- Potentially overlaps with `~/.config/jib/` purpose

**Recommendation**:
- Audit usage in `jib` script
- Either rename to `~/.jib-docker-staging/` for clarity
- Or consolidate into `~/.config/jib/docker-staging/`

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

### 5. `~/.config/jib-notifier/` (Migrate)

Legacy directory from before config consolidation. May contain:
- `config.json` - Old Slack token config

**Recommendation**:
- Migration already exists in `config/host_config.py --migrate`
- Add deprecation warning when accessed
- Remove after transition period

### 6. `~/.config/context-sync/` (Migrate)

Legacy directory. May contain:
- `.env` - Old Confluence/JIRA credentials

**Recommendation**:
- Migration already exists in `config/host_config.py --migrate`
- Add deprecation warning when accessed
- Remove after transition period

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

#### Phase 3: Add Migration Warnings

1. Add deprecation warnings when legacy configs are detected
2. Prompt users to run migration
3. Set removal timeline (e.g., 3 months)

#### Phase 4: Clean Up

1. Remove legacy config loading paths
2. Update setup.py to only create consolidated structure
3. Remove references to legacy directories

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
- [ ] `config/host_config.py` - Remove legacy fallbacks, add deprecation warnings
- [ ] `setup.py` - Ensure only consolidated structure is created

### Priority 2 (Documentation)
- [ ] `config/README.md` - Document final structure
- [x] `docs/setup/README.md` - Update setup instructions
- [x] `README.md` - Update config locations table

### Priority 3 (Services)
- [ ] `host-services/slack/slack-notifier/` - Verify uses consolidated config
- [ ] `host-services/slack/slack-receiver/` - Verify uses consolidated config
- [ ] `host-services/utilities/github-token-refresher/` - Update token location docs

## Migration Path

For existing installations:

```bash
# 1. Run config migration script (already exists for legacy configs)
python3 config/host_config.py --migrate

# 2. Verify new config location
ls -la ~/.config/jib/

# 3. Test services work
./setup.py --status

# 4. (Optional) Remove legacy configs after verification
rm -rf ~/.config/jib-notifier ~/.config/context-sync
```

**Note on migration script scope:**
- `config/host_config.py --migrate` currently handles legacy directories (`~/.config/jib-notifier/`, `~/.config/context-sync/`)
- The `~/.jib/` → `~/.cache/jib/` migration will be added to the `jib` script itself (Phase 1), since it's the component that uses this directory
- The `jib` script will auto-migrate on first run after the update

## Backward Compatibility

- Legacy paths will continue to work for 3 months
- Deprecation warnings will be logged
- Migration script handles all formats

## Consequences

### Positive
- Single location for all config (`~/.config/jib/`)
- XDG-compliant directory structure
- Clear separation: config vs runtime vs staging
- Simpler troubleshooting

### Negative
- Users need to run migration
- Brief transition period with dual support

## Related

- PR #523 - Configuration Modernization Framework
- `config/host_config.py` - Existing migration code
- `setup.py` - Setup script that creates config structure
