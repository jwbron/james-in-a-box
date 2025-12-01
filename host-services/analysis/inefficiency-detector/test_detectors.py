#!/usr/bin/env python3
"""
Simple test script for inefficiency detectors (no pytest required).

Run: python test_detectors.py
"""

import sys
from datetime import datetime
from pathlib import Path


# Add necessary paths
sys.path.insert(0, str(Path(__file__).parent.parent / "trace-collector"))

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


def test_tool_discovery_documentation_miss():
    """Test detection of multiple failing searches before success."""
    print("Testing Tool Discovery - Documentation Miss...")

    detector = ToolDiscoveryDetector()

    # Pattern: 3 greps with 0 results, then glob succeeds
    events = [
        create_event("evt-1", 1, "Grep", ToolCategory.SEARCH, "success", 0, "SpecificTerm"),
        create_event("evt-2", 2, "Grep", ToolCategory.SEARCH, "success", 0, "Term"),
        create_event("evt-3", 3, "Grep", ToolCategory.SEARCH, "success", 0, "term"),
        create_event("evt-4", 4, "Glob", ToolCategory.FILE_READ, "success", 5, "*term*"),
    ]

    inefficiencies = detector.detect(events)

    # Detector finds both documentation_miss AND search_failures - both are valid
    # Just check that at least one is documentation_miss
    assert len(inefficiencies) >= 1, f"Expected at least 1 inefficiency, got {len(inefficiencies)}"
    doc_miss = [i for i in inefficiencies if i.sub_category == "documentation_miss"]
    assert len(doc_miss) >= 1, "Expected to find documentation_miss inefficiency"
    assert doc_miss[0].wasted_tokens > 0
    print("✓ Passed")


def test_tool_execution_retry_storm():
    """Test detection of retry storm pattern."""
    print("Testing Tool Execution - Retry Storm...")

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

    assert len(inefficiencies) == 1, f"Expected 1 inefficiency, got {len(inefficiencies)}"
    assert inefficiencies[0].sub_category == "retry_storm"
    print("✓ Passed")


def test_resource_efficiency_redundant_reads():
    """Test detection of redundant file reads."""
    print("Testing Resource Efficiency - Redundant Reads...")

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

    assert len(inefficiencies) == 1, f"Expected 1 inefficiency, got {len(inefficiencies)}"
    assert inefficiencies[0].sub_category == "redundant_reads"
    print("✓ Passed")


def test_resource_efficiency_excessive_context():
    """Test detection of large file read without limits."""
    print("Testing Resource Efficiency - Excessive Context...")

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

    assert len(inefficiencies) == 1, f"Expected 1 inefficiency, got {len(inefficiencies)}"
    assert inefficiencies[0].sub_category == "excessive_context"
    print("✓ Passed")


def main():
    """Run all tests."""
    print("Running Inefficiency Detector Tests\n")
    print("=" * 50)

    tests = [
        test_tool_discovery_documentation_miss,
        test_tool_execution_retry_storm,
        test_resource_efficiency_redundant_reads,
        test_resource_efficiency_excessive_context,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ Failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ Error: {e}")
            failed += 1

    print("=" * 50)
    print(f"\nResults: {passed} passed, {failed} failed")

    if failed == 0:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
