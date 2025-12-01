# ADR: Feature Analyzer - Documentation Sync Workflow

**Driver:** James Wiesebron
**Approver:** James Wiesebron
**Status:** Implemented
**Proposed:** November 2025
**Implemented:** December 2025

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Implementation Details](#implementation-details)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

Currently, ADR implementation and documentation updates are disconnected processes:

1. **ADR workflow**: ADR is proposed → reviewed → approved → implemented → merged
2. **Documentation gap**: After ADR merge, relevant documentation in the codebase is not systematically updated
3. **Manual tracking**: Engineers must remember to update docs after ADR implementation
4. **Drift risk**: Implemented ADRs don't reflect in user-facing guides, READMEs, or code comments

**Example scenario:**
- ADR proposes using MCP servers for context sync
- ADR is approved and implementation PR is merged
- `docs/setup/README.md`, `CLAUDE.md`, and related guides still reference old approach
- Users discover outdated instructions

**Current State:**

james-in-a-box has:
- ADRs organized by status (`not-implemented/`, `in-progress/`, `implemented/`)
- Documentation index in `docs/index.md`
- No automated link between ADR implementation and documentation updates
- No structured feature-to-source mapping (FEATURES.md will be created as part of this ADR's implementation)

### What We're Deciding

This ADR establishes a **feature analyzer** responsible for maintaining FEATURES.md and related documentation through two mechanisms:

**1. ADR-Triggered Documentation Sync:**
- ADRs trigger documentation updates after implementation and merge
- Feature analyzer detects which docs need updating based on ADR content
- Updates are proposed as PRs for human review
- Documentation stays synchronized with architectural decisions

**2. Weekly Code Analysis:**
- Automatically scan all merged code to identify new features, components, and capabilities
- Update FEATURES.md with newly discovered features
- Remove or update entries for deprecated/changed features
- Ensure FEATURES.md accurately reflects the codebase's current state

### Goals

**Primary Goals:**
1. **Maintain FEATURES.md:** Automatically keep the feature list current by analyzing both ADRs and merged code
2. **Automate doc discovery:** Identify which documentation is affected by each ADR
3. **Prevent doc drift:** Ensure docs reflect implemented ADRs
4. **Maintain quality:** Human review all auto-generated doc updates
5. **Low friction:** Minimal manual tracking of what needs updating

**Secondary Goals:**
- Automatically analyze all merged code weekly to identify new features
- Remove or update feature entries as code evolves
- Ensure FEATURES.md accurately reflects the current state of the codebase

**Non-Goals:**
- Automatically merge documentation PRs without review
- Replace human documentation writing entirely
- Track features across multiple repositories (single-repo scope for initial implementation)

## Decision

**We will implement a feature analyzer that:**
1. **Automatically detects and proposes documentation updates after ADR implementation and merge**
2. **Runs weekly to analyze all merged code and update FEATURES.md with newly discovered features**

### Core Workflow

```
ADR Lifecycle:
1. ADR proposed → drafted and reviewed
2. ADR approved → merged to docs/adr/not-implemented/, FEATURES.md entry created
3. Implementation begins → ADR moved to in-progress/, FEATURES.md status updated
4. Implementation merged → ADR moved to implemented/, FEATURES.md status updated
5. **Feature Analyzer triggered** → detects doc sync needed
6. Doc updates proposed → new PR with documentation changes
7. Doc updates reviewed → human reviews and merges
```

**Note on FEATURES.md:** Any time an ADR changes status directories, the corresponding feature entry in FEATURES.md should be updated with a standardized status flag matching the ADR's location (not-implemented, in-progress, implemented).

### Feature Analyzer Responsibilities

The feature analyzer will:

**For ADR-triggered documentation updates:**
1. **Detect ADR status changes** via systemd-scheduled polling (see Implementation Roadmap)
2. **Parse ADR content** to identify affected systems/features
3. **Map to documentation** using docs index and feature list
4. **Generate doc updates** with LLM assistance
5. **Create PR** with proposed documentation changes
6. **Link back to ADR** in PR description for context

**For weekly code analysis:**
1. **Scan all merged code** from the past week in the repository
2. **Identify new features, components, and capabilities** added to the codebase
3. **Extract feature metadata** (name, description, implementation files, tests)
4. **Update FEATURES.md** with newly discovered features and their locations
5. **Create PR** with FEATURES.md updates for human review
6. **Link to commits** that introduced each new feature

### Integration Points

| Component | Role |
|-----------|------|
| **GitHub Watcher** | Detects when ADR PR is merged |
| **Feature Analyzer** | Identifies affected documentation |
| **LLM Documentation Agent** | Generates updated doc content |
| **GitHub MCP** | Creates PR with doc updates |
| **FEATURES.md** | Maps features to source locations |
| **docs/index.md** | Navigation to all documentation |

## Implementation Details

### Implementation Roadmap

This ADR will be implemented in progressive phases to manage complexity and validate approach:

**Prerequisites:**
1. Create `docs/FEATURES.md` with initial feature-to-source mapping
2. Establish standardized feature status flags (not-implemented, in-progress, implemented)
3. Set up systemd service infrastructure for host-services

**Phase 1: MVP - Manual Trigger**
- **Goal:** Prove the concept with manual invocation
- **Components:**
  - CLI tool: `feature-analyzer sync-docs --adr [path]`
  - Single doc update capability
  - Basic validation (link checking, diff bounds)
  - Manual PR creation
- **Success criteria:** Successfully update one doc for one ADR with human review
- **Complexity:** Low - no automation, proves LLM generation quality

**Phase 2: Automated Detection - Polling**
- **Goal:** Automatic detection of ADR status changes
- **Components:**
  - Systemd timer (15-minute interval)
  - ADR directory watcher service
  - State persistence (last-checked timestamp)
  - Auto-trigger on `implemented/` moves
- **Success criteria:** Automatically detects and processes newly implemented ADRs
- **Complexity:** Medium - adds scheduling, state management
- **External dependencies:** None (runs locally)

**Phase 3: Multi-Doc Updates**
- **Goal:** Update multiple affected docs per ADR
- **Components:**
  - FEATURES.md querying logic
  - Batch update generation
  - Validation per-doc with failure handling
  - Consolidated PR with all changes
- **Success criteria:** One PR updates 3-5 related docs correctly
- **Complexity:** Medium - coordination across files

**Phase 4: Enhanced Validation & Rollback**
- **Goal:** Production-ready quality gates
- **Components:**
  - Full validation suite (all 6 checks)
  - HTML comment metadata injection
  - Git tagging for traceability
  - Rollback documentation and tooling
- **Success criteria:** Failed validations caught, easy rollback demonstrated
- **Complexity:** Medium - testing edge cases

**Phase 5: Weekly Code Analysis for FEATURES.md**
- **Goal:** Automatically discover and document new features from merged code
- **Components:**
  - Weekly systemd timer (runs Monday mornings)
  - Git log analyzer (scans commits from past 7 days in the repository)
  - LLM-based feature extractor (analyzes diffs to identify new capabilities)
  - FEATURES.md updater (adds new entries with proper status flags)
  - PR creator for FEATURES.md updates
- **Success criteria:** Identifies 80%+ of new features from weekly merges
- **Complexity:** Medium-High - requires code analysis and feature classification
- **Quality control:**
  - **Precision vs Recall tradeoff:** Tune for high precision (fewer false positives) to avoid noise in FEATURES.md. Better to miss 20% of features (requiring manual backfill) than pollute FEATURES.md with non-features (refactors, internal changes).
  - **Confidence scoring:** Each detected feature includes a confidence score (0.0-1.0). Low-confidence features (<0.7) are flagged with "⚠️ Needs Review" in the PR for human validation.
  - **False positive handling:** Refactors and internal changes are filtered using heuristics (no new public APIs, no new user-facing capabilities, primarily code movement).
  - **Missed features (the 20%):** Manual backfill process via monthly review or ad-hoc discovery. Engineers can also manually add features to FEATURES.md if the analyzer misses them.
- **Implementation approach:**
  ```python
  # Scan repository for merged code from past week
  commits = get_commits_since(days=7)
  for commit in commits:
      features = analyze_commit_for_features(commit)
      for feature in features:
          if not in_features_md(feature):
              add_to_features_md(feature, status="implemented")
  ```
- **Detection heuristics:**
  - New files in key directories (e.g., `host-services/`, `jib-container/`)
  - New CLI commands or scripts
  - New systemd services
  - New API endpoints or handlers
  - Significant new classes/modules (>50 LOC)

**Phase 6 (Future): Real-time Webhooks (TBD)**
- **Goal:** Near-instant response to ADR merges
- **Components:**
  - GitHub webhook receiver (requires GCP deployment)
  - Authentication/security for webhook endpoint
  - Fallback to polling if webhook unavailable
- **Success criteria:** <1 minute latency from merge to PR creation
- **Complexity:** High - requires cloud infrastructure
- **External dependencies:** GCP deployment, ADR-GCP-Deployment
- **Decision:** Defer until local polling proves valuable

**Risk Mitigation:**
- Start with MVP to validate LLM generation quality before investing in automation
- Polling approach (Phase 2) avoids cloud dependencies, keeps everything local
- Each phase builds incrementally on previous work
- Can stop after any phase if value doesn't justify further investment

### Phase 1: ADR Merge Detection

**Trigger mechanism:**

```python
# host-services/analysis/github-watcher/watcher.py
def on_pr_merged(pr_data):
    """Handle PR merge events."""
    if is_adr_pr(pr_data):
        adr_path = extract_adr_path(pr_data)
        old_status = detect_status_change(pr_data)
        new_status = determine_new_status(adr_path)

        if new_status == "implemented":
            trigger_feature_analyzer(adr_path, pr_data)
```

**Detection criteria:**
- ADR file moved from `in-progress/` to `implemented/` directory
- Polling detects the directory change via git status tracking
- Trigger fires on detection of newly implemented ADRs

**Polling implementation:**
- Systemd timer runs every 15 minutes
- Service checks for ADRs moved to `implemented/` since last check
- Persists last-checked timestamp in state file

### Phase 2: Documentation Mapping

**Feature analyzer logic:**

```python
# host-services/analysis/feature-analyzer/doc_mapper.py
def map_adr_to_docs(adr_path):
    """Identify documentation affected by ADR."""

    # Parse ADR content
    adr = parse_adr(adr_path)

    # Extract key concepts (technologies, components, workflows)
    concepts = extract_concepts(adr)

    # Query FEATURES.md for affected features
    features = find_affected_features(concepts)

    # Query docs/index.md for related documentation
    docs = find_related_docs(concepts, features)

    # Include standard docs that reference architecture
    standard_docs = [
        "docs/index.md",          # Navigation index
        "CLAUDE.md",              # Agent instructions
        "README.md",              # Project overview
        "docs/setup/README.md"    # Setup guide
    ]

    # Filter to docs that actually mention affected concepts
    relevant_docs = filter_relevant(standard_docs + docs, concepts)

    return {
        'adr': adr,
        'concepts': concepts,
        'features': features,
        'docs_to_update': relevant_docs
    }
```

**Example mapping:**

For `ADR-Context-Sync-Strategy-Custom-vs-MCP.md`:
- **Concepts:** MCP servers, context sync, Confluence, JIRA
- **Features:** Context sync (from FEATURES.md)
- **Docs to update:**
  - `docs/setup/README.md` (setup instructions)
  - `CLAUDE.md` (mentions context sources)
  - `docs/index.md` (context sync section)
  - `docs/architecture/README.md` (system architecture)

### Phase 3: Documentation Update Generation

**LLM-assisted generation:**

```python
# host-services/analysis/feature-analyzer/doc_updater.py
def generate_doc_updates(mapping):
    """Generate proposed documentation updates."""

    updates = []

    for doc_path in mapping['docs_to_update']:
        # Read current doc content
        current = read_file(doc_path)

        # Generate update using LLM
        prompt = f"""
        ADR {mapping['adr']['title']} has been implemented.

        Key changes:
        {mapping['adr']['decision']}

        Current documentation in {doc_path}:
        {current}

        Update this documentation to reflect the implemented ADR.
        Preserve existing structure and style.
        Only modify sections directly affected by the ADR.
        """

        updated = call_llm(prompt)

        # Validate update (non-destructive, preserves critical info)
        if validate_update(current, updated):
            updates.append({
                'path': doc_path,
                'current': current,
                'updated': updated,
                'reason': f"Sync with {mapping['adr']['filename']}"
            })

    return updates
```

**Update Validation:**

The `validate_update()` function ensures auto-generated updates meet quality standards:

1. **Non-destructive checks:**
   - No complete removal of major sections
   - Critical content preserved (setup instructions, code examples, warnings)
   - Document length doesn't shrink by >50%

2. **Link preservation:**
   - All original links still present or intentionally updated
   - No broken internal references

3. **Concept retention:**
   - Key concepts from original doc still mentioned
   - Technical terms not accidentally removed

4. **Diff bounds:**
   - Changes within reasonable limits (e.g., max 40% of doc changed)
   - No complete rewrites

5. **Structure preservation:**
   - Major headings still exist
   - Document hierarchy maintained

6. **Traceability:**
   - All new claims traceable to the ADR
   - No hallucinated features or capabilities

**Validation failure handling:**
- Failed docs skipped with warning logged
- Notification created for human review
- PR includes comment: "⚠️ Auto-validation failed for [file], manual review required"
- Link to validation failure details in PR description

### Phase 4: PR Creation

**Automated PR workflow:**

```python
# host-services/analysis/feature-analyzer/pr_creator.py
def create_documentation_sync_pr(mapping, updates):
    """Create PR with documentation updates."""

    # Create branch
    branch_name = f"docs/sync-{mapping['adr']['slug']}"

    # Commit updates
    for update in updates:
        write_file(update['path'], update['updated'])
        git_add(update['path'])

    # Commit with traceability markers
    commit_msg = f"""docs: Sync with {mapping['adr']['filename']} (auto-generated)

Auto-updated documentation to reflect implemented ADR.

ADR: {mapping['adr']['path']}
Generated: {datetime.now().isoformat()}
"""
    git_commit(commit_msg)

    # Push and create PR
    git_push(branch_name)

    pr_body = f"""
## Summary

Updates documentation to reflect implemented ADR: {mapping['adr']['title']}

### ADR Context

**ADR:** [{mapping['adr']['filename']}](../blob/main/{mapping['adr']['path']})
**Decision:** {mapping['adr']['decision_summary']}

### Documentation Updated

{format_doc_list(updates)}

### Changes Made

{format_diff_summary(updates)}

## Test Plan

- [x] All updated docs render correctly
- [x] Links are valid
- [x] Content accurately reflects ADR decision
- [ ] Human review of technical accuracy

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"""

    create_pr(
        title=f"docs: Sync documentation with {mapping['adr']['title']}",
        head=branch_name,
        base="main",
        body=pr_body
    )
```

### Phase 5: Weekly Code Analysis and FEATURES.md Updates

**Automated code analysis workflow:**

```python
# host-services/analysis/feature-analyzer/weekly_analyzer.py
def analyze_weekly_code():
    """Analyze all merged code from past week and update FEATURES.md."""

    # Collect commits from past 7 days in current repository
    commits = get_commits_since(days=7)

    # Analyze each commit for new features
    new_features = []
    for commit in commits:
        diff = get_commit_diff(commit)
        features = extract_features_from_diff(diff, commit)
        new_features.extend(features)

    # Deduplicate and filter features
    features = deduplicate_features(new_features)
    features = filter_existing_features(features, "docs/FEATURES.md")

    # Generate FEATURES.md updates
    if features:
        updated_content = add_features_to_md(features, "docs/FEATURES.md")
        create_features_update_pr(features, updated_content)
```

**Feature extraction logic:**

The LLM analyzes code diffs to identify features using these heuristics:

1. **New files in key directories:**
   - `host-services/*/` → New service or component
   - `jib-container/scripts/` → New CLI tool
   - `systemd/` → New background service

2. **Significant code additions:**
   - New Python classes (>50 LOC)
   - New API endpoints
   - New CLI commands (argparse definitions)
   - New configuration files

3. **Feature metadata extraction:**
   - **Name:** Derived from class/function names, file names, or commit messages
   - **Description:** From docstrings, comments, or LLM analysis of code purpose
   - **Status:** Always "implemented" (since code is merged)
   - **Files:** List of implementation files from the diff
   - **Tests:** Auto-detect corresponding test files

**Example feature detection:**

```python
# Commit adds: host-services/analysis/feature-analyzer/analyzer.py
# LLM analyzes and extracts:
{
    "name": "Feature Analyzer Service",
    "description": "Automated service that analyzes codebase to identify features and maintain FEATURES.md",
    "status": "implemented",
    "files": [
        "host-services/analysis/feature-analyzer/analyzer.py",
        "host-services/analysis/feature-analyzer/feature_extractor.py"
    ],
    "tests": [
        "host-services/analysis/feature-analyzer/test_analyzer.py"
    ],
    "introduced_in_commit": "abc123",
    "date_added": "2025-11-30"
}
```

**FEATURES.md update PR:**

```markdown
## Summary

Weekly code analysis identified 3 new features merged in the past 7 days.

### New Features Detected

1. **Feature Analyzer Service** (host-services/analysis/feature-analyzer/)
   - Automated feature detection and FEATURES.md maintenance
   - Introduced in commit: abc123

2. **Beads Task Tracker** (jib-container/scripts/bd)
   - Persistent task tracking across container restarts
   - Introduced in commit: def456

3. **Slack Notification Library** (jib-container/shared/notifications.py)
   - Standardized async notifications to Slack
   - Introduced in commit: ghi789

## Test Plan

- [x] All entries include correct file paths
- [x] Status flags are accurate (all "implemented")
- [x] No duplicate entries in FEATURES.md
- [ ] Human review for accuracy and completeness

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

**Systemd timer configuration:**

```ini
# /etc/systemd/system/feature-analyzer-weekly.timer
[Unit]
Description=Weekly feature analyzer run
Requires=feature-analyzer-weekly.service

[Timer]
# Runs Mondays at 11:00 AM Pacific Time (America/Los_Angeles)
OnCalendar=Mon *-*-* 11:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Note on timezone:** Systemd timers use the system timezone. Ensure the host is configured to `America/Los_Angeles` timezone, or use UTC offset equivalents (Mon 19:00 UTC during standard time, Mon 18:00 UTC during daylight saving).

### Phase 6: Human Review Process

**Review workflow:**

1. **Feature analyzer** creates PR with doc updates or FEATURES.md updates
2. **GitHub notification** alerts human reviewer
3. **Reviewer checks:**
   - Technical accuracy of updates
   - Completeness (all affected docs updated)
   - Style consistency
   - No unintended changes
4. **Reviewer approves or requests changes**
5. **PR merged** → documentation now synchronized

**Quality gates:**
- No auto-merge of documentation PRs
- Human must explicitly approve
- CI checks markdown formatting
- Link checker validates all references

## Consequences

### Benefits

1. **Systematic doc updates:** No more forgotten documentation after ADR implementation
2. **Reduced manual work:** Automated detection and generation reduces engineer burden
3. **Consistency:** Documentation consistently reflects architectural decisions
4. **Auditability:** PR trail shows exactly what changed and why
5. **Quality control:** Human review ensures accuracy
6. **Discoverability:** FEATURES.md provides structured mapping

### Drawbacks

1. **Initial setup cost:** Building feature analyzer and integration points
2. **False positives:** May suggest doc updates for unaffected files
3. **Review overhead:** Human must review auto-generated documentation
4. **LLM accuracy:** Generated updates may need significant editing
5. **Maintenance:** Feature analyzer itself needs maintenance

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| **Incorrect doc updates** | Human review required, never auto-merge |
| **Missing affected docs** | Comprehensive mapping in FEATURES.md, conservative detection |
| **Overwhelming PR volume** | Batch updates per ADR, clear PR descriptions |
| **Analyzer bugs** | Extensive testing, gradual rollout, fail-safe defaults |
| **LLM hallucinations** | Validation checks, diff review, cite ADR as source |

### Rollback Strategy

Auto-generated documentation updates are traceable and reversible:

**Traceability mechanisms:**

1. **Commit message convention:**
   - Format: `docs: Sync with [ADR-filename] (auto-generated)`
   - Includes ADR path and generation timestamp in commit body
   - Example:
     ```
     docs: Sync with ADR-Feature-Analyzer-Documentation-Sync (auto-generated)

     Auto-updated documentation to reflect implemented ADR.

     ADR: docs/adr/implemented/ADR-Feature-Analyzer-Documentation-Sync.md
     Generated: 2025-11-30T14:23:45Z
     ```

2. **HTML metadata in updated docs:**
   - Add HTML comments to modified sections:
   - `<!-- Auto-updated from ADR-XYZ on YYYY-MM-DD -->`
   - Enables filtering: `grep -r "Auto-updated from" docs/`

3. **Git tags for audit:**
   - Tag commits containing auto-generated content: `auto-doc-sync-YYYYMMDD`
   - Query all auto-updates: `git log --tags='auto-doc-sync-*'`

**Rollback procedures:**

1. **Single doc revert:**
   ```bash
   # Find the auto-generated commit
   git log --grep="auto-generated" --oneline -- path/to/doc.md

   # Revert specific file
   git checkout [commit-before-auto-gen]~1 -- path/to/doc.md
   ```

2. **Batch revert (all updates from one ADR):**
   ```bash
   # Find commits for specific ADR
   git log --grep="ADR-Feature-Analyzer" --grep="auto-generated"

   # Revert the PR merge
   git revert -m 1 [merge-commit-sha]
   ```

3. **Audit auto-generated changes:**
   ```bash
   # Show all auto-generated doc commits from last week
   git log --since="1 week ago" --grep="auto-generated" --oneline

   # Show files modified by auto-generation
   git log --grep="auto-generated" --name-only --pretty=format:
   ```

**Quality gates prevent bad rollbacks:**
- All auto-generated PRs reviewed by human before merge
- If mistakes found post-merge, create corrective PR (not force-push)
- Maintain audit trail of what was auto-generated vs manually fixed

## Decision Permanence

**Medium permanence.**

The workflow pattern (ADR → implementation → doc sync) is stable, but the implementation details (detection mechanisms, LLM prompts, mapping logic) can evolve.

**Low-permanence elements:**
- Specific detection triggers (webhook vs polling)
- LLM prompts for generation
- Exact files in FEATURES.md

**Higher-permanence elements:**
- ADR lifecycle workflow
- Human review requirement
- Documentation mapping principle
- PR-based update process

## Alternatives Considered

### Alternative 1: Manual Documentation Updates

**Description:** Continue relying on engineers to manually update documentation after ADR merge.

**Pros:**
- No automation complexity
- Human writes all content

**Cons:**
- Frequently forgotten
- Inconsistent coverage
- Higher engineer burden
- Documentation drift

**Rejected because:** Already a problem; doesn't scale with growing ADR count.

### Alternative 2: Pre-Merge Documentation Requirements

**Description:** Require documentation updates in the same PR as ADR implementation.

**Pros:**
- Documentation always updated
- Single review cycle

**Cons:**
- Bloats implementation PRs
- Harder to review (code + docs mixed)
- Blocks merge on doc quality
- Doesn't help with ADRs that affect multiple repos

**Rejected because:** Couples unrelated changes, increases PR review complexity.

### Alternative 3: Scheduled Batch Documentation Sync

**Description:** Weekly/monthly automated scan for doc drift, batch all updates.

**Pros:**
- Fewer PRs to review
- More context for reviewer

**Cons:**
- Delayed updates (drift exists longer)
- Harder to trace which ADR caused which doc change
- Large batched PRs difficult to review

**Rejected because:** Longer drift window, less clear causality.

### Alternative 4: Documentation in ADR Itself

**Description:** Include all affected documentation directly in ADR, deprecate separate docs.

**Pros:**
- Single source of truth
- No sync needed

**Cons:**
- ADRs become unwieldy
- Hard to navigate
- Doesn't serve different audiences (engineers vs operations vs users)
- Duplicates information

**Rejected because:** ADRs are decisions, not user guides; different purposes require different docs.

## References

- [PR #259: Comprehensive Feature List](https://github.com/jwbron/james-in-a-box/pull/259) - Feature analyzer context
- [ADR-LLM-Documentation-Index-Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md) - Documentation generation workflows
- [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) - Mentions codebase analyzer needing feature list
- [FEATURES.md](../../FEATURES.md) - Feature-to-source mapping
- [Documentation Index](../../index.md) - Navigation structure

### Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-LLM-Documentation-Index-Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md) | Provides doc generation pipeline and external research workflow |
| [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) | Uses feature analyzer for continuous improvement |

---

**Last Updated:** 2025-12-01
**Status:** Implementation complete (Phases 1-5). Phase 6 (webhooks) deferred as planned.
