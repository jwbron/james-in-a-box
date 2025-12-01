"""
Improvement Proposal Schemas - Phase 4 of ADR-LLM-Inefficiency-Reporting

Defines data structures for improvement proposals that are generated from
detected inefficiencies and submitted for human review.

Proposal Categories (from ADR):
- Category A: Prompt Refinements (CLAUDE.md, rules files, system prompts)
- Category B: Tool Additions (new tools or commands)
- Category C: Decision Frameworks (structured approaches for common decisions)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProposalCategory(Enum):
    """Category of improvement proposal from ADR."""

    PROMPT_REFINEMENT = "prompt_refinement"  # Changes to CLAUDE.md, rules
    TOOL_ADDITION = "tool_addition"  # New tools or commands
    DECISION_FRAMEWORK = "decision_framework"  # Structured decision guidance


class ProposalStatus(Enum):
    """Status of an improvement proposal in the review workflow."""

    PENDING = "pending"  # Awaiting human review
    APPROVED = "approved"  # Approved for implementation
    MODIFIED = "modified"  # Approved with modifications
    REJECTED = "rejected"  # Rejected (with reason)
    DEFERRED = "deferred"  # Revisit next week
    IMPLEMENTED = "implemented"  # Change has been applied
    TRACKED = "tracked"  # Impact is being measured


class ProposalPriority(Enum):
    """Priority level for proposals based on potential impact."""

    HIGH = "high"  # >1000 tokens/week potential savings
    MEDIUM = "medium"  # 500-1000 tokens/week potential savings
    LOW = "low"  # <500 tokens/week potential savings


@dataclass
class ProposedChange:
    """A specific change proposed within an improvement proposal."""

    file_path: str  # Target file (e.g., "CLAUDE.md", ".claude/rules/decision-frameworks.md")
    section: str | None  # Section within the file (e.g., "Doing tasks")
    change_type: str  # "add", "modify", "remove"
    description: str  # What to add/change/remove
    content: str  # Actual content to add/modify (if applicable)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "section": self.section,
            "change_type": self.change_type,
            "description": self.description,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProposedChange":
        """Create ProposedChange from dictionary."""
        return cls(
            file_path=data["file_path"],
            section=data.get("section"),
            change_type=data["change_type"],
            description=data["description"],
            content=data.get("content", ""),
        )


@dataclass
class ImprovementProposal:
    """
    An improvement proposal generated from detected inefficiencies.

    This is submitted for human review before implementation.
    """

    # Required fields (no defaults) - must come first
    proposal_id: str  # Unique ID (e.g., "prop-20251201-001")
    created_at: datetime
    category: ProposalCategory
    priority: ProposalPriority
    title: str  # Short title (e.g., "Tool Discovery Guidance")
    description: str  # Detailed description of the proposal
    rationale: str  # Why this proposal is needed

    # Fields with defaults
    status: ProposalStatus = ProposalStatus.PENDING

    # Evidence
    evidence: dict[str, Any] = field(default_factory=dict)  # Supporting data
    source_inefficiencies: list[str] = field(default_factory=list)  # IDs of detected inefficiencies
    occurrences_count: int = 0  # Number of times the pattern was observed
    total_wasted_tokens: int = 0  # Total tokens wasted by this pattern

    # Proposed changes
    changes: list[ProposedChange] = field(default_factory=list)

    # Expected impact
    expected_token_savings: int = 0  # Estimated tokens saved per week
    expected_improvement_percent: float = 0.0  # Expected % reduction in this inefficiency

    # Review tracking
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_notes: str | None = None
    modified_changes: list[ProposedChange] | None = None  # If status is MODIFIED

    # Implementation tracking (Phase 4 impact tracking)
    implemented_at: datetime | None = None
    implementation_pr: str | None = None  # PR URL where change was made

    # Impact measurement
    impact_measurement_started: datetime | None = None
    measured_token_savings: int | None = None  # Actual savings measured
    measured_improvement_percent: float | None = None  # Actual improvement %

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "proposal_id": self.proposal_id,
            "created_at": self.created_at.isoformat(),
            "category": self.category.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "rationale": self.rationale,
            "evidence": self.evidence,
            "source_inefficiencies": self.source_inefficiencies,
            "occurrences_count": self.occurrences_count,
            "total_wasted_tokens": self.total_wasted_tokens,
            "changes": [c.to_dict() for c in self.changes],
            "expected_token_savings": self.expected_token_savings,
            "expected_improvement_percent": round(self.expected_improvement_percent, 1),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewed_by": self.reviewed_by,
            "review_notes": self.review_notes,
            "modified_changes": (
                [c.to_dict() for c in self.modified_changes] if self.modified_changes else None
            ),
            "implemented_at": self.implemented_at.isoformat() if self.implemented_at else None,
            "implementation_pr": self.implementation_pr,
            "impact_measurement_started": (
                self.impact_measurement_started.isoformat()
                if self.impact_measurement_started
                else None
            ),
            "measured_token_savings": self.measured_token_savings,
            "measured_improvement_percent": (
                round(self.measured_improvement_percent, 1)
                if self.measured_improvement_percent is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImprovementProposal":
        """Create ImprovementProposal from dictionary."""
        return cls(
            proposal_id=data["proposal_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            category=ProposalCategory(data["category"]),
            priority=ProposalPriority(data["priority"]),
            status=ProposalStatus(data["status"]),
            title=data["title"],
            description=data["description"],
            rationale=data["rationale"],
            evidence=data.get("evidence", {}),
            source_inefficiencies=data.get("source_inefficiencies", []),
            occurrences_count=data.get("occurrences_count", 0),
            total_wasted_tokens=data.get("total_wasted_tokens", 0),
            changes=[ProposedChange.from_dict(c) for c in data.get("changes", [])],
            expected_token_savings=data.get("expected_token_savings", 0),
            expected_improvement_percent=data.get("expected_improvement_percent", 0.0),
            reviewed_at=(
                datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None
            ),
            reviewed_by=data.get("reviewed_by"),
            review_notes=data.get("review_notes"),
            modified_changes=(
                [ProposedChange.from_dict(c) for c in data["modified_changes"]]
                if data.get("modified_changes")
                else None
            ),
            implemented_at=(
                datetime.fromisoformat(data["implemented_at"])
                if data.get("implemented_at")
                else None
            ),
            implementation_pr=data.get("implementation_pr"),
            impact_measurement_started=(
                datetime.fromisoformat(data["impact_measurement_started"])
                if data.get("impact_measurement_started")
                else None
            ),
            measured_token_savings=data.get("measured_token_savings"),
            measured_improvement_percent=data.get("measured_improvement_percent"),
        )

    def to_markdown(self, include_evidence: bool = True) -> str:
        """Generate markdown representation of the proposal."""
        lines = []

        # Header with priority emoji
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}[self.priority.value]
        status_emoji = {
            "pending": "⏳",
            "approved": "✅",
            "modified": "📝",
            "rejected": "❌",
            "deferred": "⏸️",
            "implemented": "🚀",
            "tracked": "📊",
        }[self.status.value]

        lines.append(f"## {priority_emoji} {self.title}")
        lines.append("")
        lines.append(f"**ID:** `{self.proposal_id}`")
        lines.append(f"**Category:** {self.category.value.replace('_', ' ').title()}")
        lines.append(f"**Priority:** {self.priority.value.upper()}")
        lines.append(f"**Status:** {status_emoji} {self.status.value.upper()}")
        lines.append("")

        # Description
        lines.append("### Description")
        lines.append("")
        lines.append(self.description)
        lines.append("")

        # Rationale
        lines.append("### Rationale")
        lines.append("")
        lines.append(self.rationale)
        lines.append("")

        # Evidence (if requested)
        if include_evidence and self.evidence:
            lines.append("### Evidence")
            lines.append("")
            lines.append(f"- **Occurrences:** {self.occurrences_count}")
            lines.append(f"- **Total Wasted Tokens:** {self.total_wasted_tokens:,}")
            if self.evidence.get("examples"):
                lines.append("- **Example patterns:**")
                for ex in self.evidence["examples"][:3]:
                    lines.append(f"  - {ex}")
            lines.append("")

        # Proposed Changes
        if self.changes:
            lines.append("### Proposed Changes")
            lines.append("")
            for i, change in enumerate(self.changes, 1):
                lines.append(f"**{i}. {change.description}**")
                lines.append("")
                lines.append(f"- **File:** `{change.file_path}`")
                if change.section:
                    lines.append(f"- **Section:** {change.section}")
                lines.append(f"- **Action:** {change.change_type}")
                if change.content:
                    lines.append("")
                    lines.append("```")
                    lines.append(change.content)
                    lines.append("```")
                lines.append("")

        # Expected Impact
        lines.append("### Expected Impact")
        lines.append("")
        lines.append(f"- **Estimated Weekly Savings:** ~{self.expected_token_savings:,} tokens")
        lines.append(f"- **Expected Improvement:** {self.expected_improvement_percent:.0f}%")
        lines.append("")

        # Review status (if reviewed)
        if self.reviewed_at:
            lines.append("### Review")
            lines.append("")
            lines.append(f"- **Reviewed:** {self.reviewed_at.strftime('%Y-%m-%d %H:%M')}")
            if self.reviewed_by:
                lines.append(f"- **By:** {self.reviewed_by}")
            if self.review_notes:
                lines.append(f"- **Notes:** {self.review_notes}")
            lines.append("")

        # Implementation tracking
        if self.implemented_at:
            lines.append("### Implementation")
            lines.append("")
            lines.append(f"- **Implemented:** {self.implemented_at.strftime('%Y-%m-%d')}")
            if self.implementation_pr:
                lines.append(f"- **PR:** {self.implementation_pr}")
            lines.append("")

        # Impact measurement
        if self.measured_token_savings is not None:
            lines.append("### Measured Impact")
            lines.append("")
            lines.append(f"- **Actual Savings:** {self.measured_token_savings:,} tokens/week")
            if self.measured_improvement_percent is not None:
                lines.append(f"- **Actual Improvement:** {self.measured_improvement_percent:.1f}%")
            # Compare to expected
            if self.expected_token_savings > 0:
                ratio = self.measured_token_savings / self.expected_token_savings * 100
                lines.append(f"- **vs Expected:** {ratio:.0f}%")
            lines.append("")

        return "\n".join(lines)


@dataclass
class ProposalBatch:
    """A batch of proposals from a single analysis run."""

    batch_id: str  # e.g., "batch-20251201"
    created_at: datetime
    time_period: str  # Analysis period (e.g., "2025-11-25 to 2025-12-01")
    proposals: list[ImprovementProposal] = field(default_factory=list)

    # Summary stats
    total_proposals: int = 0
    total_expected_savings: int = 0

    def add_proposal(self, proposal: ImprovementProposal) -> None:
        """Add a proposal to this batch."""
        self.proposals.append(proposal)
        self.total_proposals += 1
        self.total_expected_savings += proposal.expected_token_savings

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "batch_id": self.batch_id,
            "created_at": self.created_at.isoformat(),
            "time_period": self.time_period,
            "proposals": [p.to_dict() for p in self.proposals],
            "total_proposals": self.total_proposals,
            "total_expected_savings": self.total_expected_savings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProposalBatch":
        """Create ProposalBatch from dictionary."""
        batch = cls(
            batch_id=data["batch_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            time_period=data["time_period"],
            total_proposals=data.get("total_proposals", 0),
            total_expected_savings=data.get("total_expected_savings", 0),
        )
        batch.proposals = [ImprovementProposal.from_dict(p) for p in data.get("proposals", [])]
        return batch

    def to_markdown(self) -> str:
        """Generate markdown summary of all proposals."""
        lines = []

        lines.append("# Improvement Proposals")
        lines.append("")
        lines.append(f"**Batch ID:** `{self.batch_id}`")
        lines.append(f"**Period:** {self.time_period}")
        lines.append(f"**Generated:** {self.created_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Proposals:** {self.total_proposals}")
        lines.append(f"- **Total Expected Savings:** ~{self.total_expected_savings:,} tokens/week")
        lines.append("")

        # Group by priority
        high = [p for p in self.proposals if p.priority == ProposalPriority.HIGH]
        medium = [p for p in self.proposals if p.priority == ProposalPriority.MEDIUM]
        low = [p for p in self.proposals if p.priority == ProposalPriority.LOW]

        if high:
            lines.append("## High Priority")
            lines.append("")
            for p in high:
                lines.append(p.to_markdown(include_evidence=False))
                lines.append("")
                lines.append("---")
                lines.append("")

        if medium:
            lines.append("## Medium Priority")
            lines.append("")
            for p in medium:
                lines.append(p.to_markdown(include_evidence=False))
                lines.append("")
                lines.append("---")
                lines.append("")

        if low:
            lines.append("## Low Priority")
            lines.append("")
            for p in low:
                lines.append(p.to_markdown(include_evidence=False))
                lines.append("")
                lines.append("---")
                lines.append("")

        return "\n".join(lines)
