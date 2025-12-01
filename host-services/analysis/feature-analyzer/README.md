# Feature Analyzer

Automated feature detection and documentation sync workflow.

## Overview

The Feature Analyzer implements [ADR-Feature-Analyzer-Documentation-Sync](../../../docs/adr/not-implemented/ADR-Feature-Analyzer-Documentation-Sync.md) in progressive phases:

- **Phase 1 (MVP)**: Manual CLI tool for syncing documentation with implemented ADRs
- **Phase 2**: Automated ADR detection via systemd polling (15-minute interval)
- **Phase 3**: Multi-document batch updates with LLM generation and PR creation
- **Phase 4**: Enhanced validation and rollback
- **Phase 5**: Weekly code analysis for FEATURES.md updates

## Current Status: Phase 3 (Multi-Doc Updates)

Phase 3 adds LLM-powered documentation generation and automated PR creation.

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

### Phase 3 Capabilities (Multi-Doc Updates)

1. **FEATURES.md querying** - Finds related features based on ADR concepts
2. **Concept extraction** - Identifies technologies, components, and terms from ADR
3. **Multi-doc mapping** - Identifies all documentation files affected by an ADR
4. **LLM generation** - Uses jib containers to generate updated documentation (optional)
5. **Batch validation** - Validates each update independently with failure handling
6. **PR creation** - Creates consolidated PR with all documentation changes

### What It Does NOT Do (Yet)

- HTML comment metadata injection (Phase 4)
- Git tagging for traceability (Phase 4)
- Rollback tooling (Phase 4)
- Weekly code analysis for new features (Phase 5)

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

### Phase 3: Multi-Doc Updates with PR Creation

#### Generate and Create PR

```bash
# Generate documentation updates and create PR
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md

# With LLM assistance (requires jib containers)
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --use-jib

# Dry-run mode (show what would be done)
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --dry-run

# Generate updates without creating PR
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --no-pr
```

#### Run Watcher in Phase 3 Mode

```bash
# Process new ADRs with auto-PR creation
adr-watcher watch --phase3

# With LLM-powered generation
adr-watcher watch --phase3 --use-jib

# Dry-run Phase 3
adr-watcher watch --phase3 --dry-run
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

### Phase 4: Enhanced Validation (Future)

- Full validation suite (6 checks)
- HTML comment metadata injection
- Git tagging for traceability
- Rollback documentation

### Phase 5: Weekly Code Analysis (Future)

- Scan merged commits from past week
- Extract new features using LLM
- Update FEATURES.md
- Create PR for review

## Architecture

```
feature-analyzer/
├── feature-analyzer.py                  # Main CLI tool (Phase 1-3)
├── adr_watcher.py                       # Automated watcher (Phase 2-3)
├── doc_generator.py                     # LLM-powered doc generation (Phase 3)
├── pr_creator.py                        # Automated PR creation (Phase 3)
├── feature-analyzer-watcher.service     # Systemd service (Phase 2)
├── feature-analyzer-watcher.timer       # Systemd timer - 15 min (Phase 2)
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
