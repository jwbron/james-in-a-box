# ADR: Multi-Agent Pipeline Architecture

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Proposed (Not Implemented)

---

> **2025 Research Update**: This ADR has been enhanced with latest industry research and best practices:
> - [Anthropic's multi-agent system](https://www.anthropic.com/engineering/multi-agent-research-system) achieved **90% performance improvement** over single-agent
> - Multi-agent systems use **~15× more tokens** than single-agent chats - economic viability requires high-value tasks
> - **Context engineering** (clear objectives, task boundaries, termination criteria) is the #1 success factor
> - [40% of agentic AI projects](https://galileo.ai/blog/hidden-cost-of-agentic-ai) are canceled before production due to cost/complexity
> - Industry has converged on core patterns: Sequential, Parallel, Hierarchical, Consensus, Iterative

---

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Multi-Agent Architecture](#multi-agent-architecture)
- [Pipeline Patterns](#pipeline-patterns)
- [Implementation Phases](#implementation-phases)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

The current jib architecture uses a **single-agent, single-invocation pattern** for task processing. Each workflow (Slack task, PR review, check failure analysis, etc.) invokes Claude Code once with a comprehensive prompt and relies on that single invocation to:

1. Understand the full context
2. Make all decisions
3. Execute all sub-tasks
4. Generate output

This approach has several limitations:

1. **Cognitive Load:** Complex tasks require a single agent to juggle multiple concerns simultaneously (understanding requirements, analyzing code, making decisions, testing, documenting)
2. **Failure Modes:** If the agent fails partway through, all progress is lost (no checkpointing)
3. **Context Window Pressure:** All context must be loaded upfront, even if only portions are needed
4. **Quality Variance:** Single-pass execution doesn't allow for review or refinement of intermediate steps
5. **Specialization Limits:** One prompt template must handle diverse task types (analysis vs. implementation vs. review)
6. **Parallel Work Constraints:** Can't divide work across multiple agents running concurrently

**Current Implementation:**

```
Slack Task → incoming-processor.py → Claude Code (single invocation)
  ├─ Understands task
  ├─ Gathers context
  ├─ Plans approach
  ├─ Implements changes
  ├─ Tests
  ├─ Creates PR
  └─ Updates beads
```

**Industry Patterns (2025):**

Multi-agent systems have become established best practice for complex LLM workflows. Research from [Anthropic's multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) showed **over 90% performance improvement** when using Claude Opus 4 as lead agent with Claude Sonnet 4 subagents compared to single-agent setups. [Microsoft Azure](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns), [Google Cloud](https://cloud.google.com/architecture/choose-design-pattern-agentic-ai-system), and industry practitioners have standardized on core orchestration patterns:

| Pattern | Example | Benefit | When to Use |
|---------|---------|---------|-------------|
| **Sequential Pipeline** | Plan → Implement → Test → Review | Specialization, checkpointing, clear dependencies | Multi-stage processes with linear workflow |
| **Parallel/Concurrent** | Multiple PR checks simultaneously | Reduced latency (vs sequential), comprehensive coverage | Independent analyses, time-sensitive workflows |
| **Hierarchical/Delegating** | Coordinator → Specialist agents | Complex orchestration, sub-task delegation | Large tasks requiring diverse expertise |
| **Debate/Consensus** | Multiple agents propose, best chosen | Quality through diversity, reduced bias | High-stakes decisions, ambiguous requirements |
| **Tool-Specialized** | Code agent, research agent, test agent | Deep expertise per domain | Domain-specific tasks requiring specialized knowledge |
| **Iterative Refinement** | Code → Test → Fix loop (max 3 iterations) | Quality improvement, graceful failure handling | Flaky processes, quality-critical outputs |

**Key Industry Insight**: According to 2025 industry data, over 80% of enterprise workloads are expected to run on AI-driven systems by 2026, with multi-agent architectures leading this transformation.

### What We're Deciding

This ADR proposes a **multi-agent pipeline architecture** for jib where:

1. **Workflows are decomposed into stages** with clear inputs/outputs
2. **Each stage can invoke a specialized agent** with tailored prompts and context
3. **Agents can run sequentially** (with checkpointing) or **in parallel** (for throughput)
4. **Coordination logic** manages agent orchestration, state, and error handling
5. **Reusable agent templates** enable consistent patterns across workflows

### 2025 Best Practices from Industry

Based on research from [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system), [Microsoft](https://azure.microsoft.com/en-us/blog/agent-factory-the-new-era-of-agentic-ai-common-use-cases-and-design-patterns/), and [leading AI practitioners](https://collabnix.com/multi-agent-and-multi-llm-architecture-complete-guide-for-2025/), the following principles emerged as critical for successful multi-agent systems:

**1. Context Engineering (Critical Success Factor)**

Context engineering is **the #1 job of engineers building AI agents** in 2025. Anthropic's research found that early agent systems failed when agents:
- Spawned 50 subagents for simple queries (lack of task scoping)
- Scoured the web endlessly for nonexistent sources (no termination criteria)
- Distracted each other with excessive updates (poor coordination boundaries)

**Each subagent must have:**
- Clear objective and output format
- Guidance on tools and sources to use
- Explicit task boundaries (what NOT to do)
- Termination criteria

**2. Economic Viability Through Value Alignment**

[Industry data](https://medium.com/@anishnarayan09/agentic-ai-automation-optimize-efficiency-minimize-token-costs-69185687713c) shows that:
- Agents use **~4× more tokens** than chat interactions
- Multi-agent systems use **~15× more tokens** than chats
- Complex agents with tool-calling consume **5-20× more tokens** than simple chains due to loops and retries

**Rule of thumb**: Multi-agent systems require tasks where the **value of the task is high enough** to pay for increased performance and cost.

**3. When to Use Multi-Agent vs Single-Agent**

Multi-agent systems excel at:
- Tasks requiring heavy parallelization
- Information exceeding single context windows
- Interfacing with numerous complex tools
- Tasks where quality/accuracy improvements justify 15× token cost

Multi-agent systems designed for **"reading" tasks** (analysis, research) tend to be more manageable than **"writing" tasks** (code generation, content creation).

**4. Orchestration Framework Selection**

[Industry guidance](https://research.aimultiple.com/agentic-orchestration/) suggests using orchestrators when you have **3+ of**:
- State management requirements
- Branching logic
- Parallelism needs
- Multiple tools/LLMs
- Strict observability requirements

**5. State Management and Checkpointing**

[Research on checkpoint/restore systems](https://eunomia.dev/blog/2025/05/11/checkpointrestore-systems-evolution-techniques-and-applications-in-ai-agents/) and [LangGraph state machines](https://dev.to/jamesli/langgraph-state-machines-managing-complex-agent-task-flows-in-production-36f4) emphasize:
- Every agent state change should be durably checkpointed
- Agents must survive crashes and infrastructure updates
- State should enable time-travel debugging
- Centralized state management prevents conflicts

### Key Requirements

**Functional:**
1. **Backward Compatibility:** Existing single-agent workflows continue to work
2. **Incremental Adoption:** Can migrate workflows one at a time to multi-agent
3. **State Persistence:** Pipeline progress survives container restarts (Beads integration)
4. **Error Recovery:** Failed stages can retry without restarting entire pipeline
5. **Observable:** Clear visibility into which agent did what and why

**Non-Functional:**
1. **Performance:** Multi-agent should be faster or similar to single-agent (not slower)
2. **Cost-Effective:** Token usage optimized (don't load unnecessary context)
3. **Maintainable:** Pipeline definitions readable and easy to modify
4. **Extensible:** New workflows easy to build from existing agent templates

## Decision

**We will implement a multi-agent pipeline architecture with coordinated sequential and parallel agent execution, while maintaining backward compatibility with existing single-agent workflows.**

### Core Principles

1. **Workflows as Pipelines:** Complex tasks decomposed into stages with clear contracts
2. **Specialized Agents:** Each stage uses a tailored agent with focused responsibilities
3. **State as First-Class:** Pipeline state tracked in Beads for persistence and observability
4. **Fail-Safe Coordination:** Orchestrator handles retries, fallbacks, and error propagation
5. **Gradual Migration:** Existing workflows continue working; migrate selectively based on value

### Approach Summary

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| **Pipeline Definition** | Declarative workflow specification | YAML or Python DSL |
| **Pipeline Orchestrator** | Executes stages, manages state | Python framework |
| **Agent Templates** | Reusable agent prompts and configs | Jinja2 templates + Python |
| **State Manager** | Persistence and recovery | Beads integration |
| **Execution Models** | Sequential, parallel, conditional | Built-in patterns |

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Pipeline Format** | Python DSL with YAML fallback | Flexible, type-safe, debugging support, aligns with [LangGraph approach](https://latenode.com/blog/langgraph-vs-autogen-vs-crewai-complete-ai-agent-framework-comparison-architecture-analysis-2025) | Pure YAML (less expressive), pure code (verbose) |
| **Orchestration** | Custom Python framework | Lightweight, jib-specific, no external deps, control over checkpointing | Airflow (heavy), Prefect (overkill), Temporal (complex), Microsoft Agent Framework (see below) |
| **Agent Invocation** | Subprocess with timeout | Isolation, resource control, crash recovery | In-process (less isolation), containers (slow startup) |
| **State Storage** | Beads with structured notes | Already integrated, git-backed, follows [checkpoint/restore patterns](https://eunomia.dev/blog/2025/05/11/checkpointrestore-systems-evolution-techniques-and-applications-in-ai-agents/) | Separate DB (complexity), files (unstructured) |
| **Parallelism** | Process pool (multiprocessing) | Simple, reliable, bounded concurrency, follows [Azure concurrent pattern](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) | Threads (GIL), async (event loop complexity) |
| **Agent Templates** | Jinja2 + Python functions | Familiar, powerful, reusable, [context engineering focused](https://www.anthropic.com/engineering/multi-agent-research-system) | Plain strings (not reusable), pure Python (verbose) |
| **Token Optimization** | Stage-specific context loading | Reduce 5-20× token overhead, [optimize costs](https://medium.com/@anishnarayan09/agentic-ai-automation-optimize-efficiency-minimize-token-costs-69185687713c) | Load all context upfront (wasteful) |

## Multi-Agent Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Pipeline Orchestrator                      │
│                                                              │
│  ┌────────────────────────────────────────────────────┐   │
│  │           Pipeline Definition (YAML/Python)          │   │
│  │  - Stages: Plan → Implement → Test → Review         │   │
│  │  - Agents: Planner, Coder, Tester, Reviewer         │   │
│  │  - Inputs/Outputs: Context → Code → Tests → PR      │   │
│  └────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │ Stage 1 │→ │ Stage 2 │→ │ Stage 3 │→ │ Stage 4 │     │
│  │ Plan    │  │ Implement│  │  Test   │  │ Review  │     │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘     │
│       │            │            │            │             │
│       ▼            ▼            ▼            ▼             │
│  ┌─────────────────────────────────────────────────┐     │
│  │              Agent Executor                       │     │
│  │  - Loads agent template                          │     │
│  │  - Injects stage-specific context                │     │
│  │  - Invokes Claude Code (subprocess)              │     │
│  │  - Parses and validates output                   │     │
│  └─────────────────────────────────────────────────┘     │
│                                                              │
│  ┌─────────────────────────────────────────────────┐     │
│  │              State Manager (Beads)                │     │
│  │  - Pipeline status (pending/in_progress/done)    │     │
│  │  - Stage results (Plan: ADR-042, Code: 3 files) │     │
│  │  - Checkpointing and resumption                  │     │
│  └─────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### Pipeline Definition Example

**Python DSL (Preferred for Complex Workflows):**

```python
from jib.pipelines import Pipeline, Stage, Agent, ParallelStages

# Define reusable agents
planner = Agent(
    name="planner",
    template="agents/planner.jinja2",
    timeout=5 * 60,  # 5 minutes
)

implementer = Agent(
    name="implementer",
    template="agents/implementer.jinja2",
    timeout=30 * 60,  # 30 minutes
)

tester = Agent(
    name="tester",
    template="agents/tester.jinja2",
    timeout=10 * 60,
)

reviewer = Agent(
    name="reviewer",
    template="agents/reviewer.jinja2",
    timeout=5 * 60,
)

# Define pipeline
feature_implementation = Pipeline(
    name="feature_implementation",
    description="Implement a new feature from requirements to PR",

    stages=[
        Stage(
            name="analyze_requirements",
            agent=planner,
            inputs={"task_description": "input.task"},
            outputs={"plan": "plan.md", "files_to_change": "list[str]"},
        ),

        Stage(
            name="implement_changes",
            agent=implementer,
            inputs={
                "plan": "stages.analyze_requirements.outputs.plan",
                "files": "stages.analyze_requirements.outputs.files_to_change",
            },
            outputs={"changed_files": "list[str]", "commit_sha": "str"},
        ),

        ParallelStages(
            name="quality_checks",
            stages=[
                Stage(
                    name="run_tests",
                    agent=tester,
                    inputs={"changed_files": "stages.implement_changes.outputs.changed_files"},
                    outputs={"test_results": "dict", "passed": "bool"},
                ),
                Stage(
                    name="security_scan",
                    agent=Agent(name="security_scanner", template="agents/security.jinja2"),
                    inputs={"changed_files": "stages.implement_changes.outputs.changed_files"},
                    outputs={"vulnerabilities": "list", "safe": "bool"},
                ),
            ],
        ),

        Stage(
            name="create_pr",
            agent=reviewer,
            inputs={
                "commit_sha": "stages.implement_changes.outputs.commit_sha",
                "test_results": "stages.quality_checks.run_tests.outputs.test_results",
                "security_results": "stages.quality_checks.security_scan.outputs.vulnerabilities",
            },
            outputs={"pr_url": "str"},
            conditions={
                "stages.quality_checks.run_tests.outputs.passed": True,
                "stages.quality_checks.security_scan.outputs.safe": True,
            },
        ),
    ],
)
```

**YAML (Simpler Workflows):**

```yaml
name: pr_review
description: Review a pull request with multiple specialized agents

stages:
  - name: analyze_code
    agent: code_analyzer
    inputs:
      pr_number: "{{ input.pr_number }}"
      repository: "{{ input.repository }}"
    outputs:
      - issues: list
      - complexity_score: float

  - name: analyze_tests
    agent: test_analyzer
    inputs:
      pr_number: "{{ input.pr_number }}"
    outputs:
      - coverage_delta: float
      - missing_tests: list

  - name: generate_review
    agent: reviewer
    inputs:
      code_issues: "{{ stages.analyze_code.outputs.issues }}"
      test_issues: "{{ stages.analyze_tests.outputs.missing_tests }}"
    outputs:
      - review_comment: str
      - approval_status: str
```

### Agent Template Example

**Planner Agent (`agents/planner.jinja2`):**

```jinja2
# Task Planning Agent

You are a specialized planning agent. Your job is to analyze a task and create a detailed implementation plan.

## Task Description

{{ task_description }}

## Your Responsibilities

1. **Understand Requirements:** Extract functional and non-functional requirements
2. **Identify Files:** Determine which files need to be created/modified
3. **Design Approach:** Outline the implementation strategy
4. **List Dependencies:** Note any prerequisites or blockers
5. **Estimate Complexity:** Rate as simple/moderate/complex

## Output Format (JSON)

Return ONLY valid JSON with this structure:

```json
{
  "requirements": {
    "functional": ["req1", "req2"],
    "non_functional": ["perf requirement", "security requirement"]
  },
  "files_to_change": [
    {"path": "src/foo.py", "reason": "Add new function"},
    {"path": "tests/test_foo.py", "reason": "Add tests"}
  ],
  "approach": "High-level strategy here",
  "dependencies": ["ADR-042", "Redis client"],
  "complexity": "moderate",
  "estimated_stages": 3
}
```

## Context

{% if beads_context %}
### Previous Work
{{ beads_context }}
{% endif %}

{% if related_docs %}
### Related Documentation
{{ related_docs }}
{% endif %}

## Important Notes

- Focus on PLANNING only - do not implement
- Be specific about file changes
- Consider edge cases and error handling
- Output ONLY the JSON (no explanations before/after)
```

### State Management with Beads

Pipeline state is tracked in Beads using structured notes:

```python
# Pipeline creates a Beads task on start
beads_id = bd.create(
    title=f"Pipeline: {pipeline.name}",
    labels=[f"pipeline:{pipeline.name}", f"task:{task_id}"],
    description=f"Multi-agent pipeline execution for {task_description}"
)

# Each stage updates the task
bd.update(
    beads_id,
    notes=f"""
Stage: {stage.name}
Status: in_progress
Started: {timestamp}
Agent: {stage.agent.name}
Inputs: {json.dumps(stage.inputs)}
""",
    status="in_progress"
)

# On stage completion
bd.update(
    beads_id,
    notes=f"""
Stage: {stage.name}
Status: completed
Duration: {duration}s
Outputs: {json.dumps(stage.outputs)}
""",
)

# Pipeline result stored in Beads
bd.update(
    beads_id,
    notes=f"""
Pipeline: {pipeline.name}
Status: completed
Total Duration: {total_duration}s
Stages Completed: {len(completed_stages)}
Final Output: {json.dumps(final_output)}
""",
    status="closed"
)
```

**Resumption:**

```python
# On container restart or failure recovery
def resume_pipeline(beads_id):
    task = bd.show(beads_id)
    pipeline_state = parse_beads_notes(task.notes)

    # Find last completed stage
    last_stage = pipeline_state["last_completed_stage"]

    # Resume from next stage
    remaining_stages = pipeline.stages[last_stage + 1:]
    execute_stages(remaining_stages, previous_outputs=pipeline_state["outputs"])
```

## Pipeline Patterns

### Pattern 1: Sequential Specialization

**Use Case:** Feature implementation requiring multiple specialized steps

```python
Pipeline(
    stages=[
        Stage("plan", planner_agent),
        Stage("implement", coder_agent),
        Stage("test", tester_agent),
        Stage("review", reviewer_agent),
        Stage("create_pr", pr_agent),
    ]
)
```

**Benefits:**
- Each agent specialized for its task
- Clear handoff points
- Easy to debug which stage failed
- Can cache stage outputs

**When to Use:**
- Complex tasks with distinct phases
- High-value tasks where quality matters
- Tasks requiring checkpointing (long-running)

### Pattern 2: Parallel Analysis

**Use Case:** PR review with multiple independent checks

```python
Pipeline(
    stages=[
        ParallelStages(
            Stage("code_review", code_reviewer_agent),
            Stage("security_scan", security_agent),
            Stage("performance_analysis", perf_agent),
            Stage("docs_check", docs_agent),
        ),
        Stage("synthesize_review", synthesis_agent),
    ]
)
```

**Benefits:**
- Faster execution (parallel)
- Independent perspectives
- Bounded resource usage

**When to Use:**
- Multiple independent analyses needed
- Time-sensitive workflows (PR reviews)
- Resource-efficient parallelism

### Pattern 3: Conditional Branching

**Use Case:** Different paths based on task complexity

```python
Pipeline(
    stages=[
        Stage("assess_complexity", complexity_agent),
        ConditionalStage(
            condition="stages.assess_complexity.outputs.complexity == 'simple'",
            if_true=Stage("quick_implement", simple_coder_agent),
            if_false=Pipeline(stages=[
                Stage("detailed_plan", planner_agent),
                Stage("implement_with_tests", full_coder_agent),
                Stage("comprehensive_review", reviewer_agent),
            ]),
        ),
    ]
)
```

**Benefits:**
- Adaptive resource allocation
- Simpler tasks complete faster
- Complex tasks get appropriate rigor

**When to Use:**
- Variable task complexity
- Cost optimization important
- Different quality bars for different tasks

### Pattern 4: Iterative Refinement

**Use Case:** Code generation with feedback loop

```python
Pipeline(
    stages=[
        Stage("generate_code", coder_agent),
        Stage("test_code", tester_agent),
        LoopUntil(
            condition="stages.test_code.outputs.all_tests_passed",
            max_iterations=3,
            stages=[
                Stage("fix_failures", fixer_agent, inputs={
                    "code": "stages.generate_code.outputs.code",
                    "failures": "stages.test_code.outputs.failures",
                }),
                Stage("test_code", tester_agent),
            ],
        ),
        Stage("finalize", finalizer_agent),
    ]
)
```

**Benefits:**
- Quality improvement through iteration
- Handles failures gracefully
- Bounded retry attempts

**When to Use:**
- Flaky processes (tests, builds)
- Quality-critical outputs
- Self-correcting workflows

### Pattern 5: Debate/Consensus

**Use Case:** High-stakes decisions (security, architecture)

```python
Pipeline(
    stages=[
        ParallelStages(
            Stage("propose_solution_1", architect_agent_1),
            Stage("propose_solution_2", architect_agent_2),
            Stage("propose_solution_3", architect_agent_3),
        ),
        Stage("critique_all", critic_agent, inputs={
            "solutions": [
                "stages.propose_solution_1.outputs.proposal",
                "stages.propose_solution_2.outputs.proposal",
                "stages.propose_solution_3.outputs.proposal",
            ],
        }),
        Stage("select_best", selector_agent, inputs={
            "solutions": "stages.critique_all.inputs.solutions",
            "critiques": "stages.critique_all.outputs.critiques",
        }),
    ]
)
```

**Benefits:**
- Multiple perspectives
- Higher quality decisions
- Reduced bias

**When to Use:**
- High-impact decisions
- Ambiguous requirements
- Trade-offs between approaches

### Token Optimization Strategies

Given that multi-agent systems use **~15× more tokens** than single-agent chats ([source](https://medium.com/@anishnarayan09/agentic-ai-automation-optimize-efficiency-minimize-token-costs-69185687713c)), optimization is critical for economic viability.

**Key Optimization Techniques:**

1. **Stage-Specific Context Loading**
   - Load only context needed for each stage
   - Don't pass full codebase to every agent
   - Planner needs requirements; Coder needs relevant files; Tester needs test framework info

2. **Prompt Engineering**
   - [Research shows](https://adam.holter.com/ai-costs-in-2025-cheaper-tokens-pricier-workflows-why-your-bill-is-still-rising/) optimized prompts reduce token consumption 30-50%
   - Concise prompting and context pruning cut usage 40-50%
   - Each agent template should be minimal yet complete

3. **Dynamic Model Selection**
   - Use smaller models (Haiku) for simple stages (validation, formatting)
   - Reserve Opus/Sonnet for complex reasoning stages
   - Anthropic's system used Opus 4 (lead) + Sonnet 4 (subagents) for cost balance

4. **Termination Criteria**
   - Prevent agents from running indefinitely
   - Set max iterations for loops (typically 3)
   - Include explicit "done" conditions in agent prompts

5. **Modular Agent Design**
   - Break agents into smaller, specialized units
   - Reduces coordination overhead by ~20%
   - Avoids redundant tool calls and retrieval

**Measurement:**
- Track token usage per stage
- Compare multi-agent vs single-agent baselines
- Target: multi-agent should provide >2× quality improvement to justify 15× token cost

## Implementation Phases

### Phase 1: Core Framework

**Goal:** Build minimal pipeline orchestrator and prove concept

**Success Criteria:**
- Sequential pipeline execution works
- Beads state management integrated
- Single workflow migrated successfully (e.g., feature implementation)
- Observable pipeline state via Beads

**Components:**
- Pipeline DSL (Python API)
- Orchestrator (stage execution, error handling)
- State manager (Beads integration)
- Agent executor (subprocess invocation)
- 2-3 agent templates (planner, coder, reviewer)

**Deliverables:**
- `jib/pipelines/` - Core framework
- `jib/agents/` - Agent templates
- 1 working pipeline (feature_implementation)
- Tests for orchestrator
- Documentation

### Phase 2: Parallel Execution

**Goal:** Enable parallel stage execution

**Success Criteria:**
- ParallelStages executes concurrently
- Resource limits enforced (max_workers)
- Error handling for partial failures
- 1-2 workflows use parallelism (PR review, multi-repo analysis)

**Components:**
- Process pool executor
- Parallel stage coordinator
- Output aggregation
- Timeouts and cancellation

**Deliverables:**
- Parallel execution support
- 2 parallel workflows
- Performance benchmarks

### Phase 3: Advanced Patterns

**Goal:** Support conditional, iterative, and debate patterns

**Success Criteria:**
- ConditionalStage works
- LoopUntil pattern implemented
- Debate/consensus pattern works
- 3+ workflows use advanced patterns

**Components:**
- Conditional branching
- Loop constructs
- Consensus mechanisms
- Dynamic pipeline generation

**Deliverables:**
- Full pattern library
- 5+ production workflows
- Pattern cookbook

### Phase 4: Migration & Optimization

**Goal:** Migrate all high-value workflows, optimize performance

**Success Criteria:**
- All complex workflows migrated
- Token usage optimized (vs. single-agent baseline)
- Execution time competitive or better
- Developer satisfaction high

**Components:**
- Workflow migration toolkit
- Performance profiling
- Cost analysis
- Developer UX improvements

**Deliverables:**
- Migration guide
- Performance report
- Cost comparison
- Production rollout

## Consequences

### Positive

**For Development:**
- ✅ Higher quality output (specialized agents, review steps)
- ✅ Better error recovery (checkpoint and resume)
- ✅ Faster complex workflows (parallelism)
- ✅ More observable (stage-by-stage visibility)
- ✅ Easier to optimize (profile per-stage token usage)
- ✅ Reusable agents (templates shared across workflows)

**For Operations:**
- ✅ Lower cost for some workflows (load only needed context per stage)
- ✅ Better resource utilization (parallel execution)
- ✅ Easier debugging (know which stage failed)
- ✅ State persistence (survive container restarts)

**For Users:**
- ✅ More reliable task completion
- ✅ Better quality results
- ✅ Faster turnaround on some tasks
- ✅ Clearer progress updates (stage-by-stage)

### Negative / Trade-offs

**Initial Costs:**
- ⚠️ Framework development time
- ⚠️ Workflow migration effort
- ⚠️ Learning curve for new patterns
- ⚠️ More complex debugging (distributed)

**Ongoing Considerations:**
- ⚠️ Increased code complexity (orchestration logic)
- ⚠️ Potential for over-engineering (not all tasks need multi-agent)
- ⚠️ More moving parts (more failure modes)
- ⚠️ **Economic impact**: [15× token usage](https://medium.com/@anishnarayan09/agentic-ai-automation-optimize-efficiency-minimize-token-costs-69185687713c) vs single-agent; must justify with value
- ⚠️ **Industry failure rate**: [40% of agentic AI projects canceled](https://galileo.ai/blog/hidden-cost-of-agentic-ai) before production by 2027 (Gartner prediction)

**Risks:**
- ⚠️ Poor stage boundaries → worse than single-agent
- ⚠️ Over-specialization → context loss between stages
- ⚠️ Coordination bugs hard to debug
- ⚠️ Performance regression if parallelism poorly tuned

**Mitigations:**
- Maintain single-agent as fallback
- Measure token usage per workflow (optimize or revert)
- Comprehensive logging and observability
- Clear guidelines on when to use multi-agent vs. single-agent
- Gradual rollout with A/B comparison

## Decision Permanence

**Reversible Decisions (Low Cost to Change):**
- Pipeline DSL syntax (Python vs. YAML)
- Agent template format (Jinja2 vs. other)
- Specific workflow definitions
- Execution timeouts and resource limits
- Parallelism strategy (process vs. thread)

**Semi-Permanent (Moderate Cost to Change):**
- Core orchestrator design
- Beads state schema
- Agent invocation mechanism (subprocess vs. other)
- Error handling strategy
- Pattern library structure

**Permanent (High Cost to Change):**
- Multi-agent philosophy (vs. single-agent)
- State persistence requirement (Beads integration)
- Backward compatibility promise
- Observable pipeline execution

**Review Cadence:**
- **Weekly:** Workflow performance metrics, token usage
- **Monthly:** Pattern effectiveness, developer feedback
- **Quarterly:** Architecture assessment, migration progress
- **Annually:** Strategic review of multi-agent approach

## Alternatives Considered

### Alternative 1: Stay with Single-Agent

**Approach:** Keep current architecture, improve prompts and context

**Pros:**
- No new complexity
- No migration effort
- Simpler to understand
- Lower maintenance burden

**Cons:**
- Doesn't address core limitations (context overload, no checkpointing, no specialization)
- Quality ceiling lower
- No parallelism benefits
- State management still ad-hoc

**Rejected Because:** Incremental improvements won't solve fundamental limitations. Multi-agent enables qualitatively better capabilities.

### Alternative 2: External Orchestration (Airflow, Prefect, Temporal)

**Approach:** Use existing workflow orchestration framework

**Pros:**
- Battle-tested
- Rich feature set (UI, monitoring, retries)
- Community support
- Mature tooling

**Cons:**
- Heavy dependencies (databases, web UI, scheduler)
- Over-engineered for jib's needs
- Complex setup and maintenance
- Not designed for LLM workflows (no agent-specific features)
- Learning curve for team

**Rejected Because:** Too much infrastructure for jib's scale. Custom lightweight solution better fits needs and constraints.

### Alternative 3: Agentic Framework (LangGraph, CrewAI, AutoGen, Microsoft Agent Framework)

**Approach:** Use purpose-built multi-agent LLM framework

Based on [comprehensive 2025 framework comparison](https://latenode.com/blog/langgraph-vs-autogen-vs-crewai-complete-ai-agent-framework-comparison-architecture-analysis-2025):

**Framework Characteristics:**

| Framework | Strengths | Weaknesses |
|-----------|-----------|------------|
| **LangGraph** | Graph-based architecture, sophisticated orchestration, fine-grained state management | Rigid state (defined upfront), steeper learning curve |
| **CrewAI** | Intuitive role-based design, fast iteration, YAML-driven simplicity | Logging challenges, less flexible for dynamic workflows |
| **AutoGen** | Conversational architecture, research-grade flexibility, LLM-to-LLM collaboration | Procedural code style, verbosity, no DAG support |
| **Microsoft Agent Framework** | [Enterprise-grade](https://azure.microsoft.com/en-us/blog/introducing-microsoft-agent-framework/), converges AutoGen + Semantic Kernel, built-in observability/durability | Public preview (new), enterprise focus, potential complexity |

**Pros:**
- Designed for LLM agents
- Built-in patterns (sequential, parallel, hierarchical)
- Active development and community examples
- Microsoft Agent Framework offers [durability and checkpointing](https://techcommunity.microsoft.com/blog/appsonazureblog/bulletproof-agents-with-the-durable-task-extension-for-microsoft-agent-framework/4467122)

**Cons:**
- External dependency (increase complexity)
- Abstractions may not fit jib's needs (Beads, Claude Code specifics, container isolation)
- Migration effort still required
- Less control over orchestration details
- LangGraph: demands higher upfront investment
- CrewAI: logging difficulties ("huge pain" according to practitioners)
- AutoGen: code readability drops as network complexity grows
- Microsoft Agent Framework: public preview, unproven stability

**Rejected Because:**
- Prefer to own orchestration logic for jib-specific needs (Beads integration, Claude Code specifics, container isolation)
- Custom solution provides better control over checkpointing strategy
- Can adopt or integrate framework patterns later if custom solution proves insufficient
- [Context engineering](https://www.anthropic.com/engineering/multi-agent-research-system) requirements are jib-specific
- Frameworks add dependency overhead for features we can build more simply

### Alternative 4: Agent Mesh (Fully Autonomous Collaboration)

**Approach:** Agents discover and collaborate without central orchestration

**Pros:**
- Maximum flexibility
- Emergent behavior
- Self-organizing

**Cons:**
- Unpredictable outcomes
- Hard to debug
- No clear ownership
- Coordination overhead high
- State management complex

**Rejected Because:** Too experimental for production use. Need deterministic, observable workflows.

### Alternative 5: Hybrid (Single-Agent + Multi-Agent)

**Approach:** Use single-agent for simple tasks, multi-agent for complex

**Pros:**
- Best of both worlds
- Gradual adoption
- Right-sized complexity
- Cost-effective

**Cons:**
- Two systems to maintain
- When to use which?
- Potential confusion

**Accepted:** This is actually the chosen approach - backward compatibility with single-agent, selective migration to multi-agent.

## References

### Internal Documentation
- [ADR: Autonomous Software Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) - Core jib architecture
- [ADR: LLM Documentation Index Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md) - Multi-agent doc generation example

### Industry Research & Best Practices (2025)
- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) - 90% performance improvement with multi-agent
- [Multi-Agent and Multi-LLM Architecture: Complete Guide for 2025](https://collabnix.com/multi-agent-and-multi-llm-architecture-complete-guide-for-2025/)
- [Microsoft Azure: AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) - Sequential, concurrent, group chat patterns
- [Microsoft: Agent Factory - Agentic AI Design Patterns](https://azure.microsoft.com/en-us/blog/agent-factory-the-new-era-of-agentic-ai-common-use-cases-and-design-patterns/)
- [Google Cloud: Choose a design pattern for your agentic AI system](https://cloud.google.com/architecture/choose-design-pattern-agentic-ai-system)
- [LangChain: How and when to build multi-agent systems](https://blog.langchain.com/how-and-when-to-build-multi-agent-systems/)

### Economic & Cost Optimization
- [Agentic AI Automation: Optimize Efficiency, Minimize Token Costs](https://medium.com/@anishnarayan09/agentic-ai-automation-optimize-efficiency-minimize-token-costs-69185687713c)
- [AI Costs in 2025: Cheaper Tokens, Pricier Workflows](https://adam.holter.com/ai-costs-in-2025-cheaper-tokens-pricier-workflows-why-your-bill-is-still-rising/)
- [The Hidden Costs of Agentic AI](https://galileo.ai/blog/hidden-cost-of-agentic-ai) - 40% of projects fail before production

### State Management & Checkpointing
- [Checkpoint/Restore Systems: Evolution and Applications in AI Agents](https://eunomia.dev/blog/2025/05/11/checkpointrestore-systems-evolution-techniques-and-applications-in-ai-agents/)
- [Bulletproof agents with durable task extension](https://techcommunity.microsoft.com/blog/appsonazureblog/bulletproof-agents-with-the-durable-task-extension-for-microsoft-agent-framework/4467122)
- [LangGraph State Machines: Managing Complex Agent Task Flows in Production](https://dev.to/jamesli/langgraph-state-machines-managing-complex-agent-task-flows-in-production-36f4)
- [Multi-Agent AI Failure Recovery That Actually Works](https://galileo.ai/blog/multi-agent-ai-system-failure-recovery)

### Framework Comparisons
- [LangGraph vs AutoGen vs CrewAI: Complete Comparison 2025](https://latenode.com/blog/langgraph-vs-autogen-vs-crewai-complete-ai-agent-framework-comparison-architecture-analysis-2025)
- [A Detailed Comparison of Top 6 AI Agent Frameworks in 2025](https://www.turing.com/resources/ai-agent-frameworks)
- [Comparing Open-Source AI Agent Frameworks](https://langfuse.com/blog/2025-03-19-ai-agent-comparison)
- [Microsoft Agent Framework](https://azure.microsoft.com/en-us/blog/introducing-microsoft-agent-framework/) - Converges AutoGen + Semantic Kernel

### Orchestration Patterns
- [9 Agentic AI Workflow Patterns Transforming AI Agents in 2025](https://www.marktechpost.com/2025/08/09/9-agentic-ai-workflow-patterns-transforming-ai-agents-in-2025/)
- [Top 10+ Agentic Orchestration Frameworks & Tools](https://research.aimultiple.com/agentic-orchestration/)
- [Agent Orchestration Patterns: Linear and Adaptive Approaches](https://www.getdynamiq.ai/post/agent-orchestration-patterns-in-multi-agent-systems-linear-and-adaptive-approaches-with-dynamiq)

### Legacy References
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph) - Graph-based multi-agent patterns
- [CrewAI](https://github.com/joaomdmoura/crewAI) - Role-based agent orchestration
- [AutoGen](https://microsoft.github.io/autogen/) - Original Microsoft research multi-agent framework
- [Temporal Workflows](https://temporal.io/) - Distributed workflow orchestration

---

**Last Updated:** 2025-11-30
**Next Review:** 2025-12-30 (Monthly)
**Status:** Proposed (Not Implemented)
