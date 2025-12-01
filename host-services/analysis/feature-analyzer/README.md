# Feature Analyzer

Automated feature detection and documentation sync workflow.

## Overview

The Feature Analyzer implements [ADR-Feature-Analyzer-Documentation-Sync](../../../docs/adr/not-implemented/ADR-Feature-Analyzer-Documentation-Sync.md) in progressive phases:

- **Phase 1 (MVP)**: Manual CLI tool for syncing documentation with implemented ADRs
- **Phase 2**: Automated ADR detection via systemd polling (15-minute interval)
- **Phase 3**: Multi-document batch updates
- **Phase 4**: Enhanced validation and rollback
- **Phase 5**: Weekly code analysis for FEATURES.md updates

## Current Status: Phase 2 (Automated Detection)

Phase 2 adds automated detection of newly implemented ADRs via a systemd timer that runs every 15 minutes.

### Phase 1 Capabilities (Manual CLI)

1. **Parses ADR** - Extracts metadata from ADR file (title, status, decision)
2. **Maps to Docs** - Identifies documentation files that reference the ADR
3. **Validates** - Checks if proposed updates meet quality standards
4. **Reports** - Shows which docs need updating

### Phase 2 Capabilities (Automated Detection)

1. **Monitors implemented/ directory** - Detects ADRs moved to `docs/adr/implemented/`
2. **State persistence** - Tracks which ADRs have been processed across restarts
3. **Auto-triggers sync** - Runs sync analysis for newly detected ADRs
4. **Systemd integration** - Runs as a user service on 15-minute intervals

### What It Does NOT Do (Yet)

- Auto-generate updated documentation content (Phase 3+)
- Create PRs automatically (Phase 3+)
- Analyze code for new features (Phase 5)

## Installation

```bash
# From host machine
cd ~/khan/james-in-a-box/host-services/analysis/feature-analyzer
./setup.sh
```

This installs:
- `~/.local/bin/feature-analyzer` - Manual CLI tool (Phase 1)
- `~/.local/bin/adr-watcher` - Automated watcher CLI (Phase 2)
- `feature-analyzer-watcher.timer` - Systemd timer (every 15 min)
- `feature-analyzer-watcher.service` - Systemd service

## Usage

### Phase 1: Manual CLI

#### Validate Documentation for an ADR

Check which documents would be affected without making changes:

```bash
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --validate-only
```

#### Dry Run (Show Proposed Updates)

See what would be updated:

```bash
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --dry-run
```

### Phase 2: Automated Watcher

#### Check Watcher Status

```bash
# View overall status
adr-watcher status

# Check systemd timer status
systemctl --user status feature-analyzer-watcher.timer

# View recent logs
journalctl --user -u feature-analyzer-watcher.service -n 50
```

#### Manual Watcher Commands

```bash
# Run the watcher manually (same as systemd does)
adr-watcher watch

# Check for new ADRs without processing
adr-watcher check

# Reset state to reprocess all ADRs
adr-watcher reset

# Dry-run mode (detect but don't update state)
adr-watcher watch --dry-run
```

#### Systemd Commands

```bash
# Start the timer
systemctl --user start feature-analyzer-watcher.timer

# Stop the timer
systemctl --user stop feature-analyzer-watcher.timer

# Run service manually (without waiting for timer)
systemctl --user start feature-analyzer-watcher.service

# View live logs
journalctl --user -u feature-analyzer-watcher.service -f
```

## Validation Checks

The validator ensures auto-generated updates meet quality standards:

1. **Non-destructive**: Document length doesn't shrink >50%
2. **Structure preserved**: Major section headings maintained
3. **Link preservation**: Links not accidentally removed
4. **Diff bounds**: Changes within 40% threshold

## Examples

### Example 1: Check if Documentation Needs Updating (Phase 1)

```bash
$ feature-analyzer sync-docs \
    --adr docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md \
    --validate-only

ADR: ADR: LLM Documentation Index Strategy
Status: implemented
File: docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md

Documents that would be checked: 3
  - docs/index.md
  - README.md
  - docs/setup/README.md

[VALIDATE ONLY] No updates proposed.
```

### Example 2: Check Watcher Status (Phase 2)

```bash
$ adr-watcher status

ADR Watcher Status
========================================
State file: /home/user/.local/share/feature-analyzer/state.json
State exists: True
Last check: 2025-12-01T00:10:00+00:00
Processed ADRs: 3

Processed ADR files:
  - ADR-Context-Sync-Strategy-Custom-vs-MCP.md
  - ADR-LLM-Documentation-Index-Strategy.md
  - ADR-Slack-Integration-Strategy-MCP-vs-Custom.md

Current implemented ADRs: 3
```

### Example 3: Detect New Implemented ADRs (Phase 2)

```bash
$ adr-watcher watch

ADR Watcher starting at 2025-12-01T00:15:00+00:00
Checking: /home/user/khan/james-in-a-box/docs/adr/implemented
Last check: 2025-12-01T00:10:00+00:00

Found 1 new implemented ADR(s):

Processing: ADR-New-Feature.md
  ✓ Sync analysis complete for: docs/adr/implemented/ADR-New-Feature.md
    ADR: New Feature ADR
    Status: implemented
    ...

Processed 1/1 ADR(s)
```

## State Management

The watcher maintains state in `~/.local/share/feature-analyzer/state.json`:

```json
{
  "processed_adrs": [
    "ADR-Context-Sync-Strategy-Custom-vs-MCP.md",
    "ADR-LLM-Documentation-Index-Strategy.md"
  ],
  "last_check_timestamp": "2025-12-01T00:10:00+00:00",
  "version": 1
}
```

This ensures:
- ADRs are only processed once (unless state is reset)
- Processing resumes correctly after restarts
- You can audit which ADRs have been handled

## Future Phases

### Phase 3: Multi-Doc Updates (Weeks 5-6)

- Use LLM to generate updated content
- Batch updates per ADR
- Create PR with all changes

### Phase 4: Enhanced Validation (Weeks 7-8)

- Full validation suite (6 checks)
- HTML comment metadata injection
- Git tagging for traceability
- Rollback documentation

### Phase 5: Weekly Code Analysis (Weeks 9-10)

- Scan merged commits from past week
- Extract new features using LLM
- Update FEATURES.md
- Create PR for review

## Architecture

```
feature-analyzer/
├── feature-analyzer.py                  # Phase 1: Main CLI tool
├── adr_watcher.py                       # Phase 2: Automated watcher
├── feature-analyzer-watcher.service     # Phase 2: Systemd service
├── feature-analyzer-watcher.timer       # Phase 2: Systemd timer (15 min)
├── README.md                            # This file
└── setup.sh                             # Installation script

State files (created at runtime):
~/.local/share/feature-analyzer/
└── state.json                           # Watcher state persistence
```

## Development

### Running Tests

```bash
# From repo root
pytest tests/analysis/test_feature_analyzer.py
```

### Adding New Validation Checks

Edit the `validate_update()` method in `feature-analyzer.py`:

```python
def validate_update(self, current: str, proposed: str) -> tuple[bool, list[str]]:
    errors = []

    # Add new check here
    if some_condition:
        errors.append("Validation error message")

    return (len(errors) == 0, errors)
```

## Troubleshooting

### "ADR not found" error

Ensure the ADR path is relative to the repository root:

```bash
# Correct
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md

# Wrong
feature-analyzer sync-docs --adr ADR-Example.md
```

### No documents identified

The tool only identifies docs that mention the ADR or related concepts. If nothing is found, the ADR may not affect existing documentation.

### Timer not running

Check if the timer is enabled and active:

```bash
systemctl --user status feature-analyzer-watcher.timer

# If not enabled:
systemctl --user enable --now feature-analyzer-watcher.timer
```

### Watcher processing ADRs repeatedly

Check and reset the state if corrupted:

```bash
# View current state
adr-watcher status

# Reset if needed
adr-watcher reset
```

## References

- [ADR-Feature-Analyzer-Documentation-Sync](../../../docs/adr/not-implemented/ADR-Feature-Analyzer-Documentation-Sync.md) - Full ADR
- [FEATURES.md](../../../docs/FEATURES.md) - Feature-to-source mapping
- [docs/index.md](../../../docs/index.md) - Documentation index
- [host-services/README.md](../../README.md) - Systemd service standards
