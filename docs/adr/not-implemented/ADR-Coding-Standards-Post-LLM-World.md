# ADR: Coding Standards in a Post-LLM World

**Driver:** Engineering Leadership
**Approver:** TBD
**Contributors:** James Wiesebron, jib (Autonomous Agent)
**Informed:** Engineering teams
**Proposed:** December 2025
**Status:** In Progress

## Table of Contents

- [Executive Summary](#executive-summary)
- [Context](#context)
  - [The Problem: PR Review is a Bottleneck](#the-problem-pr-review-is-a-bottleneck)
  - [The Post-LLM Reality](#the-post-llm-reality)
  - [The Insight: Automate Recurring Feedback](#the-insight-automate-recurring-feedback)
- [Decision](#decision)
  - [The Core Principle](#the-core-principle)
  - [The Automation Responsibility](#the-automation-responsibility)
  - [The Review Stack](#the-review-stack)
  - [The Workflow](#the-workflow)
- [Implementation](#implementation)
  - [Tier 1: Pre-Commit Hooks](#tier-1-pre-commit-hooks-instant-feedback)
  - [Tier 2: CI Pipeline](#tier-2-ci-pipeline-comprehensive)
  - [Tier 3: LLM Review](#tier-3-llm-review-semantic-understanding)
  - [Tier 4: PR Review Reviewer](#tier-4-the-pr-review-reviewer-self-improvement)
- [Success Metrics](#success-metrics)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)
- [Implementation Status](#implementation-status)
- [Related Documents](#related-documents)

## Executive Summary

This ADR establishes new coding standards for a world where LLMs generate code faster than humans can review it. The solution: **invert the review model—LLMs review first, humans approve last**. The core mechanism is a self-improving feedback loop where recurring human review comments automatically become automated checks.

**The Core Insight:**

> **If you as a reviewer see a pattern of feedback on a specific topic, it's your responsibility to add a linter to solve the problem systematically.**
>
> **If you're not able to do that, you should assess the value-add of the feedback.**

Every piece of recurring feedback represents a process failure. It should either be automated or questioned.

For practical implementation guidance, see the [LLM-Assisted Code Review Guide](../../reference/llm-assisted-code-review.md).

## Context

### The Problem: PR Review is a Bottleneck

In traditional software development, code reviews serve as the primary quality gate. However, this model has fundamental inefficiencies:

1. **Recurring feedback themes**: The same feedback appears across multiple PRs
   - "Add type hints"
   - "Missing docstring"
   - "Use `const` instead of `let`"
   - "This could be a list comprehension"

2. **Cognitive waste**: Reviewers spend mental energy on mechanical checks that could be automated

3. **Inconsistent enforcement**: What one reviewer catches, another misses

4. **Delayed feedback loop**: Issues discovered in PR review could have been caught at commit time

5. **Knowledge silos**: Style expectations live in reviewers' heads, not in tooling

### The Post-LLM Reality

LLMs fundamentally change how code is written and reviewed:

- **Velocity increase**: LLMs generate code faster than humans can review
- **Pattern replication**: LLMs learn from existing code, amplifying both good and bad patterns
- **Consistency opportunity**: LLMs can enforce standards programmatically
- **Review bottleneck**: Human review becomes the limiting factor, not code generation

When an LLM agent like jib can generate a PR in minutes, human review time becomes precious. We cannot afford to waste that time on issues that should never have reached review.

### The Insight: Automate Recurring Feedback

> **If you as a reviewer see a pattern of feedback on a specific topic, it's your responsibility to add a linter to solve the problem systematically.**
>
> **If you're not able to do that, you should assess the value-add of the feedback.**

Every piece of recurring feedback represents a process failure. Either:
1. The feedback should be automated (linter, LLM check, custom script)
2. The feedback isn't worth giving (it's not actually improving code quality)

There is no third option where "a human should keep manually checking this forever."

## Decision

**We will adopt an "LLM Reviews First" model where automated review is the primary review mechanism and human review is the final approval checkpoint.**

### The Core Principle

This inverts the traditional model:

| Traditional | LLM-First |
|-------------|-----------|
| PR created → Human reviews → Developer fixes → Merge | PR created → LLM reviews → LLM fixes → Human approves → Merge |

And critically, when humans *do* provide feedback:

```
Human provides feedback → PR Review Reviewer detects pattern →
New check auto-generated → Human approves check → Future PRs automatically pass
```

**Human reviewers should rarely request changes.** When they do, it triggers process improvement—not just a fix to the current PR.

**The Human Reviewer's New Role:**

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

**The key insight:** Human review time is expensive and limited. Spending it on issues an LLM could catch is waste. Every piece of human feedback should either be high-level (architecture, strategy, business logic) or should trigger an improvement to the automated review process.

### The Automation Responsibility

> **If you as a reviewer see a pattern of feedback on a specific topic, it's your responsibility to add it to the LLM review prompt or create an automated check.**
>
> **If you can't create the automated check yourself, escalate it. But if you're repeatedly giving the same feedback without automating it, you're wasting everyone's time—including your own.**

This is a forcing function. Reviewers who repeatedly provide low-level feedback instead of automating it will be identified through metrics (review comments per PR, percentage of comments that become automated checks). This data makes the conversation objective:

- High-level feedback with low automation triggers → Valuable reviewer
- Low-level feedback without automation → Needs coaching on LLM-assisted workflows
- Persistent low-level feedback after coaching → Operating as a bottleneck

### The Review Stack

| Layer | Handled By | Examples |
|-------|------------|----------|
| **Syntax & Style** | Linters (ruff, ESLint, prettier) | Formatting, import order, naming conventions |
| **Type Safety** | Type checkers (mypy, TypeScript) | Missing types, type mismatches |
| **Security Basics** | SAST tools (detect-secrets, semgrep) | Hardcoded secrets, common vulnerabilities |
| **Pattern Compliance** | LLM reviewer (first pass) | Over-engineering, scope creep, naming clarity, code duplication, missing tests |
| **Implementation Quality** | LLM reviewer (first pass) | Error handling, edge cases, performance concerns |
| **Business Logic** | Human reviewer (final pass) | Requirements fit, domain correctness |
| **Architecture** | Human reviewer (final pass) | Design decisions, system impact, scalability |
| **Strategy** | Human reviewer (final pass) | Direction, priorities, novel concerns |

**The goal: humans focus exclusively on the bottom three layers.** If a human is regularly requesting changes on PRs, that's a signal to tune the LLM review process—either by improving prompts, adding custom checks, or adjusting the review criteria.

### The Workflow

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

### Decision Matrix

| Feedback Type | Automation Approach | Enforcement Point |
|--------------|---------------------|-------------------|
| **Style issues** (formatting, naming) | Linter rules (ESLint, Ruff, Black) | Pre-commit hook |
| **Missing elements** (types, docs) | Custom lint rules, AST checks | Pre-commit hook |
| **Pattern violations** (anti-patterns) | Custom scripts, semgrep rules | CI pipeline |
| **Consistency issues** (imports, structure) | Import sorters, structure enforcers | Pre-commit hook |
| **Security issues** (secrets, vulnerabilities) | Secret scanners, SAST tools | CI + pre-push |
| **Test requirements** (coverage, presence) | Coverage tools, test existence checks | CI pipeline |

## Implementation

### Tier 1: Pre-Commit Hooks (Instant Feedback)

Fast checks (<5 seconds) that run on every commit. These must be fast to maintain developer flow.

**Python:**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.2
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        args: [--ignore-missing-imports]
```

**Shell:**
```yaml
  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.10.0.1
    hooks:
      - id: shellcheck
```

**General:**
```yaml
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
      - id: detect-private-key
```

See `.pre-commit-config.yaml` for full configuration.

### Tier 2: CI Pipeline (Comprehensive)

Pre-commit hooks optimize for speed. CI serves a different purpose: comprehensive checks that are too slow or resource-intensive for every commit.

**When CI adds value over pre-commit:**

| Check Type | Why CI, Not Pre-Commit |
|------------|------------------------|
| **Full test suite** | Too slow for commits; run on PRs |
| **Security scanning** | Requires external APIs, network access |
| **Cross-file analysis** | Needs full codebase context |
| **Integration tests** | Requires services, databases |
| **Coverage thresholds** | Needs complete test run to calculate |

Pre-commit catches formatting and obvious errors instantly. CI catches systemic issues before merge.

### Tier 3: LLM Review (Semantic Understanding)

**This is the defining feature of post-LLM code review.** Instead of LLMs being an "assistant" to human review, LLMs become the primary reviewer with humans as the escalation path.

LLM reviewers catch issues that require semantic understanding—things traditional linters cannot express:

- "This is over-engineered for the current requirements"
- "This PR includes changes unrelated to its stated purpose"
- "These variable names don't clearly communicate intent"
- "This abstraction is premature"
- "Missing test coverage for this edge case"
- "This duplicates logic from X module"

**LLMs can catch all of these.** And critically, another LLM agent can usually *fix* them automatically.

#### The Two-Agent Pattern

The most efficient implementation uses two LLM agents:

1. **Reviewer Agent**: Analyzes the PR, identifies issues, posts review comments
2. **Fixer Agent**: Reads the review comments, applies the suggested changes, pushes fixes

This creates a feedback loop where most issues are resolved without human involvement:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         LLM Reviews First                                │
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐             │
│  │  PR Created  │────▶│ LLM Reviews  │────▶│ LLM Applies  │             │
│  │              │     │              │     │   Feedback   │             │
│  │  By human    │     │ Identifies   │     │              │             │
│  │  or agent    │     │ all issues   │     │ Pushes fixes │             │
│  └──────────────┘     └──────────────┘     └──────────────┘             │
│                                                     │                    │
│                                                     ▼                    │
│                              ┌──────────────────────────────────┐       │
│                              │       Human Reviews (Final)       │       │
│                              │                                   │       │
│                              │  - High-level approval only       │       │
│                              │  - Architecture & strategy        │       │
│                              │  - Rarely requests changes        │       │
│                              └──────────────────────────────────┘       │
│                                                                          │
│  Key insight: Most LLM feedback should be auto-applied by another       │
│  LLM agent, not manually fixed by the author.                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Human feedback triggers improvement:** When a human *does* request changes, that's a signal that the automated review process missed something. The team should:

1. Understand why the LLM reviewer didn't catch this
2. Add it to the review prompt or create a custom check
3. Tune the process so it catches this class of issue next time

#### Acknowledging LLM Limitations

LLMs are not perfect reviewers. They can:

- Miss subtle bugs that require deep domain knowledge
- Overlook security implications that depend on deployment context
- Suggest changes that technically work but don't fit the architecture
- Generate false positives, especially on unfamiliar codebases

**The goal is not perfection—it's efficiency.** If LLM review catches 80% of issues automatically, that's an 80% reduction in human review effort. The remaining 20% is where human expertise adds the most value.

### Tier 4: The PR Review Reviewer (Self-Improvement)

**This is the key innovation.** The ultimate goal is self-improving review infrastructure. When humans provide feedback that slips past automated review, we don't just fix it once—we automatically generate new checks to prevent recurrence.

The **PR Review Reviewer** agent monitors human review feedback across all PRs and:

1. **Detects patterns**: Identifies recurring feedback themes (same comment appearing 3+ times)
2. **Generates checks**: Automatically creates new linter rules, custom scripts, or LLM review prompts
3. **Proposes PRs**: Submits the new checks for human approval
4. **Tracks effectiveness**: Monitors whether the new checks reduce human feedback

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    The Self-Improving Review Loop                            │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │    Human provides      PR Review Reviewer     New check auto-         │   │
│  │    feedback on PR  ──▶ detects pattern   ──▶  generated and     ◀──┐ │   │
│  │                        (3+ occurrences)       proposed as PR       │ │   │
│  │                                                                     │ │   │
│  └─────────────────────────────────────────────────────────────────────┘ │   │
│                                         │                                │   │
│                                         ▼                                │   │
│                            ┌──────────────────────┐                      │   │
│                            │  Human approves      │                      │   │
│                            │  or rejects check    │──────────────────────┘   │
│                            └──────────────────────┘                          │
│                                         │                                    │
│                                         ▼                                    │
│                            ┌──────────────────────┐                          │
│                            │  Check catches       │                          │
│                            │  future issues       │                          │
│                            │  automatically       │                          │
│                            └──────────────────────┘                          │
│                                                                              │
│  Result: Human feedback becomes rarer over time as the system learns         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Pattern Detection Strategy:**

| Feedback Pattern | Generated Check Type | Example |
|-----------------|---------------------|---------|
| "Add type hints" | Ruff rule enablement | Enable ANN rules, create PR |
| "Use pathlib instead of os.path" | Custom linter rule | Add PTH rules to ruff config |
| "Missing error handling for X" | LLM review prompt update | Add to REVIEW_PROMPT |
| "This duplicates code in Y" | Custom cross-file check | Generate semgrep pattern |
| "Follow the pattern in Z" | LLM review prompt example | Add example to prompt |

**Key Principle:**

> **Every human review comment is a potential automation opportunity. The PR Review Reviewer makes this opportunity visible and actionable—automatically.**

This transforms human reviewers from gatekeepers into *trainers* of the automated system. Their feedback improves not just the current PR, but all future PRs.

## Success Metrics

### System-Level Metrics

| Metric | Target Direction | Why It Matters |
|--------|------------------|----------------|
| % of PRs passing human review with no changes | ↑ Increase | Shows automation effectiveness |
| Average human review comments per PR | ↓ Decrease | Less manual work needed |
| Time from PR creation to human review start | ↑ Increase | LLM handles more first |
| % of LLM suggestions auto-applied | ↑ Increase | Less manual fixing |
| Number of auto-generated checks proposed | ↑ Increase | System is learning |
| Reduction in recurring feedback patterns | ↓ Decrease | Patterns being automated |

### Reviewer-Level Metrics (Accountability)

| Metric | What It Indicates |
|--------|-------------------|
| **Comments per PR by reviewer** | High numbers = operating at wrong level |
| **% of comments that trigger new automated checks** | Low % after coaching = problem |
| **Comment abstraction level** | Architecture/strategy vs style/syntax (auto-classified by LLM) |
| **Time spent on low-level feedback** | Tracked automatically, creates visibility |

These metrics are not punitive—they're diagnostic. A reviewer with high comments-per-PR isn't "bad," they may just need coaching on LLM workflows. But persistent patterns after coaching indicate someone who is choosing not to adapt, which is unacceptable when it impacts team velocity.

## Consequences

### Benefits

1. **Reviewer time freed**: No more mechanical feedback, only substantive review
2. **Faster feedback loops**: Issues caught at commit time, not PR time
3. **Consistent enforcement**: Same rules for everyone, automated
4. **Self-improving system**: Human feedback automatically becomes automated checks
5. **Documented standards**: Rules are explicit, not in reviewers' heads
6. **LLM alignment**: jib automatically learns and follows standards
7. **Reduced frustration**: Authors know expectations upfront
8. **Knowledge transfer**: Standards survive team changes

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Checks too strict | Start with warnings, escalate to errors after team alignment |
| Checks too slow | Pre-commit for fast checks, CI for comprehensive checks |
| False positives | Provide escape hatches (# noqa, eslint-disable) with justification requirement |
| LLM misses issues | Human review remains the final checkpoint |
| Maintenance neglect | Monthly review of check effectiveness, prune unused rules |

## Alternatives Considered

### Alternative 1: LLM as Assistant (Traditional)

**Approach:** Use LLMs to help human reviewers (suggestions, summaries) but keep humans as primary reviewers.

**Rejected because:** This doesn't fundamentally change the bottleneck. Human review is still the primary gate, and LLMs are just adding features to the existing model. "LLM Reviews First" inverts this—LLMs are the primary reviewer, humans are the escalation path.

### Alternative 2: AI-Only Review

**Approach:** Replace human review entirely with LLM analysis.

**Rejected because:** LLMs can miss subtle bugs requiring deep domain knowledge, overlook security implications in deployment context, and suggest changes that don't fit the architecture. Human oversight remains valuable for high-level concerns. However, this alternative is *closer* to the target than traditional review—we want to maximize LLM review coverage while keeping humans as the final checkpoint.

### Alternative 3: More Detailed Style Guides

**Approach:** Write comprehensive style guides that reviewers reference.

**Rejected because:** Style guides without enforcement are documentation theater. They add cognitive load without reducing review friction.

### Alternative 4: Reviewer Training

**Approach:** Train reviewers to be more consistent.

**Rejected because:** Human consistency is fundamentally limited. Automation is more reliable and scalable.

### Alternative 5: Post-Hoc Analysis Only

**Approach:** Analyze merged code for patterns, fix later.

**Rejected because:** Delayed feedback is less effective. Issues should be caught before merge.

## Implementation Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Foundation | Done | Pre-commit config, CI workflow |
| Phase 2: Feedback Collection | In Progress | `docs/standards/feedback-patterns.md` tracking |
| Phase 3: Custom Enforcers | In Progress | `scripts/check-standards/` |
| Phase 4: PR Review Reviewer | Planned | `scripts/pr-review-reviewer/` |
| Phase 5: jib Integration | Planned | `.claude/rules/code-standards.md` |

## Related Documents

- [LLM-Assisted Code Review Guide](../../reference/llm-assisted-code-review.md) — Practical implementation guide
- [Feedback Patterns](../../standards/feedback-patterns.md) — Tracking recurring feedback
- [ADR-LLM-Inefficiency-Reporting](../implemented/ADR-LLM-Inefficiency-Reporting.md) — Identifying patterns in agent behavior
- [ADR-Autonomous-Software-Engineer](./ADR-Autonomous-Software-Engineer.md) — jib architecture and quality standards

### External Resources

- [Pre-commit Framework](https://pre-commit.com/)
- [Ruff - Python Linter](https://docs.astral.sh/ruff/)
- [ESLint](https://eslint.org/)
- [Semgrep - Code Analysis](https://semgrep.dev/)

---

**Last Updated:** 2025-12-02
**Next Review:** 2025-01-02 (Monthly)
**Status:** In Progress
