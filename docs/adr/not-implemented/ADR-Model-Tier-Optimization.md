# ADR: Model Tier Optimization for Token Cost Reduction

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** December 2025
**Status:** Proposed (Not Implemented)

---

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Task Taxonomy](#task-taxonomy)
- [Model Selection Framework](#model-selection-framework)
- [Assessment Methodology](#assessment-methodology)
- [Implementation Architecture](#implementation-architecture)
- [Cost Analysis](#cost-analysis)
- [Rollout Plan](#rollout-plan)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

**Problem Statement:**

jib currently runs on Opus 4.5 (`claude-opus-4-5-20251101`) for all tasks regardless of complexity. While Opus provides the highest quality reasoning, it is also the most expensive model:

| Model | Input Cost ($/MTok) | Output Cost ($/MTok) | Cost Factor vs Haiku |
|-------|---------------------|----------------------|----------------------|
| Opus 4.5 | $15.00 | $75.00 | 18.75x |
| Sonnet 4.5 | $3.00 | $15.00 | 3.75x |
| Haiku 3.5 | $0.80 | $4.00 | 1x |

Many jib tasks—validation, simple file edits, formatting, test execution, PR description generation—do not require Opus-level reasoning. Running these on Sonnet or Haiku could significantly reduce token costs without meaningful quality degradation.

**Industry Context:**

Research from [Anthropic's multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) demonstrates that using Claude Opus as a lead agent with Sonnet subagents achieves over 90% of the performance improvement at a fraction of the cost. The Multi-Agent Pipeline Architecture ADR (not-implemented) documents model selection strategies that this ADR operationalizes.

**Current State:**

- All jib invocations use Opus 4.5
- Model pricing is already tracked in `config/model_pricing.py`
- Token usage is captured via `shared/jib_logging/model_capture.py`
- Inefficiency detection infrastructure exists (ADR-LLM-Inefficiency-Reporting)
- No programmatic assessment of task complexity exists

### What We're Deciding

This ADR proposes:

1. **A task taxonomy** that categorizes jib tasks by complexity and model requirements
2. **A Claude-assisted assessment pipeline** that analyzes tasks and recommends optimal model tiers
3. **An automated model selection framework** that routes tasks to appropriate models
4. **A validation approach** to measure quality impact of model tier changes

### Goals

**Primary Goals:**
1. **Reduce Token Costs:** Target 40-60% cost reduction through appropriate model routing
2. **Maintain Quality:** Ensure no meaningful degradation in task outcomes
3. **Automate Assessment:** Use Claude to analyze and categorize tasks programmatically
4. **Enable Continuous Optimization:** Build feedback loops to refine model selection

**Non-Goals:**
- Real-time model switching mid-task (future enhancement)
- Multi-model ensemble for single tasks (covered in Multi-Agent ADR)
- Training custom models or fine-tuning

## Decision

**We will implement a Claude-assisted model tier optimization system that programmatically analyzes tasks, recommends appropriate model tiers, and validates quality outcomes.**

### Core Principles

1. **Conservative Downgrading:** Start with high-confidence candidates for model downgrade
2. **Data-Driven:** Decisions based on empirical task analysis, not intuition
3. **Reversible:** Easy to revert any task to higher-tier model if quality issues emerge
4. **Transparent:** Clear logging of which model handled each task and why

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Assessment Method** | Claude-assisted analysis with human review | Leverages Claude's understanding of task complexity | Pure heuristics (too rigid), human-only (doesn't scale) |
| **Routing Mechanism** | Task type + complexity scoring | Balances automation with flexibility | Per-invocation analysis (too expensive), static mapping (inflexible) |
| **Validation** | A/B comparison with quality metrics | Objective measurement of impact | Subjective review (inconsistent), no validation (risky) |
| **Rollout** | Incremental by task type | Manages risk, allows learning | Big-bang (risky), single model first (slow learning) |

## Task Taxonomy

### Task Categories

Tasks are classified by the model tier that is sufficient for quality completion:

#### Tier 1: Haiku-Suitable Tasks (Simple)

Tasks with well-defined inputs/outputs requiring minimal reasoning:

| Task Type | Characteristics | Examples |
|-----------|-----------------|----------|
| **Validation** | Binary pass/fail, rule-based | Lint checking, format validation, schema validation |
| **Formatting** | Transform to known format | JSON formatting, markdown cleanup, import sorting |
| **Simple File Ops** | Single-file, mechanical changes | Add/remove imports, rename variables, add type hints |
| **Status Queries** | Retrieve and format info | Git status summary, test result formatting, log extraction |
| **Template Application** | Fill known template | PR description from commit messages, changelog generation |

**Haiku Suitability Score:** 0.8-1.0

#### Tier 2: Sonnet-Suitable Tasks (Moderate)

Tasks requiring understanding and moderate reasoning:

| Task Type | Characteristics | Examples |
|-----------|-----------------|----------|
| **Implementation** | Clear requirements, standard patterns | Feature implementation per spec, bug fixes with clear cause |
| **Test Writing** | Following established patterns | Unit tests, integration tests following codebase conventions |
| **Code Review** | Pattern-based analysis | PR review, code quality assessment, convention checking |
| **Documentation** | Technical writing | API docs, README updates, inline comments |
| **Research** | Information synthesis | Code exploration, dependency analysis, pattern identification |
| **Refactoring** | Well-scoped improvements | Extract method, rename class, reorganize imports |

**Sonnet Suitability Score:** 0.5-0.79

#### Tier 3: Opus-Required Tasks (Complex)

Tasks requiring deep reasoning and nuanced judgment:

| Task Type | Characteristics | Examples |
|-----------|-----------------|----------|
| **Architecture** | System-wide impact, trade-off analysis | Design decisions, ADR creation, system design |
| **Complex Debugging** | Unclear cause, multi-system | Production incidents, race conditions, subtle bugs |
| **Security Review** | High-stakes, requires deep analysis | Security audit, vulnerability assessment, threat modeling |
| **Ambiguous Requirements** | Requires interpretation and judgment | Unclear specs, stakeholder alignment needed |
| **Cross-Cutting Changes** | Multiple systems, coordination | Large refactors, migration planning, API changes |
| **Novel Problems** | No established pattern to follow | New algorithms, unique integrations, research tasks |

**Opus Suitability Score:** 0.0-0.49

### Complexity Scoring Dimensions

Each task is scored across dimensions that contribute to model selection:

| Dimension | Weight | Haiku (0-0.3) | Sonnet (0.3-0.7) | Opus (0.7-1.0) |
|-----------|--------|---------------|------------------|----------------|
| **Reasoning Depth** | 30% | Rule-based, mechanical | Pattern matching, standard | Abstract, novel reasoning |
| **Scope** | 25% | Single file, isolated | Multiple files, related | System-wide, cross-cutting |
| **Ambiguity** | 20% | Well-defined | Mostly clear | Significant interpretation needed |
| **Stakes** | 15% | Low impact | Moderate impact | High impact, hard to reverse |
| **Context Requirements** | 10% | Minimal context | Moderate context | Deep codebase understanding |

**Composite Score Formula:**
```
task_score = sum(dimension_score * weight for each dimension)
```

## Model Selection Framework

### Static Task Type Mapping

First, check if task type has a known model requirement:

```python
TASK_TYPE_MODELS = {
    # Tier 1: Haiku
    "lint_check": "haiku",
    "format_validation": "haiku",
    "import_sorting": "haiku",
    "simple_rename": "haiku",
    "status_query": "haiku",
    "template_fill": "haiku",
    "changelog_generate": "haiku",

    # Tier 2: Sonnet
    "feature_implementation": "sonnet",
    "bug_fix_clear": "sonnet",
    "test_writing": "sonnet",
    "pr_review": "sonnet",
    "documentation": "sonnet",
    "code_research": "sonnet",
    "simple_refactor": "sonnet",

    # Tier 3: Opus
    "architecture_decision": "opus",
    "security_review": "opus",
    "complex_debugging": "opus",
    "adr_creation": "opus",
    "system_design": "opus",
    "ambiguous_task": "opus",
}
```

### Dynamic Complexity Assessment

For tasks without static mapping, or to validate static mapping:

```python
class TaskComplexityAssessor:
    """Uses Claude to assess task complexity and recommend model tier."""

    ASSESSMENT_PROMPT = """
    Analyze this task and recommend the appropriate Claude model tier.

    ## Task Description
    {task_description}

    ## Context
    - Files involved: {files}
    - Estimated scope: {scope_hint}
    - Related tasks: {related_tasks}

    ## Score each dimension (0.0-1.0):

    1. **Reasoning Depth** (0=mechanical, 1=novel reasoning): How much abstract reasoning is required?
    2. **Scope** (0=single file, 1=system-wide): How many components are affected?
    3. **Ambiguity** (0=well-defined, 1=needs interpretation): How clear are the requirements?
    4. **Stakes** (0=low impact, 1=high impact): What's the risk of mistakes?
    5. **Context Requirements** (0=minimal, 1=deep understanding): How much codebase knowledge is needed?

    ## Output Format (JSON only):
    {
      "reasoning_depth": <0.0-1.0>,
      "scope": <0.0-1.0>,
      "ambiguity": <0.0-1.0>,
      "stakes": <0.0-1.0>,
      "context_requirements": <0.0-1.0>,
      "recommended_model": "<haiku|sonnet|opus>",
      "confidence": <0.0-1.0>,
      "rationale": "<brief explanation>"
    }
    """

    def assess(self, task: dict) -> dict:
        """Assess task complexity and return model recommendation."""
        prompt = self.ASSESSMENT_PROMPT.format(
            task_description=task.get("description", ""),
            files=task.get("files", []),
            scope_hint=task.get("scope_hint", "unknown"),
            related_tasks=task.get("related_tasks", []),
        )

        # Use Haiku for the assessment itself (meta-optimization)
        response = self.invoke_claude(prompt, model="haiku")

        assessment = json.loads(response)
        assessment["composite_score"] = self._calculate_composite(assessment)

        return assessment

    def _calculate_composite(self, assessment: dict) -> float:
        """Calculate weighted composite score."""
        weights = {
            "reasoning_depth": 0.30,
            "scope": 0.25,
            "ambiguity": 0.20,
            "stakes": 0.15,
            "context_requirements": 0.10,
        }

        return sum(
            assessment.get(dim, 0.5) * weight
            for dim, weight in weights.items()
        )
```

### Model Router

```python
class ModelRouter:
    """Routes tasks to appropriate model tier."""

    def __init__(self, config: dict):
        self.static_mappings = config.get("task_type_models", TASK_TYPE_MODELS)
        self.assessor = TaskComplexityAssessor()
        self.thresholds = config.get("thresholds", {
            "haiku_max": 0.30,
            "sonnet_max": 0.70,
        })

    def select_model(self, task: dict) -> tuple[str, dict]:
        """Select model for task. Returns (model, metadata)."""

        # Check static mapping first
        task_type = task.get("task_type")
        if task_type in self.static_mappings:
            return (
                self.static_mappings[task_type],
                {"source": "static_mapping", "task_type": task_type}
            )

        # Dynamic assessment
        assessment = self.assessor.assess(task)
        score = assessment["composite_score"]

        if score <= self.thresholds["haiku_max"]:
            model = "haiku"
        elif score <= self.thresholds["sonnet_max"]:
            model = "sonnet"
        else:
            model = "opus"

        # Override if Claude strongly recommends different
        if assessment.get("confidence", 0) > 0.9:
            model = assessment["recommended_model"]

        return (model, {"source": "dynamic_assessment", **assessment})
```

## Assessment Methodology

### Phase 1: Task Analysis

Analyze historical jib sessions to understand current task distribution:

```python
class TaskAnalyzer:
    """Analyzes historical tasks to build optimization model."""

    def analyze_session_history(self, days: int = 30) -> dict:
        """Analyze past sessions for task patterns."""

        sessions = self.load_sessions(days)

        analysis = {
            "total_sessions": len(sessions),
            "total_tokens": 0,
            "task_distribution": {},
            "model_recommendations": {},
            "potential_savings": 0,
        }

        for session in sessions:
            task_type = self.classify_task(session)
            tokens = session.get("tokens", {})

            analysis["total_tokens"] += tokens.get("total", 0)
            analysis["task_distribution"][task_type] = (
                analysis["task_distribution"].get(task_type, 0) + 1
            )

            # Assess what model could have been used
            assessment = self.assessor.assess(session)
            recommended = assessment["recommended_model"]

            if recommended != "opus":
                current_cost = self.calculate_cost(tokens, "opus")
                optimal_cost = self.calculate_cost(tokens, recommended)
                analysis["potential_savings"] += current_cost - optimal_cost

            analysis["model_recommendations"][task_type] = recommended

        return analysis
```

### Phase 2: Quality Validation

For each task type considered for downgrade, run A/B validation:

```python
class QualityValidator:
    """Validates model tier changes don't degrade quality."""

    VALIDATION_CRITERIA = {
        "task_completion": {
            "weight": 0.40,
            "threshold": 0.95,  # Must complete task successfully
        },
        "output_quality": {
            "weight": 0.30,
            "threshold": 0.85,  # Output quality score (Claude-assessed)
        },
        "error_rate": {
            "weight": 0.20,
            "threshold": 0.05,  # Max 5% error rate increase
        },
        "iteration_count": {
            "weight": 0.10,
            "threshold": 1.2,  # Max 20% more iterations needed
        },
    }

    def validate_model_change(
        self,
        task_type: str,
        from_model: str,
        to_model: str,
        sample_size: int = 20,
    ) -> dict:
        """Run validation comparing model performance on task type."""

        # Get sample tasks of this type
        tasks = self.get_sample_tasks(task_type, sample_size)

        results = {
            "baseline": [],
            "candidate": [],
        }

        for task in tasks:
            # Run with both models (or use historical baseline)
            baseline_result = self.execute_task(task, from_model)
            candidate_result = self.execute_task(task, to_model)

            results["baseline"].append(baseline_result)
            results["candidate"].append(candidate_result)

        # Calculate quality metrics
        comparison = self._compare_results(results)

        # Determine if change is acceptable
        acceptable = all(
            comparison[criterion]["delta"] <= config["threshold"]
            for criterion, config in self.VALIDATION_CRITERIA.items()
        )

        return {
            "task_type": task_type,
            "from_model": from_model,
            "to_model": to_model,
            "sample_size": sample_size,
            "comparison": comparison,
            "acceptable": acceptable,
            "cost_savings": self._calculate_savings(results),
        }
```

### Phase 3: Continuous Monitoring

Track quality metrics post-deployment:

```python
class ModelTierMonitor:
    """Monitors quality metrics for model tier decisions."""

    def record_task_outcome(
        self,
        task_id: str,
        model: str,
        selection_metadata: dict,
        outcome: dict,
    ):
        """Record task outcome for quality monitoring."""

        record = {
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat(),
            "model": model,
            "selection_source": selection_metadata.get("source"),
            "composite_score": selection_metadata.get("composite_score"),
            "task_type": selection_metadata.get("task_type"),
            "outcome": {
                "success": outcome.get("success", False),
                "errors": outcome.get("errors", []),
                "iterations": outcome.get("iterations", 1),
                "human_correction_needed": outcome.get("corrected", False),
                "tokens_used": outcome.get("tokens", {}),
            },
        }

        self._store_record(record)
        self._check_quality_alerts(record)

    def generate_quality_report(self, period_days: int = 7) -> dict:
        """Generate quality report for model tier decisions."""

        records = self.load_records(period_days)

        report = {
            "period": f"Last {period_days} days",
            "total_tasks": len(records),
            "by_model": {},
            "by_task_type": {},
            "recommendations": [],
        }

        # Aggregate by model
        for model in ["haiku", "sonnet", "opus"]:
            model_records = [r for r in records if r["model"] == model]
            report["by_model"][model] = self._calculate_metrics(model_records)

        # Identify issues
        for model, metrics in report["by_model"].items():
            if metrics["error_rate"] > 0.10:
                report["recommendations"].append({
                    "type": "quality_concern",
                    "model": model,
                    "issue": f"Error rate {metrics['error_rate']:.1%} exceeds threshold",
                    "action": "Review task assignments and consider upgrading",
                })

        return report
```

## Implementation Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Model Tier Optimization System                     │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Task Intake                                  │ │
│  │  Slack/GitHub/JIRA → incoming-processor.py                      │ │
│  └───────────────────────────┬────────────────────────────────────┘ │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Model Router                                 │ │
│  │                                                                  │ │
│  │  ┌─────────────┐    ┌─────────────────┐    ┌───────────────┐   │ │
│  │  │   Static    │    │    Dynamic      │    │   Override    │   │ │
│  │  │   Mapping   │ →  │   Assessment    │ →  │   Rules       │   │ │
│  │  │             │    │   (Haiku)       │    │               │   │ │
│  │  └─────────────┘    └─────────────────┘    └───────────────┘   │ │
│  │                              │                                   │ │
│  │                              ▼                                   │ │
│  │                     Model Selection                              │ │
│  │              ┌────────┬────────┬────────┐                       │ │
│  │              │ Haiku  │ Sonnet │ Opus   │                       │ │
│  │              └────────┴────────┴────────┘                       │ │
│  └───────────────────────────┬────────────────────────────────────┘ │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Task Execution                               │ │
│  │  Claude Code invocation with selected model                     │ │
│  └───────────────────────────┬────────────────────────────────────┘ │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                     Quality Monitoring                           │ │
│  │  - Outcome tracking                                             │ │
│  │  - Quality metrics                                              │ │
│  │  - Cost tracking                                                │ │
│  │  - Feedback loop                                                │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Integration Points

| Component | Integration | Description |
|-----------|-------------|-------------|
| **incoming-processor.py** | Task intake | Extract task type and initial classification |
| **claude wrapper** | Model selection | Pass model parameter to Claude invocation |
| **model_capture.py** | Outcome tracking | Record model used and token counts |
| **inefficiency-detector** | Quality analysis | Include model tier in inefficiency reports |
| **beads** | Task correlation | Link model decisions to task outcomes |

### Configuration

```yaml
# config/model_tier_config.yaml

model_selection:
  default_model: "sonnet"  # Default when no mapping found

  thresholds:
    haiku_max_score: 0.30
    sonnet_max_score: 0.70

  static_mappings:
    # See TASK_TYPE_MODELS above
    enabled: true

  dynamic_assessment:
    enabled: true
    assessment_model: "haiku"  # Use Haiku for assessments
    cache_duration_hours: 24   # Cache assessment results

  overrides:
    # Force specific tasks to specific models
    security_review: "opus"
    adr_creation: "opus"

quality_monitoring:
  error_rate_threshold: 0.10
  correction_rate_threshold: 0.15
  alert_channel: "slack"
  report_frequency: "weekly"
```

## Cost Analysis

### Projected Savings

Based on typical jib task distribution:

| Task Category | % of Tasks | Current Model | Recommended | Savings |
|---------------|------------|---------------|-------------|---------|
| Validation/Formatting | 15% | Opus | Haiku | 94% |
| Simple File Ops | 10% | Opus | Haiku | 94% |
| Feature Implementation | 25% | Opus | Sonnet | 80% |
| Test Writing | 15% | Opus | Sonnet | 80% |
| PR Review | 10% | Opus | Sonnet | 80% |
| Documentation | 10% | Opus | Sonnet | 80% |
| Complex Tasks | 15% | Opus | Opus | 0% |

**Weighted Average Savings:** ~65% cost reduction

### Cost-Quality Curves

```
Quality Score (1.0 = Opus baseline)
│
1.0 ├────────────────────────────●──── Opus
│                               │
0.95├─────────────────●─────────┤     Sonnet (most tasks)
│                    │         │
0.90├────────●───────┤         │     Haiku (simple tasks)
│           │       │         │
0.85├────────┤       │         │
│          │       │         │
    └───────┴───────┴─────────┴────► Cost ($/MTok output)
           $4      $15       $75
```

### Break-Even Analysis

For a task type to be worth downgrading:

```
Quality_Degradation < Cost_Savings × Acceptable_Trade_off_Ratio

Example:
- Sonnet achieves 95% of Opus quality for PR reviews
- Cost savings: 80%
- Trade-off ratio threshold: 0.1 (accept 10% quality loss for 50%+ savings)

95% quality, 80% savings = well above threshold → DOWNGRADE
```

## Rollout Plan

### Phase 1: Analysis (1 iteration)

- [ ] Deploy task analyzer to categorize historical sessions
- [ ] Generate task distribution report
- [ ] Identify top candidates for model tier changes
- [ ] Establish quality baselines

**Success Criteria:**
- Task taxonomy covering 90%+ of jib tasks
- Baseline quality metrics for each task type
- Potential savings estimate

### Phase 2: Validation (2-3 iterations)

- [ ] Implement A/B validation framework
- [ ] Validate Haiku suitability for Tier 1 tasks
- [ ] Validate Sonnet suitability for Tier 2 tasks
- [ ] Document quality deltas

**Success Criteria:**
- <5% quality degradation for validated task types
- Validation data for 80%+ of task types
- Clear go/no-go criteria established

### Phase 3: Gradual Rollout (ongoing)

- [ ] Deploy model router with conservative thresholds
- [ ] Start with highest-confidence task types
- [ ] Enable dynamic assessment for unknown tasks
- [ ] Implement quality monitoring dashboards

**Success Criteria:**
- 50%+ of tasks routed to lower-tier models
- Error rate within 5% of baseline
- Cost reduction >40%

### Phase 4: Optimization (ongoing)

- [ ] Tune thresholds based on production data
- [ ] Expand task type coverage
- [ ] Integrate with inefficiency reporting
- [ ] Build feedback loop for continuous improvement

**Success Criteria:**
- 60%+ cost reduction
- Automated threshold adjustment
- Self-improving model selection

## Consequences

### Positive

**Cost:**
- 40-60% reduction in token costs
- Better utilization of model capabilities
- Budget predictability

**Quality:**
- Appropriate model for each task type
- Faster response times for simple tasks (Haiku is faster)
- Preserved quality for complex tasks

**Operations:**
- Data-driven model selection
- Transparent decision logging
- Continuous optimization path

### Negative / Trade-offs

**Complexity:**
- Additional routing logic to maintain
- More configuration to manage
- Potential for misclassification

**Risk:**
- Quality degradation if thresholds misconfigured
- Edge cases may get wrong model
- Assessment overhead (mitigated by using Haiku)

**Mitigation:**
- Conservative initial thresholds
- Override capability for known complex tasks
- Quality monitoring with automatic alerts
- Easy rollback to single-model approach

## Decision Permanence

**Reversible Decisions (Low Cost to Change):**
- Threshold values for model selection
- Static task type mappings
- Assessment prompt template

**Semi-Permanent (Moderate Cost to Change):**
- Task taxonomy categories
- Quality metric definitions
- Assessment pipeline architecture

**Permanent (High Cost to Change):**
- Decision to use multi-tier model approach
- Integration points with existing infrastructure

**Review Cadence:**
- **Weekly:** Quality metrics review, threshold adjustments
- **Monthly:** Task taxonomy updates, cost analysis
- **Quarterly:** Architecture review, framework evaluation

## Alternatives Considered

### Alternative 1: Single Model (Status Quo)

**Approach:** Continue using Opus for all tasks.

**Pros:**
- Simplicity
- Consistent quality
- No routing complexity

**Cons:**
- Highest cost
- Overkill for simple tasks
- No optimization path

**Rejected Because:** Cost is unsustainable as jib usage scales; many tasks demonstrably don't need Opus-level reasoning.

### Alternative 2: Manual Model Selection

**Approach:** Human specifies model tier for each task.

**Pros:**
- Human judgment
- No automation complexity
- Full control

**Cons:**
- Doesn't scale
- Inconsistent decisions
- Friction in workflow

**Rejected Because:** Adds friction to jib usage; humans shouldn't need to think about model selection.

### Alternative 3: Pure Heuristic Routing

**Approach:** Route based on simple rules (file count, task keywords) without Claude assessment.

**Pros:**
- No assessment cost
- Deterministic
- Fast

**Cons:**
- Inflexible
- Misses nuance
- Hard to tune

**Rejected Because:** Task complexity is nuanced; simple heuristics will misclassify many tasks.

### Alternative 4: Always Assess with Opus

**Approach:** Use Opus to assess every task's complexity before routing.

**Pros:**
- Highest quality assessment
- Consistent reasoning

**Cons:**
- Assessment cost negates savings
- Slow for simple tasks
- Overkill for assessment

**Rejected Because:** Using Opus just to decide to use Haiku defeats the purpose. Haiku is sufficient for task classification.

## References

### Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) | Parent ADR; defines jib architecture |
| [ADR-LLM-Inefficiency-Reporting](../implemented/ADR-LLM-Inefficiency-Reporting.md) | Token tracking infrastructure this ADR leverages |
| [ADR-Multi-Agent-Pipeline-Architecture](./ADR-Multi-Agent-Pipeline-Architecture.md) | Model selection strategy section; this ADR operationalizes |
| [ADR-Standardized-Logging-Interface](../in-progress/ADR-Standardized-Logging-Interface.md) | Model capture logging used for tracking |

### External Resources

- [Anthropic Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system) - Demonstrates Opus lead with Sonnet subagents
- [Anthropic Pricing](https://www.anthropic.com/pricing) - Current model pricing
- [Agentic AI Token Cost Optimization](https://medium.com/@anishnarayan09/agentic-ai-automation-optimize-efficiency-minimize-token-costs-69185687713c) - Industry guidance on agent cost management

### Internal Resources

- `config/model_pricing.py` - Model pricing configuration
- `shared/jib_logging/model_capture.py` - Token capture infrastructure
- `host-services/analysis/inefficiency-detector/` - Quality analysis tools

---

**Last Updated:** 2025-12-02
**Next Review:** After Phase 1 Analysis
**Status:** Proposed (Not Implemented)
