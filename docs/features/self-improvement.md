# Self-Improvement Features

LLM efficiency analysis, inefficiency detection, and automated optimization.

## Overview

JIB continuously analyzes its own performance to identify and fix inefficiencies:
- **Trace Collection**: Records every LLM tool call for analysis
- **Inefficiency Detection**: Identifies patterns like retry storms, redundant reads
- **Improvement Proposals**: Generates actionable fixes for human review
- **Beads Analysis**: Evaluates task tracking health

## Features

### LLM Trace Collector

**Purpose**: Collects structured traces of all LLM tool calls.

**Location**: `host-services/analysis/trace-collector/`

**Helper Scripts**:
```bash
# Setup
./host-services/analysis/trace-collector/setup.sh

# Query traces
python host-services/analysis/trace-collector/trace_reader.py list
python host-services/analysis/trace-collector/trace_reader.py query --tool-name Read
python host-services/analysis/trace-collector/trace_reader.py export --format json
```

**Data Collected**:
- Tool name and parameters
- Result and timing
- Context metrics (tokens, cost)
- Session metadata

**Output Location**: `~/.jib-sharing/traces/`

**Key Capabilities**:
- PostToolUse hook integration
- SessionStart/SessionEnd tracking
- JSONL format for streaming
- Tool categorization

### LLM Inefficiency Detector

**Purpose**: Analyzes traces to find processing inefficiencies.

**Location**: `host-services/analysis/inefficiency-detector/`

**Helper Scripts**:
```bash
# Setup
./host-services/analysis/inefficiency-detector/setup.sh

# Run analysis
python host-services/analysis/inefficiency-detector/inefficiency_detector.py analyze

# Generate weekly report
python host-services/analysis/inefficiency-detector/weekly_report_generator.py
```

**Detected Patterns**:

| Inefficiency | Description | Impact |
|--------------|-------------|--------|
| Tool Discovery Failures | Documentation misses, search failures | Wasted tokens |
| Retry Storms | >3 retries for same operation | Time waste |
| Redundant Reads | Same file read multiple times | Token waste |
| Excessive Context | Loading too much context at once | Cost increase |
| API Confusion | Wrong parameters, invalid calls | Failures |

**Detector Modules**:
- `tool_discovery_detector.py` - Finding/using tools
- `tool_execution_detector.py` - Technical failures
- `resource_efficiency_detector.py` - Token/compute waste

### Improvement Proposer

**Purpose**: Generates structured improvement proposals from detected inefficiencies.

**Location**: `host-services/analysis/inefficiency-detector/improvement_proposer.py`

**Proposal Format**:
```markdown
## Improvement Proposal: [Title]

**Inefficiency**: [Pattern detected]
**Impact**: [Token/time savings estimate]
**Solution**: [Specific fix]
**Implementation**:
- [ ] Step 1
- [ ] Step 2

**Expected Savings**: X tokens/session
```

### Impact Tracker

**Purpose**: Measures effectiveness of implemented improvements.

**Location**: `host-services/analysis/inefficiency-detector/impact_tracker.py`

**Tracked Metrics**:
- Token usage before/after
- Time to completion
- Error rates
- Retry frequency

### Weekly Report Generator

**Purpose**: Automated weekly inefficiency analysis with PR creation.

**Location**: `host-services/analysis/inefficiency-detector/weekly_report_generator.py`

**Schedule**: Weekly via systemd timer

**Output**:
- Inefficiency summary
- Trend analysis
- Proposed improvements
- PR for human review

### Beads Integration Analyzer

**Purpose**: Analyzes health of the Beads task tracking system.

**Location**: `host-services/analysis/beads-analyzer/`

**Helper Scripts**:
```bash
# Setup
./host-services/analysis/beads-analyzer/setup.sh

# Service management
systemctl --user status beads-analyzer.timer
systemctl --user start beads-analyzer.service

# Manual run
python host-services/analysis/beads-analyzer/beads-analyzer.py analyze
```

**Health Score (0-100)**:
- Task lifecycle management
- Context continuity
- Task quality (notes, labels)
- Issue detection

**Detected Issues**:
| Issue | Severity | Description |
|-------|----------|-------------|
| Task Abandonment | High | in_progress >24h with no updates |
| Missing Notes | Medium | Closed tasks with no notes |
| Missing Labels | Low | Tasks without source labels |
| Orphan Tasks | Medium | Tasks with no related work |

**Output**: Weekly health report as PR

### Conversation Analyzer Service

**Purpose**: Analyzes Slack/GitHub conversation patterns.

**Location**: `host-services/analysis/conversation-analyzer/`

**Schedule**: Weekly via systemd timer

**Analysis**:
- Communication quality
- Response times
- Task completion patterns
- Improvement opportunities

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Claude Code Session                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Tool calls → Hook Handler → Trace Collector           │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                 Trace Storage (JSONL)                        │
│                 ~/.jib-sharing/traces/                       │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│              Inefficiency Detector (Weekly)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │   Discovery  │ │  Execution   │ │  Resource    │        │
│  │   Detector   │ │  Detector    │ │  Detector    │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│              Improvement Proposer                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Templates → Proposals → PR for Human Review           │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│              Impact Tracker                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Measure before/after → Update effectiveness scores    │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Traces not being collected

1. Verify hook is installed: Check `.claude/hooks/`
2. Check trace directory exists: `~/.jib-sharing/traces/`
3. Review hook handler logs

### Inefficiency detector missing patterns

1. Ensure sufficient trace data (need full sessions)
2. Check detector configuration
3. Run with verbose mode: `--verbose`

### Beads analyzer reporting false positives

1. Review task lifecycle in context
2. Check time zone settings
3. Adjust thresholds in config

### Weekly reports not generating

1. Check timer: `systemctl --user status inefficiency-detector.timer`
2. Verify trace data exists
3. Check for errors in logs

## Related Documentation

- [ADR: LLM Inefficiency Reporting](../adr/implemented/ADR-LLM-Inefficiency-Reporting.md)
- [Beads Task Tracking](../reference/beads.md)
- [Prompt Caching](../reference/prompt-caching.md)

## Source Files

| Component | Path |
|-----------|------|
| Trace Collector | `host-services/analysis/trace-collector/` |
| Inefficiency Detector | `host-services/analysis/inefficiency-detector/` |
| Beads Analyzer | `host-services/analysis/beads-analyzer/` |
| Conversation Analyzer | `host-services/analysis/conversation-analyzer/` |
| Hook Handler | `host-services/analysis/trace-collector/hook_handler.py` |
| Improvement Proposer | `host-services/analysis/inefficiency-detector/improvement_proposer.py` |
| Impact Tracker | `host-services/analysis/inefficiency-detector/impact_tracker.py` |

---

*Auto-generated by Feature Analyzer*
