# ADR: Review Artifacts for Async Human Review

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, jib (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** December 2025
**Status:** Proposed (Not Implemented)

---

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Artifact Types and Guidelines](#artifact-types-and-guidelines)
- [Multi-Agent Pipeline Integration](#multi-agent-pipeline-integration)
- [Artifact Delivery Mechanisms](#artifact-delivery-mechanisms)
- [Quality Standards](#quality-standards)
- [Review Workflow](#review-workflow)
- [Implementation Phases](#implementation-phases)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

jib operates as an autonomous software engineering agent that performs work asynchronously while the human reviewer is unavailable. The current guidance spread across various documents (CLAUDE.md, mission.md, pr-descriptions.md) provides partial direction on what to communicate, but lacks a comprehensive framework for:

1. **What artifacts to produce:** Which deliverables need human review at each stage of a workflow
2. **When to notify:** Triggering conditions for proactive communication vs. waiting for completion
3. **How to format:** Consistent structure that enables effective async review on mobile devices
4. **What detail level:** Balancing completeness with conciseness for different artifact types
5. **Multi-agent coordination:** How artifact production changes in multi-agent pipeline contexts

**Current State:**

The existing guidance is fragmented:
- `CLAUDE.md` covers PR creation basics and notification patterns
- `mission.md` establishes the human-in-the-loop model
- `pr-descriptions.md` specifies PR format but not other artifacts
- `ADR-Multi-Agent-Pipeline-Architecture.md` discusses stage outputs but not human review artifacts
- No unified guidance on what artifacts enable effective async review

**User Impact:**

Without clear artifact guidelines:
- Human reviews incomplete or overwhelming information
- Critical decision points may not be flagged for review
- Mobile review is difficult due to inconsistent formatting
- Multi-agent pipelines produce disconnected outputs
- Async workflows stall waiting for clarification that could have been anticipated

### What We're Deciding

This ADR establishes a **comprehensive framework for review artifacts** that jib produces during automated workflows, covering:

1. **Artifact taxonomy:** Categories of review artifacts with clear purposes
2. **Production triggers:** When each artifact type should be generated
3. **Format standards:** Structure optimized for async and mobile review
4. **Detail guidelines:** What to include/exclude for effective review
5. **Multi-agent considerations:** How artifacts flow through pipeline stages

### Goals

**Primary Goals:**
1. **Enable effective async review:** Human can understand and evaluate jib's work without real-time interaction
2. **Mobile-first accessibility:** All artifacts reviewable on mobile devices
3. **Right-sized information:** Enough detail for decisions, not overwhelming
4. **Clear decision points:** Explicit identification of what needs human judgment
5. **Pipeline traceability:** Artifacts that span multi-agent workflows maintain coherent narrative

**Non-Goals:**
- Automating human approval decisions
- Replacing human judgment on architectural choices
- Creating artifacts that only LLMs can understand
- Exhaustive logging of every action (that's for debugging, not review)

## Decision

**We will establish a standardized artifact framework with five artifact categories, clear production triggers, and format guidelines optimized for async human review.**

### Core Principles

1. **Artifacts are for human judgment:** Every artifact answers the question "What does the human need to decide/approve/understand?"
2. **Mobile-first formatting:** Short summaries, clear structure, action items prominent
3. **Progressive detail:** Summary → Details → Full context (reviewer chooses depth)
4. **Explicit decision requests:** Never bury questions in long descriptions
5. **Pipeline continuity:** Multi-agent artifacts reference prior stages

## Artifact Types and Guidelines

### 1. Decision Request Artifacts

**Purpose:** Request human guidance on choices that require judgment

**When to produce:**
- Ambiguous requirements discovered
- Multiple valid approaches identified
- Security or breaking change implications
- Architecture decisions not covered by existing ADRs
- Found a better approach than originally requested

**Format:**

```markdown
# Decision Required: [Brief Topic]

**Priority:** [Low/Medium/High/Urgent]
**Blocking:** [Yes/No - is work stopped until answered?]

## Context (2-3 sentences)
[What situation prompted this decision]

## Options

### Option A: [Name]
- **Pros:** [bullet points]
- **Cons:** [bullet points]
- **Effort:** [Low/Medium/High]

### Option B: [Name]
- **Pros:** [bullet points]
- **Cons:** [bullet points]
- **Effort:** [Low/Medium/High]

## Recommendation
[Clear recommendation with rationale]

## Decision Requested
- [ ] Proceed with Option A
- [ ] Proceed with Option B
- [ ] Need clarification on: [specific question]
- [ ] Discuss before proceeding
```

**Length target:** 200-400 words

---

### 2. Progress Update Artifacts

**Purpose:** Keep human informed of work status during long-running tasks

**When to produce:**
- Significant milestone completed
- Entering a new phase of work
- Unexpected findings that don't block work
- Every 30+ minutes of active work without other artifacts

**Format:**

```markdown
# Progress: [Task Name]

**Status:** [In Progress / Blocked / Awaiting Review]
**Beads ID:** [bd-xxxx]

## Completed
- [x] [Milestone 1]
- [x] [Milestone 2]

## In Progress
- [ ] [Current work]

## Upcoming
- [ ] [Next step]

## Notes (if any)
[Brief findings, decisions made, or concerns]

**ETA to next milestone:** [estimate if applicable]
```

**Length target:** 100-200 words

---

### 3. Pull Request Artifacts

**Purpose:** Enable code review and merge decision

**When to produce:**
- Code changes ready for review
- After pushing commits to a branch

**Format:** (Aligned with existing pr-descriptions.md)

```markdown
<one-line summary - 50 chars max>

## Summary
[2-3 paragraphs: Context → Changes → Impact]

## Changes Made
- [Bullet point summary of key changes]

## Files Changed
| File | Change Type | Description |
|------|-------------|-------------|
| path/to/file.py | Modified | [Brief description] |

## Test Plan
- [ ] [Specific test steps]
- [ ] [What to verify]
- [ ] [Edge cases tested]

Issue: [JIRA link or "none"]

---
Authored-by: jib
```

**Length target:** 200-500 words (under 500 total)

**Additional guidelines:**
- Include diff stats if >100 lines changed
- Flag breaking changes at the top with migration path
- For large PRs (>500 lines), add "Reviewer Guide" section

---

### 4. Completion Summary Artifacts

**Purpose:** Report task completion with actionable next steps

**When to produce:**
- Task fully completed
- PR created and ready for review
- Analysis or research task finished

**Format:**

```markdown
# Completed: [Task Name]

**Beads ID:** [bd-xxxx]
**Duration:** [time spent]

## What Was Done
[2-3 sentence summary]

## Deliverables
- **PR:** [URL] (if applicable)
- **Branch:** [branch-name]
- **Files:** [count] files changed, [+X/-Y] lines

## Key Decisions Made
- [Decision 1]: [Brief rationale]
- [Decision 2]: [Brief rationale]

## Next Steps for Human
- [ ] Review PR at [URL]
- [ ] [Any other actions needed]

## Follow-up Tasks (if any)
- [Task that emerged during work]
```

**Length target:** 150-300 words

---

### 5. Blocker/Issue Artifacts

**Purpose:** Report problems that prevent progress

**When to produce:**
- Unable to proceed without human intervention
- Discovered critical issue
- Test failures that can't be resolved
- Access/permission issues

**Format:**

```markdown
# Blocked: [Brief Description]

**Severity:** [Critical/High/Medium/Low]
**Beads ID:** [bd-xxxx]

## What's Blocked
[Task/workflow that cannot proceed]

## The Issue
[Clear description of the problem]

## What I Tried
1. [Attempt 1 and result]
2. [Attempt 2 and result]

## What I Need
- [ ] [Specific action needed from human]

## Workaround (if any)
[Temporary solution if one exists]
```

**Length target:** 150-250 words

---

## Multi-Agent Pipeline Integration

When jib operates in a multi-agent pipeline (per ADR-Multi-Agent-Pipeline-Architecture), artifact production follows these additional guidelines:

### Stage-Level Artifacts

Each pipeline stage produces a **stage completion artifact** that includes:

```markdown
# Stage Complete: [Stage Name]

**Pipeline:** [Pipeline name]
**Stage:** [N] of [Total]
**Beads ID:** [bd-xxxx]

## Stage Output
[Summary of what this stage produced]

## Input from Previous Stage
[What was received and used]

## Output for Next Stage
[What is being passed forward]

## Human Review Points (if any)
- [Any decisions or approvals needed before proceeding]

## Confidence Level
[High/Medium/Low] - [Brief rationale for confidence assessment]
```

### Pipeline Checkpoints

**Mandatory human review points:**
1. **Before implementation:** After planning stage, before code generation
2. **Before PR creation:** After all code/test stages, before creating PR
3. **On any stage failure:** Before retry or alternative approach

**Optional checkpoint triggers:**
- Low confidence score from any stage
- Significant deviation from original plan
- Discovery of scope expansion

### Artifact Aggregation

For multi-stage pipelines, produce a **pipeline summary artifact** at completion:

```markdown
# Pipeline Complete: [Pipeline Name]

**Total Stages:** [N]
**Duration:** [total time]
**Beads ID:** [bd-xxxx]

## Stages Executed
| Stage | Status | Duration | Key Output |
|-------|--------|----------|------------|
| Plan | Complete | Xm | Identified 3 files to change |
| Implement | Complete | Xm | 150 lines added |
| Test | Complete | Xm | All tests passing |
| Review | Complete | Xm | PR #123 created |

## Overall Result
[2-3 sentence summary]

## Deliverables
- PR: [URL]
- Branch: [name]

## Decisions Made by Pipeline
[List of autonomous decisions for human awareness]

## Requires Human Action
- [ ] Review and merge PR
- [ ] [Any other actions]
```

---

## Artifact Delivery Mechanisms

### Primary: Slack Notifications

All artifacts are delivered via Slack DM with these formatting rules:
- **Subject line:** Clear, scannable title
- **Priority indicator:** Visual priority marker (no emoji unless critical)
- **Mobile-friendly:** No long code blocks in notification body
- **Links prominent:** PR URLs, Beads IDs clickable

### Secondary: PR Descriptions

For code-related artifacts, the PR description serves as the permanent artifact record.

### Tertiary: Beads Notes

All artifacts are also recorded in Beads task notes for:
- Persistent memory across container restarts
- Audit trail of decisions and communications
- Context for future related work

---

## Quality Standards

### Do Include
- Clear action items with checkboxes
- Specific next steps for human
- Brief rationale for decisions made
- Links to related PRs, ADRs, tickets
- Confidence indicators where applicable

### Do Not Include
- Implementation minutiae (file-by-file changes)
- Raw error logs (summarize instead)
- Speculative commentary without clear purpose
- Multiple decision requests in one artifact (split them)
- Filler text or excessive hedging

### Formatting Rules
- Use headers for scannability
- Bullet points over paragraphs where possible
- Tables for comparing options
- Checkboxes for action items
- Bold for key terms and decisions

---

## Review Workflow

### Human Review Process

1. **Notification received** via Slack
2. **Quick scan** of summary/title (should take <10 seconds)
3. **Decide engagement level:**
   - Approve quickly (checkboxes, LGTM)
   - Dig into details (follow links)
   - Request changes (reply in thread)
4. **Respond** via Slack reply or GitHub action
5. **jib continues** based on response

### Response Time Expectations

| Artifact Type | Expected Response | If No Response |
|---------------|-------------------|----------------|
| Decision Request (Blocking) | <4 hours | jib waits, sends reminder |
| Decision Request (Non-blocking) | <24 hours | jib proceeds with recommendation |
| Progress Update | No response needed | - |
| PR Ready | <24 hours | jib sends reminder |
| Blocker | <4 hours | jib waits, escalates visibility |

### jib Behavior on No Response

- **After 4 hours (blocking):** Send reminder notification
- **After 24 hours (blocking):** Escalate priority, note in Beads
- **Non-blocking requests:** Proceed with stated recommendation after 24 hours

---

## Implementation Phases

### Phase 1: Artifact Templates
- Create template files for each artifact type in `.claude/templates/`
- Update CLAUDE.md rules to reference artifact guidelines
- Add artifact type selection guidance to mission.md

### Phase 2: Validation and Formatting
- Implement artifact format validation in notification library
- Add length checks and warnings
- Create mobile-preview test utility

### Phase 3: Multi-Agent Integration
- Integrate with pipeline orchestrator (per ADR-Multi-Agent-Pipeline)
- Implement stage completion artifacts
- Add checkpoint triggers

### Phase 4: Response Handling
- Implement response timeout tracking
- Add reminder notification logic
- Build escalation workflow

---

## Consequences

### Benefits

1. **Consistent review experience:** Human always knows what to expect
2. **Faster decisions:** Right information, right format, right time
3. **Mobile productivity:** Review effectively from phone
4. **Audit trail:** All decisions documented in artifacts
5. **Pipeline visibility:** Multi-agent work remains coherent

### Drawbacks

1. **Artifact overhead:** Time spent formatting vs. doing work
2. **Template rigidity:** May not fit all situations perfectly
3. **Training required:** jib must learn new patterns
4. **Response dependency:** Some workflows blocked on human response

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Over-notification | Clear triggers, batch related updates |
| Under-notification | Mandatory checkpoints, time-based progress updates |
| Format drift | Template validation, periodic review |
| Response delays | Timeout handling, proceed-with-recommendation policy |

---

## Decision Permanence

**Medium permanence.**

The artifact categories and human-in-the-loop principle are stable, but specific formats and triggers can evolve based on review feedback.

**Low-permanence elements:**
- Specific template text
- Length targets
- Timeout durations
- Delivery mechanism details

**Higher-permanence elements:**
- Five artifact categories
- Mobile-first principle
- Progressive detail philosophy
- Multi-agent checkpoint requirements

---

## Alternatives Considered

### Alternative 1: Single Notification Format

**Description:** Use one format for all communications

**Rejected because:** Different purposes need different structures; one-size-fits-all leads to either too much or too little detail.

### Alternative 2: Pull-Based Review Only

**Description:** Human pulls status when they want it, no push notifications

**Rejected because:** Async workflow requires proactive communication; human shouldn't need to poll for updates.

### Alternative 3: Full Automation with Post-Hoc Review

**Description:** Complete work first, review all at once after

**Rejected because:** Violates human-in-the-loop principle; costly to undo large amounts of misaligned work.

### Alternative 4: Verbose Logging as Artifacts

**Description:** Send full logs of all actions

**Rejected because:** Information overload prevents effective review; logs are for debugging, not decisions.

---

## References

- [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) - Core architecture and human-in-the-loop model
- [ADR-Multi-Agent-Pipeline-Architecture](./ADR-Multi-Agent-Pipeline-Architecture.md) - Pipeline stage outputs and checkpointing
- [pr-descriptions.md](../../.claude/rules/pr-descriptions.md) - Existing PR format guidelines
- [mission.md](../../.claude/rules/mission.md) - Agent operating model
- [ADR-Feature-Analyzer-Documentation-Sync](../implemented/ADR-Feature-Analyzer-Documentation-Sync.md) - Related artifact production patterns

### Related ADRs

| ADR | Relationship |
|-----|--------------|
| ADR-Autonomous-Software-Engineer | Establishes human-in-the-loop requirement this ADR operationalizes |
| ADR-Multi-Agent-Pipeline-Architecture | Defines pipeline stages this ADR adds review artifacts to |
| ADR-Feature-Analyzer-Documentation-Sync | Similar automated artifact production for documentation |

---

**Last Updated:** 2025-12-02
**Status:** Proposed (Not Implemented)
