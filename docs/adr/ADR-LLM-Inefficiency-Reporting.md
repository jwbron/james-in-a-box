# ADR: LLM Processing Inefficiency Reporting and Self-Improvement

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Draft

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Inefficiency Taxonomy](#inefficiency-taxonomy)
- [Data Collection Architecture](#data-collection-architecture)
- [Report Generation](#report-generation)
- [Self-Improvement Loop](#self-improvement-loop)
- [Implementation Details](#implementation-details)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)
- [References](#references)

## Context

### Background

The james-in-a-box (jib) agent performs complex software engineering tasks autonomously. While task completion is tracked via Beads, we currently lack visibility into **how efficiently** the LLM processes tasks. Inefficiencies manifest as:

- Repeated tool calls that fail to find information
- Circular reasoning or decision loops
- Excessive token consumption for simple tasks
- Difficulties locating documentation or tools
- Unclear direction leading to thrashing

Research shows that LLM agents can significantly improve performance through self-reflection ([Renze & Guven, 2024](https://arxiv.org/abs/2405.06682)), and that metacognitive capabilities—monitoring, evaluating, and regulating reasoning—are essential for truly self-improving agents ([OpenReview, 2024](https://openreview.net/forum?id=4KhDd0Ozqe)).

### Problem Statement

**Current state:** We know *what* jib accomplished but not *how efficiently* it worked.

**Missing visibility:**
1. **Tool Discovery Failures:** How often does jib fail to find the right tool or documentation?
2. **Decision Loops:** How frequently does jib reconsider the same decision multiple times?
3. **Direction Changes:** How often does jib change approach mid-task?
4. **Token Waste:** What percentage of tokens are spent on unproductive exploration?
5. **Retry Patterns:** How often do tool calls fail and require retries?
6. **Context Gaps:** What information was missing that would have helped?

Industry research identifies these as common failure modes in agentic workflows, with agents often getting "stuck in loops, burn[ing] a bunch of tokens, wast[ing] resources" ([Retool, 2025](https://retool.com/blog/agentic-ai-workflows)).

### Goals

**Primary Goals:**
1. Generate actionable reports on LLM processing inefficiencies
2. Enable data-driven improvements to prompts and tooling
3. Reduce token consumption and task completion time
4. Surface patterns that indicate systemic issues
5. Create feedback loops for continuous improvement

**Non-Goals:**
- Real-time intervention during task execution (future enhancement)
- Automated prompt modification without human review
- Performance comparison across different LLM providers

## Decision

**We will implement a comprehensive inefficiency reporting system with four components:**

1. **Trace Collection:** Capture structured traces of all LLM interactions
2. **Inefficiency Detection:** Analyze traces to identify failure patterns
3. **Report Generation:** Produce weekly reports with actionable insights
4. **Self-Improvement Loop:** Feed learnings back into prompt engineering

### Core Principles

1. **Observe, Don't Block:** Collection happens passively without impacting task execution
2. **Classify, Don't Judge:** Categorize inefficiencies objectively using defined taxonomy
3. **Aggregate, Then Drill Down:** Reports show patterns first, details on request
4. **Human-in-the-Loop Improvement:** All prompt changes require human review

## Inefficiency Taxonomy

Based on industry research on LLM failure modes and hallucination taxonomies ([arXiv 2311.05232](https://arxiv.org/abs/2311.05232), [arXiv 2508.01781](https://arxiv.org/abs/2508.01781)), we define the following categories:

### Category 1: Tool Discovery Failures

Issues locating or using the right tools and documentation.

| Sub-Category | Description | Detection Signal |
|--------------|-------------|------------------|
| **Tool Not Found** | Searched for tool that doesn't exist | Grep/Glob returns empty for tool-like patterns |
| **Wrong Tool Selected** | Used inappropriate tool for task | Tool call followed by immediate different tool for same goal |
| **Documentation Miss** | Failed to find relevant documentation | Multiple searches with decreasing specificity |
| **API Confusion** | Misunderstood tool parameters or behavior | Tool call error followed by retry with different params |
| **Tool Misuse** | Used tool in unintended way | Tool succeeds but output not used meaningfully |

**Example Trace Pattern:**
```
INEFFICIENCY: Tool Discovery - Documentation Miss
Sequence:
  1. Grep("authentication handler") → 0 results
  2. Grep("auth handler") → 0 results
  3. Grep("AuthHandler") → 0 results
  4. Glob("**/auth*.py") → 3 results (success)
Token cost: 2,340 (estimated 800 if direct glob)
Recommendation: Consider glob patterns before grep for file discovery
```

### Category 2: Decision Loops

Circular reasoning or repeated reconsideration of the same decision.

| Sub-Category | Description | Detection Signal |
|--------------|-------------|------------------|
| **Approach Oscillation** | Switching between approaches repeatedly | Same decision point visited 3+ times |
| **Analysis Paralysis** | Excessive deliberation before action | >500 tokens of reasoning without tool call |
| **Backtracking** | Undoing recent work to try different approach | Edit/Write followed by revert-like Edit/Write |
| **Confirmation Seeking** | Repeatedly verifying already-confirmed information | Same file read multiple times in session |
| **Scope Creep Loop** | Repeatedly expanding then constraining scope | Task todo items added then removed |

**Example Trace Pattern:**
```
INEFFICIENCY: Decision Loop - Approach Oscillation
Sequence:
  Turn 5: "I'll use a recursive approach"
  Turn 8: "Actually, an iterative approach would be better"
  Turn 12: "On reflection, recursive is cleaner"
  Turn 15: "Let me reconsider - iterative handles edge cases better"
Loop count: 4
Token cost: 3,200 in deliberation
Recommendation: Establish decision criteria upfront; commit after single evaluation
```

### Category 3: Direction and Planning Issues

Problems with task understanding, planning, or maintaining focus.

| Sub-Category | Description | Detection Signal |
|--------------|-------------|------------------|
| **Unclear Requirements** | Proceeded without clarifying ambiguity | AskUserQuestion not used when should have been |
| **Plan Drift** | Deviated from established plan without reason | Todo items completed out of order or skipped |
| **Scope Misunderstanding** | Work significantly over/under task scope | Deliverable doesn't match request |
| **Context Loss** | Forgot earlier context, repeated work | Re-read file already in context window |
| **Premature Optimization** | Added unnecessary complexity | Added features not in requirements |

**Example Trace Pattern:**
```
INEFFICIENCY: Direction - Scope Misunderstanding
Task: "Fix the typo in the README"
Actual work:
  - Fixed typo (requested)
  - Reformatted entire README (not requested)
  - Added new section on installation (not requested)
  - Updated badges (not requested)
Scope creep: 340% of requested work
Token cost: 4,100 (estimated 400 for actual task)
Recommendation: Clarify scope boundaries; avoid "while I'm here" improvements
```

### Category 4: Tool Execution Failures

Technical failures in tool invocation and response handling.

| Sub-Category | Description | Detection Signal |
|--------------|-------------|------------------|
| **Retry Storm** | Multiple retries of failing operation | Same tool call 3+ times with errors |
| **Parameter Errors** | Incorrect parameters to tool | Tool returns parameter validation error |
| **Timeout Issues** | Operations that exceed time limits | Bash command timeout |
| **Permission Errors** | Attempted operations without access | Permission denied errors |
| **Parse Failures** | Failed to parse tool output correctly | Incorrect extraction from tool result |

**Example Trace Pattern:**
```
INEFFICIENCY: Tool Execution - Retry Storm
Sequence:
  1. Bash("npm test") → Error: ENOENT
  2. Bash("npm test") → Error: ENOENT (same error)
  3. Bash("npm test") → Error: ENOENT (same error)
  4. Read("package.json") → Discovered no test script
  5. Bash("npm run test:unit") → Success
Wasted calls: 3
Token cost: 1,800 in retries
Recommendation: Investigate errors before retrying; check prerequisites
```

### Category 5: Reasoning Quality Issues

Problems with the quality of reasoning and conclusions.

| Sub-Category | Description | Detection Signal |
|--------------|-------------|------------------|
| **Hallucinated Context** | Referenced non-existent code/docs | Claims about files that don't exist |
| **Incorrect Inference** | Drew wrong conclusion from evidence | Conclusion contradicts evidence |
| **Overconfidence** | High confidence in incorrect assertion | Stated certainty followed by correction |
| **Underconfidence** | Excessive hedging on correct conclusions | Multiple qualifiers on accurate statements |
| **Missing Connections** | Failed to connect related information | Relevant context available but not used |

**Example Trace Pattern:**
```
INEFFICIENCY: Reasoning - Hallucinated Context
Statement: "Based on the AuthService class in src/auth/service.py..."
Reality: No such file exists; authentication is in src/users/auth.py
Detection: File path mentioned but never read; Glob finds no match
Impact: Subsequent reasoning based on false premise
Recommendation: Always verify file existence before referencing
```

### Category 6: Communication Inefficiencies

Problems in interaction quality with user or external systems.

| Sub-Category | Description | Detection Signal |
|--------------|-------------|------------------|
| **Unnecessary Clarification** | Asked questions with obvious answers | Question about information already in context |
| **Missing Clarification** | Didn't ask when should have | Proceeded with assumption that proved wrong |
| **Verbose Responses** | Excessive explanation for simple tasks | Response length >> task complexity |
| **Incomplete Updates** | Failed to communicate progress | Long silence during multi-step task |
| **Notification Spam** | Too many low-value notifications | Multiple notifications for single logical event |

### Category 7: Resource Efficiency

Token and computational resource usage patterns.

| Sub-Category | Description | Detection Signal |
|--------------|-------------|------------------|
| **Redundant Reads** | Read same file multiple times | Same file in multiple Read calls |
| **Excessive Context** | Loaded unnecessary context | Large file reads with minimal usage |
| **Verbose Tool Output** | Didn't limit output when possible | Full file read when head/grep would suffice |
| **Parallel Opportunity Missed** | Sequential calls that could be parallel | Independent tool calls in separate turns |
| **Unnecessary Exploration** | Explored irrelevant codebase areas | Reads/Greps with no bearing on task |

## Data Collection Architecture

### Trace Format

All LLM interactions are captured in a structured trace format:

```json
{
  "trace_id": "tr-20251128-abc123",
  "session_id": "sess-xyz789",
  "task_id": "bd-a3f8",
  "timestamp": "2025-11-28T10:30:00Z",
  "turn_number": 5,
  "event_type": "tool_call",
  "data": {
    "tool": "Grep",
    "parameters": {
      "pattern": "AuthHandler",
      "path": "/home/jwies/khan/webapp"
    },
    "result": {
      "status": "success",
      "matches": 0,
      "duration_ms": 245
    }
  },
  "context": {
    "tokens_in_context": 45000,
    "tokens_generated": 150,
    "reasoning_snippet": "Searching for authentication handler..."
  },
  "inefficiency_flags": ["tool_discovery_miss"]
}
```

### Collection Points

```
┌────────────────────────────────────────────────────────────────────┐
│                        Claude Code Session                          │
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐             │
│  │   Prompt    │───▶│  Reasoning  │───▶│  Tool Call  │             │
│  │   Input     │    │             │    │             │             │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘             │
│         │                  │                  │                     │
│         ▼                  ▼                  ▼                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Trace Collector                            │  │
│  │  - Token counts    - Reasoning patterns   - Tool results     │  │
│  │  - Timing          - Decision points      - Error types      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                │                                    │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                     ~/sharing/traces/                               │
│                                                                     │
│  traces/                                                           │
│  ├── 2025-11-28/                                                   │
│  │   ├── tr-abc123.jsonl    (raw trace events)                    │
│  │   ├── tr-abc123.meta     (session metadata)                    │
│  │   └── tr-abc123.summary  (computed summaries)                  │
│  └── index.json             (trace index for queries)             │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### Implementation: Hook-Based Collection

Use Claude Code hooks to capture interactions without modifying core behavior:

```bash
# .claude/hooks/post-tool-call.sh
#!/bin/bash
# Captures tool call results for trace analysis

TOOL_NAME="$1"
TOOL_RESULT="$2"
TRACE_FILE="$HOME/sharing/traces/$(date +%Y-%m-%d)/current.jsonl"

# Append structured trace event
jq -n \
  --arg tool "$TOOL_NAME" \
  --arg result "$TOOL_RESULT" \
  --arg timestamp "$(date -Iseconds)" \
  '{timestamp: $timestamp, tool: $tool, result: $result}' \
  >> "$TRACE_FILE"
```

### Inefficiency Detection Engine

```python
# inefficiency_detector.py

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

class InefficiencyCategory(Enum):
    TOOL_DISCOVERY = "tool_discovery"
    DECISION_LOOP = "decision_loop"
    DIRECTION = "direction"
    TOOL_EXECUTION = "tool_execution"
    REASONING = "reasoning"
    COMMUNICATION = "communication"
    RESOURCE = "resource"

@dataclass
class DetectedInefficiency:
    category: InefficiencyCategory
    sub_category: str
    severity: str  # low, medium, high
    trace_events: List[str]  # event IDs involved
    token_cost: int
    estimated_optimal_cost: int
    description: str
    recommendation: str

class InefficiencyDetector:
    """Analyzes traces to detect inefficiency patterns."""

    def detect_tool_discovery_failures(self, trace: List[dict]) -> List[DetectedInefficiency]:
        """Detect patterns indicating tool/doc discovery issues."""
        inefficiencies = []

        # Pattern: Multiple searches with decreasing specificity
        search_sequences = self._extract_search_sequences(trace)
        for seq in search_sequences:
            if len(seq) >= 3 and self._is_narrowing_pattern(seq):
                inefficiencies.append(DetectedInefficiency(
                    category=InefficiencyCategory.TOOL_DISCOVERY,
                    sub_category="documentation_miss",
                    severity="medium",
                    trace_events=[e["trace_id"] for e in seq],
                    token_cost=sum(e.get("tokens", 0) for e in seq),
                    estimated_optimal_cost=seq[0].get("tokens", 0),  # First try should work
                    description=f"Searched {len(seq)} times before finding target",
                    recommendation="Consider using glob patterns for file discovery"
                ))

        return inefficiencies

    def detect_decision_loops(self, trace: List[dict]) -> List[DetectedInefficiency]:
        """Detect circular reasoning or repeated decisions."""
        inefficiencies = []

        # Pattern: Same decision point visited multiple times
        decision_points = self._extract_decision_points(trace)
        for topic, occurrences in decision_points.items():
            if len(occurrences) >= 3:
                inefficiencies.append(DetectedInefficiency(
                    category=InefficiencyCategory.DECISION_LOOP,
                    sub_category="approach_oscillation",
                    severity="high",
                    trace_events=[o["trace_id"] for o in occurrences],
                    token_cost=sum(o.get("tokens", 0) for o in occurrences),
                    estimated_optimal_cost=occurrences[0].get("tokens", 0),
                    description=f"Reconsidered '{topic}' {len(occurrences)} times",
                    recommendation="Establish decision criteria upfront"
                ))

        return inefficiencies

    def detect_retry_storms(self, trace: List[dict]) -> List[DetectedInefficiency]:
        """Detect repeated failing tool calls."""
        inefficiencies = []

        consecutive_failures = []
        for event in trace:
            if event.get("event_type") == "tool_call":
                if event.get("data", {}).get("result", {}).get("status") == "error":
                    consecutive_failures.append(event)
                else:
                    if len(consecutive_failures) >= 3:
                        inefficiencies.append(DetectedInefficiency(
                            category=InefficiencyCategory.TOOL_EXECUTION,
                            sub_category="retry_storm",
                            severity="high",
                            trace_events=[e["trace_id"] for e in consecutive_failures],
                            token_cost=sum(e.get("tokens", 0) for e in consecutive_failures),
                            estimated_optimal_cost=consecutive_failures[0].get("tokens", 0),
                            description=f"{len(consecutive_failures)} consecutive failed calls",
                            recommendation="Investigate errors before retrying"
                        ))
                    consecutive_failures = []

        return inefficiencies
```

## Report Generation

### Weekly Inefficiency Report

Generated every Monday by the existing analyzer infrastructure:

```markdown
# JIB Inefficiency Report - Week of 2025-11-25

## Executive Summary

| Metric | This Week | Last Week | Change |
|--------|-----------|-----------|--------|
| Total Tasks | 23 | 19 | +21% |
| Total Tokens | 1.2M | 980K | +22% |
| Inefficiency Rate | 12.3% | 15.1% | -2.8% |
| Estimated Waste | 147K tokens | 148K tokens | -0.7% |

**Top Issue:** Tool Discovery failures account for 45% of inefficiencies.

## Inefficiency Breakdown

### By Category

```
Tool Discovery     ████████████████ 45%
Decision Loops     ██████████ 25%
Direction          ██████ 15%
Tool Execution     ████ 10%
Resource           ██ 5%
```

### Top 5 Specific Issues

1. **Documentation Miss** (34 occurrences)
   - Pattern: Multiple grep attempts before successful glob
   - Token waste: 41K
   - Recommendation: Update CLAUDE.md to prefer glob for file discovery

2. **Approach Oscillation** (12 occurrences)
   - Pattern: Switching between implementation approaches
   - Token waste: 38K
   - Recommendation: Add decision framework for common architectural choices

3. **Retry Storm** (8 occurrences)
   - Pattern: Repeated npm/pytest failures without investigation
   - Token waste: 24K
   - Recommendation: Add prerequisite checking guidance

4. **Redundant Reads** (23 occurrences)
   - Pattern: Same file read multiple times in session
   - Token waste: 18K
   - Recommendation: Improve context window management prompts

5. **Scope Creep** (5 occurrences)
   - Pattern: Added unrequested improvements
   - Token waste: 16K
   - Recommendation: Strengthen "stay focused" guidance in CLAUDE.md

## Trend Analysis

### Inefficiency Rate Over Time

```
Week 1:  ████████████████████ 20%
Week 2:  █████████████████ 17%
Week 3:  ███████████████ 15%
Week 4:  ████████████ 12%  ← This week
```

### Improvement Attribution

| Change Made | Impact |
|-------------|--------|
| Added glob-first guidance (Week 2) | -3% tool discovery failures |
| Added retry investigation prompt (Week 3) | -40% retry storms |
| Scope boundaries in CLAUDE.md (Week 4) | -50% scope creep |

## Detailed Session Analysis

### Session with Highest Inefficiency

**Session:** sess-abc123 (2025-11-26)
**Task:** Implement OAuth2 authentication
**Total Tokens:** 89,000
**Inefficiency Tokens:** 23,000 (26%)

**Timeline:**
```
10:00 - Task start
10:05 - [INEFFICIENCY] 6 grep attempts to find auth module
10:12 - Found auth module via glob
10:15 - [INEFFICIENCY] Approach oscillation: class vs functional
10:25 - Committed to class-based approach
10:30 - [INEFFICIENCY] Re-read same config file 4 times
10:45 - Task complete
```

**Recommendations for this session:**
1. Could have found auth module in 1 call with glob pattern
2. Decision framework would have resolved class/functional in 1 turn
3. Config file should have been read once and referenced from context

## Actionable Improvements

### High Priority (This Week)

1. **Update CLAUDE.md Section 4.2**
   - Add: "For file discovery, prefer glob patterns over grep"
   - Add: "When grep returns 0 results, try glob before re-grepping"

2. **Add Decision Framework**
   - Create: `.claude/rules/decision-frameworks.md`
   - Include: Common architectural decisions (class vs functional, etc.)
   - Include: Criteria for each decision type

### Medium Priority (Next Sprint)

3. **Improve Error Handling Guidance**
   - Add: "On tool error, investigate before retrying"
   - Add: "Check prerequisites (e.g., npm install) before running commands"

4. **Context Management**
   - Add: "Avoid re-reading files already in context"
   - Add: "Use file content from previous reads when available"

### Tracking

| Recommendation | Status | PR | Impact Measured |
|----------------|--------|-----|------------------|
| Glob-first guidance | Implemented | #45 | -3% tool discovery |
| Retry investigation | Implemented | #52 | -40% retry storms |
| Decision frameworks | In Progress | #67 | TBD |
| Context management | Planned | - | - |
```

### Report Delivery

Reports are delivered via the existing notification system:

```bash
# Generate and notify
analyze-inefficiency.py --week 2025-11-25 --output ~/sharing/reports/
slack-notify.py "Weekly Inefficiency Report Ready" \
  --file ~/sharing/reports/inefficiency-2025-11-25.md \
  --priority low
```

## Self-Improvement Loop

### Metacognitive Framework

Based on research on LLM metacognition ([Semantic Scholar](https://www.semanticscholar.org/paper/Metacognition-is-all-you-need-Using-Introspection-Toy-MacAdam/3e8e63bc80176ce913c9ee8f8e9e2472adfd7109)), we implement a three-component framework:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Self-Improvement Loop                             │
│                                                                      │
│  ┌──────────────────┐                                               │
│  │ 1. METACOGNITIVE │  "What patterns am I exhibiting?"             │
│  │    KNOWLEDGE     │  - Track own failure patterns                 │
│  │                  │  - Identify capability gaps                   │
│  │                  │  - Recognize decision tendencies              │
│  └────────┬─────────┘                                               │
│           │                                                          │
│           ▼                                                          │
│  ┌──────────────────┐                                               │
│  │ 2. METACOGNITIVE │  "What should I do differently?"              │
│  │    PLANNING      │  - Propose prompt improvements                │
│  │                  │  - Suggest tool usage changes                 │
│  │                  │  - Identify missing capabilities              │
│  └────────┬─────────┘                                               │
│           │                                                          │
│           ▼                                                          │
│  ┌──────────────────┐                                               │
│  │ 3. METACOGNITIVE │  "Did the changes help?"                      │
│  │    EVALUATION    │  - Measure improvement impact                 │
│  │                  │  - Validate hypotheses                        │
│  │                  │  - Refine or revert changes                   │
│  └──────────────────┘                                               │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Improvement Categories

**Category A: Prompt Refinements**
Changes to CLAUDE.md, rules files, or system prompts.

```
IMPROVEMENT PROPOSAL: Tool Discovery Guidance
─────────────────────────────────────────────
Evidence:
  - 34 documentation miss events this week
  - Average 3.2 grep attempts before success
  - 89% of successful finds used glob pattern

Proposed Change:
  File: CLAUDE.md
  Section: "Doing tasks"

  Add:
  > When searching for files or code locations:
  > 1. Start with glob patterns for file discovery (e.g., `**/auth*.py`)
  > 2. Use grep only when you know the file exists
  > 3. If grep returns 0 results, try glob before broadening grep pattern

Expected Impact:
  - Reduce tool discovery misses by 50%
  - Save ~20K tokens/week

Status: PENDING HUMAN REVIEW
```

**Category B: Tool Additions**
New tools or commands that would address gaps.

```
IMPROVEMENT PROPOSAL: File Existence Check Tool
───────────────────────────────────────────────
Evidence:
  - 8 hallucinated file reference events
  - Agent referenced files without verifying existence

Proposed Change:
  Add lightweight tool: FileExists(path) -> bool

  Use case:
  - Verify file before referencing in explanation
  - Quick check before detailed read

Expected Impact:
  - Eliminate hallucinated file references
  - Faster verification than full Read

Status: PENDING HUMAN REVIEW
```

**Category C: Decision Frameworks**
Structured approaches for common decision points.

```
IMPROVEMENT PROPOSAL: Implementation Approach Framework
───────────────────────────────────────────────────────
Evidence:
  - 12 approach oscillation events
  - 67% involved class vs functional decision
  - Average 3.5 back-and-forth turns

Proposed Framework:
  File: .claude/rules/decision-frameworks.md

  ## Class vs Functional Implementation

  Use CLASS-BASED when:
  - Multiple related methods share state
  - Need inheritance or polymorphism
  - Existing codebase uses classes for similar features

  Use FUNCTIONAL when:
  - Single responsibility, stateless operation
  - Pipeline/composition patterns fit naturally
  - Existing codebase uses functional style

  Decision process:
  1. Check existing similar code (follow convention)
  2. If no precedent, evaluate criteria above
  3. Commit after one evaluation pass
  4. Do not reconsider unless requirements change

Expected Impact:
  - Reduce approach oscillation by 75%
  - Save ~30K tokens/week

Status: PENDING HUMAN REVIEW
```

### Human-in-the-Loop Process

```
┌─────────────────────────────────────────────────────────────────────┐
│                 Improvement Review Process                           │
│                                                                      │
│  1. Weekly report generated with improvement proposals               │
│                           │                                          │
│                           ▼                                          │
│  2. Human reviews proposals via Slack                                │
│     - Approve: Implement change                                      │
│     - Modify: Adjust proposal, then implement                        │
│     - Reject: Log reason, suggest alternative                        │
│     - Defer: Revisit next week                                       │
│                           │                                          │
│                           ▼                                          │
│  3. Approved changes implemented                                     │
│     - CLAUDE.md updates via PR                                       │
│     - Rule file additions via PR                                     │
│     - Tool changes via implementation task                           │
│                           │                                          │
│                           ▼                                          │
│  4. Impact tracked in next week's report                             │
│     - Compare before/after metrics                                   │
│     - Validate improvement hypothesis                                │
│     - Roll back if negative impact                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Feedback Cycle Timeline

```
Week N:
  - Collect traces
  - Detect inefficiencies
  - Generate improvement proposals

Week N+1 (Monday):
  - Report delivered
  - Human reviews proposals
  - Approved changes implemented

Week N+1:
  - New behavior in effect
  - Continue collecting traces

Week N+2 (Monday):
  - Report includes impact analysis
  - Validate or revert changes
```

## Implementation Details

### Phase 1: Trace Collection (Week 1-2)

**Deliverables:**
- [ ] Define trace event schema
- [ ] Implement hook-based trace collection
- [ ] Create trace storage structure
- [ ] Build trace indexing for queries

**Files:**
- `jib-container/scripts/trace-collector.py`
- `jib-container/.claude/hooks/post-tool-call.sh`
- `~/sharing/traces/` directory structure

### Phase 2: Inefficiency Detection (Week 3-4)

**Deliverables:**
- [ ] Implement pattern detectors for each category
- [ ] Build inefficiency scoring algorithm
- [ ] Create detection configuration (thresholds, weights)
- [ ] Test against historical sessions (if available)

**Files:**
- `jib-container/analysis/inefficiency_detector.py`
- `jib-container/analysis/patterns/` (one file per category)
- `jib-container/config/inefficiency_thresholds.yaml`

### Phase 3: Report Generation (Week 5-6)

**Deliverables:**
- [ ] Build report generator
- [ ] Create report templates
- [ ] Integrate with existing analyzer timer
- [ ] Set up Slack delivery

**Files:**
- `jib-container/analysis/report_generator.py`
- `jib-container/templates/inefficiency_report.md`
- `host-services/inefficiency-analyzer.timer`

### Phase 4: Self-Improvement Loop (Week 7-8)

**Deliverables:**
- [ ] Build improvement proposal generator
- [ ] Create human review interface (Slack-based)
- [ ] Implement impact tracking
- [ ] Document improvement review process

**Files:**
- `jib-container/analysis/improvement_proposer.py`
- `jib-container/scripts/apply-improvement.py`
- `docs/runbooks/inefficiency-review-process.md`

### Integration with Existing Systems

**Conversation Analyzer Integration:**
The existing `conversation-analyzer.py` will be extended to:
1. Generate inefficiency-focused analysis
2. Include improvement proposals
3. Track impact of previous changes

**Beads Integration:**
Each detected inefficiency can optionally create a Beads task:
```bash
bd add "Investigate high retry rate in auth tasks" \
  --tags inefficiency,tool-execution \
  --notes "8 retry storm events detected this week"
```

**Codebase Analyzer Integration:**
Weekly codebase analysis can include:
- Gaps between documentation and actual code structure
- Missing documentation that causes discovery failures
- Outdated patterns that lead to confusion

## Consequences

### Benefits

1. **Visibility:** Clear understanding of where LLM processing is inefficient
2. **Data-Driven Improvement:** Evidence-based prompt and tool changes
3. **Cost Reduction:** Measurable token savings from improvements
4. **Faster Tasks:** Reduced time-to-completion as inefficiencies decrease
5. **Continuous Learning:** System gets better over time
6. **Proactive Issue Detection:** Identify problems before they become severe

### Drawbacks

1. **Overhead:** Trace collection adds some processing overhead
2. **Storage:** Traces consume disk space (mitigated by rotation)
3. **Analysis Time:** Weekly analysis requires compute resources
4. **Human Review:** Improvement proposals require human attention
5. **Complexity:** Adds another system to maintain

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Trace collection impacts performance | Async collection, batch writes |
| False positive inefficiency detection | Tune thresholds, human review |
| Storage growth | 30-day retention, compression |
| Over-fitting to specific patterns | Regular threshold review |
| Improvement proposals cause regressions | A/B testing, rollback capability |

## Decision Permanence

**Medium permanence.**

- The taxonomy and detection patterns will evolve as we learn more
- Report format can change without major impact
- Self-improvement loop is experimental and may be refined
- Core architecture (trace collection → detection → reporting) is stable

**Review cadence:**
- Weekly: Review reports, approve/reject proposals
- Monthly: Assess overall effectiveness, tune thresholds
- Quarterly: Review taxonomy, add new categories if needed

## Alternatives Considered

### Alternative 1: Real-Time Intervention

**Description:** Detect inefficiencies during execution and intervene.

**Pros:**
- Immediate correction
- No wasted tokens after detection

**Cons:**
- Complex to implement safely
- Risk of breaking valid workflows
- Interrupts agent flow

**Rejected because:** Too risky for initial implementation. May revisit after observational system proves value.

### Alternative 2: External Observability Platform

**Description:** Use commercial LLM observability tools (Langfuse, Datadog, etc.)

**Pros:**
- Production-ready
- Rich visualization
- Less development effort

**Cons:**
- Cost
- Data privacy (traces sent externally)
- Less customization for our taxonomy

**Rejected because:** Want to iterate on taxonomy without vendor constraints. May integrate later for visualization.

### Alternative 3: Pure Manual Review

**Description:** Human reviews conversation logs manually.

**Pros:**
- No development effort
- Human judgment

**Cons:**
- Doesn't scale
- Inconsistent categorization
- Time-consuming

**Rejected because:** Not sustainable as task volume grows.

### Alternative 4: Automated Prompt Modification

**Description:** System automatically updates prompts based on detected patterns.

**Pros:**
- Faster iteration
- No human bottleneck

**Cons:**
- Risk of prompt degradation
- Hard to debug issues
- Could optimize for metrics over quality

**Rejected because:** Human review essential for prompt changes. Automated proposals, manual approval.

## References

### Research Papers

- [Self-Reflection in LLM Agents: Effects on Problem-Solving Performance](https://arxiv.org/abs/2405.06682) - Renze & Guven, 2024
- [Metacognition is all you need? Using Introspection in Generative Agents](https://www.semanticscholar.org/paper/Metacognition-is-all-you-need-Using-Introspection-Toy-MacAdam/3e8e63bc80176ce913c9ee8f8e9e2472adfd7109) - Toy & MacAdam
- [Position: Truly Self-Improving Agents Require Intrinsic Metacognitive Learning](https://openreview.net/forum?id=4KhDd0Ozqe) - OpenReview, 2024
- [A Survey on Hallucination in Large Language Models](https://arxiv.org/abs/2311.05232) - arXiv, 2024
- [A comprehensive taxonomy of hallucinations in Large Language Models](https://arxiv.org/abs/2508.01781) - arXiv, 2025
- [LLMs are Imperfect, Then What? An Empirical Study on LLM Failures in Software Engineering](https://arxiv.org/html/2411.09916v1) - arXiv, 2024

### Industry Resources

- [LLM Observability Tools: 2025 Comparison](https://lakefs.io/blog/llm-observability-tools/)
- [An Introduction to Observability for LLM-based applications using OpenTelemetry](https://opentelemetry.io/blog/2024/llm-observability/)
- [LLM Observability | Datadog](https://www.datadoghq.com/product/llm-observability/)
- [AI Agent Observability with Langfuse](https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse)
- [7 Strategies To Solve LLM Reliability Challenges at Scale](https://galileo.ai/blog/production-llm-monitoring-strategies)
- [LLM Evaluation: Frameworks, Metrics, and Best Practices](https://www.superannotate.com/blog/llm-evaluation-guide)
- [A guide to agentic AI workflows in 2025](https://retool.com/blog/agentic-ai-workflows)
- [A Survey on LLM-Based Agentic Workflows and LLM-Profiled Components](https://arxiv.org/html/2406.05804v1)

### Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Autonomous-Software-Engineer](./in-progress/ADR-Autonomous-Software-Engineer.md) | Parent ADR; defines conversation analyzer |
| [ADR-Context-Sync-Strategy](./in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | Context availability affects tool discovery |
| [ADR-LLM-Documentation-Index-Strategy](./implemented/ADR-LLM-Documentation-Index-Strategy.md) | Documentation indexes directly address Tool Discovery Failures (Category 1); well-indexed docs reduce navigation inefficiencies |
| [ADR-Standardized-Logging-Interface](./not-implemented/ADR-Standardized-Logging-Interface.md) | Structured logging enables trace collection and inefficiency detection described in this ADR |
| [ADR-Continuous-System-Reinforcement](./not-implemented/ADR-Continuous-System-Reinforcement.md) | Complementary self-improvement mechanism; Reinforcement learns from breakages, Inefficiency learns from processing patterns |

---

**Last Updated:** 2025-11-28
**Next Review:** 2025-12-28 (Monthly review)
**Status:** Draft - Awaiting Review
