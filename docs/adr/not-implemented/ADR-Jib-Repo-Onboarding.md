# ADR: Jib Repository Onboarding Strategy

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Proposed

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Implementation Details](#implementation-details)
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

**Relationship to Context Sync Strategy:**

The Confluence Documentation Discovery feature (Section 0 below) relies on pre-synced Confluence data at `~/context-sync/confluence/`. This aligns with the organization's context sync strategy where Confluence is bulk-synced (custom sync) while GitHub and JIRA use MCP for on-demand access. Understanding this context helps explain why Confluence docs are pre-synced rather than fetched on-demand.

**Future Enhancement - Model-Agnostic Architecture:**

Index generation could leverage different LLM providers for different tasks - for example, using cost-effective models for initial codebase scanning and more capable models for pattern detection and semantic description generation (see Research-Backed Enhancement #4).

| ADR | Scope | Focus |
|-----|-------|-------|
| LLM Documentation Index Strategy | james-in-a-box | Self-documentation of jib infrastructure |
| **This ADR** | Any target repo | Onboarding jib to external repositories |

### What We're Deciding

This ADR establishes:

1. **Onboarding Process:** How jib analyzes and documents a new repository
2. **Index Location:** Where generated indexes live (in the target repo)
3. **Auto-Regeneration:** How indexes stay current with code changes
4. **PR Workflow:** How jib proposes documentation infrastructure to repos

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
| **Index Location** | `<target-repo>/docs/generated/` |
| **Feature Docs Location** | `<target-repo>/docs/features/` |
| **Trigger** | Explicit onboarding task or command |
| **Phase 1 Output** | `external-docs.json` (Confluence discovery) |
| **Phase 2 Output** | `FEATURES.md`, `docs/features/*.md` (feature analysis) |
| **Phase 3 Output** | `codebase.json`, `patterns.json`, `dependencies.json` (indexes) |
| **Confluence Discovery** | Auto-scan `~/context-sync/confluence/` for org-specific docs |
| **Feature Discovery** | Auto-analyze codebase for feature-to-source mapping |
| **Delivery** | PR to target repo |
| **Maintenance** | GitHub Actions workflow for auto-regeneration |

## Implementation Details

### 0. Confluence Documentation Discovery

Before analyzing the target repository, jib should automatically scan the synced Confluence documentation (`~/context-sync/confluence/`) for org-specific documentation relevant to the target repo. This enables jib to:

1. **Find Related ADRs:** Discover architectural decision records that apply to the target codebase
2. **Locate Runbooks:** Find operational documentation for the repo's services
3. **Surface Best Practices:** Identify org-wide conventions and standards
4. **Map Team Knowledge:** Find team-specific guides and onboarding materials

**Discovery Process:**

```
┌─────────────────────────────────────────────────────────────────┐
│             Confluence Documentation Discovery                   │
│                                                                  │
│  1. Scan ~/context-sync/confluence/ for documentation           │
│  2. Search for repo name, service name, and related keywords    │
│  3. Extract ADRs, runbooks, and guides that reference the repo  │
│  4. Add discovered docs to generated docs/index.md              │
│  5. Create links in docs/generated/external-docs.json           │
└─────────────────────────────────────────────────────────────────┘
```

**Discovery Script:**

The `jib-internal-devtools-setup` script implements this workflow:

```bash
# Full onboarding (includes Confluence discovery)
jib-internal-devtools-setup --repo ~/khan/webapp

# Skip Confluence discovery for external/public repos
jib-internal-devtools-setup --repo ~/khan/public-repo --skip-confluence
```

The script orchestrates:
1. Confluence documentation discovery
2. Feature analysis (FEATURES.md generation)
3. Feature documentation (docs/features/*.md)
4. Codebase index generation (docs/generated/*.json)
5. Documentation index updates

**external-docs.json Schema:**

```json
{
  "generated": "2025-11-28T12:00:00Z",
  "repo": "webapp",
  "discovered_docs": [
    {
      "title": "ADR #601: Loosen coupling between Perseus repo and content-editing service",
      "path": "ENG/ADR #601_ Loosen coupling between the Perseus repo and the content-editing service.md",
      "relevance": "References webapp authentication patterns",
      "category": "adr"
    },
    {
      "title": "Webapp Deployment Runbook",
      "path": "INFRA/Webapp Deployment Runbook.md",
      "relevance": "Deployment procedures for this repository",
      "category": "runbook"
    }
  ],
  "index_additions": [
    "| [ADR #601: Perseus-Content Service Decoupling](../../../context-sync/confluence/ENG/ADR...) | Relevant architectural decision |"
  ]
}
```

**Index Integration:**

When generating `docs/index.md`, the onboarding process appends a new section:

```markdown
## Org-Specific Documentation

*Auto-discovered from Confluence sync. These documents are managed externally.*

| Document | Description |
|----------|-------------|
| [ADR #601: Perseus Decoupling](confluence-link) | Relevant architectural patterns |
| [Webapp Deployment Runbook](confluence-link) | Operational procedures |
```

**Security Consideration - Public Repository Onboarding:**

When onboarding public or external repositories, the `external-docs.json` output should be sanitized to avoid inadvertently exposing organizational information. Discovered docs might include:
- Internal team names
- ADR titles revealing architecture decisions
- Runbook titles revealing operational processes

**Mitigation:** Add a `--public-repo` flag to the discovery script that:
1. Omits Confluence discovery entirely, or
2. Filters results through an allowlist of safe-to-expose document categories
3. Requires explicit review of `external-docs.json` before inclusion in public PRs

This complements Open Question #4 (Private/Sensitive Code) but specifically addresses the Confluence Discovery feature.

### 1. Onboarding Task Structure

Jib onboarding can be triggered by:

1. **Slack command:** "onboard jib to repo X"
2. **JIRA ticket:** Task labeled with "jib-onboarding"
3. **Direct invocation:** Running jib with onboarding flag

**Onboarding Task Flow:**

```
┌─────────────────────────────────────────────────────────────────┐
│                     Jib Onboarding Process                       │
│                                                                  │
│  Phase 1: Context Gathering                                      │
│  1. Clone/access target repository                               │
│  2. Discover org-specific docs from Confluence sync (Step 0)     │
│                                                                  │
│  Phase 2: Feature Discovery & Documentation Generation           │
│  3. Run feature-analyzer full-repo to discover all features      │
│     → Generates docs/FEATURES.md with comprehensive feature list │
│  4. Run feature-analyzer generate-feature-docs                   │
│     → Generates docs/features/*.md category documentation        │
│                                                                  │
│  Phase 3: Index Generation                                       │
│  5. Generate codebase indexes (codebase.json, patterns.json)     │
│  6. Generate dependency graph (dependencies.json)                │
│  7. Generate external-docs.json (from Confluence discovery)      │
│  8. Generate/update navigation index (docs/index.md)             │
│                                                                  │
│  Phase 4: Delivery                                               │
│  9. Generate GitHub Actions workflow for auto-regen              │
│  10. Create PR with all artifacts                                │
│  11. Notify human for review                                     │
└─────────────────────────────────────────────────────────────────┘
```

**Orchestration Script:**

The `jib-internal-devtools-setup` script orchestrates the complete workflow:

```bash
#!/bin/bash
# jib-internal-devtools-setup - Full repository onboarding
#
# Usage:
#   jib-internal-devtools-setup --repo ~/khan/webapp
#   jib-internal-devtools-setup --repo ~/khan/public-repo --skip-confluence

REPO_PATH="$1"
SKIP_CONFLUENCE="${2:-false}"

echo "=== JIB Repository Onboarding ==="
echo "Repository: $REPO_PATH"

# Phase 1: Context Gathering
echo ""
echo "Phase 1: Gathering Confluence context..."
if [ "$SKIP_CONFLUENCE" != "--skip-confluence" ]; then
    python3 ~/tools/confluence-doc-discoverer.py \
        --confluence-dir ~/context-sync/confluence \
        --repo-name "$(basename $REPO_PATH)" \
        --output "$REPO_PATH/docs/generated/external-docs.json"
fi

# Phase 2: Feature Discovery & Documentation
echo ""
echo "Phase 2: Running feature analyzer..."
cd "$REPO_PATH"

# Full repository feature analysis
feature-analyzer full-repo \
    --repo-root "$REPO_PATH" \
    --no-pr

# Generate feature category documentation
feature-analyzer generate-feature-docs \
    --repo-root "$REPO_PATH"

# Phase 3: Index Generation
echo ""
echo "Phase 3: Generating codebase indexes..."
python3 ~/tools/index-generator/index-generator.py \
    --project "$REPO_PATH" \
    --output "$REPO_PATH/docs/generated"

# Update docs/index.md with generated content references
python3 ~/tools/docs-index-updater.py \
    --repo-root "$REPO_PATH" \
    --features-md "$REPO_PATH/docs/FEATURES.md" \
    --generated-dir "$REPO_PATH/docs/generated"

# Phase 4: Delivery
echo ""
echo "Phase 4: Creating PR..."
# (PR creation handled by calling script or jib)

echo ""
echo "=== Onboarding Complete ==="
```

**Generated Artifacts Summary:**

| Phase | Tool | Output |
|-------|------|--------|
| Context | confluence-doc-discoverer | `docs/generated/external-docs.json` |
| Features | feature-analyzer full-repo | `docs/FEATURES.md` |
| Features | feature-analyzer generate-feature-docs | `docs/features/*.md` |
| Indexes | index-generator | `docs/generated/codebase.json`, `patterns.json`, `dependencies.json` |
| Navigation | docs-index-updater | Updated `docs/index.md` |

### 2. Index Generator Deployment

The index generator (`index-generator.py`) from james-in-a-box will be:

1. **Bundled in jib-container:** Available at `/home/jib/tools/index-generator/`
2. **Invocable on any repo:** `python3 ~/tools/index-generator/index-generator.py --project /path/to/repo`
3. **Language-aware:** Initially Python-focused, extensible to other languages

**Usage from within jib-container:**

```bash
# Generate indexes for a target repo
python3 ~/tools/index-generator/index-generator.py \
    --project ~/khan/webapp \
    --output ~/khan/webapp/docs/generated
```

### 3. Generated Artifacts

**Directory Structure Created:**

```
<target-repo>/
├── docs/
│   ├── index.md                    # Navigation index (updated with generated content refs)
│   ├── FEATURES.md                 # Comprehensive feature-to-source mapping
│   ├── features/                   # Feature category documentation
│   │   ├── README.md               # Feature docs navigation
│   │   ├── communication.md        # Communication features
│   │   ├── github-integration.md   # GitHub integration features
│   │   ├── context-management.md   # Context management features
│   │   └── ...                     # Other category docs
│   └── generated/
│       ├── README.md               # Explains generated files
│       ├── codebase.json           # Structured codebase analysis
│       ├── patterns.json           # Detected code patterns
│       ├── dependencies.json       # Dependency graph
│       └── external-docs.json      # Org-specific docs from Confluence
├── .github/
│   └── workflows/
│       └── check-generated-indexes.yml  # Auto-regeneration CI
└── ... (existing repo files)
```

**File Descriptions:**

| File | Purpose | Generator |
|------|---------|-----------|
| `docs/FEATURES.md` | Maps every feature to source code locations | feature-analyzer full-repo |
| `docs/features/*.md` | Detailed docs per feature category | feature-analyzer generate-feature-docs |
| `docs/generated/codebase.json` | AST-parsed structure for LLM queries | index-generator |
| `docs/generated/patterns.json` | Detected architectural patterns | index-generator |
| `docs/generated/dependencies.json` | Import/dependency graph | index-generator |
| `docs/generated/external-docs.json` | Org-specific Confluence docs | confluence-doc-discoverer |

**codebase.json Schema:**

```json
{
  "generated": "2025-11-28T12:00:00Z",
  "generator_version": "1.0.0",
  "project": "webapp",
  "structure": {
    "src/": {
      "description": "Source code",
      "children": { ... }
    }
  },
  "components": [
    {
      "name": "UserController",
      "type": "class",
      "file": "src/controllers/user.py",
      "line": 25,
      "description": "Handles user CRUD operations"
    }
  ],
  "summary": {
    "total_python_files": 150,
    "total_classes": 75,
    "total_functions": 320,
    "patterns_detected": ["mvc", "repository", "decorator"]
  }
}
```

### 4. GitHub Actions Workflow

**Generated `.github/workflows/check-generated-indexes.yml`:**

```yaml
name: Check Generated Indexes

on:
  push:
    branches: [main, master]
    paths:
      - '**/*.py'
      - '**/requirements*.txt'
      - '**/pyproject.toml'
  pull_request:
    branches: [main, master]
    paths:
      - '**/*.py'
      - '**/requirements*.txt'
      - '**/pyproject.toml'

jobs:
  check-indexes:
    name: Verify Generated Indexes
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install index generator
        run: |
          # Download index generator from james-in-a-box (pinned to release tag)
          # SECURITY: Pin to specific version and verify checksum
          GENERATOR_VERSION="v1.0.0"  # Update when new versions are released
          EXPECTED_SHA256="<checksum-to-be-determined>"  # Update with actual checksum

          curl -sL "https://raw.githubusercontent.com/jwbron/james-in-a-box/${GENERATOR_VERSION}/host-services/analysis/index-generator/index-generator.py" \
            -o /tmp/index-generator.py

          # Verify integrity (uncomment when checksum is available)
          # echo "${EXPECTED_SHA256}  /tmp/index-generator.py" | sha256sum -c -

      - name: Regenerate indexes
        run: python3 /tmp/index-generator.py --project . --output docs/generated

      - name: Check for differences
        run: |
          if git diff --exit-code docs/generated/; then
            echo "✅ Generated indexes are up to date"
          else
            echo "❌ Generated indexes are out of date!"
            echo "Run: python3 index-generator.py --project . --output docs/generated"
            exit 1
          fi
```

## Onboarding Workflow

### Step 1: Initial Analysis

```python
# Pseudo-code for onboarding analysis
def analyze_repo(repo_path: Path) -> RepoAnalysis:
    """Analyze target repository for onboarding."""
    return RepoAnalysis(
        has_docs_dir=has_directory(repo_path / "docs"),
        has_existing_index=has_file(repo_path / "docs" / "index.md"),
        has_llms_txt=has_file(repo_path / "llms.txt"),
        has_github_workflows=has_directory(repo_path / ".github" / "workflows"),
        primary_language=detect_primary_language(repo_path),
        existing_documentation=find_documentation_files(repo_path),
    )
```

### Step 2: Generate Artifacts

Based on analysis, generate appropriate artifacts:

| Condition | Action |
|-----------|--------|
| No `docs/` directory | Create `docs/` with full structure |
| Has `docs/` but no `index.md` | Add `index.md` navigation |
| Has `docs/index.md` | Preserve existing, add `generated/` only |
| No GitHub workflows | Add `check-generated-indexes.yml` |
| Has existing workflows | Add workflow without conflicting |

### Step 3: Create PR

**PR Title Format:**
```
[jib] Add LLM documentation indexes for <repo-name>
```

**PR Body Template:**
```markdown
## Summary

This PR adds LLM-friendly documentation indexes to help jib (and other LLM agents)
navigate this codebase efficiently.

## What's Included

- `docs/generated/codebase.json` - Structured codebase analysis (X components)
- `docs/generated/patterns.json` - Detected code patterns (Y patterns)
- `docs/generated/dependencies.json` - Dependency graph (Z packages)
- `docs/generated/README.md` - Documentation for generated files
- `.github/workflows/check-generated-indexes.yml` - CI to keep indexes fresh

## Why This Helps

LLM agents can query these indexes to understand the codebase structure without
reading every file. The CI workflow ensures indexes stay up to date.

## Test Plan

- [ ] CI passes (indexes are consistent)
- [ ] Generated files are valid JSON
- [ ] Workflow triggers on Python file changes

— Authored by jib
```

### Step 4: Notify Human

After PR creation, jib sends a Slack notification:

```markdown
# 🔧 Jib Onboarding Complete: <repo-name>

**Repository**: <owner>/<repo>
**PR**: #<number>

## Generated Artifacts
- Codebase index: X components, Y files
- Patterns detected: Z patterns
- External dependencies: N packages

## Next Steps
- [ ] Review and merge PR
- [ ] Future PRs will auto-check index freshness

Questions? Reply in this thread.
```

## Feature Analysis & Documentation

### Feature Analyzer Integration

The feature-analyzer is a core component of the onboarding workflow. It provides:

**1. Full Repository Analysis (`feature-analyzer full-repo`)**

Scans the entire codebase to discover and catalog features:

```bash
# Analyze repository and generate FEATURES.md
feature-analyzer full-repo \
    --repo-root ~/khan/target-repo \
    --workers 5 \
    --no-pr
```

**Output:** `docs/FEATURES.md` - A comprehensive mapping of features to source locations:

```markdown
# Features

## Communication
### 1. Slack Integration
**Location:** `host-services/slack/`
**Components:**
- **Notifier** (`slack-notifier.py`)
- **Receiver** (`slack-receiver.py`)
**Documentation:** [Communication Features](docs/features/communication.md)
```

**2. Feature Documentation Generation (`feature-analyzer generate-feature-docs`)**

Generates detailed documentation for each feature category:

```bash
# Generate docs/features/*.md from FEATURES.md
feature-analyzer generate-feature-docs \
    --repo-root ~/khan/target-repo
```

**Output:** `docs/features/` directory with:
- `README.md` - Navigation index
- `communication.md` - Communication feature details
- `github-integration.md` - GitHub integration details
- Category docs for each feature group

**3. Weekly Analysis (`feature-analyzer weekly-analyze`)**

For ongoing maintenance, analyzes recent commits to detect new features:

```bash
# Detect new features from past 7 days
feature-analyzer weekly-analyze \
    --days 7 \
    --repo-root ~/khan/target-repo
```

### Why Feature Discovery Matters for LLM Onboarding

Traditional codebase indexes (like `codebase.json`) provide structural information, but they lack semantic understanding. The feature-analyzer fills this gap:

| Index Type | What It Captures | Use Case |
|------------|------------------|----------|
| `codebase.json` | Files, classes, functions | "Where is class X defined?" |
| `FEATURES.md` | Feature-to-code mapping | "What code implements Slack integration?" |
| `docs/features/*.md` | Feature purpose & usage | "How do I use the notification system?" |

This multi-layered approach gives LLM agents comprehensive understanding of both **what** exists and **why** it exists.

## Index Generation

### Supported Languages

**Phase 1 (Initial):**
- Python (AST-based analysis)

**Phase 2 (Future):**
- JavaScript/TypeScript (tree-sitter)
- Go (go/ast)
- Java (JavaParser)

### Pattern Detection

The generator detects common patterns based on naming conventions:

| Pattern | Indicators | Description |
|---------|------------|-------------|
| `mvc` | Controller, View, Model | Model-View-Controller architecture |
| `repository` | Repository, Store, DAO | Data access layer pattern |
| `service` | Service, Manager | Business logic layer |
| `decorator` | @decorator, wrapper | Decorator pattern usage |
| `factory` | Factory, Builder, Creator | Object creation patterns |
| `observer` | Watcher, Listener, Handler | Event-driven patterns |

### Dependency Analysis

**Internal Dependencies:**
- Tracks which files import which other files
- Maps module relationships

**External Dependencies:**
- Extracts from `requirements.txt`, `pyproject.toml`
- Maps package names to import names (e.g., `pyyaml` → `yaml`)
- Identifies stdlib vs. third-party

## Auto-Regeneration

### Trigger Conditions

The CI workflow triggers when:

1. **Python files change** (`**/*.py`)
2. **Dependency files change** (`requirements*.txt`, `pyproject.toml`)
3. **Generator script changes** (if bundled in repo)

### Failure Handling

When indexes are out of date:

1. **CI fails** with clear message
2. **Instructions provided** on how to regenerate
3. **PR author** responsible for regenerating before merge

### Manual Regeneration

```bash
# From repo root
# SECURITY: Pin to specific release version (not 'main')
GENERATOR_VERSION="v1.0.0"

curl -sL "https://raw.githubusercontent.com/jwbron/james-in-a-box/${GENERATOR_VERSION}/host-services/analysis/index-generator/index-generator.py" \
  -o /tmp/index-generator.py
python3 /tmp/index-generator.py --project . --output docs/generated
git add docs/generated/
git commit -m "Regenerate codebase indexes"
```

**Future Enhancement:** Consider publishing index-generator as a pip package or reusable GitHub Action to improve security and versioning.

## PR Workflow

### Jib's PR Behavior

1. **Creates branch:** `jib/onboarding-indexes` or `jib/update-indexes`
2. **Commits artifacts:** All generated files in single commit
3. **Opens PR:** With descriptive body and test plan
4. **Waits for review:** Does NOT auto-merge
5. **Responds to feedback:** Can update PR if requested

### Human Review Checklist

- [ ] Generated JSON files are valid
- [ ] No sensitive information in indexes
- [ ] CI workflow doesn't conflict with existing workflows
- [ ] Index content matches actual codebase

## Migration Strategy

### Phase 1: james-in-a-box (Complete)

- [x] Index generator implemented
- [x] Tests written
- [x] CI workflow added
- [ ] Deploy to jib-container

### Phase 2: Pilot Repos (after Phase 1 deployed)

1. Select 2-3 repos for pilot
2. Run onboarding manually
3. Gather feedback on generated artifacts
4. Iterate on generator and templates

### Phase 3: Automated Onboarding (after pilot feedback incorporated)

1. Add onboarding command to jib
2. Integrate with Slack workflow
3. Add JIRA trigger support
4. Document onboarding process

### Phase 4: Multi-Language Support (after core workflow stable)

1. Add JavaScript/TypeScript support
2. Add Go support
3. Add Java support
4. Generalize pattern detection

## Consequences

### Benefits

1. **Consistent Understanding:** Jib has structured knowledge of any repo
2. **Faster Context:** Indexes are faster than re-analyzing codebase
3. **Self-Maintaining:** CI ensures indexes stay current
4. **Transferable:** Indexes help any LLM agent, not just jib
5. **Low Friction:** Single PR adds all infrastructure

### Drawbacks

1. **PR Overhead:** Repos must accept and maintain new files
2. **CI Time:** Additional CI step for index checking
3. **Python-First:** Other languages need additional work
4. **Maintenance:** Generator itself needs updates

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| PR rejected by repo owners | Clear documentation of benefits; opt-in approach |
| Generated indexes too large | Limit component count; exclude test files |
| False pattern detection | Conservative detection; human review |
| CI conflicts | Check for existing workflows before adding |

## Open Questions

<!-- TODO: Resolve these questions -->

### 1. Index Storage Location

**Current Decision:** `docs/generated/` in target repo

**Alternative:** Centralized storage (e.g., shared S3 bucket)

**Considerations:**
- In-repo keeps everything together, visible in PRs
- Centralized would avoid "polluting" target repos
- In-repo chosen for simplicity and transparency

### 2. Handling Monorepos

**Question:** How should jib handle monorepos with multiple services?

**Options:**
- Single index for entire monorepo
- Per-service indexes in service directories
- Configurable via `.jibconfig` file

**Recommendation (research-backed):** Per-service indexes are preferable. Research suggests treating each component like a microservice:

> *"By treating each AI agent like a microservice — versioned, monitored and sandboxed — we can scale safely."*

**Proposed structure:**
```
monorepo/
├── services/
│   ├── auth/
│   │   └── docs/generated/  # Auth service index
│   ├── billing/
│   │   └── docs/generated/  # Billing service index
├── docs/
│   └── generated/
│       └── monorepo-overview.json  # Cross-service relationships
```

### 3. Existing Documentation Integration

**Question:** How much should jib modify existing `docs/index.md`?

**Current Approach:** Create new file if missing, don't modify existing

**Alternative:** Append generated index links to existing index

**TODO:** Determine best UX for repos with existing docs

### 4. Private/Sensitive Code

**Question:** How to handle repos with sensitive patterns?

**Considerations:**
- Generated indexes might reveal internal architecture
- Some repos may not want structure exposed

**TODO:** Add `.jibignore` or similar exclusion mechanism

### 5. Version Compatibility

**Question:** How to handle generator version changes?

**Options:**
- Include generator version in output
- Warn if regenerating with different version
- Auto-upgrade workflow when generator updates

**Recommendation (research-backed):** Follow OpenTelemetry's pattern using environment variable opt-in:

```yaml
# .jibconfig
versioning:
  stability_opt_in: "stable"  # Options: stable, experimental, deprecated
  warn_on_version_change: true
```

Generator output includes version metadata:
```json
{
  "generator": {
    "version": "1.2.0",
    "schema_version": "1.0",
    "stability": "stable"
  }
}
```

This allows repos to pin to stable schemas while enabling experimental features for early adopters.

## Research-Backed Enhancements

The following enhancements are based on current best practices and emerging standards (November 2025):

### 1. Relationship Indexing

Extend `codebase.json` with import/dependency relationships to enable graph-based queries:

```json
{
  "relationships": [
    {
      "source": "src/controllers/user.py",
      "target": "src/services/auth.py",
      "type": "imports",
      "symbols": ["authenticate", "AuthService"]
    },
    {
      "source": "UserController",
      "target": "BaseController",
      "type": "inherits"
    }
  ]
}
```

**Rationale:** Research shows graph-based code indexing improves code search and retrieval by capturing structural relationships, not just file contents. (Note: The original arXiv reference needs verification - knowledge graph approaches for code search are an active research area.)

### 2. RepoAgent Framework Reference

Consider integration with or learning from **[RepoAgent (OpenBMB)](https://github.com/OpenBMB/RepoAgent)**, an LLM-powered framework for repository documentation:

> *"RepoAgent not only facilitates current and future developers in grasping the project's purpose and structure but also ensures that the project remains accessible and modifiable over time."* — [arXiv:2402.16667](https://arxiv.org/abs/2402.16667)

Key RepoAgent insights applicable here:
- Uses AST-based analysis for Python code understanding (aligned with our approach)
- Maintains documentation in sync with code changes (our CI workflow)
- Validates generated docs through qualitative and quantitative evaluation

### 3. Language Expansion Priority

Research indicates JavaScript/TypeScript as highest-value after Python due to ecosystem prevalence and tree-sitter parsing maturity. Updated phase plan:

| Phase | Language | Parser | Priority Rationale |
|-------|----------|--------|-------------------|
| 1 | Python | AST | Current implementation |
| 2 | JavaScript/TypeScript | tree-sitter | Highest adoption after Python |
| 3 | Go | go/ast | Growing cloud-native usage |
| 4 | Java | JavaParser | Enterprise codebase coverage |

### 4. Semantic Search Enhancement

Add LLM-generated descriptions alongside function signatures for improved retrieval accuracy:

```json
{
  "components": [
    {
      "name": "authenticate_user",
      "type": "function",
      "file": "src/auth.py",
      "line": 42,
      "signature": "def authenticate_user(username: str, password: str) -> User",
      "semantic_description": "Validates user credentials against the database and returns a User object if authentication succeeds. Raises AuthenticationError on failure."
    }
  ]
}
```

**Implementation:** During index generation, use a cost-effective model to generate one-sentence descriptions for each component. (Future: leverage model-agnostic architecture for optimal model selection per task.)

### 5. llms.txt as Optional

Make `llms.txt` generation configurable given limited current adoption:

> *"Only 951 domains had published an llms.txt file as of July 2025."* — [Analytics Vidhya](https://www.analyticsvidhya.com/blog/2025/03/llms-txt/)

*Note: This statistic is from July 2025 research. Adoption may have increased since then, but the overall recommendation to make llms.txt optional remains valid until it becomes a widely-adopted standard.*

**Configuration via `.jibconfig`:**

```yaml
onboarding:
  generate_llms_txt: false  # Default: false until adoption increases
  generate_index_md: true   # Default: true
```

Rationale: Focus effort on generated indexes (`docs/generated/`) which provide immediate value, while making llms.txt opt-in for repos that want web crawler compatibility.

### 6. Multi-Agent Documentation Alignment

The onboarding workflow aligns with multi-agent best practices from **[DocAgent](https://arxiv.org/html/2504.08725v1)** research:

| ADR Phase | DocAgent Pattern | Benefit |
|-----------|------------------|---------|
| Initial Analysis | Reader Agent | Understands existing codebase |
| Generate Artifacts | Writer Agent | Creates structured documentation |
| Validate & PR | Reviewer Agent | Ensures quality before delivery |

This separation of concerns enables future optimization where different model capabilities can be applied to each phase.

## References

- [LLM Documentation Index Strategy ADR](../implemented/ADR-LLM-Documentation-Index-Strategy.md) - Foundation patterns
- [llms.txt Standard](https://llmstxt.org/) - LLM-friendly content standard
- [GitHub Actions Documentation](https://docs.github.com/en/actions) - CI workflow reference
- [RepoAgent Paper (arXiv:2402.16667)](https://arxiv.org/abs/2402.16667) - LLM-powered repository documentation
- [DocAgent Multi-Agent System (arXiv:2504.08725)](https://arxiv.org/html/2504.08725v1) - Multi-agent documentation approaches

---

**Last Updated:** 2025-12-02
**Next Review:** 2026-01-02 (Monthly)
**Status:** Proposed - Awaiting Review
