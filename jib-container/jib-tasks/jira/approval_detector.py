#!/usr/bin/env python3
"""
Approval Detector - Detects approved planning PRs and triggers implementation.

When a planning document PR is merged, this module:
1. Detects the merged PR via GitHub sync
2. Parses the planning document to extract implementation plan
3. Creates a Beads task for implementation
4. Triggers CPF implementation workflow

Part of the JIRA Ticket Triage Workflow (ADR).
"""

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ApprovedPlan:
    """Container for an approved planning document."""

    pr_number: int
    ticket_key: str
    title: str
    plan_file_path: str
    plan_content: str
    merged_at: str
    merged_by: str

    # Extracted from plan
    requirements: list[dict] = field(default_factory=list)
    implementation_tasks: list[dict] = field(default_factory=list)
    affected_files: list[str] = field(default_factory=list)


class ApprovalDetector:
    """Detects approved planning PRs and triggers implementation."""

    def __init__(
        self,
        repos_dir: Path | str | None = None,
        plan_dir: str | None = None,
        enabled_repos: list[str] | None = None,
    ):
        """Initialize the approval detector.

        Args:
            repos_dir: Base directory containing repositories
            plan_dir: Directory where planning docs are stored (relative to repo)
            enabled_repos: List of enabled repositories
        """
        self.repos_dir = Path(repos_dir or os.path.expanduser("~/khan"))
        self.plan_dir = plan_dir or os.environ.get("JIB_PLAN_OUTPUT_DIR", "docs/plans")

        if enabled_repos:
            self.enabled_repos = enabled_repos
        else:
            repos_env = os.environ.get("JIB_TRIAGE_ENABLED_REPOS", "jwbron/james-in-a-box")
            self.enabled_repos = [r.strip() for r in repos_env.split(",")]

        # State tracking
        self.state_file = Path.home() / "sharing" / "tracking" / "jib-approval-state.json"

    def find_merged_planning_prs(self) -> list[ApprovedPlan]:
        """Find recently merged planning document PRs.

        Returns:
            List of ApprovedPlan objects for PRs that haven't been processed
        """
        approved_plans = []
        state = self._load_state()
        processed_prs = state.get("processed_prs", {})

        for repo in self.enabled_repos:
            repo_name = repo.split("/")[-1]
            repo_path = self.repos_dir / repo_name

            if not repo_path.exists():
                continue

            try:
                # Use gh CLI to find merged PRs with planning docs
                result = subprocess.run(
                    [
                        "gh",
                        "pr",
                        "list",
                        "--repo",
                        repo,
                        "--state",
                        "merged",
                        "--search",
                        "[JIB] Plan:",
                        "--json",
                        "number,title,mergedAt,mergedBy,headRefName,files",
                        "--limit",
                        "20",
                    ],
                    capture_output=True,
                    text=True,
                    cwd=repo_path,
                )

                if result.returncode != 0:
                    print(f"Warning: Failed to list PRs for {repo}: {result.stderr}")
                    continue

                prs = json.loads(result.stdout) if result.stdout else []

                for pr in prs:
                    pr_number = pr.get("number")
                    pr_key = f"{repo}#{pr_number}"

                    # Skip if already processed
                    if pr_key in processed_prs:
                        continue

                    # Check if PR contains a planning doc
                    files = pr.get("files", [])
                    plan_files = [f for f in files if f.get("path", "").startswith(self.plan_dir)]

                    if not plan_files:
                        continue

                    # Extract ticket key from title
                    title = pr.get("title", "")
                    ticket_match = re.search(r"\[JIB\] Plan: (\w+-\d+)", title)
                    ticket_key = ticket_match.group(1) if ticket_match else "UNKNOWN"

                    # Get the planning document content
                    plan_file = plan_files[0].get("path", "")
                    plan_content = self._get_file_content(repo_path, plan_file)

                    if plan_content:
                        approved_plan = ApprovedPlan(
                            pr_number=pr_number,
                            ticket_key=ticket_key,
                            title=title,
                            plan_file_path=plan_file,
                            plan_content=plan_content,
                            merged_at=pr.get("mergedAt", ""),
                            merged_by=pr.get("mergedBy", {}).get("login", "unknown"),
                        )

                        # Parse the plan to extract implementation details
                        self._parse_plan(approved_plan)
                        approved_plans.append(approved_plan)

            except Exception as e:
                print(f"Error checking {repo}: {e}")
                continue

        return approved_plans

    def _get_file_content(self, repo_path: Path, file_path: str) -> str | None:
        """Get content of a file from the main branch."""
        try:
            full_path = repo_path / file_path
            if full_path.exists():
                return full_path.read_text()

            # Try to get from git
            result = subprocess.run(
                ["git", "show", f"main:{file_path}"],
                capture_output=True,
                text=True,
                cwd=repo_path,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            pass
        return None

    def _parse_plan(self, plan: ApprovedPlan) -> None:
        """Parse planning document to extract implementation details."""
        content = plan.plan_content

        # Extract requirements
        req_pattern = r"\| FR-\d+ \| (.+?) \| (.+?) \| (\w+) \|"
        for match in re.finditer(req_pattern, content):
            plan.requirements.append(
                {
                    "requirement": match.group(1).strip(),
                    "criteria": match.group(2).strip(),
                    "confidence": match.group(3).strip(),
                }
            )

        # Extract affected files
        file_pattern = r"\| `(.+?)` \| (\w+) \| (.+?) \|"
        for match in re.finditer(file_pattern, content):
            plan.affected_files.append(match.group(1))

        # Extract implementation tasks
        task_pattern = r"\| (Task [^|]+) \| ([^|]+) \| ([^|]+) \|"
        for match in re.finditer(task_pattern, content):
            plan.implementation_tasks.append(
                {
                    "task": match.group(1).strip(),
                    "dependencies": match.group(2).strip(),
                    "criteria": match.group(3).strip(),
                }
            )

    def trigger_implementation(self, plan: ApprovedPlan) -> bool:
        """Trigger implementation for an approved plan.

        Args:
            plan: Approved planning document

        Returns:
            True if implementation was triggered successfully
        """
        print(f"🚀 Triggering implementation for {plan.ticket_key}")

        # Find the repository
        repo_path = None
        for repo in self.enabled_repos:
            repo_name = repo.split("/")[-1]
            path = self.repos_dir / repo_name
            if path.exists():
                repo_path = path
                break

        if not repo_path:
            print("❌ No enabled repository found")
            return False

        try:
            # Create Beads task for implementation
            self._create_beads_task(plan)

            # Build prompt for implementation
            prompt = self._build_implementation_prompt(plan)

            # Import and run agent
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "llm"))
            from llm import run_agent

            print(f"  📝 Starting CPF implementation...")
            result = run_agent(prompt, cwd=repo_path, timeout=1800)  # 30 minute timeout

            if result.success:
                print(f"  ✅ Implementation complete")
                # Try to extract PR URL
                pr_match = re.search(r"https://github\.com/[^\s]+/pull/\d+", result.stdout or "")
                if pr_match:
                    print(f"  📎 PR: {pr_match.group(0)}")
                return True
            else:
                print(f"  ❌ Implementation failed: {result.error}")
                return False

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return False

    def _create_beads_task(self, plan: ApprovedPlan) -> None:
        """Create a Beads task for tracking implementation."""
        try:
            subprocess.run(
                [
                    "bd",
                    "--allow-stale",
                    "create",
                    f"{plan.ticket_key}: Implementation",
                    "--labels",
                    f"{plan.ticket_key},jira,implementation,cpf",
                    "--description",
                    f"CPF implementation for approved plan PR #{plan.pr_number}",
                ],
                capture_output=True,
            )
        except Exception as e:
            print(f"Warning: Failed to create Beads task: {e}")

    def _build_implementation_prompt(self, plan: ApprovedPlan) -> str:
        """Build the prompt for CPF implementation."""
        requirements_text = "\n".join(
            f"- {r['requirement']} (Criteria: {r['criteria']})"
            for r in plan.requirements
        ) or "See planning document"

        tasks_text = "\n".join(
            f"- {t['task']}: {t['criteria']}"
            for t in plan.implementation_tasks
        ) or "See planning document"

        files_text = "\n".join(f"- {f}" for f in plan.affected_files) or "To be determined"

        return f"""# CPF Implementation: {plan.ticket_key}

## Context

This is a CPF (Collaborative Planning Framework) implementation task. A planning document was created and approved by a human reviewer.

**Ticket:** {plan.ticket_key}
**Title:** {plan.title}
**Approved PR:** #{plan.pr_number}
**Approved by:** {plan.merged_by}

## Planning Document

The approved planning document is at: `{plan.plan_file_path}`

Please read this document first to understand the full requirements and approach.

## Requirements Summary

{requirements_text}

## Implementation Tasks

{tasks_text}

## Affected Files

{files_text}

## Instructions

1. **Read the planning document** at `{plan.plan_file_path}` in full
2. **Create a feature branch**: `jib/{plan.ticket_key.lower()}-impl`
3. **Implement according to the approved plan**:
   - Follow the phased approach in the planning document
   - Meet all acceptance criteria
   - Address all requirements
4. **Add/update tests** to cover the changes
5. **Update documentation** if needed
6. **Create an implementation PR**:
   - Title: `[JIB] Impl: {plan.ticket_key} {{summary}}`
   - Reference the planning PR #{plan.pr_number}
   - Request review from @jwiesebron
7. **Output the PR URL**

## Important

- This is an APPROVED plan - follow it as specified
- If you encounter issues, document them but attempt to complete
- Maintain checkpoints per the planning document
- Keep the implementation focused on the approved scope

Proceed with the implementation now.
"""

    def _load_state(self) -> dict:
        """Load detector state from file."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {"processed_prs": {}}

    def _save_state(self, state: dict) -> None:
        """Save detector state to file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(state, indent=2))

    def mark_processed(self, plan: ApprovedPlan, repo: str) -> None:
        """Mark a planning PR as processed."""
        state = self._load_state()
        pr_key = f"{repo}#{plan.pr_number}"
        state.setdefault("processed_prs", {})[pr_key] = {
            "ticket_key": plan.ticket_key,
            "processed_at": datetime.now().isoformat(),
        }
        self._save_state(state)

    def run(self) -> int:
        """Run the approval detector.

        Returns:
            Number of plans processed
        """
        print("🔍 Checking for approved planning PRs...")
        approved_plans = self.find_merged_planning_prs()

        if not approved_plans:
            print("   No new approved plans found")
            return 0

        print(f"   Found {len(approved_plans)} approved plan(s)")

        processed = 0
        for plan in approved_plans:
            print(f"\n📋 Processing: {plan.ticket_key}")
            success = self.trigger_implementation(plan)

            if success:
                # Mark as processed
                for repo in self.enabled_repos:
                    self.mark_processed(plan, repo)
                processed += 1

        return processed


def main():
    """Run the approval detector."""
    import argparse

    parser = argparse.ArgumentParser(description="JIB Approval Detector")
    parser.add_argument("--dry-run", action="store_true", help="Only detect, don't trigger implementation")

    args = parser.parse_args()

    detector = ApprovalDetector()

    if args.dry_run:
        print("🔍 Dry run - checking for approved plans...")
        plans = detector.find_merged_planning_prs()
        if plans:
            print(f"\nFound {len(plans)} approved plan(s):")
            for plan in plans:
                print(f"  - {plan.ticket_key}: {plan.title}")
                print(f"    PR: #{plan.pr_number}, Merged by: {plan.merged_by}")
        else:
            print("No approved plans found")
        return 0

    processed = detector.run()
    print(f"\n✅ Processed {processed} approved plan(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
