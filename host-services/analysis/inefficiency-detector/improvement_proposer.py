"""
Improvement Proposer - Phase 4 of ADR-LLM-Inefficiency-Reporting

Generates improvement proposals based on detected inefficiencies.
Proposals are submitted for human review before implementation.

This implements the "Metacognitive Planning" component of the self-improvement loop:
"What should I do differently?"
- Propose prompt improvements
- Suggest tool usage changes
- Identify missing capabilities
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from inefficiency_schema import AggregateInefficiencyReport, InefficiencyCategory
from proposal_schema import (
    ImprovementProposal,
    ProposalBatch,
    ProposalCategory,
    ProposalPriority,
    ProposalStatus,
    ProposedChange,
)


@dataclass
class ProposalTemplate:
    """Template for generating proposals from specific inefficiency patterns."""

    category: ProposalCategory
    title_template: str
    description_template: str
    rationale_template: str
    changes: list[dict[str, str]]  # Template for changes
    savings_multiplier: float  # Expected % of wasted tokens that can be saved


# Proposal templates for each inefficiency sub-category
PROPOSAL_TEMPLATES: dict[str, ProposalTemplate] = {
    "documentation_miss": ProposalTemplate(
        category=ProposalCategory.PROMPT_REFINEMENT,
        title_template="Tool Discovery Guidance: Prefer Glob Patterns",
        description_template=(
            "Add guidance to CLAUDE.md to prefer glob patterns for file discovery. "
            "This addresses {occurrences} instances of documentation miss where "
            "multiple grep attempts preceded successful glob usage."
        ),
        rationale_template=(
            "Evidence shows {occurrences} documentation miss events this week. "
            "Average {avg_attempts:.1f} search attempts before success. "
            "{success_rate:.0f}% of successful finds used glob pattern. "
            "Wasted tokens: {wasted_tokens:,}"
        ),
        changes=[
            {
                "file_path": "CLAUDE.md",
                "section": "Doing tasks",
                "change_type": "add",
                "description": "Add glob-first guidance for file discovery",
                "content": (
                    "> When searching for files or code locations:\n"
                    "> 1. Start with glob patterns for file discovery (e.g., `**/auth*.py`)\n"
                    "> 2. Use grep only when you know the file exists\n"
                    "> 3. If grep returns 0 results, try glob before broadening grep pattern"
                ),
            }
        ],
        savings_multiplier=0.5,  # Expect 50% reduction
    ),
    "search_failure": ProposalTemplate(
        category=ProposalCategory.PROMPT_REFINEMENT,
        title_template="Search Strategy Guidance",
        description_template=(
            "Add guidance for search strategies when targets don't exist. "
            "{occurrences} instances of extended search failures detected."
        ),
        rationale_template=(
            "Detected {occurrences} extended search failures with no results. "
            "Average {avg_attempts:.1f} attempts per failure sequence. "
            "Wasted tokens: {wasted_tokens:,}"
        ),
        changes=[
            {
                "file_path": "CLAUDE.md",
                "section": "Doing tasks",
                "change_type": "add",
                "description": "Add search verification guidance",
                "content": (
                    "> Before extensive searching:\n"
                    "> - Verify the target likely exists (check related files first)\n"
                    "> - After 2-3 failed searches, reconsider if the target exists\n"
                    "> - Ask for clarification rather than continuing to search"
                ),
            }
        ],
        savings_multiplier=0.4,
    ),
    "api_confusion": ProposalTemplate(
        category=ProposalCategory.PROMPT_REFINEMENT,
        title_template="Tool API Documentation",
        description_template=(
            "Improve tool parameter documentation to reduce confusion. "
            "{occurrences} instances of API confusion detected."
        ),
        rationale_template=(
            "Detected {occurrences} API confusion events where tool parameters "
            "were incorrect on first attempt. Wasted tokens: {wasted_tokens:,}"
        ),
        changes=[
            {
                "file_path": ".claude/rules/tool-usage.md",
                "section": None,
                "change_type": "add",
                "description": "Add tool parameter examples",
                "content": (
                    "# Tool Usage Guide\n\n"
                    "## Read Tool\n"
                    "- Always use absolute paths\n"
                    "- Use `limit` and `offset` for large files\n\n"
                    "## Grep Tool\n"
                    "- Use `glob` parameter to filter file types\n"
                    "- Default output is files only; use `output_mode: content` for matches\n"
                ),
            }
        ],
        savings_multiplier=0.3,
    ),
    "retry_storm": ProposalTemplate(
        category=ProposalCategory.PROMPT_REFINEMENT,
        title_template="Error Handling Guidance",
        description_template=(
            "Add guidance to investigate errors before retrying. "
            "{occurrences} retry storm events with identical errors."
        ),
        rationale_template=(
            "Detected {occurrences} retry storms where the same command failed "
            "3+ times with identical errors. Average {avg_retries:.1f} retries "
            "before investigation. Wasted tokens: {wasted_tokens:,}"
        ),
        changes=[
            {
                "file_path": "CLAUDE.md",
                "section": "Doing tasks",
                "change_type": "add",
                "description": "Add error investigation guidance",
                "content": (
                    "> When a command fails:\n"
                    "> 1. Read the error message carefully\n"
                    "> 2. Investigate the cause before retrying\n"
                    "> 3. Check prerequisites (e.g., npm install, correct directory)\n"
                    "> 4. Never retry more than twice with the same parameters"
                ),
            }
        ],
        savings_multiplier=0.6,
    ),
    "parameter_error": ProposalTemplate(
        category=ProposalCategory.PROMPT_REFINEMENT,
        title_template="Parameter Validation Guidance",
        description_template=(
            "Add guidance to verify tool parameters before calling. "
            "{occurrences} parameter validation errors detected."
        ),
        rationale_template=(
            "Detected {occurrences} parameter validation errors across different tools. "
            "Wasted tokens: {wasted_tokens:,}"
        ),
        changes=[
            {
                "file_path": "CLAUDE.md",
                "section": "Tool usage policy",
                "change_type": "add",
                "description": "Add parameter verification guidance",
                "content": (
                    "> Before calling tools:\n"
                    "> - Verify required parameters are provided\n"
                    "> - Use absolute paths for file operations\n"
                    "> - Check parameter types match expected format"
                ),
            }
        ],
        savings_multiplier=0.4,
    ),
    "redundant_read": ProposalTemplate(
        category=ProposalCategory.PROMPT_REFINEMENT,
        title_template="Context Management Guidance",
        description_template=(
            "Add guidance to avoid re-reading files already in context. "
            "{occurrences} redundant file reads detected."
        ),
        rationale_template=(
            "Detected {occurrences} instances where the same file was read "
            "multiple times in a single session. Wasted tokens: {wasted_tokens:,}"
        ),
        changes=[
            {
                "file_path": "CLAUDE.md",
                "section": "Doing tasks",
                "change_type": "add",
                "description": "Add context reuse guidance",
                "content": (
                    "> For file content:\n"
                    "> - Reference file content from earlier in the conversation\n"
                    "> - Avoid re-reading files already displayed in context\n"
                    "> - If unsure about content, check context before re-reading"
                ),
            }
        ],
        savings_multiplier=0.7,
    ),
    "excessive_context": ProposalTemplate(
        category=ProposalCategory.PROMPT_REFINEMENT,
        title_template="Large File Handling Guidance",
        description_template=(
            "Add guidance to use limit/offset for large files. "
            "{occurrences} instances of excessive context loading detected."
        ),
        rationale_template=(
            "Detected {occurrences} instances where large files (>1000 lines) "
            "were read in full without using limit/offset. Wasted tokens: {wasted_tokens:,}"
        ),
        changes=[
            {
                "file_path": "CLAUDE.md",
                "section": "Tool usage policy",
                "change_type": "add",
                "description": "Add large file handling guidance",
                "content": (
                    "> For large files:\n"
                    "> - Use Read with `limit` and `offset` for files >500 lines\n"
                    "> - Read specific sections rather than entire file\n"
                    "> - Use Grep to find relevant sections first"
                ),
            }
        ],
        savings_multiplier=0.5,
    ),
}


class ImprovementProposer:
    """
    Generates improvement proposals from detected inefficiencies.

    Uses templates to create structured proposals that can be:
    1. Reviewed by humans via Slack
    2. Implemented via PRs
    3. Tracked for impact measurement
    """

    def __init__(
        self,
        proposals_dir: Path | None = None,
        min_occurrences: int = 3,  # Minimum occurrences to generate proposal
        min_wasted_tokens: int = 500,  # Minimum waste to consider
    ):
        """Initialize the improvement proposer.

        Args:
            proposals_dir: Directory to store proposal batches.
            min_occurrences: Minimum inefficiency occurrences to generate proposal.
            min_wasted_tokens: Minimum total wasted tokens to generate proposal.
        """
        self.proposals_dir = proposals_dir or (
            Path(__file__).parent.parent.parent.parent / "docs" / "analysis" / "proposals"
        )
        self.min_occurrences = min_occurrences
        self.min_wasted_tokens = min_wasted_tokens

        # Ensure directory exists
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def generate_proposals(
        self, report: AggregateInefficiencyReport
    ) -> ProposalBatch:
        """
        Generate improvement proposals from an aggregate inefficiency report.

        Args:
            report: Aggregate report from inefficiency detection.

        Returns:
            ProposalBatch containing generated proposals.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        batch = ProposalBatch(
            batch_id=f"batch-{timestamp}",
            created_at=datetime.now(),
            time_period=report.time_period,
        )

        # Aggregate inefficiency data by sub-category
        sub_category_data = self._aggregate_by_sub_category(report)

        # Generate proposals for each sub-category that meets thresholds
        proposal_count = 0
        for sub_category, data in sub_category_data.items():
            if (
                data["occurrences"] >= self.min_occurrences
                and data["wasted_tokens"] >= self.min_wasted_tokens
            ):
                proposal = self._generate_proposal(sub_category, data, proposal_count)
                if proposal:
                    batch.add_proposal(proposal)
                    proposal_count += 1

        return batch

    def _aggregate_by_sub_category(
        self, report: AggregateInefficiencyReport
    ) -> dict[str, dict[str, Any]]:
        """Aggregate inefficiency data by sub-category."""
        aggregated: dict[str, dict[str, Any]] = {}

        for session in report.sessions:
            for ineff in session.inefficiencies:
                sub = ineff.sub_category
                if sub not in aggregated:
                    aggregated[sub] = {
                        "category": ineff.category,
                        "occurrences": 0,
                        "wasted_tokens": 0,
                        "examples": [],
                        "inefficiency_ids": [],
                        "evidence": {},
                    }

                aggregated[sub]["occurrences"] += 1
                aggregated[sub]["wasted_tokens"] += ineff.wasted_tokens
                aggregated[sub]["inefficiency_ids"].append(
                    f"{session.session_id}:{ineff.trace_event_ids[0] if ineff.trace_event_ids else 'unknown'}"
                )

                # Collect examples (limit to 5)
                if len(aggregated[sub]["examples"]) < 5:
                    aggregated[sub]["examples"].append(ineff.description)

                # Merge evidence
                for key, value in ineff.evidence.items():
                    if key not in aggregated[sub]["evidence"]:
                        aggregated[sub]["evidence"][key] = []
                    if isinstance(value, list):
                        aggregated[sub]["evidence"][key].extend(value)
                    else:
                        aggregated[sub]["evidence"][key].append(value)

        return aggregated

    def _generate_proposal(
        self, sub_category: str, data: dict[str, Any], index: int
    ) -> ImprovementProposal | None:
        """Generate a proposal for a specific sub-category."""
        template = PROPOSAL_TEMPLATES.get(sub_category)
        if not template:
            # No template for this sub-category yet
            return None

        timestamp = datetime.now().strftime("%Y%m%d")
        proposal_id = f"prop-{timestamp}-{index + 1:03d}"

        # Calculate expected savings
        expected_savings = int(data["wasted_tokens"] * template.savings_multiplier)

        # Determine priority based on expected savings
        if expected_savings > 1000:
            priority = ProposalPriority.HIGH
        elif expected_savings > 500:
            priority = ProposalPriority.MEDIUM
        else:
            priority = ProposalPriority.LOW

        # Calculate additional stats for templates
        avg_attempts = data["evidence"].get("search_attempts", [])
        avg_attempts = (
            sum(avg_attempts) / len(avg_attempts) if avg_attempts else 3.0
        )
        success_rate = 89.0  # Default based on ADR estimates
        avg_retries = data["evidence"].get("retry_counts", [])
        avg_retries = sum(avg_retries) / len(avg_retries) if avg_retries else 3.0

        # Format template strings
        template_vars = {
            "occurrences": data["occurrences"],
            "wasted_tokens": data["wasted_tokens"],
            "avg_attempts": avg_attempts,
            "success_rate": success_rate,
            "avg_retries": avg_retries,
        }

        description = template.description_template.format(**template_vars)
        rationale = template.rationale_template.format(**template_vars)

        # Build changes
        changes = []
        for change_template in template.changes:
            changes.append(
                ProposedChange(
                    file_path=change_template["file_path"],
                    section=change_template.get("section"),
                    change_type=change_template["change_type"],
                    description=change_template["description"],
                    content=change_template.get("content", ""),
                )
            )

        return ImprovementProposal(
            proposal_id=proposal_id,
            created_at=datetime.now(),
            category=template.category,
            priority=priority,
            status=ProposalStatus.PENDING,
            title=template.title_template,
            description=description,
            rationale=rationale,
            evidence={"examples": data["examples"], **data.get("evidence", {})},
            source_inefficiencies=data["inefficiency_ids"][:10],  # Limit to 10
            occurrences_count=data["occurrences"],
            total_wasted_tokens=data["wasted_tokens"],
            changes=changes,
            expected_token_savings=expected_savings,
            expected_improvement_percent=template.savings_multiplier * 100,
        )

    def save_batch(self, batch: ProposalBatch) -> Path:
        """Save a proposal batch to disk.

        Args:
            batch: The proposal batch to save.

        Returns:
            Path to the saved JSON file.
        """
        filepath = self.proposals_dir / f"{batch.batch_id}.json"
        with open(filepath, "w") as f:
            json.dump(batch.to_dict(), f, indent=2)
        return filepath

    def load_batch(self, batch_id: str) -> ProposalBatch | None:
        """Load a proposal batch from disk.

        Args:
            batch_id: The batch ID to load.

        Returns:
            ProposalBatch or None if not found.
        """
        filepath = self.proposals_dir / f"{batch_id}.json"
        if not filepath.exists():
            return None

        with open(filepath) as f:
            data = json.load(f)
        return ProposalBatch.from_dict(data)

    def list_pending_proposals(self) -> list[ImprovementProposal]:
        """List all pending proposals across all batches.

        Returns:
            List of proposals with PENDING status.
        """
        pending = []
        for filepath in self.proposals_dir.glob("batch-*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                batch = ProposalBatch.from_dict(data)
                pending.extend(
                    p for p in batch.proposals if p.status == ProposalStatus.PENDING
                )
            except (OSError, json.JSONDecodeError):
                continue
        return pending

    def update_proposal_status(
        self,
        proposal_id: str,
        new_status: ProposalStatus,
        reviewed_by: str | None = None,
        review_notes: str | None = None,
    ) -> bool:
        """Update the status of a proposal.

        Args:
            proposal_id: The proposal ID to update.
            new_status: The new status.
            reviewed_by: Who reviewed (if applicable).
            review_notes: Review notes (if applicable).

        Returns:
            True if updated successfully.
        """
        for filepath in self.proposals_dir.glob("batch-*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)

                batch = ProposalBatch.from_dict(data)
                for proposal in batch.proposals:
                    if proposal.proposal_id == proposal_id:
                        proposal.status = new_status
                        proposal.reviewed_at = datetime.now()
                        proposal.reviewed_by = reviewed_by
                        proposal.review_notes = review_notes

                        # Save updated batch
                        with open(filepath, "w") as f:
                            json.dump(batch.to_dict(), f, indent=2)
                        return True

            except (OSError, json.JSONDecodeError):
                continue

        return False

    def generate_slack_summary(self, batch: ProposalBatch) -> str:
        """Generate a Slack-friendly summary of proposals for review.

        Args:
            batch: The proposal batch to summarize.

        Returns:
            Markdown-formatted summary for Slack notification.
        """
        lines = []
        lines.append("# Improvement Proposals Ready for Review")
        lines.append("")
        lines.append(f"**Period:** {batch.time_period}")
        lines.append(f"**Batch ID:** `{batch.batch_id}`")
        lines.append(f"**Total Proposals:** {batch.total_proposals}")
        lines.append(f"**Expected Weekly Savings:** ~{batch.total_expected_savings:,} tokens")
        lines.append("")

        # Group by priority
        high = [p for p in batch.proposals if p.priority == ProposalPriority.HIGH]
        medium = [p for p in batch.proposals if p.priority == ProposalPriority.MEDIUM]
        low = [p for p in batch.proposals if p.priority == ProposalPriority.LOW]

        if high:
            lines.append("## High Priority")
            for p in high:
                lines.append(f"- **{p.title}** (`{p.proposal_id}`)")
                lines.append(f"  - {p.occurrences_count} occurrences, {p.total_wasted_tokens:,} tokens wasted")
                lines.append(f"  - Expected savings: ~{p.expected_token_savings:,} tokens/week")
            lines.append("")

        if medium:
            lines.append("## Medium Priority")
            for p in medium:
                lines.append(f"- **{p.title}** (`{p.proposal_id}`)")
                lines.append(f"  - {p.occurrences_count} occurrences, {p.total_wasted_tokens:,} tokens wasted")
            lines.append("")

        if low:
            lines.append("## Low Priority")
            for p in low:
                lines.append(f"- **{p.title}** (`{p.proposal_id}`)")
            lines.append("")

        # Review instructions
        lines.append("## How to Review")
        lines.append("")
        lines.append("Reply to this message with one of the following commands:")
        lines.append("")
        lines.append("- `approve <proposal_id>` - Approve proposal for implementation")
        lines.append("- `reject <proposal_id> <reason>` - Reject with explanation")
        lines.append("- `defer <proposal_id>` - Revisit next week")
        lines.append("- `details <proposal_id>` - Get full proposal details")
        lines.append("")
        lines.append("Or reply `approve all` to approve all proposals.")

        return "\n".join(lines)
