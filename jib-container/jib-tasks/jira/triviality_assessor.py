#!/usr/bin/env python3
"""
Triviality Assessor - Determines if a JIRA ticket fix is trivial or non-trivial.

Uses a scoring system to assess triviality based on:
- File scope (how many files affected)
- Change type (bug fix, config change, feature, etc.)
- Test coverage (existing tests vs new tests needed)
- Requirements clarity (ambiguity)
- Dependencies (new packages/services needed)
- Risk assessment (security, data, performance implications)

Auto-disqualifiers bypass scoring and force non-trivial classification:
- Security implications
- Data migration/schema changes
- Multi-service changes
- Public API changes
- Infrastructure changes

Part of the JIRA Ticket Triage Workflow (ADR).
"""

import os
import re
from dataclasses import dataclass, field
from enum import Enum


class Classification(Enum):
    """Triviality classification result."""

    TRIVIAL = "trivial"
    NON_TRIVIAL = "non_trivial"
    FORCED_TRIVIAL = "forced_trivial"  # Via jib-trivial label
    FORCED_NON_TRIVIAL = "forced_non_trivial"  # Via jib-plan label


@dataclass
class TrivialityAssessment:
    """Result of triviality assessment."""

    classification: Classification
    score: int  # 0-100, higher = more trivial
    threshold: int  # Score threshold for trivial (default: 50)

    # Score breakdown
    score_details: dict = field(default_factory=dict)  # {factor: points}

    # Auto-disqualifiers triggered
    disqualifiers: list[str] = field(default_factory=list)

    # Human override applied
    override_label: str | None = None

    # Reasoning
    reasoning: str = ""

    @property
    def is_trivial(self) -> bool:
        """Check if the assessment indicates a trivial fix."""
        return self.classification in (Classification.TRIVIAL, Classification.FORCED_TRIVIAL)

    def to_summary(self) -> str:
        """Generate human-readable summary."""
        lines = []
        lines.append(f"**Classification:** {self.classification.value.replace('_', ' ').title()}")
        lines.append(f"**Score:** {self.score}/{100} (threshold: {self.threshold})")

        if self.override_label:
            lines.append(f"**Override:** {self.override_label}")

        if self.disqualifiers:
            lines.append(f"**Disqualifiers:** {', '.join(self.disqualifiers)}")

        lines.append("")
        lines.append("**Score Breakdown:**")
        for factor, points in sorted(self.score_details.items(), key=lambda x: -abs(x[1])):
            sign = "+" if points >= 0 else ""
            lines.append(f"- {factor}: {sign}{points}")

        if self.reasoning:
            lines.append("")
            lines.append(f"**Reasoning:** {self.reasoning}")

        return "\n".join(lines)


class TrivialityAssessor:
    """Assesses whether a JIRA ticket fix is trivial or non-trivial."""

    # Auto-disqualifiers (bypass scoring, always non-trivial)
    AUTO_DISQUALIFIERS = {
        "security_implications": [
            "security",
            "authentication",
            "authorization",
            "auth",
            "oauth",
            "jwt",
            "token",
            "password",
            "credential",
            "permission",
            "access control",
            "encryption",
            "decrypt",
            "vulnerability",
            "cve",
            "xss",
            "csrf",
            "injection",
            "sql injection",
        ],
        "data_migration": [
            "migration",
            "migrate",
            "schema",
            "database schema",
            "alter table",
            "drop table",
            "create table",
            "data migration",
            "db migration",
        ],
        "multi_service": [
            "microservice",
            "multiple services",
            "cross-service",
            "service boundary",
            "api gateway",
            "inter-service",
        ],
        "public_api_change": [
            "breaking change",
            "api change",
            "public api",
            "external api",
            "backwards compatible",
            "deprecate",
            "remove api",
        ],
        "infrastructure_change": [
            "terraform",
            "cloudformation",
            "kubernetes",
            "k8s",
            "docker compose",
            "deployment",
            "infrastructure",
            "ci/cd",
            "pipeline",
        ],
    }

    # Change type keywords
    CHANGE_TYPES = {
        "bug_fix": ["bug", "fix", "fixes", "fixed", "typo", "error", "incorrect", "wrong", "broken"],
        "config_change": ["config", "configuration", "setting", "env", "environment", "variable"],
        "new_feature": ["feature", "new", "add", "implement", "create", "build"],
        "enhancement": ["enhance", "improve", "improvement", "update", "upgrade", "optimize"],
        "refactor": ["refactor", "cleanup", "clean up", "reorganize", "restructure"],
        "documentation": ["doc", "docs", "documentation", "readme", "comment", "comments"],
    }

    def __init__(self, threshold: int | None = None):
        """Initialize the assessor.

        Args:
            threshold: Score threshold for trivial classification (default from env or 50)
        """
        self.threshold = threshold or int(os.environ.get("JIB_TRIVIALITY_THRESHOLD", "50"))

    def assess(
        self,
        ticket: dict,
        context: "GatheredContext | None" = None,  # noqa: F821
    ) -> TrivialityAssessment:
        """Assess triviality of a ticket.

        Args:
            ticket: Ticket data with keys: key, title, description, labels
            context: Optional gathered context for more accurate assessment

        Returns:
            TrivialityAssessment with classification and details
        """
        labels = [l.lower() for l in ticket.get("labels", [])]
        title = ticket.get("title", "").lower()
        description = ticket.get("description", "").lower()
        full_text = f"{title} {description}"

        # Check for human override labels
        override_label = None
        if "jib-trivial" in labels:
            override_label = "jib-trivial"
            return TrivialityAssessment(
                classification=Classification.FORCED_TRIVIAL,
                score=100,
                threshold=self.threshold,
                override_label=override_label,
                reasoning="Human override via jib-trivial label",
            )
        elif "jib-plan" in labels:
            override_label = "jib-plan"
            return TrivialityAssessment(
                classification=Classification.FORCED_NON_TRIVIAL,
                score=0,
                threshold=self.threshold,
                override_label=override_label,
                reasoning="Human override via jib-plan label",
            )

        # Check auto-disqualifiers
        disqualifiers = []
        for disqualifier, keywords in self.AUTO_DISQUALIFIERS.items():
            for keyword in keywords:
                if keyword in full_text:
                    disqualifiers.append(disqualifier)
                    break

        if disqualifiers:
            return TrivialityAssessment(
                classification=Classification.NON_TRIVIAL,
                score=0,
                threshold=self.threshold,
                disqualifiers=disqualifiers,
                reasoning=f"Auto-disqualified due to: {', '.join(disqualifiers)}",
            )

        # Calculate score
        score = 50  # Start neutral
        score_details = {}

        # 1. File scope assessment
        file_scope_score = self._assess_file_scope(context)
        score += file_scope_score["points"]
        score_details["file_scope"] = file_scope_score["points"]

        # 2. Change type assessment
        change_type_score = self._assess_change_type(full_text, labels)
        score += change_type_score["points"]
        score_details["change_type"] = change_type_score["points"]

        # 3. Test coverage assessment
        test_score = self._assess_test_coverage(context, full_text)
        score += test_score["points"]
        score_details["test_coverage"] = test_score["points"]

        # 4. Requirements clarity assessment
        clarity_score = self._assess_requirements_clarity(title, description)
        score += clarity_score["points"]
        score_details["requirements_clarity"] = clarity_score["points"]

        # 5. Dependencies assessment
        deps_score = self._assess_dependencies(full_text)
        score += deps_score["points"]
        score_details["dependencies"] = deps_score["points"]

        # 6. Estimated scope assessment
        scope_score = self._assess_estimated_scope(context, full_text)
        score += scope_score["points"]
        score_details["estimated_scope"] = scope_score["points"]

        # Clamp score to 0-100
        score = max(0, min(100, score))

        # Determine classification
        if score >= self.threshold:
            classification = Classification.TRIVIAL
            reasoning = f"Score {score} >= threshold {self.threshold}, classified as trivial"
        else:
            classification = Classification.NON_TRIVIAL
            reasoning = f"Score {score} < threshold {self.threshold}, classified as non-trivial"

        return TrivialityAssessment(
            classification=classification,
            score=score,
            threshold=self.threshold,
            score_details=score_details,
            reasoning=reasoning,
        )

    def _assess_file_scope(self, context: "GatheredContext | None") -> dict:  # noqa: F821
        """Assess based on number of files likely affected.

        +30 if 1 file
        +15 if 2-3 files
        -20 if more files
        """
        if not context or not context.related_files:
            return {"points": 0, "reason": "unknown file scope"}

        num_files = len(context.related_files)

        if num_files == 1:
            return {"points": 30, "reason": "single file"}
        elif num_files <= 3:
            return {"points": 15, "reason": f"{num_files} files"}
        else:
            return {"points": -20, "reason": f"{num_files} files (complex)"}

    def _assess_change_type(self, full_text: str, labels: list[str]) -> dict:
        """Assess based on type of change.

        +20 for bug fix or config change
        +10 for documentation
        -10 for enhancement/refactor
        -30 for new feature
        """
        # Check labels first
        label_text = " ".join(labels)

        # Bug fix
        if any(kw in full_text or kw in label_text for kw in self.CHANGE_TYPES["bug_fix"]):
            return {"points": 20, "reason": "bug fix"}

        # Config change
        if any(kw in full_text or kw in label_text for kw in self.CHANGE_TYPES["config_change"]):
            return {"points": 20, "reason": "config change"}

        # Documentation
        if any(kw in full_text or kw in label_text for kw in self.CHANGE_TYPES["documentation"]):
            return {"points": 10, "reason": "documentation"}

        # Enhancement/refactor
        if any(kw in full_text or kw in label_text for kw in self.CHANGE_TYPES["enhancement"]):
            return {"points": -10, "reason": "enhancement"}
        if any(kw in full_text or kw in label_text for kw in self.CHANGE_TYPES["refactor"]):
            return {"points": -10, "reason": "refactor"}

        # New feature
        if any(kw in full_text or kw in label_text for kw in self.CHANGE_TYPES["new_feature"]):
            return {"points": -30, "reason": "new feature"}

        return {"points": 0, "reason": "unknown change type"}

    def _assess_test_coverage(self, context: "GatheredContext | None", full_text: str) -> dict:  # noqa: F821
        """Assess based on test coverage.

        +20 if existing tests likely cover the area
        -10 if new tests needed
        """
        # Check if tests are mentioned as needed
        needs_tests = any(phrase in full_text for phrase in ["add test", "need test", "write test", "test coverage"])

        if needs_tests:
            return {"points": -10, "reason": "new tests needed"}

        # Check if context includes test files
        if context and context.related_files:
            test_files = [f for f in context.related_files if "test" in f["path"].lower()]
            if test_files:
                return {"points": 20, "reason": "existing tests found"}

        return {"points": 0, "reason": "test coverage unknown"}

    def _assess_requirements_clarity(self, title: str, description: str) -> dict:
        """Assess based on how clear the requirements are.

        +20 if requirements are clear
        -10 per ambiguous question/uncertainty
        """
        # Check for indicators of ambiguity
        ambiguity_indicators = [
            "?",
            "unclear",
            "not sure",
            "maybe",
            "possibly",
            "might",
            "could be",
            "or maybe",
            "tbd",
            "to be determined",
            "needs discussion",
            "needs clarification",
        ]

        full_text = f"{title} {description}"
        ambiguity_count = sum(1 for indicator in ambiguity_indicators if indicator in full_text.lower())

        if ambiguity_count == 0:
            # Check if description is detailed enough
            if len(description) > 50:
                return {"points": 20, "reason": "clear requirements"}
            else:
                return {"points": 10, "reason": "brief but seems clear"}
        elif ambiguity_count <= 2:
            return {"points": -10, "reason": "some ambiguity"}
        else:
            return {"points": -20, "reason": "significant ambiguity"}

    def _assess_dependencies(self, full_text: str) -> dict:
        """Assess based on new dependencies needed.

        -30 if new dependencies mentioned
        0 otherwise
        """
        dependency_indicators = [
            "new dependency",
            "new package",
            "npm install",
            "pip install",
            "add dependency",
            "requires",
            "need to install",
        ]

        if any(indicator in full_text for indicator in dependency_indicators):
            return {"points": -30, "reason": "new dependencies needed"}

        return {"points": 0, "reason": "no new dependencies"}

    def _assess_estimated_scope(self, context: "GatheredContext | None", full_text: str) -> dict:  # noqa: F821
        """Assess based on estimated lines of code.

        Based on heuristics from description and context.
        """
        # Check for explicit size mentions
        if any(phrase in full_text for phrase in ["one line", "single line", "small change", "simple fix", "typo"]):
            return {"points": 20, "reason": "small change indicated"}

        if any(
            phrase in full_text
            for phrase in ["large change", "major", "significant", "multiple", "several", "complex"]
        ):
            return {"points": -20, "reason": "large change indicated"}

        return {"points": 0, "reason": "scope not explicitly indicated"}


# For direct testing
if __name__ == "__main__":
    assessor = TrivialityAssessor()

    # Test trivial ticket
    trivial_ticket = {
        "key": "INFRA-1234",
        "title": "Fix typo in error message",
        "description": "The error message says 'recieved' instead of 'received'. Simple one line fix.",
        "labels": ["jib", "bug"],
    }

    print("=== Trivial Ticket ===")
    result = assessor.assess(trivial_ticket)
    print(result.to_summary())

    # Test non-trivial ticket
    print("\n=== Non-Trivial Ticket ===")
    nontrivial_ticket = {
        "key": "INFRA-5678",
        "title": "Add rate limiting to Slack receiver",
        "description": "We need to implement rate limiting. Not sure if we should use Redis or in-memory. Might require authentication changes.",
        "labels": ["jib", "enhancement"],
    }

    result = assessor.assess(nontrivial_ticket)
    print(result.to_summary())
