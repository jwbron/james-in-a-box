# ADR: JIRA Ticket Triage Workflow for JIB

**Driver:** James Wiesebron
**Status:** Proposed (Awaiting Review)
**Created:** 2025-12-18
**Last Updated:** 2025-12-18

## Executive Summary

This ADR proposes an automated JIRA triage workflow for james-in-a-box (JIB) that:
1. Detects tickets explicitly tagged for JIB automation
2. Gathers relevant context (code, docs, similar tickets, PRs)
3. Assesses whether the fix is trivial or requires planning
4. For **trivial fixes**: Implements the fix and creates a code PR
5. For **non-trivial issues**: Creates a Collaborative Planning Framework (CPF) document PR for human approval before implementation

**Key Design Decision:** JIB only acts on explicitly tagged tickets (not all assigned tickets) to ensure human intent is clear and prevent unexpected automation.

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

**Decision:** Use JIRA labels (`jib`, `james-in-a-box`, or `JIB`) to identify tickets for automation.

See [Design Decisions](#1-jib-tag-mechanism-jira-label) for full rationale.

**Implementation:**
```python
def is_jib_tagged(ticket: dict) -> bool:
    """Check if ticket has JIB label (case-insensitive)."""
    labels = [l.lower() for l in ticket.get("labels", [])]
    return any(tag in labels for tag in ["jib", "james-in-a-box"])
```

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

**Note:** GCP production logs access is out of scope for Phase 1. Per the parent ADR (ADR-Autonomous-Software-Engineer), GCP read-only access is planned for Phase 2-3. For now, JIB relies on error information included in ticket descriptions.

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

# TRIVIAL if trivial_score >= 50 AND no auto-disqualifiers
```

**Decision:** Threshold of 50 with automatic disqualifiers. See [Design Decisions](#2-triviality-threshold-score--50-with-auto-disqualifiers) for details.

**Auto-Disqualifiers (bypass scoring, always non-trivial):**
- `security_implications`: True
- `data_migration`: True
- `multi_service`: True
- `public_api_change`: True
- `infrastructure_change`: True

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

When a fix is non-trivial, create a PR with a Collaborative Planning Framework (CPF) document. This document follows the CPF specification from the Collaborative Development Framework, ensuring JIB produces planning artifacts that enable structured human-LLM collaboration.

**CPF Alignment:**
- Follows CPF's "AI Drives, Human Steers" principle
- Produces artifacts that are both human-readable and machine-consumable
- Creates explicit checkpoint for human approval before implementation
- Surfaces ambiguities and questions proactively (not reactively during implementation)

**PR Contents:**

```markdown
# docs/plans/JIRA-XXX-{slug}.md

# Plan: {Ticket Title}

**JIRA:** [JIRA-XXX](link)
**Status:** Proposed - Awaiting Human Approval
**Complexity:** Non-trivial
**Estimated Scope:** {small|medium|large}
**Triviality Score:** {score}/100 (threshold: 50)
**Disqualifier(s):** {if any, e.g., "security implications", "multi-service"}

---

## Checkpoint: Planning Complete

> This document represents JIB's analysis of the JIRA ticket. Human approval is required before implementation begins.

### Summary
{2-3 sentence summary of what this ticket is about and what JIB proposes to do}

### Quick Actions
- [ ] **APPROVE** — JIB proceeds with implementation
- [ ] **APPROVE WITH NOTES** — JIB proceeds with adjustments (add comments to PR)
- [ ] **REVISE** — JIB needs to revisit analysis (request changes on PR)
- [ ] **REJECT** — Do not implement (close PR without merging)

---

## Requirements Analysis

### Goals
| Priority | Goal | Source |
|----------|------|--------|
| Primary | {main objective} | JIRA ticket |
| Secondary | {additional objective} | {inference/comment} |

### Functional Requirements
| ID | Requirement | Acceptance Criteria | Confidence |
|----|-------------|---------------------|------------|
| FR-1 | {requirement} | {testable criteria} | {high/medium/low} |
| FR-2 | ... | ... | ... |

### Non-Functional Requirements
| ID | Requirement | Target | Confidence |
|----|-------------|--------|------------|
| NFR-1 | {e.g., performance} | {measurable target} | {high/medium/low} |

### Out of Scope (Negative Requirements)
- {What this change will NOT do}
- {Explicit boundaries to prevent scope creep}

### Assumptions
| Assumption | Validated? | Impact if Wrong |
|------------|------------|-----------------|
| {assumption} | {yes/no/needs validation} | {impact} |

### Ambiguities & Questions

> **⚠️ Human input needed:** The following questions require clarification. JIB recommends addressing these before approving.

1. **{Question 1}**
   - **Context:** {why this matters for implementation}
   - **Options:**
     - A: {option description}
     - B: {option description}
   - **JIB Recommendation:** {recommendation with rationale}

2. **{Question 2}**
   - ...

---

## Technical Analysis

### Affected Areas
| File/Component | Change Type | Reason |
|---------------|-------------|--------|
| `path/to/file.py` | Modify | {reason} |
| `path/to/other.py` | Modify | {reason} |
| `path/to/new.py` | Create | {reason} |

### Dependencies
| Dependency | Type | Status |
|------------|------|--------|
| {library/service} | {internal/external} | {available/needs setup} |

### Risk Register
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| {risk description} | {High/Medium/Low} | {High/Medium/Low} | {mitigation strategy} |

---

## Design Options

### Option A: {Name} ⭐ (Recommended)
{Description of approach}

**Pros:**
- {benefit 1}
- {benefit 2}

**Cons:**
- {drawback 1}

**Trade-offs:**
- {trade-off consideration}

### Option B: {Name}
{Description of approach}

**Pros:**
- {benefit 1}

**Cons:**
- {drawback 1}
- {drawback 2}

### Decision Record
**Selected:** Option A
**Rationale:** {Why this option best balances the trade-offs for this use case}

---

## Implementation Plan

### Phase 1: {Name} (Estimated: {time})
**Objective:** {what this phase accomplishes}

| Task | Dependencies | Acceptance Criteria |
|------|--------------|---------------------|
| Task 1.1: {description} | None | {criteria} |
| Task 1.2: {description} | Task 1.1 | {criteria} |

**Phase 1 Checkpoint:** {what human should see before Phase 2}

### Phase 2: {Name} (Estimated: {time})
**Objective:** {what this phase accomplishes}

| Task | Dependencies | Acceptance Criteria |
|------|--------------|---------------------|
| Task 2.1: {description} | Phase 1 | {criteria} |
| Task 2.2: {description} | Task 2.1 | {criteria} |

---

## Test Strategy

| Test Type | Scope | Coverage Target |
|-----------|-------|-----------------|
| Unit Tests | {components} | {target} |
| Integration Tests | {flows} | {target} |
| Manual Testing | {scenarios} | {checklist} |

---

## Post-Approval Workflow

After human merges this planning PR:
1. **JIB detects merge** via GitHub sync
2. **JIB enters CPF implementation** following the phased plan above
3. **Implementation PR created** with code changes, tests, documentation
4. **Human reviews implementation PR** and merges when satisfied

---

**Generated by:** james-in-a-box
**Triaged from:** {JIRA ticket link}
**Context Sources:** {list of files/docs consulted}
**Awaiting:** Human review and approval (merge this PR to proceed)
```

**Template Quality Attributes (per CPF spec):**
- Each requirement has testable acceptance criteria
- Ambiguous language eliminated ("may", "might" → concrete decisions)
- Priorities are explicit
- Tasks are appropriately sized and can be started without further clarification
- Dependencies are explicit

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

**Decision:** PR merge triggers implementation. See [Design Decisions](#3-approval-detection-pr-merge-triggers-implementation) for details.

**Detection Flow:**
1. GitHub sync runs every 15 minutes
2. Detects merged PRs with planning docs in `docs/plans/`
3. Parses planning doc to extract implementation plan
4. Creates Beads task for implementation
5. Enters CPF implementation workflow

## Worked Example

To illustrate the workflow, here's a concrete example of how JIB would handle two different tickets:

### Example 1: Trivial Fix

**JIRA Ticket: INFRA-1234**
```
Title: Fix typo in error message
Description: The error message in slack-receiver.py line 45 says "recieved" instead of "received"
Labels: jib, bug
```

**JIB Processing:**
1. **Detection:** JIB sees `jib` label during hourly sync
2. **Context Gathering:** Reads `slack-receiver.py`, finds the typo
3. **Triviality Assessment:**
   - Files affected: 1 → +30 points
   - Change type: Bug fix → +20 points
   - Existing tests: Yes → +20 points
   - Requirements clear: Yes → +20 points
   - **Score: 90/100** → TRIVIAL
4. **Implementation:** JIB fixes the typo, runs tests
5. **PR Created:** `[JIB] Fix: INFRA-1234 Fix typo in error message`
6. **Notification:** Slack message with PR link

**Human Action:** Review PR, merge if good (1 minute)

### Example 2: Non-Trivial (Planning Required)

**JIRA Ticket: INFRA-5678**
```
Title: Add rate limiting to Slack receiver
Description: We're getting hammered by Slack retries. Need rate limiting to prevent overload.
Labels: jib, enhancement
```

**JIB Processing:**
1. **Detection:** JIB sees `jib` label during hourly sync
2. **Context Gathering:**
   - Reads `slack-receiver.py`, `incoming-processor.py`
   - Finds similar ticket INFRA-4321 (previous retry handling)
   - Loads ADR-Message-Queue-Slack-Integration for context
3. **Triviality Assessment:**
   - Files affected: 3+ → -20 points
   - Change type: Enhancement → +0 points
   - Existing tests: Partial → +0 points
   - Requirements: Ambiguous (what rate limit?) → -20 points
   - New dependencies: Maybe (Redis?) → -30 points
   - **Score: 30/100** → NON-TRIVIAL
4. **Planning Doc Created:**
   ```
   Questions identified:
   - What rate limit (requests/second)?
   - Per-user or global?
   - Redis-backed or in-memory?
   - What to do when limited (queue vs reject)?
   ```
5. **PR Created:** `[JIB] Plan: INFRA-5678 Add rate limiting to Slack receiver`
6. **Notification:** Slack message asking for plan review

**Human Action:**
- Review planning doc (5-10 minutes)
- Answer questions via PR comments
- Merge to approve

**JIB Detects Merge:**
- Reads approved plan
- Implements based on human's answers
- Creates implementation PR with code

## Design Decisions (Resolved Questions)

The following design decisions have been made based on analysis and system alignment:

### 1. JIB Tag Mechanism: JIRA Label

**Decision:** Use JIRA labels `jib` or `james-in-a-box` to tag tickets for automation.

**Rationale:**
- Easy to add/remove without custom field configuration
- Visible in JIRA UI (users can see which tickets are JIB-targeted)
- Queryable via JQL for monitoring and debugging
- Consistent with existing JIRA workflows
- No JIRA admin setup required

**Implementation:**
```python
JIB_TAG_LABELS = ["jib", "james-in-a-box", "JIB"]  # Case-insensitive matching
```

### 2. Triviality Threshold: Score >= 50 with Auto-Disqualifiers

**Decision:** Use a scoring system with threshold of 50, plus automatic disqualifiers for high-risk categories.

**Rationale:**
- Scoring system allows nuanced assessment
- Auto-disqualifiers prevent high-risk changes from bypassing planning
- Errs on side of caution (questionable → non-trivial → planning doc)

**Auto-Disqualifiers (always non-trivial regardless of score):**
- Security implications (authentication, authorization, encryption)
- Data migration or schema changes
- Multi-service changes (crosses service boundaries)
- Public API changes (breaking changes possible)
- Infrastructure/deployment changes

### 3. Approval Detection: PR Merge Triggers Implementation

**Decision:** When a planning document PR is merged, JIB detects this and proceeds with CPF implementation.

**Rationale:**
- Uses existing PR review workflow (no new tools)
- PR merge is an explicit human approval action
- Creates audit trail via git history
- Allows inline comments on planning doc before approval

**Implementation:**
```
Planning PR merged → GitHub webhook → JIB detects merged planning doc
                  → Extracts implementation plan from doc
                  → Enters CPF implementation workflow
                  → Creates implementation PR(s)
```

### 4. Repository Scope: Start with james-in-a-box

**Decision:** Initial rollout targets only `james-in-a-box` repository, with configuration to expand later.

**Rationale:**
- Lower risk for initial testing
- Self-referential (JIB improving itself)
- Team is familiar with the codebase
- Easy to expand via configuration once proven

**Configuration:**
```bash
JIB_TRIAGE_ENABLED_REPOS="jwbron/james-in-a-box"  # Comma-separated for expansion
```

### 5. Context Depth: Progressive with Cost Controls

**Decision:** Use progressive context gathering with token/cost limits.

**Levels:**
1. **Always gathered** (low cost): Ticket description, comments, linked tickets
2. **Smart gathered** (medium cost): Related code files (keyword/path matching), recent PRs touching similar files
3. **On-demand** (high cost): Full codebase search, historical ticket analysis

**Cost Control:**
```python
MAX_CONTEXT_TOKENS = 50000  # ~$0.15 at Claude pricing
CONTEXT_TIMEOUT_SECONDS = 60  # Don't spend too long gathering
```

### 6. Uncertainty Handling: Default to Non-Trivial

**Decision:** When triviality cannot be confidently determined, default to non-trivial (create planning doc).

**Rationale:**
- Safer: Planning doc is reviewed before implementation
- No wasted work: Planning doc still captures analysis
- Human can override by approving and requesting direct implementation

### 7. Human Override: Ticket Labels

**Decision:** Allow human override of classification via additional labels.

**Labels:**
- `jib-trivial`: Force trivial classification (skip planning, go straight to implementation)
- `jib-plan`: Force non-trivial classification (always create planning doc)

**Use Cases:**
- `jib-trivial`: Human knows the fix is simple despite JIB's scoring
- `jib-plan`: Human wants planning doc even for simple-seeming tickets

## Open Questions (To Be Resolved During Implementation)

### Important (Iteration Candidates)

1. **Learning/Feedback:** Should JIB track misclassifications to improve scoring?
   - *Leaning:* Yes, track in Beads with outcome labels (accurate/over-planned/under-planned)
   - *Defer to:* Phase 2 after initial rollout provides data

2. **Templates:** Should planning docs be customizable per project?
   - *Leaning:* Not initially; use standard CPF template
   - *Defer to:* Add customization if needed based on feedback

3. **Metrics:** What should we track?
   - *Leaning:* Time-to-PR, classification accuracy, planning doc approval rate, implementation success rate
   - *Defer to:* Implement basic metrics in Phase 1, expand in Phase 2

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

| Document | Relationship |
|----------|--------------|
| [ADR-Autonomous-Software-Engineer.md](ADR-Autonomous-Software-Engineer.md) | Parent ADR for JIB architecture; this ADR extends the JIRA integration described there |
| [Collaborative-Planning-Framework.md](../../../../collaborative-development-framework/docs/foundations/Collaborative-Planning-Framework.md) | CPF specification; planning documents follow this framework |
| [JIRA Connector README](../../../host-services/sync/context-sync/connectors/jira/README.md) | Current JIRA sync implementation; triage builds on this infrastructure |
| [Human-Driven-LLM-Navigated-Software-Development.md](../../../../collaborative-development-framework/docs/foundations/Human-Driven-LLM-Navigated-Software-Development.md) | Philosophy underlying the "AI Drives, Human Steers" approach |

## Appendix: Configuration Reference

```bash
# Environment variables for JIRA Triage Workflow
JIB_TRIAGE_ENABLED=true                          # Enable/disable triage workflow
JIB_TRIAGE_ENABLED_REPOS="jwbron/james-in-a-box" # Repos to process (comma-separated)
JIB_TAG_LABELS="jib,james-in-a-box"              # Labels that trigger JIB processing
JIB_TRIVIALITY_THRESHOLD=50                      # Score threshold for trivial classification
JIB_AUTO_SECURITY_NONTRIVIAL=true                # Security tickets always non-trivial
JIB_PLAN_OUTPUT_DIR="docs/plans"                 # Where to store planning docs
JIB_MAX_CONTEXT_TOKENS=50000                     # Token limit for context gathering
JIB_CONTEXT_TIMEOUT_SECONDS=60                   # Timeout for context gathering
```

---

**Next Action:** Review this spec, provide any additional feedback, then approve to begin implementation.
