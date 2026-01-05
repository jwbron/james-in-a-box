# ADR: Intelligent Documentation Drift Analysis and Correction

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Proposed

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Implementation Details](#implementation-details)
- [Architecture](#architecture)
- [Drift Detection Strategies](#drift-detection-strategies)
- [Correction Workflows](#correction-workflows)
- [Integration Points](#integration-points)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

james-in-a-box has established documentation infrastructure (ADRs, runbooks, code standards), but faces a fundamental challenge: **documentation drifts from reality as code evolves**. This creates several problems:

1. **Inaccurate Documentation:** Docs describe patterns that no longer exist in the codebase
2. **Missed Opportunities:** Code changes don't trigger documentation updates, leaving new patterns undocumented
3. **Manual Burden:** Engineers must remember to update docs when changing code
4. **Quality Decay:** Over time, documentation becomes less trustworthy, reducing its value
5. **Agent Confusion:** jib relies on documentation for context, but drift causes incorrect assumptions

**Current State:**

As noted in [ADR-LLM-Documentation-Index-Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md), we have:
- ✅ Documentation index architecture with navigation
- ✅ Manual documentation authoring workflows
- ❌ **No automated drift detection**
- ❌ **No systematic correction mechanism**
- ❌ **No proactive documentation maintenance**

The LLM Documentation Index ADR outlined drift detection conceptually but didn't specify:
- How drift is detected algorithmically
- When and how corrections are made
- What triggers analysis
- How to handle ambiguous cases (code wrong vs. docs wrong)

### What We're Deciding

This ADR defines the **automated system for detecting and correcting documentation drift**, including:

1. **Detection Strategy:** How to identify when documentation no longer matches code
2. **Analysis Intelligence:** How to determine whether code or documentation is "right"
3. **Correction Workflow:** How to fix drift (update docs, update code, or flag for human review)
4. **Trigger Mechanisms:** What events initiate drift analysis
5. **Integration:** How this fits with existing workflows (PR reviews, CI/CD, scheduled jobs)

### Key Requirements

**Functional:**
1. **Automated Detection:** Identify drift without manual checking
2. **Intelligent Analysis:** Distinguish outdated docs from intentional changes
3. **Actionable Output:** Generate specific correction recommendations
4. **Multi-Format Support:** Handle ADRs, runbooks, code comments, API docs
5. **Continuous Operation:** Run regularly without human intervention

**Non-Functional:**
1. **Accuracy:** Minimize false positives (flagging non-issues)
2. **Precision:** Provide specific line/section references, not vague warnings
3. **Scalability:** Handle growing codebase and documentation
4. **Transparency:** Explain why drift was detected and how to fix it
5. **Safety:** Never auto-commit documentation changes without review

### Industry Context

Documentation drift is a universal problem in software engineering:

| Approach | Examples | Limitations |
|----------|----------|-------------|
| **Manual Review** | PR checklists, doc review sprints | Doesn't scale, easy to skip |
| **Doc-in-Code** | JSDoc, Swagger/OpenAPI, docstrings | Limited to API docs, still drifts |
| **Generated Docs** | TypeDoc, Sphinx autodoc | Only covers code structure, not patterns |
| **LLM Analysis** | Emerging (DocAider, AI code review tools) | New space, few production implementations |

**Opportunity:** LLMs can analyze code semantically, compare to documentation prose, and identify drift that traditional tools miss.

## Decision

**We will implement an automated documentation drift analysis system powered by LLM-based semantic comparison with multi-stage correction workflows.**

### Core Principles

1. **Analyze, Don't Assume:** Compare actual code to documented patterns using semantic understanding
2. **Recommend, Don't Auto-Fix:** Generate PRs for review; never silently change docs
3. **Context-Aware:** Consider recent commits, PR descriptions, and ADR history
4. **Prioritize High-Impact:** Focus on critical docs (ADRs, security patterns, API contracts)
5. **Continuous Improvement:** Learn from accepted/rejected drift corrections

### Approach Summary

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| **Drift Detector** | Identify code-doc mismatches | LLM semantic comparison + tree-sitter |
| **Context Analyzer** | Determine if drift is intentional | Git history, PR metadata, ADR status |
| **Correction Generator** | Create specific fix recommendations | LLM generates doc updates or code warnings |
| **Review Workflow** | Human validates corrections | PR creation with explanation |
| **Scheduler** | Trigger analysis | Post-merge, weekly, and on-demand |
| **FEATURES.md** | Feature-to-source mapping | Maps features to implementation files |

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Detection Method** | LLM semantic comparison + AST analysis | Catches semantic drift, not just syntactic | Pure regex (too brittle), pure LLM (too expensive) |
| **Correction Mode** | PR-based review | Safety, learning opportunity | Auto-commit (unsafe), notification-only (low action rate) |
| **Trigger Strategy** | Multi-trigger (post-merge + scheduled) | Catches drift early and comprehensively | Only scheduled (too late), only pre-merge (blocks PRs) |
| **Scope Prioritization** | High-impact docs first | Limited LLM budget, maximize value | All docs equally (too expensive) |
| **Context Sources** | Git history + PR metadata + ADRs | Rich context for intent analysis | Code-only (misses why), docs-only (misses evolution) |

## Implementation Details

### 1. Architecture

**System Components:**

```
┌─────────────────────────────────────────────────────────────────┐
│           Documentation Drift Analysis System                    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    TRIGGER LAYER                             │ │
│  │  - Post-merge hook (GitHub Actions or local git hook)       │ │
│  │  - Weekly scheduled job (systemd timer)                     │ │
│  │  - Manual invocation (bin/jib-doc-analyzer)                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    DETECTION LAYER                           │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │ Code Structure Analyzer (tree-sitter)                 │  │ │
│  │  │ - Extract classes, functions, patterns                │  │ │
│  │  │ - Generate codebase index                             │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │ Documentation Parser                                   │  │ │
│  │  │ - Extract claims from ADRs, guides, docstrings        │  │ │
│  │  │ - Identify documented patterns                        │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │ Semantic Comparator (LLM)                             │  │ │
│  │  │ - Compare code patterns to documented patterns        │  │ │
│  │  │ - Flag discrepancies with severity                    │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    ANALYSIS LAYER                            │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │ Context Analyzer                                       │  │ │
│  │  │ - Check git history for intentional change            │  │ │
│  │  │ - Review PR descriptions for context                  │  │ │
│  │  │ - Check ADR status (superseded, in-progress)          │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │ Priority Classifier                                    │  │ │
│  │  │ - Critical: Security, API contracts, ADRs             │  │ │
│  │  │ - High: Code standards, architecture patterns         │  │ │
│  │  │ - Medium: Implementation guides, examples             │  │ │
│  │  │ - Low: Comments, minor details                        │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    CORRECTION LAYER                          │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │ Correction Generator (LLM)                            │  │ │
│  │  │ - Generate doc updates for outdated documentation     │  │ │
│  │  │ - Generate code warnings for intentional deviations   │  │ │
│  │  │ - Create ADR update proposals                         │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │ PR Creator                                             │  │ │
│  │  │ - Create branch with corrections                      │  │ │
│  │  │ - Generate PR with explanation and evidence           │  │ │
│  │  │ - Tag for human review                                │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    OUTPUT LAYER                              │ │
│  │  - Pull requests with corrections                           │ │
│  │  - Drift reports (~/sharing/analysis/doc-drift/)            │ │
│  │  - Slack notifications for high-priority drift              │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Drift Detection Strategies

**2.1 Pattern-Based Detection**

Identify common drift patterns:

| Pattern | Code Reality | Documentation Claims | Detection Method |
|---------|-------------|---------------------|------------------|
| **Removed Pattern** | Code no longer uses approach X | Docs say "we use X" | Search codebase for pattern, find zero matches |
| **New Pattern** | Codebase consistently uses Y | Docs don't mention Y | Detect pattern frequency, check docs for mention |
| **API Change** | Function signature changed | Docs show old signature | AST comparison of function definitions |
| **Deprecated Practice** | Old pattern still documented | Code moved to new pattern | Pattern frequency analysis + recency |
| **Config Drift** | Config values changed | Docs show old values | Parse config files, compare to doc examples |

**2.2 Semantic Comparison Workflow**

For each documentation claim:

```python
# Simplified detection logic
def detect_drift(doc_claim: str, codebase_index: dict) -> DriftReport:
    """
    Compare documentation claim to actual code.

    Example:
    doc_claim = "We use PyJWT with HS256 algorithm for token validation"
    codebase_index = {
        "auth_patterns": {
            "jwt_algorithm": ["RS256", "RS256", "RS256"],  # Found 3 uses of RS256
            "jwt_library": ["PyJWT", "PyJWT"]
        }
    }

    Returns:
    DriftReport(
        severity="high",
        drift_type="algorithm_mismatch",
        claim="HS256 algorithm",
        reality="RS256 algorithm (3 instances)",
        recommendation="Update docs to reflect RS256"
    )
    """

    # Stage 1: Extract testable assertions from claim
    assertions = extract_assertions(doc_claim)
    # e.g., ["library=PyJWT", "algorithm=HS256"]

    # Stage 2: Query codebase for evidence
    evidence = query_codebase(assertions, codebase_index)

    # Stage 3: LLM semantic comparison
    comparison = llm_compare(
        claim=doc_claim,
        evidence=evidence,
        context={"doc_path": "...", "last_modified": "..."}
    )

    # Stage 4: Classify drift
    if comparison.matches:
        return None  # No drift
    elif comparison.partial_match:
        return DriftReport(severity="medium", ...)
    else:
        return DriftReport(severity="high", ...)
```

**2.3 Context Analysis for Intent Detection**

Determine if drift is intentional:

```python
def analyze_drift_intent(drift: DriftReport, repo_history: GitHistory) -> IntentAnalysis:
    """
    Check if drift was intentional or accidental oversight.

    Example:
    drift = DriftReport(
        claim="We use HS256",
        reality="Code uses RS256",
        affected_files=["src/auth/jwt.py"]
    )

    Returns:
    IntentAnalysis(
        intentional=True,
        evidence=[
            "PR #234 'Migrate to RS256 for improved security' changed algorithm",
            "ADR-042 recommends RS256 for JWT validation",
            "Commit msg: 'Switch to asymmetric signing per security review'"
        ],
        recommendation="Update docs to reflect intentional change to RS256"
    )
    """

    # Check 1: Recent PRs affecting same area
    related_prs = repo_history.search_prs(
        files=drift.affected_files,
        merged_within_days=180
    )

    # Check 2: ADRs related to the topic
    related_adrs = search_adrs(topic=drift.topic)

    # Check 3: Commit messages mentioning the change
    related_commits = repo_history.search_commits(
        files=drift.affected_files,
        keywords=[drift.claim_keyword, drift.reality_keyword]
    )

    # LLM synthesis
    intent = llm_analyze_intent(
        drift=drift,
        prs=related_prs,
        adrs=related_adrs,
        commits=related_commits
    )

    return intent
```

### 3. Correction Workflows

**3.1 Documentation Update (Most Common)**

When code is correct but docs are stale:

```markdown
**Drift Detected:**
- **Document:** `docs/standards/authentication.md:45`
- **Claim:** "We use HS256 algorithm for JWT signing"
- **Reality:** Codebase uses RS256 (8 instances across auth module)
- **Evidence:**
  - `src/auth/jwt_validator.py:23`: `algorithm="RS256"`
  - `src/auth/token_generator.py:67`: `jwt.encode(..., algorithm="RS256")`
- **Context:**
  - PR #234 (merged 2025-10-15): "Migrate to RS256 per security review"
  - ADR-042: Recommends asymmetric algorithms for production

**Recommended Fix:**
Update `docs/standards/authentication.md:45` to:
```
We use RS256 (asymmetric) algorithm for JWT signing, providing better
security than symmetric algorithms. Migration completed in PR #234 (Oct 2025).
```

**Correction PR:**
Creates branch `docs/fix-jwt-algorithm-drift` with:
- Updated documentation
- Link to PR #234 for context
- Reference to ADR-042
```

**3.2 Code Warning (Code Violates Standards)**

When documentation is correct but code deviates:

```markdown
**Drift Detected:**
- **Document:** `docs/standards/api-design.md:12`
- **Claim:** "All API endpoints must use plural resource names (e.g., /users, /posts)"
- **Reality:** Found 3 endpoints with singular names
- **Violations:**
  - `src/api/user.py:45`: `@app.route("/user/<id>")`
  - `src/api/comment.py:23`: `@app.route("/comment/<id>")`
- **Context:**
  - ADR-028: Established REST conventions (2024-06-10)
  - These endpoints predate ADR-028 (created 2024-02-15)

**Recommended Fix:**
Two options:
1. **Update code** to follow standard (preferred):
   - Rename `/user/<id>` to `/users/<id>`
   - Add deprecation notice for old endpoints
2. **Document exception** if intentional:
   - Add "Legacy Exceptions" section to ADR-028
   - Explain why these endpoints remain singular

**Correction PR:**
Creates issue for team discussion: "API endpoint naming drift detected"
```

**3.3 Ambiguous Cases (Human Decision Required)**

When it's unclear which is correct:

```markdown
**Drift Detected:**
- **Document:** `docs/guides/deployment.md:89`
- **Claim:** "Database migrations run automatically on deployment"
- **Reality:** Code shows manual migration step in deploy script
- **Evidence:**
  - `scripts/deploy.sh:45`: `# TODO: Run migrations manually after deployment`
  - `src/db/migrator.py`: No automatic trigger on startup
- **Context:**
  - ADR-015: Recommends automated migrations
  - Recent incidents log (Oct 2025): Migration failures on auto-run

**Ambiguous:**
Unclear if:
- Auto-migrations were disabled due to incidents (intentional deviation)
- Auto-migrations were never implemented (doc is aspirational)
- Auto-migrations exist but in different location (detection error)

**Recommended Action:**
Create GitHub issue for team discussion:
- "Clarify migration automation status"
- Tag: documentation-drift, needs-triage
- Assign: Platform team
```

### 4. Integration Points

**Integration with FEATURES.md:**

This ADR integrates with [ADR-Feature-Analyzer-Documentation-Sync](../implemented/ADR-Feature-Analyzer-Documentation-Sync.md) to leverage FEATURES.md as a core data source for drift detection.

**FEATURES.md provides:**
- Authoritative feature-to-source mapping
- Feature status tracking (not-implemented, in-progress, implemented)
- Implementation file locations for each feature

**Drift analyzer uses FEATURES.md to:**
- Map documented features to actual code locations
- Verify feature status matches documentation claims
- Detect when documented features no longer exist or have changed
- Prioritize drift detection based on feature criticality

See "Strategy 4: Feature-Based Drift Detection" below for implementation details.

**4.1 Post-Merge Hook**

Run lightweight drift detection after PRs merge:

```yaml
# .github/workflows/doc-drift-check.yml
name: Documentation Drift Detection
on:
  push:
    branches: [main]

jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 100  # Need history for context analysis

      - name: Run drift detector on changed files
        run: |
          # Only analyze docs related to changed code files
          bin/jib-doc-analyzer \
            --mode incremental \
            --changed-files "${{ github.event.commits.*.modified }}" \
            --create-pr-if-drift
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**4.2 Scheduled Comprehensive Analysis**

Weekly deep analysis of all documentation:

```bash
# host-services/analysis/doc-drift-analyzer/doc-drift-analyzer.timer
[Unit]
Description=Weekly documentation drift analysis
Requires=doc-drift-analyzer.service

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
```

```python
# host-services/analysis/doc-drift-analyzer/doc-drift-analyzer.py
#!/usr/bin/env python3
"""
Documentation Drift Analyzer for jib (James-in-a-Box)

Analyzes codebase against documentation to detect and correct drift.

Modes:
  - incremental: Analyze docs related to recently changed code (fast, post-merge)
  - comprehensive: Analyze all documentation (slow, weekly)
  - targeted: Analyze specific docs (manual, on-demand)

Outputs:
  - Drift reports: ~/sharing/analysis/doc-drift/
  - Correction PRs: Created automatically with explanations
  - Slack notifications: High-priority drift alerts

Usage:
    doc-drift-analyzer.py --mode comprehensive
    doc-drift-analyzer.py --mode incremental --changed-files "src/auth/*.py"
    doc-drift-analyzer.py --mode targeted --docs "docs/adr/ADR-042.md"
"""

def main():
    parser = argparse.ArgumentParser(description="Documentation drift analysis")
    parser.add_argument("--mode", choices=["incremental", "comprehensive", "targeted"])
    parser.add_argument("--changed-files", help="Files changed in recent commits")
    parser.add_argument("--docs", help="Specific docs to analyze")
    parser.add_argument("--create-pr", action="store_true", help="Auto-create PR for fixes")

    args = parser.parse_args()

    # Stage 1: Build codebase index
    codebase_index = build_codebase_index()

    # Stage 2: Select docs to analyze
    if args.mode == "incremental":
        docs = find_related_docs(args.changed_files)
    elif args.mode == "comprehensive":
        docs = find_all_docs()
    else:
        docs = [args.docs]

    # Stage 3: Detect drift
    drift_reports = []
    for doc in docs:
        drifts = detect_drift_in_doc(doc, codebase_index)
        drift_reports.extend(drifts)

    # Stage 4: Analyze intent
    analyzed_drifts = []
    for drift in drift_reports:
        intent = analyze_drift_intent(drift, git_history)
        analyzed_drifts.append((drift, intent))

    # Stage 5: Generate corrections
    corrections = []
    for drift, intent in analyzed_drifts:
        correction = generate_correction(drift, intent)
        corrections.append(correction)

    # Stage 6: Output
    save_drift_report(analyzed_drifts, corrections)

    if args.create_pr:
        for correction in corrections:
            create_correction_pr(correction)

    notify_high_priority_drift(analyzed_drifts)
```

**4.3 Manual Invocation**

On-demand analysis for specific investigations:

```bash
# Analyze specific ADR
bin/jib-doc-analyzer --mode targeted --docs "docs/adr/ADR-042.md"

# Analyze all security documentation
bin/jib-doc-analyzer --mode targeted --docs "docs/security/**/*.md"

# Analyze docs related to authentication module
bin/jib-doc-analyzer --mode incremental --changed-files "src/auth/**/*.py" --force
```

### 5. Prioritization Strategy

Not all drift is equally important. Prioritize by:

| Priority | Documentation Type | Impact | Response Time |
|----------|-------------------|--------|---------------|
| **Critical** | ADRs (implemented), API contracts, security patterns | Breaking assumptions | Immediate PR + Slack alert |
| **High** | Code standards, architecture guides, deployment runbooks | Confusion, errors | PR within 24h |
| **Medium** | Implementation examples, testing guides | Inefficiency | Weekly batch PR |
| **Low** | Code comments, minor details | Minor annoyance | Monthly batch PR or ignore |

**Severity Calculation:**

```python
def calculate_drift_severity(drift: DriftReport, doc_metadata: dict) -> str:
    """
    Determine drift priority.

    Factors:
    - Document type (ADR > guide > comment)
    - Document status (implemented > proposed)
    - Scope of impact (affects multiple modules > single file)
    - Recency (recent changes more important than old drift)
    """

    severity_score = 0

    # Document type weight
    if doc_metadata.get("type") == "adr":
        severity_score += 40
    elif doc_metadata.get("type") == "api_contract":
        severity_score += 35
    elif doc_metadata.get("type") == "security":
        severity_score += 30
    elif doc_metadata.get("type") == "standard":
        severity_score += 20
    elif doc_metadata.get("type") == "guide":
        severity_score += 10

    # Status weight (only for ADRs)
    if doc_metadata.get("status") == "implemented":
        severity_score += 20
    elif doc_metadata.get("status") == "in_progress":
        severity_score += 10

    # Scope weight
    if drift.affected_file_count > 10:
        severity_score += 20
    elif drift.affected_file_count > 5:
        severity_score += 10

    # Recency weight
    if drift.change_age_days < 30:
        severity_score += 15
    elif drift.change_age_days < 90:
        severity_score += 10

    # Map score to severity
    if severity_score >= 70:
        return "critical"
    elif severity_score >= 50:
        return "high"
    elif severity_score >= 30:
        return "medium"
    else:
        return "low"
```

## Drift Detection Strategies

### Strategy 1: AST-Based Structural Comparison

For code structure documentation (class hierarchies, function signatures):

```python
# Example: Detect function signature drift
def detect_function_signature_drift(doc: str, codebase: dict) -> list[Drift]:
    """
    Compare documented function signatures to actual implementations.

    Example:
    Doc says: "validate_token(token: str, algorithm: str = 'HS256') -> bool"
    Code has: "validate_token(token: str, algorithm: str = 'RS256') -> dict"

    Detects:
    - Default value change (HS256 -> RS256)
    - Return type change (bool -> dict)
    """

    # Parse doc examples for function signatures
    doc_signatures = extract_function_signatures(doc)

    drifts = []
    for sig in doc_signatures:
        # Find actual function in codebase
        actual_func = codebase.find_function(sig.name)

        if not actual_func:
            drifts.append(Drift(
                type="function_removed",
                claim=f"Function {sig.name} exists",
                reality="Function not found in codebase"
            ))
            continue

        # Compare signatures
        if sig.signature != actual_func.signature:
            drifts.append(Drift(
                type="signature_mismatch",
                claim=f"{sig.signature}",
                reality=f"{actual_func.signature}",
                file=actual_func.file,
                line=actual_func.line
            ))

    return drifts
```

### Strategy 2: Pattern Frequency Analysis

For architectural patterns and conventions:

```python
def detect_pattern_drift(doc: str, codebase: dict) -> list[Drift]:
    """
    Compare documented patterns to actual usage frequency.

    Example:
    Doc says: "We use async/await for all I/O operations"
    Code analysis finds:
    - 45 async functions
    - 23 callback-based functions (old pattern)

    Detects mixed usage, suggests doc update or code migration.
    """

    # Extract pattern claims
    pattern_claims = extract_pattern_claims(doc)
    # e.g., ["use async/await for I/O", "JWT with RS256", "plural API resources"]

    drifts = []
    for claim in pattern_claims:
        # Analyze pattern usage in codebase
        usage = analyze_pattern_usage(claim, codebase)

        if usage.consistency < 0.8:  # Less than 80% consistent
            drifts.append(Drift(
                type="inconsistent_pattern",
                claim=claim.description,
                reality=f"{usage.conforming_count} conforming, {usage.violating_count} violating",
                examples=usage.violating_examples[:5],
                severity="high" if claim.is_standard else "medium"
            ))

    return drifts
```

### Strategy 3: Semantic Claim Validation

For complex architectural descriptions:

```python
def detect_semantic_drift(doc: str, codebase: dict) -> list[Drift]:
    """
    Use LLM to validate high-level claims against code.

    Example:
    Doc says: "User authentication uses JWT tokens stored in Redis sessions"
    LLM analyzes code and finds: "JWT tokens are validated but not stored;
    sessions use database-backed session middleware"

    Detects semantic mismatch even if individual keywords exist.
    """

    # Extract high-level claims
    claims = extract_semantic_claims(doc)

    drifts = []
    for claim in claims:
        # Gather code evidence
        relevant_code = codebase.search_related_code(claim.keywords)

        # LLM validation
        validation = llm_validate_claim(
            claim=claim.text,
            code_snippets=relevant_code,
            context={"doc_path": doc.path, "claim_line": claim.line}
        )

        if not validation.is_accurate:
            drifts.append(Drift(
                type="semantic_mismatch",
                claim=claim.text,
                reality=validation.actual_implementation,
                explanation=validation.explanation,
                severity="high" if claim.is_architectural else "medium"
            ))

    return drifts
```

### Strategy 4: Feature-Based Drift Detection

For feature documentation using FEATURES.md mapping:

```python
def detect_feature_drift(doc: str, features_md: dict) -> list[Drift]:
    """
    Use FEATURES.md to validate documented features against actual code.

    Example:
    Doc says: "The GitHub watcher monitors PRs and creates jib tasks per ADR-GitHub-Integration"

    FEATURES.md shows:
    - Feature: "GitHub Watcher Service"
    - Status: "implemented"
    - Files: ["host-services/analysis/github-watcher/watcher.py"]

    Validates:
    1. Feature exists in FEATURES.md
    2. Implementation files are present
    3. Feature status matches documentation claims
    4. Referenced ADR status is correct
    """

    # Extract feature mentions from documentation
    doc_features = extract_feature_mentions(doc)

    drifts = []
    for feature_name in doc_features:
        # Look up feature in FEATURES.md
        feature = features_md.get(feature_name)

        if not feature:
            drifts.append(Drift(
                type="feature_not_found",
                claim=f"Feature '{feature_name}' exists",
                reality="Feature not found in FEATURES.md",
                severity="high",
                recommendation=f"Verify feature exists or update documentation"
            ))
            continue

        # Verify implementation files exist
        missing_files = []
        for file_path in feature.get('files', []):
            if not os.path.exists(file_path):
                missing_files.append(file_path)

        if missing_files:
            drifts.append(Drift(
                type="feature_files_missing",
                claim=f"Feature '{feature_name}' implemented in {feature['files']}",
                reality=f"Files missing: {missing_files}",
                severity="high",
                file=feature['files'][0] if feature['files'] else None
            ))

        # Check status alignment
        doc_status = extract_feature_status_from_doc(doc, feature_name)
        if doc_status and doc_status != feature.get('status'):
            drifts.append(Drift(
                type="feature_status_mismatch",
                claim=f"Feature '{feature_name}' is {doc_status}",
                reality=f"FEATURES.md shows status: {feature.get('status')}",
                severity="medium",
                recommendation=f"Update documentation to reflect current status"
            ))

    return drifts
```

**Why Feature-Based Detection Matters:**

FEATURES.md provides the **authoritative mapping** between high-level features and low-level code:

**For Drift Detection:**
- Knows which files implement which features
- Provides feature status (not-implemented, in-progress, implemented)
- Maps documentation claims to actual source locations

**For Impact Analysis:**
- Changes to feature files should trigger doc updates for related documentation
- Deprecated features trigger removal of documentation
- Status changes (implemented → deprecated) trigger doc updates

**For Validation:**
- Can verify documented features actually exist in the codebase
- Can check if feature claims align with FEATURES.md status
- Can detect when features are removed but docs still reference them

**Example Use Case:**

**Documentation says:**
> "The GitHub watcher monitors PRs and creates jib tasks per ADR-GitHub-Integration"

**Drift analyzer with FEATURES.md:**
1. Checks FEATURES.md for "GitHub watcher" feature
2. Finds it maps to `host-services/analysis/github-watcher/`
3. Verifies that directory still exists and contains PR monitoring code
4. Validates ADR-GitHub-Integration status is "implemented"
5. **If drift detected**: Creates PR updating docs

**Without FEATURES.md:**
- Drift analyzer must guess which files implement "GitHub watcher"
- May miss related files or check wrong locations
- Higher false positive/negative rate
- No authoritative source for feature status

**Integration with Feature Analyzer:**

This creates a complete documentation loop:
- **FEATURES.md → Drift Analyzer**: Provides feature context for drift detection
- **Drift Analyzer → Documentation**: Proposes doc updates when drift detected
- **Codebase Analyzer → FEATURES.md**: Keeps feature list current (per ADR-Feature-Analyzer-Documentation-Sync)

## Correction Workflows

### Workflow 1: Simple Documentation Update

**Trigger:** Code is correct, docs are outdated, high confidence

```
Drift Detected → Generate Doc Update → Create PR → Human Review → Merge
```

**PR Format:**

```markdown
## Summary
Fix documentation drift in authentication guide

**Drift detected:**
- Docs claim HS256 algorithm
- Code uses RS256 (intentionally, per PR #234)

## Changes
- Updated `docs/standards/authentication.md:45`
- Corrected algorithm reference (HS256 → RS256)
- Added link to PR #234 for context

## Evidence
- `src/auth/jwt_validator.py:23`: Uses RS256
- PR #234 (merged 2025-10-15): "Migrate to RS256 per security review"
- ADR-042: Recommends asymmetric algorithms

## Test plan
- [x] Documentation renders correctly
- [x] Links to PR #234 are valid
- [x] Technical accuracy verified against codebase

---
*— Automated drift correction by jib*
```

### Workflow 2: Code Standard Violation

**Trigger:** Docs are correct (represent standard), code violates

```
Drift Detected → Assess Scope → Create Issue/PR → Human Decides
```

**Options:**

1. **Small violation scope (<5 files):** Create PR fixing code
2. **Large violation scope (>5 files):** Create issue for team discussion
3. **Legacy code exemption:** Update docs to note exceptions

**GitHub Issue Format:**

```markdown
## Code Standard Violation Detected

**Standard:** API endpoints must use plural resource names
**Source:** `docs/standards/api-design.md:12` (ADR-028)

**Violations Found:**
- `src/api/user.py:45`: `/user/<id>` (should be `/users/<id>`)
- `src/api/comment.py:23`: `/comment/<id>` (should be `/comments/<id>`)
- `src/api/post.py:67`: `/post/<id>` (should be `/posts/<id>`)

**Context:**
- These endpoints predate ADR-028 (created 2024-02-15)
- ADR-028 established standard (2024-06-10)
- No breaking changes since standard adoption

**Options:**
1. **Update endpoints** to follow standard (preferred)
   - Add deprecation notices for old paths
   - Document migration in changelog
2. **Document exception** if intentional
   - Add "Legacy Exceptions" section to ADR-028

**Recommendation:** Update endpoints (Option 1)
- Low risk (internal API, controllable clients)
- Improves consistency
- Prevents future confusion

---
*— Automated drift detection by jib*

Labels: documentation-drift, api-standards, needs-triage
```

### Workflow 3: Ambiguous Drift

**Trigger:** Unclear which is correct, requires human judgment

```
Drift Detected → Gather Context → Create Discussion Issue → Tag Team
```

**GitHub Discussion Format:**

```markdown
## Documentation Drift Needs Review

**Document:** `docs/guides/deployment.md:89`
**Claim:** "Database migrations run automatically on deployment"
**Code Reality:** Manual migration step in deploy script

**Ambiguity:**
Cannot determine if:
1. Auto-migrations were intentionally disabled (code is correct)
2. Auto-migrations were never implemented (docs are aspirational)
3. Auto-migrations exist elsewhere (detection incomplete)

**Evidence:**
✅ **Supporting docs:**
- ADR-015: Recommends automated migrations
- Original design doc: Auto-migrations on startup

❌ **Contradicting code:**
- `scripts/deploy.sh:45`: Manual migration step with TODO comment
- `src/db/migrator.py`: No automatic trigger found

⚠️ **Context:**
- Incident log (Oct 2025): Migration failures on auto-run
- Recent rollback (2025-10-20): Migration caused downtime

**Questions for Team:**
1. Were auto-migrations disabled after incidents? (If yes, update docs)
2. Are auto-migrations planned but not implemented? (If yes, track as TODO)
3. Is the deployment guide outdated? (If yes, update)

**Suggested Action:**
Team discussion to determine current state, then:
- Update docs to match reality, OR
- Create ticket to implement auto-migrations

---
*— Automated drift detection by jib*

Labels: documentation-drift, deployment, needs-discussion
Assignees: @platform-team
```

## Migration Strategy

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Basic drift detection for high-priority docs

1. Implement codebase indexer (reuse from ADR-LLM-Documentation-Index-Strategy)
2. Create documentation claim extractor
3. Build basic semantic comparator
4. Manual testing on 3-5 ADRs

**Success Criteria:**
- Detect drift in at least 2 known outdated ADRs
- Generate actionable correction recommendations

### Phase 2: Automation (Weeks 3-4)

**Goal:** Automated detection and correction PR creation

**Dependencies:** Phase 1 complete

1. Implement context analyzer (git history, PR metadata)
2. Create correction generator
3. Build PR creation workflow
4. Set up post-merge GitHub Action hook

**Success Criteria:**
- Automatically create PR for detected drift within 24h of merge
- Zero false positive PRs in first week

### Phase 3: Expansion (Weeks 5-6)

**Goal:** Comprehensive coverage and scheduled analysis

**Dependencies:** Phase 2 complete, feedback incorporated

1. Extend to all doc types (guides, runbooks, API docs)
2. Implement priority classifier
3. Set up weekly scheduled analysis (systemd timer)
4. Add Slack notifications for critical drift

**Success Criteria:**
- Weekly comprehensive analysis completes in <30 minutes
- High-priority drift notifications have <5% false positive rate

### Phase 4: Intelligence (Weeks 7-8)

**Goal:** Smarter detection and learning from feedback

**Dependencies:** Phase 3 complete, 4+ weeks of data

1. Analyze accepted vs. rejected drift corrections
2. Refine severity scoring based on human feedback
3. Implement feedback loop (learn from PR review comments)
4. Add support for ambiguous case handling

**Success Criteria:**
- Correction PR acceptance rate >80%
- False positive rate <10%
- System learns from at least 20 reviewed corrections

## Consequences

### Benefits

1. **Always-Accurate Docs:** Documentation stays synchronized with code automatically
2. **Reduced Manual Burden:** Engineers don't have to remember to update docs
3. **Improved Trust:** Team trusts docs more when they're reliably current
4. **Better Agent Performance:** jib relies on accurate docs for context
5. **Early Violation Detection:** Catch code standard violations before they spread
6. **Knowledge Preservation:** Document why changes happened (via git context)
7. **Continuous Improvement:** System learns from corrections over time

### Drawbacks

1. **Initial Setup Effort:** Building detection system takes significant time
2. **LLM Costs:** Semantic comparison requires API calls (potentially expensive at scale)
3. **False Positives:** Will occasionally flag non-issues, requiring human review
4. **Maintenance:** Detector itself needs maintenance as codebase evolves
5. **Context Gathering:** Git history analysis adds complexity
6. **Notification Fatigue:** Too many drift PRs could overwhelm reviewers

### Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **High false positive rate** | Team ignores drift PRs | Start with high-confidence cases only; refine gradually |
| **Expensive LLM usage** | Budget overrun | Use cheaper models for initial filtering; LLM only for final validation |
| **Ambiguous cases** | System stuck, no action taken | Explicit ambiguous case workflow with human escalation |
| **Detection misses real drift** | Docs still become stale | Combine multiple detection strategies; scheduled comprehensive analysis |
| **Correction breaks docs** | Incorrect auto-updates | Never auto-merge; always require human review |
| **Performance impact** | Slow PR merges | Run asynchronously post-merge; don't block CI/CD |

## Decision Permanence

**Medium permanence.**

The general approach (automated drift detection + correction PRs) is likely stable, but implementation details will evolve:

**Low-permanence elements:**
- Specific LLM models used
- Severity scoring thresholds
- Detection algorithms (will improve over time)
- Scheduling frequencies

**Higher-permanence elements:**
- PR-based correction workflow (safe, reviewable)
- Multi-strategy detection approach
- Priority-based analysis
- Human-in-the-loop for ambiguous cases

**Evolution path:**
- Phase 1-4: Manual tuning, learning from feedback
- Phase 5+: Machine learning from historical corrections
- Long-term: Potential integration with IDE (real-time drift warnings)

## Alternatives Considered

### Alternative 1: Manual Doc Review Process

**Description:** Establish human-driven quarterly doc review sprints

**Pros:**
- Simple, no automation complexity
- Human judgment on all corrections
- No LLM costs

**Cons:**
- Doesn't scale (docs grow faster than review capacity)
- Drift accumulates between reviews
- Requires dedicated engineering time
- Low compliance (easy to skip)

**Rejected because:** Automation is necessary for maintaining doc quality at scale.

### Alternative 2: Doc-in-Code Only (No Separate Docs)

**Description:** Eliminate separate documentation; rely on docstrings, type hints, generated docs

**Pros:**
- Drift impossible (docs are code)
- Single source of truth
- Tooling well-established (Sphinx, TypeDoc)

**Cons:**
- Only works for API docs, not architectural decisions
- No place for "why" (ADRs, design rationale)
- Poor for high-level guides and runbooks
- Code comments still drift from implementation

**Rejected because:** Complementary approach, not replacement. We need both code-level and system-level documentation.

### Alternative 3: Block PRs on Doc Drift

**Description:** Pre-merge check that fails if docs are out of sync

**Pros:**
- Catches drift immediately
- Forces engineers to update docs
- Zero doc debt accumulation

**Cons:**
- Blocks development velocity
- High false positive rate would frustrate engineers
- Not all code changes require doc updates
- Engineers may write incorrect updates just to pass check

**Rejected because:** Too disruptive. Post-merge detection with PRs is less invasive.

### Alternative 4: Wiki-Style Docs (Community Edits)

**Description:** Use wiki or collaborative doc platform, rely on community maintenance

**Pros:**
- Low friction for updates
- Anyone can fix drift
- No formal review process

**Cons:**
- Quality control difficult
- No version control (or weak version control)
- Drift still happens (just easier to fix manually)
- No automated detection

**Rejected because:** Doesn't solve detection problem, reduces quality control.

### Alternative 5: Notification-Only (No PR Creation)

**Description:** Detect drift and notify team, but don't create correction PRs

**Pros:**
- Simpler implementation
- Less "spam" (no automated PRs)
- Human decides when/how to fix

**Cons:**
- Low action rate (notifications often ignored)
- Drift accumulates despite detection
- No clear ownership of fixes

**Rejected because:** Notifications alone have poor follow-through. PRs create actionable items.

## References

### Industry Tools and Approaches

- [DocAider](https://techcommunity.microsoft.com/blog/educatordeveloperblog/docaider-automated-documentation-maintenance-for-open-source-github-repositories/4245588) - Microsoft's automated documentation maintenance
- [Mintlify](https://mintlify.com/blog/ai-documentation) - AI-powered doc generation and maintenance
- [Swimm](https://swimm.io/blog/continuous-documentation) - Continuous documentation for code
- [Stepsize](https://www.stepsize.com/blog/technical-debt-detection) - Technical debt detection including doc drift

### Academic Research

- [Automatic Detection of Outdated Comments](https://ieeexplore.ieee.org/document/9240704) - IEEE 2020
- [Documenting Code: A Large-Scale Study](https://arxiv.org/abs/1908.02275) - ICSE 2020

### Related Standards

- [docs-as-code](https://www.writethedocs.org/guide/docs-as-code/) - Write the Docs community
- [ADR Process](https://adr.github.io/) - Architecture Decision Records
- [Documentation Quality](https://documentation.divio.com/) - Divio documentation system

### Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-LLM-Documentation-Index-Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md) | Provides codebase index infrastructure that drift detection builds on |
| [ADR-Feature-Analyzer-Documentation-Sync](../implemented/ADR-Feature-Analyzer-Documentation-Sync.md) | Maintains FEATURES.md which drift detection uses as authoritative feature-to-source mapping |
| [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) | jib needs accurate docs to function autonomously; drift detection ensures quality |

---

**Last Updated:** 2025-11-30
**Next Review:** 2026-01-30 (After Phase 1 implementation)
**Status:** Proposed
