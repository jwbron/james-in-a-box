"""
Notification types and data structures.

This module defines the core data types used throughout the notifications system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class NotificationType(Enum):
    """Type/priority of notification for display styling."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    ACTION_REQUIRED = "action_required"


class NotificationChannel(Enum):
    """Where the notification should be sent."""
    SLACK_DM = "slack_dm"           # Direct message to user
    SLACK_THREAD = "slack_thread"   # Reply in existing thread
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
    task_id: Optional[str] = None           # Beads task ID or auto-generated
    thread_id: Optional[str] = None         # Slack thread_ts for threading

    # Source context
    source: Optional[str] = None            # What component sent this (e.g., "comment-responder")
    repository: Optional[str] = None        # GitHub repo (e.g., "jwbron/james-in-a-box")
    pr_number: Optional[int] = None         # PR number if applicable
    branch: Optional[str] = None            # Git branch if applicable

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationMessage:
    """A notification message to be sent.

    This is the primary data structure for all notifications.
    """
    # Required fields
    title: str                              # Short title/subject
    body: str                               # Main message content (markdown supported)

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

        if footer_parts:
            lines.append("")
            lines.append("---")
            lines.append(" | ".join(footer_parts))

        return "\n".join(lines)


@dataclass
class NotificationResult:
    """Result of sending a notification.

    Contains status and any identifiers needed for follow-up (threading, etc).
    """
    success: bool
    error_message: Optional[str] = None

    # Identifiers for follow-up
    thread_id: Optional[str] = None         # Thread ID for replies
    message_id: Optional[str] = None        # Unique message identifier

    # Additional response data
    data: Dict[str, Any] = field(default_factory=dict)
