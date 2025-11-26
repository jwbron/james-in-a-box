#!/usr/bin/env python3
"""
GitHub Merge Conflict Resolver - Detects and resolves PR merge conflicts

Triggered by github-sync.service after syncing PR data.
Automatically attempts to resolve merge conflicts when possible.
"""

import json
import subprocess
import sys
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add shared path for notifications library
sys.path.insert(0, str(Path.home() / "khan" / "james-in-a-box" / "jib-container" / "shared"))
try:
    from notifications import slack_notify, NotificationContext
    HAS_NOTIFICATIONS = True
except ImportError:
    HAS_NOTIFICATIONS = False


class ConflictResolver:
    """Detects and resolves merge conflicts in open PRs."""

    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.prs_dir = self.github_dir / "prs"
        self.khan_dir = Path.home() / "khan"
        self.state_file = Path.home() / "sharing" / "tracking" / "conflict-resolver-state.json"
        self.state = self.load_state()

    def load_state(self) -> Dict:
        """Load previous state (conflicts already handled)."""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except Exception:
                pass
        return {"handled_conflicts": {}, "resolved": [], "failed": []}

    def save_state(self):
        """Save state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w") as f:
            json.dump(self.state, f, indent=2)

    def run_git(self, args: List[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )

    def run_gh(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run a gh CLI command."""
        return subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            check=False,
        )

    def get_pr_info(self, pr_file: Path) -> Optional[Dict]:
        """Extract PR info from synced markdown file."""
        try:
            content = pr_file.read_text()
            info = {
                "pr_number": None,
                "repository": None,
                "head_branch": None,
                "base_branch": None,
                "url": None,
                "title": None,
            }

            for line in content.split("\n"):
                if line.startswith("# PR #"):
                    # Parse: "# PR #123: Title"
                    parts = line[6:].split(":", 1)
                    if parts:
                        info["pr_number"] = int(parts[0].strip())
                        if len(parts) > 1:
                            info["title"] = parts[1].strip()
                elif line.startswith("**Repository**:"):
                    info["repository"] = line.replace("**Repository**:", "").strip()
                elif line.startswith("**Branch**:"):
                    branch_info = line.replace("**Branch**:", "").strip()
                    if " → " in branch_info:
                        head, base = branch_info.split(" → ", 1)
                        info["head_branch"] = head.strip()
                        info["base_branch"] = base.strip()
                elif line.startswith("**URL**:"):
                    info["url"] = line.replace("**URL**:", "").strip()

            if info["pr_number"] and info["repository"]:
                return info
            return None
        except Exception as e:
            print(f"  Error parsing {pr_file.name}: {e}")
            return None

    def check_for_conflicts(self, repo_path: Path, head_branch: str, base_branch: str) -> Tuple[bool, str]:
        """
        Check if merging base into head would cause conflicts.
        Returns (has_conflicts, message).
        """
        try:
            # Fetch latest from origin
            self.run_git(["fetch", "origin"], cwd=repo_path, check=False)

            # Create a temporary branch for testing
            temp_branch = f"jib-conflict-check-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Checkout head branch
            result = self.run_git(["checkout", head_branch], cwd=repo_path, check=False)
            if result.returncode != 0:
                # Try with origin prefix
                result = self.run_git(["checkout", "-b", head_branch, f"origin/{head_branch}"], cwd=repo_path, check=False)
                if result.returncode != 0:
                    return False, f"Could not checkout {head_branch}: {result.stderr}"

            # Pull latest
            self.run_git(["pull", "--ff-only"], cwd=repo_path, check=False)

            # Create temp branch from head
            self.run_git(["checkout", "-b", temp_branch], cwd=repo_path, check=False)

            # Try to merge base branch
            merge_result = self.run_git(
                ["merge", f"origin/{base_branch}", "--no-commit", "--no-ff"],
                cwd=repo_path,
                check=False,
            )

            has_conflicts = merge_result.returncode != 0 and "CONFLICT" in merge_result.stdout

            # Abort merge and cleanup
            self.run_git(["merge", "--abort"], cwd=repo_path, check=False)
            self.run_git(["checkout", head_branch], cwd=repo_path, check=False)
            self.run_git(["branch", "-D", temp_branch], cwd=repo_path, check=False)

            if has_conflicts:
                return True, merge_result.stdout
            return False, "No conflicts detected"

        except Exception as e:
            return False, f"Error checking conflicts: {e}"

    def resolve_conflicts(
        self, repo_path: Path, pr_info: Dict
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Attempt to resolve merge conflicts.
        Returns (success, message, commit_hash).
        """
        head_branch = pr_info["head_branch"]
        base_branch = pr_info["base_branch"]
        pr_num = pr_info["pr_number"]

        try:
            # Fetch latest
            self.run_git(["fetch", "origin"], cwd=repo_path, check=False)

            # Checkout head branch
            result = self.run_git(["checkout", head_branch], cwd=repo_path, check=False)
            if result.returncode != 0:
                result = self.run_git(
                    ["checkout", "-b", head_branch, f"origin/{head_branch}"],
                    cwd=repo_path,
                    check=False,
                )
                if result.returncode != 0:
                    return False, f"Could not checkout {head_branch}", None

            # Pull latest on head branch
            self.run_git(["pull", "--ff-only"], cwd=repo_path, check=False)

            # Try to merge base branch with different strategies
            strategies = [
                (["merge", f"origin/{base_branch}", "-m", f"Merge {base_branch} into {head_branch} (auto-resolved)"], "default"),
                (["merge", f"origin/{base_branch}", "-X", "theirs", "-m", f"Merge {base_branch} into {head_branch} (accepting base changes)"], "theirs"),
                (["merge", f"origin/{base_branch}", "-X", "ours", "-m", f"Merge {base_branch} into {head_branch} (keeping our changes)"], "ours"),
            ]

            for merge_cmd, strategy_name in strategies:
                # Reset to clean state
                self.run_git(["reset", "--hard", f"origin/{head_branch}"], cwd=repo_path, check=False)

                result = self.run_git(merge_cmd, cwd=repo_path, check=False)

                if result.returncode == 0:
                    # Success! Get commit hash
                    hash_result = self.run_git(["rev-parse", "--short", "HEAD"], cwd=repo_path, check=False)
                    commit_hash = hash_result.stdout.strip()

                    # Push the resolved changes
                    push_result = self.run_git(["push", "origin", head_branch], cwd=repo_path, check=False)
                    if push_result.returncode == 0:
                        return True, f"Resolved using '{strategy_name}' strategy", commit_hash
                    else:
                        return False, f"Merged but push failed: {push_result.stderr}", commit_hash

                # Abort failed merge attempt
                self.run_git(["merge", "--abort"], cwd=repo_path, check=False)

            return False, "Could not auto-resolve conflicts with any strategy", None

        except Exception as e:
            # Cleanup on error
            self.run_git(["merge", "--abort"], cwd=repo_path, check=False)
            return False, f"Error: {e}", None

    def notify(self, title: str, message: str, pr_info: Dict, success: bool = True):
        """Send notification about conflict resolution."""
        if HAS_NOTIFICATIONS:
            ctx = NotificationContext(
                task_id=f"conflict-pr-{pr_info['pr_number']}",
                repository=pr_info["repository"],
            )
            emoji = ":white_check_mark:" if success else ":warning:"
            slack_notify(f"{emoji} {title}", message, context=ctx)
        else:
            # Fallback to file-based notification
            notifications_dir = Path.home() / "sharing" / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            notif_file = notifications_dir / f"{timestamp}-conflict-{pr_info['pr_number']}.md"

            with notif_file.open("w") as f:
                f.write(f"# {title}\n\n")
                f.write(message)
                f.write(f"\n\n---\n{datetime.now().isoformat()}\n")

    def process_pr(self, pr_file: Path):
        """Process a single PR for conflicts."""
        pr_info = self.get_pr_info(pr_file)
        if not pr_info:
            return

        pr_key = f"{pr_info['repository']}#{pr_info['pr_number']}"
        repo_name = pr_info["repository"].split("/")[-1]
        repo_path = self.khan_dir / repo_name

        # Skip if already handled recently
        if pr_key in self.state["handled_conflicts"]:
            last_check = self.state["handled_conflicts"][pr_key]
            # Re-check if last check was more than 1 hour ago
            last_time = datetime.fromisoformat(last_check.replace("Z", "+00:00"))
            if (datetime.now(last_time.tzinfo) - last_time).total_seconds() < 3600:
                return

        print(f"Checking PR #{pr_info['pr_number']} ({repo_name}) for conflicts...")

        if not repo_path.exists():
            print(f"  Repository not found: {repo_path}")
            return

        # Check for conflicts
        has_conflicts, conflict_msg = self.check_for_conflicts(
            repo_path, pr_info["head_branch"], pr_info["base_branch"]
        )

        if not has_conflicts:
            print(f"  No conflicts detected")
            self.state["handled_conflicts"][pr_key] = datetime.utcnow().isoformat() + "Z"
            self.save_state()
            return

        print(f"  Conflicts detected! Attempting resolution...")

        # Attempt resolution
        success, resolve_msg, commit_hash = self.resolve_conflicts(repo_path, pr_info)

        if success:
            print(f"  Successfully resolved conflicts! Commit: {commit_hash}")
            self.state["resolved"].append({
                "pr_key": pr_key,
                "commit": commit_hash,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "message": resolve_msg,
            })

            # Add comment to PR
            comment = f"""## :robot: Merge Conflicts Resolved

I detected merge conflicts between `{pr_info['head_branch']}` and `{pr_info['base_branch']}` and automatically resolved them.

**Resolution**: {resolve_msg}
**Commit**: `{commit_hash}`

Please review the merge commit to ensure the resolution is correct.

--- Authored by jib"""

            self.run_gh([
                "pr", "comment", str(pr_info["pr_number"]),
                "--repo", pr_info["repository"],
                "--body", comment,
            ])

            self.notify(
                f"Merge Conflicts Resolved: PR #{pr_info['pr_number']}",
                f"**PR**: {pr_info['title']}\n**Repository**: {pr_info['repository']}\n**Resolution**: {resolve_msg}\n**Commit**: {commit_hash}",
                pr_info,
                success=True,
            )
        else:
            print(f"  Could not auto-resolve: {resolve_msg}")
            self.state["failed"].append({
                "pr_key": pr_key,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "message": resolve_msg,
            })

            self.notify(
                f"Merge Conflicts Need Attention: PR #{pr_info['pr_number']}",
                f"**PR**: {pr_info['title']}\n**Repository**: {pr_info['repository']}\n**Issue**: {resolve_msg}\n\nManual conflict resolution required.",
                pr_info,
                success=False,
            )

        self.state["handled_conflicts"][pr_key] = datetime.utcnow().isoformat() + "Z"
        self.save_state()

    def run(self):
        """Main entry point - check all PRs for conflicts."""
        print("Checking PRs for merge conflicts...")

        if not self.prs_dir.exists():
            print("No PRs directory found, skipping")
            return 0

        pr_files = list(self.prs_dir.glob("*-PR-*.md"))
        if not pr_files:
            print("No PR files found")
            return 0

        print(f"Found {len(pr_files)} PR(s) to check")

        for pr_file in pr_files:
            try:
                self.process_pr(pr_file)
            except Exception as e:
                print(f"Error processing {pr_file.name}: {e}")
                continue

        # Summary
        resolved_count = len(self.state.get("resolved", []))
        failed_count = len(self.state.get("failed", []))
        print(f"\nConflict resolution summary: {resolved_count} resolved, {failed_count} need attention")

        return 0


def main():
    """Main entry point."""
    resolver = ConflictResolver()
    return resolver.run()


if __name__ == "__main__":
    sys.exit(main())
