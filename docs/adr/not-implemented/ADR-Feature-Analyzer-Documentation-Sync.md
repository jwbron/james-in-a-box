# ADR: Feature Analyzer - Documentation Sync Workflow

**Driver:** James Wiesebron
**Approver:** TBD
**Status:** Proposed
**Proposed:** November 2025

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
- Feature list in `docs/FEATURES.md` (added in PR #259)
- Documentation index in `docs/index.md`
- No automated link between ADR implementation and documentation updates

### What We're Deciding

This ADR establishes an automated workflow where:

1. ADRs trigger documentation updates after merge
2. Feature analyzer detects which docs need updating based on ADR content
3. Updates are proposed as PRs for human review
4. Documentation stays synchronized with architectural decisions

### Goals

**Primary Goals:**
1. **Automate doc discovery:** Identify which documentation is affected by each ADR
2. **Prevent doc drift:** Ensure docs reflect implemented ADRs
3. **Maintain quality:** Human review all auto-generated doc updates
4. **Low friction:** Minimal manual tracking of what needs updating

**Non-Goals:**
- Automatically merge documentation PRs without review
- Replace human documentation writing entirely
- Handle documentation for non-ADR changes (covered by existing workflows)

## Decision

**We will implement a feature analyzer that automatically detects and proposes documentation updates after ADR implementation and merge.**

### Core Workflow

```
ADR Lifecycle:
1. ADR proposed → opened as PR in docs/adr/not-implemented/
2. ADR reviewed → feedback, iterations
3. ADR approved → human approves PR
4. ADR implemented → code changes made, ADR moved to in-progress/
5. Implementation merged → ADR moved to implemented/
6. **Feature Analyzer triggered** → detects doc sync needed
7. Doc updates proposed → new PR with documentation changes
8. Doc updates reviewed → human reviews and merges
```

### Feature Analyzer Responsibilities

The feature analyzer (introduced in PR #259) will:

1. **Detect ADR merge events** via GitHub webhook or scheduled check
2. **Parse ADR content** to identify affected systems/features
3. **Map to documentation** using docs index and feature list
4. **Generate doc updates** with LLM assistance
5. **Create PR** with proposed documentation changes
6. **Link back to ADR** in PR description for context

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
- PR modifies file in `docs/adr/`
- PR moves ADR from `in-progress/` to `implemented/`
- PR merge is the implementation completion (not just proposal merge)

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

    git_commit(f"docs: Sync documentation with {mapping['adr']['filename']}")

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

### Phase 5: Human Review Process

**Review workflow:**

1. **Feature analyzer** creates PR with doc updates
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

**Last Updated:** 2025-11-30
**Next Review:** After implementation begins
