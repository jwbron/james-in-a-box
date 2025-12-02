# Documentation System Features

Automated documentation generation, sync, and maintenance.

## Overview

JIB maintains comprehensive documentation through automated systems:
- **Feature Analyzer**: Detects and documents features from code
- **ADR Researcher**: Research-driven ADR workflow
- **Doc Generator**: Multi-agent documentation pipeline
- **Drift Detector**: Identifies stale documentation

## Features

### Feature Analyzer Service

**Purpose**: Automated feature detection and FEATURES.md maintenance.

**Location**: `host-services/analysis/feature-analyzer/`

**Helper Scripts**:
```bash
# Setup
./host-services/analysis/feature-analyzer/setup.sh

# Full repository analysis
feature-analyzer full-repo --repo-root ~/khan/james-in-a-box

# Weekly incremental updates
feature-analyzer weekly-analyze --days 7

# ADR-triggered sync
feature-analyzer sync-docs --adr docs/adr/implemented/ADR-Example.md

# Generate with PR
feature-analyzer generate --adr docs/adr/implemented/ADR-Example.md
```

**Service Management**:
```bash
# ADR watcher (15-min interval)
systemctl --user status feature-analyzer-watcher.timer
systemctl --user start feature-analyzer-watcher.timer

# Weekly analysis (Mondays 11am)
systemctl --user status feature-analyzer-weekly.timer
```

**Capabilities by Phase**:
| Phase | Capability |
|-------|------------|
| 1 | Manual CLI, basic validation |
| 2 | Automated ADR detection |
| 3 | Multi-doc updates with PR |
| 4 | Traceability, rollback |
| 5 | Weekly code analysis |
| 6 | Full repository analysis |

**Rollback Commands**:
```bash
# List auto-generated content
feature-analyzer rollback list-commits
feature-analyzer rollback list-files
feature-analyzer rollback list-tags

# Revert changes
feature-analyzer rollback revert-file docs/README.md
feature-analyzer rollback revert-adr ADR-Feature-Analyzer
```

### ADR Researcher Service

**Purpose**: Research-driven ADR workflow tool.

**Location**: `host-services/analysis/adr-researcher/`

**Helper Scripts**:
```bash
# Setup
./host-services/analysis/adr-researcher/setup.sh
# Or via bin:
bin/adr-researcher --help

# Research open ADR PRs
adr-researcher research-prs

# Update merged ADRs with research
adr-researcher update-merged

# Generate new ADR from research
adr-researcher generate --topic "API rate limiting strategies"

# Validate existing ADR claims
adr-researcher validate docs/adr/implemented/ADR-Example.md

# Research any topic
adr-researcher research --topic "microservice authentication"
```

**Service Management**:
```bash
# Weekly timer (Mondays)
systemctl --user status adr-researcher.timer
```

**Workflow**:
1. Identify open ADR PRs
2. Research claims and alternatives
3. Post findings as PR comments
4. Or generate new ADRs from scratch

### Documentation Generator Pipeline

**Purpose**: 4-agent pipeline for auto-generating documentation.

**Location**: `host-services/analysis/doc-generator/`

**Helper Scripts**:
```bash
# Setup
bin/setup-doc-generator
./host-services/analysis/doc-generator/setup.sh

# Generate docs
bin/generate-docs --source src/ --output docs/generated/
```

**Pipeline Agents**:
1. **Context Agent**: Analyzes codebase indexes
2. **Draft Agent**: Generates documentation draft
3. **Review Agent**: Reviews for accuracy
4. **Output Agent**: Formats final output

**Service Management**:
```bash
systemctl --user status doc-generator.timer
```

### Documentation Drift Detector

**Purpose**: Identifies documentation that's out of sync with code.

**Location**: `host-services/analysis/doc-generator/drift-detector.py`

**Helper Scripts**:
```bash
# Check for drift
bin/check-doc-drift

# Detailed report
python host-services/analysis/doc-generator/drift-detector.py --verbose
```

**Detected Issues**:
- References to deleted files
- Stale line number references
- Broken markdown links
- Outdated file paths

### Codebase Index Generator

**Purpose**: Generates machine-readable indexes for LLM navigation.

**Location**: `host-services/analysis/index-generator/`

**Output Files**:
```
docs/generated/
├── codebase.json      # Structured codebase analysis
├── patterns.json      # Extracted code patterns
└── dependencies.json  # Dependency graph
```

**Helper Scripts**:
```bash
# Generate indexes
python host-services/analysis/index-generator/index-generator.py

# Query indexes
python host-services/analysis/index-generator/query-index.py summary
python host-services/analysis/index-generator/query-index.py search "pattern"
```

### Spec Enricher CLI

**Purpose**: Enriches task specs with documentation links and examples.

**Location**: `host-services/analysis/spec-enricher/`

**Usage**:
```bash
# From file
spec-enricher enrich --input spec.yaml --output enriched.yaml

# From stdin
cat spec.yaml | spec-enricher enrich

# Output formats: YAML, JSON, Markdown
spec-enricher enrich --input spec.yaml --format markdown
```

### Documentation Link Fixer

**Purpose**: Automatically fixes broken documentation links.

**Location**: `scripts/fix-doc-links.py`

**Usage**:
```bash
# Dry run
python scripts/fix-doc-links.py --dry-run

# Fix links
python scripts/fix-doc-links.py

# Specific directory
python scripts/fix-doc-links.py --path docs/
```

**Fixes**:
- Links to moved files
- Removed file references
- Relative path issues

### Confluence Documentation Watcher

**Purpose**: Monitors Confluence for changes to ADRs and runbooks.

**Location**: `jib-container/jib-tasks/confluence/confluence-processor.py`

**Monitors**:
- ADR content changes
- Runbook updates
- Team doc modifications

**Actions**:
- Analyzes impact with Claude
- Creates Beads tasks
- Sends notifications

### Documentation Index

**Purpose**: Central navigation hub for all documentation.

**Location**: `docs/index.md`

**Standard**: [llms.txt](https://llmstxt.org/) for LLM-friendly navigation

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Code Changes                              │
└────────────────────────────┬────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Feature    │   │     ADR      │   │    Index     │
│   Analyzer   │   │  Researcher  │   │  Generator   │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ FEATURES.md  │   │  ADR PRs &   │   │ codebase.json│
│ Feature Docs │   │  Research    │   │ patterns.json│
└──────────────┘   └──────────────┘   └──────────────┘
       │                  │                  │
       └───────────────────┼───────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │      docs/index.md   │
              │   (Navigation Hub)   │
              └──────────────────────┘
                          │
                          ▼
              ┌──────────────────────┐
              │    Drift Detector    │
              │    (Validation)      │
              └──────────────────────┘
```

## Troubleshooting

### FEATURES.md not updating

1. Check analyzer timer: `systemctl --user status feature-analyzer-weekly.timer`
2. Manual run: `feature-analyzer full-repo`
3. Check for validation errors in logs

### ADR research not posting

1. Verify GitHub token has comment permissions
2. Check ADR watcher: `adr-watcher status`
3. Ensure ADRs are in correct directory structure

### Index generation failing

1. Check for syntax errors in source
2. Verify file permissions
3. Run with `--verbose` for details

### Drift detector false positives

1. Check if file was intentionally removed
2. Update or remove stale references
3. Run link fixer: `python scripts/fix-doc-links.py`

## Related Documentation

- [ADR: Feature Analyzer Doc Sync](../adr/implemented/ADR-Feature-Analyzer-Documentation-Sync.md)
- [ADR: LLM Documentation Index](../adr/implemented/ADR-LLM-Documentation-Index-Strategy.md)
- [docs/index.md](../index.md)
- [FEATURES.md](../FEATURES.md)

## Source Files

| Component | Path |
|-----------|------|
| Feature Analyzer | `host-services/analysis/feature-analyzer/` |
| ADR Researcher | `host-services/analysis/adr-researcher/` |
| Doc Generator | `host-services/analysis/doc-generator/` |
| Drift Detector | `host-services/analysis/doc-generator/drift-detector.py` |
| Index Generator | `host-services/analysis/index-generator/` |
| Spec Enricher | `host-services/analysis/spec-enricher/` |
| Link Fixer | `scripts/fix-doc-links.py` |
| Confluence Watcher | `jib-container/jib-tasks/confluence/confluence-processor.py` |

---

*Auto-generated by Feature Analyzer*
