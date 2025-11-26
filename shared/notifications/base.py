"""
Abstract base class for notification services.

All notification implementations must inherit from NotificationService
and implement its abstract methods.
"""

from abc import ABC, abstractmethod

from .types import NotificationContext, NotificationMessage, NotificationResult


class NotificationService(ABC):
    """Abstract base class for notification services.

    Provides a consistent interface for sending notifications across
    different channels (Slack, email, webhooks, etc.).

    Usage:
        service = SlackNotificationService()

        # Send a simple notification
        result = service.notify("Title", "Message body")

        # Send with context for threading
        result = service.notify(
            "Title",
            "Body",
            context=NotificationContext(task_id="task-123")
        )

        # Reply in existing thread
        result = service.reply(thread_id, "Follow-up message")
    """

    @abstractmethod
    def send(self, message: NotificationMessage) -> NotificationResult:
        """Send a notification message.

        Args:
            message: The notification message to send.

        Returns:
            NotificationResult with success status and any identifiers.
        """

    @abstractmethod
    def reply(self, thread_id: str, message: NotificationMessage) -> NotificationResult:
        """Reply in an existing thread/conversation.

        Args:
            thread_id: The thread identifier to reply to.
            message: The notification message to send.

        Returns:
            NotificationResult with success status.
        """

    # Convenience methods with default implementations

    def notify(
        self, title: str, body: str, context: NotificationContext | None = None, **kwargs
    ) -> NotificationResult:
        """Convenience method to send a notification.

        Args:
            title: Notification title.
            body: Notification body (markdown supported).
            context: Optional context for threading/correlation.
            **kwargs: Additional arguments passed to NotificationMessage.

        Returns:
            NotificationResult with success status.
        """
        from .types import NotificationType

        message = NotificationMessage(
            title=title,
            body=body,
            context=context or NotificationContext(),
            notification_type=kwargs.get("notification_type", NotificationType.INFO),
        )
        return self.send(message)

    def notify_success(
        self, title: str, body: str, context: NotificationContext | None = None
    ) -> NotificationResult:
        """Send a success notification."""
        from .types import NotificationType

        return self.notify(title, body, context, notification_type=NotificationType.SUCCESS)

    def notify_error(
        self, title: str, body: str, context: NotificationContext | None = None
    ) -> NotificationResult:
        """Send an error notification."""
        from .types import NotificationType

        return self.notify(title, body, context, notification_type=NotificationType.ERROR)

    def notify_warning(
        self, title: str, body: str, context: NotificationContext | None = None
    ) -> NotificationResult:
        """Send a warning notification."""
        from .types import NotificationType

        return self.notify(title, body, context, notification_type=NotificationType.WARNING)

    def notify_action_required(
        self, title: str, body: str, context: NotificationContext | None = None
    ) -> NotificationResult:
        """Send a notification requiring user action."""
        from .types import NotificationType

        return self.notify(title, body, context, notification_type=NotificationType.ACTION_REQUIRED)
