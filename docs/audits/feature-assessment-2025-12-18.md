# Feature Assessment: Half-Baked Features

**Date:** 2025-12-18
**Author:** jib (Autonomous Software Engineering Agent)
**Task ID:** task-20251217-235446

## Executive Summary

This assessment identifies features in james-in-a-box that are "half-baked" - either documented but not implemented, partially implemented, or outdated relative to current architecture. Each feature is categorized with a recommended action: **REMOVE**, **IMPROVE**, or **DOCUMENT ACCURATELY**.

## Methodology

1. Read FEATURES.md (51 top-level features, 119 including sub-features)
2. Cross-referenced with actual file existence
3. Checked existing feature audit from 2025-12-02
4. Verified implementation status vs documentation

---

## Category 1: REMOVE - Documented but Not Implemented

These features are documented in FEATURES.md or supporting docs but do not exist or are non-functional.

### 1.1 Missing Claude Custom Commands (Feature #34)

**Issue:** README.md documents 7 commands but only 3 exist as files.

**Location:** `jib-container/.claude/commands/`

| Documented Command | File Status | Action |
|-------------------|-------------|--------|
| `/load-context` | **MISSING** | Remove from README |
| `/save-context` | **MISSING** | Remove from README |
| `/create-pr` | **MISSING** | Remove from README |
| `/update-confluence-doc` | **MISSING** | Remove from README |
| `/beads-status` | EXISTS | Keep |
| `/beads-sync` | EXISTS | Keep |
| `/show-metrics` | EXISTS | Keep |

**Recommendation:** Either implement the missing 4 commands OR update README.md to only document the 3 that exist. Given these appear to be aspirational features, recommend **REMOVE from documentation**.

---

### 1.2 Conversation Analyzer Service (Feature #23)

**Issue:** Documented in FEATURES.md but directory does not exist.

**Location:** `host-services/analysis/conversation-analyzer/` - **DOES NOT EXIST**

**FEATURES.md says:**
> Weekly analysis service that analyzes Slack/GitHub conversation patterns to identify communication quality issues and improvement opportunities.

**Recommendation:** **REMOVE** from FEATURES.md entirely. This feature was never implemented.

---

### 1.3 Confluence Doc Discoverer

**Issue:** Referenced by repo-onboarding/README.md but does not exist.

**Location:** `host-services/analysis/confluence-doc-discoverer/` - **DOES NOT EXIST**

**repo-onboarding/README.md references:**
```
../confluence-doc-discoverer/
└── confluence-doc-discoverer.py # Confluence doc discovery
```

**Recommendation:** **REMOVE** reference from repo-onboarding/README.md OR implement the feature.

---

### 1.4 docs-index-updater.py

**Issue:** Referenced in repo-onboarding/README.md but file does not exist.

**Location:** `host-services/analysis/repo-onboarding/docs-index-updater.py` - **DOES NOT EXIST**

**Recommendation:** **REMOVE** reference from README.md.

---

## Category 2: IMPROVE - Partially Implemented or Inconsistent

These features exist but have significant gaps, bugs, or inconsistencies.

### 2.1 JIRA Sync Missing Rate Limiting (Feature #44)

**Issue:** Confluence connector has rate limiting, JIRA connector does not.

**Location:**
- `host-services/sync/context-sync/connectors/jira/sync.py` - **NO rate limiting**
- `host-services/sync/context-sync/connectors/confluence/sync.py` - HAS rate limiting

**Impact:** JIRA sync can fail during heavy API usage without graceful retry.

**Recommendation:** **IMPROVE** - Port rate limiting logic from Confluence to JIRA connector.

**Implementation Plan:**
1. Extract `RateLimiter` class from confluence/sync.py to shared module
2. Apply to jira/sync.py
3. Update FEATURES.md to reflect shared implementation

---

### 2.2 Symlink Management Duplication (Feature #42)

**Issue:** Duplicate symlink creation logic in two files.

**Location:**
- `host-services/sync/context-sync/utils/create_symlink.py` - Original implementation
- `host-services/sync/context-sync/utils/link_to_khan_projects.py` - Duplicates logic

**Recommendation:** **IMPROVE** - Refactor `link_to_khan_projects.py` to import from `create_symlink.py`.

---

### 2.3 Sprint Ticket Analyzer - No Claude Integration (Feature #10)

**Issue:** Feature uses hardcoded heuristics when Claude would be more effective.

**Location:** `jib-container/jib-tasks/jira/analyze-sprint.py`

**Current State:**
- Manual regex parsing
- Hardcoded scoring weights
- Rule-based recommendations

**Recommendation:** **IMPROVE** - Add Claude agent for intelligent sprint analysis.

**Implementation Plan:**
1. Create sprint analysis prompt template
2. Replace heuristic scoring with Claude analysis
3. Generate personalized recommendations

---

### 2.4 Documentation Generator - Missing Claude Integration (Feature #28)

**Issue:** Has excellent 4-agent architecture but doesn't actually invoke Claude.

**Location:** `host-services/analysis/doc-generator/doc-generator.py`

**Current State:**
- 4-agent pipeline (Context, Draft, Review, Output) exists in code structure
- Uses local heuristics instead of Claude
- Review notes appended to output

**Recommendation:** **IMPROVE** - Add Claude integration to each agent phase.

---

### 2.5 GitHub Command Handler - Regex-Based (Feature #18)

**Issue:** Uses regex patterns instead of natural language understanding.

**Location:** `jib-container/jib-tasks/github/command-handler.py`

**Current State:**
- Limited to exact patterns like "review PR 123"
- Can't understand "can you look at my latest PR?"

**Recommendation:** **IMPROVE** - Add Claude-based command parsing for natural language flexibility.

---

## Category 3: DOCUMENT ACCURATELY - Outdated Documentation

These features exist but documentation is outdated or misleading.

### 3.1 GitHub Watcher Architecture (Feature #13)

**Issue:** Recent refactor changed architecture significantly.

**FEATURES.md documents:**
- Single `github-watcher.py` (~1400 lines)
- Combined functionality

**Current State (after merge):**
- Modularized into `gwlib/` package
- Split into: `ci_fixer.py`, `comment_responder.py`, `pr_reviewer.py`
- Separate service files for each

**Recommendation:** **DOCUMENT ACCURATELY** - Update FEATURES.md to reflect modular architecture.

---

### 3.2 Feature 20: MCP Token Watcher (REMOVED)

**Issue:** Feature audit from December 2025 noted this was removed but FEATURES.md may still reference it.

**Status:** Verified - not in current FEATURES.md

**Recommendation:** No action needed - already removed.

---

## Category 4: KEEP AS-IS - Well Implemented

These features are correctly documented and implemented. No changes needed.

| Feature # | Feature Name | Status |
|-----------|-------------|--------|
| 1 | Slack Notifier Service | Well implemented |
| 2 | Slack Receiver Service | Well implemented |
| 3 | Slack Message Processor | Well implemented |
| 5 | Context Sync Service | Well implemented |
| 6 | Confluence Connector | Well implemented |
| 7 | JIRA Connector | Working (needs rate limiting) |
| 8 | Beads Task Tracking | Well implemented |
| 11 | PR Context Manager | Well implemented |
| 14 | GitHub CI/CD Failure Processor | Well implemented |
| 15 | PR Auto-Review System | Well implemented |
| 16 | PR Comment Auto-Responder | Well implemented |
| 17 | PR Analyzer Tool | Well implemented |
| 19 | GitHub App Token Generator | Well implemented (security-critical) |
| 20-22 | LLM Trace/Inefficiency System | Well implemented |
| 24 | Feature Analyzer Service | Well implemented |
| 25 | ADR Researcher Service | Well implemented (minor regex fix needed) |
| 35-40 | Container Infrastructure | Well implemented |
| 47-51 | Utilities & Configuration | Well implemented |

---

## Implementation Plan

### Phase 1: Documentation Cleanup (This PR)
**Priority: High | Effort: Low**

1. [ ] Update `jib-container/.claude/commands/README.md` - remove undocumented commands
2. [ ] Remove Conversation Analyzer Service from FEATURES.md
3. [ ] Fix repo-onboarding/README.md references
4. [ ] Update FEATURES.md for GitHub Watcher modular architecture

### Phase 2: Quick Wins (Next PR)
**Priority: High | Effort: Medium**

1. [ ] Add rate limiting to JIRA connector
2. [ ] Refactor symlink management to eliminate duplication
3. [ ] Fix ADR Researcher regex syntax error (`{1, 4}` -> `{1,4}`)

### Phase 3: Claude Integration (Future PRs)
**Priority: Medium | Effort: High**

1. [ ] Add Claude to Sprint Ticket Analyzer
2. [ ] Add Claude to Documentation Generator pipeline
3. [ ] Add Claude-based command parsing to GitHub Command Handler

---

## Summary Statistics

| Category | Count | Action Required |
|----------|-------|-----------------|
| REMOVE | 4 features/references | Documentation updates |
| IMPROVE | 5 features | Code changes |
| DOCUMENT ACCURATELY | 1 feature | Documentation update |
| KEEP AS-IS | 41 features | None |

**Total Features Assessed:** 51 top-level features

---

## Appendix: File Changes Required for Phase 1

### A. jib-container/.claude/commands/README.md

Remove documentation for non-existent commands:
- `/load-context`
- `/save-context`
- `/create-pr`
- `/update-confluence-doc`

### B. docs/FEATURES.md

1. Remove Feature #23 (Conversation Analyzer Service) entirely
2. Update Feature #13 (GitHub Watcher) to reflect modular architecture

### C. host-services/analysis/repo-onboarding/README.md

Remove references to:
- `../confluence-doc-discoverer/`
- `docs-index-updater.py`

---

*Generated by jib feature assessment task*
