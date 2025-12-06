# ADR: Collaborative Planning Framework for Autonomous Development

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
- [Decision Matrix](#decision-matrix)
- [The Collaborative Planning Framework](#the-collaborative-planning-framework)
- [Multi-Agent Architecture](#multi-agent-architecture)
- [Planning Workflow Phases](#planning-workflow-phases)
- [Human-in-the-Loop Checkpoints](#human-in-the-loop-checkpoints)
- [Output Artifacts](#output-artifacts)
- [Implementation Architecture](#implementation-architecture)
- [Implementation Phases](#implementation-phases)
- [Consequences](#consequences)
- [Evaluation and Success Metrics](#evaluation-and-success-metrics)
- [Security Considerations](#security-considerations)
- [Cost Analysis](#cost-analysis)
- [Checkpoint Flexibility](#checkpoint-flexibility)
- [Example Walkthrough](#example-walkthrough)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

Currently, jib operates reactively—users must provide detailed specifications for jib to execute tasks effectively. While jib excels at implementation given clear requirements, it lacks a structured framework to:

1. **Elicit Requirements:** Transform vague user intent ("let's rewrite jib from scratch") into comprehensive specifications
2. **Drive Planning:** Guide humans through iterative refinement of ideas into actionable plans
3. **Ensure Completeness:** Guarantee all necessary design decisions are made before implementation
4. **Enable Autonomy:** Produce documentation thorough enough for autonomous implementation with minimal intervention

**The Gap:**

| Current State | Desired State |
|---------------|---------------|
| User provides detailed spec → jib implements | User provides vague intent → jib drives planning → jib implements autonomously |
| Single-pass implementation | Multi-phase plan/review/refine cycle |
| Human fills in gaps during implementation | Human approves checkpoints, jib fills gaps proactively |
| Implementation-focused | Planning-focused with implementation as output |

**Industry Context:**

Recent research and industry practice have converged on several key insights:

1. **AI-Driven Development Life Cycle (AI-DLC):** AWS introduced the concept where "AI creates a plan, asks clarifying questions to seek context, and implements solutions only after receiving human validation" ([AWS DevOps Blog](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/)).

2. **HULA Framework:** Atlassian's "Human-in-the-Loop LLM-based agents framework" demonstrates that keeping "the engineer in the driver's seat" while the AI drives planning leads to ~900 merged PRs with high quality ([Atlassian Engineering Blog](https://www.atlassian.com/blog/atlassian-engineering/hula-blog-autodev-paper-human-in-the-loop-software-development-agents)).

3. **Multi-Agent Systems:** Research shows that multi-agent architectures with specialized agents (planner, coder, reviewer) improve accuracy by up to 40% in complex tasks through cross-validation ([ACM TOSEM](https://dl.acm.org/doi/10.1145/3712003)).

4. **Tree of Thoughts:** Deliberate problem solving through exploration of multiple reasoning paths significantly outperforms linear chain-of-thought approaches for planning tasks ([NeurIPS 2023](https://arxiv.org/abs/2305.10601)).

### What We're Deciding

This ADR establishes a **comprehensive collaborative planning framework** that enables jib to:

1. **Transform vague prompts** into thorough design documents through iterative human-AI collaboration
2. **Drive a structured planning workflow** with explicit human checkpoints
3. **Produce implementation-ready artifacts** (design docs, phased plans, tasks with subtasks)
4. **Execute autonomous implementation** based on approved plans with minimal intervention

**Target Workflow:**

```
User: "Let's rewrite jib from scratch"
    ↓
[Interactive Planning Phase - Human approvals at checkpoints]
    ↓
Design Document + Phased Plan + Task Breakdown
    ↓
[Autonomous Implementation Phase - Minimal human intervention]
    ↓
Well-structured, documented codebase
```

### Key Requirements

**Functional:**

1. **Progressive Elicitation:** Extract requirements through structured questioning
2. **Multi-Agent Collaboration:** Specialized agents for different planning aspects
3. **Human Checkpoints:** Explicit approval gates at key decision points
4. **Artifact Generation:** Comprehensive design docs, plans, and tasks
5. **Implementation Handoff:** Clear transition from planning to execution
6. **Iteration Support:** Ability to revise any phase based on feedback

**Non-Functional:**

1. **User Experience:** Natural conversation flow, not interrogation
2. **Completeness:** No ambiguous decisions deferred to implementation
3. **Traceability:** Clear lineage from requirements to implementation
4. **Documentation Quality:** Machine and human digestible outputs
5. **Resilience:** Persist progress across sessions

## Decision

**We will implement a Collaborative Planning Framework (CPF) that uses a multi-agent architecture to guide users from vague intent through comprehensive planning to autonomous implementation.**

### Core Principles

1. **AI Drives, Human Steers:** jib proactively drives the planning process; humans provide direction and approval at checkpoints
2. **Progressive Disclosure:** Start broad, drill down iteratively—don't overwhelm with all questions upfront
3. **Multiple Perspectives:** Different specialized agents provide different viewpoints (architecture, testing, security, UX)
4. **Checkpoint-Based Approval:** Explicit human sign-off at phase transitions
5. **Comprehensive Documentation:** All decisions captured in implementation-ready artifacts
6. **Autonomous Execution:** Planning phase produces everything needed for minimal-intervention implementation

### Approach Summary

| Component | Purpose | Owner |
|-----------|---------|-------|
| **Elicitation Agent** | Extract requirements through structured conversation | AI |
| **Architecture Agent** | Design system structure and component relationships | AI |
| **Planning Agent** | Break down into phases, tasks, and subtasks | AI |
| **Review Agent** | Cross-validate decisions, identify gaps | AI |
| **Human Checkpoints** | Approve phase transitions, provide direction | Human |
| **Artifact Generator** | Produce design docs, plans, task lists | AI |

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Interaction Model** | Conversational with checkpoints | Natural flow, explicit approvals | Pure Q&A (robotic), pure free-form (unstructured) |
| **Agent Architecture** | Sequential pipeline with parallel specialists | Clear handoffs, specialized expertise | Single agent (cognitive overload), pure parallel (coordination complexity) |
| **Planning Depth** | Three levels (phases → tasks → subtasks) | Sufficient granularity without overwhelming | Single level (too coarse), four+ levels (over-engineered) |
| **Human Involvement** | Checkpoint approval + optional deep-dive | Balance autonomy and control | Full approval of everything (slow), zero approval (risky) |
| **Output Format** | Markdown design doc + YAML task file | Human and machine readable | Pure JSON (hard to read), pure prose (hard to parse) |
| **State Persistence** | Beads tasks with structured notes | Already integrated, survives restarts | Files only (no tracking), database (complexity) |

## The Collaborative Planning Framework

### Overview

The Collaborative Planning Framework (CPF) is a structured, multi-phase process that transforms vague user intent into comprehensive, implementation-ready documentation through guided human-AI collaboration.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Collaborative Planning Framework (CPF)                       │
│                                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   Phase 1   │    │   Phase 2   │    │   Phase 3   │    │   Phase 4   │  │
│  │ ELICITATION │───▶│   DESIGN    │───▶│  PLANNING   │───▶│  HANDOFF    │  │
│  │             │    │             │    │             │    │             │  │
│  │ What are we │    │ How will we │    │ What's the  │    │ Ready for   │  │
│  │  building?  │    │  build it?  │    │ breakdown?  │    │ execution   │  │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘  │
│         │                  │                  │                  │          │
│         ▼                  ▼                  ▼                  ▼          │
│    [CHECKPOINT]       [CHECKPOINT]       [CHECKPOINT]       [CHECKPOINT]    │
│     Human ✓            Human ✓            Human ✓            Human ✓        │
│                                                                               │
│  Outputs:              Outputs:            Outputs:           Outputs:       │
│  - Requirements Doc    - Design Doc       - Phased Plan      - Final Package │
│  - Scope Definition    - Architecture     - Task Breakdown   - Implementation│
│  - Success Criteria    - Tech Decisions   - Dependencies       Ready Docs    │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The Planning Conversation Flow

The framework uses a **Tree of Thoughts** approach, exploring multiple paths before converging on decisions:

```
User Input: "Let's rewrite jib from scratch"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    EXPLORATION TREE                               │
│                                                                   │
│                         [Intent]                                  │
│                       /    │    \                                │
│                      /     │     \                               │
│              [Goals]   [Scope]   [Constraints]                   │
│               /   \      │         /    \                        │
│              /     \     │        /      \                       │
│        [Perf]  [Maint] [What's  [Time]  [Resources]             │
│                       in/out]                                    │
│                                                                   │
│  Each branch explored through targeted questions                  │
│  Branches pruned or expanded based on human feedback              │
│  Final path represents converged requirements                     │
└─────────────────────────────────────────────────────────────────┘
```

## Multi-Agent Architecture

### Phased Agent Introduction

The framework uses a **phased approach** to agent introduction, validated against industry research. The HULA framework (Atlassian) achieved ~900 merged PRs with a simpler 4-stage process, while Anthropic's research system uses a 2-tier model (lead + subagents).

**MVP Architecture (4 Core Agents):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MVP AGENT ARCHITECTURE (Phase 1)                           │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        ORCHESTRATOR AGENT                                 ││
│  │                                                                           ││
│  │  Responsibilities:                                                        ││
│  │  - Manages overall planning workflow                                      ││
│  │  - Routes to appropriate specialist agents                                ││
│  │  - Synthesizes outputs into cohesive artifacts                           ││
│  │  - Manages human checkpoints                                              ││
│  │  - Tracks progress in Beads                                               ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                      │                                        │
│          ┌───────────────────────────┼───────────────────────────┐           │
│          │                           │                           │           │
│          ▼                           ▼                           ▼           │
│  ┌───────────────┐           ┌───────────────┐           ┌───────────────┐  │
│  │  ELICITATION  │           │  ARCHITECTURE │           │   PLANNING    │  │
│  │    AGENT      │           │     AGENT     │           │    AGENT      │  │
│  │               │           │               │           │               │  │
│  │ - Requirements│           │ - System design│          │ - Phase breakdown│
│  │ - Constraints │           │ - Components  │           │ - Task creation │
│  │ - Goals       │           │ - Interfaces  │           │ - Dependencies │
│  │ - Scope       │           │ - Tech choices│           │ - Ordering     │
│  └───────────────┘           └───────────────┘           └───────────────┘  │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Extended Architecture (Phase 2 - Add Review):**

After validating MVP, add the Review Agent for cross-validation and gap analysis.

**Full Architecture (Phase 3 - Add Specialists if Needed):**

Testing and Security agents are **optional specialists** added only if:
- Planning output consistently lacks test strategy detail
- Security considerations are frequently missed in designs
- Token cost of specialists is justified by quality improvement

### Agent Introduction Criteria

| Agent | Introduction Phase | Trigger Criteria |
|-------|-------------------|------------------|
| **Orchestrator** | MVP (Phase 1) | Required for coordination |
| **Elicitation** | MVP (Phase 1) | Core planning requirement |
| **Architecture** | MVP (Phase 1) | Core planning requirement |
| **Planning** | MVP (Phase 1) | Core planning requirement |
| **Review** | Extended (Phase 2) | After 10+ planning sessions, if gap analysis adds measurable value |
| **Testing** | Full (Phase 3) | If test strategy sections consistently need human revision |
| **Security** | Full (Phase 3) | If security considerations consistently missed |

### Agent Responsibilities

| Agent | Primary Role | Inputs | Outputs | MVP? |
|-------|--------------|--------|---------|------|
| **Orchestrator** | Workflow management | User input, agent outputs | Synthesized artifacts, checkpoints | Yes |
| **Elicitation** | Requirements gathering | Vague intent | Structured requirements | Yes |
| **Architecture** | System design | Requirements | Design document (including test strategy, security model) | Yes |
| **Planning** | Task breakdown | Design doc | Phased plan, tasks | Yes |
| **Review** | Cross-validation | All artifacts | Gap analysis, suggestions | No (Phase 2) |
| **Testing** | Quality strategy | Requirements, design | Test plan | No (Phase 3) |
| **Security** | Risk assessment | Design | Threat model, mitigations | No (Phase 3) |

**Note:** In the MVP, the Architecture Agent handles test strategy and security considerations as sections within the design document, rather than delegating to specialists.

### Agent Interaction Patterns

**MVP Pattern (Sequential):**

```
Phase 1: Elicitation
    [Orchestrator] → [Elicitation Agent] → [CHECKPOINT] → Human ✓

Phase 2: Design
    [Orchestrator] → [Architecture Agent] → [CHECKPOINT] → Human ✓
    (Architecture Agent includes test strategy and security sections)

Phase 3: Planning
    [Orchestrator] → [Planning Agent] → [CHECKPOINT] → Human ✓

Phase 4: Handoff
    [Orchestrator] → Generate Final Artifacts → [CHECKPOINT] → Human ✓
```

**Extended Pattern (With Review Agent):**

```
Phase 1: Elicitation
    [Orchestrator] → [Elicitation Agent] → [CHECKPOINT] → Human ✓

Phase 2: Design
    [Orchestrator] → [Architecture Agent] → [Review Agent] → [CHECKPOINT] → Human ✓

Phase 3: Planning
    [Orchestrator] → [Planning Agent] → [Review Agent] → [CHECKPOINT] → Human ✓

Phase 4: Handoff
    [Orchestrator] → [Review Agent (Final)] → [CHECKPOINT] → Human ✓
```

**Full Pattern (With Specialists - if justified):**

```
Phase 2: Design (Full)
    [Orchestrator] → [Architecture Agent] ─┬─→ [Testing Agent]
                                           └─→ [Security Agent]
                     ↓
                [Review Agent] → [CHECKPOINT] → Human ✓
```

## Planning Workflow Phases

### Phase 1: Requirements Elicitation

**Goal:** Transform vague intent into clear, validated requirements.

**Process:**

```
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 1: ELICITATION                            │
│                                                                   │
│  Step 1: Intent Clarification                                    │
│  ────────────────────────────                                    │
│  "I understand you want to rewrite jib. Let me understand        │
│   your goals better..."                                          │
│                                                                   │
│  Questions:                                                       │
│  - What's driving this decision? (pain points, limitations)      │
│  - What should the end state look like? (vision)                 │
│  - What's the scope? (complete rewrite vs. incremental)          │
│                                                                   │
│  Step 2: Goal Decomposition                                      │
│  ──────────────────────────                                      │
│  "Based on your goals, let me explore specific areas..."         │
│                                                                   │
│  Explore branches:                                                │
│  - Performance goals (speed, resource usage)                     │
│  - Maintainability goals (code quality, testing)                 │
│  - Feature goals (new capabilities, removed features)            │
│  - User experience goals (CLI, API, integrations)                │
│                                                                   │
│  Step 3: Constraint Identification                               │
│  ─────────────────────────────────                               │
│  "What constraints should I be aware of?"                        │
│                                                                   │
│  Explore:                                                         │
│  - Technical constraints (languages, frameworks, infra)          │
│  - Resource constraints (time, team size)                        │
│  - Compatibility constraints (backward compat, integrations)     │
│  - Organizational constraints (standards, processes)             │
│                                                                   │
│  Step 4: Success Criteria Definition                             │
│  ───────────────────────────────────                             │
│  "How will we know we've succeeded?"                             │
│                                                                   │
│  Define:                                                          │
│  - Measurable outcomes                                           │
│  - Quality thresholds                                            │
│  - Must-have vs. nice-to-have features                           │
│                                                                   │
│  ═══════════════════════════════════════════════════════════════ │
│  OUTPUT: Requirements Document                                    │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                   │
│  CHECKPOINT: Human reviews and approves requirements              │
└─────────────────────────────────────────────────────────────────┘
```

**Elicitation Techniques:**

| Technique | When to Use | Example |
|-----------|-------------|---------|
| **Open-ended questions** | Initial exploration | "What problems are you trying to solve?" |
| **Clarifying questions** | Ambiguous responses | "When you say 'faster', what's your target?" |
| **Scenario exploration** | Understanding use cases | "Walk me through how a user would..." |
| **Trade-off questions** | Prioritization | "If you had to choose between X and Y..." |
| **Validation questions** | Confirmation | "So the key requirement is..., correct?" |
| **Negative requirements** | Scoping | "What should this explicitly NOT do?" |

### Phase 2: Architecture Design

**Goal:** Create a comprehensive design document covering all technical decisions.

**Process:**

```
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 2: DESIGN                                 │
│                                                                   │
│  Step 1: High-Level Architecture                                 │
│  ───────────────────────────────                                 │
│  - System overview and boundaries                                │
│  - Major components and their responsibilities                   │
│  - Component interactions and data flows                         │
│  - External integrations                                         │
│                                                                   │
│  Step 2: Technical Decisions                                     │
│  ───────────────────────────                                     │
│  - Language and framework choices                                │
│  - Data storage approach                                         │
│  - API design and protocols                                      │
│  - Infrastructure and deployment                                 │
│                                                                   │
│  Step 3: Interface Specifications                                │
│  ────────────────────────────────                                │
│  - Public APIs (CLI, REST, SDK)                                  │
│  - Internal interfaces between components                        │
│  - Event/message contracts                                       │
│  - Configuration schema                                          │
│                                                                   │
│  Step 4: Parallel Specialist Reviews                             │
│  ────────────────────────────────────                            │
│                                                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐        │
│  │Testing Agent  │  │Security Agent │  │Review Agent   │        │
│  │               │  │               │  │               │        │
│  │Test strategy  │  │Threat model   │  │Gap analysis   │        │
│  │Coverage plan  │  │Security reqs  │  │Consistency    │        │
│  │Quality gates  │  │Mitigations    │  │Completeness   │        │
│  └───────────────┘  └───────────────┘  └───────────────┘        │
│                                                                   │
│  ═══════════════════════════════════════════════════════════════ │
│  OUTPUT: Design Document with all sections                        │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                   │
│  CHECKPOINT: Human reviews and approves design                    │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 3: Implementation Planning

**Goal:** Break down the design into actionable phases, tasks, and subtasks.

**Process:**

```
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 3: PLANNING                               │
│                                                                   │
│  Step 1: Phase Definition                                        │
│  ─────────────────────────                                       │
│  Identify logical implementation phases:                         │
│                                                                   │
│  Phase 1: Foundation                                             │
│  ├── Core infrastructure                                         │
│  ├── Basic CLI structure                                         │
│  └── Configuration system                                        │
│                                                                   │
│  Phase 2: Core Features                                          │
│  ├── Agent execution engine                                      │
│  ├── Tool integration                                            │
│  └── State management                                            │
│                                                                   │
│  Phase 3: Advanced Features                                      │
│  └── ...                                                         │
│                                                                   │
│  Step 2: Task Breakdown                                          │
│  ───────────────────────                                         │
│  For each phase, create detailed tasks:                          │
│                                                                   │
│  Task: Implement configuration system                            │
│  ├── Description: Create hierarchical config loading             │
│  ├── Acceptance Criteria:                                        │
│  │   - Loads from file, env, CLI                                 │
│  │   - Supports validation                                       │
│  │   - Handles defaults                                          │
│  ├── Dependencies: None                                          │
│  ├── Estimated Complexity: Moderate                              │
│  └── Subtasks:                                                   │
│      ├── Define config schema                                    │
│      ├── Implement file loader                                   │
│      ├── Implement env loader                                    │
│      ├── Implement CLI override                                  │
│      ├── Add validation                                          │
│      └── Write tests                                             │
│                                                                   │
│  Step 3: Dependency Analysis                                     │
│  ───────────────────────────                                     │
│  - Identify task dependencies                                    │
│  - Determine parallel vs. sequential execution                   │
│  - Flag blocking dependencies                                    │
│  - Identify critical path                                        │
│                                                                   │
│  Step 4: Documentation Requirements                              │
│  ──────────────────────────────────                              │
│  For each task, specify documentation needed:                    │
│  - Code documentation (docstrings, comments)                     │
│  - API documentation                                             │
│  - User documentation                                            │
│  - Architecture decision records                                 │
│                                                                   │
│  ═══════════════════════════════════════════════════════════════ │
│  OUTPUT: Phased Plan + Task Breakdown + Dependencies             │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                   │
│  CHECKPOINT: Human reviews and approves plan                      │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 4: Implementation Handoff

**Goal:** Package all artifacts for autonomous execution.

**Process:**

```
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 4: HANDOFF                                │
│                                                                   │
│  Step 1: Artifact Consolidation                                  │
│  ──────────────────────────────                                  │
│  Combine all outputs into implementation package:                │
│                                                                   │
│  📁 planning-output/                                             │
│  ├── 📄 requirements.md          # Phase 1 output               │
│  ├── 📄 design-document.md       # Phase 2 output               │
│  ├── 📄 test-strategy.md         # Testing agent output         │
│  ├── 📄 security-model.md        # Security agent output        │
│  ├── 📄 phased-plan.md           # Phase 3 output               │
│  ├── 📄 tasks.yaml               # Machine-readable tasks       │
│  └── 📄 implementation-guide.md  # Execution instructions       │
│                                                                   │
│  Step 2: Implementation Guide Generation                         │
│  ───────────────────────────────────────────                     │
│  Create comprehensive guide for autonomous execution:            │
│                                                                   │
│  - Phase execution order                                         │
│  - Task dependencies and blocking relationships                  │
│  - Quality gates between phases                                  │
│  - Human checkpoint requirements (if any remain)                 │
│  - Rollback procedures                                           │
│  - Success verification steps                                    │
│                                                                   │
│  Step 3: Execution Readiness Check                               │
│  ─────────────────────────────────                               │
│  Verify:                                                          │
│  - All decisions are made (no TODOs or TBDs)                     │
│  - All dependencies are identified                               │
│  - All acceptance criteria are testable                          │
│  - Documentation requirements are specified                      │
│  - Quality gates are defined                                     │
│                                                                   │
│  ═══════════════════════════════════════════════════════════════ │
│  OUTPUT: Complete implementation package                          │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                   │
│  FINAL CHECKPOINT: Human approves for implementation              │
└─────────────────────────────────────────────────────────────────┘
```

## Human-in-the-Loop Checkpoints

### Checkpoint Design

Each checkpoint follows a consistent structure:

```
┌─────────────────────────────────────────────────────────────────┐
│                    CHECKPOINT TEMPLATE                            │
│                                                                   │
│  Phase: [Phase Name]                                              │
│  Status: Awaiting Approval                                        │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ SUMMARY                                                       │ │
│  │                                                               │ │
│  │ [2-3 sentence summary of what was accomplished]               │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ KEY DECISIONS                                                 │ │
│  │                                                               │ │
│  │ 1. [Decision 1] - [Rationale]                                │ │
│  │ 2. [Decision 2] - [Rationale]                                │ │
│  │ 3. [Decision 3] - [Rationale]                                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ OPEN QUESTIONS (if any)                                       │ │
│  │                                                               │ │
│  │ - [Question needing human input]                              │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ARTIFACTS PRODUCED                                            │ │
│  │                                                               │ │
│  │ - [Artifact 1]: [Brief description]                           │ │
│  │ - [Artifact 2]: [Brief description]                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ APPROVAL OPTIONS                                              │ │
│  │                                                               │ │
│  │ [ ] APPROVE - Proceed to next phase                           │ │
│  │ [ ] APPROVE WITH COMMENTS - Proceed with noted adjustments    │ │
│  │ [ ] REVISE - Return to phase with feedback                    │ │
│  │ [ ] RESTART PHASE - Major changes needed                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Checkpoint Behaviors

| Checkpoint | Trigger | Required Approvals | Revision Options |
|------------|---------|-------------------|------------------|
| **Requirements** | Phase 1 complete | Requirements doc | Full re-elicitation or targeted refinement |
| **Design** | Phase 2 complete | Design doc, test strategy, security model | Revise specific sections or full redesign |
| **Plan** | Phase 3 complete | Phased plan, task breakdown | Adjust phases, refine tasks |
| **Handoff** | Phase 4 complete | Complete package | Any prior phase or proceed to implementation |

### Feedback Integration

When human provides feedback:

```
Human Feedback: "The security model seems light. Can we add more
                 detail on authentication flows?"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FEEDBACK INTEGRATION                              │
│                                                                   │
│  1. Parse Feedback                                                │
│     - Category: Security                                          │
│     - Specificity: Authentication flows                          │
│     - Requested Action: Add detail                               │
│                                                                   │
│  2. Route to Appropriate Agent                                   │
│     - Primary: Security Agent                                    │
│     - Secondary: Architecture Agent (for flow integration)       │
│                                                                   │
│  3. Generate Revision                                            │
│     - Security Agent expands authentication section              │
│     - Includes OAuth, JWT, session management details            │
│     - Adds sequence diagrams                                     │
│                                                                   │
│  4. Re-present at Checkpoint                                     │
│     - "I've expanded the security model with detailed            │
│        authentication flows. Please review..."                   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Output Artifacts

### Artifact 1: Requirements Document

```markdown
# Requirements Document: [Project Name]

## Executive Summary
[One-paragraph overview]

## Goals
### Primary Goals
- [Goal 1]
- [Goal 2]

### Secondary Goals
- [Goal 1]

## Requirements

### Functional Requirements
| ID | Requirement | Priority | Acceptance Criteria |
|----|-------------|----------|---------------------|
| FR-001 | [Requirement] | Must Have | [Testable criteria] |

### Non-Functional Requirements
| ID | Requirement | Target | Measurement |
|----|-------------|--------|-------------|
| NFR-001 | Performance | [Target] | [How measured] |

## Constraints
- [Constraint 1]
- [Constraint 2]

## Out of Scope
- [Explicitly excluded item 1]

## Success Criteria
- [Measurable outcome 1]

## Open Questions
- [Resolved or pending questions]

---
*Generated by CPF Phase 1 | Approved: [Date]*
```

### Artifact 2: Design Document

```markdown
# Design Document: [Project Name]

## Overview
[System overview and high-level architecture]

## Architecture

### System Context
[Context diagram - what the system interacts with]

### Container View
[Major components and their relationships]

### Component Details

#### [Component Name]
- **Purpose:** [What it does]
- **Responsibilities:**
  - [Responsibility 1]
- **Interfaces:**
  - [Interface 1]
- **Dependencies:**
  - [Dependency 1]

## Technical Decisions

### Decision 1: [Topic]
- **Context:** [Why this decision was needed]
- **Decision:** [What was decided]
- **Rationale:** [Why this option was chosen]
- **Alternatives Considered:** [Other options]

## Data Model
[Key entities and relationships]

## API Design
[Public interfaces specification]

## Security Model
[Authentication, authorization, data protection]

## Test Strategy
[Approach to testing, coverage targets]

## Deployment Architecture
[How the system will be deployed]

---
*Generated by CPF Phase 2 | Approved: [Date]*
```

### Artifact 3: Phased Implementation Plan

```markdown
# Implementation Plan: [Project Name]

## Overview
- **Total Phases:** [N]
- **Critical Path:** [Phase sequence]
- **Quality Gates:** [Between phases]

## Phase 1: [Phase Name]

### Objectives
- [Objective 1]

### Tasks

#### Task 1.1: [Task Name]
- **Description:** [What needs to be done]
- **Acceptance Criteria:**
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Dependencies:** [None | Task X.Y]
- **Complexity:** [Simple | Moderate | Complex]
- **Documentation:** [What docs to produce]

##### Subtasks
- [ ] 1.1.1: [Subtask]
- [ ] 1.1.2: [Subtask]

### Phase 1 Quality Gate
- [ ] All tasks complete
- [ ] Tests passing
- [ ] Documentation complete
- [ ] [Specific quality criteria]

## Phase 2: [Phase Name]
[...]

## Dependencies Graph
[Visual or textual representation of task dependencies]

## Risk Register
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| [Risk] | High/Med/Low | High/Med/Low | [Strategy] |

---
*Generated by CPF Phase 3 | Approved: [Date]*
```

### Artifact 4: Machine-Readable Tasks (YAML)

```yaml
# tasks.yaml - Machine-readable task specification
project: "[Project Name]"
generated: "2025-12-04"
approved: "2025-12-04"

phases:
  - id: phase-1
    name: "Foundation"
    description: "Core infrastructure and basic structure"
    quality_gate:
      - "All tests passing"
      - "Documentation complete"
    tasks:
      - id: task-1.1
        name: "Implement configuration system"
        description: "Create hierarchical config loading"
        complexity: moderate
        dependencies: []
        acceptance_criteria:
          - "Loads from file, env, CLI"
          - "Supports validation"
          - "Handles defaults"
        documentation:
          - "API reference"
          - "Configuration guide"
        subtasks:
          - id: task-1.1.1
            name: "Define config schema"
          - id: task-1.1.2
            name: "Implement file loader"
          - id: task-1.1.3
            name: "Implement env loader"
          - id: task-1.1.4
            name: "Implement CLI override"
          - id: task-1.1.5
            name: "Add validation"
          - id: task-1.1.6
            name: "Write tests"

      - id: task-1.2
        name: "[Next task]"
        dependencies: ["task-1.1"]
        # ...

  - id: phase-2
    name: "Core Features"
    dependencies: ["phase-1"]
    # ...
```

## Implementation Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CPF IMPLEMENTATION ARCHITECTURE                            │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         USER INTERFACE LAYER                              ││
│  │                                                                           ││
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                ││
│  │  │  Slack Interface │  │  CLI Interface  │  │  Future: Web  │               ││
│  │  │  (Existing)      │  │  (Existing)     │  │  Dashboard    │               ││
│  │  └───────────────┘  └───────────────┘  └───────────────┘                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                      │                                        │
│                                      ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         ORCHESTRATION LAYER                               ││
│  │                                                                           ││
│  │  ┌─────────────────────────────────────────────────────────────────────┐││
│  │  │                    CPF Orchestrator                                   │││
│  │  │                                                                       │││
│  │  │  - Workflow state machine                                            │││
│  │  │  - Phase transitions                                                 │││
│  │  │  - Checkpoint management                                             │││
│  │  │  - Agent dispatch                                                    │││
│  │  │  - Artifact aggregation                                              │││
│  │  └─────────────────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                      │                                        │
│                                      ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           AGENT LAYER                                     ││
│  │                                                                           ││
│  │  MVP Agents (Phase 1):                                                   ││
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                                    ││
│  │  │Elicit.  │ │Arch.    │ │Planning │                                    ││
│  │  │Agent    │ │Agent    │ │Agent    │                                    ││
│  │  └─────────┘ └─────────┘ └─────────┘                                    ││
│  │                                                                           ││
│  │  Extended (Phase 2):     Full (Phase 3, if needed):                      ││
│  │  ┌─────────┐             ┌─────────┐ ┌─────────┐                        ││
│  │  │Review   │             │Testing  │ │Security │                        ││
│  │  │Agent    │             │Agent    │ │Agent    │                        ││
│  │  └─────────┘             └─────────┘ └─────────┘                        ││
│  │                                                                           ││
│  │  Each agent: Has prompt template, focused context, structured output     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                      │                                        │
│                                      ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         PERSISTENCE LAYER                                 ││
│  │                                                                           ││
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐   ││
│  │  │  Beads Integration │  │  Artifact Storage  │  │  Session State    │   ││
│  │  │                    │  │                    │  │                    │   ││
│  │  │  - Planning tasks  │  │  - Design docs    │  │  - Conversation   │   ││
│  │  │  - Phase progress  │  │  - Task files     │  │    history        │   ││
│  │  │  - Checkpoints     │  │  - Plans          │  │  - Decisions      │   ││
│  │  └───────────────────┘  └───────────────────┘  └───────────────────┘   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│                    CPF STATE MACHINE                              │
│                                                                   │
│  ┌─────────┐                                                      │
│  │  INIT   │                                                      │
│  └────┬────┘                                                      │
│       │ User provides intent                                      │
│       ▼                                                           │
│  ┌─────────┐        ┌─────────┐                                  │
│  │ELICIT   │◀──────▶│ELICIT   │ (Iteration loop)                 │
│  │_ACTIVE  │        │_REVIEW  │                                  │
│  └────┬────┘        └─────────┘                                  │
│       │ Checkpoint approved                                       │
│       ▼                                                           │
│  ┌─────────┐        ┌─────────┐                                  │
│  │DESIGN   │◀──────▶│DESIGN   │ (Iteration loop)                 │
│  │_ACTIVE  │        │_REVIEW  │                                  │
│  └────┬────┘        └─────────┘                                  │
│       │ Checkpoint approved                                       │
│       ▼                                                           │
│  ┌─────────┐        ┌─────────┐                                  │
│  │PLAN     │◀──────▶│PLAN     │ (Iteration loop)                 │
│  │_ACTIVE  │        │_REVIEW  │                                  │
│  └────┬────┘        └─────────┘                                  │
│       │ Checkpoint approved                                       │
│       ▼                                                           │
│  ┌─────────┐        ┌─────────┐                                  │
│  │HANDOFF  │───────▶│IMPLEMENT│ (Transfer to execution)          │
│  │         │        │_READY   │                                  │
│  └─────────┘        └─────────┘                                  │
│                                                                   │
│  Transitions:                                                     │
│  - APPROVE: Move to next phase                                   │
│  - REVISE: Return to phase active state                          │
│  - RESTART: Return to phase start                                │
│  - ABORT: End workflow                                           │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Integration with Existing Systems

| System | Integration Point | Purpose |
|--------|-------------------|---------|
| **Beads** | Persistence layer | Track planning tasks, phase progress, checkpoints |
| **Slack** | User interface | Checkpoint notifications, feedback collection |
| **GitHub** | Artifact storage | Store design docs, plans in repo |
| **CLAUDE.md** | Context loading | Provide organizational standards to agents |
| **Notifications** | Human alerting | Checkpoint readiness, feedback requests |

### Beads Schema for CPF Sessions

Each CPF planning session is tracked as a beads task with structured notes. This enables session resumption across container restarts.

#### Example Bead Structure

```yaml
# Bead for CPF planning session
id: beads-ipf-oauth2-001
title: "CPF: Add OAuth2 Support for GitHub Authentication"
status: in_progress  # open | in_progress | blocked | closed
priority: P2
labels:
  - ipf-session
  - feature
  - slack-thread-12345  # Link to originating request

description: |
  Collaborative Planning Framework session for adding GitHub OAuth2 authentication.
  Initiated from Slack thread by @jwiesebron.

# Structured notes field contains CPF state
notes: |
  ## CPF Session State

  session_id: ipf-session-abc123
  started: 2025-12-04T10:00:00Z
  checkpoint_mode: condensed  # full | condensed | fast-path

  ## Current Phase
  phase: design
  phase_status: awaiting_checkpoint
  iteration: 1

  ## Phase History
  phases:
    elicitation:
      status: approved
      iterations: 1
      checkpoint_approved: 2025-12-04T10:15:00Z
      tokens_used: 8200
    design:
      status: in_progress
      iterations: 1
      tokens_used: 12400

  ## Artifacts Generated
  artifacts:
    - path: planning-output/requirements.md
      phase: elicitation
      generated: 2025-12-04T10:12:00Z
    - path: planning-output/design-document.md
      phase: design
      generated: 2025-12-04T10:30:00Z
      status: draft  # draft | checkpoint_ready | approved

  ## Checkpoint History
  checkpoints:
    - id: checkpoint-1
      phase: elicitation
      outcome: APPROVE
      human_time: "3m 45s"
      feedback: null
    - id: checkpoint-2
      phase: design
      outcome: pending
      presented: 2025-12-04T10:31:00Z

  ## Token Budget
  token_budget:
    limit: 150000
    used: 20600
    remaining: 129400

  ## Resume Instructions
  resume_context: |
    Session paused at Design checkpoint. User was presented with:
    - Architecture overview (4 components)
    - Technical decisions (OAuth library choice)
    - Security considerations (CSRF, token encryption)
    Awaiting approval to proceed to Planning phase.
```

#### Session Resumption

When resuming an CPF session:

```python
# Pseudocode for session resumption
def resume_ipf_session(bead_id: str) -> CPFSession:
    bead = beads.get(bead_id)

    # Parse structured notes
    state = parse_ipf_state(bead.notes)

    # Validate state integrity
    if not validate_state(state):
        raise StateCorruptionError("CPF state invalid, manual recovery needed")

    # Restore session
    session = CPFSession(
        id=state.session_id,
        current_phase=state.phase,
        phase_status=state.phase_status,
        artifacts=load_artifacts(state.artifacts),
        token_budget=state.token_budget
    )

    # Continue from checkpoint if awaiting
    if state.phase_status == "awaiting_checkpoint":
        session.present_checkpoint()

    return session
```

#### Beads Labels for CPF

| Label | Purpose |
|-------|---------|
| `ipf-session` | Identifies all CPF planning sessions |
| `ipf-phase-{phase}` | Current phase (elicitation, design, planning, handoff) |
| `ipf-awaiting-human` | Session blocked on human checkpoint |
| `ipf-completed` | Successfully completed planning sessions |
| `ipf-abandoned` | Sessions that were cancelled or timed out |

## Implementation Phases

### Phase 1: Foundation

**Objective:** Core orchestration infrastructure

**Tasks:**
1. Implement CPF Orchestrator with state machine
2. Create agent dispatch mechanism
3. Integrate with Beads for persistence
4. Build checkpoint notification system
5. Create artifact storage structure

**Success Criteria:**
- State machine transitions correctly
- Agents can be invoked with context
- Progress persists across sessions
- Checkpoints generate notifications

**Dependencies:** Existing jib infrastructure

### Phase 2: Core Agents

**Objective:** Implement specialized planning agents

**Tasks:**
1. Implement Elicitation Agent with questioning strategies
2. Implement Architecture Agent with design patterns
3. Implement Planning Agent with task decomposition
4. Implement Review Agent with gap analysis

**Success Criteria:**
- Each agent produces structured output
- Outputs pass validation
- Agents handle iteration gracefully
- Quality comparable to human planning

**Dependencies:** Phase 1 (orchestration infrastructure)

### Phase 3: Specialist Agents

**Objective:** Add specialized review perspectives

**Tasks:**
1. Implement Testing Agent with strategy generation
2. Implement Security Agent with threat modeling
3. Create parallel execution for specialists
4. Build output synthesis for multi-agent results

**Success Criteria:**
- Specialists provide valuable additions
- Parallel execution works correctly
- Outputs integrate cleanly
- No conflicts between specialists

**Dependencies:** Phase 2 (core agents)

### Phase 4: Artifact Generation

**Objective:** Produce implementation-ready documentation

**Tasks:**
1. Create artifact templates
2. Implement document generators
3. Build YAML task file generator
4. Create implementation guide generator

**Success Criteria:**
- All artifact types generated correctly
- Documents are complete and consistent
- Machine-readable formats parse correctly
- Human-readable formats are clear

**Dependencies:** Phase 3 (all agents producing outputs)

### Phase 5: Implementation Handoff

**Objective:** Enable autonomous execution from plans

**Tasks:**
1. Create execution readiness validator
2. Build task sequencer
3. Integrate with existing implementation pipeline
4. Create quality gate validators

**Success Criteria:**
- Validator catches incomplete plans
- Tasks execute in correct order
- Quality gates enforce standards
- End-to-end workflow functional

**Dependencies:** Phase 4 (complete artifacts), ADR-Multi-Agent-Pipeline-Architecture (must be implemented first)

## Consequences

### Benefits

1. **Reduced Ambiguity:** Thorough planning eliminates gaps that cause implementation delays
2. **Better Outcomes:** Multi-perspective review catches issues early
3. **User Empowerment:** Non-technical users can drive complex projects
4. **Autonomous Execution:** Complete plans enable minimal-intervention implementation
5. **Documentation by Default:** Planning artifacts serve as project documentation
6. **Consistent Quality:** Structured process ensures completeness

### Drawbacks

1. **Initial Overhead:** More time in planning before implementation
2. **Checkpoint Fatigue:** Multiple approval points may slow progress
3. **Complexity:** Multi-agent coordination adds system complexity
4. **Token Cost:** Multiple agents and iterations increase LLM costs
5. **Learning Curve:** Users need to understand checkpoint expectations

### Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Checkpoint bottleneck | High | Medium | Async notifications, batch approvals, checkpoint flexibility |
| Agent coordination failures | High | Low | Robust error handling, state recovery |
| Over-planning simple tasks | Medium | Medium | Fast-path for simple projects, scope detection |
| User disengagement | Medium | Medium | Clear progress indicators, estimated time |
| Inconsistent outputs | Medium | Low | Validation schemas, review agent |
| Token cost overrun | Medium | Medium | Cost monitoring, phase limits, model tiering |

## Evaluation and Success Metrics

Understanding how to measure CPF's effectiveness is critical for validating the investment and guiding improvements.

### Top-Line Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **First-Checkpoint Approval Rate** | ≥70% | % of checkpoints approved without revision on first presentation |
| **Implementation Revision Rate** | <15% | % of tasks requiring significant revision after implementation starts (vs. current ~30% baseline) |
| **Planning-to-Implementation Ratio** | <0.5 | Planning token cost ÷ Implementation token cost (goal: planning is cheap relative to execution) |
| **Human Time per Session** | <30 min | Total human time spent on checkpoints and feedback |
| **Plan Completeness Score** | ≥85% | % of implementation decisions made in plan (no TODOs/TBDs deferred) |

### Quality Dimensions for Artifacts

Each artifact type is evaluated against specific quality dimensions, adapted from the Codebase Analyzer ADR:

#### Requirements Document Quality

| Dimension | Definition | Measurement |
|-----------|------------|-------------|
| **Completeness** | All necessary requirements captured | Checklist coverage + LLM-as-Judge rating |
| **Clarity** | Requirements are unambiguous | Ambiguity detection (LLM scan for "may", "might", "could") |
| **Testability** | Each requirement has measurable acceptance criteria | % of requirements with testable criteria |
| **Prioritization** | Must-have vs. nice-to-have clearly distinguished | Binary: is prioritization present? |

#### Design Document Quality

| Dimension | Definition | Measurement |
|-----------|------------|-------------|
| **Architectural Soundness** | Design follows established patterns | LLM-as-Judge against architecture guidelines |
| **Technical Feasibility** | Design is implementable with available resources | Expert review or LLM feasibility check |
| **Security Coverage** | Security considerations addressed | Presence of security section with threat analysis |
| **Test Strategy Coverage** | Testing approach defined | Presence of test strategy with coverage targets |

#### Task Breakdown Quality

| Dimension | Definition | Measurement |
|-----------|------------|-------------|
| **Granularity** | Tasks are appropriately sized (not too big/small) | Average subtask count per task (target: 3-8) |
| **Dependency Accuracy** | Dependencies correctly identified | Post-implementation validation of declared dependencies |
| **Acceptance Criteria Quality** | Criteria are specific and testable | LLM-as-Judge for specificity |
| **Actionability** | Tasks can be started immediately without clarification | First-attempt success rate during implementation |

### LLM-as-Judge Evaluation

For subjective quality dimensions, use a dedicated evaluation prompt:

```
You are evaluating the quality of a planning artifact.

Artifact Type: {requirements_doc | design_doc | task_breakdown}
Artifact Content: {content}

Rate the following dimensions on a 1-5 scale with brief justification:

1. Completeness: Are all necessary elements present?
2. Clarity: Is the content unambiguous?
3. Actionability: Can someone act on this without further clarification?
4. Consistency: Does it align with other artifacts and project context?

Output format:
{
  "completeness": {"score": N, "justification": "..."},
  "clarity": {"score": N, "justification": "..."},
  "actionability": {"score": N, "justification": "..."},
  "consistency": {"score": N, "justification": "..."},
  "overall": N,
  "improvement_suggestions": ["...", "..."]
}
```

### A/B Testing Framework

To validate CPF effectiveness:

1. **Control Group**: Tasks assigned via current reactive approach
2. **Test Group**: Tasks processed through CPF
3. **Metrics Tracked**:
   - Implementation revision count
   - Total tokens to completion
   - Human intervention count
   - Time to PR merge
   - Post-merge bug count (30-day window)

### Feedback Collection Mechanism

When a checkpoint is rejected or revised, structured feedback is captured:

```yaml
# checkpoint_feedback.yaml
checkpoint_id: "session-abc123-checkpoint-2"
phase: "design"
iteration: 2
outcome: "REVISE"  # APPROVE | APPROVE_WITH_COMMENTS | REVISE | RESTART

# Structured feedback categories
feedback:
  category: "incomplete"  # incomplete | incorrect | unclear | missing_context | other
  affected_sections:
    - "security_model"
    - "authentication_flows"
  human_comment: "Need more detail on OAuth token lifecycle"

  # Machine-parseable improvement hints
  improvement_hints:
    - type: "expand"
      target: "security_model.authentication"
      detail: "Add token refresh, expiry, revocation flows"
    - type: "add"
      target: "security_model"
      detail: "Add sequence diagram for OAuth flow"

# Metrics for learning
metrics:
  time_to_feedback: "5m 32s"
  artifact_tokens: 2340
  human_edit_distance: 0  # 0 if no direct edits, >0 if human modified artifact
```

**Feedback Integration Flow:**

```
Human Feedback Received
        │
        ▼
┌─────────────────────────────────────────┐
│  1. Parse structured feedback           │
│  2. Classify feedback type              │
│  3. Route to appropriate agent          │
│  4. Agent generates revision            │
│  5. Store feedback for pattern analysis │
└─────────────────────────────────────────┘
        │
        ▼
Pattern Analysis (Periodic):
- Common rejection reasons by phase
- Agent-specific improvement opportunities
- Prompt refinement suggestions
```

### Success Criteria for CPF Launch

CPF is considered validated when:

1. **Quantitative**: 10 planning sessions completed with metrics showing improvement over baseline
2. **Qualitative**: User feedback indicates planning feels "productive" not "bureaucratic"
3. **Economic**: Token cost per successful implementation is ≤2x current reactive approach

## Security Considerations

Agent orchestration introduces security considerations that must be addressed.

### Threat Model

| Threat | Risk Level | Mitigation |
|--------|------------|------------|
| **Prompt Injection via User Input** | High | Input sanitization, system prompt hardening, output validation |
| **Agent-to-Agent Message Tampering** | Medium | Structured message formats, validation at agent boundaries |
| **Credential Exposure in Artifacts** | High | Artifact scanning for secrets before storage, `.gitignore` patterns |
| **Excessive Permission Escalation** | Medium | Principle of least privilege for each agent, capability-based access |
| **State Corruption** | Low | Beads integrity checks, session state validation |

### Sandboxing Requirements

Each agent operates within defined boundaries:

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT SANDBOXING MODEL                         │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                    ORCHESTRATOR                             │   │
│  │                                                             │   │
│  │  Capabilities:                                              │   │
│  │  ✓ Invoke specialist agents                                │   │
│  │  ✓ Read/write beads state                                  │   │
│  │  ✓ Generate artifacts to planning-output/                  │   │
│  │  ✓ Send checkpoint notifications                           │   │
│  │  ✗ Execute arbitrary code                                  │   │
│  │  ✗ Access production systems                               │   │
│  │  ✗ Modify files outside planning-output/                   │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                  SPECIALIST AGENTS                          │   │
│  │  (Elicitation, Architecture, Planning, Review)              │   │
│  │                                                             │   │
│  │  Capabilities:                                              │   │
│  │  ✓ Receive context from orchestrator                       │   │
│  │  ✓ Generate structured output                              │   │
│  │  ✓ Read codebase (for context)                             │   │
│  │  ✗ Write any files directly                                │   │
│  │  ✗ Execute commands                                        │   │
│  │  ✗ Access network resources                                │   │
│  │  ✗ Invoke other agents directly                            │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Artifact Security Scanning

Before storing any artifact:

1. **Secret Detection**: Scan for API keys, tokens, passwords using pattern matching
2. **PII Detection**: Flag potential personally identifiable information
3. **Path Validation**: Ensure artifact paths are within allowed directories
4. **Content Validation**: Verify artifact matches expected schema

```python
# Example artifact validation
def validate_artifact(artifact_type: str, content: str, path: str) -> bool:
    # Path must be within planning-output/
    if not path.startswith("planning-output/"):
        raise SecurityError("Artifact path outside allowed directory")

    # Scan for secrets
    if contains_secrets(content):
        raise SecurityError("Artifact contains potential secrets")

    # Validate schema
    if not matches_schema(artifact_type, content):
        raise ValidationError("Artifact does not match expected schema")

    return True
```

### Security Review Requirement

**This ADR requires security team review before implementation** due to:

1. Multi-agent orchestration complexity
2. User input handling across multiple agents
3. Artifact generation and storage
4. Integration with existing authentication/authorization

### Audit Logging

All CPF operations are logged for security audit:

```yaml
# audit_log entry
timestamp: "2025-12-04T10:30:00Z"
session_id: "ipf-session-abc123"
event_type: "checkpoint_approved"  # agent_invoked | artifact_generated | checkpoint_* | session_*
actor: "human:jwiesebron"  # or "agent:orchestrator"
details:
  phase: "design"
  checkpoint_id: "checkpoint-2"
  artifact_count: 3
  token_cost: 14000
```

## Cost Analysis

Understanding the economic impact of CPF is critical before implementation.

### Token Consumption Estimates (MVP Architecture)

Based on industry research showing multi-agent systems use ~15x more tokens than single-agent for complex tasks, here are conservative estimates for a **medium-complexity planning session** (e.g., "Add OAuth2 support to authentication system"):

| Phase | Agent(s) | Input Tokens | Output Tokens | Subtotal |
|-------|----------|--------------|---------------|----------|
| **Elicitation** | Orchestrator + Elicitation | ~5,000 | ~3,000 | ~8,000 |
| **Design** | Orchestrator + Architecture | ~8,000 | ~6,000 | ~14,000 |
| **Planning** | Orchestrator + Planning | ~10,000 | ~5,000 | ~15,000 |
| **Handoff** | Orchestrator | ~6,000 | ~3,000 | ~9,000 |
| **Iterations** (2x average) | Various | ~10,000 | ~8,000 | ~18,000 |
| **TOTAL** | | | | **~64,000 tokens** |

### Cost Distribution by Percentile

The P50 estimate above assumes 2 iterations. Real-world sessions vary significantly:

| Percentile | Scenario | Iterations | Total Tokens | Cost |
|------------|----------|------------|--------------|------|
| **P25** | Straightforward requirements, fast approval | 1 | ~46,000 | ~$0.83 |
| **P50** | Typical session with minor revisions | 2 | ~64,000 | ~$1.15 |
| **P75** | Complex requirements, design debates | 4 | ~100,000 | ~$1.80 |
| **P90** | Significant scope changes, major redesign | 6 | ~150,000 | ~$2.70 |
| **P95** | Contentious project, multiple restarts | 8+ | ~200,000 | ~$3.60 |

**P95 Breakdown:**

```
P95 Session (200K tokens) - "Contentious Architecture Decision"
├── Elicitation:     ~12,000 (3 iterations - unclear stakeholder alignment)
├── Design:          ~45,000 (4 iterations - architecture debates)
├── Planning:        ~25,000 (2 iterations - dependency complexity)
├── Handoff:         ~15,000 (1 iteration)
├── Re-work:         ~50,000 (partial restart after design rejection)
└── Overhead:        ~53,000 (context loading, summaries, coordination)
```

**Cost Alerting Thresholds:**

| Threshold | Tokens | Action |
|-----------|--------|--------|
| **Warning** | 100,000 (P75) | Log warning, notify user of elevated cost |
| **Alert** | 150,000 (P90) | Require explicit human approval to continue |
| **Hard Cap** | 200,000 (P95) | Pause session, escalate for cost review |

### Cost Comparison

| Approach | Tokens per Task | Cost (Claude Sonnet @ $3/$15 per 1M) | Notes |
|----------|-----------------|--------------------------------------|-------|
| **Current reactive** (single agent) | ~15,000 | ~$0.27 | May miss requirements, requires revision |
| **CPF MVP** (4 agents) | ~64,000 | ~$1.15 | Comprehensive planning, fewer implementation revisions |
| **CPF Extended** (5 agents + Review) | ~85,000 | ~$1.53 | Adds cross-validation |
| **CPF Full** (7 agents) | ~120,000 | ~$2.16 | Full specialist coverage |

### Break-Even Analysis

CPF is economically justified when:

1. **Implementation revisions avoided:** If CPF saves even 1 implementation revision cycle (~30,000 tokens), it breaks even
2. **Human time saved:** If planning saves 30+ minutes of human clarification during implementation
3. **Quality improvement:** If reduced bugs/rework justifies 4-8x token cost increase

### When to Use CPF vs. Simpler Approaches

| Task Complexity | Approach | Rationale |
|-----------------|----------|-----------|
| **Simple** (bug fix, small feature) | Single-agent reactive | Low overhead, clear requirements |
| **Medium** (new feature, integration) | CPF with 2 checkpoints | Balance between planning and speed |
| **Complex** (new system, architecture change) | Full CPF | Comprehensive planning prevents costly rework |
| **Exploratory** (R&D, prototype) | Single-agent with iteration | Flexibility over structure |

### Cost Monitoring and Limits

To prevent cost overruns, implement:

1. **Phase token limits:** Alert if any phase exceeds 2x expected tokens
2. **Session token limits:** Cap total session at 150,000 tokens (request human guidance)
3. **Iteration limits:** Maximum 3 iterations per phase before escalating
4. **Model tiering:** Use Claude Haiku for checkpoint summaries, Sonnet for planning agents

## Checkpoint Flexibility

To address checkpoint fatigue risk, CPF supports flexible checkpoint configurations.

### Checkpoint Modes

| Mode | Checkpoints | Use When |
|------|-------------|----------|
| **Full** | 4 (after each phase) | Complex projects, high-stakes decisions, unfamiliar domains |
| **Condensed** | 2 (after Elicitation, after Handoff) | Medium projects, familiar patterns, trusted agent output |
| **Fast-Path** | 1 (final approval only) | Simple tasks, experienced users, low-risk changes |

### Scope Detection

The Orchestrator automatically suggests checkpoint mode based on:

```
┌─────────────────────────────────────────────────────────────────┐
│                    SCOPE DETECTION                                │
│                                                                   │
│  Indicators for FULL mode:                                        │
│  - Multiple system components affected                           │
│  - New architectural patterns                                     │
│  - Security-sensitive changes                                    │
│  - External integration                                          │
│  - User-facing changes                                           │
│                                                                   │
│  Indicators for CONDENSED mode:                                  │
│  - Single component affected                                     │
│  - Follows existing patterns                                     │
│  - Internal-only changes                                         │
│  - Clear success criteria provided                               │
│                                                                   │
│  Indicators for FAST-PATH:                                       │
│  - Bug fix with known solution                                   │
│  - Documentation updates                                         │
│  - Configuration changes                                         │
│  - User explicitly requests fast-path                            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Checkpoint Combining

In Condensed mode, checkpoints are combined:

**Combined Checkpoint 1 (after Elicitation + Design):**
- Requirements summary
- Architecture overview
- Test strategy outline
- Security considerations
- Single approval covers both phases

**Combined Checkpoint 2 (after Planning + Handoff):**
- Phased plan summary
- Task breakdown overview
- Final implementation package
- Single approval to proceed

### Timeout and Escalation

If human doesn't respond to checkpoint within configured timeout:

| Timeout | Action |
|---------|--------|
| 4 hours | Send reminder notification |
| 24 hours | Escalate to secondary contact (if configured) |
| 48 hours | Pause planning, mark session as "awaiting human" |

Users can configure:
- Default checkpoint timeout
- Escalation contacts
- Auto-pause behavior
- Notification frequency

## Example Walkthrough

A concrete end-to-end example using a realistic task smaller than "rewrite jib."

### Task: "Add OAuth2 Support for GitHub Authentication"

**User Input:** "I want users to be able to log in using their GitHub account instead of email/password."

---

### Phase 1: Elicitation

**Elicitation Agent Output:**

```markdown
## Requirements Summary

### Intent
Enable GitHub OAuth2 login as an authentication option alongside existing email/password.

### Goals
1. Primary: Users can authenticate via GitHub
2. Secondary: Reduce friction for developers who prefer GitHub
3. Non-goal: Replace existing email/password auth (keep both)

### Scope
- IN: GitHub OAuth2 flow, user account linking, token management
- OUT: Other OAuth providers (future work), SSO/SAML

### Constraints
- Must work with existing session management
- No changes to current user database schema (add linking table)
- Must handle GitHub account linking for existing users

### Success Criteria
- User can log in with GitHub in < 3 clicks
- Existing users can link/unlink GitHub accounts
- Session behavior identical to email/password auth
```

**Checkpoint 1 Summary:**
> "I've gathered requirements for GitHub OAuth2. Users will be able to log in via GitHub while keeping existing email/password auth. Scope excludes other OAuth providers. Ready to proceed with design?"
>
> **[APPROVE]** | [REVISE] | [RESTART]

---

### Phase 2: Design

**Architecture Agent Output (excerpt):**

```markdown
## Architecture Overview

### Component Changes
1. **Auth Service** - Add OAuth2 handler, token exchange logic
2. **User Service** - Add account linking API
3. **Frontend** - Add "Login with GitHub" button, linking UI
4. **Database** - New `user_oauth_links` table

### Technical Decisions
- **OAuth Library:** Use existing `requests-oauthlib` (Python)
- **Token Storage:** Encrypted in database, not in session
- **Account Linking:** Optional, prompt on first GitHub login

### Security Considerations
- CSRF protection on OAuth callback
- State parameter validation
- Token encryption at rest
- Rate limiting on OAuth endpoints

### Test Strategy
- Unit tests for token exchange
- Integration tests for full OAuth flow
- E2E test for login + link/unlink
```

**Checkpoint 2 Summary:**
> "Design complete. Using `requests-oauthlib`, adding linking table, frontend button. Security includes CSRF protection and token encryption. Ready for task breakdown?"
>
> **[APPROVE]** | [REVISE] | [RESTART]

---

### Phase 3: Planning

**Planning Agent Output (excerpt):**

```yaml
# tasks.yaml
phases:
  - id: phase-1
    name: "Backend OAuth Infrastructure"
    tasks:
      - id: task-1.1
        name: "Add OAuth2 handler to auth service"
        complexity: moderate
        acceptance_criteria:
          - "Initiates GitHub OAuth flow"
          - "Handles callback with code exchange"
          - "Returns user identity from GitHub"
        subtasks:
          - "Create OAuth config (client_id, secret, scopes)"
          - "Implement /auth/github/initiate endpoint"
          - "Implement /auth/github/callback endpoint"
          - "Add token exchange logic"
          - "Write unit tests"

      - id: task-1.2
        name: "Add user_oauth_links table"
        dependencies: []
        complexity: simple
        # ...

  - id: phase-2
    name: "Account Linking"
    dependencies: ["phase-1"]
    tasks:
      - id: task-2.1
        name: "Implement account linking API"
        # ...
```

**Checkpoint 3 Summary:**
> "Broke down into 2 phases, 6 tasks, 18 subtasks. Phase 1 is backend infrastructure, Phase 2 is account linking, Phase 3 is frontend. Dependencies mapped. Ready for final package?"
>
> **[APPROVE]** | [REVISE] | [RESTART]

---

### Phase 4: Handoff

**Final Package:**

```
📁 planning-output/
├── requirements.md       (4 pages)
├── design-document.md    (8 pages)
├── phased-plan.md        (6 pages)
├── tasks.yaml            (machine-readable)
└── implementation-guide.md
```

**Final Checkpoint:**
> "Complete package ready. 2 phases, 6 tasks, ~18 subtasks. Estimated token cost for implementation: ~45,000 tokens. Ready for autonomous implementation?"
>
> **[APPROVE FOR IMPLEMENTATION]** | [REVISE] | [RESTART]

---

### Session Metrics

| Metric | Value |
|--------|-------|
| **Total tokens used** | 52,000 |
| **Elicitation iterations** | 1 |
| **Design iterations** | 0 |
| **Planning iterations** | 1 (refined subtask granularity) |
| **Human approval time** | ~15 minutes total |
| **Artifacts produced** | 5 documents |

## Decision Permanence

**Medium permanence.**

The framework's core principles (AI drives planning, human approves checkpoints, comprehensive artifacts) are foundational. However, specific implementations can evolve:

**Lower permanence (expect changes):**
- Agent prompt templates
- Artifact formats
- Checkpoint UI/UX
- Specialist agents (add/remove based on value)

**Higher permanence (foundational):**
- Multi-phase planning structure
- Human checkpoint pattern
- Multi-agent collaboration approach
- Artifact-driven implementation handoff

## Alternatives Considered

### Alternative 1: Enhanced Single-Agent Planning

**Description:** Improve the existing single-agent approach with better prompts.

**Pros:**
- Simpler implementation
- Lower token cost
- Faster to deploy

**Cons:**
- Cognitive overload for complex projects
- No specialization benefits
- Limited cross-validation

**Rejected because:** Research shows 40% accuracy improvement with multi-agent systems for complex tasks; single-agent cannot match this.

### Alternative 2: Fully Automated Planning (No Checkpoints)

**Description:** Let AI complete entire planning with single final approval.

**Pros:**
- Faster end-to-end
- Less user time required
- Simpler workflow

**Cons:**
- Higher risk of misalignment
- Large rework if final approval rejected
- User feels out of control

**Rejected because:** HULA research shows human-in-the-loop produces significantly better outcomes than full automation.

### Alternative 3: Pure Q&A Interview Format

**Description:** Structured questionnaire approach instead of conversational.

**Pros:**
- Predictable
- Easy to implement
- Complete coverage

**Cons:**
- Feels robotic
- Doesn't adapt to context
- May miss nuanced requirements

**Rejected because:** Conversational approaches with skilled questioning outperform rigid questionnaires for requirements elicitation.

### Alternative 4: External Tool Integration (Notion, Linear, etc.)

**Description:** Use existing planning tools instead of building custom.

**Pros:**
- Familiar UI
- Rich features
- Team collaboration

**Cons:**
- Integration complexity
- Dependency on external services
- May not support AI workflow needs

**Rejected because:** Tight integration with jib execution is critical; external tools create friction in the AI-driven workflow.

## References

### Industry Research

- [LLM-Based Multi-Agent Systems for Software Engineering](https://dl.acm.org/doi/10.1145/3712003) - ACM TOSEM survey on multi-agent SE
- [AI-Driven Development Life Cycle](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/) - AWS AI-DLC methodology
- [HULA: Human-in-the-Loop Software Development Agents](https://www.atlassian.com/blog/atlassian-engineering/hula-blog-autodev-paper-human-in-the-loop-software-development-agents) - Atlassian's framework
- [Tree of Thoughts: Deliberate Problem Solving](https://arxiv.org/abs/2305.10601) - NeurIPS 2023
- [Multi-Agent and Multi-LLM Architecture Guide 2025](https://collabnix.com/multi-agent-and-multi-llm-architecture-complete-guide-for-2025/)
- [LLM Agent Frameworks 2025](https://livechatai.com/blog/llm-agent-frameworks)
- [Agentic Software Engineering: Foundational Pillars](https://arxiv.org/html/2509.06216v1)
- [Requirements Engineering with LLMs](https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2025.1519437/full)

### Related ADRs

| ADR | Relationship | Implementation Order |
|-----|--------------|---------------------|
| [ADR-Multi-Agent-Pipeline-Architecture](ADR-Multi-Agent-Pipeline-Architecture.md) | Provides reusable agent infrastructure (orchestration, dispatch, state management) that CPF specializes for planning workflows. CPF is a *consumer* of Multi-Agent Pipeline, not a dependency. | Multi-Agent Pipeline FIRST, then CPF |
| [ADR-LLM-Documentation-Index-Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md) | Artifact output follows doc index patterns | Already implemented |
| [ADR-Context-Sync-Strategy](../implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | External context integration for planning agents | Already implemented |

**Clarification on ADR Relationship:**

The Multi-Agent Pipeline Architecture ADR and CPF are complementary but distinct:

- **Multi-Agent Pipeline Architecture** defines the *general infrastructure*: how to orchestrate agents, manage state, handle failures, and coordinate parallel work. It's a **reusable platform**.
- **CPF** is a *specific application* of that infrastructure for planning workflows. It defines the 4-phase planning process, specialized planning agents (Elicitation, Architecture, Planning, Review), and human checkpoint patterns.

**Implementation Sequencing:**
1. **Multi-Agent Pipeline Architecture** must be implemented first (provides AgentOrchestrator, state machine, dispatch mechanisms)
2. **CPF** is then implemented as a workflow that runs on that infrastructure
3. CPF's "Orchestrator Agent" is an instance of the Multi-Agent Pipeline's AgentOrchestrator configured for planning

This is analogous to: Multi-Agent Pipeline is like Kubernetes; CPF is like a specific application deployed on Kubernetes.

### Implementation Examples

- [Open-Source AI-DLC Workflows](https://aws.amazon.com/blogs/devops/open-sourcing-adaptive-workflows-for-ai-driven-development-life-cycle-ai-dlc/) - AWS implementation
- [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD) - AI-driven development methodology
- [LangGraph State Machines](https://dev.to/jamesli/langgraph-state-machines-managing-complex-agent-task-flows-in-production-36f4) - Production state management

---

**Last Updated:** 2025-12-04
**Next Review:** On implementation start
**Status:** Proposed (Not Implemented)
