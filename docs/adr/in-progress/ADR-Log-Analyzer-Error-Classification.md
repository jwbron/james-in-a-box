# ADR: Log Analyzer with Claude-Powered Error Classification

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Proposed:** December 2025
**Status:** In Progress

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Log Centralization](#log-centralization)
- [Error Classification](#error-classification)
- [Claude Integration](#claude-integration)
- [Implementation Plan](#implementation-plan)
- [Consequences](#consequences)
- [Related ADRs](#related-adrs)

## Context

### Background

Building on [ADR-Standardized-Logging-Interface](./ADR-Standardized-Logging-Interface.md), the jib system now has structured JSON logging across all components. However, logs are currently stored in multiple locations:

| Log Type | Location | Format |
|----------|----------|--------|
| Container logs | `~/.jib-sharing/container-logs/` | JSON (docker json-file driver) |
| Context sync | `~/context-sync/logs/` | Structured JSON (jib_logging) |
| LLM traces | `~/sharing/traces/` | JSONL (trace events) |
| Model output | `/var/log/jib/model_output/` | JSON (planned) |
| Host services | Various | Structured JSON (jib_logging) |

**Current Challenges:**

1. **No Centralized Access**: Logs scattered across locations; container cannot easily access host logs
2. **Manual Error Detection**: Errors must be found manually through grep/search
3. **No Error Classification**: Errors lack categorization (transient, configuration, bug, etc.)
4. **No Proactive Analysis**: No system to detect error patterns or recurring issues

### Requirements

1. **Centralized Log Storage**: Single location accessible from container and host
2. **Error Detection**: Automatic identification of errors across all log sources
3. **Smart Classification**: Use Claude to classify errors by type, severity, root cause
4. **Actionable Output**: Generate summaries and recommendations for error resolution
5. **Low Overhead**: Lightweight analysis that doesn't impact normal operations

## Decision

**Implement a centralized log aggregation system with Claude-powered error analysis.**

### Core Principles

1. **Aggregate, Don't Replace**: Copy/stream logs to central location; don't change how services log
2. **Structured Analysis**: Use jib_logging structured format for machine-parseable error extraction
3. **Claude for Classification**: Use Claude's reasoning for error categorization and root cause analysis
4. **Batch Processing**: Analyze logs periodically (not real-time) to reduce API costs
5. **Container-Accessible**: Central location mounted in jib containers

## Log Centralization

### Unified Log Directory

All logs aggregated to `~/.jib-sharing/logs/`:

```
~/.jib-sharing/logs/
├── aggregated/              # Combined logs from all sources
│   ├── 2025-12-01.jsonl     # Daily aggregated log files
│   └── 2025-12-02.jsonl
├── container/               # Symlink to container-logs
├── host-services/           # Symlink/copy of host service logs
├── analysis/                # Log analyzer output
│   ├── errors/              # Extracted error entries
│   │   └── 2025-12-01.jsonl
│   ├── classifications/     # Claude-classified errors
│   │   └── 2025-12-01.json
│   └── summaries/           # Daily/weekly summaries
│       └── 2025-12-01.md
└── index.json               # Log index for fast queries
```

### Log Aggregation Strategy

**Phase 1: Symlinks + Log Rotation**

Services continue logging to their current locations. Aggregator script:
1. Creates symlinks for easy navigation
2. Periodically copies/rotates logs to aggregated directory
3. Maintains unified index

```bash
# Aggregator adds entry to aggregated log
{
  "timestamp": "2025-12-01T12:34:56Z",
  "source": "context-sync",
  "source_file": "sync_20251201.log",
  "severity": "ERROR",
  "message": "GitHub API rate limit exceeded",
  ...original log fields...
}
```

**Phase 2: Unified File Handler (Future)**

Configure all services to use jib_logging with file handler pointing to central location.

### Container Mount

Update jib container to mount logs directory:

```python
# In jib script - add to mount configuration
"-v", f"{SHARING_DIR}/logs:/home/{user}/logs:ro,z"
```

Container can then read all logs at `~/logs/`.

## Error Classification

### Error Extraction

The log analyzer extracts errors based on:
1. **Severity**: `ERROR`, `CRITICAL` levels
2. **Exception patterns**: Stack traces, exception messages
3. **Known error indicators**: "failed", "timeout", "refused", etc.

### Classification Schema

```python
@dataclass
class ClassifiedError:
    """Error with Claude-generated classification."""

    # Original error info
    timestamp: str
    source: str
    message: str
    context: dict
    stack_trace: str | None

    # Claude classification
    category: str          # transient, configuration, bug, external, unknown
    severity: str          # low, medium, high, critical
    root_cause: str        # Claude's analysis of likely cause
    recommendation: str    # Suggested fix or investigation steps
    related_errors: list   # IDs of similar/related errors

    # Metadata
    classification_model: str
    classification_timestamp: str
```

### Error Categories

| Category | Description | Example |
|----------|-------------|---------|
| `transient` | Temporary failures, usually resolve on retry | Network timeout, rate limit |
| `configuration` | Misconfiguration requiring user action | Missing API key, wrong path |
| `bug` | Code defect requiring fix | Null pointer, logic error |
| `external` | External service failure | GitHub API down, auth server error |
| `resource` | Resource exhaustion | Disk full, memory limit |
| `unknown` | Cannot classify | Unclear error message |

## Claude Integration

### Analysis Prompt

```markdown
You are analyzing errors from a software system. For each error, provide:

1. **Category**: transient, configuration, bug, external, resource, or unknown
2. **Severity**: low (cosmetic), medium (degraded), high (broken feature), critical (system down)
3. **Root Cause**: Your analysis of the most likely cause
4. **Recommendation**: Specific steps to investigate or fix

Context about the system:
- jib is a Docker-sandboxed Claude Code agent
- Host services include: github-watcher, slack-receiver, context-sync
- Container runs Claude Code CLI for task processing

Error to analyze:
```

### Batch Processing

Analyze errors in batches to optimize API usage:

```python
class LogAnalyzer:
    """Claude-powered log analysis."""

    def analyze_errors(self, errors: list[dict], batch_size: int = 10) -> list[ClassifiedError]:
        """Classify a batch of errors using Claude.

        Groups similar errors to reduce API calls.
        Uses caching to avoid re-analyzing known patterns.
        """
        # Group by error signature (message template)
        groups = self._group_by_signature(errors)

        # Classify unique patterns
        classifications = {}
        for signature, examples in groups.items():
            if signature in self._cache:
                classifications[signature] = self._cache[signature]
            else:
                # Call Claude for classification
                result = self._classify_with_claude(examples[0], len(examples))
                classifications[signature] = result
                self._cache[signature] = result

        # Apply classifications to all errors
        return self._apply_classifications(errors, classifications)
```

### Cost Control

1. **Grouping**: Similar errors classified once
2. **Caching**: Known patterns cached (file-based, persistent)
3. **Batch limits**: Max 50 unique patterns per run
4. **Model selection**: Use Claude 3 Haiku for classification (fast, cheap)
5. **Frequency**: Run analysis hourly or on-demand

## Implementation Plan

### Phase 1: Log Centralization

1. Create `~/.jib-sharing/logs/` directory structure
2. Implement log aggregator script
3. Update jib container mounts
4. Add symlinks for navigation

### Phase 2: Error Extraction

1. Implement error extraction from aggregated logs
2. Create error index (by timestamp, source, severity)
3. Add CLI for error queries

### Phase 3: Claude Classification

1. Implement classification prompt
2. Add batch processing with caching
3. Generate classification reports
4. Add daily summary generation

### Phase 4: Integration

1. Hook into existing notification system
2. Generate alerts for critical/recurring errors
3. Add Slack notification for error summaries
4. Create container command for log analysis

## Consequences

### Positive

1. **Single Source of Truth**: All logs in one place
2. **Smart Analysis**: Claude provides insights humans might miss
3. **Reduced Debug Time**: Pre-classified errors with recommendations
4. **Pattern Detection**: Identify recurring issues before they escalate
5. **Container Access**: Agent can read logs for self-debugging

### Negative

1. **Storage Overhead**: Aggregated logs duplicate some data
2. **API Cost**: Claude classification has per-token cost
3. **Latency**: Batch processing means delayed classification
4. **Complexity**: Additional service to maintain

### Trade-offs

| Aspect | Current State | With Log Analyzer |
|--------|---------------|-------------------|
| Error discovery | Manual grep | Automatic extraction |
| Classification | Human judgment | Claude + human review |
| Root cause | Investigation required | Suggested by Claude |
| Response time | Hours to days | Minutes to hours |
| Cost | Developer time | API tokens |

## Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Standardized-Logging-Interface](./ADR-Standardized-Logging-Interface.md) | Foundation - provides structured logs this analyzer consumes |
| [ADR-LLM-Inefficiency-Reporting](../implemented/ADR-LLM-Inefficiency-Reporting.md) | Parallel effort - inefficiency detector uses similar trace analysis |
| [ADR-Autonomous-Software-Engineer](./ADR-Autonomous-Software-Engineer.md) | Context - defines observability requirements |

---

**Last Updated:** 2025-12-02
**Status:** In Progress
