#!/usr/bin/env python3
"""
Claude Code Hook Handler for Trace Collection

This script is designed to be called from Claude Code hooks (PostToolUse, SessionEnd).
It receives hook input via stdin and records trace events.

Usage in ~/.claude/settings.json:
{
  "hooks": {
    "PostToolUse": [
      {
        "type": "command",
        "command": "python3 ~/khan/james-in-a-box/host-services/analysis/trace-collector/hook_handler.py post-tool-use"
      }
    ],
    "SessionEnd": [
      {
        "type": "command",
        "command": "python3 ~/khan/james-in-a-box/host-services/analysis/trace-collector/hook_handler.py session-end"
      }
    ]
  }
}

Hook Input Format (JSON via stdin):

PostToolUse:
{
    "session_id": "...",
    "tool_name": "Grep",
    "tool_input": {"pattern": "...", "path": "..."},
    "tool_result": {...},
    "tool_use_id": "..."
}

SessionEnd:
{
    "session_id": "...",
    "transcript_path": "..."
}
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path


# Ensure we can import from the same directory
sys.path.insert(0, str(Path(__file__).parent))

try:
    from trace_collector import TraceCollector
    from schemas import EventType
except ImportError as e:
    # Fail silently to not block Claude Code
    print(json.dumps({"continue": True, "suppress": True}))
    sys.exit(0)


# Session collectors by session_id
_collectors: dict[str, TraceCollector] = {}


def get_or_create_collector(session_id: str, task_id: str | None = None) -> TraceCollector:
    """Get existing collector for session or create new one."""
    if session_id not in _collectors:
        _collectors[session_id] = TraceCollector(
            session_id=session_id,
            task_id=task_id,
        )
    return _collectors[session_id]


def handle_post_tool_use(hook_input: dict) -> dict:
    """
    Handle PostToolUse hook event.

    Records the tool call in the trace collector.
    """
    session_id = hook_input.get("session_id", f"unknown-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    tool_name = hook_input.get("tool_name", "unknown")
    tool_input = hook_input.get("tool_input", {})
    tool_result = hook_input.get("tool_result")

    # Get or create collector
    collector = get_or_create_collector(session_id)

    # Calculate duration if timing info available
    duration_ms = 0
    if "start_time" in hook_input and "end_time" in hook_input:
        try:
            start = datetime.fromisoformat(hook_input["start_time"])
            end = datetime.fromisoformat(hook_input["end_time"])
            duration_ms = int((end - start).total_seconds() * 1000)
        except (ValueError, TypeError):
            pass

    # Record the tool call
    try:
        collector.record_tool_call(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result,
            duration_ms=duration_ms,
        )
    except Exception as e:
        # Log error but don't fail the hook
        error_log = Path.home() / "sharing" / "logs" / "trace-collector-errors.log"
        error_log.parent.mkdir(parents=True, exist_ok=True)
        with open(error_log, "a") as f:
            f.write(f"{datetime.now().isoformat()} ERROR: {e}\n")

    # Always return continue=True to not block Claude Code
    return {"continue": True}


def handle_session_end(hook_input: dict) -> dict:
    """
    Handle SessionEnd hook event.

    Finalizes the trace session and updates the index.
    """
    session_id = hook_input.get("session_id")

    if session_id and session_id in _collectors:
        collector = _collectors[session_id]

        # Determine outcome
        outcome = "completed"
        outcome_notes = None

        # Check if there's a transcript path we can reference
        transcript_path = hook_input.get("transcript_path")
        if transcript_path:
            outcome_notes = f"Transcript: {transcript_path}"

        try:
            collector.end_session(outcome=outcome, outcome_notes=outcome_notes)
        except Exception as e:
            # Log error but don't fail
            error_log = Path.home() / "sharing" / "logs" / "trace-collector-errors.log"
            error_log.parent.mkdir(parents=True, exist_ok=True)
            with open(error_log, "a") as f:
                f.write(f"{datetime.now().isoformat()} SESSION_END ERROR: {e}\n")

        # Clean up
        del _collectors[session_id]

    return {"continue": True}


def handle_session_start(hook_input: dict) -> dict:
    """
    Handle SessionStart hook event.

    Initializes a new trace session.
    """
    session_id = hook_input.get("session_id", f"sess-{datetime.now().strftime('%Y%m%d%H%M%S')}")

    # Check for task_id in environment or hook input
    task_id = hook_input.get("task_id") or os.environ.get("BEADS_TASK_ID")

    # Create collector
    collector = get_or_create_collector(session_id, task_id=task_id)

    # Record session start event
    collector.record_session_event(EventType.SESSION_START)

    return {"continue": True}


def main():
    """Main entry point for hook handler."""
    if len(sys.argv) < 2:
        print("Usage: hook_handler.py <event-type>", file=sys.stderr)
        print("  event-type: post-tool-use | session-end | session-start", file=sys.stderr)
        # Return valid hook response to not block Claude Code
        print(json.dumps({"continue": True}))
        sys.exit(0)

    event_type = sys.argv[1].lower().replace("-", "_")

    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        hook_input = {}

    # Dispatch to appropriate handler
    handlers = {
        "post_tool_use": handle_post_tool_use,
        "session_end": handle_session_end,
        "session_start": handle_session_start,
    }

    handler = handlers.get(event_type)
    if handler:
        result = handler(hook_input)
    else:
        result = {"continue": True}

    # Output hook response
    print(json.dumps(result))


if __name__ == "__main__":
    main()
