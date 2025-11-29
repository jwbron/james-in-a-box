#!/usr/bin/env python3
"""
LLM Trace Collector for jib (James-in-a-Box)

Collects structured traces of LLM tool calls for inefficiency analysis.
This module provides the core collection infrastructure that hooks into
Claude Code's PostToolUse events.

Design principles (from ADR):
- Observe, Don't Block: Collection is passive, never impacts execution
- Efficient Storage: JSONL format for streaming writes
- Queryable: Index enables fast lookups by session, date, task

Usage:
    # From Claude Code PostToolUse hook
    from trace_collector import TraceCollector

    collector = TraceCollector()
    collector.record_tool_call(
        tool_name="Grep",
        tool_input={"pattern": "AuthHandler", "path": "/home/user/code"},
        tool_result={"status": "success", "matches": 0}
    )

Storage layout:
    ~/sharing/traces/
    ├── 2025-11-29/
    │   ├── sess-abc123.jsonl    # Raw trace events
    │   └── sess-abc123.meta     # Session metadata
    ├── index.json               # Index for queries
    └── config.yaml              # Collection configuration
"""

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from schemas import (
    TOOL_CATEGORIES,
    EventType,
    SessionMetadata,
    ToolCallParams,
    ToolCategory,
    ToolResult,
    TraceEvent,
    TraceIndex,
)


class TraceCollector:
    """
    Collects and stores LLM tool call traces.

    Designed for minimal overhead. Each hook invocation is a separate process,
    so this collector does not maintain state across calls. Session correlation
    is achieved through session_id passed via CLAUDE_SESSION_ID environment
    variable or hook input.
    """

    def __init__(
        self,
        traces_dir: Path | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ):
        """
        Initialize trace collector.

        Args:
            traces_dir: Directory for trace storage (default: ~/sharing/traces)
            session_id: Explicit session ID (auto-generated if not provided)
            task_id: Beads task ID if available
        """
        self.traces_dir = traces_dir or Path.home() / "sharing" / "traces"
        self.session_id = session_id or self._generate_session_id()
        self.task_id = task_id

        # Session state
        self.turn_number = 0
        self.events: list[TraceEvent] = []
        self.metadata: SessionMetadata | None = None

        # Initialize storage
        self._init_storage()

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Add some randomness from container ID or PID
        container_id = os.environ.get("HOSTNAME", str(os.getpid()))[:8]
        return f"sess-{timestamp}-{container_id}"

    def _generate_trace_id(self) -> str:
        """Generate a unique trace event ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        hash_input = f"{self.session_id}-{self.turn_number}-{timestamp}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        return f"evt-{short_hash}"

    def _init_storage(self) -> None:
        """Initialize trace storage directories and files."""
        # Create base traces directory
        self.traces_dir.mkdir(parents=True, exist_ok=True)

        # Create date subdirectory
        self.date_dir = self.traces_dir / datetime.now().strftime("%Y-%m-%d")
        self.date_dir.mkdir(parents=True, exist_ok=True)

        # Initialize trace file
        self.trace_file = self.date_dir / f"{self.session_id}.jsonl"
        self.meta_file = self.date_dir / f"{self.session_id}.meta"

        # Initialize session metadata
        self.metadata = SessionMetadata(
            session_id=self.session_id,
            task_id=self.task_id,
            start_time=datetime.now(),
            working_directory=os.getcwd(),
            repository=self._get_repository(),
            branch=self._get_branch(),
        )

        # Write initial metadata
        self._write_metadata()

    def _get_repository(self) -> str | None:
        """Get current git repository name."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Extract repo name from URL
                match = re.search(r"[:/]([^/]+/[^/.]+)(?:\.git)?$", url)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def _get_branch(self) -> str | None:
        """Get current git branch."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass
        return None

    def _write_metadata(self) -> None:
        """Write session metadata to file."""
        if self.metadata:
            try:
                with open(self.meta_file, "w") as f:
                    json.dump(self.metadata.to_dict(), f, indent=2)
            except OSError:
                # Fail silently - don't let metadata write failures break collection
                pass

    def _append_event(self, event: TraceEvent) -> None:
        """Append event to trace file."""
        try:
            with open(self.trace_file, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except OSError:
            # Fail silently - don't let write failures break the hook
            pass

    def _extract_params(self, tool_name: str, tool_input: dict[str, Any]) -> ToolCallParams:
        """Extract normalized parameters from tool input."""
        params = ToolCallParams(raw=tool_input.copy())

        # Extract path-like parameters
        if "file_path" in tool_input:
            params.path = tool_input["file_path"]
        elif "path" in tool_input:
            params.path = tool_input["path"]
        elif "notebook_path" in tool_input:
            params.path = tool_input["notebook_path"]

        # Extract pattern parameters
        if "pattern" in tool_input:
            params.pattern = tool_input["pattern"]

        # Extract command
        if "command" in tool_input:
            params.command = tool_input["command"]

        return params

    def _parse_result(self, tool_name: str, tool_result: dict[str, Any] | str) -> ToolResult:
        """Parse tool result into normalized structure."""
        # Handle string results (success messages)
        if isinstance(tool_result, str):
            # Check for error indicators
            if "error" in tool_result.lower() or "failed" in tool_result.lower():
                return ToolResult(
                    status="error",
                    error_message=tool_result[:500],  # Truncate long errors
                )
            return ToolResult(status="success")

        # Handle dict results
        status = "success"
        error_type = None
        error_message = None
        match_count = None
        file_count = None
        lines_returned = None

        # Check for error status
        if tool_result.get("error") or tool_result.get("status") == "error":
            status = "error"
            error_message = tool_result.get("error") or tool_result.get("message", "Unknown error")
            error_type = tool_result.get("error_type", "unknown")

        # Extract counts for search tools
        if tool_name in ("Grep", "Glob"):
            if "matches" in tool_result:
                match_count = tool_result["matches"]
            elif "files" in tool_result:
                file_count = (
                    len(tool_result["files"]) if isinstance(tool_result["files"], list) else None
                )

            # No matches might indicate search failure
            if match_count == 0 or file_count == 0:
                # This isn't an error, but we note it for pattern analysis
                pass

        # Extract line count for Read
        if tool_name == "Read" and "content" in tool_result:
            content = tool_result.get("content", "")
            if isinstance(content, str):
                lines_returned = content.count("\n") + 1

        return ToolResult(
            status=status,
            error_type=error_type,
            error_message=error_message,
            match_count=match_count,
            file_count=file_count,
            lines_returned=lines_returned,
        )

    def record_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_result: dict[str, Any] | str | None = None,
        duration_ms: int = 0,
        tokens_in_context: int = 0,
        tokens_generated: int = 0,
        reasoning_snippet: str | None = None,
    ) -> TraceEvent:
        """
        Record a tool call event.

        This is the main entry point for the PostToolUse hook.

        Args:
            tool_name: Name of the tool (e.g., "Grep", "Bash")
            tool_input: Tool input parameters
            tool_result: Tool result (optional, may be added later)
            duration_ms: Execution time in milliseconds
            tokens_in_context: Current context window size
            tokens_generated: Tokens generated in this turn
            reasoning_snippet: Brief excerpt of LLM reasoning

        Returns:
            The recorded TraceEvent
        """
        self.turn_number += 1

        # Determine tool category
        category = TOOL_CATEGORIES.get(tool_name, ToolCategory.OTHER)

        # Extract normalized parameters
        params = self._extract_params(tool_name, tool_input)

        # Parse result if provided
        result = None
        if tool_result is not None:
            result = self._parse_result(tool_name, tool_result)
            result.duration_ms = duration_ms

        # Create trace event
        event = TraceEvent(
            trace_id=self._generate_trace_id(),
            session_id=self.session_id,
            task_id=self.task_id,
            timestamp=datetime.now(),
            turn_number=self.turn_number,
            event_type=EventType.TOOL_CALL,
            tool_name=tool_name,
            tool_category=category,
            tool_params=params,
            tool_result=result,
            tokens_in_context=tokens_in_context,
            tokens_generated=tokens_generated,
            reasoning_snippet=reasoning_snippet,
        )

        # Store and persist
        self.events.append(event)
        self._append_event(event)

        # Update metadata
        if self.metadata:
            self.metadata.total_events += 1
            self.metadata.total_tool_calls += 1
            self.metadata.tool_call_breakdown[tool_name] = (
                self.metadata.tool_call_breakdown.get(tool_name, 0) + 1
            )
            self.metadata.total_tokens_generated += tokens_generated
            self.metadata.peak_context_size = max(
                self.metadata.peak_context_size, tokens_in_context
            )

        return event

    def record_session_event(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
    ) -> TraceEvent:
        """
        Record a session-level event (start, end, compact).

        Args:
            event_type: Type of session event
            data: Additional event data

        Returns:
            The recorded TraceEvent
        """
        self.turn_number += 1

        event = TraceEvent(
            trace_id=self._generate_trace_id(),
            session_id=self.session_id,
            task_id=self.task_id,
            timestamp=datetime.now(),
            turn_number=self.turn_number,
            event_type=event_type,
        )

        self.events.append(event)
        self._append_event(event)

        if self.metadata:
            self.metadata.total_events += 1

        return event

    def end_session(
        self,
        outcome: str = "completed",
        outcome_notes: str | None = None,
    ) -> None:
        """
        End the trace collection session.

        Finalizes metadata and updates the index.

        Args:
            outcome: Session outcome ("completed", "abandoned", "error")
            outcome_notes: Additional notes about the outcome
        """
        if self.metadata:
            self.metadata.end_time = datetime.now()
            self.metadata.outcome = outcome
            self.metadata.outcome_notes = outcome_notes
            self._write_metadata()

            # Update index
            self._update_index()

    def _update_index(self) -> None:
        """Update the trace index with this session."""
        index_file = self.traces_dir / "index.json"

        # Load existing index
        index = TraceIndex()
        if index_file.exists():
            try:
                with open(index_file) as f:
                    index = TraceIndex.from_dict(json.load(f))
            except Exception:
                pass

        # Add this session
        if self.metadata:
            index.add_session(self.metadata)

        # Write updated index
        try:
            with open(index_file, "w") as f:
                json.dump(index.to_dict(), f, indent=2)
        except OSError:
            # Fail silently - don't let index write failures break collection
            pass

    def get_events(self) -> list[TraceEvent]:
        """Get all events from this session."""
        return self.events.copy()


# Singleton instance for use in hooks
_collector_instance: TraceCollector | None = None


def get_collector() -> TraceCollector:
    """Get or create the global trace collector instance."""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = TraceCollector()
    return _collector_instance


def record_tool_call(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_result: dict[str, Any] | str | None = None,
    duration_ms: int = 0,
) -> TraceEvent:
    """
    Convenience function for recording a tool call.

    Used by the PostToolUse hook.
    """
    return get_collector().record_tool_call(
        tool_name=tool_name,
        tool_input=tool_input,
        tool_result=tool_result,
        duration_ms=duration_ms,
    )


if __name__ == "__main__":
    # Test the collector
    import sys

    collector = TraceCollector()

    # Simulate some tool calls
    collector.record_tool_call(
        tool_name="Grep",
        tool_input={"pattern": "AuthHandler", "path": "/home/user/code"},
        tool_result={"status": "success", "matches": 0},
        duration_ms=245,
    )

    collector.record_tool_call(
        tool_name="Glob",
        tool_input={"pattern": "**/auth*.py", "path": "/home/user/code"},
        tool_result={"files": ["auth.py", "auth_handler.py", "auth_utils.py"]},
        duration_ms=120,
    )

    collector.record_tool_call(
        tool_name="Read",
        tool_input={"file_path": "/home/user/code/auth.py"},
        tool_result={"content": "# Auth module\nclass Auth:\n    pass\n"},
        duration_ms=50,
    )

    collector.end_session(outcome="completed", outcome_notes="Test session")

    print(f"Session ID: {collector.session_id}")
    print(f"Trace file: {collector.trace_file}")
    print(f"Events recorded: {len(collector.events)}")
    print("\nEvents:")
    for event in collector.events:
        print(f"  - {event.tool_name}: {event.tool_result.status if event.tool_result else 'N/A'}")

    sys.exit(0)
