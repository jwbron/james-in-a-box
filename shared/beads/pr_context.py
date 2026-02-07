"""
PR Context Manager - Manages persistent PR context in Beads.

This module provides the PRContextManager class for tracking GitHub PR
work across container sessions using the Beads task system.

Each PR gets a unique task that tracks its entire lifecycle:
- Comments and responses
- CI check failures and fixes
- Review feedback and changes
- Merge conflict resolutions

Context ID format: pr-<repo>-<number> (e.g., pr-james-in-a-box-75)
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)


class PRContextManager:
    """Manages persistent PR context in Beads.

    Each PR gets a unique task that tracks its entire lifecycle:
    - Comments and responses
    - CI check failures and fixes
    - Review feedback and changes

    Context ID format: pr-<repo>-<number> (e.g., pr-james-in-a-box-75)

    Usage:
        manager = PRContextManager()

        # Get or create context for a PR
        beads_id = manager.get_or_create_context("owner/repo", 123, "PR Title")

        # Update with progress
        manager.update_context(beads_id, "Fixed linting errors", status="in_progress")

        # Close when done
        manager.update_context(beads_id, "All checks passing, PR ready", status="closed")
    """

    def __init__(self, beads_dir: Path | None = None):
        """Initialize PRContextManager.

        Args:
            beads_dir: Path to beads directory. Defaults to ~/beads.
        """
        self.beads_dir = beads_dir or Path.home() / "beads"

    def get_context_id(self, repo: str, pr_num: int) -> str:
        """Generate unique context ID for a PR.

        Args:
            repo: Repository in "owner/repo" format
            pr_num: PR number

        Returns:
            Context ID string like "pr-repo-name-123"
        """
        repo_name = repo.rsplit("/", maxsplit=1)[-1]
        return f"pr-{repo_name}-{pr_num}"

    def search_context(self, repo: str, pr_num: int) -> str | None:
        """Search for existing beads task for this PR.

        Uses label search to find the task by its context ID label.
        NOTE: This returns the task even if it's marked as closed, allowing
        context to be preserved across PR lifecycle.

        Args:
            repo: Repository in "owner/repo" format
            pr_num: PR number

        Returns:
            Beads task ID if found, None otherwise.
        """
        context_id = self.get_context_id(repo, pr_num)
        try:
            # Use --label to search by label (more reliable than --search which
            # only searches title/description)
            result = subprocess.run(
                ["bd", "list", "--label", context_id, "--allow-stale"],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Parse output to get task ID (first word of first line)
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if line.strip() and line.startswith("beads-"):
                        return line.split()[0]
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Beads search timed out")
            return None
        except Exception as e:
            logger.warning(f"Failed to search beads context: {e}")
            return None

    def get_context(self, repo: str, pr_num: int) -> dict | None:
        """Get existing context for a PR.

        Args:
            repo: Repository in "owner/repo" format
            pr_num: PR number

        Returns:
            Dict with task_id and content, or None if not found.
        """
        task_id = self.search_context(repo, pr_num)
        if not task_id:
            return None

        try:
            result = subprocess.run(
                ["bd", "show", task_id, "--allow-stale"],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0:
                return {"task_id": task_id, "content": result.stdout.strip()}
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Beads show timed out")
            return None
        except Exception as e:
            logger.warning(f"Failed to get beads context: {e}")
            return None

    def create_context(
        self,
        repo: str,
        pr_num: int,
        pr_title: str,
        task_type: str = "github-pr",
    ) -> str | None:
        """Create new beads task for a PR.

        Args:
            repo: Repository in "owner/repo" format
            pr_num: PR number
            pr_title: PR title for the task description
            task_type: Type label (default: "github-pr")

        Returns:
            Beads task ID if created, None otherwise.
        """
        context_id = self.get_context_id(repo, pr_num)
        repo_name = repo.rsplit("/", maxsplit=1)[-1]

        try:
            result = subprocess.run(
                [
                    "bd",
                    "create",
                    f"PR #{pr_num}: {pr_title}",
                    "--label",
                    task_type,
                    "--label",
                    context_id,
                    "--label",
                    repo_name,
                    "--allow-stale",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0:
                # Parse output to get task ID
                output = result.stdout.strip()
                if "beads-" in output:
                    # Extract task ID from output like "Created beads-abc123"
                    for word in output.split():
                        if word.startswith("beads-"):
                            return word.rstrip(":")
            logger.warning(f"Failed to create beads task: {result.stderr}")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Beads create timed out")
            return None
        except Exception as e:
            logger.warning(f"Failed to create beads context: {e}")
            return None

    def update_context(
        self,
        task_id: str,
        notes: str,
        status: str | None = None,
    ) -> bool:
        """Update beads task with new notes.

        Args:
            task_id: Beads task ID
            notes: Notes to append (will be timestamped)
            status: Optional status update (in_progress, closed, etc.)

        Returns:
            True if update succeeded, False otherwise.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        timestamped_notes = f"=== {timestamp} ===\n{notes}"

        try:
            cmd = ["bd", "update", task_id, "--notes", timestamped_notes, "--allow-stale"]
            if status:
                cmd.extend(["--status", status])

            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(f"Failed to update beads task: {result.stderr}")
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.warning("Beads update timed out")
            return False
        except Exception as e:
            logger.warning(f"Failed to update beads context: {e}")
            return False

    def get_or_create_context(
        self,
        repo: str,
        pr_num: int,
        pr_title: str = "",
        task_type: str = "github-pr",
    ) -> str | None:
        """Get existing context or create new one.

        This is the primary method for ensuring a PR has a beads task.
        NOTE: This loads existing tasks even if they're marked as closed,
        ensuring context is preserved when working on a PR.

        Args:
            repo: Repository in "owner/repo" format
            pr_num: PR number
            pr_title: PR title (used if creating new task)
            task_type: Type label for new tasks

        Returns:
            Beads task ID
        """
        existing = self.search_context(repo, pr_num)
        if existing:
            logger.debug(f"Found existing beads task: {existing}")
            return existing
        return self.create_context(repo, pr_num, pr_title or f"PR #{pr_num}", task_type)

    def get_context_summary(self, repo: str, pr_num: int) -> str:
        """Get a brief summary of the PR context for including in prompts.

        Args:
            repo: Repository in "owner/repo" format
            pr_num: PR number

        Returns:
            Summary string suitable for including in a Claude prompt.
        """
        context = self.get_context(repo, pr_num)
        if not context:
            return ""

        return f"""## Beads Context (Persistent Memory)

**Task ID**: {context["task_id"]}

This PR has an existing beads task for tracking work across sessions.
Previous context:

```
{context["content"][:2000]}
{"... (truncated)" if len(context["content"]) > 2000 else ""}
```

**IMPORTANT**: When you complete your work, update this beads task:
```bash
cd ~/beads
bd --allow-stale update {context["task_id"]} --notes "Your summary of what was done" --status in_progress
```
"""
