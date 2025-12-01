# Feature Analyzer

Automated feature detection and documentation sync workflow.

## Overview

The Feature Analyzer implements [ADR-Feature-Analyzer-Documentation-Sync](../../../docs/adr/in-progress/ADR-Feature-Analyzer-Documentation-Sync.md) in progressive phases:

- **Phase 1 (MVP)**: Manual CLI tool for syncing documentation with implemented ADRs
- **Phase 2**: Automated ADR detection via systemd polling (15-minute interval)
- **Phase 3**: Multi-document batch updates with LLM generation and PR creation
- **Phase 4**: Enhanced validation, traceability metadata, git tagging, and rollback tooling
- **Phase 5**: Weekly code analysis for FEATURES.md updates
- **Phase 6**: Full repository analysis for comprehensive FEATURES.md generation

## Current Status: Phase 6 (Full Repository Analysis)

Phase 6 adds the ability to analyze an entire repository from scratch and generate a comprehensive FEATURES.md document, similar to what was created in PR #259.

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

### Phase 4 Capabilities (Enhanced Validation & Rollback)

1. **Full validation suite (6 checks)**:
   - Non-destructive (document length doesn't shrink >50%)
   - Major sections preserved (## headers maintained)
   - Link preservation (links not accidentally removed)
   - Diff bounds (max 40% of doc changed)
   - Structure preservation (document hierarchy maintained)
   - Traceability (new claims traceable to ADR)
2. **HTML comment metadata injection** - Adds `<!-- Auto-updated from ADR-XYZ on YYYY-MM-DD -->` for filtering
3. **Git tagging** - Creates `auto-doc-sync-YYYYMMDD` tags for audit trail
4. **Rollback tooling** - CLI commands to find and revert auto-generated changes

### Phase 5 Capabilities (Weekly Code Analysis)

1. **Git commit analysis** - Scans commits from past 7 days
2. **Feature extraction** - Uses LLM to identify new features from code diffs
3. **Heuristic detection** - Fallback detection for CLI tools, services, and major classes
4. **Confidence scoring** - Each feature gets a 0.0-1.0 confidence score
5. **Duplicate detection** - Skips features already in FEATURES.md
6. **FEATURES.md updates** - Adds new entries with proper formatting
7. **Weekly systemd timer** - Runs automatically on Monday mornings

### Phase 6 Capabilities (Full Repository Analysis)

1. **Deep recursive scanning** - Recursively scans ALL directories to find features (unbounded depth)
2. **Smart feature detection** - Identifies feature directories using README presence, source files, and structure
3. **Generous file analysis** - Reads up to 15 files per directory with 1000-line limits for thorough extraction
4. **LLM-powered feature detection** - Uses Claude to identify and describe ALL features comprehensively
5. **Category organization** - Organizes features into standard categories
6. **Documentation linking** - Links features to existing README files
7. **Comprehensive FEATURES.md generation** - Creates complete feature list from scratch
8. **Conservative deduplication** - Only removes TRUE duplicates, preserves related but distinct features

**Key improvements (v2):**
- Scans nested directories recursively (e.g., `host-services/analysis/adr-researcher/`)
- Includes `.claude/commands/`, `jib-tasks/`, `jib-tools/` for complete coverage
- Reads more files per directory (15 vs 5) for better LLM context
- Inclusive prompting - Claude is encouraged to find ALL features, not filter conservatively

## Installation

```bash
# From host machine
cd ~/khan/james-in-a-box/host-services/analysis/feature-analyzer
./setup.sh
```

This installs:
- `~/.local/bin/feature-analyzer` - Manual CLI tool (Phase 1-5)
- `~/.local/bin/adr-watcher` - Automated watcher CLI (Phase 2)
- `feature-analyzer-watcher.timer` - Systemd timer for ADR detection (every 15 min)
- `feature-analyzer-watcher.service` - Systemd service for ADR watcher
- `feature-analyzer-weekly.timer` - Systemd timer for weekly analysis (Mondays 11am)
- `feature-analyzer-weekly.service` - Systemd service for weekly analysis

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

### Phase 4: Rollback Utilities

#### List Auto-Generated Content

```bash
# List auto-generated commits
feature-analyzer rollback list-commits
feature-analyzer rollback list-commits --since "1 week ago"
feature-analyzer rollback list-commits --adr "ADR-Feature-Analyzer"

# List files with auto-generated metadata
feature-analyzer rollback list-files

# List auto-doc-sync tags
feature-analyzer rollback list-tags

# Use --repo-root if not in repo directory
feature-analyzer rollback --repo-root /path/to/repo list-commits
```

#### Revert Auto-Generated Changes

```bash
# Revert a single file to before last auto-generated change
feature-analyzer rollback revert-file docs/README.md

# Revert to a specific commit
feature-analyzer rollback revert-file docs/README.md --to abc1234

# Revert all changes from a specific ADR
feature-analyzer rollback revert-adr ADR-Feature-Analyzer
```

#### Query Auto-Generated Content (Git Commands)

```bash
# Find all auto-generated commits
git log --grep="auto-generated" --oneline

# Find commits for a specific ADR
git log --grep="ADR-Feature-Analyzer" --grep="auto-generated"

# Show all auto-doc-sync tags
git tag -l "auto-doc-sync-*"

# Find files with metadata comments
grep -r "Auto-updated from" docs/
```

### Phase 4 Options for Generate Command

```bash
# Skip HTML metadata injection
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --no-metadata

# Skip git tag creation
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --no-tag

# Combine options
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md --no-metadata --no-tag
```

## Validation Checks

The validator ensures auto-generated updates meet quality standards (Phase 4 Full Suite):

1. **Non-destructive**: Document length doesn't shrink >50%
2. **Major sections preserved**: ## level headers maintained
3. **Link preservation**: Links not accidentally removed (>70% retained)
4. **Diff bounds**: Changes within 40% threshold
5. **Structure preservation**: Document hierarchy maintained (no orphaned headings)
6. **Traceability**: New content relates to ADR (common terms required)

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

### Phase 5: Weekly Code Analysis

#### Run Weekly Analysis Manually

```bash
# Dry-run (show what would be done)
feature-analyzer weekly-analyze --dry-run

# Run analysis with LLM extraction
feature-analyzer weekly-analyze

# Run without LLM (heuristics only)
feature-analyzer weekly-analyze --no-llm

# Update FEATURES.md but don't create PR
feature-analyzer weekly-analyze --no-pr

# Analyze more or fewer days
feature-analyzer weekly-analyze --days 14
```

#### Weekly Timer Management

```bash
# Check timer status
systemctl --user status feature-analyzer-weekly.timer

# View next scheduled run
systemctl --user list-timers feature-analyzer-weekly.timer

# Run manually (same as timer does)
systemctl --user start feature-analyzer-weekly.service

# View logs
journalctl --user -u feature-analyzer-weekly.service -n 50

# Disable weekly analysis
systemctl --user stop feature-analyzer-weekly.timer
systemctl --user disable feature-analyzer-weekly.timer
```

#### Feature Detection Heuristics

The analyzer identifies features using:

1. **LLM Analysis** (primary): Analyzes commit diffs to identify new capabilities
2. **Heuristic Fallback**: Detects patterns like:
   - New files in `host-services/` with `main()` function
   - New CLI tools with `argparse.ArgumentParser`
   - New systemd services
   - New Python classes >50 LOC

#### Confidence Scoring

- **0.7+**: High confidence, auto-added to FEATURES.md
- **0.3-0.7**: Added with "⚠️ Needs Review" flag
- **<0.3**: Skipped (likely not a user-facing feature)

### Phase 6: Full Repository Analysis

The `full-repo` command analyzes an entire repository from scratch to generate a comprehensive FEATURES.md document. This is useful for:
- Initial feature list generation for new repositories
- Regenerating feature lists after major refactors
- Auditing existing features against actual code

#### Run Full Repository Analysis

```bash
# Dry-run (preview what would be generated)
feature-analyzer full-repo --dry-run

# Generate comprehensive FEATURES.md
feature-analyzer full-repo

# Generate without LLM (heuristics only, faster but less accurate)
feature-analyzer full-repo --no-llm

# Generate FEATURES.md but don't create PR
feature-analyzer full-repo --no-pr

# Custom output path
feature-analyzer full-repo --output /path/to/output.md

# Analyze a different repository
feature-analyzer full-repo --repo-root /path/to/repo
```

#### How It Works

1. **Directory Scanning**: Scans `host-services/`, `jib-container/`, `.claude/commands/`, `scripts/`, and `bin/` directories
2. **File Analysis**: Reads Python and shell scripts in each directory
3. **LLM Extraction**: Uses Claude to identify features from code content and READMEs
4. **Categorization**: Organizes features into standard categories (Core Architecture, Communication, etc.)
5. **Deduplication**: Removes duplicate features based on name similarity and file overlap
6. **Generation**: Creates formatted FEATURES.md with table of contents

#### Output Format

The generated FEATURES.md includes:
- Table of contents with category links
- Numbered features organized by category
- Feature name, location (file paths), and description
- Links to existing documentation (README files)
- "Needs review" flags for low-confidence detections
- Maintenance instructions

## Architecture

```
feature-analyzer/
├── feature-analyzer.py                  # Main CLI tool (Phase 1-6)
├── adr_watcher.py                       # Automated watcher (Phase 2-3)
├── doc_generator.py                     # LLM-powered doc generation (Phase 3-4)
├── pr_creator.py                        # Automated PR creation (Phase 3-6)
├── rollback.py                          # Rollback utilities (Phase 4)
├── weekly_analyzer.py                   # Weekly + full repo analysis (Phase 5-6)
│   ├── WeeklyAnalyzer                   # Commit-based weekly analysis
│   └── RepoAnalyzer                     # Full repository analysis
├── feature-analyzer-watcher.service     # Systemd service - ADR watcher (Phase 2)
├── feature-analyzer-watcher.timer       # Systemd timer - 15 min (Phase 2)
├── feature-analyzer-weekly.service      # Systemd service - weekly analysis (Phase 5)
├── feature-analyzer-weekly.timer        # Systemd timer - Mondays 11am (Phase 5)
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
