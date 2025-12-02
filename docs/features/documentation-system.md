# Documentation System Features

Automated documentation generation, sync, and maintenance.

## Overview

JIB maintains documentation automatically:
- **Feature Analysis**: Tracks features and their source locations
- **Doc Generation**: Creates and updates documentation
- **Drift Detection**: Identifies stale or inconsistent docs

## Features

### Feature Analyzer Service

**Purpose**: Automated feature detection and documentation sync workflow implementing ADR detection, multi-doc updates with LLM generation, PR creation, validation/rollback tooling, and full repository analysis for comprehensive feature lists.

**Location**:
- `host-services/analysis/feature-analyzer/feature-analyzer.py`
- `host-services/analysis/feature-analyzer/adr_watcher.py`
- `host-services/analysis/feature-analyzer/doc_generator.py`

### ADR Researcher Service

**Purpose**: Research-driven ADR workflow tool that researches open ADR PRs, updates merged ADRs with research findings, generates new ADRs grounded in industry research, and validates ADR claims. Runs weekly on Mondays.

**Location**:
- `host-services/analysis/adr-researcher/adr-researcher.py`
- `host-services/analysis/adr-researcher/README.md`
- `host-services/analysis/adr-researcher/setup.sh`
- `host-services/analysis/adr-researcher/adr-researcher.service`
- `host-services/analysis/adr-researcher/adr-researcher.timer`

**Components**:
- **Research Open ADR PRs** (`host-services/analysis/adr-researcher/adr-researcher.py`)
- **ADR Generation from Research** (`host-services/analysis/adr-researcher/adr-researcher.py`)
- **ADR Review and Validation** (`host-services/analysis/adr-researcher/adr-researcher.py`)
- **Topic Research Mode** (`host-services/analysis/adr-researcher/adr-researcher.py`)
- **Structured Research Result Parser** (`host-services/analysis/adr-researcher/adr-researcher.py`)

### ADR Processor

**Purpose**: Container-side dispatcher for ADR research tasks. Receives context from host-side adr-researcher via jib --exec and dispatches to specialized handlers for researching, generating, and reviewing ADRs.

**Location**: `jib-container/jib-tasks/adr/adr-processor.py`

### Documentation Generator Pipeline

**Purpose**: A 4-agent pipeline (Context, Draft, Review, Output) that automatically generates documentation from codebase analysis. Analyzes code patterns from indexes and generates status-quo or pattern documentation.

**Location**:
- `host-services/analysis/doc-generator/doc-generator.py`
- `host-services/analysis/doc-generator/setup.sh`
- `host-services/analysis/doc-generator/doc-generator.service`
- `host-services/analysis/doc-generator/doc-generator.timer`
- `bin/generate-docs`

**Components**:
- **Documentation PR Creation** (`host-services/analysis/doc-generator/setup.sh`)

### Documentation Drift Detector

**Purpose**: Compares documentation against current code to find discrepancies such as references to deleted files, stale line references, broken markdown links, and outdated paths. Provides suggestions for fixes.

**Location**:
- `host-services/analysis/doc-generator/drift-detector.py`
- `bin/check-doc-drift`

### Codebase Index Generator

**Purpose**: Analyzes Python codebases to generate machine-readable JSON indexes (codebase.json, patterns.json, dependencies.json) for efficient LLM navigation without loading entire files into context.

**Location**:
- `host-services/analysis/index-generator/index-generator.py`
- `host-services/analysis/index-generator/setup.sh`
- `host-services/analysis/index-generator/index-generator.service`
- `host-services/analysis/index-generator/index-generator.timer`

### Spec Enricher CLI

**Purpose**: Command-line tool that enriches task specifications with relevant documentation links and code examples. Accepts specs from files or stdin and outputs in multiple formats (YAML, JSON, Markdown).

**Location**:
- `host-services/analysis/spec-enricher/spec-enricher.py`
- `host-services/analysis/spec-enricher/setup.sh`

### Documentation Link Fixer

**Purpose**: Automatically fixes broken links in documentation files by updating links to moved files, removing references to deleted files, and fixing relative path issues.

**Location**: `scripts/fix-doc-links.py`

### Confluence Documentation Watcher

**Purpose**: Monitors Confluence documentation for changes focusing on ADRs and Runbooks. Uses Claude to analyze content and impact, creates tracking tasks in Beads, and sends notifications.

**Location**: `jib-container/jib-tasks/confluence/confluence-processor.py`

### Documentation Index

**Purpose**: Central navigation hub for all james-in-a-box documentation following the llms.txt standard for efficient LLM navigation.

**Location**: `docs/index.md`

## Related Documentation

- [Documentation Index Strategy](../index.md)

## Source Files

| Component | Path |
|-----------|------|
| Feature Analyzer Service | `host-services/analysis/feature-analyzer/feature-analyzer.py` |
| ADR Researcher Service | `host-services/analysis/adr-researcher/adr-researcher.py` |
| ADR Processor | `jib-container/jib-tasks/adr/adr-processor.py` |
| Documentation Generator Pipeline | `host-services/analysis/doc-generator/doc-generator.py` |
| Documentation Drift Detector | `host-services/analysis/doc-generator/drift-detector.py` |
| Codebase Index Generator | `host-services/analysis/index-generator/index-generator.py` |
| Spec Enricher CLI | `host-services/analysis/spec-enricher/spec-enricher.py` |
| Documentation Link Fixer | `scripts/fix-doc-links.py` |
| Confluence Documentation Watcher | `jib-container/jib-tasks/confluence/confluence-processor.py` |
| Documentation Index | `docs/index.md` |

---

*Auto-generated by Feature Analyzer*
