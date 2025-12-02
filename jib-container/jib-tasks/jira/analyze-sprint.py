#!/usr/bin/env python3
"""
Sprint Ticket Analyzer

Analyzes tickets in the active sprint and suggests:
- Next steps for currently assigned tickets
- Which tickets to pull in from backlog

Uses Claude for intelligent analysis of:
- Ticket complexity and effort estimation
- Implicit blockers and dependencies
- Personalized, actionable recommendations
- Context-aware prioritization

Usage:
  # From host
  bin/jib --exec /home/jwies/khan/james-in-a-box/jib-container/jib-tasks/jira/analyze-sprint.py

  # From inside container
  ~/khan/james-in-a-box/jib-container/jib-tasks/jira/analyze-sprint.py

  # With options
  ~/khan/james-in-a-box/jib-container/jib-tasks/jira/analyze-sprint.py --no-claude  # Fallback mode
  ~/khan/james-in-a-box/jib-container/jib-tasks/jira/analyze-sprint.py --verbose     # Show Claude output
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Add shared modules to path
sys.path.insert(0, str(Path.home() / "khan" / "james-in-a-box" / "shared"))

try:
    from claude import run_claude, is_claude_available
except ImportError:
    # Fallback if shared module not available
    def is_claude_available() -> bool:
        return False

    def run_claude(*args, **kwargs):
        return None


@dataclass
class TicketAnalysis:
    """Structured analysis result for a ticket."""

    complexity: str  # "low", "medium", "high"
    effort_estimate: str  # e.g., "1-2 hours", "1 day", "2-3 days"
    blockers: list[str]  # List of identified blockers
    dependencies: list[str]  # List of dependencies
    next_steps: list[str]  # Ordered list of recommended actions
    suggestions: list[str]  # Additional suggestions
    risk_factors: list[str]  # Potential risks
    priority_score: int  # 1-10 priority score
    confidence: str  # "low", "medium", "high" - how confident is the analysis


class ClaudeAnalysisAgent:
    """Claude-based agent for intelligent ticket analysis."""

    ANALYSIS_PROMPT_TEMPLATE = '''You are a sprint planning assistant analyzing JIRA tickets.

Analyze the following ticket and provide a structured assessment.

## Ticket Information
- **Key**: {key}
- **Title**: {title}
- **Status**: {status}
- **Priority**: {priority}
- **Type**: {type}
- **Assignee**: {assignee}
- **Updated**: {updated}

## Description
{description}

## Comments ({comment_count} total)
{comments_preview}

## Analysis Request
Provide a JSON response with the following structure (respond ONLY with valid JSON, no markdown code blocks):

{{
    "complexity": "low|medium|high",
    "effort_estimate": "estimated time (e.g., '2-4 hours', '1 day', '3-5 days')",
    "blockers": ["list of identified or implicit blockers"],
    "dependencies": ["list of dependencies on other tickets, teams, or external factors"],
    "next_steps": ["ordered list of specific, actionable next steps"],
    "suggestions": ["additional suggestions for successful completion"],
    "risk_factors": ["potential risks or things that could go wrong"],
    "priority_score": 1-10,
    "confidence": "low|medium|high"
}}

Consider:
1. **Complexity**: Based on technical scope, unknowns, and coordination needed
2. **Blockers**: Both explicit (mentioned in description) and implicit (inferred from context)
3. **Dependencies**: Technical dependencies, team dependencies, external dependencies
4. **Next Steps**: Specific actions the assignee should take, in priority order
5. **Risk Factors**: What could delay or complicate this work
6. **Priority Score**: 1-10 considering business impact, urgency, and blocking other work

Be specific and actionable. Avoid generic advice like "continue working on this".
'''

    BATCH_PRIORITIZATION_PROMPT = '''You are a sprint planning assistant helping prioritize a backlog of tickets.

## Context
The developer has the following tickets assigned and needs help deciding which to work on next.

## Current Work in Progress
{in_progress_summary}

## Tickets to Prioritize
{tickets_json}

## Task
Analyze these tickets and recommend which ones to pull into active work, considering:
1. Dependencies between tickets
2. Quick wins vs. larger efforts
3. Blocking vs. non-blocking work
4. Technical debt vs. new features
5. What's already in progress

Respond with JSON only (no markdown code blocks):

{{
    "recommendations": [
        {{
            "key": "TICKET-123",
            "action": "start_now|start_after_X|defer|needs_clarification",
            "reasoning": "Brief explanation",
            "priority_rank": 1
        }}
    ],
    "overall_strategy": "Brief summary of recommended sprint strategy",
    "warnings": ["Any concerns about the current workload or priorities"]
}}
'''

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._available = None

    def is_available(self) -> bool:
        """Check if Claude is available for analysis."""
        if self._available is None:
            self._available = is_claude_available()
        return self._available

    def analyze_ticket(self, ticket: dict) -> TicketAnalysis | None:
        """Analyze a single ticket using Claude."""
        if not self.is_available():
            return None

        # Build prompt
        prompt = self.ANALYSIS_PROMPT_TEMPLATE.format(
            key=ticket.get("key", "Unknown"),
            title=ticket.get("title", "Unknown"),
            status=ticket.get("status", "Unknown"),
            priority=ticket.get("priority", "Not Set"),
            type=ticket.get("type", "Unknown"),
            assignee=ticket.get("assignee", "Unassigned"),
            updated=ticket.get("updated", "Unknown"),
            description=ticket.get("description", "*No description*")[:2000],
            comment_count=ticket.get("comments_count", 0),
            comments_preview=ticket.get("comments_preview", "*No comments*")[:1000],
        )

        # Call Claude
        result = run_claude(
            prompt=prompt,
            timeout=60,  # 1 minute per ticket
            stream=self.verbose,
            cwd=Path.home() / "khan",
        )

        if not result or not result.success:
            if self.verbose:
                print(f"  Claude analysis failed for {ticket.get('key')}")
            return None

        # Parse JSON response
        try:
            analysis_data = self._extract_json(result.stdout)
            if analysis_data:
                return TicketAnalysis(
                    complexity=analysis_data.get("complexity", "medium"),
                    effort_estimate=analysis_data.get("effort_estimate", "unknown"),
                    blockers=analysis_data.get("blockers", []),
                    dependencies=analysis_data.get("dependencies", []),
                    next_steps=analysis_data.get("next_steps", []),
                    suggestions=analysis_data.get("suggestions", []),
                    risk_factors=analysis_data.get("risk_factors", []),
                    priority_score=analysis_data.get("priority_score", 5),
                    confidence=analysis_data.get("confidence", "medium"),
                )
        except Exception as e:
            if self.verbose:
                print(f"  Failed to parse Claude response: {e}")

        return None

    def prioritize_backlog(
        self, backlog_tickets: list[dict], in_progress: list[dict]
    ) -> dict | None:
        """Get Claude's recommendations for backlog prioritization."""
        if not self.is_available() or not backlog_tickets:
            return None

        # Build summaries
        in_progress_summary = "\n".join(
            f"- {t.get('key')}: {t.get('title')} ({t.get('status')})"
            for t in in_progress[:5]
        ) or "No work currently in progress"

        tickets_json = json.dumps(
            [
                {
                    "key": t.get("key"),
                    "title": t.get("title"),
                    "priority": t.get("priority"),
                    "type": t.get("type"),
                    "description_preview": t.get("description", "")[:500],
                    "has_acceptance_criteria": t.get("has_acceptance_criteria", False),
                    "comments_count": t.get("comments_count", 0),
                }
                for t in backlog_tickets[:10]  # Limit to 10 tickets
            ],
            indent=2,
        )

        prompt = self.BATCH_PRIORITIZATION_PROMPT.format(
            in_progress_summary=in_progress_summary,
            tickets_json=tickets_json,
        )

        result = run_claude(
            prompt=prompt,
            timeout=90,  # 1.5 minutes for batch analysis
            stream=self.verbose,
            cwd=Path.home() / "khan",
        )

        if not result or not result.success:
            return None

        try:
            return self._extract_json(result.stdout)
        except Exception:
            return None

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from Claude's response."""
        # Try to find JSON in the response
        text = text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            text = "\n".join(json_lines)

        # Try to parse as JSON directly
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return None


class SprintAnalyzer:
    """Analyzes sprint tickets and provides recommendations."""

    def __init__(self, use_claude: bool = True, verbose: bool = False):
        self.jira_dir = Path.home() / "context-sync" / "jira"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)
        self.use_claude = use_claude
        self.verbose = verbose
        self.claude_agent = ClaudeAnalysisAgent(verbose=verbose) if use_claude else None

    def parse_ticket_file(self, ticket_file: Path) -> dict | None:
        """Parse a JIRA ticket markdown file."""
        try:
            content = ticket_file.read_text()

            ticket = {
                "file": ticket_file,
                "key": "",
                "title": "",
                "status": "",
                "assignee": "",
                "priority": "",
                "type": "",
                "labels": [],
                "description": "",
                "has_acceptance_criteria": False,
                "comments_count": 0,
                "updated": "",
            }

            lines = content.split("\n")

            # Extract key and title from first line (# INFRA-1234: Title)
            first_line = lines[0] if lines else ""
            title_match = re.match(r"^#\s+([A-Z]+-\d+):\s+(.+)$", first_line)
            if title_match:
                ticket["key"] = title_match.group(1)
                ticket["title"] = title_match.group(2)

            # Extract metadata
            for line in lines:
                if line.startswith("**Status:**"):
                    ticket["status"] = line.replace("**Status:**", "").strip()
                elif line.startswith("**Assignee:**"):
                    ticket["assignee"] = line.replace("**Assignee:**", "").strip()
                elif line.startswith("**Priority:**"):
                    ticket["priority"] = line.replace("**Priority:**", "").strip()
                elif line.startswith("**Type:**"):
                    ticket["type"] = line.replace("**Type:**", "").strip()
                elif line.startswith("**Labels:**"):
                    labels_str = line.replace("**Labels:**", "").strip()
                    ticket["labels"] = [l.strip() for l in labels_str.split(",") if l.strip()]
                elif line.startswith("**Updated:**"):
                    ticket["updated"] = line.replace("**Updated:**", "").strip()

            # Check for acceptance criteria
            if "acceptance criteria" in content.lower() or "- [ ]" in content:
                ticket["has_acceptance_criteria"] = True

            # Count comments and extract preview
            ticket["comments_count"] = content.count("### Comment ")

            # Extract comments section for Claude analysis
            comments_start = content.find("## Comments")
            if comments_start != -1:
                comments_section = content[comments_start:]
                # Get first 1000 chars of comments for preview
                ticket["comments_preview"] = comments_section[:1000]
            else:
                ticket["comments_preview"] = ""

            # Extract description section
            desc_start = content.find("## Description")
            if desc_start != -1:
                desc_end = content.find("\n## ", desc_start + 1)
                if desc_end == -1:
                    desc_end = len(content)
                ticket["description"] = content[desc_start:desc_end].strip()

            # Store full content for Claude analysis
            ticket["full_content"] = content

            return ticket

        except Exception as e:
            print(f"Error parsing {ticket_file}: {e}")
            return None

    def is_assigned_to_me(self, ticket: dict) -> bool:
        """Check if ticket is assigned to current user.

        Checks multiple sources:
        1. JIRA_USER environment variable
        2. USER/USERNAME environment variable
        3. Git user.name config
        4. Git user.email config
        5. Default "james wiesebron" for jib container
        """
        assignee = ticket.get("assignee", "").lower()

        if not assignee or assignee == "unassigned":
            return False

        # Check environment variables first
        import os
        jira_user = os.environ.get("JIRA_USER", "").lower()
        if jira_user and jira_user in assignee:
            return True

        # Check system user
        sys_user = os.environ.get("USER", os.environ.get("USERNAME", "")).lower()
        if sys_user and sys_user in assignee:
            return True

        # Get user info from git config
        try:
            result = subprocess.run(
                ["git", "config", "user.name"], check=False, capture_output=True, text=True
            )
            if result.returncode == 0:
                git_name = result.stdout.strip().lower()
                if git_name and git_name in assignee:
                    return True

            result = subprocess.run(
                ["git", "config", "user.email"], check=False, capture_output=True, text=True
            )
            if result.returncode == 0:
                git_email = result.stdout.strip().lower()
                # Extract name from email
                email_name = git_email.split("@")[0].replace(".", " ")
                if email_name and email_name in assignee:
                    return True
        except (OSError, subprocess.SubprocessError):
            pass

        # Default for jib container: assume the host user is James Wiesebron
        # This handles the case where git config shows "jib" but tickets are
        # assigned to the actual developer
        if "james" in assignee and "wiesebron" in assignee:
            return True

        return False

    def is_in_active_sprint(self, ticket: dict) -> bool:
        """Check if ticket is in active sprint (heuristic based on labels/status)."""
        # Check labels for sprint indicators
        labels = [l.lower() for l in ticket.get("labels", [])]
        if any("sprint" in label for label in labels):
            return True

        # Active statuses typically indicate sprint work
        status = ticket.get("status", "").lower()
        active_statuses = ["in progress", "in review", "ready for review", "testing"]
        return bool(any(s in status for s in active_statuses))

    def analyze_ticket(self, ticket: dict) -> dict:
        """Analyze a ticket and suggest next steps.

        Uses Claude for intelligent analysis when available, with fallback
        to heuristic-based analysis.
        """
        # Try Claude analysis first if enabled
        if self.claude_agent and self.claude_agent.is_available():
            if self.verbose:
                print(f"  Analyzing {ticket.get('key')} with Claude...")

            claude_analysis = self.claude_agent.analyze_ticket(ticket)
            if claude_analysis:
                return {
                    "priority_score": claude_analysis.priority_score,
                    "next_steps": claude_analysis.next_steps,
                    "blockers": claude_analysis.blockers,
                    "suggestions": claude_analysis.suggestions,
                    "complexity": claude_analysis.complexity,
                    "effort_estimate": claude_analysis.effort_estimate,
                    "dependencies": claude_analysis.dependencies,
                    "risk_factors": claude_analysis.risk_factors,
                    "confidence": claude_analysis.confidence,
                    "analysis_source": "claude",
                }

        # Fallback to heuristic analysis
        return self._analyze_ticket_heuristic(ticket)

    def _analyze_ticket_heuristic(self, ticket: dict) -> dict:
        """Fallback heuristic-based ticket analysis."""
        analysis = {
            "priority_score": 0,
            "next_steps": [],
            "blockers": [],
            "suggestions": [],
            "complexity": "unknown",
            "effort_estimate": "unknown",
            "dependencies": [],
            "risk_factors": [],
            "confidence": "low",
            "analysis_source": "heuristic",
        }

        status = ticket.get("status", "").lower()
        priority = ticket.get("priority", "").lower()

        # Priority scoring (scaled to 1-10 for consistency with Claude)
        if "critical" in priority or "highest" in priority:
            analysis["priority_score"] = 10
        elif "high" in priority:
            analysis["priority_score"] = 8
        elif "medium" in priority or "p3" in priority:
            analysis["priority_score"] = 6
        elif "low" in priority:
            analysis["priority_score"] = 4
        else:
            analysis["priority_score"] = 5  # Default to medium

        # Status-based next steps
        if "to do" in status or "open" in status or "backlog" in status:
            analysis["next_steps"].append("Start work on this ticket")
            if not ticket.get("has_acceptance_criteria"):
                analysis["suggestions"].append("Add acceptance criteria before starting")

        elif "in progress" in status or "construction" in status:
            if ticket.get("comments_count", 0) == 0:
                analysis["suggestions"].append("Add progress update in comments")
            analysis["next_steps"].append("Continue implementation")
            analysis["next_steps"].append("Add tests for new functionality")

        elif "review" in status:
            analysis["next_steps"].append("Address review comments")
            analysis["next_steps"].append("Request re-review when ready")

        elif "testing" in status:
            analysis["next_steps"].append("Verify tests pass")
            analysis["next_steps"].append("Test in staging environment")

        # Type-based suggestions
        ticket_type = ticket.get("type", "").lower()
        if "epic" in ticket_type:
            analysis["suggestions"].append("Break down into smaller sub-tasks")
            analysis["complexity"] = "high"

        # Check for potential blockers (basic keyword matching)
        description = ticket.get("description", "").lower()
        blocker_keywords = ["blocked", "waiting", "depends on", "requires", "need"]
        for keyword in blocker_keywords:
            if keyword in description:
                analysis["blockers"].append(
                    f"Potential blocker: '{keyword}' mentioned in description"
                )

        return analysis

    def get_backlog_suggestions(
        self, all_tickets: list[dict], in_progress_tickets: list[dict] | None = None
    ) -> list[dict]:
        """Suggest which backlog tickets to pull into sprint.

        Uses Claude for intelligent prioritization when available, with
        fallback to score-based ranking.
        """
        # Get backlog candidates
        backlog_candidates = []

        for ticket in all_tickets:
            status = ticket.get("status", "").lower()

            # Skip tickets already in progress
            if any(
                s in status
                for s in ["in progress", "in review", "testing", "done", "construction"]
            ):
                continue

            # Skip unassigned tickets (not ready for current user)
            if not self.is_assigned_to_me(ticket):
                continue

            backlog_candidates.append(ticket)

        if not backlog_candidates:
            return []

        # Try Claude-based prioritization
        if self.claude_agent and self.claude_agent.is_available() and len(backlog_candidates) > 0:
            if self.verbose:
                print("  Using Claude for backlog prioritization...")

            in_progress = in_progress_tickets or []
            claude_result = self.claude_agent.prioritize_backlog(
                backlog_candidates, in_progress
            )

            if claude_result and "recommendations" in claude_result:
                # Build results from Claude's recommendations
                results = []
                recommendations = claude_result.get("recommendations", [])

                for rec in recommendations[:5]:
                    key = rec.get("key")
                    # Find matching ticket
                    matching_ticket = next(
                        (t for t in backlog_candidates if t.get("key") == key), None
                    )
                    if matching_ticket:
                        results.append({
                            "ticket": matching_ticket,
                            "score": 10 - rec.get("priority_rank", 5),  # Convert rank to score
                            "action": rec.get("action", "unknown"),
                            "reasoning": rec.get("reasoning", ""),
                            "analysis_source": "claude",
                        })

                # Add overall strategy to results metadata
                if results:
                    results[0]["overall_strategy"] = claude_result.get(
                        "overall_strategy", ""
                    )
                    results[0]["warnings"] = claude_result.get("warnings", [])

                if results:
                    return results

        # Fallback to heuristic scoring
        return self._get_backlog_suggestions_heuristic(backlog_candidates)

    def _get_backlog_suggestions_heuristic(self, backlog_candidates: list[dict]) -> list[dict]:
        """Fallback heuristic-based backlog prioritization."""
        backlog = []

        for ticket in backlog_candidates:
            # Score the ticket
            score = 0

            # Priority weight
            priority = ticket.get("priority", "").lower()
            if "critical" in priority or "highest" in priority:
                score += 10
            elif "high" in priority:
                score += 7
            elif "medium" in priority or "p3" in priority:
                score += 4

            # Completeness weight (tickets with acceptance criteria are better defined)
            if ticket.get("has_acceptance_criteria"):
                score += 3

            # Recent activity weight
            if ticket.get("comments_count", 0) > 0:
                score += 2

            # Type weight (prefer tasks over epics)
            ticket_type = ticket.get("type", "").lower()
            if "story" in ticket_type or "task" in ticket_type:
                score += 3
            elif "bug" in ticket_type:
                score += 5  # Bugs often need quick attention

            backlog.append({
                "ticket": ticket,
                "score": score,
                "analysis_source": "heuristic",
            })

        # Sort by score descending
        backlog.sort(key=lambda x: -x["score"])

        return backlog[:5]  # Top 5 suggestions

    def generate_notification(
        self,
        assigned_tickets: list[dict],
        backlog_suggestions: list[dict],
        analyses: dict[str, dict] | None = None,
    ):
        """Generate Slack notification with sprint analysis."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_id = f"{timestamp}-sprint-analysis"

        # Determine analysis source
        has_claude = analyses and any(
            a.get("analysis_source") == "claude" for a in analyses.values()
        )
        analysis_source = "Claude AI" if has_claude else "heuristic rules"

        # Create summary notification
        summary_file = self.notifications_dir / f"{task_id}.md"
        active_count = len([t for t in assigned_tickets if self.is_in_active_sprint(t)])

        summary = f"""# Sprint Ticket Analysis

**Assigned Tickets**: {len(assigned_tickets)} total, {active_count} in active work
**Backlog Suggestions**: {len(backlog_suggestions)} tickets ready to pull in
**Analysis**: Powered by {analysis_source}

Full analysis in thread below
"""

        summary_file.write_text(summary)

        # Create detailed analysis
        detail_file = self.notifications_dir / f"RESPONSE-{task_id}.md"
        detail_content = f"""# Sprint Ticket Analysis

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Source**: ~/context-sync/jira/
**Analysis Engine**: {analysis_source}

---

## Currently Assigned Tickets

"""

        # Group tickets by status
        in_progress = []
        in_review = []
        blocked = []
        todo = []

        for ticket in assigned_tickets:
            key = ticket.get("key", "")
            analysis = analyses.get(key, {}) if analyses else self.analyze_ticket(ticket)

            ticket_data = {"ticket": ticket, "analysis": analysis}

            status = ticket.get("status", "").lower()
            if "progress" in status or "construction" in status:
                in_progress.append(ticket_data)
            elif "review" in status:
                in_review.append(ticket_data)
            elif "blocked" in status or analysis.get("blockers"):
                blocked.append(ticket_data)
            else:
                todo.append(ticket_data)

        # In Progress section
        if in_progress:
            detail_content += "### In Progress\n\n"
            for item in in_progress:
                ticket = item["ticket"]
                analysis = item["analysis"]

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"
                detail_content += f"- Status: {ticket.get('status', 'Unknown')}\n"

                # Include Claude-specific analysis fields
                if analysis.get("complexity"):
                    detail_content += f"- Complexity: {analysis['complexity']}\n"
                if analysis.get("effort_estimate") and analysis["effort_estimate"] != "unknown":
                    detail_content += f"- Effort: {analysis['effort_estimate']}\n"

                if analysis.get("next_steps"):
                    detail_content += "- **Next Steps**:\n"
                    for step in analysis["next_steps"]:
                        detail_content += f"  - {step}\n"

                if analysis.get("blockers"):
                    detail_content += "- **Blockers**:\n"
                    for blocker in analysis["blockers"]:
                        detail_content += f"  - {blocker}\n"

                if analysis.get("dependencies"):
                    detail_content += "- **Dependencies**:\n"
                    for dep in analysis["dependencies"]:
                        detail_content += f"  - {dep}\n"

                if analysis.get("risk_factors"):
                    detail_content += "- **Risks**:\n"
                    for risk in analysis["risk_factors"]:
                        detail_content += f"  - {risk}\n"

                if analysis.get("suggestions"):
                    detail_content += "- **Suggestions**:\n"
                    for suggestion in analysis["suggestions"]:
                        detail_content += f"  - {suggestion}\n"

                detail_content += "\n"

        # In Review section
        if in_review:
            detail_content += "### In Review\n\n"
            for item in in_review:
                ticket = item["ticket"]
                analysis = item["analysis"]

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"

                if analysis.get("next_steps"):
                    for step in analysis["next_steps"]:
                        detail_content += f"- {step}\n"

                detail_content += "\n"

        # Blocked section
        if blocked:
            detail_content += "### Blocked or Needs Attention\n\n"
            for item in blocked:
                ticket = item["ticket"]
                analysis = item["analysis"]

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"
                detail_content += f"- Status: {ticket.get('status', 'Unknown')}\n"

                if analysis.get("blockers"):
                    detail_content += "- **Blockers**:\n"
                    for blocker in analysis["blockers"]:
                        detail_content += f"  - {blocker}\n"

                if analysis.get("dependencies"):
                    detail_content += "- **Dependencies**:\n"
                    for dep in analysis["dependencies"]:
                        detail_content += f"  - {dep}\n"

                detail_content += "\n"

        # To Do section
        if todo:
            detail_content += "### To Do\n\n"
            for item in todo:
                ticket = item["ticket"]
                analysis = item["analysis"]

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"

                if analysis.get("complexity"):
                    detail_content += f"- Complexity: {analysis['complexity']}\n"
                if analysis.get("effort_estimate") and analysis["effort_estimate"] != "unknown":
                    detail_content += f"- Effort: {analysis['effort_estimate']}\n"

                if analysis.get("next_steps"):
                    detail_content += "- **Next Steps**:\n"
                    for step in analysis["next_steps"]:
                        detail_content += f"  - {step}\n"

                if analysis.get("suggestions"):
                    for suggestion in analysis["suggestions"]:
                        detail_content += f"- {suggestion}\n"

                detail_content += "\n"

        # Backlog suggestions section
        if backlog_suggestions:
            detail_content += "\n## Suggested Tickets to Pull In\n\n"

            # Check if we have Claude-based recommendations
            first_item = backlog_suggestions[0] if backlog_suggestions else {}
            if first_item.get("overall_strategy"):
                detail_content += f"**Strategy**: {first_item['overall_strategy']}\n\n"

            if first_item.get("warnings"):
                detail_content += "**Warnings**:\n"
                for warning in first_item["warnings"]:
                    detail_content += f"- {warning}\n"
                detail_content += "\n"

            for item in backlog_suggestions:
                ticket = item["ticket"]
                score = item.get("score", 0)

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"
                detail_content += f"- Type: {ticket.get('type', 'Unknown')}\n"
                detail_content += f"- Status: {ticket.get('status', 'Unknown')}\n"

                if item.get("action"):
                    detail_content += f"- Action: {item['action']}\n"

                if item.get("reasoning"):
                    detail_content += f"- Reasoning: {item['reasoning']}\n"

                if ticket.get("has_acceptance_criteria"):
                    detail_content += "- Has acceptance criteria\n"

                if ticket.get("comments_count", 0) > 0:
                    detail_content += f"- {ticket['comments_count']} comment(s) - recent activity\n"

                detail_content += "\n"

        # Add recommendations
        detail_content += """
---

## Recommendations

1. **Focus on In Progress**: Complete current work before starting new tickets
2. **Unblock**: Address blocked tickets to maintain velocity
3. **Review Ready**: Prioritize tickets in review to unblock teammates
4. **Pull Strategically**: Use suggested tickets based on priority and clarity

---

{date}
Run again with: `bin/jib --exec ~/khan/james-in-a-box/jib-container/jib-tasks/jira/analyze-sprint.py`
""".format(date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        detail_file.write_text(detail_content)

        print("Sprint analysis complete!")
        print(f"  Summary: {summary_file}")
        print(f"  Detail: {detail_file}")

    def run(self):
        """Main analysis workflow."""
        print("Analyzing sprint tickets...")

        # Check Claude availability
        if self.use_claude:
            if self.claude_agent and self.claude_agent.is_available():
                print("  Claude analysis: enabled")
            else:
                print("  Claude analysis: unavailable (using heuristics)")
        else:
            print("  Claude analysis: disabled (using heuristics)")

        if not self.jira_dir.exists():
            print(f"Error: JIRA directory not found: {self.jira_dir}")
            print("Run context-sync first to fetch JIRA tickets")
            return 1

        # Get all ticket files (exclude hidden files like .sync_state)
        ticket_files = [f for f in self.jira_dir.glob("*.md") if not f.name.startswith(".")]

        if not ticket_files:
            print(f"No tickets found in {self.jira_dir}")
            return 1

        print(f"Found {len(ticket_files)} ticket files")

        # Parse all tickets
        all_tickets = []
        for ticket_file in ticket_files:
            ticket = self.parse_ticket_file(ticket_file)
            # Only include tickets with valid keys
            if ticket and ticket.get("key"):
                all_tickets.append(ticket)

        print(f"Parsed {len(all_tickets)} tickets")

        # Filter assigned tickets
        assigned_tickets = [t for t in all_tickets if self.is_assigned_to_me(t)]

        if not assigned_tickets:
            print("No tickets assigned to you found")
            print("Check ~/context-sync/jira/ for ticket files")
            return 1

        print(f"Found {len(assigned_tickets)} assigned tickets")

        # Analyze all assigned tickets
        print("Analyzing tickets...")
        analyses: dict[str, dict] = {}
        for ticket in assigned_tickets:
            key = ticket.get("key", "")
            if key:
                if self.verbose:
                    print(f"  Analyzing {key}...")
                analyses[key] = self.analyze_ticket(ticket)

        # Get in-progress tickets for backlog prioritization context
        in_progress_tickets = [
            t for t in assigned_tickets
            if any(
                s in t.get("status", "").lower()
                for s in ["progress", "construction", "review"]
            )
        ]

        # Get backlog suggestions
        print("Analyzing backlog...")
        backlog_suggestions = self.get_backlog_suggestions(all_tickets, in_progress_tickets)

        # Generate notification
        self.generate_notification(assigned_tickets, backlog_suggestions, analyses)

        return 0


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze sprint tickets and suggest next steps.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default: Use Claude for intelligent analysis
  %(prog)s

  # Use heuristic analysis only (faster, no Claude)
  %(prog)s --no-claude

  # Show verbose output including Claude responses
  %(prog)s --verbose

  # Combine options
  %(prog)s --verbose --no-claude
""",
    )

    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Disable Claude analysis, use heuristic rules only",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show verbose output including Claude analysis progress",
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    analyzer = SprintAnalyzer(
        use_claude=not args.no_claude,
        verbose=args.verbose,
    )
    return analyzer.run()


if __name__ == "__main__":
    sys.exit(main())
