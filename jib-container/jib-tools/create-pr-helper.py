#!/usr/bin/env python3
"""
PR Creation Helper - Creates GitHub PRs for completed tasks

Used by jib after completing a task to:
1. Create a PR with title, description
2. Request review from the user
3. Return PR URL for Slack notification

Usage:
  create-pr-helper.py --title "PR title" --body "Description"
  create-pr-helper.py --from-file pr-details.json
  create-pr-helper.py --auto  # Auto-generate from git log (uses default reviewer from config)

Repository configuration (including default reviewer and writable repos) is loaded
from config/repositories.yaml - the single source of truth for jib repo access.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


# Add shared directory to path for notifications import
# Path: jib-container/jib-tools/create-pr-helper.py -> repo-root/shared
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from notifications import get_slack_service


# Try to load repo config for default reviewer and writable repos check
try:
    # When running inside container, config is at ~/khan/james-in-a-box/config/
    config_paths = [
        Path(__file__).parent.parent.parent / "config",  # From scripts dir
        Path.home() / "khan" / "james-in-a-box" / "config",  # From container
    ]
    for config_path in config_paths:
        if (config_path / "repo_config.py").exists():
            sys.path.insert(0, str(config_path.parent))
            break
    from config.repo_config import get_default_reviewer, get_writable_repos, is_writable_repo

    HAS_REPO_CONFIG = True
except ImportError:
    HAS_REPO_CONFIG = False

    def get_default_reviewer():
        # Config not found - require explicit --reviewer flag
        return None

    def is_writable_repo(repo):
        return True  # Allow by default if config unavailable

    def get_writable_repos():
        return []  # No repos if config unavailable


class PRCreator:
    def __init__(self):
        self.repo_root = self.find_repo_root()
        self.slack = get_slack_service()

    def get_repo_name(self) -> str | None:
        """Get the owner/repo name from git remote origin."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True
            )
            url = result.stdout.strip()
            # Handle SSH URLs: git@github.com:owner/repo.git
            if url.startswith("git@"):
                parts = url.split(":")[-1]
                return parts.replace(".git", "")
            # Handle HTTPS URLs: https://github.com/owner/repo.git
            elif "github.com" in url:
                parts = url.split("github.com/")[-1]
                return parts.replace(".git", "")
            return None
        except subprocess.CalledProcessError:
            return None

    def check_writable(self) -> tuple[bool, str]:
        """Check if current repo is in the writable repos list.

        Returns:
            (is_writable, repo_name) - Whether repo is writable and its name
        """
        repo_name = self.get_repo_name()
        if not repo_name:
            return False, "unknown"
        return is_writable_repo(repo_name), repo_name

    def find_repo_root(self) -> Path | None:
        """Find the git repository root"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            return None

    def get_current_branch(self) -> str:
        """Get current git branch name"""
        result = subprocess.run(
            ["git", "branch", "--show-current"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def get_base_branch(self) -> str:
        """Determine the base branch (main or master)"""
        result = subprocess.run(
            ["git", "remote", "show", "origin"], check=False, capture_output=True, text=True
        )
        if "HEAD branch: main" in result.stdout:
            return "main"
        return "master"

    def get_commits_since_base(self, base_branch: str) -> list:
        """Get commits on current branch not in base (oneline format for titles)"""
        try:
            result = subprocess.run(
                ["git", "log", f"{base_branch}..HEAD", "--oneline"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip().split("\n") if result.stdout.strip() else []
        except subprocess.CalledProcessError:
            return []

    def warn_if_many_commits(self, base_branch: str, threshold: int = 5) -> None:
        """Warn if there are many commits - could indicate cross-contamination.

        When a branch has more commits than expected, it might contain commits
        from other PRs that were accidentally included.
        """
        commits = self.get_commits_since_base(base_branch)
        if len(commits) > threshold:
            print(f"\n⚠️  WARNING: Branch has {len(commits)} commits (threshold: {threshold})")
            print("This might indicate cross-contamination from other PRs.")
            print("Commits to be included in this PR:")
            for commit in commits[:10]:
                print(f"  - {commit}")
            if len(commits) > 10:
                print(f"  ... and {len(commits) - 10} more")
            print("\nPlease verify these commits belong to this PR before proceeding.")
            print("If unexpected commits are present, reset your branch first:\n")
            print(f"  git fetch origin && git reset --hard origin/{base_branch}\n")

    def get_full_commit_messages(self, base_branch: str) -> str:
        """Get full commit messages (including body) for all commits since base."""
        try:
            result = subprocess.run(
                ["git", "log", f"{base_branch}..HEAD", "--format=%B---COMMIT_SEPARATOR---"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return ""

    def get_changed_files(self, base_branch: str) -> list:
        """Get list of files changed since base branch."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{base_branch}..HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip().split("\n") if result.stdout.strip() else []
        except subprocess.CalledProcessError:
            return []

    def generate_pr_body(self, commits: list, custom_body: str = "") -> str:
        """Generate PR body following Khan Academy standards.

        Format:
        - Full summary (context, changes, impact)
        - Issue link
        - Test plan with specific steps

        Extracts context from commit message bodies when available.
        """
        base_branch = self.get_base_branch()
        full_messages = self.get_full_commit_messages(base_branch)
        changed_files = self.get_changed_files(base_branch)

        body_parts = []

        # Extract useful content from commit messages
        # Commit messages often have the context we need
        commit_bodies = []
        if full_messages:
            messages = full_messages.split("---COMMIT_SEPARATOR---")
            for msg in messages:
                msg = msg.strip()
                if msg:
                    # Skip lines that are just the title (first line) or metadata
                    lines = msg.split("\n")
                    # Get body (everything after first line, excluding metadata lines)
                    body_lines = []
                    for line in lines[1:]:
                        # Skip metadata lines
                        if line.startswith(("🤖", "Co-Authored-By:")):
                            continue
                        body_lines.append(line)
                    body = "\n".join(body_lines).strip()
                    if body:
                        commit_bodies.append(body)

        # Build the summary section
        if custom_body:
            body_parts.append(custom_body)
            body_parts.append("\n\n")
        elif commit_bodies:
            # Use the commit message body as the summary
            # Take the most detailed one (usually the main commit)
            best_body = max(commit_bodies, key=len)
            body_parts.append(best_body)
            body_parts.append("\n\n")
        else:
            # Fallback: generate basic summary from commits
            body_parts.append("## Summary\n\n")
            if len(commits) == 1:
                body_parts.append("This PR includes changes from 1 commit.\n\n")
            else:
                body_parts.append(f"This PR includes changes from {len(commits)} commits.\n\n")

        # Add commits section if multiple commits
        if len(commits) > 1:
            body_parts.append("## Commits\n\n")
            for commit in commits[:10]:
                body_parts.append(f"- {commit}\n")
            if len(commits) > 10:
                body_parts.append(f"- ... and {len(commits) - 10} more commits\n")
            body_parts.append("\n")

        # Issue link
        body_parts.append("Issue: none\n\n")

        # Generate test plan based on changed files
        body_parts.append("## Test Plan\n\n")
        test_items = self._generate_test_plan(changed_files)
        for item in test_items:
            body_parts.append(f"- {item}\n")

        body_parts.append("\n---\n")
        body_parts.append("*— Authored by jib*\n")

        return "".join(body_parts)

    def _generate_test_plan(self, changed_files: list) -> list:
        """Generate contextual test plan based on changed files."""
        test_items = []

        # Categorize files
        python_files = [f for f in changed_files if f.endswith(".py")]
        js_files = [f for f in changed_files if f.endswith((".js", ".ts", ".tsx"))]
        test_files = [f for f in changed_files if "test" in f.lower()]
        config_files = [f for f in changed_files if f.endswith((".yaml", ".yml", ".json", ".toml"))]

        # Add relevant test commands
        if python_files:
            if test_files:
                test_items.append("Run `pytest` - verify tests pass")
            else:
                test_items.append("Manual testing of Python changes")

        if js_files:
            if test_files:
                test_items.append("Run `npm test` - verify tests pass")
            else:
                test_items.append("Manual testing of JavaScript changes")

        if config_files:
            test_items.append("Verify configuration changes are correct")

        # Always include these basics
        if not test_items:
            test_items.append("Manual verification of changes")

        test_items.append("Code review for correctness and edge cases")

        # Add specific file hints for reviewers
        if len(changed_files) <= 5:
            test_items.append(f"Files to review: {', '.join(changed_files)}")

        return test_items

    def push_branch(self, branch: str) -> bool:
        """Push current branch to remote"""
        print(f"Pushing branch {branch} to remote...")
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch], check=False, capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"Error pushing branch: {result.stderr}", file=sys.stderr)
            return False
        print(f"  Pushed branch {branch}")
        return True

    def create_pr(
        self,
        title: str,
        body: str,
        base: str | None = None,
        reviewer: str | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Create a PR using gh CLI"""
        branch = self.get_current_branch()
        base_branch = base or self.get_base_branch()

        # Check if branch has been pushed
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch],
            check=False,
            capture_output=True,
            text=True,
        )
        if not result.stdout.strip() and not self.push_branch(branch):
            # Branch not on remote, push it
            return {"success": False, "error": "Failed to push branch to remote"}

        # Build gh pr create command
        cmd = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base_branch]

        if reviewer:
            cmd.extend(["--reviewer", reviewer])

        if draft:
            cmd.append("--draft")

        print(f"Creating PR: {title}")
        print(f"  Branch: {branch} -> {base_branch}")

        result = subprocess.run(cmd, check=False, capture_output=True, text=True)

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            # Check if PR already exists
            if "already exists" in error_msg.lower():
                # Try to get existing PR URL
                pr_url = self.get_existing_pr_url(branch)
                if pr_url:
                    return {
                        "success": True,
                        "url": pr_url,
                        "already_existed": True,
                        "branch": branch,
                        "base": base_branch,
                    }
            return {"success": False, "error": error_msg}

        # Extract PR URL from output
        pr_url = result.stdout.strip()

        return {
            "success": True,
            "url": pr_url,
            "branch": branch,
            "base": base_branch,
            "title": title,
            "reviewer": reviewer,
        }

    def get_existing_pr_url(self, branch: str) -> str | None:
        """Get URL of existing PR for branch"""
        result = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "url", "--jq", ".url"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def create_notification(self, pr_result: dict[str, Any], task_context: str = ""):
        """Create notification about PR creation using the notifications service."""
        self.get_repo_name() or "unknown"

        if pr_result["success"]:
            # Include task context in the body if provided
            body_parts = [
                f"**URL**: {pr_result['url']}",
                f"**Branch**: `{pr_result.get('branch', 'unknown')}` -> `{pr_result.get('base', 'main')}`",
                f"**Title**: {pr_result.get('title', 'New PR')}",
            ]

            if pr_result.get("reviewer"):
                body_parts.append(f"**Reviewer**: @{pr_result['reviewer']}")

            if pr_result.get("already_existed"):
                body_parts.append("\n*Note: PR already existed for this branch*")

            if task_context:
                body_parts.append(f"\n## Context\n\n{task_context}")

            self.slack.notify_success(
                title="Pull Request Created",
                body="\n".join(body_parts),
            )
        else:
            body = f"**Error**: {pr_result.get('error', 'Unknown error')}"
            if task_context:
                body += f"\n\n## Context\n\n{task_context}"

            self.slack.notify_error(
                title="PR Creation Failed",
                body=body,
            )


def main():
    # Get default reviewer from config
    default_reviewer = get_default_reviewer()

    parser = argparse.ArgumentParser(description="Create GitHub PR for completed task")
    parser.add_argument("--title", "-t", help="PR title")
    parser.add_argument("--body", "-b", help="PR description body")
    parser.add_argument(
        "--reviewer",
        "-r",
        default=default_reviewer,
        help=f"Reviewer to request (default: {default_reviewer}, from config)",
    )
    parser.add_argument("--base", help="Base branch (default: auto-detect main/master)")
    parser.add_argument("--draft", action="store_true", help="Create as draft PR")
    parser.add_argument("--from-file", "-f", help="Read PR details from JSON file")
    parser.add_argument(
        "--auto", "-a", action="store_true", help="Auto-generate title/body from git log"
    )
    parser.add_argument("--no-notify", action="store_true", help="Skip creating notification")
    parser.add_argument("--context", "-c", help="Task context for notification")
    parser.add_argument(
        "--list-writable", action="store_true", help="List repositories where jib has write access"
    )

    args = parser.parse_args()

    # Handle --list-writable flag
    if args.list_writable:
        print("Repositories where jib has write access:")
        print("(From config/repositories.yaml)")
        print()
        for repo in get_writable_repos():
            print(f"  - {repo}")
        print()
        print(f"Default reviewer: {default_reviewer}")
        sys.exit(0)

    creator = PRCreator()

    if not creator.repo_root:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    # Check if this repo is in the writable repos list
    is_writable, repo_name = creator.check_writable()
    if not is_writable:
        print(f"Note: Repository '{repo_name}' is not in the writable repos list.")
        print("Sending Slack notification with PR context instead of creating GitHub PR.")
        print()

        # Generate the PR details for the notification
        base = args.base or creator.get_base_branch()
        commits = creator.get_commits_since_base(base)
        changed_files = creator.get_changed_files(base)
        branch = creator.get_current_branch()

        if not commits:
            print("Error: No commits found to summarize", file=sys.stderr)
            sys.exit(1)

        # Warn about potential cross-contamination
        creator.warn_if_many_commits(base)

        # Generate title from first commit if not provided
        pr_title = args.title
        if not pr_title:
            first_commit = commits[0]
            if " " in first_commit:
                pr_title = first_commit.split(" ", 1)[1]
            else:
                pr_title = first_commit

        # Generate body
        creator.generate_pr_body(commits, args.body or "")

        # Send Slack notification with full context
        body_parts = [
            f"**Repository**: {repo_name} (read-only - manual PR creation required)",
            f"**Branch**: `{branch}` -> `{base}`",
            f"**Title**: {pr_title}",
            "\n## Summary\n",
        ]

        # Add commit list
        if len(commits) <= 5:
            for commit in commits:
                body_parts.append(f"- {commit}")
        else:
            for commit in commits[:5]:
                body_parts.append(f"- {commit}")
            body_parts.append(f"- ... and {len(commits) - 5} more commits")

        # Add changed files
        body_parts.append(f"\n## Changed Files ({len(changed_files)} files)\n")
        if len(changed_files) <= 10:
            for f in changed_files:
                body_parts.append(f"- `{f}`")
        else:
            for f in changed_files[:10]:
                body_parts.append(f"- `{f}`")
            body_parts.append(f"- ... and {len(changed_files) - 10} more files")

        if args.context:
            body_parts.append(f"\n## Context\n\n{args.context}")

        body_parts.append(f"\n---\n*Please create the PR manually from branch `{branch}`*")

        creator.slack.notify_action_required(
            title=f"PR Ready for Manual Creation: {pr_title}",
            body="\n".join(body_parts),
        )

        print("\nSlack notification sent!")
        print(f"Branch '{branch}' is ready for manual PR creation.")
        sys.exit(0)

    # Determine PR details
    title = args.title
    body = args.body or ""

    if args.from_file:
        # Load from JSON file
        with open(args.from_file) as f:
            data = json.load(f)
            title = data.get("title", title)
            body = data.get("body", body)

    if args.auto or not title:
        # Auto-generate from git
        base = args.base or creator.get_base_branch()
        commits = creator.get_commits_since_base(base)

        if not commits:
            print("Error: No commits found to create PR from", file=sys.stderr)
            sys.exit(1)

        # Warn about potential cross-contamination
        creator.warn_if_many_commits(base)

        if not title:
            # Use first commit message as title
            first_commit = commits[0]
            # Remove commit hash prefix if present
            if " " in first_commit:
                title = first_commit.split(" ", 1)[1]
            else:
                title = first_commit

        body = creator.generate_pr_body(commits, body)

    if not title:
        print("Error: PR title required. Use --title or --auto", file=sys.stderr)
        sys.exit(1)

    # Create the PR
    result = creator.create_pr(
        title=title, body=body, base=args.base, reviewer=args.reviewer, draft=args.draft
    )

    # Create notification
    if not args.no_notify:
        creator.create_notification(result, args.context or "")

    # Output result
    if result["success"]:
        print("\nPR created successfully!")
        print(f"URL: {result['url']}")
        sys.exit(0)
    else:
        print(f"\nFailed to create PR: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
