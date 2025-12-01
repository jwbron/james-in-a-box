"""
Tool Discovery Failures Detector (Category 1)

Detects inefficiencies in finding and using tools and documentation:
- Tool Not Found: Searched for non-existent tool
- Wrong Tool Selected: Used inappropriate tool for task
- Documentation Miss: Failed to find relevant documentation
- API Confusion: Misunderstood tool parameters
- Tool Misuse: Used tool in unintended way

According to ADR, this accounts for ~45% of inefficiencies.
"""

import sys
from pathlib import Path


# Add paths for imports
base_path = Path(__file__).parent.parent
sys.path.insert(0, str(base_path))
sys.path.insert(0, str(base_path.parent / "trace-collector"))

from base_detector import BaseDetector
from inefficiency_schema import DetectedInefficiency, InefficiencyCategory, Severity
from schemas import ToolCategory, TraceEvent


class ToolDiscoveryDetector(BaseDetector):
    """Detects tool discovery failures and documentation misses."""

    def get_category(self) -> str:
        return InefficiencyCategory.TOOL_DISCOVERY.value

    def detect(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect tool discovery inefficiencies.

        Patterns:
        1. Multiple searches with decreasing specificity (documentation miss)
        2. Search tool returns 0 results followed by different search (wrong approach)
        3. Tool errors due to wrong parameters (API confusion)
        4. Tool succeeds but output not used (tool misuse)
        """
        inefficiencies: list[DetectedInefficiency] = []

        # Pattern 1: Documentation Miss - Multiple decreasing-specificity searches
        inefficiencies.extend(self._detect_documentation_miss(events))

        # Pattern 2: Search Failures - Multiple empty search results
        inefficiencies.extend(self._detect_search_failures(events))

        # Pattern 3: API Confusion - Tool errors due to bad parameters
        inefficiencies.extend(self._detect_api_confusion(events))

        return inefficiencies

    def _detect_documentation_miss(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect: Multiple search attempts with decreasing specificity before finding target.

        Pattern: Grep("SpecificTerm") → 0 results, Grep("Term") → 0 results, Glob("*term*") → success

        This indicates the LLM tried specific searches first when a broader approach
        (like glob) would have worked immediately.
        """
        inefficiencies = []

        # Extract sequences of search tool calls
        search_sequences = self._extract_search_sequences(events)

        for sequence in search_sequences:
            if len(sequence) < 3:
                # Need at least 3 searches to indicate a pattern
                continue

            # Check if early searches returned 0 results
            zero_results = []
            for event in sequence[:-1]:  # All but the last
                if event.tool_result and event.tool_result.match_count == 0:
                    zero_results.append(event)

            if len(zero_results) >= 2:
                # Multiple failed searches before success
                all_events = sequence
                actual_cost = self._calculate_token_cost(all_events)
                # Estimate optimal cost as just the successful attempt
                optimal_cost = self._calculate_token_cost([sequence[-1]])
                wasted_tokens = actual_cost - optimal_cost

                if wasted_tokens > 100:  # Threshold for significance
                    session_id = all_events[0].session_id
                    task_id = all_events[0].task_id

                    # Determine if glob was eventually used
                    final_tool = sequence[-1].tool_name
                    used_glob = final_tool == "Glob"

                    recommendation = (
                        "Use glob patterns for file discovery instead of repeated grep attempts. "
                        "When grep returns 0 results, try glob before broadening grep pattern."
                        if used_glob
                        else "Consider using glob patterns for file discovery. "
                        "Multiple specific searches suggest unclear target location."
                    )

                    inefficiencies.append(
                        DetectedInefficiency(
                            category=InefficiencyCategory.TOOL_DISCOVERY,
                            sub_category="documentation_miss",
                            severity=Severity(self._determine_severity(wasted_tokens)),
                            trace_event_ids=self._extract_event_ids(all_events),
                            session_id=session_id,
                            task_id=task_id,
                            token_cost=actual_cost,
                            estimated_optimal_cost=optimal_cost,
                            wasted_tokens=wasted_tokens,
                            wasted_percentage=(wasted_tokens / actual_cost * 100)
                            if actual_cost > 0
                            else 0,
                            description=f"Searched {len(all_events)} times with {len(zero_results)} empty results before finding target",
                            recommendation=recommendation,
                            turn_range=self._get_turn_range(all_events),
                            timestamp_range=self._get_timestamp_range(all_events),
                            evidence={
                                "search_sequence": [
                                    {
                                        "tool": e.tool_name,
                                        "pattern": e.tool_params.pattern if e.tool_params else None,
                                        "results": e.tool_result.match_count
                                        if e.tool_result
                                        else None,
                                    }
                                    for e in all_events
                                ],
                            },
                        )
                    )

        return inefficiencies

    def _detect_search_failures(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect: Multiple consecutive search tools returning 0 results.

        This indicates the LLM is "hunting" for something and not finding it,
        suggesting either:
        - Wrong search approach
        - Target doesn't exist (hallucination)
        - Incorrect assumptions about codebase structure
        """
        inefficiencies = []

        consecutive_failures = []
        for event in events:
            if (
                event.tool_category in (ToolCategory.SEARCH, ToolCategory.FILE_READ)
                and event.tool_name in ("Grep", "Glob")
                and event.tool_result
            ):
                match_count = event.tool_result.match_count or event.tool_result.file_count or 0
                if match_count == 0:
                    consecutive_failures.append(event)
                else:
                    # Success - check if we had a pattern of failures before this success
                    if len(consecutive_failures) >= 3:
                        self._create_search_failure_inefficiency(
                            consecutive_failures, inefficiencies
                        )
                    consecutive_failures = []

        # Check final sequence - only report if failures are NOT followed by success
        # (documentation_miss already handles failures-then-success pattern)
        if len(consecutive_failures) >= 3:
            self._create_search_failure_inefficiency(consecutive_failures, inefficiencies)

        return inefficiencies

    def _create_search_failure_inefficiency(
        self, failed_events: list[TraceEvent], inefficiencies: list[DetectedInefficiency]
    ) -> None:
        """Helper to create inefficiency for consecutive search failures."""
        actual_cost = self._calculate_token_cost(failed_events)
        # Optimal would be 0 if target doesn't exist, or 1 search if it does
        optimal_cost = actual_cost // len(failed_events)  # Estimate
        wasted_tokens = actual_cost - optimal_cost

        if wasted_tokens > 100:
            session_id = failed_events[0].session_id
            task_id = failed_events[0].task_id

            inefficiencies.append(
                DetectedInefficiency(
                    category=InefficiencyCategory.TOOL_DISCOVERY,
                    sub_category="search_failure",
                    severity=Severity(self._determine_severity(wasted_tokens)),
                    trace_event_ids=self._extract_event_ids(failed_events),
                    session_id=session_id,
                    task_id=task_id,
                    token_cost=actual_cost,
                    estimated_optimal_cost=optimal_cost,
                    wasted_tokens=wasted_tokens,
                    wasted_percentage=(wasted_tokens / actual_cost * 100) if actual_cost > 0 else 0,
                    description=f"{len(failed_events)} consecutive search attempts returned no results",
                    recommendation="Verify target exists before searching. Consider alternative search strategies or ask user for clarification.",
                    turn_range=self._get_turn_range(failed_events),
                    timestamp_range=self._get_timestamp_range(failed_events),
                    evidence={
                        "patterns_tried": [
                            e.tool_params.pattern if e.tool_params else None for e in failed_events
                        ],
                    },
                )
            )

    def _detect_api_confusion(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect: Tool calls that fail due to parameter errors, followed by retry with different params.

        Pattern: ToolX(params_a) → error, ToolX(params_b) → success

        This indicates the LLM didn't understand the tool's API initially.
        """
        inefficiencies = []

        for i in range(len(events) - 1):
            curr = events[i]
            next_event = events[i + 1]

            # Same tool called twice in a row, first call failed, second succeeded
            if (
                curr.tool_name == next_event.tool_name
                and curr.tool_name
                and curr.tool_result
                and curr.tool_result.status == "error"
                and next_event.tool_result
                and next_event.tool_result.status == "success"
            ):
                both_events = [curr, next_event]
                actual_cost = self._calculate_token_cost(both_events)
                optimal_cost = self._calculate_token_cost([next_event])
                wasted_tokens = actual_cost - optimal_cost

                if wasted_tokens > 50:  # Even small API confusion is notable
                    session_id = curr.session_id
                    task_id = curr.task_id

                    inefficiencies.append(
                        DetectedInefficiency(
                            category=InefficiencyCategory.TOOL_DISCOVERY,
                            sub_category="api_confusion",
                            severity=Severity(self._determine_severity(wasted_tokens)),
                            trace_event_ids=self._extract_event_ids(both_events),
                            session_id=session_id,
                            task_id=task_id,
                            token_cost=actual_cost,
                            estimated_optimal_cost=optimal_cost,
                            wasted_tokens=wasted_tokens,
                            wasted_percentage=(wasted_tokens / actual_cost * 100)
                            if actual_cost > 0
                            else 0,
                            description=f"{curr.tool_name} called with incorrect parameters, then retried with correct parameters",
                            recommendation=f"Review {curr.tool_name} API documentation. Add clearer parameter examples to tool descriptions.",
                            turn_range=self._get_turn_range(both_events),
                            timestamp_range=self._get_timestamp_range(both_events),
                            evidence={
                                "tool": curr.tool_name,
                                "error_message": curr.tool_result.error_message,
                                "failed_params": curr.tool_params.raw if curr.tool_params else {},
                                "success_params": next_event.tool_params.raw
                                if next_event.tool_params
                                else {},
                            },
                        )
                    )

        return inefficiencies

    def _extract_search_sequences(self, events: list[TraceEvent]) -> list[list[TraceEvent]]:
        """
        Extract sequences of consecutive search tool calls.

        Returns sequences where search tools (Grep, Glob, Read with search intent)
        are used consecutively, likely targeting the same goal.
        """
        sequences = []
        current_sequence = []

        search_tools = {"Grep", "Glob"}

        for event in events:
            if event.tool_name in search_tools:
                current_sequence.append(event)
            else:
                # Non-search tool breaks the sequence
                if len(current_sequence) >= 2:
                    sequences.append(current_sequence)
                current_sequence = []

        # Add final sequence
        if len(current_sequence) >= 2:
            sequences.append(current_sequence)

        return sequences
