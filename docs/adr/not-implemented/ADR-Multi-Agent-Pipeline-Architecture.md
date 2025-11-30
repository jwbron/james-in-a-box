# ADR: Multi-Agent Pipeline Architecture

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Proposed (Not Implemented)

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

**Industry Patterns:**

Multi-agent systems are emerging as best practice for complex LLM workflows:

| Pattern | Example | Benefit |
|---------|---------|---------|
| **Sequential Pipeline** | Plan → Implement → Test → Review | Specialization, checkpointing |
| **Parallel Execution** | Multiple PRs reviewed concurrently | Throughput, resource utilization |
| **Hierarchical** | Coordinator → Specialist agents | Complex orchestration, sub-task delegation |
| **Debate/Consensus** | Multiple agents propose, best chosen | Quality through diversity |
| **Tool-Specialized** | Code agent, research agent, test agent | Deep expertise per domain |

### What We're Deciding

This ADR proposes a **multi-agent pipeline architecture** for jib where:

1. **Workflows are decomposed into stages** with clear inputs/outputs
2. **Each stage can invoke a specialized agent** with tailored prompts and context
3. **Agents can run sequentially** (with checkpointing) or **in parallel** (for throughput)
4. **Coordination logic** manages agent orchestration, state, and error handling
5. **Reusable agent templates** enable consistent patterns across workflows

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
| **Pipeline Format** | Python DSL with YAML fallback | Flexible, type-safe, debugging support | Pure YAML (less expressive), pure code (verbose) |
| **Orchestration** | Custom Python framework | Lightweight, jib-specific, no external deps | Airflow (heavy), Prefect (overkill), Temporal (complex) |
| **Agent Invocation** | Subprocess with timeout | Isolation, resource control | In-process (less isolation), containers (slow) |
| **State Storage** | Beads with structured notes | Already integrated, git-backed | Separate DB (complexity), files (unstructured) |
| **Parallelism** | Process pool (multiprocessing) | Simple, reliable, bounded concurrency | Threads (GIL), async (event loop complexity) |
| **Agent Templates** | Jinja2 + Python functions | Familiar, powerful, reusable | Plain strings (not reusable), pure Python (verbose) |

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
- ⚠️ Token usage could increase for simple tasks (overhead)

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

### Alternative 3: Agentic Framework (LangGraph, CrewAI, AutoGen)

**Approach:** Use purpose-built multi-agent LLM framework

**Pros:**
- Designed for LLM agents
- Built-in patterns (sequential, parallel, hierarchical)
- Active development
- Community examples

**Cons:**
- External dependency
- Abstractions may not fit jib's needs
- Migration effort still required
- Less control over orchestration
- Potential vendor lock-in

**Rejected Because:** Prefer to own orchestration logic for jib-specific needs (Beads integration, Claude Code specifics, container isolation). Can adopt framework later if custom solution proves insufficient.

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

- [ADR: Autonomous Software Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) - Core jib architecture
- [ADR: LLM Documentation Index Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md) - Multi-agent doc generation example
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph) - Multi-agent patterns
- [CrewAI](https://github.com/joaomdmoura/crewAI) - Role-based agent orchestration
- [AutoGen](https://microsoft.github.io/autogen/) - Microsoft's multi-agent framework
- [Temporal Workflows](https://temporal.io/) - Distributed workflow orchestration
- [BMAD Method](https://github.com/mshumer/ai-researcher) - AI-driven development with specialized agents

---

**Last Updated:** 2025-11-30
**Next Review:** 2025-12-30 (Monthly)
**Status:** Proposed (Not Implemented)
