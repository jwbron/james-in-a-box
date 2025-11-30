"""
Resource Efficiency Detector (Category 7)

Detects token and computational resource usage patterns:
- Redundant Reads: Same file read multiple times
- Excessive Context: Loaded unnecessary context
- Verbose Tool Output: Didn't limit output when possible
- Parallel Opportunity Missed: Sequential calls that could be parallel
- Unnecessary Exploration: Explored irrelevant codebase areas
"""

import sys
from pathlib import Path

# Add paths for imports
base_path = Path(__file__).parent.parent
sys.path.insert(0, str(base_path))
sys.path.insert(0, str(base_path.parent / "trace-collector"))

from base_detector import BaseDetector
from inefficiency_schema import DetectedInefficiency, InefficiencyCategory, Severity
from schemas import TraceEvent


class ResourceEfficiencyDetector(BaseDetector):
    """Detects inefficient resource usage patterns."""

    def __init__(self, tokens_per_line: int = 3):
        """
        Initialize the detector.

        Args:
            tokens_per_line: Estimated tokens per line of code for waste calculations.
                           Default is 3 (conservative). Adjust based on actual trace data.
        """
        self.tokens_per_line = tokens_per_line

    def get_category(self) -> str:
        return InefficiencyCategory.RESOURCE.value

    def detect(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect resource efficiency inefficiencies.

        Patterns:
        1. Redundant reads - same file read multiple times
        2. Excessive file reads - reading very large files without limits
        3. Sequential calls - independent calls that could be parallel
        """
        inefficiencies: list[DetectedInefficiency] = []

        # Pattern 1: Redundant file reads
        inefficiencies.extend(self._detect_redundant_reads(events))

        # Pattern 2: Excessive file reads (large files without limits)
        inefficiencies.extend(self._detect_excessive_reads(events))

        return inefficiencies

    def _detect_redundant_reads(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect: Same file read multiple times in a session.

        This wastes tokens when the file content is already in context.
        """
        inefficiencies = []

        # Track file reads by path
        file_reads: dict[str, list[TraceEvent]] = {}

        for event in events:
            if event.tool_name == "Read" and event.tool_params and event.tool_params.path:
                path = event.tool_params.path
                if path not in file_reads:
                    file_reads[path] = []
                file_reads[path].append(event)

        # Check for files read more than once
        for path, read_events in file_reads.items():
            if len(read_events) >= 2:
                # Calculate redundant cost (all reads after the first)
                redundant_events = read_events[1:]
                wasted_tokens = self._calculate_token_cost(redundant_events)

                # Only flag if significant waste
                if wasted_tokens > 200:
                    session_id = read_events[0].session_id
                    task_id = read_events[0].task_id

                    # Total cost includes first read
                    total_cost = self._calculate_token_cost(read_events)
                    optimal_cost = self._calculate_token_cost([read_events[0]])

                    inefficiencies.append(
                        DetectedInefficiency(
                            category=InefficiencyCategory.RESOURCE,
                            sub_category="redundant_reads",
                            severity=Severity(self._determine_severity(wasted_tokens)),
                            trace_event_ids=self._extract_event_ids(redundant_events),
                            session_id=session_id,
                            task_id=task_id,
                            token_cost=total_cost,
                            estimated_optimal_cost=optimal_cost,
                            wasted_tokens=wasted_tokens,
                            wasted_percentage=(wasted_tokens / total_cost * 100)
                            if total_cost > 0
                            else 0,
                            description=f"File '{path}' read {len(read_events)} times in session",
                            recommendation="Reference file content from context instead of re-reading. Use context window effectively.",
                            turn_range=self._get_turn_range(redundant_events),
                            timestamp_range=self._get_timestamp_range(redundant_events),
                            evidence={
                                "file_path": path,
                                "read_count": len(read_events),
                                "turn_numbers": [e.turn_number for e in read_events],
                            },
                        )
                    )

        return inefficiencies

    def _detect_excessive_reads(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect: Very large files read without using limit/offset.

        Reading a 5000-line file when you only need 50 lines wastes tokens.
        """
        inefficiencies = []

        # Threshold for "large" file
        LARGE_FILE_THRESHOLD = 1000  # lines

        for event in events:
            if event.tool_name == "Read":
                if event.tool_result and event.tool_result.lines_returned:
                    lines = event.tool_result.lines_returned

                    # Check if this was a limited read
                    limited_read = False
                    if event.tool_params and event.tool_params.raw:
                        limited_read = "limit" in event.tool_params.raw or "offset" in event.tool_params.raw

                    # Large file read without limits
                    if lines >= LARGE_FILE_THRESHOLD and not limited_read:
                        # Estimate token waste using configurable tokens_per_line
                        tokens_read = lines * self.tokens_per_line
                        # Assume optimal would be 10% of file (200 lines for 1000-line file)
                        optimal_lines = min(200, lines // 5)
                        optimal_tokens = optimal_lines * self.tokens_per_line
                        wasted_tokens = tokens_read - optimal_tokens

                        if wasted_tokens > 500:
                            session_id = event.session_id
                            task_id = event.task_id
                            path = event.tool_params.path if event.tool_params else "unknown"

                            inefficiencies.append(
                                DetectedInefficiency(
                                    category=InefficiencyCategory.RESOURCE,
                                    sub_category="excessive_context",
                                    severity=Severity(self._determine_severity(wasted_tokens)),
                                    trace_event_ids=[event.trace_id],
                                    session_id=session_id,
                                    task_id=task_id,
                                    token_cost=tokens_read,
                                    estimated_optimal_cost=optimal_tokens,
                                    wasted_tokens=wasted_tokens,
                                    wasted_percentage=(wasted_tokens / tokens_read * 100)
                                    if tokens_read > 0
                                    else 0,
                                    description=f"Read {lines} lines from '{path}' without using limit/offset",
                                    recommendation="Use Read tool with limit/offset parameters for large files. Use Grep to find specific sections first.",
                                    turn_range=(event.turn_number, event.turn_number),
                                    timestamp_range=(
                                        event.timestamp.isoformat(),
                                        event.timestamp.isoformat(),
                                    ),
                                    evidence={
                                        "file_path": path,
                                        "lines_read": lines,
                                        "estimated_optimal_lines": optimal_lines,
                                    },
                                )
                            )

        return inefficiencies
