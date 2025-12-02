# LLM Trace Collector

Phase 1 implementation of [ADR-LLM-Inefficiency-Reporting](../../../docs/adr/not-implemented/ADR-LLM-Inefficiency-Reporting.md).

Collects structured traces of LLM tool calls for inefficiency analysis. This enables identification of:
- Tool discovery failures (failed searches, wrong tool selection)
- Decision loops (approach oscillation, analysis paralysis)
- Retry storms (repeated failing tool calls)
- Resource inefficiency (redundant reads, excessive context)

## Architecture

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
│  │              Hook Handler (PostToolUse, SessionEnd)           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                │                                    │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                     ~/sharing/traces/                               │
│                                                                     │
│  traces/                                                           │
│  ├── 2025-11-29/                                                   │
│  │   ├── sess-abc123.jsonl    (raw trace events)                   │
│  │   └── sess-abc123.meta     (session metadata)                   │
│  └── index.json               (trace index for queries)            │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

## Components

### `schemas.py`
Data structures for trace events:
- `TraceEvent`: Individual tool call or session event
- `SessionMetadata`: Session-level metadata and aggregates
- `TraceIndex`: Index of all sessions for querying

### `trace_collector.py`
Core collection infrastructure:
- `TraceCollector`: Main collector class
- `record_tool_call()`: Convenience function for hooks
- Automatic session management and indexing

### `hook_handler.py`
Claude Code hook integration:
- Handles PostToolUse, SessionStart, SessionEnd hooks
- Parses hook input and records events
- Designed for minimal overhead

### `trace_reader.py`
Query and analysis utilities:
- `TraceReader`: Read and query traces
- CLI for listing, showing, and exporting sessions
- Index rebuild capability

## Installation

### Automatic (Recommended)

The trace collector is automatically configured when you run the main jib setup:

```bash
cd ~/khan/james-in-a-box
./setup.sh
```

This will:
- Create the `~/sharing/traces/` storage directory
- Configure Claude Code hooks in `~/.claude/settings.json`

### Manual Installation

If you need to set up manually (e.g., without running full setup):

```bash
# Run the trace-collector setup script
cd ~/khan/james-in-a-box/host-services/analysis/trace-collector
./setup.sh
```

Or configure manually:

1. **Add hooks to `~/.claude/settings.json`:**

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/khan/james-in-a-box/host-services/analysis/trace-collector/hook_handler.py post-tool-use"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/khan/james-in-a-box/host-services/analysis/trace-collector/hook_handler.py session-end"
          }
        ]
      }
    ]
  }
}
```

2. **Create storage directory:**

```bash
mkdir -p ~/sharing/traces
```

### Verify Installation

```bash
# Run the collector test
python3 trace_collector.py

# Check the output
ls -la ~/sharing/traces/
```

## Usage

### CLI Commands

```bash
# List recent sessions
python3 trace_reader.py list

# Show session details
python3 trace_reader.py show <session_id>

# Show session with all events
python3 trace_reader.py show <session_id> --events

# Query sessions by date
python3 trace_reader.py list --since 2025-11-01 --until 2025-11-30

# Filter by task or repo
python3 trace_reader.py list --task bd-abc123 --repo jwbron/james-in-a-box

# Export session to JSON
python3 trace_reader.py export <session_id> -o session.json

# Rebuild index
python3 trace_reader.py reindex

# Show tool call summary
python3 trace_reader.py summary
```

### Programmatic Usage

```python
from trace_collector import TraceCollector

# Create collector
collector = TraceCollector(task_id="bd-abc123")

# Record tool calls
collector.record_tool_call(
    tool_name="Grep",
    tool_input={"pattern": "AuthHandler", "path": "/code"},
    tool_result={"status": "success", "matches": 0},
    duration_ms=245,
)

# End session
collector.end_session(outcome="completed")
```

```python
from trace_reader import TraceReader

reader = TraceReader()

# List sessions
sessions = reader.list_sessions(limit=10)

# Read session events
for event in reader.read_session_events("sess-abc123"):
    print(f"{event.tool_name}: {event.tool_result.status}")

# Get summary statistics
summary = reader.get_tool_call_summary()
print(f"Total calls: {summary['total_tool_calls']}")
```

## Trace Event Schema

Each trace event is stored as a JSON line:

```json
{
  "trace_id": "evt-abc12345",
  "session_id": "sess-20251129-xyz",
  "task_id": "bd-a3f8",
  "timestamp": "2025-11-29T10:30:00Z",
  "turn_number": 5,
  "event_type": "tool_call",
  "tool_name": "Grep",
  "tool_category": "search",
  "tool_params": {
    "path": "/home/user/code",
    "pattern": "AuthHandler",
    "raw": {"pattern": "AuthHandler", "path": "/home/user/code"}
  },
  "tool_result": {
    "status": "success",
    "match_count": 0,
    "duration_ms": 245
  },
  "tokens_in_context": 45000,
  "tokens_generated": 150,
  "inefficiency_flags": []
}
```

## Storage Layout

```
~/sharing/traces/
├── 2025-11-29/
│   ├── sess-20251129-abc123.jsonl  # Events (JSONL)
│   └── sess-20251129-abc123.meta   # Metadata (JSON)
├── 2025-11-28/
│   └── ...
├── index.json                      # Session index
└── config.yaml                     # Configuration (optional)
```

## Next Phases

This is Phase 1 (Trace Collection). Subsequent phases will add:

- **Phase 2: Inefficiency Detection** - Pattern detectors for each category
- **Phase 3: Report Generation** - Weekly reports with actionable insights
- **Phase 4: Self-Improvement Loop** - Feed learnings into prompt engineering

See the ADR for full details.

## Troubleshooting

### Traces not appearing

1. Check hooks are configured: `cat ~/.claude/settings.json | jq .hooks`
2. Check storage directory exists: `ls ~/sharing/traces/`
3. Check error log: `cat ~/sharing/logs/trace-collector-errors.log`

### Hook errors

Hooks are designed to fail silently to not block Claude Code. Check the error log for issues.

### Index out of sync

Run `python3 trace_reader.py reindex` to rebuild from trace files.
