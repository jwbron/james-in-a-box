"""
Unit tests for LLM Inefficiency Detector (Phase 2)

Tests the detection patterns for all implemented detector categories.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest


# Add inefficiency-detector to path
detector_path = (
    Path(__file__).parent.parent.parent / "host-services" / "analysis" / "inefficiency-detector"
)
trace_collector_path = (
    Path(__file__).parent.parent.parent / "host-services" / "analysis" / "trace-collector"
)
sys.path.insert(0, str(detector_path))
sys.path.insert(0, str(trace_collector_path))

from detectors.resource_efficiency_detector import ResourceEfficiencyDetector
from detectors.tool_discovery_detector import ToolDiscoveryDetector
from detectors.tool_execution_detector import ToolExecutionDetector
from schemas import EventType, ToolCallParams, ToolCategory, ToolResult, TraceEvent


def create_event(
    trace_id: str,
    turn_number: int,
    tool_name: str,
    tool_category: ToolCategory,
    result_status: str = "success",
    match_count: int | None = None,
    pattern: str | None = None,
    path: str | None = None,
    tokens_generated: int = 100,
) -> TraceEvent:
    """Helper to create a test trace event."""
    params = ToolCallParams(pattern=pattern, path=path)
    result = ToolResult(status=result_status, match_count=match_count)

    return TraceEvent(
        trace_id=trace_id,
        session_id="test-session",
        task_id="test-task",
        timestamp=datetime.now(),
        turn_number=turn_number,
        event_type=EventType.TOOL_CALL,
        tool_name=tool_name,
        tool_category=tool_category,
        tool_params=params,
        tool_result=result,
        tokens_generated=tokens_generated,
    )


class TestToolDiscoveryDetector:
    """Test Tool Discovery Failures detector (Category 1)."""

    def test_documentation_miss_pattern(self):
        """Test detection of multiple failing searches before success."""
        detector = ToolDiscoveryDetector()

        # Pattern: 3 greeps with 0 results, then glob succeeds
        events = [
            create_event("evt-1", 1, "Grep", ToolCategory.SEARCH, "success", 0, "SpecificTerm"),
            create_event("evt-2", 2, "Grep", ToolCategory.SEARCH, "success", 0, "Term"),
            create_event("evt-3", 3, "Grep", ToolCategory.SEARCH, "success", 0, "term"),
            create_event("evt-4", 4, "Glob", ToolCategory.FILE_READ, "success", 5, "*term*"),
        ]

        inefficiencies = detector.detect(events)

        # Should detect both documentation_miss and search_failure patterns
        # documentation_miss: 4 searches with 3 empty results before success
        # search_failure: 3 consecutive grep searches with 0 results
        assert len(inefficiencies) == 2

        # Find the documentation_miss inefficiency
        doc_miss = next(i for i in inefficiencies if i.sub_category == "documentation_miss")
        assert doc_miss.wasted_tokens > 0
        assert "glob" in doc_miss.recommendation.lower()

        # Find the search_failure inefficiency
        search_fail = next(i for i in inefficiencies if i.sub_category == "search_failure")
        assert search_fail.wasted_tokens > 0

    def test_api_confusion_pattern(self):
        """Test detection of tool call with wrong params, then correct params."""
        detector = ToolDiscoveryDetector()

        events = [
            # First call fails due to bad params
            create_event(
                "evt-1",
                1,
                "Read",
                ToolCategory.FILE_READ,
                "error",
                path="/wrong/path.py",
                tokens_generated=150,
            ),
            # Second call succeeds
            create_event(
                "evt-2",
                2,
                "Read",
                ToolCategory.FILE_READ,
                "success",
                path="/correct/path.py",
                tokens_generated=150,
            ),
        ]

        inefficiencies = detector.detect(events)

        # Should detect API confusion
        assert len(inefficiencies) == 1
        assert inefficiencies[0].sub_category == "api_confusion"


class TestToolExecutionDetector:
    """Test Tool Execution Failures detector (Category 4)."""

    def test_retry_storm_pattern(self):
        """Test detection of multiple retries with same error."""
        detector = ToolExecutionDetector()

        # Same bash command failing 3 times
        events = [
            create_event("evt-1", 1, "Bash", ToolCategory.EXECUTION, "error", tokens_generated=200),
            create_event("evt-2", 2, "Bash", ToolCategory.EXECUTION, "error", tokens_generated=200),
            create_event("evt-3", 3, "Bash", ToolCategory.EXECUTION, "error", tokens_generated=200),
        ]

        # Set same error type for all
        for event in events:
            if event.tool_result:
                event.tool_result.error_type = "ENOENT"
                event.tool_result.error_message = "npm: command not found"

        inefficiencies = detector.detect(events)

        # Should detect retry storm
        assert len(inefficiencies) == 1
        assert inefficiencies[0].sub_category == "retry_storm"
        assert inefficiencies[0].wasted_tokens > 0

    def test_no_false_positive_on_different_errors(self):
        """Test that different errors don't trigger retry storm."""
        detector = ToolExecutionDetector()

        events = [
            create_event("evt-1", 1, "Bash", ToolCategory.EXECUTION, "error"),
            create_event("evt-2", 2, "Bash", ToolCategory.EXECUTION, "error"),
            create_event("evt-3", 3, "Bash", ToolCategory.EXECUTION, "error"),
        ]

        # Set different errors
        events[0].tool_result.error_type = "ENOENT"
        events[1].tool_result.error_type = "PERMISSION_DENIED"
        events[2].tool_result.error_type = "TIMEOUT"

        inefficiencies = detector.detect(events)

        # Should NOT detect retry storm (different errors)
        assert len(inefficiencies) == 0


class TestResourceEfficiencyDetector:
    """Test Resource Efficiency detector (Category 7)."""

    def test_redundant_reads_pattern(self):
        """Test detection of same file read multiple times."""
        detector = ResourceEfficiencyDetector()

        # Same file read 3 times
        events = [
            create_event(
                "evt-1",
                1,
                "Read",
                ToolCategory.FILE_READ,
                "success",
                path="/home/user/code.py",
                tokens_generated=300,
            ),
            create_event(
                "evt-2",
                5,
                "Read",
                ToolCategory.FILE_READ,
                "success",
                path="/home/user/code.py",
                tokens_generated=300,
            ),
            create_event(
                "evt-3",
                10,
                "Read",
                ToolCategory.FILE_READ,
                "success",
                path="/home/user/code.py",
                tokens_generated=300,
            ),
        ]

        inefficiencies = detector.detect(events)

        # Should detect redundant reads
        assert len(inefficiencies) == 1
        assert inefficiencies[0].sub_category == "redundant_reads"
        assert "/home/user/code.py" in inefficiencies[0].description

    def test_excessive_context_pattern(self):
        """Test detection of large file read without limits."""
        detector = ResourceEfficiencyDetector()

        # Large file read (2000 lines) without limit
        event = create_event(
            "evt-1",
            1,
            "Read",
            ToolCategory.FILE_READ,
            "success",
            path="/home/user/large_file.py",
        )
        event.tool_result.lines_returned = 2000

        inefficiencies = detector.detect([event])

        # Should detect excessive context
        assert len(inefficiencies) == 1
        assert inefficiencies[0].sub_category == "excessive_context"
        assert "limit" in inefficiencies[0].recommendation.lower()

    def test_no_false_positive_on_small_file(self):
        """Test that small files don't trigger excessive context."""
        detector = ResourceEfficiencyDetector()

        event = create_event(
            "evt-1", 1, "Read", ToolCategory.FILE_READ, "success", path="/home/user/small.py"
        )
        event.tool_result.lines_returned = 100

        inefficiencies = detector.detect([event])

        # Should NOT flag small file
        assert len(inefficiencies) == 0


class TestInefficiencyDetectorIntegration:
    """Integration tests for the full detector orchestrator."""

    def test_multiple_detectors_combined(self):
        """Test that multiple detector categories work together."""
        from inefficiency_detector import InefficiencyDetector

        # Note: Can't easily test full integration without real trace files
        # This test would need mock trace files
        detector = InefficiencyDetector()
        assert detector is not None
        assert len(detector.detectors) == 3  # 3 implemented detectors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
