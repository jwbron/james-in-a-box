# A Pragmatic Guide for Software Engineering in a Post-LLM World

**Status:** Draft
**Author:** James Wiesebron, james-in-a-box
**Created:** December 2025
**Purpose:** Strategic umbrella document connecting the three pillars of LLM-augmented software engineering

---

## Executive Summary

We are witnessing a fundamental shift in software engineering. Large Language Models have moved from experimental tools to practical collaborators capable of generating, reviewing, and maintaining code at unprecedented scale. This creates both opportunity and challenge: opportunity to amplify human capabilities, challenge to adapt our practices accordingly.

This document serves as a **strategic overview** connecting three complementary approaches to software engineering in the post-LLM era:

| Pillar | Focus | Document |
|--------|-------|----------|
| **1. LLM-First Code Reviews** | Lower the barrier to adoption by automating the review bottleneck | [LLM-First Code Reviews](../reference/llm-assisted-code-review.md) |
| **2. Human-Directed, LLM-Navigated Development** | Philosophical framework for human-LLM collaboration | [Human-Directed, LLM-Navigated Software Development](LLM-First-Software-Development-Lifecycle.md) |
| **3. Radical Self-Improvement** | Autonomous systems that continuously improve themselves | [Radical Self-Improvement for LLMs](Radical-Self-Improvement-for-LLMs.md) |

**The core thesis:** Software engineering practices must evolve to leverage LLM strengths (exhaustive attention, pattern consistency, tireless execution) while preserving human strengths (strategic judgment, creative problem-solving, interpersonal collaboration).

---

## Table of Contents

- [Why This Matters Now](#why-this-matters-now)
- [The Three Pillars](#the-three-pillars)
- [How They Work Together](#how-they-work-together)
- [Adoption Path](#adoption-path)
- [Key Principles](#key-principles)
- [What This Is Not](#what-this-is-not)
- [Getting Started](#getting-started)
- [References](#references)

---

## Why This Matters Now

### The Productivity Gap

LLMs can now generate code faster than humans can review it. This creates a bottleneck:

```
Before LLMs:        Code Generation ─────▶ Review ─────▶ Merge
                    (slow)                 (manageable)

With LLMs:          Code Generation ─────▶ Review ─────▶ Merge
                    (very fast)            (BOTTLENECK)
```

Traditional code review assumes human-speed code generation. When an LLM can produce a complete feature in minutes, waiting days for human review defeats the purpose.

### The Quality Question

Speed without quality is counterproductive. The question isn't "can LLMs generate code?" but rather:

- How do we ensure generated code meets our standards?
- How do we maintain consistency across an LLM-augmented codebase?
- How do we preserve human oversight without creating bottlenecks?
- How do we continuously improve the system itself?

### The Human Factor

Engineers are already overwhelmed. Adding "review LLM output" to their responsibilities without changing how review works leads to:

- Rubber-stamping (approving without genuine review)
- Burnout (trying to thoroughly review everything)
- Inconsistency (different reviewers catching different things)

We need practices that **reduce** human cognitive load while **increasing** code quality.

---

## The Three Pillars

### Pillar 1: LLM-First Code Reviews

**Problem:** Code review is a bottleneck that doesn't scale with LLM-speed code generation.

**Solution:** Invert the review model—LLMs review first, humans approve last.

**Key Insight:**
> Every piece of recurring human feedback represents a process failure. It should either be automated or questioned.

**Core Practices:**
- Automated tools (linters, type checkers, SAST) catch mechanical issues
- LLM reviewers catch semantic issues (patterns, naming, complexity)
- Human reviewers focus on strategy, architecture, and business logic
- Recurring feedback becomes new automated checks

**Why Start Here:** This pillar has the **lowest barrier to adoption**. Teams can begin with existing tooling and incrementally add LLM review capabilities. It produces immediate, measurable results (faster reviews, fewer iterations) without requiring philosophical buy-in.

**Read more:** [LLM-First Code Reviews](../reference/llm-assisted-code-review.md)

---

### Pillar 2: Human-Directed, LLM-Navigated Development

**Problem:** How should humans and LLMs collaborate on software development?

**Solution:** Humans drive strategy (the "driver"), LLMs handle structural rigor (the "navigator").

**Key Insight:**
> Humans and LLMs have complementary cognitive strengths. Optimal software development emerges when each focuses on what they do best.

**Division of Labor:**

| Human Responsibilities | LLM Responsibilities |
|----------------------|---------------------|
| Define vision and goals | Enumerate edge cases and considerations |
| Make strategic decisions | Ensure pattern consistency |
| Review and approve changes | Generate comprehensive tests |
| Handle novel situations | Keep documentation current |
| Collaborate with stakeholders | Track dependencies and implications |

**Core Philosophy:**
- Humans decide **what** and **why**
- LLMs handle **how** with precision
- Neither role is subordinate; both are essential
- Human judgment remains the final authority

**Read more:** [Human-Directed, LLM-Navigated Software Development](LLM-First-Software-Development-Lifecycle.md)

---

### Pillar 3: Radical Self-Improvement for LLMs

**Problem:** How do LLM systems improve over time without constant human intervention?

**Solution:** Build systems that proactively detect inefficiencies and propose improvements.

**Key Insight:**
> An LLM agent system should get measurably better at its job every week, automatically. Human oversight shifts from directing improvements to validating them.

**Four Sub-Pillars:**
1. **Automated Maintenance** - Repository hygiene, documentation sync, dependency health
2. **Continuous Self-Reflection** - Pattern detection, inefficiency analysis, root cause identification
3. **PR Review Reviewer** - Meta-review that improves the review process itself
4. **Strategic Human Feedback** - Escalating systemic issues, not fixing individual bugs

**The Shift:**
- **Old model:** Humans tell the system what to improve
- **New model:** System proposes improvements, humans validate

**Read more:** [Radical Self-Improvement for LLMs](Radical-Self-Improvement-for-LLMs.md)

---

## How They Work Together

The three pillars are not independent—they form a reinforcing system:

```
                    ┌──────────────────────────────────┐
                    │          UMBRELLA                │
                    │   Pragmatic Guide for Software   │
                    │   Engineering in Post-LLM World  │
                    └──────────────┬───────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   PILLAR 1      │     │   PILLAR 2      │     │   PILLAR 3      │
│   LLM-First     │     │   Human-Directed│     │   Radical       │
│   Code Reviews  │     │   LLM-Navigated │     │   Self-Improve  │
│                 │     │                 │     │                 │
│  Entry point,   │     │  Philosophy,    │     │  Continuous     │
│  immediate ROI  │────▶│  collaboration  │────▶│  evolution      │
│                 │     │  model          │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                         │                         │
         │                         │                         │
         └─────────────────────────┴─────────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────┐
                    │         FEEDBACK LOOP            │
                    │   Self-improvement informs       │
                    │   review practices and           │
                    │   collaboration patterns         │
                    └──────────────────────────────────┘
```

**The flow:**
1. **Start with Code Reviews** - Concrete, measurable, low risk
2. **Adopt the Philosophy** - Understand the human-LLM collaboration model
3. **Enable Self-Improvement** - Let the system evolve autonomously
4. **Feedback Loop** - Improvements inform all three pillars

---

## Adoption Path

### Phase 1: Immediate Wins (LLM-First Code Reviews)

**Goal:** Reduce review bottleneck, establish automated quality gates.

**Actions:**
- Enable comprehensive linting and type checking
- Add LLM-based PR review (pre-approval comments)
- Track recurring review feedback
- Begin automating repeated patterns

**Success Metrics:**
- Time from PR open to merge decreases
- Human review comments decrease
- Automated catch rate increases

### Phase 2: Philosophy Alignment (Human-Directed, LLM-Navigated)

**Goal:** Establish clear human-LLM collaboration patterns.

**Actions:**
- Define what decisions require human judgment
- Create structured handoff formats
- Establish review checkpoints
- Train team on new collaboration model

**Success Metrics:**
- Clearer task specifications
- Reduced back-and-forth
- Higher first-attempt success rate

### Phase 3: Autonomous Evolution (Radical Self-Improvement)

**Goal:** Enable continuous, autonomous improvement.

**Actions:**
- Implement self-reflection infrastructure
- Enable PR Review Reviewer
- Set up automated maintenance
- Define escalation criteria

**Success Metrics:**
- System generates improvement proposals
- Proposal acceptance rate >70%
- Decreasing human intervention over time

---

## Key Principles

### 1. Humans Remain in Control

LLMs are powerful tools, not autonomous decision-makers. Humans:
- Set strategic direction
- Make judgment calls on trade-offs
- Approve all changes before deployment
- Can override any automated decision

### 2. Automation Should Reduce Burden, Not Add It

Every automated system should make humans' lives easier:
- Less cognitive load, not more
- Faster feedback, not more noise
- Clearer decisions, not more complexity

### 3. Quality Through Consistency

LLMs excel at applying patterns consistently. Use this to:
- Enforce standards across the entire codebase
- Catch issues that humans might miss
- Maintain documentation in sync with code

### 4. Continuous Improvement Is Built In

The system should get better over time:
- Recurring issues become automated checks
- Human feedback improves LLM behavior
- Documentation evolves with the code

### 5. Transparency and Observability

All automated actions should be:
- Visible (humans can see what's happening)
- Explainable (humans can understand why)
- Reversible (humans can undo if needed)

---

## What This Is Not

### Not a Replacement for Human Judgment

LLMs cannot:
- Understand business context you haven't explained
- Make trade-offs only humans can evaluate
- Take accountability for decisions
- Replace the need for human oversight

### Not a Silver Bullet

This approach requires:
- Investment in tooling and infrastructure
- Team training and buy-in
- Ongoing calibration and adjustment
- Clear ownership and accountability

### Not "Set and Forget"

Even self-improving systems need:
- Human validation of improvements
- Periodic review of system behavior
- Adjustment as requirements change
- Intervention when things go wrong

---

## Getting Started

### For Individual Contributors

1. **Read the Code Reviews guide** - Understand the new review model
2. **Trust the automation** - If linters passed, focus on bigger issues
3. **Give feedback intentionally** - Your comments train the system
4. **Focus on what matters** - Strategy, architecture, business logic

### For Tech Leads

1. **Enable the tooling** - Linters, type checkers, LLM review
2. **Model the behavior** - Focus your reviews on high-level concerns
3. **Champion automation** - When you see patterns, propose checks
4. **Track metrics** - Measure review time, iteration count, catch rate

### For Engineering Leadership

1. **Set the vision** - Commit to LLM-augmented development
2. **Invest in infrastructure** - Tooling, training, measurement
3. **Celebrate wins** - Recognize when automation improves quality
4. **Stay involved** - Validate that human oversight remains meaningful

---

## References

### This Document Series

| Document | Focus |
|----------|-------|
| [LLM-First Code Reviews](../reference/llm-assisted-code-review.md) | Practical guide to LLM-assisted review |
| [Human-Directed, LLM-Navigated Development](LLM-First-Software-Development-Lifecycle.md) | Collaboration philosophy |
| [Radical Self-Improvement for LLMs](Radical-Self-Improvement-for-LLMs.md) | Autonomous improvement framework |
| [ADR: Coding Standards in a Post-LLM World](../adr/not-implemented/ADR-Coding-Standards-Post-LLM-World.md) | Technical implementation details |

### External Resources

- [AWS AI-Driven Development Life Cycle](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/)
- [Atlassian HULA Framework](https://www.atlassian.com/blog/atlassian-engineering/hula-blog-autodev-paper-human-in-the-loop-software-development-agents)
- [Anthropic Claude Best Practices](https://docs.anthropic.com/claude/docs/claude-for-work)

---

**Last Updated:** 2025-12-05
**Next Review:** 2026-01-05 (Monthly)
