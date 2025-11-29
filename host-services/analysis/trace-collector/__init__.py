"""
LLM Trace Collector for Inefficiency Analysis

This package provides infrastructure for collecting and analyzing LLM tool call
traces to identify processing inefficiencies.

Components:
- schemas: Data structures for trace events, sessions, and indexes
- trace_collector: Core collection infrastructure
- hook_handler: Claude Code hook integration
- trace_reader: Query and analysis utilities

Usage:
    from trace_collector import TraceCollector, record_tool_call

    # Create a collector
    collector = TraceCollector()

    # Record a tool call
    collector.record_tool_call(
        tool_name="Grep",
        tool_input={"pattern": "...", "path": "..."},
        tool_result={"status": "success", "matches": 5}
    )

    # End session
    collector.end_session()

See ADR-LLM-Inefficiency-Reporting.md for design details.
"""

from schemas import (
    EventType,
    SessionMetadata,
    ToolCallParams,
    ToolCategory,
    ToolResult,
    TraceEvent,
    TraceIndex,
    TOOL_CATEGORIES,
)
from trace_collector import TraceCollector, get_collector, record_tool_call
from trace_reader import TraceReader

__all__ = [
    "EventType",
    "SessionMetadata",
    "ToolCallParams",
    "ToolCategory",
    "ToolResult",
    "TraceEvent",
    "TraceIndex",
    "TOOL_CATEGORIES",
    "TraceCollector",
    "TraceReader",
    "get_collector",
    "record_tool_call",
]
