# ADR: Jib Repository Onboarding Strategy

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming), jib
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** In Progress (Implementation Started December 2025)

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Implementation Details](#implementation-details)
- [Implementation Status](#implementation-status)
- [Onboarding Workflow](#onboarding-workflow)
- [Feature Analysis & Documentation](#feature-analysis--documentation)
- [Index Generation](#index-generation)
- [Auto-Regeneration](#auto-regeneration)
- [PR Workflow](#pr-workflow)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Open Questions](#open-questions)
- [Research-Backed Enhancements](#research-backed-enhancements)
- [References](#references)

## Context

### Background

**Problem Statement:**

When jib (the LLM agent running in jib-container) works on a repository, it needs to understand that repository's structure, patterns, and conventions. Currently:

1. **No Standardized Onboarding:** Each repo requires manual context-gathering by jib
2. **No Persistent Indexes:** Jib re-analyzes the codebase each session
3. **No Documentation Infrastructure:** Many repos lack LLM-friendly documentation
4. **Context Scattered:** Relevant documentation may be spread across files without clear navigation

**Relationship to LLM Documentation ADR:**

The [LLM Documentation Index Strategy ADR](../implemented/ADR-LLM-Documentation-Index-Strategy.md) established patterns for documentation indexes within the james-in-a-box repository. This ADR extends those patterns to **any repository** jib works on.

**Relationship to Feature Analyzer Documentation Sync ADR:**

The [Feature Analyzer Documentation Sync ADR](../implemented/ADR-Feature-Analyzer-Documentation-Sync.md) establishes the feature-analyzer component and its documentation sync workflows. This ADR leverages those capabilities for onboarding external repositories.

**Relationship to Context Sync Strategy:**

The Confluence Documentation Discovery feature (Section 0 below) relies on pre-synced Confluence data at `~/context-sync/confluence/`. This aligns with the organization's context sync strategy where Confluence is bulk-synced (custom sync) while GitHub and JIRA use MCP for on-demand access.

| ADR | Scope | Focus |
|-----|-------|-------|
| [LLM Documentation Index Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md) | james-in-a-box | Self-documentation of jib infrastructure |
| [Feature Analyzer Documentation Sync](../implemented/ADR-Feature-Analyzer-Documentation-Sync.md) | james-in-a-box | Feature detection and documentation sync workflows |
| **This ADR** | Any target repo | Onboarding jib to external repositories |

### Core Tooling

This ADR leverages tools from the `host-services/analysis/` directory:

| Tool | Location | Purpose | Status |
|------|----------|---------|--------|
| **feature-analyzer** | `host-services/analysis/feature-analyzer/` | Discovers features, generates `FEATURES.md` | ✅ Existing |
| **doc-generator** | `host-services/analysis/doc-generator/` | Generates documentation, detects drift | ✅ Existing |
| **index-generator** | `host-services/analysis/index-generator/` | Creates `codebase.json`, `patterns.json`, `dependencies.json` | ✅ Existing |
| **confluence-doc-discoverer** | `host-services/analysis/confluence-doc-discoverer/` | Discovers relevant Confluence docs | ✅ **NEW** |
| **repo-onboarding tools** | `host-services/analysis/repo-onboarding/` | Orchestration and index updates | ✅ **NEW** |

## Decision

**Jib will have a standardized onboarding process that generates documentation indexes in target repositories, with auto-regeneration via GitHub Actions and changes proposed through PRs.**

### Core Principles

1. **Indexes Live in Target Repo:** Generated documentation belongs to the repo being analyzed
2. **Onboarding is Explicit:** A deliberate "onboarding" task triggers index generation
3. **Non-Invasive by Default:** Jib proposes changes via PR, doesn't commit directly
4. **Incremental Adoption:** Repos can adopt indexes without other jib infrastructure
5. **Consistent with LLM Doc ADR:** Uses same index formats and patterns

### Approach Summary

| Aspect | Approach |
|--------|----------|
| **Index Location** | `<target-repo>/docs/generated/` (local-only, gitignored) |
| **Feature Docs Location** | `<target-repo>/docs/features/` (checked into git) |
| **Trigger** | Explicit onboarding task or command |
| **Phase 1 Output** | `external-docs.json` (Confluence discovery, local-only) |
| **Phase 2 Output** | `FEATURES.md`, `docs/features/*.md` (feature analysis, checked in) |
| **Phase 3 Output** | `codebase.json`, `patterns.json`, `dependencies.json` (indexes, local-only) |
| **Confluence Discovery** | Auto-scan `~/context-sync/confluence/` for org-specific docs |
| **Feature Discovery** | Auto-analyze codebase for feature-to-source mapping |
| **Delivery** | PR to target repo (for checked-in files only) |
| **Maintenance** | Local regeneration (indexes), GitHub Actions (feature docs drift detection) |

## Implementation Status

### Completed (December 2025)

- [x] **confluence-doc-discoverer** - Scans Confluence sync for relevant docs
  - Location: `host-services/analysis/confluence-doc-discoverer/`
  - Features: keyword matching, category detection, confidence scoring, public repo filtering

- [x] **jib-internal-devtools-setup** - Main orchestration script
  - Location: `host-services/analysis/repo-onboarding/`
  - Orchestrates all 4 phases of onboarding

- [x] **jib-regenerate-indexes** - Quick index regeneration
  - Location: `host-services/analysis/repo-onboarding/`
  - Convenience script for refreshing local indexes

- [x] **docs-index-updater** - Updates docs/index.md
  - Location: `host-services/analysis/repo-onboarding/`
  - Manages jib-specific sections in documentation index

- [x] **GitHub Actions template** - Feature docs drift detection
  - Location: `host-services/analysis/repo-onboarding/templates/`
  - Ready to copy to target repos

- [x] **bin/ symlinks** - All new tools accessible from bin/
  - `confluence-doc-discoverer`, `jib-internal-devtools-setup`, `jib-regenerate-indexes`, `docs-index-updater`

### Pending

- [ ] Integration testing on pilot repos
- [ ] Container bundling (tools available in jib-container)
- [ ] Slack command integration ("onboard jib to repo X")
- [ ] JIRA trigger support

## Implementation Details

### 0. Confluence Documentation Discovery

The `confluence-doc-discoverer` tool scans pre-synced Confluence documentation for relevant docs:

```bash
# Full discovery
confluence-doc-discoverer --repo-name webapp

# Skip for public repos
confluence-doc-discoverer --repo-name public-lib --public-repo

# Custom Confluence directory
confluence-doc-discoverer --repo-name webapp --confluence-dir ~/context-sync/confluence
```

**Output:** `docs/generated/external-docs.json`

```json
{
  "generated": "2025-12-03T12:00:00Z",
  "repo": "webapp",
  "search_terms": ["webapp", "web app"],
  "discovered_docs": [
    {
      "title": "ADR #601: Perseus Decoupling",
      "path": "ENG/ADR...",
      "relevance": "Architectural decision referencing webapp",
      "category": "adr",
      "confidence": 0.8
    }
  ],
  "index_additions": ["| [ADR #601](link) | Description |"]
}
```

### 1. Full Onboarding Workflow

Use `jib-internal-devtools-setup` for complete onboarding:

```bash
# Full onboarding (all phases)
jib-internal-devtools-setup --repo ~/khan/webapp

# Skip Confluence for public repos
jib-internal-devtools-setup --repo ~/khan/public-lib --skip-confluence --public-repo

# Preview without making changes
jib-internal-devtools-setup --repo ~/khan/webapp --dry-run
```

**Phases executed:**
1. Confluence Documentation Discovery
2. Feature Analysis & Documentation (via feature-analyzer)
3. Index Generation (via index-generator)
4. Documentation Index Updates (via docs-index-updater)

### 2. Quick Index Regeneration

For refreshing local indexes after pulling changes:

```bash
# Current directory
jib-regenerate-indexes

# Specific repo
jib-regenerate-indexes ~/khan/webapp
```

### 3. Generated Artifacts

**Directory Structure Created:**

```
<target-repo>/
├── docs/
│   ├── index.md                    # Navigation index (updated)
│   ├── FEATURES.md                 # Feature-to-source mapping
│   ├── features/                   # Feature category docs
│   │   ├── README.md
│   │   └── *.md
│   └── generated/                  # Local-only (gitignored)
│       ├── codebase.json
│       ├── patterns.json
│       ├── dependencies.json
│       └── external-docs.json
└── .github/
    └── workflows/
        └── check-feature-docs.yml  # Optional drift detection
```

### 4. GitHub Actions Workflow

Copy the template to enable drift detection:

```bash
cp ~/khan/james-in-a-box/host-services/analysis/repo-onboarding/templates/check-feature-docs.yml \
   ~/khan/target-repo/.github/workflows/
```

## Onboarding Workflow

### Quick Start

```bash
# 1. Install tools (one-time)
~/khan/james-in-a-box/host-services/analysis/repo-onboarding/setup.sh

# 2. Onboard a repository
jib-internal-devtools-setup --repo ~/khan/target-repo

# 3. After pulling changes, refresh indexes
jib-regenerate-indexes ~/khan/target-repo
```

### Human Review Checklist

After onboarding:
- [ ] Review generated `docs/FEATURES.md`
- [ ] Add `docs/generated/*.json` to `.gitignore`
- [ ] Optionally install GitHub Actions workflow
- [ ] Commit feature documentation if desired

## Migration Strategy

### Phase 1: james-in-a-box (Complete)

- [x] Index generator implemented
- [x] Tests written
- [x] CI workflow added
- [x] Onboarding tools implemented

### Phase 2: Pilot Repos (Current)

1. Test onboarding on 2-3 internal repos
2. Gather feedback on generated artifacts
3. Iterate on tools based on feedback

### Phase 3: Automated Onboarding (Future)

1. Add onboarding command to jib
2. Integrate with Slack workflow
3. Add JIRA trigger support

## Consequences

### Benefits

1. **Consistent Understanding:** Jib has structured knowledge of any repo
2. **Faster Context:** Indexes are faster than re-analyzing codebase
3. **Self-Maintaining:** CI ensures indexes stay current
4. **Transferable:** Indexes help any LLM agent, not just jib
5. **Low Friction:** Single command adds all infrastructure

### Drawbacks

1. **PR Overhead:** Repos must accept and maintain new files
2. **CI Time:** Additional CI step for index checking
3. **Python-First:** Other languages need additional work

## Open Questions

### 1. Index Storage Location

**Decision:** `docs/generated/` in target repo (local-only, gitignored)

### 2. Handling Monorepos

**Recommendation:** Per-service indexes in service directories

### 3. Existing Documentation Integration

**Current Approach:** Append jib-managed section to existing `docs/index.md`

### 4. Private/Sensitive Code

**TODO:** Add `.jibignore` or similar exclusion mechanism

## References

### Related ADRs

- [LLM Documentation Index Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md)
- [Feature Analyzer Documentation Sync](../implemented/ADR-Feature-Analyzer-Documentation-Sync.md)

### Core Tooling

| Tool | Purpose | Location |
|------|---------|----------|
| feature-analyzer | Feature discovery | `host-services/analysis/feature-analyzer/` |
| doc-generator | Documentation generation | `host-services/analysis/doc-generator/` |
| index-generator | Codebase indexes | `host-services/analysis/index-generator/` |
| confluence-doc-discoverer | Confluence discovery | `host-services/analysis/confluence-doc-discoverer/` |
| repo-onboarding | Orchestration | `host-services/analysis/repo-onboarding/` |

---

**Last Updated:** 2025-12-03
**Next Review:** 2026-01-03 (Monthly)
**Status:** In Progress - Core tooling implemented, testing pending
