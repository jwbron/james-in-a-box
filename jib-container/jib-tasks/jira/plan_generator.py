#!/usr/bin/env python3
"""
Plan Generator - Creates Collaborative Planning Framework (CPF) documents for non-trivial JIRA tickets.

When a ticket is classified as non-trivial, this module generates a structured
planning document that follows the CPF specification, enabling human-LLM collaboration.

The generated document is designed to be:
- Human-readable for review and approval
- Machine-consumable for subsequent implementation
- Clear about requirements, ambiguities, and proposed approaches

Part of the JIRA Ticket Triage Workflow (ADR).
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from jib_tasks.jira.context_gatherer import GatheredContext
    from jib_tasks.jira.triviality_assessor import TrivialityAssessment


@dataclass
class GeneratedPlan:
    """Container for a generated planning document."""

    ticket_key: str
    title: str
    content: str
    file_path: str  # Relative path where the plan should be stored
    pr_title: str
    pr_body: str

    def to_file(self, base_dir: Path | str) -> Path:
        """Write the plan to a file.

        Args:
            base_dir: Base directory for the repository

        Returns:
            Path to the written file
        """
        base_dir = Path(base_dir)
        full_path = base_dir / self.file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(self.content)
        return full_path


class PlanGenerator:
    """Generates CPF planning documents for non-trivial JIRA tickets."""

    def __init__(self, plan_output_dir: str | None = None):
        """Initialize the plan generator.

        Args:
            plan_output_dir: Directory for plan files (default from env or docs/plans)
        """
        self.plan_output_dir = plan_output_dir or os.environ.get("JIB_PLAN_OUTPUT_DIR", "docs/plans")

    def generate(
        self,
        ticket: dict,
        context: "GatheredContext",
        assessment: "TrivialityAssessment",
    ) -> GeneratedPlan:
        """Generate a CPF planning document for a non-trivial ticket.

        Args:
            ticket: Ticket data with keys: key, title, description, labels
            context: Gathered context for the ticket
            assessment: Triviality assessment result

        Returns:
            GeneratedPlan with the document and metadata
        """
        ticket_key = ticket.get("key", "UNKNOWN")
        title = ticket.get("title", "Untitled")
        description = ticket.get("description", "")

        # Generate slug for filename
        slug = self._generate_slug(title)
        file_path = f"{self.plan_output_dir}/{ticket_key}-{slug}.md"

        # Generate the planning document
        content = self._generate_document(ticket, context, assessment)

        # Generate PR metadata
        pr_title = f"[JIB] Plan: {ticket_key} {title}"
        pr_body = self._generate_pr_body(ticket, assessment)

        return GeneratedPlan(
            ticket_key=ticket_key,
            title=title,
            content=content,
            file_path=file_path,
            pr_title=pr_title,
            pr_body=pr_body,
        )

    def _generate_slug(self, title: str) -> str:
        """Generate a URL-safe slug from the title."""
        # Convert to lowercase and replace spaces with hyphens
        slug = title.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)
        slug = slug.strip("-")
        return slug[:50]  # Limit length

    def _generate_document(
        self,
        ticket: dict,
        context: "GatheredContext",
        assessment: "TrivialityAssessment",
    ) -> str:
        """Generate the full planning document content."""
        ticket_key = ticket.get("key", "UNKNOWN")
        title = ticket.get("title", "Untitled")
        description = ticket.get("description", "")
        labels = ticket.get("labels", [])

        # Extract estimated scope from context
        estimated_scope = self._estimate_scope(context, assessment)

        # Extract questions/ambiguities
        questions = self._extract_questions(description, context)

        # Identify affected areas
        affected_areas = self._identify_affected_areas(context)

        # Generate the document
        lines = []

        # Header
        lines.append(f"# Plan: {title}")
        lines.append("")
        lines.append(f"**JIRA:** [{ticket_key}](https://khanacademy.atlassian.net/browse/{ticket_key})")
        lines.append("**Status:** Proposed - Awaiting Human Approval")
        lines.append("**Complexity:** Non-trivial")
        lines.append(f"**Estimated Scope:** {estimated_scope}")
        lines.append(f"**Triviality Score:** {assessment.score}/100 (threshold: {assessment.threshold})")
        if assessment.disqualifiers:
            lines.append(f"**Disqualifier(s):** {', '.join(assessment.disqualifiers)}")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Checkpoint section
        lines.append("## Checkpoint: Planning Complete")
        lines.append("")
        lines.append(
            "> This document represents JIB's analysis of the JIRA ticket. "
            "Human approval is required before implementation begins."
        )
        lines.append("")
        lines.append("### Summary")
        lines.append("")
        lines.append(self._generate_summary(title, description))
        lines.append("")
        lines.append("### Quick Actions")
        lines.append("")
        lines.append("- [ ] **APPROVE** — JIB proceeds with implementation")
        lines.append("- [ ] **APPROVE WITH NOTES** — JIB proceeds with adjustments (add comments to PR)")
        lines.append("- [ ] **REVISE** — JIB needs to revisit analysis (request changes on PR)")
        lines.append("- [ ] **REJECT** — Do not implement (close PR without merging)")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Requirements Analysis
        lines.append("## Requirements Analysis")
        lines.append("")
        lines.append("### Goals")
        lines.append("")
        lines.append("| Priority | Goal | Source |")
        lines.append("|----------|------|--------|")
        lines.append(f"| Primary | {self._extract_primary_goal(title, description)} | JIRA ticket |")
        secondary_goal = self._extract_secondary_goal(description, context)
        if secondary_goal:
            lines.append(f"| Secondary | {secondary_goal} | inference |")
        lines.append("")

        lines.append("### Functional Requirements")
        lines.append("")
        lines.append("| ID | Requirement | Acceptance Criteria | Confidence |")
        lines.append("|----|-------------|---------------------|------------|")
        requirements = self._extract_requirements(description)
        for i, req in enumerate(requirements, 1):
            lines.append(f"| FR-{i} | {req['requirement']} | {req['criteria']} | {req['confidence']} |")
        lines.append("")

        lines.append("### Out of Scope (Negative Requirements)")
        lines.append("")
        lines.append("- Related changes not explicitly mentioned in the ticket")
        lines.append("- Performance optimizations beyond what's needed for functionality")
        lines.append("- UI/UX changes unless specified")
        lines.append("")

        lines.append("### Assumptions")
        lines.append("")
        lines.append("| Assumption | Validated? | Impact if Wrong |")
        lines.append("|------------|------------|-----------------|")
        assumptions = self._generate_assumptions(context, description)
        for assumption in assumptions:
            lines.append(f"| {assumption['text']} | {assumption['validated']} | {assumption['impact']} |")
        lines.append("")

        # Questions section
        if questions:
            lines.append("### Ambiguities & Questions")
            lines.append("")
            lines.append(
                "> **⚠️ Human input needed:** The following questions require clarification. "
                "JIB recommends addressing these before approving."
            )
            lines.append("")
            for i, q in enumerate(questions, 1):
                lines.append(f"{i}. **{q['question']}**")
                lines.append(f"   - **Context:** {q['context']}")
                if q.get("options"):
                    lines.append("   - **Options:**")
                    for opt in q["options"]:
                        lines.append(f"     - {opt}")
                if q.get("recommendation"):
                    lines.append(f"   - **JIB Recommendation:** {q['recommendation']}")
                lines.append("")

        lines.append("---")
        lines.append("")

        # Technical Analysis
        lines.append("## Technical Analysis")
        lines.append("")
        lines.append("### Affected Areas")
        lines.append("")
        lines.append("| File/Component | Change Type | Reason |")
        lines.append("|---------------|-------------|--------|")
        for area in affected_areas[:10]:
            lines.append(f"| `{area['path']}` | {area['change_type']} | {area['reason']} |")
        lines.append("")

        # Risk Register
        lines.append("### Risk Register")
        lines.append("")
        lines.append("| Risk | Impact | Likelihood | Mitigation |")
        lines.append("|------|--------|------------|------------|")
        risks = self._identify_risks(assessment, context)
        for risk in risks:
            lines.append(f"| {risk['description']} | {risk['impact']} | {risk['likelihood']} | {risk['mitigation']} |")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Design Options
        lines.append("## Design Options")
        lines.append("")
        lines.append("### Option A: Direct Implementation ⭐ (Recommended)")
        lines.append("")
        lines.append("Implement the change directly following existing patterns in the codebase.")
        lines.append("")
        lines.append("**Pros:**")
        lines.append("- Consistent with existing code")
        lines.append("- Lower risk of introducing new patterns")
        lines.append("")
        lines.append("**Cons:**")
        lines.append("- May not address underlying architectural issues")
        lines.append("")
        lines.append("### Option B: Alternative Approach")
        lines.append("")
        lines.append("*To be filled in if alternative approaches are identified during analysis.*")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Implementation Plan
        lines.append("## Implementation Plan")
        lines.append("")
        lines.append("### Phase 1: Core Implementation")
        lines.append("**Objective:** Implement the primary functionality")
        lines.append("")
        lines.append("| Task | Dependencies | Acceptance Criteria |")
        lines.append("|------|--------------|---------------------|")
        lines.append("| Implement core changes | None | Code compiles and basic tests pass |")
        lines.append("| Add/update tests | Core changes | All tests pass |")
        lines.append("| Update documentation | Tests pass | Docs reflect new behavior |")
        lines.append("")
        lines.append("**Phase 1 Checkpoint:** Core functionality works, tests pass")
        lines.append("")

        # Test Strategy
        lines.append("---")
        lines.append("")
        lines.append("## Test Strategy")
        lines.append("")
        lines.append("| Test Type | Scope | Coverage Target |")
        lines.append("|-----------|-------|-----------------|")
        lines.append("| Unit Tests | New/modified functions | 80% |")
        lines.append("| Integration Tests | Affected flows | Key paths covered |")
        lines.append("| Manual Testing | Edge cases | Exploratory testing |")
        lines.append("")

        # Post-Approval Workflow
        lines.append("---")
        lines.append("")
        lines.append("## Post-Approval Workflow")
        lines.append("")
        lines.append("After human merges this planning PR:")
        lines.append("1. **JIB detects merge** via GitHub sync")
        lines.append("2. **JIB enters CPF implementation** following the phased plan above")
        lines.append("3. **Implementation PR created** with code changes, tests, documentation")
        lines.append("4. **Human reviews implementation PR** and merges when satisfied")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("**Generated by:** james-in-a-box")
        lines.append(f"**Triaged from:** [{ticket_key}](https://khanacademy.atlassian.net/browse/{ticket_key})")
        context_sources = [f["path"] for f in context.related_files[:5]] if context.related_files else ["ticket"]
        lines.append(f"**Context Sources:** {', '.join(context_sources)}")
        lines.append("**Awaiting:** Human review and approval (merge this PR to proceed)")

        return "\n".join(lines)

    def _generate_summary(self, title: str, description: str) -> str:
        """Generate a 2-3 sentence summary."""
        # Simple extraction of first sentence(s) from description
        sentences = re.split(r"[.!?]+", description)
        summary = ". ".join(s.strip() for s in sentences[:2] if s.strip())
        if not summary:
            summary = f"This ticket requests: {title}"
        return summary[:300]  # Limit length

    def _extract_primary_goal(self, title: str, description: str) -> str:
        """Extract the primary goal from the ticket."""
        # Use title as primary goal, cleaned up
        return title[:100]

    def _extract_secondary_goal(self, description: str, context: "GatheredContext") -> str | None:
        """Extract secondary goals if present."""
        # Look for "also" or similar patterns
        patterns = [r"also\s+(.+?)[.,]", r"additionally\s+(.+?)[.,]", r"and\s+(.+?)[.,]"]
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:100]
        return None

    def _extract_requirements(self, description: str) -> list[dict]:
        """Extract functional requirements from the description."""
        requirements = []

        # Split by common separators
        lines = description.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith(("-", "*", "•")) or re.match(r"^\d+\.", line):
                # Remove bullet/number
                req_text = re.sub(r"^[-*•\d.]+\s*", "", line)
                if len(req_text) > 10:
                    requirements.append(
                        {
                            "requirement": req_text[:100],
                            "criteria": "Implemented as specified",
                            "confidence": "medium",
                        }
                    )

        # If no list items found, extract from description
        if not requirements and description:
            requirements.append(
                {
                    "requirement": description[:100],
                    "criteria": "Ticket requirements met",
                    "confidence": "medium",
                }
            )

        return requirements[:5]  # Limit to 5

    def _extract_questions(self, description: str, context: "GatheredContext") -> list[dict]:
        """Extract questions and ambiguities."""
        questions = []

        # Look for explicit questions
        explicit_questions = re.findall(r"([^.!?]*\?)", description)
        for q in explicit_questions[:3]:
            q = q.strip()
            if len(q) > 10:
                questions.append(
                    {
                        "question": q,
                        "context": "Explicit question in ticket",
                        "options": [],
                        "recommendation": None,
                    }
                )

        # Look for ambiguity indicators
        ambiguity_patterns = [
            (r"(unclear|not sure|maybe|possibly) (.+?)[.,]", "Ambiguous requirement"),
            (r"(or|versus|vs\.?) (.+?)[.,]", "Multiple options mentioned"),
        ]

        for pattern, context_text in ambiguity_patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches[:2]:
                questions.append(
                    {
                        "question": f"Clarification needed: {match[1]}",
                        "context": context_text,
                        "options": [],
                        "recommendation": None,
                    }
                )

        return questions[:5]

    def _identify_affected_areas(self, context: "GatheredContext") -> list[dict]:
        """Identify code areas that will be affected."""
        affected = []

        if context.related_files:
            for f in context.related_files[:10]:
                affected.append(
                    {
                        "path": f["path"].split("/")[-1],  # Just filename
                        "change_type": "Modify",
                        "reason": f.get("relevance", "Related to ticket"),
                    }
                )

        if not affected:
            affected.append(
                {
                    "path": "TBD during implementation",
                    "change_type": "Unknown",
                    "reason": "Specific files to be determined",
                }
            )

        return affected

    def _identify_risks(
        self,
        assessment: "TrivialityAssessment",
        context: "GatheredContext",
    ) -> list[dict]:
        """Identify potential risks."""
        risks = []

        # Add risks based on disqualifiers
        if assessment.disqualifiers:
            for d in assessment.disqualifiers:
                risks.append(
                    {
                        "description": f"{d.replace('_', ' ').title()} concerns",
                        "impact": "High",
                        "likelihood": "Medium",
                        "mitigation": "Careful review and testing",
                    }
                )

        # Add standard risks
        risks.append(
            {
                "description": "Incomplete requirements",
                "impact": "Medium",
                "likelihood": "Medium",
                "mitigation": "Clarify questions before implementation",
            }
        )

        return risks[:5]

    def _generate_assumptions(self, context: "GatheredContext", description: str) -> list[dict]:
        """Generate assumptions list."""
        assumptions = []

        # Standard assumptions
        assumptions.append(
            {
                "text": "Existing test suite covers related functionality",
                "validated": "needs validation",
                "impact": "May need additional tests",
            }
        )

        assumptions.append(
            {"text": "No breaking changes to existing APIs", "validated": "no", "impact": "Would require migration plan"}
        )

        return assumptions

    def _estimate_scope(self, context: "GatheredContext", assessment: "TrivialityAssessment") -> str:
        """Estimate the scope of the change."""
        score = assessment.score

        if score >= 70:
            return "small"
        elif score >= 40:
            return "medium"
        else:
            return "large"

    def _generate_pr_body(self, ticket: dict, assessment: "TrivialityAssessment") -> str:
        """Generate PR body for the planning document."""
        ticket_key = ticket.get("key", "UNKNOWN")
        title = ticket.get("title", "Untitled")

        lines = []
        lines.append("## Summary")
        lines.append("")
        lines.append(f"This PR contains a planning document for [{ticket_key}](https://khanacademy.atlassian.net/browse/{ticket_key}): {title}")
        lines.append("")
        lines.append("The ticket was classified as **non-trivial** by JIB's triage system:")
        lines.append(f"- Triviality Score: {assessment.score}/100 (threshold: {assessment.threshold})")
        if assessment.disqualifiers:
            lines.append(f"- Disqualifiers: {', '.join(assessment.disqualifiers)}")
        lines.append("")
        lines.append("## Actions")
        lines.append("")
        lines.append("Please review the planning document and:")
        lines.append("- **Merge** to approve the plan and trigger implementation")
        lines.append("- **Request changes** if the plan needs revision")
        lines.append("- **Close** if the ticket should not be implemented")
        lines.append("")
        lines.append("## Test Plan")
        lines.append("")
        lines.append("- [ ] Review planning document for completeness")
        lines.append("- [ ] Verify requirements are correctly understood")
        lines.append("- [ ] Answer any questions in the document")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("🤖 Generated with [Claude Code](https://claude.com/claude-code)")

        return "\n".join(lines)


# For direct testing
if __name__ == "__main__":
    from context_gatherer import GatheredContext
    from triviality_assessor import TrivialityAssessment, Classification

    generator = PlanGenerator()

    # Mock ticket
    ticket = {
        "key": "INFRA-5678",
        "title": "Add rate limiting to Slack receiver",
        "description": "We're getting hammered by Slack retries. Need rate limiting to prevent overload. Not sure if we should use Redis or in-memory.",
        "labels": ["jib", "enhancement"],
    }

    # Mock context
    context = GatheredContext(
        ticket_key="INFRA-5678",
        ticket_title="Add rate limiting to Slack receiver",
        ticket_description=ticket["description"],
        related_files=[{"path": "slack-receiver.py", "relevance": "main file"}],
    )

    # Mock assessment
    assessment = TrivialityAssessment(
        classification=Classification.NON_TRIVIAL,
        score=30,
        threshold=50,
        score_details={"change_type": -10, "ambiguity": -20},
    )

    plan = generator.generate(ticket, context, assessment)
    print(f"File: {plan.file_path}")
    print(f"PR Title: {plan.pr_title}")
    print("\n--- Document ---\n")
    print(plan.content)
