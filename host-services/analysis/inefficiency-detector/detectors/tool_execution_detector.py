"""
Tool Execution Failures Detector (Category 4)

Detects technical failures in tool invocation and response handling:
- Retry Storm: Multiple retries of failing operation
- Parameter Errors: Incorrect parameters to tool
- Timeout Issues: Operations exceeding time limits
- Permission Errors: Attempted operations without access
- Parse Failures: Failed to parse tool output correctly
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


class ToolExecutionDetector(BaseDetector):
    """Detects tool execution failures and retry patterns."""

    def get_category(self) -> str:
        return InefficiencyCategory.TOOL_EXECUTION.value

    def detect(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect tool execution inefficiencies.

        Patterns:
        1. Retry storms - same tool failing 3+ times with same error
        2. Parameter errors - validation failures
        3. Timeout patterns - commands exceeding limits
        """
        inefficiencies: list[DetectedInefficiency] = []

        # Pattern 1: Retry Storms - consecutive failures of same tool
        inefficiencies.extend(self._detect_retry_storms(events))

        # Pattern 2: Parameter Errors - repeated validation failures
        inefficiencies.extend(self._detect_parameter_errors(events))

        return inefficiencies

    def _detect_retry_storms(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect: Same tool called 3+ times with same error before changing approach.

        Example: Bash("npm test") → ENOENT, Bash("npm test") → ENOENT, Bash("npm test") → ENOENT

        This indicates the LLM is retrying without investigating the error first.
        """
        inefficiencies = []

        consecutive_failures = []
        last_tool = None
        last_error = None

        for event in events:
            if event.tool_result and event.tool_result.status == "error":
                current_tool = event.tool_name
                current_error = event.tool_result.error_type or event.tool_result.error_message

                # Same tool and error as previous failure?
                if current_tool == last_tool and current_error == last_error:
                    consecutive_failures.append(event)
                else:
                    # Different tool or error - check if we had a pattern
                    if len(consecutive_failures) >= 3:
                        self._create_retry_storm_inefficiency(consecutive_failures, inefficiencies)
                    consecutive_failures = [event]
                    last_tool = current_tool
                    last_error = current_error
            else:
                # Success or non-error event - check for pattern
                if len(consecutive_failures) >= 3:
                    self._create_retry_storm_inefficiency(consecutive_failures, inefficiencies)
                consecutive_failures = []
                last_tool = None
                last_error = None

        # Check final sequence
        if len(consecutive_failures) >= 3:
            self._create_retry_storm_inefficiency(consecutive_failures, inefficiencies)

        return inefficiencies

    def _create_retry_storm_inefficiency(
        self, failed_events: list[TraceEvent], inefficiencies: list[DetectedInefficiency]
    ) -> None:
        """Helper to create retry storm inefficiency."""
        actual_cost = self._calculate_token_cost(failed_events)
        # Optimal cost is investigating error ONCE, then fixing - estimate as 1 failed attempt
        optimal_cost = self._calculate_token_cost([failed_events[0]])
        wasted_tokens = actual_cost - optimal_cost

        if wasted_tokens > 100:
            session_id = failed_events[0].session_id
            task_id = failed_events[0].task_id
            tool_name = failed_events[0].tool_name or "unknown"
            error_msg = (
                failed_events[0].tool_result.error_message
                if failed_events[0].tool_result
                else "Unknown error"
            )

            # Truncate error message for readability
            error_msg = error_msg[:200] if error_msg else "Unknown"

            inefficiencies.append(
                DetectedInefficiency(
                    category=InefficiencyCategory.TOOL_EXECUTION,
                    sub_category="retry_storm",
                    severity=Severity(self._determine_severity(wasted_tokens)),
                    trace_event_ids=self._extract_event_ids(failed_events),
                    session_id=session_id,
                    task_id=task_id,
                    token_cost=actual_cost,
                    estimated_optimal_cost=optimal_cost,
                    wasted_tokens=wasted_tokens,
                    wasted_percentage=(wasted_tokens / actual_cost * 100) if actual_cost > 0 else 0,
                    description=f"{len(failed_events)} consecutive failed calls to {tool_name} with same error",
                    recommendation="Investigate errors before retrying. Check prerequisites (e.g., npm install, file exists) before re-running commands.",
                    turn_range=self._get_turn_range(failed_events),
                    timestamp_range=self._get_timestamp_range(failed_events),
                    evidence={
                        "tool": tool_name,
                        "retry_count": len(failed_events),
                        "error_message": error_msg,
                        "commands": [
                            e.tool_params.command if e.tool_params else None for e in failed_events
                        ],
                    },
                )
            )

    def _detect_parameter_errors(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect: Tools failing due to parameter validation errors.

        Different from API confusion (Category 1) - this is repeated failures
        with parameter-related errors across different tools, suggesting
        a pattern of not checking tool requirements.
        """
        inefficiencies = []

        param_error_keywords = [
            "parameter",
            "argument",
            "required",
            "missing",
            "invalid",
            "validation",
        ]

        param_errors = []
        for event in events:
            if event.tool_result and event.tool_result.status == "error":
                error_msg = (event.tool_result.error_message or "").lower()
                if any(keyword in error_msg for keyword in param_error_keywords):
                    param_errors.append(event)

        # If we have 3+ parameter errors in a session, it's a pattern
        if len(param_errors) >= 3:
            actual_cost = self._calculate_token_cost(param_errors)
            # Optimal would be getting it right first time
            optimal_cost = 0
            wasted_tokens = actual_cost

            if wasted_tokens > 200:
                session_id = param_errors[0].session_id
                task_id = param_errors[0].task_id

                tools_affected = list({e.tool_name for e in param_errors if e.tool_name})

                inefficiencies.append(
                    DetectedInefficiency(
                        category=InefficiencyCategory.TOOL_EXECUTION,
                        sub_category="parameter_errors",
                        severity=Severity(self._determine_severity(wasted_tokens)),
                        trace_event_ids=self._extract_event_ids(param_errors),
                        session_id=session_id,
                        task_id=task_id,
                        token_cost=actual_cost,
                        estimated_optimal_cost=optimal_cost,
                        wasted_tokens=wasted_tokens,
                        wasted_percentage=(wasted_tokens / actual_cost * 100)
                        if actual_cost > 0
                        else 0,
                        description=f"{len(param_errors)} parameter validation errors across {len(tools_affected)} different tools",
                        recommendation="Verify tool parameter requirements before calling. Add parameter validation guidance to tool descriptions.",
                        turn_range=self._get_turn_range(param_errors),
                        timestamp_range=self._get_timestamp_range(param_errors),
                        evidence={
                            "tools_affected": tools_affected,
                            "error_samples": [
                                {
                                    "tool": e.tool_name,
                                    "error": e.tool_result.error_message[:100]
                                    if e.tool_result
                                    else None,
                                }
                                for e in param_errors[:5]  # First 5 examples
                            ],
                        },
                    )
                )

        return inefficiencies
