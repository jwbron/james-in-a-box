# Foundational Technical Requirements for Post-LLM Software Engineering

**Status:** Draft
**Author:** James Wiesebron, james-in-a-box
**Created:** December 2025
**Purpose:** High-level planning document defining the technical foundations needed to implement the Post-LLM Software Engineering vision

---

> **Context:** This document defines the foundational technical requirements that enable the philosophy outlined in [A Pragmatic Guide for Software Engineering in a Post-LLM World](Pragmatic-Guide-Software-Engineering-Post-LLM-World.md). Each requirement maps to capabilities needed to realize the three pillars.

---

## Executive Summary

The Post-LLM Software Engineering vision requires six foundational technical capabilities:

| Foundation | Purpose | Enables |
|------------|---------|---------|
| **Multi-Agent Framework** | Coordinate specialized LLM agents | All pillars |
| **Interactive Development Framework** | Structured human-LLM collaboration | Pillar 2 |
| **PR Reviewer System** | Automated, specialized code review | Pillar 1 |
| **Codebase Analysis Engine** | Deep understanding of code structure | All pillars |
| **Index-Based Documentation** | Always-current, navigable documentation | Pillar 1, 2 |
| **Continual Self-Reflection** | Autonomous system improvement | Pillar 3 |

This document provides high-level technical requirements for each foundation, identifies dependencies and integration points, and proposes an implementation approach.

---

## Table of Contents

- [Foundation 1: Multi-Agent Framework](#foundation-1-multi-agent-framework)
- [Foundation 2: Interactive Development Framework](#foundation-2-interactive-development-framework)
- [Foundation 3: PR Reviewer System](#foundation-3-pr-reviewer-system)
- [Foundation 4: Codebase Analysis Engine](#foundation-4-codebase-analysis-engine)
- [Foundation 5: Index-Based Documentation Strategy](#foundation-5-index-based-documentation-strategy)
- [Foundation 6: Continual Self-Reflection Framework](#foundation-6-continual-self-reflection-framework)
- [Cross-Cutting Concerns](#cross-cutting-concerns)
- [Integration Architecture](#integration-architecture)
- [Implementation Approach](#implementation-approach)
- [Success Metrics](#success-metrics)
- [Open Questions](#open-questions)

---

## Foundation 1: Multi-Agent Framework

### Purpose

Provide infrastructure for coordinating multiple specialized LLM agents that collaborate on complex tasks. This is the **execution layer** that powers all other foundations.

### Core Requirements

#### Agent Orchestration

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Agent Registry** | Central registry of available agents with capabilities, constraints, and configuration | P0 |
| **Task Routing** | Route tasks to appropriate agents based on task type and agent capabilities | P0 |
| **Agent Communication** | Enable agents to hand off work, share context, and collaborate | P0 |
| **Execution Modes** | Support sequential, parallel, and hierarchical agent execution | P1 |
| **State Management** | Maintain shared state across agent invocations within a task | P0 |

#### Agent Types (Initial Set)

| Agent | Specialization | Use Cases |
|-------|---------------|-----------|
| **Orchestrator** | Task decomposition and delegation | Complex multi-step tasks |
| **Researcher** | Information gathering and synthesis | Context collection, documentation lookup |
| **Implementer** | Code generation and modification | Feature implementation, bug fixes |
| **Reviewer** | Code analysis and feedback | PR review, quality checks |
| **Documenter** | Documentation generation and maintenance | API docs, README updates |
| **Analyst** | Pattern detection and insights | Performance analysis, inefficiency detection |

#### Agent Lifecycle

```
┌────────────────────────────────────────────────────────────────┐
│                     Agent Lifecycle                            │
│                                                                │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  CREATE  │───▶│ CONFIGURE│───▶│  EXECUTE │───▶│ COMPLETE │  │
│  │          │    │          │    │          │    │          │  │
│  │ • Load   │    │ • Set    │    │ • Run    │    │ • Return │  │
│  │   config │    │   context│    │   tools  │    │   result │  │
│  │ • Init   │    │ • Apply  │    │ • Track  │    │ • Clean  │  │
│  │   state  │    │   limits │    │   state  │    │   up     │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### Observability

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Execution Tracing** | Full trace of agent execution, tool calls, and decisions | P0 |
| **Token Tracking** | Track token usage per agent, task, and session | P0 |
| **Performance Metrics** | Latency, success rate, retry count per agent type | P1 |
| **Audit Logging** | Immutable log of all agent actions for accountability | P0 |

### Key Design Decisions

1. **Agent Isolation vs. Shared State**: How much context do agents share?
2. **Synchronous vs. Async Execution**: When should agents run in parallel?
3. **Error Handling**: How do agents recover from failures? Retry? Escalate?
4. **Resource Limits**: Per-agent token budgets, time limits, tool restrictions

### Dependencies

- LLM provider integration (Claude, potentially others)
- Tool infrastructure (filesystem, git, MCP servers)
- State persistence (beads, database)

---

## Foundation 2: Interactive Development Framework

### Purpose

Enable structured, rigorous collaboration between humans and LLMs during the development process. This is the **collaboration layer** that implements Pillar 2 (Human-Driven, LLM-Navigated).

### Core Requirements

#### Interactive Planning Framework (IPF)

The IPF provides structured dialogue for complex development tasks:

| Phase | Purpose | Outputs |
|-------|---------|---------|
| **Elicitation** | Transform vague intent into validated requirements | Requirements document with stated assumptions |
| **Design** | Explore solution space and present options | Design options with trade-offs |
| **Planning** | Break down into implementable tasks | Phased task breakdown with dependencies |
| **Handoff** | Package for autonomous execution | Machine-readable task specifications |

#### Human-in-the-Loop Checkpoints

| Checkpoint Type | Trigger | Required Action |
|-----------------|---------|-----------------|
| **Approval** | Phase transition | Human must explicitly approve |
| **Decision** | Multiple valid options | Human must choose |
| **Review** | Significant output | Human must validate |
| **Escalation** | Agent uncertainty or risk | Human must provide guidance |

#### Dialogue Management

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Structured Questions** | LLM asks targeted questions to elicit requirements | P0 |
| **Context Persistence** | Maintain conversation context across sessions | P0 |
| **Decision Capture** | Record human decisions with rationale | P0 |
| **Progress Tracking** | Show where in the planning process the user is | P1 |
| **Resumability** | Resume interrupted planning sessions | P1 |

#### Task Specification Format

```yaml
# Example task specification output from IPF
task:
  id: task-001
  title: "Add rate limiting to API"
  type: implementation

requirements:
  functional:
    - "Limit requests to 100/minute per API key"
    - "Return 429 status with retry-after header when exceeded"
  non_functional:
    - "Must not add >5ms latency to requests"
    - "Must work in distributed deployment"

constraints:
  - "Must not break existing clients"
  - "Prefer Redis for distributed rate limiting"

design_decisions:
  - decision: "Use sliding window algorithm"
    rationale: "Better handles burst traffic than fixed window"
    alternatives_considered: ["fixed window", "token bucket"]
    decided_by: "human"

success_criteria:
  - "All existing tests pass"
  - "New tests cover rate limit scenarios"
  - "Documentation updated"

phases:
  - phase: 1
    tasks:
      - "Implement rate limiter core logic"
      - "Add Redis integration"
  - phase: 2
    tasks:
      - "Add middleware to API"
      - "Update API documentation"
```

### Key Design Decisions

1. **Framework vs. Freeform**: How structured should the planning dialogue be?
2. **Synchronous vs. Async**: Can planning happen over multiple sessions?
3. **Persistence**: How are planning artifacts stored and versioned?
4. **Integration**: How does IPF integrate with task tracking (beads)?

### Dependencies

- Multi-Agent Framework (agent orchestration)
- Task tracking system (beads)
- Context persistence layer

---

## Foundation 3: PR Reviewer System

### Purpose

Provide automated, specialized code review that catches issues before human review. This is the **quality layer** that implements Pillar 1 (LLM-First Code Reviews).

### Core Requirements

#### Specialized Review Agents

| Agent | Focus Area | Checks |
|-------|------------|--------|
| **Security Reviewer** | Security vulnerabilities | OWASP Top 10, auth/authz issues, secrets exposure, injection vectors |
| **Infrastructure Reviewer** | DevOps and infrastructure | Resource limits, scaling concerns, configuration issues, deployment safety |
| **Product Reviewer** | Business logic and UX | Requirement alignment, edge cases, user impact, accessibility |
| **Architecture Reviewer** | Design patterns and structure | Consistency, coupling, separation of concerns, technical debt |
| **Nitpicker** | Code quality and style | Naming, formatting, documentation, test coverage |

#### Review Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PR Review Pipeline                           │
│                                                                 │
│  ┌───────────────┐                                              │
│  │  PR Created   │                                              │
│  └───────┬───────┘                                              │
│          │                                                      │
│          ▼                                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Automated Checks (Parallel)                              │  │
│  │  • Linting, Type Checking, Tests                          │  │
│  │  • SAST, Dependency Scanning                              │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Specialized Agent Reviews (Parallel or Sequential)       │  │
│  │  • Security → Infrastructure → Product → Architecture     │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Review Synthesis                                         │  │
│  │  • Aggregate findings                                     │  │
│  │  • Deduplicate and prioritize                             │  │
│  │  • Generate unified review                                │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Human Review                                             │  │
│  │  • Focus on strategic concerns                            │  │
│  │  • Approve, request changes, or escalate                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Review Configuration

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Agent Selection** | Choose which reviewers run based on PR characteristics | P0 |
| **Severity Levels** | Categorize findings (critical, warning, suggestion) | P0 |
| **Blocking Rules** | Configure which findings block merge | P1 |
| **Custom Rules** | Add organization-specific review rules | P1 |
| **Review Templates** | Consistent output format across agents | P0 |

#### Feedback Learning

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Feedback Capture** | Track which review comments are accepted/rejected | P0 |
| **Pattern Detection** | Identify recurring review themes | P1 |
| **Rule Generation** | Propose new automated checks from patterns | P1 |
| **False Positive Tracking** | Learn from dismissed findings | P1 |

### Key Design Decisions

1. **Agent Independence**: Do reviewers share context or review independently?
2. **Review Order**: Sequential (findings inform later reviews) or parallel (faster)?
3. **GitHub Integration**: Native GitHub review API or custom UI?
4. **Scope Limits**: Maximum PR size for automated review?

### Dependencies

- Multi-Agent Framework (agent coordination)
- Codebase Analysis Engine (code understanding)
- GitHub MCP (PR integration)
- Continual Self-Reflection (feedback learning)

---

## Foundation 4: Codebase Analysis Engine

### Purpose

Provide deep, structured understanding of codebase structure, patterns, and semantics. This is the **knowledge layer** that powers code-aware operations across all foundations.

### Core Requirements

#### Code Understanding

| Capability | Description | Priority |
|------------|-------------|----------|
| **Syntax Analysis** | Parse code into AST across supported languages | P0 |
| **Semantic Analysis** | Understand types, symbols, and their relationships | P0 |
| **Dependency Mapping** | Map import/export relationships between modules | P0 |
| **Pattern Detection** | Identify common patterns and anti-patterns | P1 |
| **Change Impact Analysis** | Determine what's affected by a code change | P1 |

#### Analysis Outputs

| Output | Description | Use Cases |
|--------|-------------|-----------|
| **Module Graph** | Dependency graph of modules/packages | Impact analysis, architecture visualization |
| **Symbol Index** | Searchable index of functions, classes, variables | Code navigation, refactoring |
| **Pattern Catalog** | Detected patterns with locations | Consistency checking, documentation |
| **Complexity Metrics** | Cyclomatic complexity, coupling, cohesion | Quality assessment, refactoring targets |
| **Test Coverage Map** | What code is covered by which tests | Risk assessment, test gap identification |

#### Analysis Modes

```
┌────────────────────────────────────────────────────────────────┐
│                    Analysis Modes                              │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  FULL ANALYSIS                                           │  │
│  │  • Complete codebase scan                                │  │
│  │  • Expensive but comprehensive                           │  │
│  │  • Run: On major changes, periodically                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  INCREMENTAL ANALYSIS                                    │  │
│  │  • Only analyze changed files + affected dependents      │  │
│  │  • Fast, efficient                                       │  │
│  │  • Run: On every commit/PR                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  TARGETED ANALYSIS                                       │  │
│  │  • Analyze specific paths or patterns                    │  │
│  │  • On-demand                                             │  │
│  │  • Run: When specific questions need answering           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### Language Support

| Language | Analysis Depth | Priority |
|----------|---------------|----------|
| **Python** | Full (AST, types, imports) | P0 |
| **TypeScript/JavaScript** | Full | P0 |
| **Go** | Full | P1 |
| **Java** | Partial | P2 |
| **Generic** | Basic (text search, regex) | P0 |

### Key Design Decisions

1. **Analysis Storage**: In-memory, filesystem, or database?
2. **Cache Invalidation**: How to know when analysis is stale?
3. **Incremental Updates**: How to efficiently update partial analysis?
4. **Multi-Repo**: Support for monorepos and multi-repo setups?

### Dependencies

- Language parsers (tree-sitter, language servers)
- Storage layer for analysis results
- File watching for incremental updates

---

## Foundation 5: Index-Based Documentation Strategy

### Purpose

Maintain always-current, navigable documentation through automated index generation and drift detection. This is the **navigation layer** that keeps humans and LLMs oriented.

### Core Requirements

#### Index Generation

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Automated Index** | Generate index from directory structure and file metadata | P0 |
| **Topic Clustering** | Group related documents by topic | P1 |
| **Cross-References** | Detect and maintain links between documents | P0 |
| **Navigation Hierarchy** | Multi-level navigation (category → subcategory → document) | P0 |

#### Documentation Types

| Type | Location | Update Trigger |
|------|----------|----------------|
| **Architecture Docs** | `docs/architecture/` | Manual + drift detection |
| **ADRs** | `docs/adr/` | Decision events |
| **Reference** | `docs/reference/` | Code changes |
| **Guides** | `docs/guides/` | Manual |
| **API Docs** | Generated | Code changes |

#### Drift Detection

```
┌────────────────────────────────────────────────────────────────┐
│                  Documentation Drift Detection                 │
│                                                                │
│  ┌──────────────────┐         ┌──────────────────┐             │
│  │     Code         │◀───────▶│   Documentation  │             │
│  │    Reality       │  SYNC?  │    Claims        │             │
│  └────────┬─────────┘         └────────┬─────────┘             │
│           │                            │                       │
│           ▼                            ▼                       │
│  ┌──────────────────┐         ┌──────────────────┐             │
│  │  Code Analysis   │         │   Doc Analysis   │             │
│  │  • Functions     │         │  • References    │             │
│  │  • Classes       │         │  • Examples      │             │
│  │  • Patterns      │         │  • Diagrams      │             │
│  └────────┬─────────┘         └────────┬─────────┘             │
│           │                            │                       │
│           └───────────┬────────────────┘                       │
│                       ▼                                        │
│           ┌──────────────────────────────┐                     │
│           │       DRIFT REPORT           │                     │
│           │  • Outdated references       │                     │
│           │  • Missing documentation     │                     │
│           │  • Stale examples            │                     │
│           │  • Broken links              │                     │
│           └──────────────────────────────┘                     │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

#### Documentation Features

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Search** | Full-text search across all documentation | P1 |
| **Versioning** | Link documentation to code versions | P2 |
| **Freshness Indicators** | Show last update date and staleness warnings | P0 |
| **Auto-Generation** | Generate docs from code comments and structure | P1 |

### Key Design Decisions

1. **Single Source of Truth**: Markdown files or generated from code?
2. **Hosting**: Static site generation or dynamic rendering?
3. **Update Frequency**: Real-time vs. batch updates?
4. **LLM Integration**: How do LLMs consume documentation?

### Dependencies

- Codebase Analysis Engine (code understanding)
- File system access for document management
- Index generator tooling

---

## Foundation 6: Continual Self-Reflection Framework

### Purpose

Enable the system to observe its own behavior, detect inefficiencies, and propose improvements. This is the **improvement layer** that implements Pillar 3 (Radical Self-Improvement).

### Core Requirements

#### Observation and Metrics

| Metric | Description | Collection |
|--------|-------------|------------|
| **Token Efficiency** | Tokens used per task type | Per-session |
| **Task Success Rate** | First-attempt success vs. rework needed | Per-task |
| **Clarification Frequency** | How often agent asks for clarification | Per-task |
| **Error Patterns** | Recurring error types | Per-session |
| **Execution Time** | Time to complete task types | Per-task |

#### Analysis Components

| Component | Purpose | Outputs |
|-----------|---------|---------|
| **Process Analyzer** | Detect inefficiencies in development process | Process improvement proposals |
| **LLM Inefficiency Analyzer** | Identify patterns of wasted tokens or rework | Prompt improvements, tool suggestions |
| **PR Review Reviewer** | Analyze human review feedback for patterns | New automated checks, rule updates |
| **Documentation Analyzer** | Find gaps between code and docs | Documentation update tasks |

#### Improvement Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                  Self-Improvement Loop                          │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   OBSERVE    │───▶│   ANALYZE    │───▶│   PROPOSE    │       │
│  │              │    │              │    │              │       │
│  │ • Collect    │    │ • Detect     │    │ • Generate   │       │
│  │   metrics    │    │   patterns   │    │   hypothesis │       │
│  │ • Track      │    │ • Identify   │    │ • Estimate   │       │
│  │   outcomes   │    │   root cause │    │   impact     │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                │                │
│                                                ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   MEASURE    │◀───│   IMPLEMENT  │◀───│   VALIDATE   │       │
│  │              │    │              │    │  (Human)     │       │
│  │ • Track      │    │ • Apply      │    │              │       │
│  │   outcomes   │    │   changes    │    │ • Review     │       │
│  │ • Compare    │    │ • Update     │    │ • Approve    │       │
│  │   to baseline│    │   systems    │    │ • Reject     │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Proposal Types

| Type | Description | Approval Required |
|------|-------------|-------------------|
| **Rule Addition** | New linting or review rule | Human approval |
| **Prompt Update** | Improved agent prompts | Human review |
| **Process Change** | Workflow modification | Human approval |
| **Documentation** | Auto-generated doc updates | Auto-merge (low risk) |
| **Tool Enhancement** | New tool or tool improvement | Human approval |

#### Memory and Persistence

| Requirement | Description | Priority |
|-------------|-------------|----------|
| **Pattern Log** | Persistent record of detected patterns | P0 |
| **Experiment Tracking** | Record of improvement experiments and results | P0 |
| **Cross-Session Context** | Maintain analysis context across sessions | P0 |
| **Historical Trends** | Track metrics over time | P1 |

### Key Design Decisions

1. **Human Approval Threshold**: What changes require human approval?
2. **Rollback Mechanism**: How to revert improvements that don't work?
3. **Experiment Design**: A/B testing vs. before/after comparison?
4. **Feedback Latency**: How quickly can we know if a change helped?

### Dependencies

- Multi-Agent Framework (specialized analysis agents)
- PR Reviewer System (feedback source)
- Metrics and logging infrastructure
- Beads or similar for persistence

---

## Cross-Cutting Concerns

### Security

| Concern | Mitigation | Priority |
|---------|------------|----------|
| **Secret Exposure** | Never log or expose secrets, sanitize all outputs | P0 |
| **Code Execution** | Sandbox all code execution, limit filesystem access | P0 |
| **API Security** | Authenticate all API calls, rate limit | P0 |
| **Data Isolation** | Separate data between organizations/projects | P0 |

### Scalability

| Concern | Approach | Priority |
|---------|----------|----------|
| **Large Codebases** | Incremental analysis, caching | P0 |
| **Concurrent Users** | Stateless agents, horizontal scaling | P1 |
| **Token Costs** | Budget management, caching, prompt optimization | P0 |
| **Storage** | Efficient storage of analysis results, pruning | P1 |

### Reliability

| Concern | Approach | Priority |
|---------|----------|----------|
| **Agent Failures** | Retry logic, graceful degradation | P0 |
| **Partial Results** | Handle incomplete analysis gracefully | P0 |
| **Idempotency** | Operations should be safely repeatable | P0 |
| **Audit Trail** | Full logging for debugging and accountability | P0 |

### Observability

| Concern | Approach | Priority |
|---------|----------|----------|
| **Logging** | Structured logging at all levels | P0 |
| **Metrics** | Key metrics for each foundation | P0 |
| **Tracing** | Distributed tracing across agents | P1 |
| **Alerting** | Alerts for failures and anomalies | P1 |

---

## Integration Architecture

### Component Relationships

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Integration Architecture                         │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                   MULTI-AGENT FRAMEWORK                     │    │
│  │              (Orchestration & Execution Layer)              │    │
│  └───────┬──────────────┬──────────────┬──────────────┬────────┘    │
│          │              │              │              │             │
│          ▼              ▼              ▼              ▼             │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │
│  │ INTERACTIVE│  │ PR REVIEW  │  │ CODEBASE   │  │ SELF-      │     │
│  │ DEVELOPMENT│  │ SYSTEM     │  │ ANALYSIS   │  │ REFLECTION │     │
│  │ FRAMEWORK  │  │            │  │ ENGINE     │  │ FRAMEWORK  │     │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘     │
│         │               │               │               │           │
│         └───────────────┴───────┬───────┴───────────────┘           │
│                                 │                                   │
│                                 ▼                                   │
│         ┌───────────────────────────────────────────────┐           │
│         │         INDEX-BASED DOCUMENTATION             │           │
│         │              (Navigation Layer)               │           │
│         └───────────────────────────────────────────────┘           │
│                                                                     │
│  ═══════════════════════════════════════════════════════════════    │
│                        INFRASTRUCTURE                               │
│                                                                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │  LLM    │  │  Git    │  │  GitHub │  │ Storage │  │ Metrics │    │
│  │ Provider│  │         │  │   MCP   │  │ (Beads) │  │/Logging │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow

| Flow | From | To | Data |
|------|------|----|------|
| **Task Creation** | Interactive Framework | Multi-Agent | Task specifications |
| **Code Context** | Codebase Analysis | PR Review, Interactive | Analysis results |
| **Review Feedback** | PR Review | Self-Reflection | Review comments, outcomes |
| **Improvements** | Self-Reflection | All foundations | Configuration updates |
| **Documentation** | All foundations | Index System | Generated docs |

---

## Implementation Approach

### Phase 0: Foundation Infrastructure

**Goal:** Establish the base infrastructure that all other foundations depend on.

**Deliverables:**
- Basic multi-agent orchestration
- Execution tracing and logging
- Beads integration for persistence
- GitHub MCP integration

### Phase 1: Core Capabilities

**Goal:** Deliver minimum viable versions of each foundation.

**Deliverables:**
- Basic agent types (Orchestrator, Implementer, Reviewer)
- Simple PR review pipeline (one or two specialized reviewers)
- Basic codebase analysis (file structure, imports)
- Index generator for documentation

### Phase 2: Specialized Agents

**Goal:** Add specialized capabilities to each foundation.

**Deliverables:**
- Full suite of PR review agents
- Interactive Planning Framework
- Deep codebase analysis (AST, patterns)
- Documentation drift detection

### Phase 3: Self-Improvement

**Goal:** Enable the system to improve itself.

**Deliverables:**
- Process analyzer
- LLM inefficiency analyzer
- PR Review Reviewer
- Improvement proposal pipeline

### Phase 4: Refinement

**Goal:** Optimize, harden, and scale.

**Deliverables:**
- Performance optimization
- Scalability improvements
- Advanced observability
- Cross-foundation integration polish

---

## Success Metrics

### Foundation Metrics

| Foundation | Key Metric | Target |
|------------|------------|--------|
| **Multi-Agent** | Task completion rate | >95% |
| **Interactive Development** | First-attempt success rate | >80% |
| **PR Review** | Issues caught before human review | >70% |
| **Codebase Analysis** | Analysis accuracy | >95% |
| **Documentation** | Documentation freshness (< 30 days stale) | >90% |
| **Self-Reflection** | Improvement proposals accepted | >60% |

### North Star Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| **Human Cognitive Load** | Self-reported reduction in tedious tasks | -50% |
| **Code Quality** | Defect escape rate | -30% |
| **Development Velocity** | Tasks completed per week | +25% |
| **System Improvement** | New automated checks per month | 5+ |

---

## Open Questions

### Technical

1. **Agent Communication Protocol**: How do agents share context and hand off work?
2. **State Management**: Where does shared state live? How is it synchronized?
3. **Multi-Repository Support**: How do we handle analysis across multiple repos?
4. **Language Support Prioritization**: Which languages need full vs. partial support?

### Process

1. **Rollout Strategy**: How do we introduce these capabilities incrementally?
2. **Human Training**: What training do humans need to work effectively with the system?
3. **Feedback Collection**: How do we systematically gather user feedback?
4. **Success Measurement**: How do we measure whether the system is achieving its goals?

### Strategic

1. **Build vs. Buy**: Which components should be built custom vs. using existing tools?
2. **Open Source vs. Proprietary**: Which components should be open-sourced?
3. **Multi-Tenancy**: Is this a platform for one team or many?
4. **LLM Provider Lock-in**: How dependent should we be on a single LLM provider?

---

## Related Documents

| Document | Description |
|----------|-------------|
| [A Pragmatic Guide for Software Engineering in a Post-LLM World](Pragmatic-Guide-Software-Engineering-Post-LLM-World.md) | Philosophy umbrella document |
| [LLM-First Code Reviews](../reference/llm-assisted-code-review.md) | Pillar 1 implementation guide |
| [Human-Driven, LLM-Navigated Development](Human-Driven-LLM-Navigated-Software-Development.md) | Pillar 2 philosophy |
| [Radical Self-Improvement for LLMs](Radical-Self-Improvement-for-LLMs.md) | Pillar 3 framework |

---

**Last Updated:** 2025-12-06
**Next Review:** 2026-01-06 (Monthly)

Authored-by: jib
