# LLM-First Code Reviews

**Status:** Draft
**Author:** James Wiesebron, james-in-a-box
**Created:** December 2025
**Purpose:** A philosophy and framework for code review where LLMs handle mechanical validation and humans focus on strategic judgment

---

> **Part of:** [A Pragmatic Guide for Software Engineering in a Post-LLM World](../architecture/Pragmatic-Guide-Software-Engineering-Post-LLM-World.md)

---

This document articulates a fundamental shift in how we think about code review: **LLM-first, human-last**. The core insight is that traditional code review has become misaligned with how software is actually developed in the LLM era.

**The problem:** LLMs can now generate code faster than humans can review it. Traditional code review—where humans catch everything—becomes a bottleneck, not a quality gate.

**The solution:** Invert the review model. Let LLMs handle mechanical validation while humans focus on strategic judgment. The result is faster feedback, higher consistency, and human attention directed where it matters most.

**The goal:** Free human reviewers from repetitive, automatable feedback so they can focus on what only humans can evaluate—business context, architectural direction, and strategic alignment.

---

## Table of Contents

- [The Core Philosophy](#the-core-philosophy)
- [The Transformation](#the-transformation)
- [Division of Review Responsibilities](#division-of-review-responsibilities)
- [The Review Stack](#the-review-stack)
- [Benefits for Reviewers](#benefits-for-reviewers)
- [Benefits for Teams](#benefits-for-teams)
- [The Self-Improving System](#the-self-improving-system)
- [Implementation Patterns](#implementation-patterns)
- [Anti-Patterns to Avoid](#anti-patterns-to-avoid)
- [Getting Started](#getting-started)
- [Related Documents](#related-documents)

---

## The Core Philosophy

### The Key Insight

> If you find yourself giving the same feedback twice, stop and automate it.

Every piece of recurring feedback represents a process failure. It should either become an automated check or be questioned as not worth giving. This simple principle drives everything that follows.

### Why Traditional Review Fails at Scale

Traditional code review places an enormous burden on human reviewers:

```
┌────────────────────────────────────────────────────────────────┐
│              TRADITIONAL REVIEW COGNITIVE LOAD                 │
│                                                                │
│  Strategic Concerns        │  Mechanical Concerns              │
│  ─────────────────         │  ──────────────────               │
│  • Does this solve the     │  • Is this formatted correctly?   │
│    right problem?          │  • Are type hints present?        │
│  • Is the architecture     │  • Is naming consistent?          │
│    sound?                  │  • Are there obvious bugs?        │
│  • Are there security      │  • Is documentation current?      │
│    implications?           │  • Are tests comprehensive?       │
│  • Is this the right       │  • Are patterns followed?         │
│    direction?              │  • Are imports organized?         │
│                            │                                   │
│        (~30%)              │          (~70%)                   │
└────────────────────────────────────────────────────────────────┘
```

The majority of reviewer attention goes toward mechanical concerns—tasks that require tedious attention to detail rather than strategic insight. This is backwards.

### The LLM-First Model

```
┌────────────────────────────────────────────────────────────────┐
│              LLM-FIRST REVIEW RESPONSIBILITY                   │
│                                                                │
│     HUMAN REVIEWER         │      LLM REVIEWER                 │
│     ──────────────         │      ────────────                 │
│  • Does this solve the     │  • Format and style validation    │
│    right problem?          │  • Type safety verification       │
│  • Is the architecture     │  • Pattern consistency checks     │
│    sound?                  │  • Common anti-pattern detection  │
│  • Are there security      │  • Documentation completeness     │
│    implications?           │  • Test coverage analysis         │
│  • Is this the right       │  • Naming convention enforcement  │
│    direction?              │  • Automatic fix application      │
│  • Should we proceed?      │                                   │
│                            │                                   │
│  Strategic, Judgment-based │  Mechanical, Rule-based           │
└────────────────────────────────────────────────────────────────┘
```

Human attention is now concentrated entirely on what requires human judgment.

---

## The Transformation

### The Old Way

```
Developer writes code
        ↓
Developer opens PR
        ↓
Human reviewer checks EVERYTHING
  • Formatting ← tedious
  • Types ← automatable
  • Patterns ← automatable
  • Architecture ← requires judgment
  • Business logic ← requires judgment
        ↓
Developer fixes feedback
        ↓
Reviewer re-reviews
        ↓
Repeat until approved
        ↓
Eventually merges (days later)
```

### The New Way

```
Developer writes code
        ↓
Pre-commit hooks catch formatting, linting
        ↓
Developer opens PR
        ↓
LLM reviewer analyzes automatically
  • Patterns, naming, anti-patterns
  • Suggests or applies fixes
        ↓
Human reviewer focuses on:
  • Business requirements
  • Architecture decisions
  • Security implications
  • Strategic direction
        ↓
Approval (same day)
```

### Why This Matters Now

Traditional review accumulated problems that LLMs can solve:

| Problem | Traditional Impact | LLM-First Solution |
|---------|-------------------|-------------------|
| Same feedback given repeatedly | Reviewer fatigue, inconsistency | Automated once, enforced forever |
| Different reviewers catch different things | Inconsistent quality | Uniform rule application |
| Feedback comes late | Wasted developer time | Issues caught at commit time |
| Review doesn't scale | Bottleneck when PRs increase | Parallel automated review |
| Nitpicks dominate discussion | Important feedback gets lost | Mechanical issues pre-resolved |

---

## Division of Review Responsibilities

### What Humans Review

| Domain | Focus | Why Human |
|--------|-------|-----------|
| **Business Requirements** | Does this solve the actual problem? | Requires understanding user needs, business context |
| **Architecture** | Is this the right structural approach? | Requires system-wide judgment, trade-off analysis |
| **Security** | Are there implications to flag? | Requires threat modeling, risk assessment |
| **Strategy** | Is this the right direction? | Requires organizational knowledge, roadmap awareness |
| **Novel Situations** | How do we handle this unprecedented case? | Requires creative problem-solving |

### What LLMs Review

| Domain | Focus | Why LLM |
|--------|-------|---------|
| **Formatting** | Style consistency | Perfect pattern matching |
| **Types** | Type safety | Exhaustive verification |
| **Patterns** | Convention adherence | Tireless consistency |
| **Common Bugs** | Obvious errors | Known anti-pattern detection |
| **Documentation** | Completeness | No resistance to "boring" checks |
| **Tests** | Coverage gaps | Systematic enumeration |

### The Handoff Principle

When a human reviewer catches something mechanical, the response shouldn't be "please fix this"—it should be "how do we automate catching this?"

```
Human catches issue
        ↓
Ask: "Can this be automated?"
        ↓
    ┌───┴───┐
   Yes      No
    ↓        ↓
Automate  Accept as
it        human-review item
    ↓
Future PRs never
have this issue
```

---

## The Review Stack

Different tools handle different concerns. By the time a human sees the PR, mechanical issues should already be resolved.

```
┌────────────────────────────────────────────────────────────────┐
│                     THE REVIEW STACK                           │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  HUMAN REVIEWER (Top of Stack)                           │  │
│  │  • Business logic, architecture, strategy                │  │
│  │  • Judgment calls requiring context                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ▲                                    │
│                           │ Only strategic concerns reach here │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  LLM REVIEWER                                            │  │
│  │  • Code patterns, naming, duplication                    │  │
│  │  • Semantic issues, over-engineering                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ▲                                    │
│                           │ Semantic issues filtered          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  STATIC ANALYSIS (SAST)                                  │  │
│  │  • Security basics (detect-secrets, semgrep)             │  │
│  │  • Vulnerability patterns                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ▲                                    │
│                           │ Security issues filtered          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  TYPE CHECKERS                                           │  │
│  │  • Type safety (mypy, TypeScript)                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           ▲                                    │
│                           │ Type errors filtered              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  LINTERS & FORMATTERS (Base of Stack)                    │  │
│  │  • Style, formatting, syntax (ruff, ESLint, prettier)    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

Each layer filters out its category of issues. Human reviewers only see what requires human judgment.

---

## Benefits for Reviewers

### Cognitive Relief

When LLMs handle mechanical validation:

- **Reduced mental fatigue** — No more scanning for typos, style violations, missing types
- **Fewer context switches** — Stay in strategic thinking mode
- **Less repetition** — Never give the same feedback twice
- **More sustainable pace** — Review energy isn't depleted by tedious checks

### Focus on High-Value Work

With mechanical concerns automated, reviewers can concentrate on:

- **Mentorship** — Teaching architectural thinking, not style rules
- **Design discussions** — Debating approaches, not formatting
- **Security review** — Actual threat modeling, not "add input validation"
- **Strategic alignment** — Ensuring code moves the product forward

### Better Decision Quality

When reviewers aren't mentally exhausted:

- **Clearer thinking** — Full cognitive capacity for important decisions
- **Deeper review** — Time to actually understand the change
- **More thoughtful feedback** — Quality over quantity
- **Healthier skepticism** — Energy to question assumptions

---

## Benefits for Teams

### Faster Feedback Loops

| Metric | Traditional | LLM-First |
|--------|-------------|-----------|
| Time to first feedback | Hours-days | Minutes |
| Review iterations | 3-5 | 1-2 |
| Time to merge | Days | Hours |
| Reviewer availability | Scarce | Augmented |

### Consistent Quality

- **Uniform enforcement** — Same rules applied to every PR
- **No reviewer lottery** — Quality doesn't depend on who reviews
- **Institutional knowledge captured** — Patterns encoded in automation
- **Reduced bus factor** — Standards exist independent of individuals

### Healthier Collaboration

When reviews focus on substance:

- **Less friction** — Feedback is about design, not nitpicks
- **More learning** — Discussions are educational, not pedantic
- **Better relationships** — Reviews feel collaborative, not adversarial
- **Sustainable culture** — Review doesn't cause burnout

---

## The Self-Improving System

### The Feedback-to-Automation Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                 SELF-IMPROVING REVIEW SYSTEM                    │
│                                                                 │
│     ┌─────────────────┐                                         │
│     │ Human gives     │                                         │
│     │ feedback on PR  │                                         │
│     └────────┬────────┘                                         │
│              ↓                                                  │
│     ┌─────────────────┐                                         │
│     │ System tracks:  │                                         │
│     │ "Feedback X     │                                         │
│     │  appeared 3+    │                                         │
│     │  times"         │                                         │
│     └────────┬────────┘                                         │
│              ↓                                                  │
│     ┌─────────────────┐                                         │
│     │ New automated   │                                         │
│     │ check proposed  │                                         │
│     └────────┬────────┘                                         │
│              ↓                                                  │
│     ┌─────────────────┐                                         │
│     │ Team reviews    │                                         │
│     │ and approves    │                                         │
│     └────────┬────────┘                                         │
│              ↓                                                  │
│     ┌─────────────────┐                                         │
│     │ Future PRs      │                                         │
│     │ never have      │                                         │
│     │ this issue      │                                         │
│     └─────────────────┘                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Reviewers as Trainers

In this model, human reviewers become **trainers** of the automation, not gatekeepers:

- Every piece of feedback potentially improves the system
- Giving feedback once is an investment in never giving it again
- The system gets smarter over time
- Reviewer expertise is multiplied across all future PRs

This connects to [Radical Self-Improvement for LLMs](../architecture/Radical-Self-Improvement-for-LLMs.md)—the review process isn't static, it evolves.

---

## Implementation Patterns

### Pattern 1: Pre-Commit Automation

Catch issues before code is even committed:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: format
        name: Format code
        entry: ruff format
        language: system
      - id: lint
        name: Lint code
        entry: ruff check --fix
        language: system
      - id: typecheck
        name: Type check
        entry: mypy
        language: system
```

### Pattern 2: LLM Review Integration

Configure LLM reviewers to run on every PR:

```yaml
# LLM review triggers
on_pr_opened:
  - check_patterns
  - check_naming
  - check_complexity
  - suggest_improvements

on_feedback_pattern:
  threshold: 3
  action: propose_automation
```

### Pattern 3: Human Review Focus Areas

Guide human reviewers on what to focus on:

```markdown
## Human Review Checklist

- [ ] Does this PR solve the stated problem?
- [ ] Is the architecture appropriate for this change?
- [ ] Are there security implications?
- [ ] Does this align with our technical direction?
- [ ] Would I be comfortable deploying this?

Note: Style, formatting, and mechanical issues are handled
by automated tools. Focus on strategic concerns.
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Duplicate Feedback

**Problem:** Human comments on something a linter should catch

```
Human: "Please use const instead of let here"
```

**Why it fails:** Wastes human attention on automatable concerns.

**Solution:** Add a lint rule; never comment on this again.

### Anti-Pattern 2: Style Debates in PRs

**Problem:** Reviewers argue about formatting, naming conventions

```
Reviewer A: "I prefer camelCase for this"
Reviewer B: "snake_case is more readable"
```

**Why it fails:** Style debates should happen once, then be encoded.

**Solution:** Establish conventions in automation; PRs follow rules, not opinions.

### Anti-Pattern 3: Rubber-Stamp Reviews

**Problem:** Human approves without substantive review

```
Human: "LGTM" (after 30 seconds on 500-line change)
```

**Why it fails:** Defeats the purpose of human oversight.

**Solution:** If automated tools pass and you have no strategic concerns, explicitly note what you checked.

### Anti-Pattern 4: Reviewing What's Already Validated

**Problem:** Human re-checks things that passed automated validation

```
Human: "Are you sure the types are correct?"
(Types already validated by mypy)
```

**Why it fails:** Duplicates work that's already done better by machines.

**Solution:** Trust the automation. Focus on what it can't check.

---

## Getting Started

### For Reviewers

1. **Trust the automation** — If pre-commit passed, don't comment on formatting
2. **Focus on strategy** — Architecture, business logic, security, direction
3. **Think "automate or accept"** — Every manual comment should either become a rule or be acknowledged as human-only
4. **When in doubt, approve** — If automated tools passed and you have no strategic concerns, approve

### For Teams

1. **Audit your feedback** — What comments are given repeatedly? Automate them.
2. **Configure the stack** — Linters → Type checkers → SAST → LLM reviewers → Human reviewers
3. **Define human focus areas** — Explicitly list what humans should review
4. **Track the loop** — Monitor feedback patterns; propose new automation

### The Goal

The goal is not to eliminate human judgment—it's to focus human judgment where it matters most.

When humans review architecture and strategy while machines handle mechanics, everyone wins: reviewers are more engaged, developers get faster feedback, and code quality improves.

---

## Related Documents

| Document | Description |
|----------|-------------|
| [A Pragmatic Guide for Software Engineering in a Post-LLM World](../architecture/Pragmatic-Guide-Software-Engineering-Post-LLM-World.md) | Strategic umbrella connecting all three pillars |
| [Human-Driven, LLM-Navigated Development](../architecture/Human-Driven-LLM-Navigated-Software-Development.md) | Philosophy for human-LLM collaboration |
| [Radical Self-Improvement for LLMs](../architecture/Radical-Self-Improvement-for-LLMs.md) | Framework for autonomous LLM self-improvement |
| [ADR: Coding Standards in a Post-LLM World](../adr/not-implemented/ADR-Coding-Standards-Post-LLM-World.md) | Complete architectural decision record with implementation phases and technical specifications |

---

**Last Updated:** 2025-12-05
**Next Review:** 2026-01-05 (Monthly)
