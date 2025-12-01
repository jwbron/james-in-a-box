"""
Slack notification utilities for jib container.

This module provides a simple interface to send Slack notifications
by writing markdown files to ~/sharing/notifications/ which are
picked up by the host's notification watcher service.

Usage:
    from notifications import slack_notify, NotificationContext

    # Simple notification
    slack_notify("Task Complete", "Finished implementing feature X")

    # With threading context (for Slack thread replies)
    ctx = NotificationContext(task_id="task-20251201-100411", repository="owner/repo")
    slack_notify("Update", "Fixed the bug", context=ctx)

    # Using the full service
    slack = get_slack_service()
    slack.notify_warning("Security Issue", "Found vulnerability in X")
    slack.notify_action_required("Review Needed", "PR ready for review")
"""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class NotificationContext:
    """Context for threading and tracking notifications."""
    task_id: Optional[str] = None
    thread_ts: Optional[str] = None
    repository: Optional[str] = None
    pr_number: Optional[int] = None
    beads_id: Optional[str] = None


class SlackNotificationService:
    """Service for sending Slack notifications via file-based mechanism."""

    def __init__(self, notifications_dir: Optional[Path] = None):
        self.notifications_dir = notifications_dir or Path.home() / "sharing" / "notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)

    def _generate_filename(self, topic: str) -> str:
        """Generate a unique filename for the notification."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # Sanitize topic for filename
        safe_topic = "".join(c if c.isalnum() or c in "-_" else "-" for c in topic.lower())
        safe_topic = safe_topic[:30]  # Limit length
        return f"{timestamp}-{safe_topic}.md"

    def _build_frontmatter(self, context: Optional[NotificationContext] = None) -> str:
        """Build YAML frontmatter for threading support."""
        if not context:
            return ""

        lines = ["---"]
        if context.task_id:
            lines.append(f'task_id: "{context.task_id}"')
        if context.thread_ts:
            lines.append(f'thread_ts: "{context.thread_ts}"')
        if context.repository:
            lines.append(f'repository: "{context.repository}"')
        if context.pr_number:
            lines.append(f'pr_number: {context.pr_number}')
        if context.beads_id:
            lines.append(f'beads_id: "{context.beads_id}"')
        lines.append("---")

        return "\n".join(lines) + "\n"

    def send(
        self,
        title: str,
        body: str,
        context: Optional[NotificationContext] = None,
        priority: str = "Low",
    ) -> Path:
        """
        Send a notification by writing a markdown file.

        Args:
            title: Notification title (will be the markdown heading)
            body: Notification body content
            context: Optional context for threading
            priority: Priority level (Low, Medium, High, Urgent)

        Returns:
            Path to the created notification file
        """
        frontmatter = self._build_frontmatter(context)

        content = f"""{frontmatter}# {title}

**Priority**: {priority}

{body}

--- Authored by jib
"""

        filename = self._generate_filename(title)
        filepath = self.notifications_dir / filename

        filepath.write_text(content)
        return filepath

    def notify_work_complete(
        self,
        description: str,
        repository: str,
        branch: str,
        commits: int = 1,
        summary: str = "",
        pr_url: Optional[str] = None,
        context: Optional[NotificationContext] = None,
    ) -> Path:
        """Send a work completion notification."""
        body = f"""**Repository**: {repository}
**Branch**: `{branch}`
**Commits**: {commits}

## What Was Done
{summary or description}

## Next Steps
"""
        if pr_url:
            body += f"- [x] PR created: {pr_url}\n"
            body += "- [ ] Human review and merge\n"
        else:
            body += "- [ ] Human review commits on branch\n"
            body += "- [ ] Create PR\n"

        return self.send(
            f"Work Completed: {description}",
            body,
            context=context,
            priority="Low",
        )

    def notify_warning(
        self,
        title: str,
        details: str,
        context: Optional[NotificationContext] = None,
    ) -> Path:
        """Send a warning notification."""
        return self.send(
            f"Warning: {title}",
            details,
            context=context,
            priority="Medium",
        )

    def notify_action_required(
        self,
        title: str,
        details: str,
        options: Optional[list[str]] = None,
        context: Optional[NotificationContext] = None,
    ) -> Path:
        """Send a notification requiring human action."""
        body = details
        if options:
            body += "\n\n## Options\n"
            for opt in options:
                body += f"- [ ] {opt}\n"

        return self.send(
            f"Action Required: {title}",
            body,
            context=context,
            priority="High",
        )

    def notify_blocked(
        self,
        title: str,
        reason: str,
        context: Optional[NotificationContext] = None,
    ) -> Path:
        """Send a notification that work is blocked."""
        return self.send(
            f"Blocked: {title}",
            f"## Reason\n{reason}\n\n## Waiting For\nHuman guidance to proceed.",
            context=context,
            priority="High",
        )

    def notify_error(
        self,
        title: str,
        error_details: str,
        context: Optional[NotificationContext] = None,
    ) -> Path:
        """Send an error notification."""
        return self.send(
            f"Error: {title}",
            f"```\n{error_details}\n```",
            context=context,
            priority="High",
        )


# Module-level singleton
_service: Optional[SlackNotificationService] = None


def get_slack_service() -> SlackNotificationService:
    """Get the singleton Slack notification service."""
    global _service
    if _service is None:
        _service = SlackNotificationService()
    return _service


def slack_notify(
    title: str,
    body: str,
    context: Optional[NotificationContext] = None,
    priority: str = "Low",
) -> Path:
    """
    Send a Slack notification.

    This is a convenience function that uses the singleton service.

    Args:
        title: Notification title
        body: Notification body
        context: Optional context for threading
        priority: Priority level (Low, Medium, High, Urgent)

    Returns:
        Path to the created notification file
    """
    return get_slack_service().send(title, body, context, priority)
