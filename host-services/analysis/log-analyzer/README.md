# Log Analyzer

Claude-powered error detection and classification for jib logs.

See [ADR-Log-Analyzer-Error-Classification](../../../docs/adr/in-progress/ADR-Log-Analyzer-Error-Classification.md) for architecture details.

## Overview

The log analyzer provides:

1. **Log Aggregation**: Centralizes logs from multiple jib sources
2. **Error Extraction**: Identifies errors by severity, patterns, and exceptions
3. **Claude Classification**: Intelligent categorization with root cause analysis
4. **Summary Reports**: Daily summaries with recommendations

## Quick Start

```bash
# Run full analysis
cd ~/khan/james-in-a-box/host-services/analysis/log-analyzer
python -m log_analyzer.log_analyzer --analyze

# Aggregate logs only
python -m log_analyzer.log_analyzer --aggregate --hours 24

# Extract and classify errors
python -m log_analyzer.log_analyzer --classify --hours 12

# Generate summary
python -m log_analyzer.log_analyzer --summary
```

## Components

### `log_aggregator.py`

Collects logs from multiple sources:
- `~/.jib-sharing/container-logs/` - Container stdout/stderr
- `~/context-sync/logs/` - Context sync service
- `~/sharing/traces/` - LLM trace events

Output: `~/.jib-sharing/logs/aggregated/YYYY-MM-DD.jsonl`

### `error_extractor.py`

Identifies errors based on:
- Severity levels (ERROR, CRITICAL)
- Exception patterns (stack traces)
- Error keywords (failed, timeout, refused)

Output: `~/.jib-sharing/logs/analysis/errors/YYYY-MM-DD.jsonl`

### `error_classifier.py`

Uses Claude to classify each unique error pattern:
- **Category**: transient, configuration, bug, external, resource, unknown
- **Severity**: low, medium, high, critical
- **Root cause**: Analysis of likely cause
- **Recommendation**: Steps to fix

Features:
- Groups similar errors by signature
- Caches classifications to reduce API calls
- Batches requests for efficiency

Output: `~/.jib-sharing/logs/analysis/classifications/YYYY-MM-DD.json`

### `log_analyzer.py`

Main entry point that orchestrates the full pipeline:

```python
from log_analyzer import LogAnalyzer

analyzer = LogAnalyzer()
result = analyzer.analyze(hours=24)

# Result includes:
# - aggregated_file: Path to combined logs
# - errors_file: Path to extracted errors
# - classifications_file: Path to Claude classifications
# - summary_file: Path to summary report
# - summary: Dict with stats and recommendations
```

## Directory Structure

```
~/.jib-sharing/logs/
├── aggregated/              # Combined logs from all sources
│   └── 2025-12-01.jsonl
├── analysis/
│   ├── errors/              # Extracted error entries
│   │   └── 2025-12-01.jsonl
│   ├── classifications/     # Claude-classified errors
│   │   └── 2025-12-01.json
│   └── summaries/           # Daily summaries
│       ├── 2025-12-01.json
│       └── 2025-12-01.md
├── container/               # Symlink to container-logs
├── context-sync/            # Symlink to context-sync logs
└── index.json               # Log index
```

## Classification Categories

| Category | Description | Example |
|----------|-------------|---------|
| `transient` | Temporary, usually self-resolving | Network timeout, rate limit |
| `configuration` | User action required | Missing API key, wrong path |
| `bug` | Code defect | Null pointer, logic error |
| `external` | External service issue | GitHub API down |
| `resource` | Resource exhaustion | Disk full, OOM |
| `unknown` | Cannot classify | Unclear error message |

## Cost Management

Claude API calls are minimized through:

1. **Signature grouping**: Similar errors classified once
2. **Persistent cache**: Known patterns stored in `classification_cache.json`
3. **Batch limits**: `--max-calls` flag (default: 50 per run)
4. **Model selection**: Uses Haiku by default (fast, inexpensive)

## Container Access

Logs are mounted in jib containers at `~/logs/` (read-only):

```bash
# Inside container
ls ~/logs/
cat ~/logs/aggregated/2025-12-01.jsonl
cat ~/logs/analysis/summaries/2025-12-01.md
```

This enables the Claude agent to:
- Read its own error logs for debugging
- Analyze patterns in its behavior
- Self-diagnose issues

## Scheduled Analysis

To run analysis automatically, add a systemd timer or cron job:

```bash
# Cron example: Run hourly
0 * * * * cd ~/khan/james-in-a-box && ./host-services/.venv/bin/python -m host_services.analysis.log_analyzer.log_analyzer --analyze --hours 1 >> /var/log/jib/log-analyzer.log 2>&1
```

## Related

- [ADR-Standardized-Logging-Interface](../../../docs/adr/in-progress/ADR-Standardized-Logging-Interface.md) - Foundation logging library
- [ADR-LLM-Inefficiency-Reporting](../../../docs/adr/implemented/ADR-LLM-Inefficiency-Reporting.md) - Parallel analysis effort
- [Trace Collector](../trace-collector/) - LLM trace collection
