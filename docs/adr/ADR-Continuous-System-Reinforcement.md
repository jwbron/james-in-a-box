# ADR: Continuous System Reinforcement Process

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** jib users, Engineering teams
**Proposed:** November 2025
**Status:** Proposed

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Process Overview](#process-overview)
- [Implementation Details](#implementation-details)
- [Reinforcement Categories](#reinforcement-categories)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)

## Context

### Background

jib (James-in-a-Box) is an autonomous software engineering agent that operates with minimal supervision. As jib evolves and handles increasingly complex tasks, changes can inadvertently introduce breakages - failed tests, broken functionality, or regressions.

Currently, when something breaks:
1. The immediate issue gets fixed
2. Specific tests may be added for that case
3. Learning is often not systematically captured
4. Similar issues may recur in different contexts

### Problem Statement

**Reactive fixes address symptoms, not root causes.** When jib introduces a change that breaks something, we typically:

- Fix the specific failure
- Move on to the next task

This approach misses opportunities to:
1. **Identify patterns** - Similar mistakes may repeat in different forms
2. **Strengthen processes** - The underlying workflow may have gaps
3. **Improve documentation** - Instructions (CLAUDE.md) may be ambiguous
4. **Enhance testing** - Test coverage may have blind spots
5. **Reinforce guardrails** - Safety mechanisms may be insufficient

### What We're Deciding

This ADR establishes a **systematic process for learning from breakages** that:

1. Captures the root cause at a higher process level (not just the specific bug)
2. Identifies preventive measures that generalize beyond the immediate fix
3. Updates documentation, tests, and guardrails to prevent recurrence
4. Creates a feedback loop that continuously strengthens the system

## Decision

**We will implement a Continuous System Reinforcement (CSR) process that triggers on every breakage.**

### Core Principle

> "Every failure is a system design flaw, not just a code bug."

When something breaks, the question isn't just "how do we fix this?" but:
- **Why did the system allow this to happen?**
- **What process change would have prevented this class of failure?**
- **How do we make this mistake impossible (or harder) in the future?**

## Process Overview

### The Reinforcement Loop

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CONTINUOUS SYSTEM REINFORCEMENT                      │
│                                                                           │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│   │  DETECT  │───▶│ ANALYZE  │───▶│ REINFORCE│───▶│ VALIDATE │          │
│   │ Breakage │    │ Root     │    │ System   │    │ Fix      │          │
│   │          │    │ Cause    │    │          │    │          │          │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘          │
│        │                                               │                  │
│        └───────────────────────────────────────────────┘                  │
│                         Feedback Loop                                     │
└───────────────────────────────────────────────────────────────────────────┘
```

### Step 1: DETECT - Identify the Breakage

Breakages can manifest as:
- Test failures (unit, integration, E2E)
- Build failures
- Lint/type check failures
- Runtime errors
- Unexpected behavior reported by human reviewer
- PR feedback identifying issues

### Step 2: ANALYZE - Root Cause Analysis

For each breakage, answer these questions:

**Immediate Cause:**
- What specific code change caused the failure?
- What was the direct technical error?

**Process Cause (CRITICAL):**
- Why didn't existing tests catch this?
- Why didn't existing documentation prevent this?
- Why didn't existing guardrails block this?
- What information was missing that would have helped?

**Pattern Recognition:**
- Have we seen similar failures before?
- Is this a one-off or part of a larger pattern?
- What category does this failure fall into?

### Step 3: REINFORCE - Strengthen the System

Based on analysis, implement one or more reinforcements:

| Reinforcement Type | Example Actions |
|--------------------|------------------|
| **Documentation** | Update CLAUDE.md with clearer guidance |
| **Testing** | Add tests that catch this failure class |
| **Guardrails** | Add pre-commit hooks, linting rules |
| **Process** | Add checklist items, workflow steps |
| **Tooling** | Create helper scripts, validation tools |

### Step 4: VALIDATE - Confirm the Fix

- Verify the original breakage is resolved
- Verify the reinforcement would have prevented it
- Run regression tests
- Document the reinforcement for future reference

## Implementation Details

### Reinforcement Record Template

When a breakage occurs, create a reinforcement record in `docs/reinforcements/`:

```markdown
# Reinforcement: [Brief Title]

**Date:** YYYY-MM-DD
**Breakage Type:** [Test Failure | Build Failure | Runtime Error | Review Feedback]
**Severity:** [Low | Medium | High | Critical]

## What Broke

[Brief description of the failure]

## Immediate Fix

[What code change resolved the immediate issue]

## Root Cause Analysis

### Technical Cause
[Direct technical reason for failure]

### Process Cause
[Why did the system allow this? What was missing?]

### Pattern Category
[See Reinforcement Categories below]

## Reinforcement Applied

### Type
[Documentation | Testing | Guardrail | Process | Tooling]

### Changes Made
- [ ] Change 1
- [ ] Change 2

### Files Modified
- `path/to/file.md` - Added guidance on X
- `path/to/test.py` - Added test for Y

## Prevention Validation

[How we verified this reinforcement would prevent recurrence]

## Lessons Learned

[Key takeaways that generalize beyond this specific case]
```

### Integration with CLAUDE.md

The CLAUDE.md file should be updated to include:

```markdown
## Breakage Response Protocol

When you cause or encounter a breakage:

1. **Fix the immediate issue first**
2. **Create a reinforcement record** in `docs/reinforcements/`
3. **Analyze at the process level** - Why did the system allow this?
4. **Apply reinforcement** - Update docs, add tests, strengthen guardrails
5. **Report the reinforcement** in your PR description or notification
```

### Periodic Review

Monthly, review all reinforcement records to:
- Identify recurring patterns
- Consolidate related reinforcements
- Update this ADR with new categories
- Assess overall system health

## Reinforcement Categories

### Category 1: Missing Test Coverage

**Pattern:** Code changes break functionality that had no test coverage

**Reinforcements:**
- Add unit tests for the specific case
- Add integration tests for the workflow
- Add test coverage requirements for changed files
- Update testing guidelines in CLAUDE.md

### Category 2: Ambiguous Documentation

**Pattern:** Instructions in CLAUDE.md or other docs were unclear or incomplete

**Reinforcements:**
- Clarify the ambiguous section
- Add concrete examples
- Add "do/don't" guidance
- Add links to related documentation

### Category 3: Missing Guardrails

**Pattern:** A mistake could have been caught by automated checks

**Reinforcements:**
- Add pre-commit hooks
- Add linting rules
- Add type checking requirements
- Add CI/CD validation steps

### Category 4: Workflow Gaps

**Pattern:** The process itself was missing a step or check

**Reinforcements:**
- Add checklist items
- Add workflow validation scripts
- Update step-by-step procedures
- Add verification commands

### Category 5: Insufficient Context

**Pattern:** Information needed to make the right decision wasn't available

**Reinforcements:**
- Update context-sync sources
- Add required reading before specific tasks
- Create reference documentation
- Improve error messages with guidance

### Category 6: Edge Cases Not Considered

**Pattern:** Unusual but valid scenarios weren't handled

**Reinforcements:**
- Document edge cases explicitly
- Add edge case tests
- Add input validation
- Update decision trees

### Category 7: External Dependencies

**Pattern:** Changes in external systems caused failures

**Reinforcements:**
- Add dependency version pinning
- Add health checks for external services
- Document external dependencies
- Add fallback handling

## Consequences

### Positive

1. **Compound improvement** - Each fix makes the system stronger for future work
2. **Pattern recognition** - Recurring issues become visible and addressable
3. **Knowledge capture** - Learnings are documented, not lost
4. **Reduced regressions** - Same mistakes become harder to make twice
5. **Better documentation** - CLAUDE.md evolves based on real experience
6. **Test coverage growth** - Test suite becomes more comprehensive over time

### Negative

1. **Increased overhead** - Each breakage requires additional analysis time
2. **Documentation maintenance** - Reinforcement records need periodic review
3. **Potential over-engineering** - Not every breakage needs a system-level response

### Mitigation for Negatives

- **Overhead:** Keep reinforcement records lightweight; 5-10 minutes max
- **Maintenance:** Consolidate records monthly; archive old ones
- **Over-engineering:** Use severity levels; Low severity may only need immediate fix

## Alternatives Considered

### Alternative 1: Fix and Move On (Current Approach)

**How it works:** Fix the immediate issue, add a specific test if needed, continue

**Why rejected:**
- Misses process-level improvements
- Same classes of mistakes recur
- No systematic learning

### Alternative 2: Formal Incident Reviews

**How it works:** Hold post-mortem meetings for each significant failure

**Why rejected:**
- Too heavyweight for an autonomous agent system
- Meeting-based process doesn't fit async workflow
- Slows down iteration speed

### Alternative 3: AI-Driven Analysis Only

**How it works:** Let the AI agent analyze breakages without human review

**Why rejected:**
- Misses human oversight on process changes
- May lead to over-complicated solutions
- Process changes should have human approval

### Selected Approach: Lightweight Continuous Reinforcement

**Why selected:**
- Async and document-based (fits jib workflow)
- Human reviews reinforcement proposals
- Minimal overhead per incident
- Cumulative effect over time
- Creates audit trail for improvement

## Related Documents

- [CLAUDE.md](../../CLAUDE.md) - jib operating instructions
- [ADR-Autonomous-Software-Engineer.md](./ADR-Autonomous-Software-Engineer.md) - jib architecture

## Revision History

| Date | Change |
|------|--------|
| 2025-11-28 | Initial proposal |
