# ADR: Multi-Agent Processing Optimization Pattern

**Driver:** jib
**Approver:** James Wiesebron
**Contributors:** jib, Claude
**Informed:** Engineering teams
**Proposed:** December 2025
**Status:** Proposed

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [The Scout Pattern](#the-scout-pattern)
- [Optimization Opportunities](#optimization-opportunities)
- [Implementation Priority](#implementation-priority)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

Several jib analysis tools read large numbers of files and make extensive LLM calls during processing. This leads to long execution times and high token consumption. For example, `jib-internal-devtools-setup` on the webapp repository was taking over an hour due to the feature analyzer blindly reading 15 files per directory across 59+ directories.

### Problem Statement

**Current state:** Analysis tools use brute-force file reading strategies:
- Read all files matching a pattern (e.g., all `.py` files)
- Read a fixed number of files per directory (e.g., always 15)
- Make LLM calls for every file/directory without pre-filtering

**Inefficiencies:**
1. **Blind File Selection:** Tools read files without considering relevance
2. **No Prioritization:** All directories/files treated equally important
3. **Duplicate Work:** Similar information extracted from multiple files
4. **Token Waste:** LLM processes irrelevant content

### Proven Solution

PR #407 implemented a multi-agent pipeline for the feature analyzer with dramatic improvements:

1. **Cartographer Agent:** Analyzes directory structure, prioritizes directories
2. **Scout Agent:** Recommends 3-5 key files per directory (vs. reading 15 blindly)
3. **Analyzer Agent:** Performs deep analysis on Scout-recommended files
4. **Consolidator Agent:** Deduplicates and organizes results

The Scout pattern alone reduces file reads by ~70% while maintaining analysis quality.

## Decision

**We will apply the Scout pattern to other jib analysis tools that exhibit similar brute-force file reading behavior.**

### Core Principles

1. **Intelligence Over Exhaustiveness:** Let LLMs decide what to read, not fixed rules
2. **Cheap Before Expensive:** Quick metadata scan before expensive file reads
3. **Heuristic Fallbacks:** Always have non-LLM fallbacks for reliability
4. **Preserve Full Coverage:** Optimize what we read, not what we analyze

## The Scout Pattern

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Cartographer│────▶│   Scout     │────▶│  Analyzer   │
│ (structure) │     │ (recommend) │     │ (deep read) │
└─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │
      ▼                   ▼                   ▼
  List of dirs       3-5 files/dir      Rich analysis
  + priorities       to actually read   of selected files
```

### Implementation Template

```python
def scout_recommend_files(directory: Path, context: str) -> list[Path]:
    """Scout agent recommends which files to read for deep analysis."""

    # 1. Get directory listing (cheap operation)
    all_files = list(directory.rglob("*"))
    file_names = [f.name for f in all_files if f.is_file()]

    # 2. Ask LLM to recommend key files (small prompt, no file content)
    prompt = f"""Given this directory structure for {context}:

Files: {file_names[:50]}  # Limit to avoid huge prompts

Recommend 3-5 files most likely to contain the core information.
Prioritize: README, main entry points, config files, core modules.

Return as JSON: {{"files": ["file1.py", "file2.py"]}}"""

    recommendations = llm_call(prompt)

    # 3. Return recommended files (or fallback to heuristics)
    return recommendations.get("files", heuristic_fallback(all_files))

def heuristic_fallback(files: list[Path]) -> list[Path]:
    """Non-LLM fallback when Scout unavailable."""
    priority_names = ["README", "main", "index", "core", "__init__", "config"]
    return [f for f in files if any(p in f.name.lower() for p in priority_names)][:5]
```

## Optimization Opportunities

### HIGH Priority (Significant Impact)

#### 1. index-generator.py

**Location:** `host-services/analysis/index-generator/index-generator.py`

**Current Behavior:**
- `rglob("*.py")` reads ALL Python files in project
- Processes every file regardless of relevance
- Large repositories = thousands of unnecessary file reads

**Proposed Optimization:**
- Add Scout to identify "core" modules vs. utilities/tests
- Prioritize files with high import counts (entry points)
- Skip obvious non-core files (tests, migrations, generated code)

**Expected Reduction:** 60-80% fewer file reads

#### 2. drift-detector.py

**Location:** `host-services/analysis/drift-detector/drift-detector.py`

**Current Behavior:**
- Caches entire filesystem structure
- No prioritization of what to track
- Potentially scans thousands of files on every run

**Proposed Optimization:**
- Scout identifies which directories are "active" (frequently changed)
- Focus drift detection on core source directories
- Exclude generated files, caches, node_modules

**Expected Reduction:** 50-70% fewer files tracked

#### 3. weekly_analyzer.py (Already Implemented)

**Location:** `host-services/analysis/feature-analyzer/weekly_analyzer.py`

**Status:** Scout pattern implemented in PR #407

**Result:** Reduced from 15 files/directory to 3-5 recommended files

### MEDIUM Priority (Moderate Impact)

#### 4. confluence-doc-discoverer.py

**Location:** `host-services/analysis/confluence-doc-discoverer/confluence-doc-discoverer.py`

**Current Behavior:**
- Searches all Confluence docs for repository mentions
- Returns potentially large result sets
- No relevance ranking

**Proposed Optimization:**
- Scout ranks docs by relevance before full extraction
- Prioritize ADRs, runbooks, and technical specs
- Filter out meeting notes and outdated docs

**Expected Reduction:** 40-60% fewer docs processed in detail

#### 5. adr-researcher.py

**Location:** `host-services/analysis/adr-researcher/adr-researcher.py`

**Current Behavior:**
- Reads all ADR files for cross-referencing
- Processes entire ADR content

**Proposed Optimization:**
- Scout identifies ADRs relevant to current context
- Read only sections needed (not full docs)
- Cache frequently-referenced ADRs

**Expected Reduction:** 30-50% token reduction

#### 6. beads-analyzer-processor.py

**Location:** `jib-container/jib-tasks/analysis/beads-analyzer-processor.py`

**Current Behavior:**
- Analyzes all beads in database
- No prioritization of which beads to analyze deeply

**Proposed Optimization:**
- Scout identifies beads most relevant to current task
- Prioritize recent and in-progress beads
- Light-touch analysis for old/closed beads

**Expected Reduction:** 40-60% fewer deep analyses

#### 7. inefficiency-detector.py

**Location:** `host-services/analysis/inefficiency-detector/inefficiency-detector.py`

**Current Behavior:**
- Scans all log entries for patterns
- Processes entire trace files

**Proposed Optimization:**
- Scout identifies high-signal log sections
- Focus on error/warning patterns first
- Sample representative entries from large logs

**Expected Reduction:** 50% token reduction on large logs

## Implementation Priority

Based on impact and effort, we recommend this implementation order:

| Phase | Tool | Impact | Effort | Notes |
|-------|------|--------|--------|-------|
| 1 | index-generator | HIGH | Medium | Highest file count reduction potential |
| 2 | drift-detector | HIGH | Medium | Runs frequently, compounds savings |
| 3 | confluence-doc-discoverer | MEDIUM | Low | Quick win, limited scope |
| 4 | beads-analyzer-processor | MEDIUM | Medium | Improves task context loading |
| 5 | adr-researcher | MEDIUM | Low | Small scope, quick implementation |
| 6 | inefficiency-detector | MEDIUM | Medium | Meta-improvement to efficiency tracking |

## Consequences

### Positive

- **Faster Analysis:** 50-80% reduction in execution time for heavy tools
- **Lower Token Costs:** LLMs process only relevant content
- **Better Scalability:** Performance degrades gracefully with repo size
- **Maintained Coverage:** Still analyze all directories, just read smarter

### Negative

- **Scout Overhead:** Additional LLM call per directory (mitigated by cheap prompt)
- **Heuristic Fallbacks Needed:** Must handle cases where Scout fails
- **Implementation Effort:** Each tool needs custom Scout logic

### Risks

- **Over-optimization:** Scout might skip important but unusual files
- **Mitigation:** Include "surprising files" instruction in Scout prompts
- **Mitigation:** Log what Scout skips for later review

## Alternatives Considered

### 1. Static Configuration Files

**Approach:** Define which files/directories to analyze in config

**Rejected because:**
- Doesn't adapt to different repository structures
- Requires manual maintenance
- Misses newly added important files

### 2. Historical Analysis

**Approach:** Track which files were useful in past analyses

**Rejected because:**
- Cold-start problem for new repos
- Past relevance may not predict current relevance
- Adds complexity with persistence layer

### 3. File Size/Complexity Heuristics

**Approach:** Prioritize larger files or files with more functions

**Rejected because:**
- Size doesn't correlate with importance
- Missing semantic understanding
- Would still read irrelevant large files

## References

- PR #407: Multi-Agent Feature Analyzer Implementation
- [ADR-LLM-Inefficiency-Reporting](../implemented/ADR-LLM-Inefficiency-Reporting.md)
- weekly_analyzer.py: Reference implementation of Scout pattern

---
*Authored by jib*
