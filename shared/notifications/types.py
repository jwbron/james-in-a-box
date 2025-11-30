"""
Notification types and data structures.

This module defines the core data types used throughout the notifications system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class NotificationType(Enum):
    """Type/priority of notification for display styling."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    ACTION_REQUIRED = "action_required"


class NotificationChannel(Enum):
    """Where the notification should be sent."""

    SLACK_DM = "slack_dm"  # Direct message to user
    SLACK_THREAD = "slack_thread"  # Reply in existing thread
    # Future channels:
    # EMAIL = "email"
    # WEBHOOK = "webhook"
    # GITHUB_COMMENT = "github_comment"


@dataclass
class NotificationContext:
    """Context about what triggered the notification.

    This helps maintain conversation/task continuity across notifications.
    """

    # Task correlation
    task_id: str | None = None  # Beads task ID or auto-generated
    thread_id: str | None = None  # Slack thread_ts for threading

    # Source context
    source: str | None = None  # What component sent this (e.g., "comment-responder")
    repository: str | None = None  # GitHub repo (e.g., "owner/repo-name")
    pr_number: int | None = None  # PR number if applicable
    branch: str | None = None  # Git branch if applicable

    # Workflow context
    workflow_id: str | None = None  # Unique identifier for the workflow/job
    workflow_type: str | None = None  # Type of workflow (e.g., 'check_failure', 'comment')

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationMessage:
    """A notification message to be sent.

    This is the primary data structure for all notifications.
    """

    # Required fields
    title: str  # Short title/subject
    body: str  # Main message content (markdown supported)

    # Classification
    notification_type: NotificationType = NotificationType.INFO

    # Context for threading and correlation
    context: NotificationContext = field(default_factory=NotificationContext)

    # Timestamp (auto-generated if not provided)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """Render the notification as markdown."""
        type_emoji = {
            NotificationType.INFO: "",
            NotificationType.SUCCESS: "",
            NotificationType.WARNING: "",
            NotificationType.ERROR: "",
            NotificationType.ACTION_REQUIRED: "",
        }
        emoji = type_emoji.get(self.notification_type, "")

        lines = [f"# {emoji} {self.title}".strip()]
        lines.append("")
        lines.append(self.body)

        # Add context footer if we have useful info
        footer_parts = []
        if self.context.repository:
            footer_parts.append(f"Repo: {self.context.repository}")
        if self.context.pr_number:
            footer_parts.append(f"PR: #{self.context.pr_number}")
        if self.context.branch:
            footer_parts.append(f"Branch: `{self.context.branch}`")
        if self.context.source:
            footer_parts.append(f"Source: {self.context.source}")

        # Add workflow context footer (smaller font, less prominent)
        workflow_parts = []
        if self.context.workflow_type:
            workflow_parts.append(f"Workflow: {self.context.workflow_type}")
        if self.context.workflow_id:
            workflow_parts.append(f"ID: `{self.context.workflow_id}`")

        if footer_parts:
            lines.append("")
            lines.append("---")
            lines.append(" | ".join(footer_parts))

        if workflow_parts:
            lines.append("")
            lines.append(f"_({' | '.join(workflow_parts)})_")

        return "\n".join(lines)


@dataclass
class NotificationResult:
    """Result of sending a notification.

    Contains status and any identifiers needed for follow-up (threading, etc).
    """

    success: bool
    error_message: str | None = None

    # Identifiers for follow-up
    thread_id: str | None = None  # Thread ID for replies
    message_id: str | None = None  # Unique message identifier

    # Additional response data
    data: dict[str, Any] = field(default_factory=dict)
