# Feature Analyzer

Automated feature detection and documentation sync workflow.

## Overview

The Feature Analyzer implements [ADR-Feature-Analyzer-Documentation-Sync](../../../docs/adr/not-implemented/ADR-Feature-Analyzer-Documentation-Sync.md) in progressive phases:

- **Phase 1 (MVP)**: Manual CLI tool for syncing documentation with implemented ADRs
- **Phase 2**: Automated ADR detection via systemd polling
- **Phase 3**: Multi-document batch updates
- **Phase 4**: Enhanced validation and rollback
- **Phase 5**: Weekly code analysis for FEATURES.md updates

## Current Status: Phase 1 (MVP)

The MVP provides a manual CLI tool to identify documentation affected by implemented ADRs.

### What It Does

1. **Parses ADR** - Extracts metadata from ADR file (title, status, decision)
2. **Maps to Docs** - Identifies documentation files that reference the ADR
3. **Validates** - Checks if proposed updates meet quality standards
4. **Reports** - Shows which docs need updating

### What It Does NOT Do (Yet)

- ❌ Auto-generate updated documentation content (Phase 2+)
- ❌ Create PRs automatically (Phase 2+)
- ❌ Run on schedule (Phase 2+)
- ❌ Analyze code for new features (Phase 5)

## Installation

```bash
# From host machine
cd ~/khan/james-in-a-box/host-services/analysis/feature-analyzer
./setup.sh
```

This creates a symlink: `~/.local/bin/feature-analyzer` → `feature-analyzer.py`

## Usage

### Validate Documentation for an ADR

Check which documents would be affected without making changes:

```bash
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --validate-only
```

### Dry Run (Show Proposed Updates)

See what would be updated:

```bash
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md --dry-run
```

### Full Sync (Phase 2+)

Not yet implemented. In future phases:

```bash
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md
# Would generate content, validate, and create PR
```

## Validation Checks

The validator ensures auto-generated updates meet quality standards:

1. **Non-destructive**: Document length doesn't shrink >50%
2. **Structure preserved**: Major section headings maintained
3. **Link preservation**: Links not accidentally removed
4. **Diff bounds**: Changes within 40% threshold

## Examples

### Example 1: Check if Documentation Needs Updating

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

### Example 2: Dry Run with Updates Identified

```bash
$ feature-analyzer sync-docs \
    --adr docs/adr/implemented/ADR-Context-Sync-Strategy.md \
    --dry-run

ADR: Context Sync Strategy
Status: implemented
File: docs/adr/implemented/ADR-Context-Sync-Strategy.md

Documents affected: 2

  CLAUDE.md
    Reason: Mentions ADR-Context-Sync-Strategy.md or related concepts
    Validation: ✓ Passed

  docs/setup/README.md
    Reason: Mentions ADR-Context-Sync-Strategy.md or related concepts
    Validation: ✓ Passed

[DRY RUN] No changes made.
```

## Future Phases

### Phase 2: Automated Detection (Weeks 3-4)

- Systemd timer runs every 15 minutes
- Detects ADRs moved to `implemented/` directory
- Auto-triggers sync for newly implemented ADRs

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
feature-analyzer
├── feature-analyzer.py    # Main CLI tool
├── README.md             # This file
└── setup.sh              # Installation script

Future structure (Phase 2+):
├── doc_mapper.py         # Map ADRs to affected docs
├── doc_updater.py        # Generate updated content via LLM
├── pr_creator.py         # Create PRs with updates
├── validator.py          # Enhanced validation logic
└── weekly_analyzer.py    # Weekly code analysis (Phase 5)
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
# ✓ Correct
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md

# ✗ Wrong
feature-analyzer sync-docs --adr ADR-Example.md
```

### No documents identified

The tool only identifies docs that mention the ADR or related concepts. If nothing is found, the ADR may not affect existing documentation.

## References

- [ADR-Feature-Analyzer-Documentation-Sync](../../../docs/adr/not-implemented/ADR-Feature-Analyzer-Documentation-Sync.md) - Full ADR
- [FEATURES.md](../../../docs/FEATURES.md) - Feature-to-source mapping
- [docs/index.md](../../../docs/index.md) - Documentation index
