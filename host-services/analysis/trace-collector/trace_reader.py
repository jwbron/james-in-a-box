#!/usr/bin/env python3
"""
Trace Reader and Query Utility

Provides utilities for reading, querying, and analyzing collected traces.
This is used by the inefficiency detection engine (Phase 2) to process traces.

Usage:
    # List all sessions
    python trace_reader.py list

    # Show session details
    python trace_reader.py show <session_id>

    # Query sessions by date range
    python trace_reader.py query --since 2025-11-01 --until 2025-11-30

    # Export session to JSON
    python trace_reader.py export <session_id> --output session.json

    # Rebuild index from trace files
    python trace_reader.py reindex
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from schemas import SessionMetadata, TraceEvent, TraceIndex


class TraceReader:
    """
    Reader for trace files with querying capabilities.
    """

    def __init__(self, traces_dir: Path | None = None):
        """
        Initialize trace reader.

        Args:
            traces_dir: Directory containing traces (default: ~/sharing/traces)
        """
        self.traces_dir = traces_dir or Path.home() / "sharing" / "traces"
        self._index: TraceIndex | None = None

    def _load_index(self) -> TraceIndex:
        """Load or create the trace index."""
        if self._index is not None:
            return self._index

        index_file = self.traces_dir / "index.json"
        if index_file.exists():
            with open(index_file) as f:
                self._index = TraceIndex.from_dict(json.load(f))
        else:
            self._index = TraceIndex()

        return self._index

    def list_sessions(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        task_id: str | None = None,
        repository: str | None = None,
        outcome: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        List sessions matching the given criteria.

        Args:
            since: Only sessions starting after this time
            until: Only sessions starting before this time
            task_id: Filter by Beads task ID
            repository: Filter by repository
            outcome: Filter by outcome ("completed", "abandoned", "error")
            limit: Maximum number of sessions to return

        Returns:
            List of session summaries
        """
        index = self._load_index()
        sessions = []

        for session in index.sessions:
            # Apply filters
            if task_id and session.get("task_id") != task_id:
                continue
            if repository and session.get("repository") != repository:
                continue
            if outcome and session.get("outcome") != outcome:
                continue

            start_time = datetime.fromisoformat(session["start_time"])
            if since and start_time < since:
                continue
            if until and start_time > until:
                continue

            sessions.append(session)

        # Sort by start time (newest first)
        sessions.sort(key=lambda s: s["start_time"], reverse=True)

        if limit:
            sessions = sessions[:limit]

        return sessions

    def get_session_metadata(self, session_id: str) -> SessionMetadata | None:
        """
        Get metadata for a specific session.

        Args:
            session_id: The session ID to look up

        Returns:
            SessionMetadata or None if not found
        """
        # Find the meta file
        for date_dir in sorted(self.traces_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue

            meta_file = date_dir / f"{session_id}.meta"
            if meta_file.exists():
                with open(meta_file) as f:
                    return SessionMetadata.from_dict(json.load(f))

        return None

    def read_session_events(self, session_id: str) -> Iterator[TraceEvent]:
        """
        Read all events for a session.

        Yields events in order as they were recorded.

        Args:
            session_id: The session ID to read

        Yields:
            TraceEvent objects
        """
        # Find the trace file
        trace_file = None
        for date_dir in sorted(self.traces_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue

            candidate = date_dir / f"{session_id}.jsonl"
            if candidate.exists():
                trace_file = candidate
                break

        if not trace_file:
            return

        with open(trace_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        yield TraceEvent.from_dict(data)
                    except (json.JSONDecodeError, KeyError) as e:
                        # Skip malformed lines
                        continue

    def get_session_events(self, session_id: str) -> list[TraceEvent]:
        """
        Get all events for a session as a list.

        Args:
            session_id: The session ID to read

        Returns:
            List of TraceEvent objects
        """
        return list(self.read_session_events(session_id))

    def rebuild_index(self) -> TraceIndex:
        """
        Rebuild the index from all trace files.

        Useful if the index gets out of sync with the actual files.

        Returns:
            The rebuilt TraceIndex
        """
        index = TraceIndex()

        for date_dir in sorted(self.traces_dir.iterdir()):
            if not date_dir.is_dir():
                continue

            for meta_file in date_dir.glob("*.meta"):
                try:
                    with open(meta_file) as f:
                        metadata = SessionMetadata.from_dict(json.load(f))
                        index.add_session(metadata)
                except Exception:
                    continue

        # Write updated index
        index_file = self.traces_dir / "index.json"
        with open(index_file, "w") as f:
            json.dump(index.to_dict(), f, indent=2)

        self._index = index
        return index

    def export_session(self, session_id: str) -> dict[str, Any]:
        """
        Export a session to a single JSON structure.

        Args:
            session_id: The session ID to export

        Returns:
            Dictionary containing metadata and all events
        """
        metadata = self.get_session_metadata(session_id)
        events = self.get_session_events(session_id)

        return {
            "metadata": metadata.to_dict() if metadata else None,
            "events": [e.to_dict() for e in events],
        }

    def get_tool_call_summary(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get aggregate statistics about tool calls.

        Args:
            since: Start of time range
            until: End of time range

        Returns:
            Dictionary with tool call statistics
        """
        sessions = self.list_sessions(since=since, until=until)

        total_calls = 0
        tool_counts: dict[str, int] = {}
        error_counts: dict[str, int] = {}
        total_sessions = len(sessions)

        for session_summary in sessions:
            session_id = session_summary["session_id"]
            metadata = self.get_session_metadata(session_id)

            if metadata:
                total_calls += metadata.total_tool_calls
                for tool, count in metadata.tool_call_breakdown.items():
                    tool_counts[tool] = tool_counts.get(tool, 0) + count

            # Count errors from events
            for event in self.read_session_events(session_id):
                if event.tool_result and event.tool_result.status == "error":
                    tool = event.tool_name or "unknown"
                    error_counts[tool] = error_counts.get(tool, 0) + 1

        return {
            "total_sessions": total_sessions,
            "total_tool_calls": total_calls,
            "tool_counts": tool_counts,
            "error_counts": error_counts,
            "most_used_tools": sorted(tool_counts.items(), key=lambda x: -x[1])[:10],
            "most_errors": sorted(error_counts.items(), key=lambda x: -x[1])[:5],
        }


def format_session_summary(session: dict[str, Any]) -> str:
    """Format a session summary for display."""
    start = session.get("start_time", "unknown")[:19]  # Trim to datetime
    outcome = session.get("outcome", "?")
    outcome_emoji = {"completed": "✅", "abandoned": "⚠️", "error": "❌"}.get(outcome, "❓")
    task = session.get("task_id", "no-task")
    repo = session.get("repository", "no-repo")
    events = session.get("total_events", 0)
    tools = session.get("total_tool_calls", 0)

    return f"{outcome_emoji} {session['session_id']} | {start} | {tools} tools | {events} events | {task} | {repo}"


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Trace Reader and Query Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List sessions")
    list_parser.add_argument("--since", help="Sessions since date (YYYY-MM-DD)")
    list_parser.add_argument("--until", help="Sessions until date (YYYY-MM-DD)")
    list_parser.add_argument("--task", help="Filter by task ID")
    list_parser.add_argument("--repo", help="Filter by repository")
    list_parser.add_argument("--outcome", choices=["completed", "abandoned", "error"])
    list_parser.add_argument("--limit", type=int, default=20, help="Max sessions to show")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show session details")
    show_parser.add_argument("session_id", help="Session ID to show")
    show_parser.add_argument("--events", action="store_true", help="Show all events")

    # Export command
    export_parser = subparsers.add_parser("export", help="Export session to JSON")
    export_parser.add_argument("session_id", help="Session ID to export")
    export_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # Reindex command
    subparsers.add_parser("reindex", help="Rebuild index from trace files")

    # Summary command
    summary_parser = subparsers.add_parser("summary", help="Show tool call summary")
    summary_parser.add_argument("--since", help="Sessions since date (YYYY-MM-DD)")
    summary_parser.add_argument("--until", help="Sessions until date (YYYY-MM-DD)")

    args = parser.parse_args()
    reader = TraceReader()

    if args.command == "list":
        since = datetime.fromisoformat(args.since) if args.since else None
        until = datetime.fromisoformat(args.until) if args.until else None

        sessions = reader.list_sessions(
            since=since,
            until=until,
            task_id=args.task,
            repository=args.repo,
            outcome=args.outcome,
            limit=args.limit,
        )

        if not sessions:
            print("No sessions found.")
            return

        print(f"Found {len(sessions)} sessions:\n")
        for session in sessions:
            print(format_session_summary(session))

    elif args.command == "show":
        metadata = reader.get_session_metadata(args.session_id)
        if not metadata:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)

        print(f"Session: {metadata.session_id}")
        print(f"Task: {metadata.task_id or 'none'}")
        print(f"Start: {metadata.start_time}")
        print(f"End: {metadata.end_time or 'ongoing'}")
        print(f"Outcome: {metadata.outcome or 'unknown'}")
        print(f"Repository: {metadata.repository or 'unknown'}")
        print(f"Branch: {metadata.branch or 'unknown'}")
        print(f"Working Dir: {metadata.working_directory or 'unknown'}")
        print()
        print(f"Total Events: {metadata.total_events}")
        print(f"Total Tool Calls: {metadata.total_tool_calls}")
        print(f"Peak Context Size: {metadata.peak_context_size:,} tokens")
        print(f"Tokens Generated: {metadata.total_tokens_generated:,}")
        print()
        print("Tool Breakdown:")
        for tool, count in sorted(metadata.tool_call_breakdown.items(), key=lambda x: -x[1]):
            print(f"  {tool}: {count}")

        if args.events:
            print("\nEvents:")
            events = reader.get_session_events(args.session_id)
            for event in events:
                status = ""
                if event.tool_result:
                    status = f" [{event.tool_result.status}]"
                print(
                    f"  {event.turn_number:3d}. {event.timestamp.strftime('%H:%M:%S')} "
                    f"{event.tool_name or event.event_type.value}{status}"
                )

    elif args.command == "export":
        data = reader.export_session(args.session_id)
        if not data["metadata"]:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)

        output = json.dumps(data, indent=2, default=str)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Exported to {args.output}")
        else:
            print(output)

    elif args.command == "reindex":
        print("Rebuilding trace index...")
        index = reader.rebuild_index()
        print(f"Indexed {len(index.sessions)} sessions")

    elif args.command == "summary":
        since = datetime.fromisoformat(args.since) if args.since else None
        until = datetime.fromisoformat(args.until) if args.until else None

        summary = reader.get_tool_call_summary(since=since, until=until)

        print("Trace Summary")
        print("=" * 40)
        print(f"Total Sessions: {summary['total_sessions']}")
        print(f"Total Tool Calls: {summary['total_tool_calls']}")
        print()
        print("Most Used Tools:")
        for tool, count in summary["most_used_tools"]:
            print(f"  {tool}: {count}")
        print()
        if summary["most_errors"]:
            print("Most Errors:")
            for tool, count in summary["most_errors"]:
                print(f"  {tool}: {count}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
