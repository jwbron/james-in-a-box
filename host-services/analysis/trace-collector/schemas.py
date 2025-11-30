"""
Trace Event Schemas for LLM Inefficiency Detection

Defines the data structures for capturing and analyzing LLM tool call traces.
These traces enable identification of processing inefficiencies like:
- Tool discovery failures (failed searches, wrong tool selection)
- Decision loops (approach oscillation, analysis paralysis)
- Retry storms (repeated failing tool calls)
- Resource inefficiency (redundant reads, excessive context loading)

Schema follows the design in ADR-LLM-Inefficiency-Reporting.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of events that can be traced."""

    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    REASONING = "reasoning"  # LLM reasoning/thinking blocks
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    COMPACT = "compact"  # Context compaction event


class ToolCategory(Enum):
    """Categories of tools for pattern analysis."""

    FILE_READ = "file_read"  # Read, Glob, Grep
    FILE_WRITE = "file_write"  # Write, Edit, NotebookEdit
    SEARCH = "search"  # Grep, Glob, WebSearch
    EXECUTION = "execution"  # Bash, BashOutput, KillShell
    COMMUNICATION = "communication"  # WebFetch, Skill, SlashCommand
    AGENT = "agent"  # Task (subagents)
    PLANNING = "planning"  # TodoWrite, EnterPlanMode, ExitPlanMode
    OTHER = "other"


# Map tool names to categories
TOOL_CATEGORIES: dict[str, ToolCategory] = {
    "Read": ToolCategory.FILE_READ,
    "Glob": ToolCategory.FILE_READ,
    "Grep": ToolCategory.SEARCH,
    "Write": ToolCategory.FILE_WRITE,
    "Edit": ToolCategory.FILE_WRITE,
    "NotebookEdit": ToolCategory.FILE_WRITE,
    "Bash": ToolCategory.EXECUTION,
    "BashOutput": ToolCategory.EXECUTION,
    "KillShell": ToolCategory.EXECUTION,
    "WebFetch": ToolCategory.COMMUNICATION,
    "WebSearch": ToolCategory.SEARCH,
    "Task": ToolCategory.AGENT,
    "TodoWrite": ToolCategory.PLANNING,
    "EnterPlanMode": ToolCategory.PLANNING,
    "ExitPlanMode": ToolCategory.PLANNING,
    "Skill": ToolCategory.COMMUNICATION,
    "SlashCommand": ToolCategory.COMMUNICATION,
}


@dataclass
class ToolCallParams:
    """Normalized tool call parameters for analysis."""

    # Common parameters
    path: str | None = None  # File/directory path
    pattern: str | None = None  # Search pattern (grep, glob)
    command: str | None = None  # Bash command

    # Original raw parameters
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result of a tool call."""

    status: str  # "success", "error", "timeout"
    error_type: str | None = None  # Type of error if failed
    error_message: str | None = None  # Error details
    match_count: int | None = None  # For search tools: number of matches
    file_count: int | None = None  # For glob: number of files found
    lines_returned: int | None = None  # For Read: lines read
    duration_ms: int = 0  # Tool execution time


@dataclass
class TraceEvent:
    """
    A single trace event capturing one LLM interaction.

    This is the core data structure for trace collection.
    Events are written as JSONL (one JSON object per line) for efficient streaming.
    """

    # Identity
    trace_id: str  # Unique event ID (e.g., "evt-20251129-abc123")
    session_id: str  # Session ID (e.g., "sess-xyz789")
    task_id: str | None  # Beads task ID if available

    # Timing
    timestamp: datetime
    turn_number: int  # Which turn in the conversation

    # Event data
    event_type: EventType
    tool_name: str | None = None  # For tool_call events
    tool_category: ToolCategory | None = None  # Derived from tool_name

    # Tool-specific data
    tool_params: ToolCallParams | None = None
    tool_result: ToolResult | None = None

    # Context metrics
    tokens_in_context: int = 0  # Estimated tokens in context window
    tokens_generated: int = 0  # Tokens generated in this turn

    # Prompt caching metrics (from Claude API usage field)
    cache_creation_input_tokens: int = 0  # Tokens written to cache
    cache_read_input_tokens: int = 0  # Tokens read from cache
    input_tokens: int = 0  # Regular input tokens (not cached)

    # Analysis hints (filled during collection or later analysis)
    reasoning_snippet: str | None = None  # Brief excerpt of reasoning
    inefficiency_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "turn_number": self.turn_number,
            "event_type": self.event_type.value,
            "tool_name": self.tool_name,
            "tool_category": self.tool_category.value if self.tool_category else None,
            "tokens_in_context": self.tokens_in_context,
            "tokens_generated": self.tokens_generated,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "input_tokens": self.input_tokens,
            "reasoning_snippet": self.reasoning_snippet,
            "inefficiency_flags": self.inefficiency_flags,
        }

        if self.tool_params:
            result["tool_params"] = {
                "path": self.tool_params.path,
                "pattern": self.tool_params.pattern,
                "command": self.tool_params.command,
                "raw": self.tool_params.raw,
            }

        if self.tool_result:
            result["tool_result"] = {
                "status": self.tool_result.status,
                "error_type": self.tool_result.error_type,
                "error_message": self.tool_result.error_message,
                "match_count": self.tool_result.match_count,
                "file_count": self.tool_result.file_count,
                "lines_returned": self.tool_result.lines_returned,
                "duration_ms": self.tool_result.duration_ms,
            }

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceEvent":
        """Create TraceEvent from dictionary."""
        tool_params = None
        if data.get("tool_params"):
            p = data["tool_params"]
            tool_params = ToolCallParams(
                path=p.get("path"),
                pattern=p.get("pattern"),
                command=p.get("command"),
                raw=p.get("raw", {}),
            )

        tool_result = None
        if data.get("tool_result"):
            r = data["tool_result"]
            tool_result = ToolResult(
                status=r["status"],
                error_type=r.get("error_type"),
                error_message=r.get("error_message"),
                match_count=r.get("match_count"),
                file_count=r.get("file_count"),
                lines_returned=r.get("lines_returned"),
                duration_ms=r.get("duration_ms", 0),
            )

        return cls(
            trace_id=data["trace_id"],
            session_id=data["session_id"],
            task_id=data.get("task_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            turn_number=data["turn_number"],
            event_type=EventType(data["event_type"]),
            tool_name=data.get("tool_name"),
            tool_category=ToolCategory(data["tool_category"])
            if data.get("tool_category")
            else None,
            tool_params=tool_params,
            tool_result=tool_result,
            tokens_in_context=data.get("tokens_in_context", 0),
            tokens_generated=data.get("tokens_generated", 0),
            cache_creation_input_tokens=data.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=data.get("cache_read_input_tokens", 0),
            input_tokens=data.get("input_tokens", 0),
            reasoning_snippet=data.get("reasoning_snippet"),
            inefficiency_flags=data.get("inefficiency_flags", []),
        )


@dataclass
class SessionMetadata:
    """
    Metadata about a trace collection session.

    Stored in a separate .meta file alongside the trace JSONL.
    """

    session_id: str
    task_id: str | None  # Beads task if known
    start_time: datetime
    end_time: datetime | None = None

    # Environment context
    working_directory: str | None = None
    repository: str | None = None
    branch: str | None = None

    # Aggregated metrics (computed at session end)
    total_events: int = 0
    total_tool_calls: int = 0
    tool_call_breakdown: dict[str, int] = field(default_factory=dict)  # tool_name -> count

    # Token metrics
    total_tokens_generated: int = 0
    peak_context_size: int = 0

    # Prompt caching metrics
    total_cache_creation_tokens: int = 0  # Total tokens written to cache
    total_cache_read_tokens: int = 0  # Total tokens read from cache
    total_input_tokens: int = 0  # Total regular input tokens
    cache_hit_rate: float = 0.0  # Percentage of input from cache

    # Outcome
    outcome: str | None = None  # "completed", "abandoned", "error"
    outcome_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "working_directory": self.working_directory,
            "repository": self.repository,
            "branch": self.branch,
            "total_events": self.total_events,
            "total_tool_calls": self.total_tool_calls,
            "tool_call_breakdown": self.tool_call_breakdown,
            "total_tokens_generated": self.total_tokens_generated,
            "peak_context_size": self.peak_context_size,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_input_tokens": self.total_input_tokens,
            "cache_hit_rate": self.cache_hit_rate,
            "outcome": self.outcome,
            "outcome_notes": self.outcome_notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMetadata":
        """Create SessionMetadata from dictionary."""
        return cls(
            session_id=data["session_id"],
            task_id=data.get("task_id"),
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            working_directory=data.get("working_directory"),
            repository=data.get("repository"),
            branch=data.get("branch"),
            total_events=data.get("total_events", 0),
            total_tool_calls=data.get("total_tool_calls", 0),
            tool_call_breakdown=data.get("tool_call_breakdown", {}),
            total_tokens_generated=data.get("total_tokens_generated", 0),
            peak_context_size=data.get("peak_context_size", 0),
            total_cache_creation_tokens=data.get("total_cache_creation_tokens", 0),
            total_cache_read_tokens=data.get("total_cache_read_tokens", 0),
            total_input_tokens=data.get("total_input_tokens", 0),
            cache_hit_rate=data.get("cache_hit_rate", 0.0),
            outcome=data.get("outcome"),
            outcome_notes=data.get("outcome_notes"),
        )


@dataclass
class TraceIndex:
    """
    Index of all trace sessions for efficient querying.

    Stored as index.json in the traces directory.
    """

    sessions: list[dict[str, Any]] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    def add_session(self, metadata: SessionMetadata) -> None:
        """Add a session to the index."""
        self.sessions.append(
            {
                "session_id": metadata.session_id,
                "task_id": metadata.task_id,
                "start_time": metadata.start_time.isoformat(),
                "end_time": metadata.end_time.isoformat() if metadata.end_time else None,
                "total_events": metadata.total_events,
                "total_tool_calls": metadata.total_tool_calls,
                "outcome": metadata.outcome,
                "repository": metadata.repository,
                "branch": metadata.branch,
            }
        )
        self.last_updated = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "sessions": self.sessions,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceIndex":
        """Create TraceIndex from dictionary."""
        return cls(
            sessions=data.get("sessions", []),
            last_updated=datetime.fromisoformat(data["last_updated"])
            if data.get("last_updated")
            else datetime.now(),
        )
