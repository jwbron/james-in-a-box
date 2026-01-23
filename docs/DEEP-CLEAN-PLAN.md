# james-in-a-box Deep Clean Plan

> **Status**: Proposed
> **Created**: 2026-01-23
> **Bead**: beads-g37a

## Objectives

1. Ensure documentation is up to date and consistent
2. Check functionality of each feature
3. Label and remove features that are half-baked, incomplete, or deemed "not useful"
4. Assess opportunities for code isolation and sharing
5. Find bugs, inconsistencies, errors, and undefined behavior

## Executive Summary

This plan organizes the deep clean into 5 phases:

| Phase | Focus | Scope |
|-------|-------|-------|
| 1 | Codebase Inventory | Crawl and catalog all code, features, and documentation |
| 2 | Feature-by-Feature Analysis | Deep analysis of each of the 52 features |
| 3 | Documentation Analysis | Audit all documentation for accuracy and completeness |
| 4 | Feature Removal | Remove confirmed incomplete/unused features |
| 5 | Documentation Update | Sync all docs with current state |

> **Note**: Phases 2 and 3 are largely independent and can run concurrently.

---

## Phase 1: Codebase Inventory

Before analyzing features, we need a complete inventory of what exists.

### 1.1 Directory Structure Catalog

Create a comprehensive map of the repository:

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `bin/` | Executable symlinks | 35+ commands |
| `config/` | Configuration templates | host_config.py, repo_config.py |
| `docs/` | Documentation | index.md, FEATURES.md, ADRs |
| `gateway-sidecar/` | Policy enforcement gateway | gateway.py, policy.py |
| `host-services/` | Host-side services | analysis/, slack/, sync/, utilities/ |
| `jib-container/` | Container contents | entrypoint.py, .claude/, jib-tasks/, llm/ |
| `scripts/` | Utility scripts | validation, migration |
| `shared/` | Shared Python modules | beads, jib_config, notifications |
| `tests/` | Test suite | pytest-based tests |

### 1.2 Feature Inventory

Current feature count from FEATURES.md:
- **52 top-level features** (after removing 2 confirmed for deletion)
- **127 including sub-features**
- **11 categories**

Categories to analyze:
1. Communication (4 features)
2. Context Management (8 features)
3. GitHub Integration (7 features)
4. Self-Improvement System (3 features)
5. Documentation System (10 features)
6. Custom Commands (1 feature)
7. LLM Providers (1 feature after removal) - *2 features confirmed for removal*
8. Container Infrastructure (5 features)
9. Utilities (7 features)
10. Security Features (1 feature)
11. Configuration (3 features)

### 1.3 Documentation Inventory

| Location | Type | Count |
|----------|------|-------|
| `docs/` | Main documentation | ~30 files |
| `docs/adr/` | Architecture Decision Records | 12 ADRs |
| `docs/setup/` | Setup guides | 5 files |
| `docs/reference/` | Reference docs | 8 files |
| `docs/features/` | Feature docs | 9 files |
| `*/README.md` | Component READMEs | ~20 files |
| `jib-container/.claude/rules/` | Agent rules | 10 files |

### 1.4 Test Inventory

| Directory | Coverage |
|-----------|----------|
| `tests/config/` | Configuration validation |
| `tests/context_sync/` | Sync connectors |
| `tests/host_services/` | Host service tests |
| `tests/jib/` | Container tests |
| `tests/jib_config/` | Config framework tests |
| `tests/shared/` | Shared module tests |

---

## Phase 2: Feature-by-Feature Analysis

### 2.0 Prioritization Criteria

With 52 features to analyze, prioritize in this order:

1. **Experimental features** (marked in FEATURES.md) - highest risk of being incomplete
2. **Features with no tests** - may have undiscovered issues
3. **Features with known issues** - referenced in beads or PRs
4. **Rarely used features** - candidates for removal
5. **Core features** - analyze last since they're most stable

### 2.0.1 Analysis Template

Analyze each feature using this template:

```
Feature: [Name]
Location: [File paths]
Status: [Working | Partial | Broken | Unused]
Documentation: [Complete | Partial | Missing | Outdated]
Tests: [Yes | No | Partial]
Dependencies: [What it depends on]
Dependents: [What depends on it]
Recommendation: [Keep | Improve | Deprecate | Remove]
Notes: [Any issues found]
```

### 2.1 Communication Features (4)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 1 | Slack Notifier Service | Pending |
| 2 | Slack Receiver Service | Pending |
| 3 | Slack Message Processor | Pending |
| 4 | Container Notifications Library | Pending |

### 2.2 Context Management Features (8)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 5 | Context Sync Service | Pending |
| 6 | Confluence Connector | Pending |
| 7 | JIRA Connector | Pending |
| 8 | Beads Task Tracking System | Pending |
| 9 | JIRA Ticket Processor | Pending |
| 10 | Sprint Ticket Analyzer | Pending |
| 11 | PR Context Manager | Pending |
| 12 | Beads Task Memory Initialization | Pending |

### 2.3 GitHub Integration Features (7)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 13 | GitHub Watcher Service | Pending |
| 14 | GitHub CI/CD Failure Processor | Pending |
| 15 | PR Auto-Review System | Pending |
| 16 | PR Comment Auto-Responder | Pending |
| 17 | PR Analyzer Tool | Pending |
| 18 | GitHub Command Handler | Pending |
| 19 | GitHub App Token Generator | Pending |

### 2.4 Self-Improvement System Features (3)

**Note**: These are marked as "experimental" in FEATURES.md

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 20 | LLM Trace Collector | Pending |
| 21 | LLM Inefficiency Detector | Pending |
| 22 | Beads Integration Analyzer | Pending |

### 2.5 Documentation System Features (10)

**Note**: Most are marked as "experimental" in FEATURES.md

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 23 | Feature Analyzer Service | Pending |
| 24 | ADR Researcher Service | Pending |
| 25 | ADR Processor | Pending |
| 26 | Documentation Generator Pipeline | Pending |
| 27 | Documentation Drift Detector | Pending |
| 28 | Codebase Index Generator | Pending |
| 29 | Spec Enricher CLI | Pending |
| 30 | Documentation Link Fixer | Pending |
| 31 | Confluence Documentation Watcher | Pending |
| 32 | Documentation Index | Pending |

### 2.6 Custom Commands Features (1)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 33 | Claude Custom Commands | Pending |

### 2.7 LLM Providers Features (3)

**Note**: Features #35 and #36 are confirmed for removal

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 34 | Multi-Provider LLM Module | **SIMPLIFY** - remove multi-provider |
| 35 | Gemini CLI Integration | **REMOVE** - confirmed |
| 36 | Claude Code Router Support | **REMOVE** - confirmed |

### 2.8 Container Infrastructure Features (5)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 37 | JIB Container Management System | Pending |
| 38 | Docker Development Environment Setup | Pending |
| 39 | Analysis Task Processor | Pending |
| 40 | Session End Hook | Pending |
| 41 | Container Directory Communication | Pending |

### 2.9 Utilities Features (7)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 42 | Documentation Search Utility | Pending |
| 43 | Sync Maintenance Tools | Pending |
| 44 | Symlink Management for Projects | Pending |
| 45 | Rate Limiting Handler | Pending |
| 46 | Codebase Index Query Tool | Pending |
| 47 | Worktree Watcher Service | Pending |
| 48 | Test Discovery Tool | Pending |

### 2.10 Security Features (1)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 49 | GitHub Token Refresher Service | Pending |

### 2.11 Configuration Features (3)

| # | Feature | Analysis Status |
|---|---------|-----------------|
| 50 | Master Setup System | Pending |
| 51 | Interactive Configuration Setup | Pending |
| 52 | Claude Agent Rules System | Pending |

---

## Phase 3: Documentation Analysis

### 3.1 Documentation Accuracy Audit

For each documentation file, verify:
- [ ] All code references point to existing files
- [ ] All features mentioned actually exist
- [ ] Instructions are accurate and work
- [ ] Examples are correct and runnable
- [ ] Links are not broken

### 3.2 ADR Status Verification

| ADR | Listed Status | Actual Status | Action |
|-----|---------------|---------------|--------|
| Context Sync Strategy | Implemented | Verify | Check code matches ADR |
| Feature Analyzer - Doc Sync | Implemented | Verify | Check code matches ADR |
| LLM Documentation Index Strategy | Implemented | Verify | Check code matches ADR |
| LLM Inefficiency Reporting | Implemented | Verify | Check code matches ADR |
| Autonomous Software Engineer | In-Progress | Verify | Check what's actually done |
| Continuous System Reinforcement | Not-Implemented | Verify | Should this be removed? |
| GCP Deployment | Not-Implemented | Verify | Still planned? |
| Internet Tool Access Lockdown | Not-Implemented | Verify | Misfiled in in-progress? |
| Jib Repository Onboarding | Not-Implemented | Verify | Implemented elsewhere? |
| Message Queue Integration | Not-Implemented | Verify | Still planned? |
| Slack Bot GCP Integration | Not-Implemented | Verify | Still planned? |
| Slack Integration Strategy | Not-Implemented | Verify | Actually implemented? |

### 3.3 README Completeness Check

| README Location | Exists | Up-to-date | Complete |
|-----------------|--------|------------|----------|
| `/README.md` | Pending | Pending | Pending |
| `/docs/README.md` | Pending | Pending | Pending |
| `/host-services/*/README.md` | Pending | Pending | Pending |
| `/jib-container/README.md` | Pending | Pending | Pending |
| `/gateway-sidecar/README.md` | Pending | Pending | Pending |
| `/shared/*/README.md` | Pending | Pending | Pending |

### 3.4 Cross-Reference Verification

Check that:
- `docs/index.md` references all key documents
- `docs/FEATURES.md` matches actual code
- Setup guides work with current code
- Reference docs are accurate

---

## Phase 4: Feature Removal

### 4.0 Testing Strategy

Before any removal:
1. **Establish baseline**: Run full test suite, record results
2. **Incremental removal**: Remove one feature at a time
3. **Test after each removal**: Run tests immediately after each change
4. **Rollback plan**: If tests fail, revert and investigate before proceeding

```bash
# Baseline before removal
make test > baseline-results.txt 2>&1

# After each removal
make test

# If failure, revert
git checkout -- <files>
```

### 4.1 Confirmed Removals

> **Note**: File lists below are preliminary and may change after Phase 2 analysis reveals additional dependencies.

#### Remove Claude Code Router Support

**Files to delete:**
- `jib-container/llm/claude/router.py`

**Files to modify:**
- `jib-container/llm/claude/__init__.py` - remove router imports
- `jib-container/llm/claude/config.py` - remove `ANTHROPIC_BASE_URL` references
- `jib-container/llm/claude/runner.py` - remove router usage
- `jib-container/llm/__init__.py` - remove router references
- `jib-container/llm/config.py` - remove `OPENAI` provider from enum
- `jib-container/llm/runner.py` - simplify provider selection
- `shared/jib_config/configs/llm.py` - remove router config
- `docs/FEATURES.md` - remove feature #36

#### Remove Gemini CLI Support

**Directories to delete:**
- `jib-container/llm/gemini/` (entire directory)

**Files to delete:**
- `jib-container/GEMINI.md` (if exists)

**Files to modify:**
- `jib-container/llm/__init__.py` - remove gemini references
- `jib-container/llm/config.py` - remove `GOOGLE` provider, `GEMINI_MODEL`
- `jib-container/llm/runner.py` - remove gemini handling
- `jib-container/entrypoint.py` - remove GEMINI.md setup
- `jib-container/Dockerfile` - remove gemini CLI if present
- `jib-container/jib` - remove gemini references
- `shared/jib_config/configs/llm.py` - remove gemini config
- `docs/FEATURES.md` - remove features #34, #35
- `tests/jib/test_entrypoint.py` - update tests
- `tests/jib_config/test_configs.py` - update tests

#### Simplify LLM Module

After removals, the LLM module should have this simplified API:

**Target Public API** (`jib-container/llm/__init__.py`):
```python
# Functions to keep
run_agent(prompt: str, cwd: Path = None, timeout: int = 7200) -> AgentResult
run_agent_async(prompt: str, cwd: Path = None, timeout: int = 7200) -> AgentResult
run_interactive(cwd: Path = None) -> None

# Classes to keep
AgentResult  # dataclass with success, stdout, stderr, return_code

# Remove
Provider enum (no longer needed)
LLMConfig class (simplify or remove)
get_provider() function
```

**Changes**:
- Remove multi-provider abstraction layer
- Remove `LLM_PROVIDER` env var support
- Remove `Provider` enum entirely
- Simplify `LLMConfig` to just `cwd` and `timeout` (or remove entirely)
- Keep core functions with simplified signatures

### 4.2 Features Pending Removal Decision

After Phase 2 analysis, features may be added here:

| Feature | Reason | Decision |
|---------|--------|----------|
| (pending Phase 2) | | |

---

## Phase 5: Documentation Update

### 5.1 Post-Removal Updates

After Phase 4:
1. Regenerate FEATURES.md: `feature-analyzer full-repo`
2. Update docs/index.md
3. Update README.md if needed
4. Remove references to deleted features

### 5.2 Consistency Fixes

Based on Phase 3 findings:
1. Fix broken links
2. Update outdated instructions
3. Correct inaccurate code references
4. Add missing documentation

### 5.3 Verification

```bash
# Check for broken doc links
bin/check-doc-drift

# Check for references to removed features
grep -r "gemini\|router\|LLM_PROVIDER" docs/

# Validate all internal links
bin/fix-doc-links --dry-run
```

---

## Analysis Templates

### Feature Analysis Template

```markdown
## Feature #X: [Name]

**Location:**
- Primary: `path/to/main/file.py`
- Supporting: `path/to/support/`

**Purpose:** [One-sentence description]

**Status:**
- [ ] Code exists and runs
- [ ] Has tests
- [ ] Has documentation
- [ ] Actively used
- [ ] Well-integrated with other features

**Dependencies:**
- Depends on: [list features/modules]
- Used by: [list features/modules]

**Issues Found:**
- [Issue 1]
- [Issue 2]

**Recommendation:** [Keep | Improve | Deprecate | Remove]

**Notes:**
[Additional context]
```

### Documentation Analysis Template

```markdown
## Document: [path/to/doc.md]

**Purpose:** [What this doc is for]

**Accuracy Check:**
- [ ] All code paths exist
- [ ] Examples work
- [ ] Commands are correct
- [ ] Links work

**Completeness:**
- [ ] Covers all relevant topics
- [ ] Has examples where needed
- [ ] Has troubleshooting if applicable

**Issues Found:**
- [Issue 1]
- [Issue 2]

**Recommendation:** [Keep as-is | Update | Merge | Remove]
```

---

## Success Criteria

- [ ] All 53 features analyzed with status documented
- [ ] All documentation files audited
- [ ] All ADR statuses verified
- [ ] Claude router code removed
- [ ] Gemini CLI code removed
- [ ] LLM module simplified
- [ ] All tests pass
- [ ] FEATURES.md regenerated and accurate
- [ ] docs/index.md has no broken links
- [ ] No grep hits for "gemini" or "router" in active code

---

## Appendix: Quick Reference

### Key Directories

```
james-in-a-box/
├── bin/                    # 35+ executable symlinks
├── config/                 # Configuration templates
├── docs/                   # All documentation
│   ├── adr/               # Architecture Decision Records
│   ├── features/          # Feature documentation
│   ├── reference/         # Reference guides
│   └── setup/             # Setup guides
├── gateway-sidecar/        # Policy enforcement
├── host-services/          # Host-side services
│   ├── analysis/          # Analyzers (10+ services)
│   ├── slack/             # Slack integration
│   ├── sync/              # Context sync
│   └── utilities/         # Helper services
├── jib-container/          # Container contents
│   ├── .claude/           # Agent configuration
│   ├── jib-tasks/         # Task processors
│   ├── jib-tools/         # Interactive tools
│   └── llm/               # LLM interface
├── scripts/                # Utility scripts
├── shared/                 # Shared Python modules
└── tests/                  # Test suite
```

### Commands for Analysis

```bash
# Run tests
make test

# Check linting
make lint

# Find features in code
grep -r "def " host-services/ --include="*.py" | head -50

# Check doc links
bin/check-doc-drift

# Search for patterns
grep -r "pattern" . --include="*.py"

# Count lines by directory
find host-services -name "*.py" -exec wc -l {} + | tail -1
```
