"""
Impact Tracker - Phase 4 of ADR-LLM-Inefficiency-Reporting

Tracks the impact of implemented improvement proposals.
This implements the "Metacognitive Evaluation" component of the self-improvement loop:
"Did the changes help?"
- Measure improvement impact
- Validate hypotheses
- Refine or revert changes
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from proposal_schema import (
    ImprovementProposal,
    ProposalBatch,
    ProposalStatus,
)


@dataclass
class ImpactMeasurement:
    """A single impact measurement for an implemented proposal."""

    proposal_id: str
    measurement_date: datetime

    # Before metrics (from the week the proposal was based on)
    baseline_occurrences: int
    baseline_wasted_tokens: int

    # After metrics (from the week after implementation)
    measured_occurrences: int
    measured_wasted_tokens: int

    # Calculated impact
    occurrence_reduction: int  # baseline - measured
    token_savings: int  # baseline - measured
    improvement_percent: float  # (baseline - measured) / baseline * 100

    # Comparison to expected
    expected_savings: int
    savings_ratio: float  # actual / expected

    # Notes
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "proposal_id": self.proposal_id,
            "measurement_date": self.measurement_date.isoformat(),
            "baseline_occurrences": self.baseline_occurrences,
            "baseline_wasted_tokens": self.baseline_wasted_tokens,
            "measured_occurrences": self.measured_occurrences,
            "measured_wasted_tokens": self.measured_wasted_tokens,
            "occurrence_reduction": self.occurrence_reduction,
            "token_savings": self.token_savings,
            "improvement_percent": round(self.improvement_percent, 1),
            "expected_savings": self.expected_savings,
            "savings_ratio": round(self.savings_ratio, 2),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImpactMeasurement":
        """Create ImpactMeasurement from dictionary."""
        return cls(
            proposal_id=data["proposal_id"],
            measurement_date=datetime.fromisoformat(data["measurement_date"]),
            baseline_occurrences=data["baseline_occurrences"],
            baseline_wasted_tokens=data["baseline_wasted_tokens"],
            measured_occurrences=data["measured_occurrences"],
            measured_wasted_tokens=data["measured_wasted_tokens"],
            occurrence_reduction=data["occurrence_reduction"],
            token_savings=data["token_savings"],
            improvement_percent=data["improvement_percent"],
            expected_savings=data["expected_savings"],
            savings_ratio=data["savings_ratio"],
            notes=data.get("notes"),
        )


@dataclass
class ImpactReport:
    """Aggregate impact report across multiple implemented proposals."""

    report_date: datetime
    time_period: str  # Measurement period

    # Aggregate metrics
    total_proposals_tracked: int = 0
    total_expected_savings: int = 0
    total_actual_savings: int = 0
    overall_savings_ratio: float = 0.0

    # Individual measurements
    measurements: list[ImpactMeasurement] = field(default_factory=list)

    # Proposals that need attention
    underperforming: list[str] = field(default_factory=list)  # proposal_ids
    overperforming: list[str] = field(default_factory=list)  # proposal_ids

    def add_measurement(self, measurement: ImpactMeasurement) -> None:
        """Add a measurement to this report."""
        self.measurements.append(measurement)
        self.total_proposals_tracked += 1
        self.total_expected_savings += measurement.expected_savings
        self.total_actual_savings += measurement.token_savings

        # Update overall ratio
        if self.total_expected_savings > 0:
            self.overall_savings_ratio = self.total_actual_savings / self.total_expected_savings

        # Track under/over performing
        if measurement.savings_ratio < 0.5:  # Less than 50% of expected
            self.underperforming.append(measurement.proposal_id)
        elif measurement.savings_ratio > 1.5:  # More than 150% of expected
            self.overperforming.append(measurement.proposal_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "report_date": self.report_date.isoformat(),
            "time_period": self.time_period,
            "total_proposals_tracked": self.total_proposals_tracked,
            "total_expected_savings": self.total_expected_savings,
            "total_actual_savings": self.total_actual_savings,
            "overall_savings_ratio": round(self.overall_savings_ratio, 2),
            "measurements": [m.to_dict() for m in self.measurements],
            "underperforming": self.underperforming,
            "overperforming": self.overperforming,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImpactReport":
        """Create ImpactReport from dictionary."""
        report = cls(
            report_date=datetime.fromisoformat(data["report_date"]),
            time_period=data["time_period"],
            total_proposals_tracked=data.get("total_proposals_tracked", 0),
            total_expected_savings=data.get("total_expected_savings", 0),
            total_actual_savings=data.get("total_actual_savings", 0),
            overall_savings_ratio=data.get("overall_savings_ratio", 0.0),
            underperforming=data.get("underperforming", []),
            overperforming=data.get("overperforming", []),
        )
        report.measurements = [
            ImpactMeasurement.from_dict(m) for m in data.get("measurements", [])
        ]
        return report

    def to_markdown(self) -> str:
        """Generate markdown representation of the impact report."""
        lines = []

        lines.append("# Impact Report")
        lines.append("")
        lines.append(f"**Period:** {self.time_period}")
        lines.append(f"**Generated:** {self.report_date.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Proposals Tracked:** {self.total_proposals_tracked}")
        lines.append(f"- **Expected Savings:** {self.total_expected_savings:,} tokens")
        lines.append(f"- **Actual Savings:** {self.total_actual_savings:,} tokens")
        lines.append(f"- **Effectiveness:** {self.overall_savings_ratio * 100:.0f}%")
        lines.append("")

        # Effectiveness interpretation
        if self.overall_savings_ratio >= 1.0:
            lines.append("Improvements are **meeting or exceeding** expectations.")
        elif self.overall_savings_ratio >= 0.7:
            lines.append("Improvements are **mostly effective** (70%+ of expected).")
        elif self.overall_savings_ratio >= 0.5:
            lines.append("Improvements are **partially effective** (50-70% of expected).")
        else:
            lines.append("Improvements are **underperforming** (<50% of expected). Consider reviewing proposals.")
        lines.append("")

        # Individual measurements
        if self.measurements:
            lines.append("## Individual Measurements")
            lines.append("")
            lines.append("| Proposal | Baseline | Measured | Savings | Expected | Ratio |")
            lines.append("|----------|----------|----------|---------|----------|-------|")

            for m in sorted(self.measurements, key=lambda x: -x.token_savings):
                emoji = "✅" if m.savings_ratio >= 0.7 else "⚠️" if m.savings_ratio >= 0.5 else "❌"
                lines.append(
                    f"| {emoji} `{m.proposal_id}` | {m.baseline_wasted_tokens:,} | "
                    f"{m.measured_wasted_tokens:,} | {m.token_savings:,} | "
                    f"{m.expected_savings:,} | {m.savings_ratio:.0%} |"
                )
            lines.append("")

        # Underperforming proposals
        if self.underperforming:
            lines.append("## Underperforming Proposals")
            lines.append("")
            lines.append("These proposals achieved less than 50% of expected savings:")
            for pid in self.underperforming:
                lines.append(f"- `{pid}` - Consider reviewing or reverting")
            lines.append("")

        # Overperforming proposals
        if self.overperforming:
            lines.append("## Overperforming Proposals")
            lines.append("")
            lines.append("These proposals exceeded expectations (>150%):")
            for pid in self.overperforming:
                lines.append(f"- `{pid}` - Consider applying similar patterns elsewhere")
            lines.append("")

        return "\n".join(lines)


class ImpactTracker:
    """
    Tracks the impact of implemented improvement proposals.

    Workflow:
    1. When a proposal is implemented, mark it for tracking
    2. After one week, measure the impact
    3. Compare actual vs expected savings
    4. Generate impact report
    """

    def __init__(
        self,
        tracking_dir: Path | None = None,
        proposals_dir: Path | None = None,
        measurement_delay_days: int = 7,  # Days after implementation to measure
    ):
        """Initialize the impact tracker.

        Args:
            tracking_dir: Directory to store tracking data.
            proposals_dir: Directory containing proposal batches.
            measurement_delay_days: Days to wait before measuring impact.
        """
        base_dir = Path(__file__).parent.parent.parent.parent
        self.tracking_dir = tracking_dir or (base_dir / "docs" / "analysis" / "impact")
        self.proposals_dir = proposals_dir or (base_dir / "docs" / "analysis" / "proposals")
        self.measurement_delay_days = measurement_delay_days

        # Ensure directories exist
        self.tracking_dir.mkdir(parents=True, exist_ok=True)

    def mark_implemented(
        self,
        proposal_id: str,
        implementation_pr: str,
        implemented_at: datetime | None = None,
    ) -> bool:
        """Mark a proposal as implemented and start impact tracking.

        Args:
            proposal_id: The proposal ID that was implemented.
            implementation_pr: URL of the PR where it was implemented.
            implemented_at: When it was implemented (default: now).

        Returns:
            True if marked successfully.
        """
        implemented_at = implemented_at or datetime.now()

        # Find and update the proposal
        for filepath in self.proposals_dir.glob("batch-*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)

                batch = ProposalBatch.from_dict(data)
                for proposal in batch.proposals:
                    if proposal.proposal_id == proposal_id:
                        proposal.status = ProposalStatus.IMPLEMENTED
                        proposal.implemented_at = implemented_at
                        proposal.implementation_pr = implementation_pr
                        proposal.impact_measurement_started = implemented_at

                        # Save updated batch
                        with open(filepath, "w") as f:
                            json.dump(batch.to_dict(), f, indent=2)

                        # Create tracking entry
                        self._create_tracking_entry(proposal)
                        return True

            except (OSError, json.JSONDecodeError):
                continue

        return False

    def _create_tracking_entry(self, proposal: ImprovementProposal) -> None:
        """Create a tracking entry for an implemented proposal."""
        entry = {
            "proposal_id": proposal.proposal_id,
            "sub_category": proposal.source_inefficiencies[0].split(":")[0] if proposal.source_inefficiencies else "unknown",
            "implemented_at": proposal.implemented_at.isoformat() if proposal.implemented_at else None,
            "expected_savings": proposal.expected_token_savings,
            "baseline_occurrences": proposal.occurrences_count,
            "baseline_wasted_tokens": proposal.total_wasted_tokens,
            "measurement_due": (
                (proposal.implemented_at + timedelta(days=self.measurement_delay_days)).isoformat()
                if proposal.implemented_at
                else None
            ),
            "measured": False,
        }

        # Save tracking entry
        tracking_file = self.tracking_dir / f"tracking-{proposal.proposal_id}.json"
        with open(tracking_file, "w") as f:
            json.dump(entry, f, indent=2)

    def get_proposals_due_for_measurement(self) -> list[dict[str, Any]]:
        """Get proposals that are due for impact measurement.

        Returns:
            List of tracking entries that need measurement.
        """
        due = []
        now = datetime.now()

        for filepath in self.tracking_dir.glob("tracking-*.json"):
            try:
                with open(filepath) as f:
                    entry = json.load(f)

                if entry.get("measured"):
                    continue

                measurement_due = entry.get("measurement_due")
                if measurement_due:
                    due_date = datetime.fromisoformat(measurement_due)
                    if now >= due_date:
                        entry["tracking_file"] = str(filepath)
                        due.append(entry)

            except (OSError, json.JSONDecodeError):
                continue

        return due

    def record_measurement(
        self,
        proposal_id: str,
        measured_occurrences: int,
        measured_wasted_tokens: int,
        notes: str | None = None,
    ) -> ImpactMeasurement | None:
        """Record an impact measurement for a proposal.

        Args:
            proposal_id: The proposal being measured.
            measured_occurrences: Number of occurrences in measurement period.
            measured_wasted_tokens: Wasted tokens in measurement period.
            notes: Optional notes about the measurement.

        Returns:
            ImpactMeasurement if recorded successfully.
        """
        # Find the tracking entry
        tracking_file = self.tracking_dir / f"tracking-{proposal_id}.json"
        if not tracking_file.exists():
            return None

        with open(tracking_file) as f:
            entry = json.load(f)

        # Calculate impact
        baseline_occurrences = entry["baseline_occurrences"]
        baseline_wasted_tokens = entry["baseline_wasted_tokens"]
        expected_savings = entry["expected_savings"]

        occurrence_reduction = baseline_occurrences - measured_occurrences
        token_savings = baseline_wasted_tokens - measured_wasted_tokens
        improvement_percent = (
            (token_savings / baseline_wasted_tokens * 100) if baseline_wasted_tokens > 0 else 0.0
        )
        savings_ratio = token_savings / expected_savings if expected_savings > 0 else 0.0

        measurement = ImpactMeasurement(
            proposal_id=proposal_id,
            measurement_date=datetime.now(),
            baseline_occurrences=baseline_occurrences,
            baseline_wasted_tokens=baseline_wasted_tokens,
            measured_occurrences=measured_occurrences,
            measured_wasted_tokens=measured_wasted_tokens,
            occurrence_reduction=occurrence_reduction,
            token_savings=token_savings,
            improvement_percent=improvement_percent,
            expected_savings=expected_savings,
            savings_ratio=savings_ratio,
            notes=notes,
        )

        # Update tracking entry
        entry["measured"] = True
        entry["measurement"] = measurement.to_dict()
        with open(tracking_file, "w") as f:
            json.dump(entry, f, indent=2)

        # Update the proposal with measured impact
        self._update_proposal_impact(proposal_id, measurement)

        return measurement

    def _update_proposal_impact(
        self, proposal_id: str, measurement: ImpactMeasurement
    ) -> None:
        """Update a proposal with its measured impact."""
        for filepath in self.proposals_dir.glob("batch-*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)

                batch = ProposalBatch.from_dict(data)
                for proposal in batch.proposals:
                    if proposal.proposal_id == proposal_id:
                        proposal.status = ProposalStatus.TRACKED
                        proposal.measured_token_savings = measurement.token_savings
                        proposal.measured_improvement_percent = measurement.improvement_percent

                        with open(filepath, "w") as f:
                            json.dump(batch.to_dict(), f, indent=2)
                        return

            except (OSError, json.JSONDecodeError):
                continue

    def generate_impact_report(self, time_period: str | None = None) -> ImpactReport:
        """Generate an impact report for all tracked proposals.

        Args:
            time_period: Description of the time period (default: auto-generated).

        Returns:
            ImpactReport with all measurements.
        """
        if time_period is None:
            time_period = f"Through {datetime.now().strftime('%Y-%m-%d')}"

        report = ImpactReport(
            report_date=datetime.now(),
            time_period=time_period,
        )

        # Collect all measurements
        for filepath in self.tracking_dir.glob("tracking-*.json"):
            try:
                with open(filepath) as f:
                    entry = json.load(f)

                if entry.get("measured") and entry.get("measurement"):
                    measurement = ImpactMeasurement.from_dict(entry["measurement"])
                    report.add_measurement(measurement)

            except (OSError, json.JSONDecodeError):
                continue

        return report

    def save_impact_report(self, report: ImpactReport) -> Path:
        """Save an impact report to disk.

        Args:
            report: The impact report to save.

        Returns:
            Path to the saved file.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filepath = self.tracking_dir / f"impact-report-{timestamp}.json"

        with open(filepath, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

        # Also save markdown version
        md_filepath = self.tracking_dir / f"impact-report-{timestamp}.md"
        with open(md_filepath, "w") as f:
            f.write(report.to_markdown())

        return filepath

    def get_implementation_summary(self) -> dict[str, Any]:
        """Get a summary of all implemented proposals and their status.

        Returns:
            Dictionary with implementation statistics.
        """
        summary = {
            "total_implemented": 0,
            "awaiting_measurement": 0,
            "measured": 0,
            "total_expected_savings": 0,
            "total_actual_savings": 0,
            "overall_effectiveness": 0.0,
            "proposals": [],
        }

        for filepath in self.tracking_dir.glob("tracking-*.json"):
            try:
                with open(filepath) as f:
                    entry = json.load(f)

                summary["total_implemented"] += 1
                summary["total_expected_savings"] += entry.get("expected_savings", 0)

                if entry.get("measured"):
                    summary["measured"] += 1
                    measurement = entry.get("measurement", {})
                    summary["total_actual_savings"] += measurement.get("token_savings", 0)
                else:
                    summary["awaiting_measurement"] += 1

                summary["proposals"].append({
                    "proposal_id": entry["proposal_id"],
                    "implemented_at": entry.get("implemented_at"),
                    "measured": entry.get("measured", False),
                    "expected_savings": entry.get("expected_savings", 0),
                    "actual_savings": entry.get("measurement", {}).get("token_savings"),
                })

            except (OSError, json.JSONDecodeError):
                continue

        if summary["total_expected_savings"] > 0:
            summary["overall_effectiveness"] = (
                summary["total_actual_savings"] / summary["total_expected_savings"]
            )

        return summary
