"""
Notifications library for jib.

Provides a unified interface for sending notifications through various channels.
Currently implements Slack via file-based communication with the host.

Usage:
    from lib.notifications import slack_notify, NotificationContext

    # Simple notification
    slack_notify("Title", "Body text")

    # With context for threading
    ctx = NotificationContext(task_id="my-task", repository="owner/repo")
    slack_notify("Title", "Body", context=ctx)

    # GitHub-specific helpers
    from lib.notifications import get_slack_service
    slack = get_slack_service()
    slack.notify_pr_created(url, title, branch, base, repo)
    slack.notify_pr_comment(pr_num, repo, author, comment, response)

Threading:
    - Each notification gets a task_id (auto-generated or from context)
    - The host-side notifier maps task_id -> Slack thread_ts
    - Subsequent notifications with the same task_id reply in the same thread
    - You can also explicitly set thread_id in NotificationContext
"""

from .types import (
    NotificationType,
    NotificationChannel,
    NotificationContext,
    NotificationMessage,
    NotificationResult,
)

from .base import NotificationService

from .slack import (
    SlackNotificationService,
    get_slack_service,
)


# Convenience function for quick notifications
def slack_notify(
    title: str,
    body: str,
    context: NotificationContext = None,
    notification_type: NotificationType = NotificationType.INFO,
) -> NotificationResult:
    """Send a Slack notification.

    This is the simplest way to send a notification:

        from lib.notifications import slack_notify
        slack_notify("PR Created", "Details here...")

    Args:
        title: Notification title.
        body: Notification body (markdown supported).
        context: Optional context for threading/correlation.
        notification_type: Type of notification (info, success, error, etc).

    Returns:
        NotificationResult with success status and thread_id.
    """
    service = get_slack_service()
    return service.notify(
        title=title,
        body=body,
        context=context,
        notification_type=notification_type,
    )


__all__ = [
    # Types
    "NotificationType",
    "NotificationChannel",
    "NotificationContext",
    "NotificationMessage",
    "NotificationResult",
    # Base class
    "NotificationService",
    # Slack implementation
    "SlackNotificationService",
    "get_slack_service",
    # Convenience functions
    "slack_notify",
]
