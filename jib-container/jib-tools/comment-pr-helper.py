#!/usr/bin/env python3
"""
PR Comment Helper - Adds comments to GitHub PRs with Slack notification.

Used by jib to:
1. Post comments on GitHub PRs consistently
2. Send Slack notifications about comments posted
3. Maintain threading context for related notifications
4. For non-writable repos: send Slack notification instead of GitHub comment

Usage:
  comment-pr-helper.py --pr 123 --body "Comment text"
  comment-pr-helper.py --pr 123 --body-file comment.md
  comment-pr-helper.py --pr 123 --body "Comment" --no-notify
  comment-pr-helper.py --pr 123 --body "Comment" --task-id my-task-123

The comment body is always signed with "-- Authored by jib" unless --no-sign is used.

For repositories without write access, the helper will automatically send a
Slack notification with the comment content instead of posting to GitHub.
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any


# Add shared directory to path for notifications import
# Path: jib-container/jib-tools/comment-pr-helper.py -> repo-root/shared
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from notifications import NotificationContext, get_slack_service


# Try to load repo config for writable repos check
try:
    config_paths = [
        Path(__file__).parent.parent.parent / "config",  # From scripts dir
        Path.home() / "khan" / "james-in-a-box" / "config",  # From container
    ]
    for config_path in config_paths:
        if (config_path / "repo_config.py").exists():
            sys.path.insert(0, str(config_path.parent))
            break
    from config.repo_config import is_writable_repo

    HAS_REPO_CONFIG = True
except ImportError:
    HAS_REPO_CONFIG = False

    def is_writable_repo(repo):
        return True  # Allow by default if config unavailable


class PRCommenter:
    def __init__(self):
        self.repo_root = self.find_repo_root()
        self.slack = get_slack_service()

    def find_repo_root(self) -> Path | None:
        """Find the git repository root."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
            )
            return Path(result.stdout.strip())
        except subprocess.CalledProcessError:
            return None

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

    def check_writable(self) -> tuple:
        """Check if current repo is in the writable repos list.

        Returns:
            (is_writable, repo_name) - Whether repo is writable and its name
        """
        repo_name = self.get_repo_name()
        if not repo_name:
            return False, "unknown"
        return is_writable_repo(repo_name), repo_name

    def get_pr_info(self, pr_number: int) -> dict[str, Any] | None:
        """Get information about a PR."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "--json",
                    "number,title,url,author,headRefName,baseRefName",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            import json

            return json.loads(result.stdout)
        except subprocess.CalledProcessError:
            return None

    def add_signature(self, body: str) -> str:
        """Add jib signature to comment body if not already present."""
        signature = "\n\n---\n*-- Authored by jib*"
        if "-- Authored by jib" in body or "-- jib" in body:
            return body
        return body + signature

    def post_comment(self, pr_number: int, body: str, sign: bool = True) -> dict[str, Any]:
        """Post a comment on a PR using gh CLI.

        Args:
            pr_number: The PR number to comment on.
            body: The comment body (markdown supported).
            sign: Whether to add jib signature.

        Returns:
            Dict with success status and comment details.
        """
        if sign:
            body = self.add_signature(body)

        print(f"Posting comment on PR #{pr_number}...")

        result = subprocess.run(
            ["gh", "pr", "comment", str(pr_number), "--body", body],
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            return {"success": False, "error": error_msg}

        # gh pr comment outputs the comment URL on success
        comment_url = result.stdout.strip()

        return {"success": True, "pr_number": pr_number, "comment_url": comment_url, "body": body}

    def create_notification(
        self,
        result: dict[str, Any],
        pr_info: dict[str, Any] | None = None,
        task_id: str | None = None,
    ):
        """Create Slack notification about the comment."""
        repo_name = self.get_repo_name() or "unknown"
        pr_number = result.get("pr_number", "?")

        if result["success"]:
            # Build notification body
            body_parts = [
                f"**Repository**: {repo_name}",
                f"**PR**: #{pr_number}",
            ]

            if pr_info:
                body_parts.append(f"**PR Title**: {pr_info.get('title', 'Unknown')}")
                body_parts.append(
                    f"**Branch**: `{pr_info.get('headRefName', '?')}` -> `{pr_info.get('baseRefName', '?')}`"
                )

            if result.get("comment_url"):
                body_parts.append(f"**Comment URL**: {result['comment_url']}")

            # Add preview of comment (truncated)
            comment_body = result.get("body", "")
            preview = comment_body[:500] + "..." if len(comment_body) > 500 else comment_body
            body_parts.append(f"\n## Comment Posted\n\n{preview}")

            context = NotificationContext(
                task_id=task_id,
                source="comment-pr-helper",
                repository=repo_name,
                pr_number=pr_number,
            )

            self.slack.notify_success(
                title=f"Comment Posted on PR #{pr_number}",
                body="\n".join(body_parts),
                context=context,
            )
        else:
            self.slack.notify_error(
                title=f"Failed to Comment on PR #{pr_number}",
                body=f"**Error**: {result.get('error', 'Unknown error')}",
                context=NotificationContext(
                    task_id=task_id,
                    source="comment-pr-helper",
                    repository=repo_name,
                    pr_number=pr_number,
                ),
            )

    def send_slack_only_notification(
        self,
        pr_number: int,
        body: str,
        pr_info: dict[str, Any] | None = None,
        task_id: str | None = None,
    ):
        """Send Slack notification for non-writable repos (instead of GitHub comment)."""
        repo_name = self.get_repo_name() or "unknown"

        # Build notification body
        body_parts = [
            f"**Repository**: {repo_name} (read-only - cannot post GitHub comment)",
            f"**PR**: #{pr_number}",
        ]

        if pr_info:
            body_parts.append(f"**PR Title**: {pr_info.get('title', 'Unknown')}")
            body_parts.append(
                f"**Branch**: `{pr_info.get('headRefName', '?')}` -> `{pr_info.get('baseRefName', '?')}`"
            )
            if pr_info.get("url"):
                body_parts.append(f"**PR URL**: {pr_info['url']}")

        # Add the full comment
        body_parts.append(f"\n## Comment (not posted to GitHub)\n\n{body}")
        body_parts.append("\n---\n*Please post this comment manually on the PR if needed.*")

        context = NotificationContext(
            task_id=task_id,
            source="comment-pr-helper",
            repository=repo_name,
            pr_number=pr_number,
        )

        self.slack.notify_action_required(
            title=f"Comment Ready for PR #{pr_number}",
            body="\n".join(body_parts),
            context=context,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Add comments to GitHub PRs with Slack notification"
    )
    parser.add_argument("--pr", "-p", type=int, required=True, help="PR number to comment on")
    parser.add_argument("--body", "-b", help="Comment body (markdown supported)")
    parser.add_argument("--body-file", "-f", help="Read comment body from file")
    parser.add_argument("--no-notify", action="store_true", help="Skip sending Slack notification")
    parser.add_argument("--no-sign", action="store_true", help="Don't add jib signature to comment")
    parser.add_argument("--task-id", "-t", help="Task ID for Slack thread correlation")

    args = parser.parse_args()

    # Validate we have a comment body
    if not args.body and not args.body_file:
        print("Error: Must provide --body or --body-file", file=sys.stderr)
        sys.exit(1)

    # Get comment body
    if args.body_file:
        try:
            body = Path(args.body_file).read_text()
        except Exception as e:
            print(f"Error reading body file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        body = args.body

    commenter = PRCommenter()

    if not commenter.repo_root:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    # Check if this repo is in the writable repos list
    is_writable, repo_name = commenter.check_writable()

    # Get PR info for richer notification
    pr_info = commenter.get_pr_info(args.pr)

    # For non-writable repos, send Slack notification instead of posting to GitHub
    if not is_writable:
        print(f"Note: Repository '{repo_name}' is not in the writable repos list.")
        print("Sending Slack notification with comment content instead of posting to GitHub.")
        print()

        # Add signature if requested
        comment_body = body
        if not args.no_sign:
            comment_body = commenter.add_signature(body)

        commenter.send_slack_only_notification(
            pr_number=args.pr, body=comment_body, pr_info=pr_info, task_id=args.task_id
        )

        print("\nSlack notification sent!")
        print(f"Comment content ready for manual posting on PR #{args.pr}")
        sys.exit(0)

    # Post the comment (for writable repos)
    result = commenter.post_comment(pr_number=args.pr, body=body, sign=not args.no_sign)

    # Send notification
    if not args.no_notify:
        commenter.create_notification(result=result, pr_info=pr_info, task_id=args.task_id)

    # Output result
    if result["success"]:
        print("\nComment posted successfully!")
        if result.get("comment_url"):
            print(f"URL: {result['comment_url']}")
        sys.exit(0)
    else:
        print(f"\nFailed to post comment: {result['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
