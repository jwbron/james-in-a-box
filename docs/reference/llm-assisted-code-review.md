# LLM-First Code Reviews

**Status:** Draft
**Author:** James Wiesebron, james-in-a-box
**Created:** December 2025
**Purpose:** A practical guide to code review in a world where LLMs generate code faster than humans can review it

---

> **Part of:** [A Pragmatic Guide for Software Engineering in a Post-LLM World](../architecture/Pragmatic-Guide-Software-Engineering-Post-LLM-World.md)

---

LLMs can now generate code faster than humans can review it. This creates a fundamental problem: traditional code review becomes a bottleneck, not a quality gate.

This guide presents a solution: **invert the review model**. Instead of humans catching everything, let LLMs review first and humans approve last. The result is faster feedback, higher consistency, and human attention focused where it matters most.

**The key insight:**

> If you find yourself giving the same feedback twice, stop and automate it.

Every piece of recurring feedback represents a process failure. It should either become an automated check or be questioned as not worth giving.

---

## Table of Contents

- [The Shift](#the-shift)
- [What Changes for Reviewers](#what-changes-for-reviewers)
- [What Changes for PR Authors](#what-changes-for-pr-authors)
- [The Review Stack](#the-review-stack)
- [The Self-Improving System](#the-self-improving-system)
- [Getting Started](#getting-started)
- [Related Documents](#related-documents)

---

## The Shift

Traditional code review worked like this:

```
You write code → You open a PR → A human reviewer checks everything →
You fix their feedback → They re-review → Eventually it merges
```

The new model works like this:

```
You write code → You open a PR → LLMs automatically review and fix issues →
A human does a final approval → It merges
```

This matters because traditional review has accumulated problems:

- **Reviewers give the same feedback over and over** — "Add type hints," "Use const instead of let," "Missing docstring"
- **Different reviewers catch different things** — Inconsistent quality enforcement
- **Feedback comes late** — Issues found at PR time could've been caught at commit time
- **It doesn't scale** — When LLMs can generate PRs in minutes, human review becomes the bottleneck

We solve this by flipping the model: **LLMs review first, humans approve last**.

---

## What Changes for Reviewers

Your job shifts from "catch everything" to "focus on what matters."

### Still Your Job

- Does this meet the business requirements?
- Does the architecture make sense?
- Are there security implications I should flag?
- Is this the right direction strategically?

### No Longer Your Job

- Checking for style issues (linters do this)
- Catching missing type hints (type checkers do this)
- Spotting common anti-patterns (LLM reviewers do this)
- Requesting minor fixes (LLM agents apply these automatically)

### The New Responsibility

When you *do* find something the automated tools missed, don't just request a fix—ask yourself: "Can I add this to the automation so no one has to catch this manually again?"

If the answer is yes, you have a new responsibility: turn your feedback into an automated check. If you don't know how, raise it with the team. But "I'll just keep commenting this manually forever" is not an acceptable long-term answer.

---

## What Changes for PR Authors

Your workflow stays mostly the same, but with faster feedback:

1. **Pre-commit hooks catch issues immediately** — Before you even push, linters and formatters clean things up
2. **LLM reviewers catch semantic issues** — Over-engineering, unclear naming, missing error handling
3. **LLM agents apply fixes** — Many issues get auto-fixed without you lifting a finger
4. **Human review is the final step** — Focused on high-level concerns, not nitpicks

The result: less back-and-forth, faster merges, cleaner code.

---

## The Review Stack

Different tools handle different concerns. By the time a human sees the PR, all the mechanical issues should already be resolved.

| Concern | Handled By |
|---------|------------|
| Formatting, style, syntax | Linters (ruff, ESLint, prettier) |
| Type safety | Type checkers (mypy, TypeScript) |
| Security basics | SAST tools (detect-secrets, semgrep) |
| Code patterns, naming, duplication | LLM reviewer |
| Business logic, architecture, strategy | Human reviewer |

Notice how human attention sits at the top of the stack. Humans focus on judgment calls that require understanding business context, organizational goals, and strategic direction—things that can't be automated.

---

## The Self-Improving System

Over time, this creates a feedback loop that makes the system better:

```
1. Human gives feedback on a PR
           ↓
2. System notices "this feedback has appeared 3+ times"
           ↓
3. A new automated check is proposed
           ↓
4. Team approves the check
           ↓
5. Future PRs never have this issue
```

In this model, reviewers become **trainers** of the automation, not gatekeepers. Every piece of feedback you give has the potential to improve the system for everyone.

This is the connection to [Radical Self-Improvement for LLMs](../architecture/Radical-Self-Improvement-for-LLMs.md)—the review process isn't static, it evolves.

---

## Getting Started

If you're new to this approach:

1. **Trust the linters** — If something passed pre-commit, don't comment on formatting
2. **Focus on the big picture** — Architecture, business logic, security
3. **When in doubt, approve** — If the automated tools passed and you don't have high-level concerns, approve
4. **Document patterns** — When you give feedback, consider whether it should become a rule

The goal is not to eliminate human judgment—it's to focus human judgment where it matters most.

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
