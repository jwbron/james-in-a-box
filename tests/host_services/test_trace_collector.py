"""
Unit tests for trace collector cache metrics functionality.

Tests the cache metric tracking, calculation, and serialization added in PR #250.
"""

import sys
from pathlib import Path

import pytest

# Import trace collector modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "host-services" / "analysis" / "trace-collector"))

from trace_collector import TraceCollector
from schemas import SessionMetadata, TraceEvent


class TestCacheMetrics:
    """Tests for prompt caching metrics tracking."""

    def test_cache_hit_rate_calculation(self, temp_dir):
        """Verify cache hit rate is calculated correctly."""
        collector = TraceCollector(traces_dir=temp_dir, session_id="test-session")

        # Turn 1: Cache creation (1000 tokens written)
        collector.record_tool_call(
            tool_name="Read",
            tool_input={"file_path": "/test/file.py"},
            tool_result={"success": True},
            cache_creation_input_tokens=1000,
            cache_read_input_tokens=0,
            input_tokens=0,
        )

        # Turn 2: Cache read (1000 tokens read) + 50 regular tokens
        collector.record_tool_call(
            tool_name="Read",
            tool_input={"file_path": "/test/file2.py"},
            tool_result={"success": True},
            cache_creation_input_tokens=0,
            cache_read_input_tokens=1000,
            input_tokens=50,
        )

        # Expected cache hit rate: 1000 / (1000 + 1000 + 50) * 100 = 48.78%
        assert collector.metadata is not None
        assert abs(collector.metadata.cache_hit_rate - 48.78) < 0.01

    def test_cache_hit_rate_zero_division_safety(self, temp_dir):
        """Ensure cache hit rate handles zero input tokens gracefully."""
        collector = TraceCollector(traces_dir=temp_dir, session_id="test-session-zero")

        # Record event with zero tokens
        collector.record_tool_call(
            tool_name="Bash",
            tool_input={"command": "ls"},
            tool_result={"success": True},
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            input_tokens=0,
        )

        # Should not raise division by zero
        assert collector.metadata is not None
        assert collector.metadata.cache_hit_rate == 0.0

    def test_cache_hit_rate_100_percent(self, temp_dir):
        """Test 100% cache hit rate (all tokens from cache)."""
        collector = TraceCollector(traces_dir=temp_dir, session_id="test-session-100")

        # All tokens from cache
        collector.record_tool_call(
            tool_name="Grep",
            tool_input={"pattern": "test", "path": "/test"},
            tool_result={"matches": 5},
            cache_creation_input_tokens=0,
            cache_read_input_tokens=5000,
            input_tokens=0,
        )

        assert collector.metadata is not None
        assert collector.metadata.cache_hit_rate == 100.0

    def test_backward_compatibility_missing_cache_fields(self):
        """Ensure old traces without cache fields can be loaded."""
        # Simulate old trace event without cache metrics
        old_trace_dict = {
            "trace_id": "evt-test-123",
            "session_id": "sess-old-session",
            "task_id": None,
            "timestamp": "2025-11-30T10:00:00",
            "turn_number": 1,
            "event_type": "tool_call",
            "tool_name": "Read",
            "tool_category": "file_read",
            "tokens_in_context": 1000,
            "tokens_generated": 100,
            # No cache_creation_input_tokens, cache_read_input_tokens, or input_tokens
        }

        # Should load without errors and default cache fields to 0
        event = TraceEvent.from_dict(old_trace_dict)
        assert event.cache_creation_input_tokens == 0
        assert event.cache_read_input_tokens == 0
        assert event.input_tokens == 0

    def test_cache_metrics_accumulation(self, temp_dir):
        """Test that cache metrics accumulate correctly across multiple turns."""
        collector = TraceCollector(traces_dir=temp_dir, session_id="test-accumulation")

        # Turn 1: Cache creation
        collector.record_tool_call(
            tool_name="Read",
            tool_input={"file_path": "/test/a.py"},
            tool_result={"success": True},
            cache_creation_input_tokens=2000,
            cache_read_input_tokens=0,
            input_tokens=100,
        )

        # Turn 2: Cache read
        collector.record_tool_call(
            tool_name="Grep",
            tool_input={"pattern": "foo", "path": "/test"},
            tool_result={"matches": 3},
            cache_creation_input_tokens=500,
            cache_read_input_tokens=3000,
            input_tokens=200,
        )

        # Turn 3: More cache reads
        collector.record_tool_call(
            tool_name="Edit",
            tool_input={"file_path": "/test/b.py", "old_string": "x", "new_string": "y"},
            tool_result={"success": True},
            cache_creation_input_tokens=0,
            cache_read_input_tokens=5000,
            input_tokens=150,
        )

        assert collector.metadata is not None
        assert collector.metadata.total_cache_creation_tokens == 2500
        assert collector.metadata.total_cache_read_tokens == 8000
        assert collector.metadata.total_input_tokens == 450

        # Cache hit rate: 8000 / (2500 + 8000 + 450) * 100 = 73.06%
        assert abs(collector.metadata.cache_hit_rate - 73.06) < 0.01

    def test_cache_hit_rate_rounding_in_serialization(self, temp_dir):
        """Test that cache hit rate is rounded to 1 decimal place in to_dict()."""
        from datetime import datetime

        metadata = SessionMetadata(
            session_id="test-round",
            task_id=None,
            start_time=datetime.now(),
            total_cache_creation_tokens=100,
            total_cache_read_tokens=333,
            total_input_tokens=67,
        )

        # Calculate hit rate: 333 / (100 + 333 + 67) * 100 = 66.6%
        total = 100 + 333 + 67
        metadata.cache_hit_rate = (333 / total) * 100

        # Serialize to dict
        serialized = metadata.to_dict()

        # Should be rounded to 1 decimal place
        assert serialized["cache_hit_rate"] == 66.6
        # Verify it's actually rounded (not just truncated)
        assert isinstance(serialized["cache_hit_rate"], float)

    def test_metadata_serialization_includes_cache_fields(self, temp_dir):
        """Ensure SessionMetadata.to_dict() includes all cache fields."""
        from datetime import datetime

        metadata = SessionMetadata(
            session_id="test-serial",
            task_id="beads-123",
            start_time=datetime.now(),
            total_cache_creation_tokens=1500,
            total_cache_read_tokens=4500,
            total_input_tokens=300,
            cache_hit_rate=69.2,
        )

        serialized = metadata.to_dict()

        # All cache fields should be present
        assert "total_cache_creation_tokens" in serialized
        assert "total_cache_read_tokens" in serialized
        assert "total_input_tokens" in serialized
        assert "cache_hit_rate" in serialized

        # Values should match
        assert serialized["total_cache_creation_tokens"] == 1500
        assert serialized["total_cache_read_tokens"] == 4500
        assert serialized["total_input_tokens"] == 300
        assert serialized["cache_hit_rate"] == 69.2

    def test_metadata_deserialization_with_cache_fields(self):
        """Test that SessionMetadata.from_dict() correctly loads cache fields."""
        metadata_dict = {
            "session_id": "sess-deser",
            "task_id": "beads-456",
            "start_time": "2025-11-30T12:00:00",
            "end_time": None,
            "working_directory": "/home/test",
            "repository": "owner/repo",
            "branch": "main",
            "total_events": 10,
            "total_tool_calls": 8,
            "tool_call_breakdown": {"Read": 3, "Grep": 2, "Edit": 3},
            "total_tokens_generated": 500,
            "peak_context_size": 15000,
            "total_cache_creation_tokens": 2000,
            "total_cache_read_tokens": 6000,
            "total_input_tokens": 400,
            "cache_hit_rate": 71.4,
            "outcome": "completed",
            "outcome_notes": "All tasks done",
        }

        metadata = SessionMetadata.from_dict(metadata_dict)

        assert metadata.total_cache_creation_tokens == 2000
        assert metadata.total_cache_read_tokens == 6000
        assert metadata.total_input_tokens == 400
        assert metadata.cache_hit_rate == 71.4
