#!/usr/bin/env python3
"""
Ticket Triager - Main orchestrator for JIB JIRA ticket triage workflow.

This module:
1. Detects JIB-tagged tickets (via labels jib, james-in-a-box, JIB)
2. Gathers relevant context
3. Assesses triviality
4. Routes to appropriate workflow:
   - TRIVIAL: Direct implementation via Claude agent
   - NON-TRIVIAL: Generates CPF planning document PR

Part of the JIRA Ticket Triage Workflow (ADR).
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING


# Add shared modules to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "llm"))

# Import from same directory (jira modules)
from .context_gatherer import ContextGatherer, GatheredContext
from .plan_generator import GeneratedPlan, PlanGenerator
from .triviality_assessor import Classification, TrivialityAssessment, TrivialityAssessor


if TYPE_CHECKING:
    from llm import AgentResult


# JIB tag labels - use config for single source of truth
# Fallback to james-in-a-box if config not available
try:
    from host_services.sync.context_sync.connectors.jira.config import JIRAConfig
    JIB_TAG_LABELS = JIRAConfig.get_jib_tag_labels()
except ImportError:
    JIB_TAG_LABELS = ["james-in-a-box"]


@dataclass
class TriageResult:
    """Result of ticket triage."""

    ticket_key: str
    ticket_title: str
    classification: Classification
    assessment: TrivialityAssessment
    context: GatheredContext

    # For trivial tickets
    implementation_result: "AgentResult | None" = None

    # For non-trivial tickets
    generated_plan: GeneratedPlan | None = None

    # PR information (if created)
    pr_url: str | None = None
    pr_number: int | None = None
    branch_name: str | None = None

    # Metadata
    triaged_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error: str | None = None


class TicketTriager:
    """Main ticket triage orchestrator."""

    def __init__(
        self,
        repos_dir: Path | str | None = None,
        jira_dir: Path | str | None = None,
        enabled: bool | None = None,
        enabled_repos: list[str] | None = None,
    ):
        """Initialize the triager.

        Args:
            repos_dir: Base directory containing repositories
            jira_dir: Directory containing synced JIRA tickets
            enabled: Whether triage is enabled (default from env)
            enabled_repos: List of enabled repositories (default from env)
        """
        self.repos_dir = Path(repos_dir or os.path.expanduser("~/khan"))
        self.jira_dir = Path(jira_dir or os.path.expanduser("~/context-sync/jira"))

        # Configuration from environment
        self.enabled = enabled if enabled is not None else os.environ.get("JIB_TRIAGE_ENABLED", "true").lower() == "true"

        if enabled_repos:
            self.enabled_repos = enabled_repos
        else:
            repos_env = os.environ.get("JIB_TRIAGE_ENABLED_REPOS", "jwbron/james-in-a-box")
            self.enabled_repos = [r.strip() for r in repos_env.split(",")]

        # State tracking
        self.state_file = Path.home() / "sharing" / "tracking" / "jib-triage-state.json"

        # Initialize components
        self.context_gatherer = ContextGatherer(repos_dir=self.repos_dir, jira_dir=self.jira_dir)
        self.assessor = TrivialityAssessor()
        self.plan_generator = PlanGenerator()

    def is_jib_tagged(self, ticket: dict) -> bool:
        """Check if a ticket has a JIB tag label.

        Args:
            ticket: Ticket data with 'labels' key

        Returns:
            True if ticket has jib, james-in-a-box, or JIB label
        """
        labels = [l.lower() for l in ticket.get("labels", [])]
        return any(tag in labels for tag in JIB_TAG_LABELS)

    def parse_ticket_file(self, ticket_path: Path) -> dict | None:
        """Parse a JIRA ticket markdown file.

        Args:
            ticket_path: Path to the ticket markdown file

        Returns:
            Parsed ticket data or None if parsing fails
        """
        try:
            content = ticket_path.read_text()

            # Extract ticket key from filename
            ticket_key = ticket_path.stem.split("_")[0]

            # Parse title from first heading
            title_match = re.search(r"^#\s*(?:\w+-\d+:\s*)?(.+)$", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else ticket_path.stem

            # Parse labels
            labels_match = re.search(r"\*\*Labels:\*\*\s*(.+)", content)
            labels = []
            if labels_match:
                labels = [l.strip() for l in labels_match.group(1).split(",")]

            # Parse description
            desc_match = re.search(r"## Description\s*\n+(.*?)(?=\n##|\Z)", content, re.DOTALL)
            description = desc_match.group(1).strip() if desc_match else ""

            # Parse comments
            comments = []
            comment_matches = re.findall(r"### Comment \d+.*?\n+(.*?)(?=\n###|\n## |\Z)", content, re.DOTALL)
            comments = [c.strip() for c in comment_matches]

            return {
                "key": ticket_key,
                "title": title,
                "description": description,
                "labels": labels,
                "comments": comments,
                "file_path": str(ticket_path),
                "raw_content": content,
            }

        except Exception as e:
            print(f"Error parsing ticket {ticket_path}: {e}")
            return None

    def find_jib_tagged_tickets(self) -> list[dict]:
        """Find all JIB-tagged tickets in the JIRA directory.

        Returns:
            List of parsed ticket data for JIB-tagged tickets
        """
        jib_tickets = []

        if not self.jira_dir.exists():
            print(f"JIRA directory not found: {self.jira_dir}")
            return jib_tickets

        for ticket_file in self.jira_dir.glob("*.md"):
            ticket = self.parse_ticket_file(ticket_file)
            if ticket and self.is_jib_tagged(ticket):
                jib_tickets.append(ticket)

        return jib_tickets

    def triage_ticket(self, ticket: dict) -> TriageResult:
        """Triage a single ticket.

        Args:
            ticket: Parsed ticket data

        Returns:
            TriageResult with classification and results
        """
        ticket_key = ticket.get("key", "UNKNOWN")
        ticket_title = ticket.get("title", "Untitled")

        print(f"🔍 Triaging ticket: {ticket_key} - {ticket_title}")

        # 1. Gather context
        print("  📚 Gathering context...")
        context = self.context_gatherer.gather_context(ticket)
        print(f"     Found {len(context.related_files)} related files, {len(context.similar_tickets)} similar tickets")

        # 2. Assess triviality
        print("  🧪 Assessing triviality...")
        assessment = self.assessor.assess(ticket, context)
        print(f"     Score: {assessment.score}/100, Classification: {assessment.classification.value}")

        # 3. Create result
        result = TriageResult(
            ticket_key=ticket_key,
            ticket_title=ticket_title,
            classification=assessment.classification,
            assessment=assessment,
            context=context,
        )

        # 4. Route to appropriate workflow
        if assessment.is_trivial:
            print("  🚀 Routing to TRIVIAL workflow...")
            self._handle_trivial(ticket, result)
        else:
            print("  📋 Routing to NON-TRIVIAL workflow (planning)...")
            self._handle_nontrivial(ticket, result)

        return result

    def _handle_trivial(self, ticket: dict, result: TriageResult) -> None:
        """Handle trivial ticket - implement directly via Claude agent.

        Args:
            ticket: Parsed ticket data
            result: TriageResult to update
        """
        from llm import run_agent

        ticket_key = ticket.get("key", "UNKNOWN")
        ticket_title = ticket.get("title", "Untitled")
        description = ticket.get("description", "")

        # Build prompt for Claude agent
        prompt = f"""# JIB Trivial Fix: {ticket_key}

## Task

Implement a trivial fix for the following JIRA ticket:

**Ticket:** {ticket_key}
**Title:** {ticket_title}
**Description:**
{description}

## Context

{result.context.to_prompt_context()}

## Instructions

1. **Analyze the ticket** to understand what needs to be fixed
2. **Locate the relevant code** in the codebase
3. **Implement the fix**:
   - Create a feature branch: `jib/{ticket_key.lower()}-fix`
   - Make the necessary code changes
   - Ensure changes follow existing code conventions
4. **Validate**:
   - Run any relevant tests
   - Ensure the fix is complete and correct
5. **Create a PR**:
   - Use the gh CLI to create a PR
   - Title: `[JIB] Fix: {ticket_key} {ticket_title}`
   - Include a clear description of the fix
   - Request review from @jwiesebron
6. **Output the PR URL** at the end

## Important

- This is a TRIVIAL fix - keep changes minimal and focused
- Do not introduce new patterns or dependencies
- Follow existing code style
- If you encounter unexpected complexity, note it but still attempt the fix

Proceed with the implementation now.
"""

        # Determine working directory (first enabled repo)
        cwd = None
        for repo in self.enabled_repos:
            repo_name = repo.split("/")[-1]
            repo_path = self.repos_dir / repo_name
            if repo_path.exists():
                cwd = repo_path
                break

        if not cwd:
            result.error = "No enabled repository found"
            return

        try:
            # Run Claude agent
            agent_result = run_agent(prompt, cwd=cwd, timeout=600)  # 10 minute timeout
            result.implementation_result = agent_result

            if agent_result.success:
                # Try to extract PR URL from output
                pr_match = re.search(r"https://github\.com/[^\s]+/pull/\d+", agent_result.stdout or "")
                if pr_match:
                    result.pr_url = pr_match.group(0)
                    pr_num_match = re.search(r"/pull/(\d+)", result.pr_url)
                    if pr_num_match:
                        result.pr_number = int(pr_num_match.group(1))
                print(f"  ✅ Implementation complete. PR: {result.pr_url or 'not found'}")
            else:
                result.error = agent_result.error or "Unknown error"
                print(f"  ❌ Implementation failed: {result.error}")

        except Exception as e:
            result.error = str(e)
            print(f"  ❌ Error during implementation: {e}")

    def _handle_nontrivial(self, ticket: dict, result: TriageResult) -> None:
        """Handle non-trivial ticket - generate planning document.

        Args:
            ticket: Parsed ticket data
            result: TriageResult to update
        """
        import subprocess

        ticket_key = ticket.get("key", "UNKNOWN")

        # Generate planning document
        plan = self.plan_generator.generate(ticket, result.context, result.assessment)
        result.generated_plan = plan

        # Determine repository path
        repo_path = None
        repo_name = None
        for repo in self.enabled_repos:
            repo_name = repo.split("/")[-1]
            path = self.repos_dir / repo_name
            if path.exists():
                repo_path = path
                break

        if not repo_path:
            result.error = "No enabled repository found"
            return

        try:
            # Create branch
            branch_name = f"jib/{ticket_key.lower()}-plan"
            result.branch_name = branch_name

            # Git operations
            subprocess.run(["git", "checkout", "main"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "pull"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "checkout", "-B", branch_name], cwd=repo_path, capture_output=True)

            # Write planning document
            doc_path = plan.to_file(repo_path)
            print(f"  📄 Created planning document: {doc_path}")

            # Git add and commit
            subprocess.run(["git", "add", str(doc_path)], cwd=repo_path, capture_output=True)
            commit_msg = f"""[JIB] Plan: {ticket_key} {ticket.get('title', 'Planning document')}

Planning document for non-trivial ticket.
Triviality Score: {result.assessment.score}/100

🤖 Generated with [Claude Code](https://claude.com/claude-code)
"""
            subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, capture_output=True)

            # Push branch
            push_result = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            if push_result.returncode != 0:
                # Try force-with-lease if branch exists (safer than -f)
                subprocess.run(
                    ["git", "push", "-u", "--force-with-lease", "origin", branch_name],
                    cwd=repo_path,
                    capture_output=True,
                )

            # Create PR using gh CLI
            pr_result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    plan.pr_title,
                    "--body",
                    plan.pr_body,
                    "--base",
                    "main",
                    "--reviewer",
                    "jwiesebron",
                ],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )

            if pr_result.returncode == 0:
                # Extract PR URL from output
                pr_url_match = re.search(r"https://github\.com/[^\s]+", pr_result.stdout)
                if pr_url_match:
                    result.pr_url = pr_url_match.group(0)
                    pr_num_match = re.search(r"/pull/(\d+)", result.pr_url)
                    if pr_num_match:
                        result.pr_number = int(pr_num_match.group(1))
                print(f"  ✅ Created planning PR: {result.pr_url}")
            else:
                # PR might already exist
                if "already exists" in pr_result.stderr:
                    print("  ℹ️ PR already exists for this branch")
                else:
                    result.error = f"Failed to create PR: {pr_result.stderr}"
                    print(f"  ⚠️ {result.error}")

        except Exception as e:
            result.error = str(e)
            print(f"  ❌ Error creating planning PR: {e}")

    def load_state(self) -> dict:
        """Load triage state from file."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {"processed_tickets": {}}

    def save_state(self, state: dict) -> None:
        """Save triage state to file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2))

    def triage_all(self, force: bool = False) -> list[TriageResult]:
        """Triage all JIB-tagged tickets.

        Args:
            force: If True, re-triage already processed tickets

        Returns:
            List of triage results
        """
        if not self.enabled:
            print("⚠️ JIB triage is disabled")
            return []

        print("🔍 Scanning for JIB-tagged tickets...")
        jib_tickets = self.find_jib_tagged_tickets()
        print(f"   Found {len(jib_tickets)} JIB-tagged ticket(s)")

        if not jib_tickets:
            return []

        # Load state to skip already-processed tickets
        state = self.load_state()
        processed = state.get("processed_tickets", {})

        results = []
        for ticket in jib_tickets:
            ticket_key = ticket.get("key", "")

            # Skip if already processed (unless force)
            if not force and ticket_key in processed:
                print(f"⏭️ Skipping already processed: {ticket_key}")
                continue

            result = self.triage_ticket(ticket)
            results.append(result)

            # Update state
            processed[ticket_key] = {
                "triaged_at": result.triaged_at,
                "classification": result.classification.value,
                "pr_url": result.pr_url,
            }

        # Save state
        state["processed_tickets"] = processed
        self.save_state(state)

        return results


def main():
    """Run the ticket triager."""
    import argparse

    parser = argparse.ArgumentParser(description="JIB Ticket Triager")
    parser.add_argument("--force", action="store_true", help="Re-triage already processed tickets")
    parser.add_argument("--ticket", type=str, help="Triage a specific ticket by key")

    args = parser.parse_args()

    triager = TicketTriager()

    if args.ticket:
        # Find and triage specific ticket
        jib_tickets = triager.find_jib_tagged_tickets()
        ticket = next((t for t in jib_tickets if t.get("key") == args.ticket), None)
        if ticket:
            result = triager.triage_ticket(ticket)
            print(f"\n✅ Triage complete: {result.classification.value}")
            if result.pr_url:
                print(f"   PR: {result.pr_url}")
        else:
            print(f"❌ Ticket not found: {args.ticket}")
            return 1
    else:
        # Triage all
        results = triager.triage_all(force=args.force)
        print(f"\n✅ Triaged {len(results)} ticket(s)")
        for result in results:
            status = "✓" if not result.error else "✗"
            print(f"   {status} {result.ticket_key}: {result.classification.value}")
            if result.pr_url:
                print(f"     PR: {result.pr_url}")
            if result.error:
                print(f"     Error: {result.error}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
