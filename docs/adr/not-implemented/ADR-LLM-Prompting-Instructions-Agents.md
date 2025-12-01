# ADR: LLM Prompting, Instructions, and Agent Design

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Tyler Burleigh, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** December 2025
**Status:** Proposed (Not Implemented)

---

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Context Engineering Principles](#context-engineering-principles)
- [Prompt Architecture](#prompt-architecture)
- [Agent Design Patterns](#agent-design-patterns)
- [Multi-Agent Orchestration](#multi-agent-orchestration)
- [Review and Feedback Loops](#review-and-feedback-loops)
- [Model Selection Strategy](#model-selection-strategy)
- [Implementation Phases](#implementation-phases)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

As LLM-powered agents become central to software engineering workflows, the quality of outputs depends heavily on how instructions, context, and prompts are structured. Without systematic approaches to prompt engineering and agent design:

1. **Inconsistent Outputs:** Similar tasks yield varying quality depending on how they're framed
2. **Context Overload:** Agents receive too much irrelevant information, degrading performance
3. **Missed Requirements:** Critical context not included leads to incomplete solutions
4. **Wasted Tokens:** Poor prompt design increases costs without improving quality
5. **Unreliable Agents:** Agents without clear boundaries make unpredictable decisions
6. **Review Bottlenecks:** Single-pass generation without review stages produces lower quality

**Industry Context (2025):**

Context engineering has emerged as **the #1 job of engineers building AI agents** according to Anthropic's research. Key findings:

| Challenge | Impact | Solution |
|-----------|--------|----------|
| Agents spawn 50 subagents for simple queries | Resource waste, confusion | Clear task scoping |
| Endless web searches for nonexistent sources | Timeout failures | Explicit termination criteria |
| Agents distract each other with updates | Coordination overhead | Communication boundaries |
| Context window pressure | Degraded reasoning | Stage-specific context loading |

**Current State in jib:**

james-in-a-box currently uses:
- `CLAUDE.md` as primary instruction source (comprehensive but monolithic)
- `.claude/rules/` for agent behavior rules (modular but not specialized)
- `.claude/commands/` for slash commands (utility functions)
- Single-agent pattern for most workflows (no orchestration)
- Human review as only quality gate (no automated review stages)

### What We're Deciding

This ADR establishes standards for:

1. **Context Engineering:** How to select, structure, and deliver context to agents
2. **Prompt Architecture:** Layered prompt design with clear responsibilities
3. **Agent Design Patterns:** Templates for specialized agents with bounded responsibilities
4. **Multi-Agent Orchestration:** Coordination patterns for complex workflows
5. **Review and Feedback Loops:** Quality assurance through iterative refinement
6. **Model Selection:** Matching model capabilities to task requirements

### Key Requirements

**Functional:**
1. **Reproducible Quality:** Same task types should yield consistent quality
2. **Context Efficiency:** Agents receive minimal necessary context per stage
3. **Clear Agent Boundaries:** Each agent knows what it should and shouldn't do
4. **Quality Gates:** Automated review stages before human review
5. **Graceful Degradation:** System handles failures without losing progress

**Non-Functional:**
1. **Token Efficiency:** Minimize token usage while maintaining quality
2. **Maintainability:** Prompts and agents are easy to understand and modify
3. **Observability:** Clear visibility into prompt construction and agent decisions
4. **Extensibility:** Easy to add new agent types and workflows

## Decision

**We will implement a layered prompt architecture with specialized agent templates, context engineering guidelines, and multi-agent orchestration patterns.**

### Core Principles

1. **Context Engineering First:** Context selection is more important than prompt wording
2. **Specialization Over Generalization:** Purpose-built agents outperform general-purpose ones
3. **Pull Don't Push:** Agents request context as needed rather than receiving all upfront
4. **Review as a Stage:** Quality gates are workflow stages, not afterthoughts
5. **Bounded Autonomy:** Clear limits on what each agent can and cannot do

### Approach Summary

| Component | Purpose | Location |
|-----------|---------|----------|
| **Context Selection Rules** | Define what context each agent needs | `.claude/context/` |
| **Prompt Templates** | Jinja2 templates for consistent prompting | `.claude/templates/` |
| **Agent Definitions** | Specialized agent configurations | `.claude/agents/` |
| **Orchestration Patterns** | Multi-agent workflow definitions | `.claude/pipelines/` |
| **Review Criteria** | Automated quality assessment rules | `.claude/review/` |

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Prompt Format** | Jinja2 templates | Reusable, composable, testable | Plain text (not reusable), Python strings (verbose) |
| **Context Delivery** | Stage-specific loading | Token efficiency, focused reasoning | All-upfront (overload), on-demand API (latency) |
| **Agent Specialization** | Role-based templates | Clear responsibilities, consistent outputs | General-purpose (inconsistent), task-specific (not reusable) |
| **Review Integration** | Pipeline stage | Systematic, automated | Post-hoc only (reactive), none (quality issues) |
| **Model Selection** | Task-complexity based | Cost optimization, capability matching | Single model (expensive), random (unpredictable) |

## Context Engineering Principles

### The Context Hierarchy

Context should be layered based on scope and relevance:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Context Hierarchy                            │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 1: PERMANENT CONTEXT (Always Included)                 │ │
│  │                                                               │ │
│  │ - Agent identity and role                                    │ │
│  │ - Organization standards (Khan Academy values)               │ │
│  │ - Security boundaries (what NOT to do)                       │ │
│  │ - Output format requirements                                 │ │
│  │                                                               │ │
│  │ Size: ~500-1000 tokens                                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 2: WORKFLOW CONTEXT (Per Pipeline)                     │ │
│  │                                                               │ │
│  │ - Pipeline goal and current stage                            │ │
│  │ - Previous stage outputs (summaries, not raw)                │ │
│  │ - Relevant ADRs and standards                                │ │
│  │ - Quality criteria for this workflow                         │ │
│  │                                                               │ │
│  │ Size: ~1000-3000 tokens                                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 3: TASK CONTEXT (Per Stage)                            │ │
│  │                                                               │ │
│  │ - Specific files to read/modify                              │ │
│  │ - Test requirements                                          │ │
│  │ - Related code examples                                      │ │
│  │ - Error messages or failure context                          │ │
│  │                                                               │ │
│  │ Size: Variable (loaded on-demand)                            │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Layer 4: DYNAMIC CONTEXT (On-Demand)                         │ │
│  │                                                               │ │
│  │ - Tool outputs (file reads, command results)                 │ │
│  │ - External data (API responses, web searches)                │ │
│  │ - User clarifications                                        │ │
│  │ - Error recovery information                                 │ │
│  │                                                               │ │
│  │ Size: As needed                                              │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Context Selection Guidelines

**What to Include:**

| Context Type | When to Include | How to Include |
|--------------|-----------------|----------------|
| **Requirements** | Always | Summarized, not raw JIRA |
| **Relevant Files** | When modifying | Full content or key sections |
| **Test Patterns** | When writing tests | Examples from same codebase |
| **ADRs** | For architectural work | Relevant decisions only |
| **Error Messages** | When debugging | Full stack trace + context |
| **Previous Decisions** | Multi-stage workflows | Summary from prior stages |

**What to Exclude:**

| Context Type | Why Exclude | Alternative |
|--------------|-------------|-------------|
| **Entire codebase** | Overwhelms reasoning | Targeted file loading |
| **Historical discussions** | Noise | Summarized decisions |
| **Unrelated ADRs** | Distraction | Index-based lookup |
| **Raw API responses** | Token waste | Parsed, relevant fields |
| **Sensitive data** | Security risk | Redacted or excluded |

### Context Compression Techniques

**1. Summarization Before Inclusion:**

```python
# Bad: Include entire JIRA ticket
context["jira"] = full_ticket_json  # 5000 tokens

# Good: Extract relevant fields
context["requirements"] = {
    "summary": ticket.summary,  # 50 tokens
    "acceptance_criteria": extract_criteria(ticket),  # 200 tokens
    "priority": ticket.priority,  # 10 tokens
}
```

**2. Progressive Disclosure:**

```python
# Stage 1: Planning - high-level only
context["codebase"] = get_file_tree()  # Structure, not content

# Stage 2: Implementation - targeted files
context["files"] = read_files(plan.files_to_modify)  # Only needed files

# Stage 3: Testing - test patterns
context["test_examples"] = get_similar_tests(plan.component)  # Relevant tests
```

**3. Reference Instead of Inline:**

```markdown
# Bad: Inline entire document
Here is our security policy: [5000 words of security docs]

# Good: Reference with summary
Security Policy: See ~/context-sync/confluence/security-policy.md
Key points for this task:
- Authentication: OAuth2 required for all endpoints
- Data: No PII in logs
- Validation: Input validation required
```

### Termination Criteria

Every agent must have explicit stopping conditions:

```yaml
agent:
  name: code_researcher
  termination_criteria:
    success:
      - "Found relevant code examples"
      - "Identified all files to modify"
      - "Confirmed no blocking dependencies"
    failure:
      - "No relevant code found after 3 search attempts"
      - "Circular dependency detected"
      - "Required file not found in codebase"
    timeout:
      max_duration: "5 minutes"
      max_tool_calls: 20
```

## Prompt Architecture

### Layered Prompt Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                      Prompt Composition                          │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ SYSTEM PROMPT (Identity Layer)                               │ │
│  │                                                               │ │
│  │ You are {agent_name}, a specialized agent for {purpose}.     │ │
│  │                                                               │ │
│  │ Core Behaviors:                                               │ │
│  │ - {behavior_1}                                               │ │
│  │ - {behavior_2}                                               │ │
│  │                                                               │ │
│  │ You MUST NOT:                                                │ │
│  │ - {constraint_1}                                             │ │
│  │ - {constraint_2}                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ CONTEXT BLOCK (Information Layer)                            │ │
│  │                                                               │ │
│  │ ## Task Context                                               │ │
│  │ {task_description}                                           │ │
│  │                                                               │ │
│  │ ## Available Information                                      │ │
│  │ {structured_context}                                         │ │
│  │                                                               │ │
│  │ ## Previous Stage Results                                     │ │
│  │ {prior_outputs}                                              │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ INSTRUCTION BLOCK (Action Layer)                             │ │
│  │                                                               │ │
│  │ ## Your Task                                                  │ │
│  │ {specific_instruction}                                       │ │
│  │                                                               │ │
│  │ ## Expected Output                                            │ │
│  │ {output_format}                                              │ │
│  │                                                               │ │
│  │ ## Quality Criteria                                           │ │
│  │ {success_criteria}                                           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ EXAMPLE BLOCK (Optional - Demonstration Layer)               │ │
│  │                                                               │ │
│  │ ## Example Input                                              │ │
│  │ {example_input}                                              │ │
│  │                                                               │ │
│  │ ## Example Output                                             │ │
│  │ {example_output}                                             │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Prompt Template Example

**Planner Agent Template (`templates/planner.jinja2`):**

```jinja2
{# System Prompt #}
You are the Planning Agent for james-in-a-box.

Your role is to analyze requirements and create actionable implementation plans.

## Core Behaviors
- Break complex tasks into discrete, testable steps
- Identify all files that need modification
- Estimate complexity (simple/moderate/complex)
- Flag risks and dependencies
- Consider edge cases and error scenarios

## You MUST NOT
- Write any code (planning only)
- Make architectural decisions without ADR references
- Skip the complexity assessment
- Ignore existing patterns in the codebase

{# Context Block #}
## Task Description
{{ task_description }}

## Codebase Structure
{{ codebase_summary }}

{% if related_adrs %}
## Relevant ADRs
{% for adr in related_adrs %}
- {{ adr.title }}: {{ adr.summary }}
{% endfor %}
{% endif %}

{% if beads_context %}
## Previous Work Context
{{ beads_context }}
{% endif %}

{# Instruction Block #}
## Your Task

Analyze the task description and create a detailed implementation plan.

## Expected Output

Return a JSON object with this structure:

```json
{
  "summary": "One-sentence summary of the plan",
  "complexity": "simple|moderate|complex",
  "phases": [
    {
      "name": "Phase name",
      "description": "What this phase accomplishes",
      "files_to_modify": ["path/to/file.py"],
      "dependencies": ["ADR-042", "existing-auth-module"],
      "risks": ["Risk description"],
      "success_criteria": ["Testable criteria"]
    }
  ],
  "total_files": 5,
  "estimated_tests": 12,
  "blockers": ["Any blocking issues identified"]
}
```

## Quality Criteria
- [ ] All acceptance criteria from task are addressed
- [ ] File paths are accurate (verify with codebase structure)
- [ ] Complexity rating justified
- [ ] Risks are specific and actionable
- [ ] Success criteria are testable
```

### Prompt Composition Engine

```python
class PromptComposer:
    """Composes prompts from templates and context."""

    def __init__(self, template_dir: str = ".claude/templates"):
        self.env = Environment(loader=FileSystemLoader(template_dir))

    def compose(
        self,
        agent_type: str,
        task_context: dict,
        workflow_context: Optional[dict] = None,
        examples: Optional[list] = None,
    ) -> str:
        """Compose a complete prompt from layers."""

        # Load agent template
        template = self.env.get_template(f"{agent_type}.jinja2")

        # Build context hierarchy
        context = {
            # Layer 1: Permanent context (from agent definition)
            **self.load_agent_defaults(agent_type),

            # Layer 2: Workflow context
            **(workflow_context or {}),

            # Layer 3: Task context
            **task_context,

            # Layer 4: Examples (optional)
            "examples": examples or [],
        }

        return template.render(**context)

    def load_agent_defaults(self, agent_type: str) -> dict:
        """Load permanent context for agent type."""
        config_path = f".claude/agents/{agent_type}.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)
```

## Agent Design Patterns

### Agent Types and Responsibilities

| Agent Type | Purpose | Inputs | Outputs | Constraints |
|------------|---------|--------|---------|-------------|
| **Planner** | Analyze requirements, create plans | Task description, codebase summary | Implementation plan (JSON) | No code writing |
| **Implementer** | Write code per plan | Plan, target files | Code changes, commits | Follow plan exactly |
| **Tester** | Write and run tests | Changed files, test patterns | Test code, results | No production code |
| **Reviewer** | Evaluate code quality | Code changes, standards | Review comments, score | No modifications |
| **Fixer** | Resolve failures | Error logs, failing code | Fix commits | Minimal changes |
| **Documenter** | Write documentation | Code, API specs | Docs, READMEs | No code changes |

### Agent Definition Schema

```yaml
# .claude/agents/implementer.yaml
name: implementer
version: "1.0"
description: "Writes code based on implementation plans"

identity:
  role: "Code Implementation Agent"
  persona: "A senior engineer who writes clean, tested code"

capabilities:
  tools:
    - read_file
    - write_file
    - run_command
    - git_commit
  permissions:
    - modify_code: true
    - run_tests: true
    - create_commits: true
    - push_code: false  # Human must push
    - modify_config: false

constraints:
  must_not:
    - "Deviate from the provided plan"
    - "Skip writing tests"
    - "Introduce new dependencies without plan approval"
    - "Make architectural changes beyond plan scope"
  must:
    - "Follow existing code patterns"
    - "Include error handling"
    - "Write descriptive commit messages"
    - "Update related documentation"

context_requirements:
  required:
    - implementation_plan
    - target_files
    - test_patterns
  optional:
    - related_tests
    - style_guide
    - error_handling_patterns

output_format:
  type: structured
  schema:
    changed_files: "list[str]"
    commit_shas: "list[str]"
    tests_written: "list[str]"
    documentation_updated: "bool"

quality_criteria:
  - "All plan phases completed"
  - "Tests pass locally"
  - "No linter errors"
  - "Commits are atomic and well-described"

termination:
  success:
    - "All planned changes implemented"
    - "Tests pass"
  failure:
    - "Cannot resolve merge conflicts"
    - "Tests fail after 3 fix attempts"
    - "Blocked by missing dependency"
  timeout:
    max_duration: "30 minutes"
    max_iterations: 5
```

### Agent Template Inheritance

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Template Hierarchy                      │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ BASE AGENT (base.yaml)                                       │ │
│  │                                                               │ │
│  │ - Organization standards (Khan Academy)                      │ │
│  │ - Security constraints (no credentials)                      │ │
│  │ - Communication style (concise, technical)                   │ │
│  │ - Error handling patterns                                    │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                             │                                     │
│            ┌────────────────┼────────────────┐                   │
│            │                │                │                    │
│            ▼                ▼                ▼                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ READING     │  │ WRITING     │  │ REVIEWING   │              │
│  │ AGENTS      │  │ AGENTS      │  │ AGENTS      │              │
│  │             │  │             │  │             │              │
│  │ - Planner   │  │ - Implmtr   │  │ - Reviewer  │              │
│  │ - Researcher│  │ - Tester    │  │ - Auditor   │              │
│  │ - Analyzer  │  │ - Fixer     │  │ - Validator │              │
│  │             │  │ - Documtr   │  │             │              │
│  │ Read-only   │  │ Read-write  │  │ Read-only   │              │
│  │ tools       │  │ tools       │  │ + scoring   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### Specialized Agent Examples

**Researcher Agent (Reading):**

```yaml
name: researcher
extends: base
category: reading

identity:
  role: "Research Agent"
  persona: "A thorough investigator who finds relevant information"

capabilities:
  tools:
    - read_file
    - glob_search
    - grep_search
    - web_search
  permissions:
    - modify_code: false
    - run_tests: false

termination:
  success:
    - "Found sufficient relevant information"
    - "Identified all related files"
  failure:
    - "No relevant information after exhaustive search"
    - "Information contradictory, needs human input"
```

**Reviewer Agent (Reviewing):**

```yaml
name: reviewer
extends: base
category: reviewing

identity:
  role: "Code Review Agent"
  persona: "A constructive critic focused on code quality"

capabilities:
  tools:
    - read_file
    - git_diff
  permissions:
    - modify_code: false
    - post_comments: true

output_format:
  type: review
  schema:
    overall_score: "1-5"
    summary: "string"
    issues:
      - severity: "critical|major|minor|suggestion"
        file: "string"
        line: "int"
        message: "string"
        suggestion: "string"
    approved: "bool"

quality_criteria:
  - "All critical issues must be flagged"
  - "Suggestions are actionable"
  - "Feedback is constructive, not dismissive"
```

## Multi-Agent Orchestration

### Pipeline Patterns

Building on the [Multi-Agent Pipeline Architecture ADR](./ADR-Multi-Agent-Pipeline-Architecture.md), this section defines specific orchestration patterns for common workflows.

**Pattern 1: Plan-Review-Implement (Standard Feature)**

```
┌─────────────────────────────────────────────────────────────────┐
│                Plan-Review-Implement Pipeline                    │
│                                                                   │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐     │
│  │ Planner │───▶│ Plan    │───▶│Implementer│───▶│ Impl    │     │
│  │         │    │ Reviewer│    │         │    │ Reviewer│     │
│  └─────────┘    └────┬────┘    └─────────┘    └────┬────┘     │
│                      │                              │           │
│                      ▼                              ▼           │
│               [Plan Approved?]              [Code Approved?]    │
│                 /        \                    /        \        │
│               Yes         No                Yes         No      │
│                │           │                 │           │      │
│                ▼           ▼                 ▼           ▼      │
│           [Continue]  [Revise Plan]     [Create PR]  [Fix Code] │
│                           │                              │      │
│                           └──────────────────────────────┘      │
│                                (max 3 iterations)               │
└─────────────────────────────────────────────────────────────────┘
```

```python
plan_review_implement = Pipeline(
    name="plan_review_implement",
    stages=[
        Stage(
            name="plan",
            agent="planner",
            inputs={"task": "input.task_description"},
            outputs={"plan": "json"},
        ),
        Stage(
            name="plan_review",
            agent="plan_reviewer",
            inputs={"plan": "stages.plan.outputs.plan"},
            outputs={"approved": "bool", "feedback": "str"},
        ),
        ConditionalLoop(
            name="plan_refinement",
            condition="not stages.plan_review.outputs.approved",
            max_iterations=2,
            stages=[
                Stage(
                    name="revise_plan",
                    agent="planner",
                    inputs={
                        "original_plan": "stages.plan.outputs.plan",
                        "feedback": "stages.plan_review.outputs.feedback",
                    },
                ),
                Stage(
                    name="re_review_plan",
                    agent="plan_reviewer",
                    inputs={"plan": "stages.revise_plan.outputs.plan"},
                ),
            ],
        ),
        Stage(
            name="implement",
            agent="implementer",
            inputs={"plan": "stages.plan.outputs.plan"},
            outputs={"changed_files": "list", "commits": "list"},
            conditions={"stages.plan_review.outputs.approved": True},
        ),
        Stage(
            name="impl_review",
            agent="code_reviewer",
            inputs={
                "plan": "stages.plan.outputs.plan",
                "changes": "stages.implement.outputs.changed_files",
            },
            outputs={"approved": "bool", "issues": "list"},
        ),
        ConditionalLoop(
            name="fix_issues",
            condition="not stages.impl_review.outputs.approved",
            max_iterations=3,
            stages=[
                Stage(
                    name="fix",
                    agent="fixer",
                    inputs={"issues": "stages.impl_review.outputs.issues"},
                ),
                Stage(
                    name="re_review",
                    agent="code_reviewer",
                    inputs={"changes": "stages.fix.outputs.changed_files"},
                ),
            ],
        ),
        Stage(
            name="create_pr",
            agent="pr_creator",
            inputs={
                "plan": "stages.plan.outputs.plan",
                "changes": "stages.implement.outputs.changed_files",
            },
            conditions={"stages.impl_review.outputs.approved": True},
        ),
    ],
)
```

**Pattern 2: Parallel Analysis (PR Review)**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Parallel Analysis Pipeline                    │
│                                                                   │
│                      ┌─────────────┐                             │
│                      │   PR Data   │                             │
│                      │   Loader    │                             │
│                      └──────┬──────┘                             │
│                             │                                     │
│          ┌──────────────────┼──────────────────┐                 │
│          │                  │                  │                  │
│          ▼                  ▼                  ▼                  │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐        │
│  │ Code Quality  │  │ Security      │  │ Test Coverage │        │
│  │ Analyzer      │  │ Scanner       │  │ Analyzer      │        │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘        │
│          │                  │                  │                  │
│          └──────────────────┼──────────────────┘                 │
│                             │                                     │
│                             ▼                                     │
│                    ┌───────────────┐                             │
│                    │   Review      │                             │
│                    │   Synthesizer │                             │
│                    └───────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

**Pattern 3: Consensus Decision (Architecture)**

```
┌─────────────────────────────────────────────────────────────────┐
│                   Consensus Decision Pipeline                    │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Problem Statement                         │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                             │                                     │
│          ┌──────────────────┼──────────────────┐                 │
│          │                  │                  │                  │
│          ▼                  ▼                  ▼                  │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐        │
│  │  Architect 1  │  │  Architect 2  │  │  Architect 3  │        │
│  │  (Simplicity) │  │  (Scalability)│  │  (Security)   │        │
│  │               │  │               │  │               │        │
│  │  Proposes     │  │  Proposes     │  │  Proposes     │        │
│  │  Solution A   │  │  Solution B   │  │  Solution C   │        │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘        │
│          │                  │                  │                  │
│          └──────────────────┼──────────────────┘                 │
│                             │                                     │
│                             ▼                                     │
│                    ┌───────────────┐                             │
│                    │    Critic     │                             │
│                    │               │                             │
│                    │ Evaluates all │                             │
│                    │   proposals   │                             │
│                    └───────┬───────┘                             │
│                            │                                      │
│                            ▼                                      │
│                    ┌───────────────┐                             │
│                    │   Selector    │                             │
│                    │               │                             │
│                    │ Recommends    │                             │
│                    │ best approach │                             │
│                    └───────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

### Orchestration Configuration

```yaml
# .claude/pipelines/feature_implementation.yaml
name: feature_implementation
description: "Standard workflow for implementing new features"
version: "1.0"

stages:
  - name: plan
    agent: planner
    timeout: 5m
    retry:
      max_attempts: 2
      on_failure: "abort"

  - name: plan_review
    agent: plan_reviewer
    timeout: 3m

  - name: implement
    agent: implementer
    timeout: 30m
    depends_on: [plan_review]
    conditions:
      plan_review.approved: true

  - name: quality_checks
    parallel: true
    stages:
      - name: test
        agent: tester
        timeout: 10m
      - name: lint
        agent: linter
        timeout: 2m
      - name: security
        agent: security_scanner
        timeout: 5m

  - name: code_review
    agent: code_reviewer
    depends_on: [quality_checks]
    timeout: 5m

  - name: create_pr
    agent: pr_creator
    depends_on: [code_review]
    conditions:
      code_review.approved: true

state_management:
  backend: beads
  checkpoint_after: [plan, implement, quality_checks]

error_handling:
  on_stage_failure: "notify_and_pause"
  on_timeout: "retry_once_then_notify"
  max_pipeline_duration: 60m
```

## Review and Feedback Loops

### Automated Review Stages

**Plan Review Criteria:**

```yaml
# .claude/review/plan_criteria.yaml
plan_review:
  required_fields:
    - summary
    - complexity
    - phases
    - success_criteria

  complexity_validation:
    simple:
      max_files: 3
      max_phases: 2
    moderate:
      max_files: 10
      max_phases: 4
    complex:
      requires: "ADR reference or justification"

  quality_checks:
    - name: "specific_files"
      description: "All file paths must be verifiable"
      validator: "file_exists_check"

    - name: "testable_criteria"
      description: "Success criteria must be testable"
      validator: "criteria_specificity_check"

    - name: "risk_assessment"
      description: "Complex changes must identify risks"
      condition: "complexity in ['moderate', 'complex']"
      validator: "has_risks_field"
```

**Code Review Criteria:**

```yaml
# .claude/review/code_criteria.yaml
code_review:
  severity_levels:
    critical:
      must_fix: true
      examples:
        - "Security vulnerability"
        - "Data loss risk"
        - "Breaking change without migration"
    major:
      must_fix: true
      examples:
        - "Missing error handling"
        - "No tests for new functionality"
        - "Performance regression"
    minor:
      must_fix: false
      examples:
        - "Code style inconsistency"
        - "Missing documentation"
        - "Unnecessary complexity"
    suggestion:
      must_fix: false
      examples:
        - "Alternative approach possible"
        - "Refactoring opportunity"

  automatic_checks:
    - name: "tests_exist"
      rule: "new_files.any(f => f.is_code) implies new_files.any(f => f.is_test)"
    - name: "no_debug_code"
      rule: "not changes.contains('console.log') and not changes.contains('print(')"
    - name: "error_handling"
      rule: "new_functions.all(f => f.has_try_catch or f.has_error_return)"

  human_escalation:
    conditions:
      - "security_issues.count > 0"
      - "breaking_changes.count > 0"
      - "review_score < 3"
```

### Feedback Integration

**How Review Feedback Flows:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Feedback Integration Flow                     │
│                                                                   │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────┐  │
│  │   Agent       │     │   Review      │     │   Feedback    │  │
│  │   Output      │────▶│   Stage       │────▶│   Parser      │  │
│  └───────────────┘     └───────────────┘     └───────┬───────┘  │
│                                                       │          │
│                                   ┌───────────────────┴───────┐  │
│                                   │                           │  │
│                                   ▼                           ▼  │
│                        ┌───────────────┐           ┌──────────┐ │
│                        │   Actionable  │           │ Context  │ │
│                        │   Issues      │           │ Updates  │ │
│                        └───────┬───────┘           └────┬─────┘ │
│                                │                        │       │
│                                ▼                        ▼       │
│                        ┌───────────────┐     ┌───────────────┐  │
│                        │   Fixer       │     │   Next Stage  │  │
│                        │   Agent       │     │   Context     │  │
│                        │               │     │               │  │
│                        │ Addresses     │     │ Includes      │  │
│                        │ specific      │     │ review        │  │
│                        │ issues        │     │ learnings     │  │
│                        └───────────────┘     └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Feedback Format:**

```json
{
  "review_id": "rev-abc123",
  "overall_assessment": {
    "approved": false,
    "score": 3,
    "summary": "Good implementation but missing edge case handling"
  },
  "issues": [
    {
      "id": "issue-1",
      "severity": "major",
      "file": "src/auth/oauth.py",
      "line": 45,
      "message": "Missing null check for token response",
      "suggestion": "Add: if not token_response: raise AuthError(...)",
      "actionable": true,
      "auto_fixable": true
    },
    {
      "id": "issue-2",
      "severity": "minor",
      "file": "src/auth/oauth.py",
      "line": 67,
      "message": "Magic number should be constant",
      "suggestion": "Extract 3600 to TOKEN_EXPIRY_SECONDS constant",
      "actionable": true,
      "auto_fixable": true
    }
  ],
  "praise": [
    {
      "file": "src/auth/oauth.py",
      "line": 12,
      "message": "Good use of dependency injection for the HTTP client"
    }
  ],
  "context_for_next_stage": {
    "key_concerns": ["null safety", "token validation"],
    "patterns_to_follow": ["existing error handling in auth module"],
    "tests_needed": ["test_oauth_null_token", "test_oauth_expired_token"]
  }
}
```

## Model Selection Strategy

### Task-Complexity Mapping

| Task Complexity | Characteristics | Recommended Model | Rationale |
|-----------------|-----------------|-------------------|-----------|
| **Simple** | Single file, well-defined, < 50 lines | Haiku | Fast, cheap, sufficient |
| **Moderate** | Multiple files, some ambiguity, tests needed | Sonnet | Good balance |
| **Complex** | Architectural, multi-phase, high stakes | Opus | Best reasoning |
| **Validation** | Format checking, linting, simple review | Haiku | Speed matters |
| **Research** | Web search, doc synthesis, exploration | Sonnet | Good comprehension |
| **Decision** | Architecture, trade-offs, high impact | Opus | Deep reasoning |

### Dynamic Model Selection

```python
class ModelSelector:
    """Selects appropriate model based on task characteristics."""

    def select_model(
        self,
        task_type: str,
        complexity: str,
        stage: str,
        token_budget: Optional[int] = None,
    ) -> str:
        """Select model based on task requirements."""

        # Stage-specific overrides
        stage_models = {
            "validation": "haiku",
            "formatting": "haiku",
            "planning": "sonnet",
            "implementation": "sonnet",
            "architecture_decision": "opus",
            "security_review": "opus",
        }

        if stage in stage_models:
            return stage_models[stage]

        # Complexity-based selection
        complexity_models = {
            "simple": "haiku",
            "moderate": "sonnet",
            "complex": "opus",
        }

        base_model = complexity_models.get(complexity, "sonnet")

        # Budget constraints can force downgrade
        if token_budget and token_budget < 1000:
            return "haiku"

        return base_model
```

### Cost-Quality Trade-offs

| Model | Cost Factor | Quality Factor | Best For |
|-------|-------------|----------------|----------|
| Haiku | 1x | Good enough | Validation, formatting, simple tasks |
| Sonnet | 3x | Better | Most development work |
| Opus | 15x | Best | Critical decisions, complex reasoning |

**Optimization Guidelines:**

1. **Use Haiku for:** Validation stages, format checking, simple transformations
2. **Use Sonnet for:** Implementation, testing, standard reviews, research
3. **Use Opus for:** Architectural decisions, security reviews, complex debugging

## Implementation Phases

### Phase 1: Foundation

**Goal:** Establish core prompt architecture and agent templates

**Deliverables:**
- `.claude/templates/` with base templates
- `.claude/agents/` with 3-4 core agent definitions
- Prompt composition engine
- Context selection guidelines document

**Success Criteria:**
- Prompts are composable from templates
- Agent definitions are validated against schema
- Context layers are clearly separated

### Phase 2: Orchestration

**Goal:** Implement multi-agent pipeline support

**Deliverables:**
- `.claude/pipelines/` with workflow definitions
- Pipeline orchestrator (builds on Multi-Agent ADR)
- Review stage integration
- Feedback parsing and routing

**Success Criteria:**
- Plan-Review-Implement pipeline works end-to-end
- Review feedback automatically routes to fixer
- Pipeline state persists in Beads

### Phase 3: Optimization

**Goal:** Optimize for cost and quality

**Deliverables:**
- Dynamic model selection
- Context compression utilities
- Quality metrics dashboard
- A/B testing framework for prompts

**Success Criteria:**
- 30%+ reduction in token usage
- Quality metrics stable or improved
- Model selection matches task complexity

### Phase 4: Advanced Patterns

**Goal:** Support consensus and parallel patterns

**Deliverables:**
- Parallel analysis pipelines
- Consensus decision workflows
- Multi-model ensemble support
- Advanced review criteria

**Success Criteria:**
- PR reviews use parallel analysis
- Architecture decisions use consensus pattern
- Review quality exceeds single-agent baseline

## Consequences

### Positive

**For Development Quality:**
- More consistent outputs across similar tasks
- Automated quality gates catch issues early
- Clear agent boundaries reduce confusion
- Review feedback improves subsequent attempts

**For Efficiency:**
- Token usage optimized through context engineering
- Model selection matches task requirements
- Parallel execution reduces latency
- Reusable templates reduce prompt engineering time

**For Maintainability:**
- Modular prompt components are easier to update
- Agent definitions are self-documenting
- Pipeline configurations are declarative
- Quality criteria are explicit and testable

### Negative / Trade-offs

**Initial Investment:**
- Significant effort to establish templates and patterns
- Learning curve for new prompt architecture
- Migration of existing workflows required

**Ongoing Complexity:**
- More moving parts than single-agent approach
- Orchestration adds failure modes
- Review stages add latency to workflows

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Over-engineering simple tasks | Start with simple pipelines, add complexity as needed |
| Review stages become bottleneck | Set timeouts, allow bypass for low-risk changes |
| Context selection too restrictive | Monitor for missed context, adjust guidelines |
| Model selection suboptimal | Track quality metrics, adjust mappings |

## Decision Permanence

**Reversible Decisions (Low Cost to Change):**
- Specific prompt templates (easily updated)
- Agent configurations (YAML changes)
- Pipeline definitions (declarative)
- Model selection mappings (configuration)

**Semi-Permanent (Moderate Cost to Change):**
- Prompt layer structure (templates depend on it)
- Agent definition schema (agents depend on it)
- Review criteria format (review stages depend on it)

**Permanent (High Cost to Change):**
- Context engineering philosophy (architectural)
- Specialization over generalization principle
- Review as pipeline stage concept

**Review Cadence:**
- **Weekly:** Prompt effectiveness metrics
- **Monthly:** Agent definition updates, pipeline adjustments
- **Quarterly:** Architecture review, pattern assessment

## Alternatives Considered

### Alternative 1: Monolithic Prompts

**Approach:** Continue with single large CLAUDE.md file

**Pros:**
- Simple, no orchestration needed
- Everything in one place

**Cons:**
- Hard to maintain at scale
- No specialization benefits
- Context always loaded regardless of task

**Rejected Because:** Doesn't scale, no quality improvement path

### Alternative 2: External Prompt Management (LangChain, etc.)

**Approach:** Use external framework for prompt management

**Pros:**
- Rich ecosystem of tools
- Community-tested patterns
- Built-in orchestration

**Cons:**
- External dependency
- Learning curve for framework
- May not fit jib's specific needs
- Overhead for simple tasks

**Rejected Because:** Custom solution better fits jib's architecture and avoids dependency overhead

### Alternative 3: Pure Code (No Templates)

**Approach:** Build prompts entirely in Python code

**Pros:**
- Full programmatic control
- Type safety possible
- Familiar to developers

**Cons:**
- Verbose for complex prompts
- Harder for non-developers to modify
- Less visible structure

**Rejected Because:** Templates provide better readability and easier modification

### Alternative 4: No Review Stages

**Approach:** Rely solely on human review

**Pros:**
- Simpler pipeline
- No automated review overhead
- Human judgment for all quality decisions

**Cons:**
- Quality issues reach human review
- More human time spent on fixable issues
- No learning loop for agents

**Rejected Because:** Automated review catches issues earlier, improves agent learning

## References

### Internal Documentation
- [ADR: Multi-Agent Pipeline Architecture](./ADR-Multi-Agent-Pipeline-Architecture.md)
- [ADR: LLM Documentation Index Strategy](../implemented/ADR-LLM-Documentation-Index-Strategy.md)
- [ADR: Autonomous Software Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md)

### Industry Research
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) - Agent design principles
- [Anthropic: Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) - Context engineering lessons
- [Anthropic: Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) - Context management guide
- [OpenAI: Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering) - General prompting best practices

### Prompt Engineering Resources
- [Prompt Engineering Guide](https://www.promptingguide.ai/) - Comprehensive patterns
- [DAIR.AI Prompt Engineering](https://github.com/dair-ai/Prompt-Engineering-Guide) - Academic perspective
- [LangChain Prompts](https://python.langchain.com/docs/modules/model_io/prompts/) - Template patterns

### Related Slack Discussion
- Multi-agent pipeline discussion (2025-12-01)
  - Tyler Burleigh's plugin patterns: [claude-sdd-toolkit](https://github.com/tylerburleigh/claude-sdd-toolkit)
  - Multi-model chorus concept: [claude-model-chorus](https://github.com/tylerburleigh/claude-model-chorus)
  - Review cadence patterns: task, phase, or entire plan implementation review

---

**Last Updated:** 2025-12-01
**Next Review:** 2026-01-01 (Monthly)
**Status:** Proposed (Not Implemented)
