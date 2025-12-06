# A Pragmatic Guide for Software Engineering in a Post-LLM World

**Status:** Draft
**Author:** James Wiesebron, james-in-a-box
**Created:** December 2025
**Purpose:** Strategic umbrella document connecting the three pillars of LLM-augmented software engineering

---

## Executive Summary

The idea that speed is an inherent benefit of software development with LLMs is a fallacy.

With the models that exist currently, we don't have a path forward for automating the job of software engineers generally. We do, however, have a path towards radically improving the software development lifecycle, leading to higher quality code while reducing cognitive load on engineers.

But we can only navigate this path with **intentionality**, **rigor**, and **care**.

This document presents a philosophy for software engineering in the post-LLM era, built on three mutually reinforcing pillars—each aligned with one of these guiding values:

| Value | Pillar | Core Question | Document |
|-------|--------|---------------|----------|
| **Intentionality** | LLM-First Code Reviews | Where should human attention focus? | [LLM-First Code Reviews](../reference/llm-assisted-code-review.md) |
| **Rigor** | Human-Driven, LLM-Navigated Development | How do we maintain structural discipline? | [Human-Driven, LLM-Navigated Software Development](Human-Driven-LLM-Navigated-Software-Development.md) |
| **Care** | Radical Self-Improvement | How do systems get better over time? | [Radical Self-Improvement for LLMs](Radical-Self-Improvement-for-LLMs.md) |

**The core thesis:** The promise of LLMs in software engineering is not speed—it's quality. By approaching this new paradigm with intentionality about where humans focus, rigor in how humans and LLMs collaborate, and care for continuous improvement, we can build better software while making engineering more sustainable.

---

## Table of Contents

- [The Speed Fallacy](#the-speed-fallacy)
- [Intentionality, Rigor, and Care](#intentionality-rigor-and-care)
- [The Three Pillars](#the-three-pillars)
- [How They Work Together](#how-they-work-together)
- [Adopting the Philosophy](#adopting-the-philosophy)
- [Key Principles](#key-principles)
- [What This Is Not](#what-this-is-not)
- [Getting Started](#getting-started)
- [References](#references)

---

## The Speed Fallacy

There is a seductive narrative in the industry: LLMs will make software development faster. Ship more features. Move faster. 10x productivity.

This framing is wrong—and dangerous.

**Why it's wrong:** Speed without quality creates technical debt. Speed without intentionality creates chaos. Speed without care creates systems that degrade over time. The organizations chasing "faster" with LLMs will find themselves moving faster toward failure.

**Why it's dangerous:** When speed becomes the goal, engineers become rubber-stampers. Review becomes a formality. Quality becomes someone else's problem. The very practices that make software engineering sustainable get sacrificed on the altar of velocity.

**What we actually have:** With current models, we cannot automate software engineering. We cannot replace the judgment, creativity, and accountability that humans bring. What we *can* do is fundamentally reshape *how* humans and LLMs work together—in ways that produce higher quality outcomes while reducing the cognitive burden on engineers.

But this requires a different mindset entirely.

---

## Intentionality, Rigor, and Care

The path forward requires three qualities that stand in direct opposition to the "move fast" mentality:

### Intentionality

> Where should human attention focus?

LLMs can process vast amounts of code, but they cannot decide what matters. **Intentionality** means deliberately choosing where human cognitive capacity should be invested—and systematically offloading everything else.

This isn't about humans doing less. It's about humans doing *what only humans can do*: making strategic decisions, providing accountability, exercising judgment that carries weight.

### Rigor

> How do we maintain structural discipline?

LLMs enable a new kind of collaboration, but without clear structure, that collaboration becomes chaos. **Rigor** means establishing precise roles—humans as drivers of strategy, LLMs as navigators handling structural discipline—and maintaining that division consistently.

This isn't about bureaucracy. It's about the kind of systematic discipline that produces reliable outcomes at scale.

### Care

> How do systems get better over time?

Static systems cannot keep pace with evolving needs. **Care** means building systems that actively improve themselves—detecting inefficiencies, learning from feedback, and proposing their own enhancements.

This isn't about automation for its own sake. It's about treating the development process itself as something worth investing in, nurturing, and continuously refining.

---

## Why This Matters Now

Engineers are already overwhelmed. Adding "work with LLMs" to their responsibilities without changing how work happens leads to:

- Rubber-stamping (approving without genuine review)
- Cognitive overload (trying to manage LLM output without clear frameworks)
- Inconsistency (different team members collaborating with LLMs differently)
- Stagnation (no mechanism for the system to improve)

The answer is not "go faster." The answer is to approach this paradigm shift with the intentionality, rigor, and care it deserves—and in doing so, create practices that **reduce** human cognitive load while **increasing** code quality.

---

## The Three Pillars

Each pillar embodies one of the guiding values—intentionality, rigor, and care—and together they form a complete philosophy for LLM-augmented software engineering.

### Pillar 1: LLM-First Code Reviews (Intentionality)

**Value:** Intentionality — Where should human attention focus?

**Core Practice:** Invert the review model—LLMs review first, humans approve last.

**Key Insight:**
> Every piece of recurring human feedback represents a process failure. It should either be automated or questioned.

Intentionality in code review means being deliberate about what deserves human cognitive investment. LLMs can assess architecture, security, and business logic—but humans must own the go/no-go decisions that carry accountability.

**The Intentional Division:**
- **Automate ruthlessly:** Formatting, types, patterns, common bugs
- **LLM analysis:** Architecture assessment, security scanning, business logic coherence
- **Human focus:** Accountability, organizational context, strategic trade-offs, team dynamics

**Why Intentionality:** Without intentionality, human reviewers drown in mechanical concerns while strategic issues slip through. With intentionality, every piece of human attention is invested where it creates irreplaceable value.

**Connection to Other Pillars:** Intentional focus requires the structural rigor of Pillar 2 to define clear boundaries. Review signals feed the caring systems of Pillar 3 for continuous improvement.

**Read more:** [LLM-First Code Reviews](../reference/llm-assisted-code-review.md)

---

### Pillar 2: Human-Driven, LLM-Navigated Development (Rigor)

**Value:** Rigor — How do we maintain structural discipline?

**Core Practice:** Humans drive strategy (the "driver"), LLMs handle structural rigor (the "navigator").

**Key Insight:**
> Humans and LLMs have complementary cognitive strengths. Optimal software development emerges when each focuses on what they do best—and that division is maintained with discipline.

Rigor in human-LLM collaboration means establishing precise roles and maintaining them consistently. The driver/navigator metaphor isn't just a suggestion—it's a discipline that prevents the chaos of undefined collaboration.

**The Rigorous Division:**

| Human (Driver) | LLM (Navigator) |
|----------------|-----------------|
| Define vision and goals | Enumerate edge cases and considerations |
| Make strategic decisions | Ensure pattern consistency |
| Review and approve changes | Generate comprehensive tests |
| Handle novel situations | Keep documentation current |
| Collaborate with stakeholders | Track dependencies and implications |

**Why Rigor:** Without rigor, collaboration with LLMs becomes ad-hoc and inconsistent. Different team members interact differently; quality varies unpredictably. With rigor, the collaboration model produces reliable, repeatable outcomes.

**The Interactive Planning Framework:** For complex changes, the [Interactive Planning Framework](../adr/in-progress/ADR-Interactive-Planning-Framework.md) enforces rigor through structured phases—elicitation, design, planning, handoff—each with human checkpoints.

**Connection to Other Pillars:** Rigor defines how humans exercise intentionality (Pillar 1) and validates improvements (Pillar 3). It's the structural foundation that makes the other pillars practical.

**Read more:** [Human-Driven, LLM-Navigated Software Development](Human-Driven-LLM-Navigated-Software-Development.md)

---

### Pillar 3: Radical Self-Improvement for LLMs (Care)

**Value:** Care — How do systems get better over time?

**Core Practice:** Build systems that proactively detect inefficiencies and propose improvements.

**Key Insight:**
> An LLM agent system should get measurably better at its job every week, automatically. Human oversight shifts from directing improvements to validating them.

Care in software systems means treating the development process itself as something worth nurturing. Rather than accepting static tooling, we invest in systems that actively reflect on their own behavior and propose their own improvements.

**The Caring System:**
1. **Automated Maintenance** — Repository hygiene, documentation sync, dependency health
2. **Continuous Self-Reflection** — Pattern detection, inefficiency analysis, root cause identification
3. **PR Review Reviewer** — Meta-review that turns human feedback into automated checks
4. **Strategic Human Escalation** — Surfacing systemic issues for human decision

**Why Care:** Without care, systems stagnate. The same mistakes repeat. Technical debt accumulates. With care, every interaction becomes an opportunity for the system—and the team—to improve.

**The Shift:**
- **Old model:** Humans tell the system what to improve
- **New model:** System proposes improvements, humans validate

**Connection to Other Pillars:** Care learns from the intentional review patterns of Pillar 1 and operates within the rigorous collaboration model of Pillar 2.

**Read more:** [Radical Self-Improvement for LLMs](Radical-Self-Improvement-for-LLMs.md)

---

## How They Work Together

The three pillars—and their values of intentionality, rigor, and care—are not independent options or sequential phases. They are mutually reinforcing aspects of a single philosophy:

```
                    ┌──────────────────────────────────┐
                    │    INTENTIONALITY, RIGOR, CARE   │
                    │   "Each pillar supports the      │
                    │    weight of the whole idea"     │
                    └──────────────────────────────────┘
                                   │
         ┌─────────────────────────┼───────────────────────┐
         │                         │                       │
         ▼                         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌────────────────────┐
│   PILLAR 1      │◀───▶│   PILLAR 2      │◀───▶│   PILLAR 3         │
│ (Intentionality)│     │    (Rigor)      │     │     (Care)         │
│                 │     │                 │     │                    │
│  LLM-First      │     │  Human-Driven   │     │  Radical           │
│  Code Reviews   │     │  LLM-Navigated  │     │  Self-Improvement  │
└────────┬────────┘     └────────┬────────┘     └──────────┬─────────┘
         │                       │                         │
         └───────────────────────┼─────────────────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────────────┐
                    │       MUTUAL REINFORCEMENT       │
                    │  Intentionality without rigor    │
                    │  becomes chaos. Rigor without    │
                    │  care becomes stagnation. Care   │
                    │  without intentionality wastes   │
                    │  effort on the wrong things.     │
                    └──────────────────────────────────┘
```

**How they reinforce each other:**

- **Rigor + Care → Quality → Intentional Focus:** This is the foundational causal chain. When humans maintain rigorous collaboration (Pillar 2) and systems continuously improve with care (Pillar 3), the resulting code is higher quality from the start. Higher quality code means fewer issues to catch in review, allowing intentional focus (Pillar 1) on what truly matters.

- **Intentionality informs Care:** When humans focus intentionally on strategic concerns, their review feedback becomes higher signal—exactly what self-improving systems need to learn from.

- **Care enhances Intentionality:** As systems improve themselves, they handle more mechanical concerns automatically, freeing even more human attention for intentional focus.

- **Rigor governs both:** The human-as-driver, LLM-as-navigator discipline applies whether you're reviewing code, approving improvements, or designing the system.

- **Each value requires the others:** Intentionality without rigor becomes scattered. Rigor without care becomes brittle. Care without intentionality wastes effort on the wrong improvements.

---

## Adopting the Philosophy

You don't adopt these pillars sequentially—you adopt them together as aspects of a unified approach. However, your emphasis may vary based on context.

### For Teams New to LLM Collaboration

**Start with rigor:** Establish the driver/navigator model (Pillar 2) before anything else. Without this structural discipline, the other pillars have no foundation.

**Then add intentionality:** Once roles are clear, establish review practices (Pillar 1) that deliberately focus human attention on strategic concerns.

**Build toward care:** As the system matures, introduce self-improvement capabilities (Pillar 3) that learn from your team's patterns.

### For Teams Already Using LLM Tools

**Assess intentionality:** Are humans focused on what only humans can do? Or are they drowning in mechanical concerns? (Pillar 1)

**Assess rigor:** Is there a consistent collaboration model? Or does each team member interact with LLMs differently, producing inconsistent results? (Pillar 2)

**Assess care:** Are you learning from your experience? Or making the same mistakes repeatedly with no mechanism for improvement? (Pillar 3)

### Success Indicators

| Value | What to Measure |
|-------|-----------------|
| **Intentionality** | Human review time spent on strategic concerns vs. mechanical issues |
| **Rigor** | Task specification clarity, first-attempt success rate, consistency across team members |
| **Care** | Automated check growth, proposal acceptance rate, decreasing repetition of feedback |

---

## Key Principles

These principles span all three pillars:

### 1. Humans Remain in Control

LLMs are powerful collaborators, not autonomous decision-makers. Humans:
- Set strategic direction
- Make judgment calls on trade-offs
- Approve all changes before deployment
- Can override any automated decision

### 2. Leverage Complementary Strengths

Don't use LLMs for what humans do better (judgment, creativity, relationships). Don't burden humans with what LLMs do better (exhaustive checking, pattern consistency, documentation sync).

### 3. Reduce Burden, Not Add It

Every automated system should make humans' lives easier:
- Less cognitive load, not more
- Faster feedback, not more noise
- Clearer decisions, not more complexity

### 4. Continuous Improvement Is Built In

Static systems cannot keep pace. The system should get better over time:
- Recurring issues become automated checks
- Human feedback improves LLM behavior
- LLM feedback improves human behavior
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

### Understand the Philosophy

1. **Read Pillar 2 first (Rigor)** — The driver/navigator model provides the structural foundation for everything else
2. **Then Pillar 1 (Intentionality)** — See how to focus human attention where it creates irreplaceable value
3. **Then Pillar 3 (Care)** — Understand how to build systems that continuously improve

### For Individual Contributors

1. **Embrace rigor** — Internalize the driver/navigator model; you drive strategic decisions, LLMs navigate details
2. **Practice intentionality** — If automated checks pass, focus on strategic concerns, not mechanical ones
3. **Give feedback with care** — Your review feedback shapes how the system improves; make it high-signal
4. **Resist the speed trap** — Quality and sustainability matter more than velocity

### For Tech Leads

1. **Model rigor** — Demonstrate the driver/navigator dynamic consistently with your team
2. **Establish intentional practices** — Define clearly where human attention should focus
3. **Champion care** — When you see recurring patterns, help turn them into automated improvements
4. **Measure what matters** — Intentionality, rigor, and care—not just speed

### For Engineering Leadership

1. **Reject the speed fallacy** — Commit to quality and sustainability, not velocity
2. **Invest in all three values** — Intentionality, rigor, and care each need support and resources
3. **Validate the model** — Ensure human oversight remains meaningful as automation grows
4. **Lead the mindset shift** — This is a new paradigm that requires cultural change, not just tooling

---

## References

### This Document Series

| Value | Document | Focus |
|-------|----------|-------|
| Intentionality | [LLM-First Code Reviews](../reference/llm-assisted-code-review.md) | Practical guide to LLM-assisted review |
| Rigor | [Human-Driven, LLM-Navigated Development](Human-Driven-LLM-Navigated-Software-Development.md) | Collaboration philosophy |
| Care | [Radical Self-Improvement for LLMs](Radical-Self-Improvement-for-LLMs.md) | Autonomous improvement framework |
| — | [ADR: Coding Standards in a Post-LLM World](../adr/not-implemented/ADR-Coding-Standards-Post-LLM-World.md) | Technical implementation details |

### External Resources

- [AWS AI-Driven Development Life Cycle](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/)
- [Atlassian HULA Framework](https://www.atlassian.com/blog/atlassian-engineering/hula-blog-autodev-paper-human-in-the-loop-software-development-agents)
- [Anthropic Claude Best Practices](https://docs.anthropic.com/claude/docs/claude-for-work)

---

**Last Updated:** 2025-12-05
**Next Review:** 2026-01-05 (Monthly)
