# LLM-First Software Development Lifecycle

**Status:** Draft
**Author:** Tyler Burleigh, James Wiesebron
**Created:** December 2025
**Purpose:** Strategic framework for evaluating and improving LLM-assisted development systems

---

## Executive Summary

This document captures the strategic concerns and evaluation frameworks for building LLM-assisted software development systems. It provides guidance on:

- **Quality metrics** for measuring LLM-generated artifacts
- **Evaluation methodologies** including LLM-as-Judge panels
- **A/B testing infrastructure** for iterative improvement
- **Success metrics** for stakeholder communication
- **Organizational considerations** for security and model strategy

This is a companion document to implementation-focused ADRs (e.g., Codebase Analyzer Strategy, Interactive Planning Framework) and should evolve as we learn from production use.

---

## Table of Contents

- [Quality Metrics Framework](#quality-metrics-framework)
- [LLM-as-a-Judge Evaluation](#llm-as-a-judge-evaluation)
- [Success Metrics](#success-metrics)
- [A/B Testing Infrastructure](#ab-testing-infrastructure)
- [Human Feedback Collection](#human-feedback-collection)
- [Intermediate Artifact Caching](#intermediate-artifact-caching)
- [Model and Provider Strategy](#model-and-provider-strategy)
- [Security Considerations](#security-considerations)
- [References](#references)

---

## Quality Metrics Framework

### The Challenge

How do we measure "quality" for LLM-generated outputs like documentation, code recommendations, or analysis reports? This is critical for:

1. **A/B testing** - Deciding which developments are worth keeping
2. **Evidence-based decisions** - Demonstrating value of iterations
3. **Continuous improvement** - Identifying areas for refinement

### Quality Dimensions

| Dimension | Definition | Evaluation Criteria |
|-----------|------------|---------------------|
| **Accuracy** | Did the analysis correctly identify the issue? | No hallucinated issues; findings match actual code state |
| **Comprehensiveness** | Did it miss anything critical? | Coverage of security, performance, maintainability concerns |
| **Parsimony** | Did it avoid extraneous or unnecessary detail? | Concise recommendations; no redundant findings |
| **Actionability** | Are recommendations specific enough to implement? | Clear steps; specific file/line references |
| **Prioritization** | Are severity levels appropriate? | Critical items are truly critical; noise is filtered |
| **Organization** | Is it properly organized and cross-referenced? | Logical structure; easy navigation; proper linking |
| **Efficiency** | What resources were consumed? | Time, token consumption, cost |

### Measuring Impact on Agent Effectiveness

To measure whether codebase documentation improves agent task completion:

**Experimental Design:**

```
Task Suite: Collection of 20 realistic tasks requiring codebase understanding
  - "Add rate limiting to the API"
  - "Fix the authentication bypass in /admin"
  - "Refactor duplicate code in utils/"

For each task:
  - Branch A: Agent with Documentation Version A
  - Branch B: Agent with Documentation Version B

Measures:
  - Time to completion (wall clock)
  - Tokens consumed
  - Solution quality (LLM judge panel)
  - Test pass rate
  - Human review verdict (approve/reject)
```

---

## LLM-as-a-Judge Evaluation

For subjective quality dimensions (documentation quality, code recommendation quality), we employ an LLM judge panel approach based on [recent research](https://arxiv.org/abs/2411.15594) showing LLM judges can achieve 85% alignment with human judgment.

### Multi-Model Judge Panel

To mitigate individual model bias, use a panel of 3 LLM judges with diverse perspectives:

```yaml
# judge-panel-config.yaml
judges:
  - model: "claude-3-5-sonnet"
    role: "technical_accuracy"
    focus: "Correctness of findings, false positive detection"

  - model: "gpt-4o"
    role: "completeness_check"
    focus: "Missed issues, coverage gaps"

  - model: "claude-3-5-haiku"
    role: "actionability"
    focus: "Clarity and implementability of recommendations"

consensus_threshold: 2  # 2 of 3 judges must agree
```

### Evaluation Output Format

```json
{
  "evaluation_id": "eval-2025-12-01-001",
  "analysis_run_id": "run-abc123",
  "judge_results": [
    {
      "judge": "claude-3-5-sonnet",
      "scores": {
        "accuracy": 4.2,
        "comprehensiveness": 3.8,
        "parsimony": 4.5,
        "actionability": 4.0,
        "prioritization": 3.9
      },
      "consensus_findings": ["finding-001", "finding-003"],
      "disputed_findings": ["finding-002"],
      "reasoning": "Finding-002 flagged as medium but is low severity..."
    }
  ],
  "consensus_score": 4.1,
  "improvement_recommendations": [
    "Reduce false positives in unused import detection",
    "Improve specificity of refactoring suggestions"
  ]
}
```

### Validating LLM Judges Against Human Judgment

If documentation is meant for human consumers, we need to validate that LLM judges faithfully represent human judgment:

1. **Collect human evaluations** on a sample of outputs
2. **Compare LLM judge scores** to human scores
3. **Measure alignment** (target: 85%+ agreement)
4. **Calibrate judges** based on disagreements

---

## Success Metrics

### Top-Line Metrics (1-3 for Stakeholder Communication)

These metrics should be:
- Easy for stakeholders to interpret
- Sensitive to improvements over time
- Representative of actual success

| Metric | Definition | Target | Measurement Method |
|--------|------------|--------|-------------------|
| **PR Acceptance Rate** | Percentage of generated PRs merged (with or without modifications) | ≥75% | Track merged/closed status |
| **Time to Remediation** | Average time from issue detection to merged fix | <48h critical, <7d high | Timestamp analysis |
| **False Positive Rate** | Percentage of findings marked as "not an issue" | <15% | Track rejection reasons |

### Why PR Acceptance Rate?

If the "deliverable" is a PR, then PR acceptance rate is the ultimate metric:
- Emphasizes quality over quantity
- Provides a clear signal of value
- Enables comparison over time

For rejected PRs, require structured feedback to understand *why* and feed back into system improvement.

---

## A/B Testing Infrastructure

### Test Codebase Collection

Maintain a collection of "toy" codebases as standardized test cases. This avoids:
- Running against only `webapp` (large, homogeneous)
- "Overfitting" to a particular codebase

| Codebase | Purpose | Characteristics |
|----------|---------|-----------------|
| **toy-webapp-python** | Python web app patterns | Flask/FastAPI, ~5K LoC, known issues injected |
| **toy-cli-python** | CLI tool patterns | Click/Typer, ~2K LoC, good coverage |
| **toy-legacy-python** | Legacy code patterns | Mixed styles, low coverage, tech debt |
| **toy-microservices** | Multi-service patterns | Docker, 3 services, integration complexity |

Test codebases include:
- **Known issues** (injected bugs, security vulnerabilities, coverage gaps)
- **Ground truth labels** (what the analyzer should find)
- **Diverse patterns** (to prevent overfitting)

### A/B Comparison Protocol

```
For each test codebase:
1. Run Version A → Collect findings A
2. Run Version B → Collect findings B
3. LLM Judge Panel evaluates both against ground truth
4. Calculate:
   - Precision: % of findings that are correct
   - Recall: % of known issues detected
   - F1 score: Harmonic mean of precision/recall
   - Time: Analysis duration
   - Cost: Token consumption
5. Human tiebreaker for disputed cases
```

---

## Human Feedback Collection

### PR Review Feedback Template

For every rejected or heavily-modified generated PR:

```markdown
## Rejection/Modification Feedback

**PR:** #XXX
**Reason:** [ ] False positive [ ] Low priority [ ] Incorrect fix [ ] Style preference [ ] Other

**Feedback Category:**
- [ ] Analysis was wrong (false positive)
- [ ] Analysis was right, but fix was wrong
- [ ] Analysis was right, fix was right, but priority was wrong
- [ ] Analysis was right, but not worth the churn

**Detailed Feedback:**
[Free-form explanation]

**Would this feedback apply to similar findings?** [ ] Yes [ ] No
```

This feedback:
- Serves analytic purposes
- Enables A/B decision-making
- Feeds into the system's ability to self-improve
- Allows comparison across reviewers and over time

### Continuous Improvement Loop

```
┌─────────────────────────────────────────────────────────────────┐
│              Continuous Improvement Loop                         │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Analysis   │───▶│  PR Output   │───▶│ Human Review │      │
│  │    Run       │    │              │    │  + Feedback  │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│                                                  │               │
│                                                  ▼               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │   Calibrate  │◀───│  LLM Judge   │◀───│   Collect    │      │
│  │   System     │    │  Evaluation  │    │  Feedback    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Intermediate Artifact Caching

### The Problem

As codebases evolve, how do we efficiently update documentation without re-analyzing unchanged code? Intermediate artifacts can:
- Speed up incremental updates
- Support failure/retry/resume scenarios
- Reduce costs

### Cache Architecture

```
cache/
├── structural/
│   ├── {file_hash}.ast.json     # AST for unchanged files
│   └── dependency_graph.json    # Updated incrementally
├── semantic/
│   └── {file_hash}.analysis.json # LLM analysis cache
├── coverage/
│   └── {test_hash}.coverage.json # Coverage for test runs
└── manifest.json                 # Cache validity tracking

Invalidation: File hash change → Invalidate file + dependents
Retention: 7 days for semantic, 30 days for structural
```

### Expected Benefits

| Scenario | Without Cache | With Cache | Improvement |
|----------|---------------|------------|-------------|
| Full repo analysis (no changes) | ~30 min | ~2 min | 15x faster |
| Single file change | ~30 min | ~5 min | 6x faster |
| Failure at Phase 4 | Restart from Phase 1 | Resume from Phase 4 | Significant savings |

### Update Strategy Options

1. **Weekly full analysis** - Check diff for last week, update docs based on changes
2. **Pre/post-merge hooks** - Run same analysis on smaller diff as part of CI
3. **Hybrid** - Full analysis weekly, incremental on each merge

---

## Model and Provider Strategy

### MVP Approach (v0)

- Target Claude (Sonnet) as primary model since it's currently SOTA for code understanding
- Single-provider implementation to minimize complexity

### Future Evolution

- Design abstractions that allow model swapping without architectural changes
- Consider multi-model pipelines (cheaper models for structural analysis, frontier for semantic)
- Enable provider redundancy for reliability

**Decision:** Build v0 on Claude, but structure code with provider abstraction layer for future flexibility. Model/provider agnosticism is a Phase 6+ concern, not a v0 requirement.

---

## Security Considerations

### Dependencies and Blockers

This work depends on the security team's ongoing review of model sandboxing and autonomous edit modes. Specifically:

- **Model autonomy requirements:** Running code analysis tools may trigger security concerns
- **Sandboxing assurances:** Clarity on what isolation guarantees are required
- **Container isolation:** Current Docker containers may or may not meet requirements

**Recommendation:** Before implementing semantic analysis with LLM, confirm security team approval. Consider:
- WebAssembly sandboxing ([NVIDIA's approach](https://developer.nvidia.com/blog/sandboxing-agentic-ai-workflows-with-webassembly/))
- gVisor for stronger container isolation
- Restricted tool access patterns

### Sidecar Architecture for Secret Isolation

Consider an architecture that entirely isolates the LLM agent from secrets using a "sidecar" that also filters network traffic to avoid data exfiltration. The filtering will be challenging but valuable.

---

## References

### LLM-as-a-Judge Evaluation
- [A Survey on LLM-as-a-Judge](https://arxiv.org/abs/2411.15594) - arXiv comprehensive survey
- [LLM-as-a-judge: A Complete Guide](https://www.evidentlyai.com/llm-guide/llm-as-a-judge) - Evidently AI
- [LLMs-as-Judges: Comprehensive Survey on LLM-based Evaluation](https://arxiv.org/html/2412.05579v2) - arXiv

### Security and Sandboxing
- [Sandboxing Agentic AI Workflows with WebAssembly](https://developer.nvidia.com/blog/sandboxing-agentic-ai-workflows-with-webassembly/) - NVIDIA
- [Agentic AI and Security](https://martinfowler.com/articles/agentic-ai-security.html) - Martin Fowler
- [LLM Security in 2025: Risks and Best Practices](https://www.oligo.security/academy/llm-security-in-2025-risks-examples-and-best-practices) - Oligo Security

### Related Documents
- [ADR: Codebase Analyzer Strategy](../adr/not-implemented/ADR-Codebase-Analyzer-Strategy.md) - POC implementation
- [ADR: Interactive Planning Framework](../adr/not-implemented/ADR-Interactive-Planning-Framework.md) - Planning workflow
- [ADR: Continuous System Reinforcement](../adr/not-implemented/ADR-Continuous-System-Reinforcement.md) - Feedback loops

---

**Last Updated:** 2025-12-05
**Next Review:** 2026-01-05 (Monthly)
