# ADR: JIRA Ticket Triage Workflow for JIB

**Driver:** James Wiesebron
**Status:** Proposed (Awaiting Review)
**Created:** 2025-12-18

## Overview

This ADR proposes a reworked JIRA integration for james-in-a-box (JIB) that automatically triages tickets tagged for JIB, determines fixability, and either creates a PR with the fix or creates a PR with a collaborative planning document.

## Context

### Current State

Today, the JIRA integration works as follows:

1. **context-sync** (scheduled hourly): Syncs all open INFRA tickets to `~/context-sync/jira/` as markdown files
2. **jira-processor.py** (triggered after sync): Analyzes new/updated tickets assigned to you
   - Extracts action items from descriptions
   - Estimates scope (small/medium/large)
   - Creates Beads tasks automatically
   - Sends Slack notifications with summaries

### Problem

The current workflow:
- Processes ALL assigned tickets equally (no filtering for JIB-tagged tickets)
- Does not attempt automatic fixes
- Does not produce actionable PRs
- Does not integrate with the Collaborative Planning Framework (CPF)

### Desired State

When a JIRA ticket is tagged for "James-in-a-box" (via label, custom field, or mention):

```
┌────────────────────────────────────────────────────────────────────┐
│                    JIRA Ticket Created                             │
│            (Tagged: james-in-a-box / jib / JIB)                   │
└───────────────────────────┬────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│                   Context-Sync (Hourly)                            │
│           Pulls ticket to ~/context-sync/jira/                    │
└───────────────────────────┬────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│                    JIB Ticket Triage                               │
│                                                                    │
│  1. Detect JIB-tagged tickets (new or updated)                    │
│  2. Pull in appropriate context:                                   │
│     - Related codebase files                                       │
│     - Relevant documentation                                       │
│     - Similar past tickets/PRs                                     │
│     - Error logs (if referenced)                                   │
│  3. Analyze ticket requirements                                    │
│  4. Determine if fix is trivial                                   │
└───────────────────────────┬────────────────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
┌──────────────────────────┐   ┌───────────────────────────────────┐
│    TRIVIAL FIX           │   │      NON-TRIVIAL                  │
│                          │   │                                   │
│  - Implement the fix     │   │  - Generate CPF planning doc      │
│  - Run tests             │   │  - Identify questions/ambiguities │
│  - Create PR with:       │   │  - Create PR with:                │
│    * Code changes        │   │    * Planning document            │
│    * Test coverage       │   │    * Requirements analysis        │
│    * Clear description   │   │    * Design options               │
│                          │   │    * Questions for human          │
└──────────────────────────┘   └───────────────────────────────────┘
              │                           │
              └─────────────┬─────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│                    Human Review                                    │
│                                                                    │
│  For TRIVIAL: Review code, merge if good                          │
│  For NON-TRIVIAL: Review plan, approve, JIB proceeds with CPF     │
└────────────────────────────────────────────────────────────────────┘
```

## Design

### 1. JIB Tag Detection

**Question for James:** How should JIB-targeted tickets be identified?

Options:
1. **JIRA Label**: `jib` or `james-in-a-box` label on the ticket
2. **Custom Field**: A custom JIRA field "Automation Target: JIB"
3. **Mention in Description**: `@james-in-a-box` or similar mention
4. **Assignee**: Assign ticket to a JIB service account
5. **Component**: Add a "JIB" component to the ticket

**Recommendation:** Use **JIRA Label** (`jib` or `james-in-a-box`) as it's:
- Easy to add/remove
- Visible in JIRA UI
- Queryable via JQL
- Doesn't require custom field setup

### 2. Context Gathering

When a JIB-tagged ticket is detected, gather context:

| Context Type | Source | Method |
|--------------|--------|--------|
| **Related Code** | Codebase | Grep for keywords from ticket, analyze stack traces |
| **Documentation** | Confluence sync | Search for related ADRs, runbooks |
| **Similar Tickets** | JIRA history | Search closed tickets with similar keywords |
| **Past PRs** | GitHub sync | Find PRs that touched related files |
| **Error Logs** | Ticket description | Parse error messages, stack traces |
| **Repository Context** | CLAUDE.md files | Load repo-specific guidelines |

**Question for James:** Should JIB have access to production logs via GCP read-only access for richer debugging context? (Currently not implemented per ADR)

### 3. Triviality Assessment

Criteria for determining if a fix is "trivial":

| Factor | Trivial | Non-Trivial |
|--------|---------|-------------|
| **Scope** | Single file or 2-3 closely related files | Multiple components/services |
| **Type** | Bug fix, typo, config change | Feature, architecture change |
| **Tests** | Existing tests cover the area | New test patterns needed |
| **Dependencies** | No new dependencies | New packages/services |
| **Ambiguity** | Clear requirements | Multiple interpretations possible |
| **Risk** | Low (isolated change) | High (security, data, performance) |
| **Estimated Lines** | < 50-100 lines changed | > 100 lines or complex refactor |

**Scoring System (Proposed):**
```
trivial_score = 0

# File scope
if files_affected == 1: trivial_score += 30
elif files_affected <= 3: trivial_score += 15
else: trivial_score -= 20

# Change type
if is_bug_fix: trivial_score += 20
if is_config_change: trivial_score += 20
if is_new_feature: trivial_score -= 30

# Test coverage
if existing_tests_cover_area: trivial_score += 20
else: trivial_score -= 10

# Ambiguity
if requirements_clear: trivial_score += 20
if questions_identified: trivial_score -= 10 * num_questions

# Dependencies
if new_dependencies_needed: trivial_score -= 30

# Risk assessment
if security_implications: trivial_score -= 40
if data_migration: trivial_score -= 30

# TRIVIAL if trivial_score >= 50
```

**Question for James:** What threshold feels right? Should certain factors be automatic disqualifiers (e.g., security implications always → non-trivial)?

### 4. Trivial Fix Workflow

When a fix is determined trivial:

1. **Implement the fix**
   - Create feature branch
   - Make code changes
   - Follow repo conventions (CLAUDE.md)

2. **Validate**
   - Run existing tests
   - Add tests if needed (for bug fixes, add regression test)
   - Lint/format check

3. **Create PR**
   - Title: `[JIB] Fix: {JIRA-KEY} {summary}`
   - Body includes:
     - Link to JIRA ticket
     - Summary of the issue
     - Description of the fix
     - Test coverage
     - Screenshot/evidence if applicable
   - Request review from @jwiesebron

4. **Notify**
   - Slack notification with PR link
   - Update Beads task

### 5. Non-Trivial Workflow (CPF Integration)

When a fix is non-trivial, create a PR with a Collaborative Planning Framework document:

**PR Contents:**

```markdown
# docs/plans/JIRA-XXX-{slug}.md

# Plan: {Ticket Title}

**JIRA:** [JIRA-XXX](link)
**Status:** Proposed - Awaiting Human Approval
**Complexity:** Non-trivial
**Estimated Scope:** {small|medium|large}

## Executive Summary

{2-3 sentence summary of what this ticket is about}

## Requirements Analysis

### Goals
- Primary: {main objective}
- Secondary: {additional objectives}

### Requirements Captured
| ID | Requirement | Source | Confidence |
|----|-------------|--------|------------|
| R1 | {requirement} | {ticket/inference} | {high/medium/low} |
| R2 | ... | ... | ... |

### Ambiguities & Questions

> **Human input needed:** The following questions require clarification before proceeding.

1. **{Question 1}**
   - Context: {why this matters}
   - Options: {A, B, C}
   - Recommendation: {if any}

2. **{Question 2}**
   - ...

## Technical Analysis

### Affected Areas
- `path/to/file.py` - {reason}
- `path/to/other.py` - {reason}

### Dependencies
- {Dependency 1}
- {Dependency 2}

### Risks
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| {risk} | {H/M/L} | {H/M/L} | {mitigation} |

## Design Options

### Option A: {Name}
{Description}

**Pros:**
- ...

**Cons:**
- ...

### Option B: {Name}
{Description}

**Pros:**
- ...

**Cons:**
- ...

### Recommendation
{Recommended option with rationale}

## Proposed Implementation Plan

### Phase 1: {Name}
- [ ] Task 1.1: {description}
- [ ] Task 1.2: {description}

### Phase 2: {Name}
- [ ] Task 2.1: {description}
- [ ] Task 2.2: {description}

## Next Steps

After human approval of this plan:
1. JIB will proceed with implementation using CPF
2. Checkpoints will be created at each phase
3. Final PR(s) with code will be submitted for review

---

**Generated by:** james-in-a-box
**Awaiting:** Human review and approval
```

### 6. Implementation Components

#### New/Modified Files

| File | Type | Description |
|------|------|-------------|
| `jib-container/jib-tasks/jira/ticket-triager.py` | New | Main triage logic |
| `jib-container/jib-tasks/jira/context-gatherer.py` | New | Context collection utilities |
| `jib-container/jib-tasks/jira/triviality-assessor.py` | New | Scoring logic for trivial vs non-trivial |
| `jib-container/jib-tasks/jira/plan-generator.py` | New | CPF document generator |
| `jib-container/jib-tasks/jira/jira-processor.py` | Modified | Add JIB tag detection, call triager |
| `host-services/sync/context-sync/connectors/jira/config.py` | Modified | Add JIB label config |

#### Configuration Changes

```bash
# New environment variables
JIB_TRIAGE_ENABLED=true
JIB_TAG_LABELS="jib,james-in-a-box"
JIB_TRIVIALITY_THRESHOLD=50
JIB_AUTO_SECURITY_NONTRIVIAL=true  # Security tickets always non-trivial
JIB_PLAN_OUTPUT_DIR="docs/plans"
```

### 7. Integration Points

#### With Existing Systems

| System | Integration |
|--------|-------------|
| **context-sync** | Triggers triage after JIRA sync completes |
| **Beads** | Creates/updates tasks for tracked tickets |
| **Slack** | Notifications for triage decisions and PRs |
| **GitHub** | PR creation for both trivial fixes and plans |

#### With CPF (Post-Plan Approval)

After human approves a planning PR:
1. JIB detects merged planning doc
2. Enters CPF implementation workflow
3. Creates implementation PR(s) with checkpoints
4. Follows standard review process

**Question for James:** How should JIB detect that a planning doc has been approved? Options:
1. PR merge triggers webhook
2. Scheduled scan for merged planning docs
3. Human sends Slack message "proceed with JIRA-XXX"
4. Add GitHub label "jib-approved" to merged PR

## Open Questions

### Critical (Need answers before implementation)

1. **JIB Tag Mechanism:** How should tickets be tagged for JIB? (Label recommended)

2. **Triviality Threshold:** What threshold feels right for trivial vs non-trivial? (50 proposed)

3. **Approval Detection:** How should JIB know a plan is approved to proceed?

4. **Repository Scope:** Should this work for all configured repos or start with a specific one?

### Important (Can iterate on)

5. **Context Depth:** How much context should JIB gather? (Cost vs. quality tradeoff)

6. **Retry Logic:** What happens if JIB can't determine triviality? (Default to non-trivial?)

7. **Human Override:** Should there be a way to force trivial/non-trivial classification?

### Nice to Have

8. **Learning:** Should JIB track which tickets it got "wrong" to improve future triaging?

9. **Templates:** Should planning docs be customizable per project/team?

10. **Metrics:** What should we track to measure success?

## Success Criteria

| Metric | Target |
|--------|--------|
| JIB-tagged tickets processed | 100% within 2 hours of sync |
| Trivial fixes that are actually trivial | > 90% (measured by merge without major changes) |
| Non-trivial plans that are useful | > 80% (measured by approval rate) |
| Time from ticket to first PR | < 2 hours for trivial, < 4 hours for plan |
| Human satisfaction | Qualitative feedback positive |

## Implementation Phases

### Phase 1: Foundation (Week 1)
- [ ] Add JIB label detection to JIRA sync
- [ ] Implement context gathering
- [ ] Create triviality scoring

### Phase 2: Trivial Flow (Week 2)
- [ ] Implement trivial fix workflow
- [ ] PR creation with proper formatting
- [ ] Slack notifications

### Phase 3: Non-Trivial Flow (Week 3)
- [ ] CPF planning document generator
- [ ] PR creation for plans
- [ ] Approval detection mechanism

### Phase 4: Integration & Polish (Week 4)
- [ ] End-to-end testing
- [ ] Metrics/logging
- [ ] Documentation

## Related Documents

- [ADR-Autonomous-Software-Engineer.md](ADR-Autonomous-Software-Engineer.md) - Parent ADR for JIB architecture
- [Collaborative-Planning-Framework.md](../../../../collaborative-development-framework/docs/foundations/Collaborative-Planning-Framework.md) - CPF specification
- [JIRA Connector README](../../../host-services/sync/context-sync/connectors/jira/README.md) - Current JIRA sync implementation

---

**Next Action:** Review this plan, answer open questions, approve or request changes.
