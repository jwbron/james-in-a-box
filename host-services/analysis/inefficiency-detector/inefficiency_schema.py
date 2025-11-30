"""
Inefficiency Detection Schemas

Defines data structures for detected inefficiencies based on the taxonomy
in ADR-LLM-Inefficiency-Reporting.md.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InefficiencyCategory(Enum):
    """Top-level inefficiency categories from ADR taxonomy."""

    TOOL_DISCOVERY = "tool_discovery"
    DECISION_LOOP = "decision_loop"
    DIRECTION = "direction"
    TOOL_EXECUTION = "tool_execution"
    REASONING = "reasoning"
    COMMUNICATION = "communication"
    RESOURCE = "resource"


class Severity(Enum):
    """Severity levels for detected inefficiencies."""

    LOW = "low"  # Minor waste, < 500 tokens
    MEDIUM = "medium"  # Moderate waste, 500-2000 tokens
    HIGH = "high"  # Significant waste, > 2000 tokens


@dataclass
class DetectedInefficiency:
    """
    A detected inefficiency pattern in an LLM trace session.

    This is the core output of the inefficiency detection engine.
    """

    # Classification
    category: InefficiencyCategory
    sub_category: str  # Specific type within category (e.g., "documentation_miss")
    severity: Severity

    # Evidence
    trace_event_ids: list[str]  # Event IDs involved in this inefficiency
    session_id: str  # Session this occurred in
    task_id: str | None  # Beads task ID if available

    # Impact metrics
    token_cost: int  # Actual tokens consumed
    estimated_optimal_cost: int  # What it should have cost
    wasted_tokens: int  # token_cost - estimated_optimal_cost
    wasted_percentage: float  # wasted_tokens / token_cost * 100

    # Description
    description: str  # Human-readable description of what happened
    recommendation: str  # Actionable recommendation to prevent recurrence

    # Context
    turn_range: tuple[int, int] | None = None  # (start_turn, end_turn)
    timestamp_range: tuple[str, str] | None = None  # (start_iso, end_iso)

    # Supporting data
    evidence: dict[str, Any] = field(default_factory=dict)  # Additional evidence details

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category.value,
            "sub_category": self.sub_category,
            "severity": self.severity.value,
            "trace_event_ids": self.trace_event_ids,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "token_cost": self.token_cost,
            "estimated_optimal_cost": self.estimated_optimal_cost,
            "wasted_tokens": self.wasted_tokens,
            "wasted_percentage": round(self.wasted_percentage, 1),
            "description": self.description,
            "recommendation": self.recommendation,
            "turn_range": self.turn_range,
            "timestamp_range": self.timestamp_range,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectedInefficiency":
        """Create DetectedInefficiency from dictionary."""
        return cls(
            category=InefficiencyCategory(data["category"]),
            sub_category=data["sub_category"],
            severity=Severity(data["severity"]),
            trace_event_ids=data["trace_event_ids"],
            session_id=data["session_id"],
            task_id=data.get("task_id"),
            token_cost=data["token_cost"],
            estimated_optimal_cost=data["estimated_optimal_cost"],
            wasted_tokens=data["wasted_tokens"],
            wasted_percentage=data["wasted_percentage"],
            description=data["description"],
            recommendation=data["recommendation"],
            turn_range=tuple(data["turn_range"]) if data.get("turn_range") else None,
            timestamp_range=tuple(data["timestamp_range"]) if data.get("timestamp_range") else None,
            evidence=data.get("evidence", {}),
        )


@dataclass
class SessionInefficiencyReport:
    """
    Inefficiency report for a single trace session.
    """

    session_id: str
    task_id: str | None
    total_tokens: int  # Total tokens consumed in session
    total_wasted_tokens: int  # Sum of all inefficiency waste
    inefficiency_rate: float  # Percentage of tokens wasted (0-100)

    inefficiencies: list[DetectedInefficiency] = field(default_factory=list)

    # Breakdown by category
    category_breakdown: dict[str, int] = field(default_factory=dict)  # category -> count
    severity_breakdown: dict[str, int] = field(default_factory=dict)  # severity -> count

    def add_inefficiency(self, ineff: DetectedInefficiency) -> None:
        """Add an inefficiency to this report."""
        self.inefficiencies.append(ineff)
        self.total_wasted_tokens += ineff.wasted_tokens

        # Update breakdowns
        cat = ineff.category.value
        self.category_breakdown[cat] = self.category_breakdown.get(cat, 0) + 1

        sev = ineff.severity.value
        self.severity_breakdown[sev] = self.severity_breakdown.get(sev, 0) + 1

        # Recalculate inefficiency rate
        if self.total_tokens > 0:
            self.inefficiency_rate = (self.total_wasted_tokens / self.total_tokens) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "task_id": self.task_id,
            "total_tokens": self.total_tokens,
            "total_wasted_tokens": self.total_wasted_tokens,
            "inefficiency_rate": round(self.inefficiency_rate, 1),
            "inefficiencies": [i.to_dict() for i in self.inefficiencies],
            "category_breakdown": self.category_breakdown,
            "severity_breakdown": self.severity_breakdown,
        }


@dataclass
class AggregateInefficiencyReport:
    """
    Aggregated inefficiency report across multiple sessions.
    Used for weekly reports and trend analysis.
    """

    time_period: str  # e.g., "2025-11-25 to 2025-12-01"
    total_sessions: int
    total_tokens: int
    total_wasted_tokens: int
    average_inefficiency_rate: float  # Average across all sessions

    # Session reports
    sessions: list[SessionInefficiencyReport] = field(default_factory=list)

    # Aggregate breakdowns
    category_counts: dict[str, int] = field(default_factory=dict)
    severity_counts: dict[str, int] = field(default_factory=dict)
    sub_category_counts: dict[str, int] = field(default_factory=dict)

    # Top issues
    top_issues: list[dict[str, Any]] = field(default_factory=list)

    def add_session_report(self, report: SessionInefficiencyReport) -> None:
        """Add a session report to this aggregate."""
        self.sessions.append(report)
        self.total_sessions += 1
        self.total_tokens += report.total_tokens
        self.total_wasted_tokens += report.total_wasted_tokens

        # Update category counts
        for cat, count in report.category_breakdown.items():
            self.category_counts[cat] = self.category_counts.get(cat, 0) + count

        # Update severity counts
        for sev, count in report.severity_breakdown.items():
            self.severity_counts[sev] = self.severity_counts.get(sev, 0) + count

        # Update sub-category counts
        for ineff in report.inefficiencies:
            sub = ineff.sub_category
            self.sub_category_counts[sub] = self.sub_category_counts.get(sub, 0) + 1

        # Recalculate average inefficiency rate
        if self.total_sessions > 0:
            self.average_inefficiency_rate = sum(s.inefficiency_rate for s in self.sessions) / self.total_sessions

    def compute_top_issues(self, limit: int = 5) -> None:
        """
        Compute the top N issues by waste impact.

        Populates the top_issues field with the most impactful sub-categories.
        """
        # Aggregate waste by sub-category
        sub_category_waste: dict[str, int] = {}
        sub_category_examples: dict[str, DetectedInefficiency] = {}

        for session in self.sessions:
            for ineff in session.inefficiencies:
                sub = ineff.sub_category
                sub_category_waste[sub] = sub_category_waste.get(sub, 0) + ineff.wasted_tokens
                if sub not in sub_category_examples:
                    sub_category_examples[sub] = ineff

        # Sort by waste
        sorted_issues = sorted(sub_category_waste.items(), key=lambda x: -x[1])[:limit]

        # Build top issues
        self.top_issues = []
        for sub_cat, total_waste in sorted_issues:
            example = sub_category_examples[sub_cat]
            occurrences = self.sub_category_counts[sub_cat]
            self.top_issues.append(
                {
                    "sub_category": sub_cat,
                    "category": example.category.value,
                    "occurrences": occurrences,
                    "total_waste_tokens": total_waste,
                    "example_description": example.description,
                    "recommendation": example.recommendation,
                }
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "time_period": self.time_period,
            "total_sessions": self.total_sessions,
            "total_tokens": self.total_tokens,
            "total_wasted_tokens": self.total_wasted_tokens,
            "average_inefficiency_rate": round(self.average_inefficiency_rate, 1),
            "sessions": [s.to_dict() for s in self.sessions],
            "category_counts": self.category_counts,
            "severity_counts": self.severity_counts,
            "sub_category_counts": self.sub_category_counts,
            "top_issues": self.top_issues,
        }
