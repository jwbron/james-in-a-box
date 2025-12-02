# LLM-Assisted Code Review Guide

A practical guide for dramatically increasing PR review efficiency through LLM automation.

## The Core Insight

> **LLM agents review every PR first. LLM agents auto-apply their own feedback. Humans approve the refined result.**
>
> **When humans request changes, that's a failure of the automated review process—and a signal to improve it.**

This inverts the traditional review model:

| Traditional | LLM-First |
|-------------|-----------|
| PR created → Human reviews → Developer fixes → Human re-reviews → Merge | PR created → LLM reviews → LLM fixes → Human approves → Merge |

Human reviewers become the *escalation path*, not the primary gate.

## The Review Stack

Different concerns belong at different layers:

| Layer | Handled By | Examples |
|-------|------------|----------|
| **Syntax & Style** | Linters (ruff, ESLint, prettier) | Formatting, import order, naming conventions |
| **Type Safety** | Type checkers (mypy, TypeScript) | Missing types, type mismatches |
| **Security Basics** | SAST tools (detect-secrets, semgrep) | Hardcoded secrets, common vulnerabilities |
| **Pattern Compliance** | LLM reviewer | Over-engineering, scope creep, naming clarity, code duplication, missing tests |
| **Implementation Quality** | LLM reviewer | Error handling, edge cases, performance concerns |
| **Business Logic** | Human reviewer (final pass) | Requirements fit, domain correctness |
| **Architecture** | Human reviewer (final pass) | Design decisions, system impact |
| **Strategy** | Human reviewer (final pass) | Direction, priorities, novel concerns |

**Key principle:** Human reviewers should rarely request changes. When they do, it signals the automated layer needs improvement.

## The Reviewer's New Role

```
When reviewing a PR:
├─ Does it meet business requirements? → Approve or discuss
├─ Does the architecture make sense? → Approve or discuss
├─ Did I find an issue the LLM missed?
│   ├─ Yes → Add to LLM review prompt, then request changes
│   │        (Make the automated process catch this next time)
│   └─ No → Approve
└─ Am I leaving line-by-line feedback?
    └─ Yes → STOP. The LLM should be doing this.
             Add this feedback pattern to the LLM reviewer.
```

## The Automation Responsibility

> **If you as a reviewer see a pattern of feedback on a specific topic, it's your responsibility to add it to the LLM review prompt or create an automated check.**
>
> **If you can't create the automated check yourself, escalate it. But if you're repeatedly giving the same feedback without automating it, you're wasting everyone's time—including your own.**

This is a forcing function. Reviewers who repeatedly provide low-level feedback instead of automating it will be visible through metrics:

- **Comments per PR** — High numbers indicate operating at wrong level
- **% of comments that become automated checks** — Low % after coaching = problem
- **Comment abstraction level** — Architecture/strategy vs style/syntax

These metrics are diagnostic, not punitive—until coaching fails.

## The Self-Improving Review Loop

The **PR Review Reviewer** pattern closes the feedback loop:

```
Human provides feedback → Pattern detected → New check auto-generated → Human approves → Future PRs pass automatically
```

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    The Self-Improving Review Loop                            │
│                                                                              │
│    Human provides      PR Review Reviewer     New check auto-                │
│    feedback on PR  ──▶ detects pattern   ──▶  generated and     ◀──┐        │
│                        (3+ occurrences)       proposed as PR       │        │
│                                                                     │        │
│                                    │                                │        │
│                                    ▼                                │        │
│                         ┌──────────────────────┐                    │        │
│                         │  Human approves      │                    │        │
│                         │  or rejects check    │────────────────────┘        │
│                         └──────────────────────┘                             │
│                                    │                                         │
│                                    ▼                                         │
│                         ┌──────────────────────┐                             │
│                         │  Check catches       │                             │
│                         │  future issues       │                             │
│                         │  automatically       │                             │
│                         └──────────────────────┘                             │
│                                                                              │
│  Result: Human feedback becomes rarer over time as the system learns         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

Human reviewers become *trainers* of the automated system. Their feedback improves not just the current PR, but all future PRs.

## The Two-Agent Pattern

The most efficient implementation uses two LLM agents:

1. **Reviewer Agent**: Analyzes the PR, identifies issues, posts review comments
2. **Fixer Agent**: Reads the review comments, applies the suggested changes, pushes fixes

```
Author creates PR
       ↓
Reviewer Agent analyzes → Posts comments
       ↓
Fixer Agent reads comments → Applies fixes → Pushes
       ↓
Reviewer Agent re-analyzes → Approves (or iterates)
       ↓
Human does final review → Approves or provides high-level feedback
```

Most issues are resolved without human involvement.

## Why LLMs Can Review Better Than Linters

Traditional linters catch issues expressible as AST patterns or regex. But many recurring PR feedback themes require semantic understanding:

- "This is over-engineered for the current requirements"
- "This PR includes changes unrelated to its stated purpose"
- "These variable names don't clearly communicate intent"
- "This abstraction is premature"
- "Missing test coverage for this edge case"
- "This duplicates logic from X module"

**LLMs can catch all of these.** And critically, another LLM agent can usually *fix* them automatically.

## Acknowledging LLM Limitations

LLMs are not perfect reviewers. They can:

- Miss subtle bugs requiring deep domain knowledge
- Overlook security implications depending on deployment context
- Suggest changes that technically work but don't fit the architecture
- Generate false positives, especially on unfamiliar codebases

**The goal is not perfection—it's efficiency.** If LLM review catches 80% of issues automatically, that's an 80% reduction in human review effort. The remaining 20% is where human expertise adds the most value.

## Pattern Detection and Check Generation

When the PR Review Reviewer detects patterns in human feedback:

| Feedback Pattern | Generated Check Type | Example |
|-----------------|---------------------|---------|
| "Add type hints" | Ruff rule enablement | Enable ANN rules, create PR |
| "Use pathlib instead of os.path" | Custom linter rule | Add PTH rules to ruff config |
| "Missing error handling for X" | LLM review prompt update | Add to REVIEW_PROMPT |
| "This duplicates code in Y" | Custom cross-file check | Generate semgrep pattern |
| "Follow the pattern in Z" | LLM review prompt example | Add example to prompt |

## Success Metrics

**System-level:**
- % of PRs that pass human review with no requested changes
- Average human review comments per PR (should decrease over time)
- % of LLM suggestions auto-applied vs manually addressed
- Reduction in recurring feedback patterns over time

**Reviewer-level (creates accountability):**
- Comments per PR by reviewer
- % of comments that trigger new automated checks
- Comment abstraction level (architecture/strategy vs style/syntax)

## The Workflow: Complain → Automate → Enforce

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Complain → Automate → Enforce                         │
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐             │
│  │   COMPLAIN   │────▶│   AUTOMATE   │────▶│   ENFORCE    │             │
│  │              │     │              │     │              │             │
│  │ "I've given  │     │ Write a      │     │ Add to CI,   │             │
│  │  this same   │     │ linter rule, │     │ pre-commit,  │             │
│  │  feedback    │     │ custom check,│     │ or editor    │             │
│  │  3+ times"   │     │ or script    │     │ config       │             │
│  └──────────────┘     └──────────────┘     └──────────────┘             │
│                                                                          │
│  Outputs:                                                                │
│  - No PR ever has this issue again                                      │
│  - Reviewer time freed for higher-value work                            │
│  - Standard is explicit and documented                                  │
│  - Agent (jib) learns the rule automatically                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Reference

| Traditional Behavior | LLM-First Behavior |
|---------------------|-------------------|
| Leave detailed line comments | Add pattern to LLM reviewer |
| Manually check for style issues | Trust linters |
| Re-review after fixes | Let LLM handle iterations |
| Approve when "good enough" | Approve when architecture/strategy is sound |
| Give same feedback repeatedly | Automate after 2nd occurrence |

---

**Related:** See [ADR: Coding Standards in a Post-LLM World](../adr/in-progress/ADR-Coding-Standards-Post-LLM-World.md) for the full architectural decision record.
