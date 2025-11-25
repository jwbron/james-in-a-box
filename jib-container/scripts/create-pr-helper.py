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
from datetime import datetime
from typing import Optional, Dict, Any

# Add shared directory to path for notifications import
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
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
    from config.repo_config import get_default_reviewer, is_writable_repo, get_writable_repos
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

    def get_repo_name(self) -> Optional[str]:
        """Get the owner/repo name from git remote origin."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, check=True
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

    def find_repo_root(self) -> Optional[Path]:
        """Find the git repository root"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            return None

    def get_current_branch(self) -> str:
        """Get current git branch name"""
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def get_base_branch(self) -> str:
        """Determine the base branch (main or master)"""
        result = subprocess.run(
            ["git", "remote", "show", "origin"],
            capture_output=True, text=True
        )
        if "HEAD branch: main" in result.stdout:
            return "main"
        return "master"

    def get_commits_since_base(self, base_branch: str) -> list:
        """Get commits on current branch not in base"""
        try:
            result = subprocess.run(
                ["git", "log", f"{base_branch}..HEAD", "--oneline"],
                capture_output=True, text=True, check=True
            )
            return result.stdout.strip().split('\n') if result.stdout.strip() else []
        except subprocess.CalledProcessError:
            return []

    def generate_pr_body(self, commits: list, custom_body: str = "") -> str:
        """Generate PR body from commits and custom description"""
        body_parts = []

        if custom_body:
            body_parts.append("## Summary\n")
            body_parts.append(custom_body)
            body_parts.append("\n")

        if commits:
            body_parts.append("## Changes\n")
            for commit in commits[:10]:  # Limit to 10 commits
                body_parts.append(f"- {commit}\n")
            if len(commits) > 10:
                body_parts.append(f"- ... and {len(commits) - 10} more commits\n")
            body_parts.append("\n")

        body_parts.append("## Test Plan\n")
        body_parts.append("- [ ] Tests pass locally\n")
        body_parts.append("- [ ] Manual verification\n")
        body_parts.append("\n")
        body_parts.append("---\n")
        body_parts.append("*— Authored by jib*\n")

        return "".join(body_parts)

    def push_branch(self, branch: str) -> bool:
        """Push current branch to remote"""
        print(f"Pushing branch {branch} to remote...")
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            capture_output=True, text=True
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
        base: Optional[str] = None,
        reviewer: Optional[str] = None,
        draft: bool = False
    ) -> Dict[str, Any]:
        """Create a PR using gh CLI"""
        branch = self.get_current_branch()
        base_branch = base or self.get_base_branch()

        # Check if branch has been pushed
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch],
            capture_output=True, text=True
        )
        if not result.stdout.strip():
            # Branch not on remote, push it
            if not self.push_branch(branch):
                return {
                    "success": False,
                    "error": "Failed to push branch to remote"
                }

        # Build gh pr create command
        cmd = [
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--base", base_branch
        ]

        if reviewer:
            cmd.extend(["--reviewer", reviewer])

        if draft:
            cmd.append("--draft")

        print(f"Creating PR: {title}")
        print(f"  Branch: {branch} -> {base_branch}")

        result = subprocess.run(cmd, capture_output=True, text=True)

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
                        "base": base_branch
                    }
            return {
                "success": False,
                "error": error_msg
            }

        # Extract PR URL from output
        pr_url = result.stdout.strip()

        return {
            "success": True,
            "url": pr_url,
            "branch": branch,
            "base": base_branch,
            "title": title,
            "reviewer": reviewer
        }

    def get_existing_pr_url(self, branch: str) -> Optional[str]:
        """Get URL of existing PR for branch"""
        result = subprocess.run(
            ["gh", "pr", "view", branch, "--json", "url", "--jq", ".url"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def create_notification(self, pr_result: Dict[str, Any], task_context: str = ""):
        """Create notification about PR creation using the notifications service."""
        repo_name = self.get_repo_name() or "unknown"

        if pr_result["success"]:
            # Include task context in the body if provided
            body_parts = [
                f"**URL**: {pr_result['url']}",
                f"**Branch**: `{pr_result.get('branch', 'unknown')}` -> `{pr_result.get('base', 'main')}`",
                f"**Title**: {pr_result.get('title', 'New PR')}",
            ]

            if pr_result.get('reviewer'):
                body_parts.append(f"**Reviewer**: @{pr_result['reviewer']}")

            if pr_result.get('already_existed'):
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
    parser.add_argument("--reviewer", "-r", default=default_reviewer,
                        help=f"Reviewer to request (default: {default_reviewer}, from config)")
    parser.add_argument("--base", help="Base branch (default: auto-detect main/master)")
    parser.add_argument("--draft", action="store_true", help="Create as draft PR")
    parser.add_argument("--from-file", "-f", help="Read PR details from JSON file")
    parser.add_argument("--auto", "-a", action="store_true", help="Auto-generate title/body from git log")
    parser.add_argument("--no-notify", action="store_true", help="Skip creating notification")
    parser.add_argument("--context", "-c", help="Task context for notification")
    parser.add_argument("--list-writable", action="store_true",
                        help="List repositories where jib has write access")

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
        print(f"Warning: Repository '{repo_name}' is not in the writable repos list.", file=sys.stderr)
        print(f"Writable repos (from config/repositories.yaml):", file=sys.stderr)
        for repo in get_writable_repos():
            print(f"  - {repo}", file=sys.stderr)
        print(f"\nYou can still create the PR, but jib may not have push access.", file=sys.stderr)
        print(f"If the PR creation fails, notify the user to push manually from host.", file=sys.stderr)
        print()

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

        if not title:
            # Use first commit message as title
            first_commit = commits[0]
            # Remove commit hash prefix if present
            if ' ' in first_commit:
                title = first_commit.split(' ', 1)[1]
            else:
                title = first_commit

        body = creator.generate_pr_body(commits, body)

    if not title:
        print("Error: PR title required. Use --title or --auto", file=sys.stderr)
        sys.exit(1)

    # Create the PR
    result = creator.create_pr(
        title=title,
        body=body,
        base=args.base,
        reviewer=args.reviewer,
        draft=args.draft
    )

    # Create notification
    if not args.no_notify:
        creator.create_notification(result, args.context or "")

    # Output result
    if result["success"]:
        print(f"\nPR created successfully!")
        print(f"URL: {result['url']}")
        sys.exit(0)
    else:
        print(f"\nFailed to create PR: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
