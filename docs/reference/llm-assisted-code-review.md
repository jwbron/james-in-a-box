# LLM-First Code Reviews

**Status:** Draft
**Author:** James Wiesebron
**Created:** December 2025
**Purpose:** Practical guide to code review in a world where LLMs generate code faster than humans can review it

---

> **Part of:** [A Pragmatic Guide for Software Engineering in a Post-LLM World](../architecture/Pragmatic-Guide-Software-Engineering-Post-LLM-World.md)

---

## Introduction

This guide introduces our approach to code review in a world where LLMs generate code faster than humans can review it.

## What's Changing

**The old way:** You write code → You open a PR → A human reviewer checks everything → You fix their feedback → They re-review → Eventually it merges.

**The new way:** You write code → You open a PR → LLMs automatically review and fix issues → A human does a final approval → It merges.

The key insight:

> **If you as a reviewer see a pattern of feedback on a specific topic, it's your responsibility to add a linter to solve the problem systematically.**
>
> **If you're not able to do that, you should assess the value-add of the feedback.**

In other words: every piece of recurring feedback is a process failure. It should either be automated or questioned.

## Why This Matters

Traditional code review has problems:

- **Reviewers give the same feedback over and over** — "Add type hints," "Use const instead of let," "Missing docstring"
- **Different reviewers catch different things** — Inconsistent quality enforcement
- **Feedback comes late** — Issues found at PR time could've been caught at commit time
- **It doesn't scale** — When LLMs can generate PRs in minutes, human review becomes the bottleneck

We're solving this by flipping the model: **LLMs review first, humans approve last**.

## What This Means for Reviewers

Your job changes from "catch everything" to "focus on what matters":

**Still your job:**
- Does this meet the business requirements?
- Does the architecture make sense?
- Are there security implications I should flag?
- Is this the right direction strategically?

**No longer your job:**
- Checking for style issues (linters do this)
- Catching missing type hints (type checkers do this)
- Spotting common anti-patterns (LLM reviewers do this)
- Requesting minor fixes (LLM agents apply these automatically)

When you *do* find something the automated tools missed, don't just request a fix—ask yourself: "Can I add this to the automation so no one has to catch this manually again?"

## What This Means for PR Authors

Your workflow stays mostly the same, but with faster feedback:

1. **Pre-commit hooks catch issues immediately** — Before you even push, linters and formatters clean things up
2. **LLM reviewers catch semantic issues** — Over-engineering, unclear naming, missing error handling
3. **LLM agents apply fixes** — Many issues get auto-fixed without you lifting a finger
4. **Human review is the final step** — Focused on high-level concerns, not nitpicks

Result: Less back-and-forth, faster merges, cleaner code.

## The Review Stack

Different tools handle different concerns:

| What | Who handles it |
|------|----------------|
| Formatting, style, syntax | Linters (ruff, ESLint, prettier) |
| Type safety | Type checkers (mypy, TypeScript) |
| Security basics | SAST tools (detect-secrets, semgrep) |
| Code patterns, naming, duplication | LLM reviewer |
| Business logic, architecture, strategy | Human reviewer |

The goal: by the time a human sees the PR, all the mechanical issues are already resolved.

## The Key Principle

> **When you find yourself giving the same feedback twice, stop and automate it.**

This applies to everyone—not just tooling experts. If you don't know how to create an automated check yourself, raise it with the team. But "I'll just keep commenting this manually" is not an acceptable long-term answer.

Over time, this creates a self-improving system:

1. Human gives feedback on a PR
2. System notices "this feedback has appeared 3+ times"
3. A new automated check is proposed
4. Team approves the check
5. Future PRs never have this issue

Reviewers become *trainers* of the automation, not gatekeepers.

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
| [Human-Directed, LLM-Navigated Development](../architecture/LLM-First-Software-Development-Lifecycle.md) | Philosophy for human-LLM collaboration |
| [Radical Self-Improvement for LLMs](../architecture/Radical-Self-Improvement-for-LLMs.md) | Framework for autonomous LLM self-improvement |
| [ADR: Coding Standards in a Post-LLM World](../adr/not-implemented/ADR-Coding-Standards-Post-LLM-World.md) | Complete architectural decision record with implementation phases, success metrics, and technical specifications |

---

**Last Updated:** 2025-12-05
**Next Review:** 2026-01-05 (Monthly)
