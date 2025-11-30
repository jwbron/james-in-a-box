"""
Base Detector Interface

Defines the abstract interface that all inefficiency detectors must implement.
Each detector focuses on one category from the ADR taxonomy.
"""

from abc import ABC, abstractmethod

import sys
from pathlib import Path

# Add trace-collector to path for imports
trace_collector_path = Path(__file__).parent.parent / "trace-collector"
sys.path.insert(0, str(trace_collector_path))

from schemas import TraceEvent

from inefficiency_schema import DetectedInefficiency


class BaseDetector(ABC):
    """
    Abstract base class for all inefficiency detectors.

    Each detector analyzes a sequence of trace events and returns
    detected inefficiencies for its specific category.
    """

    def __init__(self, config: dict | None = None):
        """
        Initialize detector with optional configuration.

        Args:
            config: Detector-specific configuration (thresholds, weights, etc.)
        """
        self.config = config or {}

    @abstractmethod
    def detect(self, events: list[TraceEvent]) -> list[DetectedInefficiency]:
        """
        Detect inefficiencies in a sequence of trace events.

        Args:
            events: Ordered list of events from a session

        Returns:
            List of detected inefficiencies
        """
        pass

    @abstractmethod
    def get_category(self) -> str:
        """Return the inefficiency category this detector handles."""
        pass

    def _calculate_token_cost(self, events: list[TraceEvent]) -> int:
        """
        Calculate total token cost for a sequence of events.

        Includes tokens generated + input tokens.
        """
        total = 0
        for event in events:
            total += event.tokens_generated
            total += event.input_tokens
            total += event.cache_creation_input_tokens
            # Note: cache_read_input_tokens are "free" (already paid for)
        return total

    def _extract_event_ids(self, events: list[TraceEvent]) -> list[str]:
        """Extract trace IDs from a list of events."""
        return [e.trace_id for e in events]

    def _get_turn_range(self, events: list[TraceEvent]) -> tuple[int, int] | None:
        """Get the turn number range for a sequence of events."""
        if not events:
            return None
        turns = [e.turn_number for e in events]
        return (min(turns), max(turns))

    def _get_timestamp_range(self, events: list[TraceEvent]) -> tuple[str, str] | None:
        """Get the timestamp range for a sequence of events."""
        if not events:
            return None
        timestamps = [e.timestamp.isoformat() for e in events]
        return (min(timestamps), max(timestamps))

    def _determine_severity(self, wasted_tokens: int) -> str:
        """
        Determine severity level based on wasted tokens.

        Thresholds:
        - LOW: < 500 tokens
        - MEDIUM: 500-2000 tokens
        - HIGH: > 2000 tokens
        """
        if wasted_tokens < 500:
            return "low"
        elif wasted_tokens < 2000:
            return "medium"
        else:
            return "high"
