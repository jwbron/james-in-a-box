"""
Slack notification service implementation.

Uses file-based communication with the host-side Slack notifier.
Notifications are written as markdown files to ~/sharing/notifications/
which are picked up by the host-side service and sent to Slack.

Threading:
- New messages get a unique task_id in the filename
- The host-side notifier stores thread_ts mappings
- Replies include thread_ts in YAML frontmatter
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from .base import NotificationService
from .types import (
    NotificationContext,
    NotificationMessage,
    NotificationResult,
)


class SlackNotificationService(NotificationService):
    """Slack notification service using file-based communication.

    This implementation writes notification files to a shared directory
    that is monitored by the host-side Slack notifier service.

    File format:
        - YAML frontmatter for metadata (thread_ts, task_id)
        - Markdown body for message content

    Threading:
        - Each notification gets a task_id (from context or auto-generated)
        - Host-side notifier maintains task_id -> thread_ts mapping
        - Replies include thread_ts in frontmatter to thread correctly

    Usage:
        slack = SlackNotificationService()

        # Send a new message
        result = slack.notify("PR Created", "Details here...")

        # Reply in existing thread
        slack.reply(thread_id, "Follow-up message")

        # Or use context for automatic threading
        ctx = NotificationContext(task_id="my-task-123")
        slack.notify("Update", "More info", context=ctx)
    """

    def __init__(
        self,
        notifications_dir: Path | None = None,
        threads_file: Path | None = None,
    ):
        """Initialize the Slack notification service.

        Args:
            notifications_dir: Directory to write notification files.
                Defaults to ~/sharing/notifications/
            threads_file: File storing task_id -> thread_ts mappings.
                Defaults to ~/sharing/tracking/slack-threads.json
        """
        self.notifications_dir = notifications_dir or (Path.home() / "sharing" / "notifications")
        self.threads_file = threads_file or (
            Path.home() / "sharing" / "tracking" / "slack-threads.json"
        )

        # Ensure directories exist
        self.notifications_dir.mkdir(parents=True, exist_ok=True)
        self.threads_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_threads(self) -> dict:
        """Load thread mappings from file."""
        if self.threads_file.exists():
            try:
                with self.threads_file.open() as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save_threads(self, threads: dict):
        """Save thread mappings to file."""
        try:
            with self.threads_file.open("w") as f:
                json.dump(threads, f, indent=2)
        except OSError as e:
            print(f"Warning: Could not save thread mappings: {e}")

    def _get_thread_ts(self, task_id: str) -> str | None:
        """Look up thread_ts for a task_id."""
        threads = self._load_threads()
        return threads.get(task_id)

    def _generate_task_id(self, context: NotificationContext) -> str:
        """Generate a unique task ID for a notification.

        Uses context info if available, otherwise generates a UUID-based ID.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Build descriptive prefix from context
        parts = []
        if context.source:
            parts.append(context.source)
        if context.repository:
            # Use short repo name
            parts.append(context.repository.split("/")[-1])
        if context.pr_number:
            parts.append(f"pr{context.pr_number}")

        if parts:
            prefix = "-".join(parts)
            return f"{prefix}-{timestamp}"
        else:
            # Fallback to generic task ID
            short_uuid = uuid.uuid4().hex[:8]
            return f"task-{timestamp}-{short_uuid}"

    def _build_frontmatter(self, task_id: str, thread_ts: str | None = None) -> str:
        """Build YAML frontmatter for the notification file."""
        lines = ["---"]
        lines.append(f'task_id: "{task_id}"')
        if thread_ts:
            lines.append(f'thread_ts: "{thread_ts}"')
        lines.append("---")
        return "\n".join(lines)

    def _write_notification(
        self,
        task_id: str,
        content: str,
        thread_ts: str | None = None,
        suffix: str = "",
    ) -> Path:
        """Write a notification file.

        Args:
            task_id: Unique task identifier for threading.
            content: Markdown content of the notification.
            thread_ts: Optional Slack thread_ts for replying.
            suffix: Optional suffix for the filename.

        Returns:
            Path to the written file.
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Build filename
        filename_parts = [timestamp, task_id]
        if suffix:
            filename_parts.append(suffix)
        filename = "-".join(filename_parts) + ".md"

        filepath = self.notifications_dir / filename

        # Build file content with frontmatter
        frontmatter = self._build_frontmatter(task_id, thread_ts)
        full_content = f"{frontmatter}\n\n{content}"

        filepath.write_text(full_content)
        return filepath

    def send(self, message: NotificationMessage) -> NotificationResult:
        """Send a notification to Slack.

        Args:
            message: The notification message to send.

        Returns:
            NotificationResult with the task_id for threading.
        """
        context = message.context

        # Determine task_id
        task_id = context.task_id or self._generate_task_id(context)

        # Check if we should thread (existing thread for this task)
        thread_ts = context.thread_id or self._get_thread_ts(task_id)

        # Render message content
        content = message.to_markdown()

        try:
            filepath = self._write_notification(
                task_id=task_id,
                content=content,
                thread_ts=thread_ts,
            )

            print(f"  Notification written: {filepath.name}")

            return NotificationResult(
                success=True,
                thread_id=task_id,  # Use task_id for follow-up
                message_id=filepath.name,
                data={"filepath": str(filepath)},
            )

        except Exception as e:
            return NotificationResult(
                success=False,
                error_message=str(e),
            )

    def reply(self, thread_id: str, message: NotificationMessage) -> NotificationResult:
        """Reply in an existing Slack thread.

        Args:
            thread_id: The task_id or thread_ts to reply to.
            message: The notification message to send.

        Returns:
            NotificationResult with success status.
        """
        # Look up the actual Slack thread_ts
        thread_ts = self._get_thread_ts(thread_id)

        # If no mapping found, thread_id might be the actual thread_ts
        # (from frontmatter or direct specification)
        if not thread_ts and thread_id.startswith("1"):  # Slack ts format
            thread_ts = thread_id

        # Update message context
        message.context.task_id = thread_id
        message.context.thread_id = thread_ts

        # Render message content
        content = message.to_markdown()

        try:
            filepath = self._write_notification(
                task_id=thread_id,
                content=content,
                thread_ts=thread_ts,
                suffix="reply",
            )

            print(f"  Reply notification written: {filepath.name}")

            return NotificationResult(
                success=True,
                thread_id=thread_id,
                message_id=filepath.name,
                data={"filepath": str(filepath)},
            )

        except Exception as e:
            return NotificationResult(
                success=False,
                error_message=str(e),
            )

    # GitHub-specific convenience methods

    def notify_pr_comment(
        self,
        pr_number: int,
        repo: str,
        comment_author: str,
        comment_body: str,
        response_text: str,
        pushed_branch: str | None = None,
        new_pr_url: str | None = None,
        task_id: str | None = None,
    ) -> NotificationResult:
        """Notify about a PR comment response.

        Args:
            pr_number: The PR number.
            repo: Repository name (e.g., "owner/repo").
            comment_author: Who made the original comment.
            comment_body: The original comment text.
            response_text: jib's response.
            pushed_branch: Branch where code was pushed (if any).
            new_pr_url: URL of new PR created (if any).
            task_id: Optional task ID for threading.

        Returns:
            NotificationResult with success status.
        """
        # Build action summary
        actions = ["Posted comment on PR"]
        if pushed_branch:
            actions.append(f"Pushed code to `{pushed_branch}`")
        if new_pr_url:
            actions.append(f"Created new PR: {new_pr_url}")

        actions_text = "\n".join(f"- {a}" for a in actions)

        # Truncate for readability
        comment_preview = comment_body[:300] + "..." if len(comment_body) > 300 else comment_body
        response_preview = (
            response_text[:500] + "..." if len(response_text) > 500 else response_text
        )

        body = f"""**Repository**: {repo}
**Triggered by**: Comment from {comment_author}

## Actions Taken

{actions_text}

## Original Comment

> {comment_preview}

## Response Posted

{response_preview}"""

        context = NotificationContext(
            task_id=task_id or f"pr-comment-{repo.split('/')[-1]}-{pr_number}",
            source="comment-responder",
            repository=repo,
            pr_number=pr_number,
            branch=pushed_branch,
        )

        return self.notify_success(
            title=f"GitHub Action: PR #{pr_number}",
            body=body,
            context=context,
        )

    def notify_pr_created(
        self,
        pr_url: str,
        title: str,
        branch: str,
        base_branch: str,
        repo: str,
        reviewer: str | None = None,
    ) -> NotificationResult:
        """Notify about a new PR being created.

        Args:
            pr_url: URL of the created PR.
            title: PR title.
            branch: Source branch.
            base_branch: Target branch.
            repo: Repository name.
            reviewer: Requested reviewer (if any).

        Returns:
            NotificationResult with success status.
        """
        body = f"""**URL**: {pr_url}
**Branch**: `{branch}` -> `{base_branch}`
**Title**: {title}"""

        if reviewer:
            body += f"\n**Reviewer**: @{reviewer}"

        context = NotificationContext(
            task_id=f"pr-created-{repo.split('/')[-1]}-{branch}",
            source="create-pr-helper",
            repository=repo,
            branch=branch,
        )

        return self.notify_success(
            title="Pull Request Created",
            body=body,
            context=context,
        )

    def notify_code_pushed(
        self,
        branch: str,
        repo: str,
        commit_message: str,
        pr_number: int | None = None,
    ) -> NotificationResult:
        """Notify about code being pushed to a branch.

        Args:
            branch: Branch name.
            repo: Repository name.
            commit_message: The commit message.
            pr_number: Related PR number (if any).

        Returns:
            NotificationResult with success status.
        """
        body = f"""**Repository**: {repo}
**Branch**: `{branch}`

## Commit

{commit_message}"""

        if pr_number:
            body += f"\n\n**Related PR**: #{pr_number}"

        context = NotificationContext(
            source="code-push",
            repository=repo,
            branch=branch,
            pr_number=pr_number,
        )

        return self.notify_success(
            title=f"Code Pushed to {branch}",
            body=body,
            context=context,
        )


# Singleton instance for easy import
_default_instance: SlackNotificationService | None = None


def get_slack_service() -> SlackNotificationService:
    """Get the default Slack notification service instance."""
    global _default_instance
    if _default_instance is None:
        _default_instance = SlackNotificationService()
    return _default_instance
