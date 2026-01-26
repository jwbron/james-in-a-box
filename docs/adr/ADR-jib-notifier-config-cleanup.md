# ADR: Complete jib-notifier Config Directory Cleanup

## Status

Proposed

## Context

PR #549 ("Implement config directory consolidation") migrated the main jib configuration directories to XDG compliance:
- `~/.jib/` → `~/.cache/jib/`
- New unified config at `~/.config/jib/config.yaml` and `~/.config/jib/secrets.env`

However, references to the legacy `~/.config/jib-notifier/` directory were not fully cleaned up. This causes a confusing warning at startup:

```
! Configuration file not found: /home/user/.config/jib-notifier/config.json
```

## Analysis

### Current State

The Slack services (slack-notifier.py, slack-receiver.py) have **already been migrated** to use the unified config framework:

1. **Config loading**: Both use `SlackConfig.from_env()` which reads from environment variables and `~/.config/jib/secrets.env`
2. **Service config**: Both use `_load_service_config()` which loads from `~/.config/jib/config.yaml`

The old `jib-notifier/config.json` is **never read** by any code.

### Dead Code Identified

| File | Dead Code | Notes |
|------|-----------|-------|
| `slack-notifier.py` | `config_dir`, `config_file`, `state_file`, `_save_config()` | Directory created but never used for config |
| `slack-receiver.py` | `config_dir`, `config_file`, `_save_config()` | Same pattern |
| `host_command_handler.py` | `~/.config/jib-notifier/remote-control.log` path | Should use `~/.config/jib/` |
| `jib-container/jib` | Check for `jib-notifier/config.json` at line 591 | Causes the startup warning |

### Outdated Documentation

| File | Issue |
|------|-------|
| `docs/development/STRUCTURE.md` | Lines 149-150 reference `~/.config/jib-notifier/config.json` |
| `slack-notifier.service` | Comment references old config path |

### Migration Logic to Keep

`setup.py` contains migration logic from `jib-notifier/config.json` → `~/.config/jib/`. This should be **kept** for users who may still have legacy configs from before PR #549.

## Decision

Complete the cleanup started in PR #549 by:

1. **Remove dead code** from slack-notifier.py and slack-receiver.py
2. **Update jib startup check** to check for `~/.config/jib/config.yaml` instead
3. **Update host_command_handler.py** log path to use `~/.config/jib/`
4. **Update documentation** in STRUCTURE.md and slack-notifier.service
5. **Keep migration logic** in setup.py (for backwards compatibility)

## Consequences

### Positive
- No more confusing startup warning
- Cleaner codebase with no dead code
- Documentation matches actual behavior
- Consistent config directory usage (`~/.config/jib/`)

### Negative
- None significant

### Risks
- Users with existing `~/.config/jib-notifier/` directories may wonder what to do
  - Mitigation: setup.py migration still works; users can run `python setup.py --migrate`

## Implementation

See PR that accompanies this ADR for the specific changes.
