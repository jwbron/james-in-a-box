"""
Tests for the notifications base module (NotificationService abstract class).
"""

import pytest
from unittest.mock import MagicMock, patch

from notifications.base import NotificationService
from notifications.types import (
    NotificationType,
    NotificationContext,
    NotificationMessage,
    NotificationResult,
)


class ConcreteNotificationService(NotificationService):
    """Concrete implementation for testing the abstract base class."""

    def __init__(self):
        self.sent_messages = []
        self.replies = []

    def send(self, message: NotificationMessage) -> NotificationResult:
        """Track sent messages and return success."""
        self.sent_messages.append(message)
        return NotificationResult(
            success=True,
            thread_id=message.context.task_id or "generated-id",
            message_id="msg-123",
        )

    def reply(self, thread_id: str, message: NotificationMessage) -> NotificationResult:
        """Track replies and return success."""
        self.replies.append((thread_id, message))
        return NotificationResult(
            success=True,
            thread_id=thread_id,
            message_id="reply-456",
        )


class FailingNotificationService(NotificationService):
    """Implementation that always fails."""

    def send(self, message: NotificationMessage) -> NotificationResult:
        return NotificationResult(success=False, error_message="Send failed")

    def reply(self, thread_id: str, message: NotificationMessage) -> NotificationResult:
        return NotificationResult(success=False, error_message="Reply failed")


class TestNotificationServiceAbstract:
    """Tests for abstract base class behavior."""

    def test_cannot_instantiate_abstract(self):
        """Test that NotificationService cannot be instantiated directly."""
        with pytest.raises(TypeError):
            NotificationService()

    def test_must_implement_send(self):
        """Test that subclasses must implement send()."""

        class PartialImplementation(NotificationService):
            def reply(self, thread_id, message):
                return NotificationResult(success=True)

        with pytest.raises(TypeError):
            PartialImplementation()

    def test_must_implement_reply(self):
        """Test that subclasses must implement reply()."""

        class PartialImplementation(NotificationService):
            def send(self, message):
                return NotificationResult(success=True)

        with pytest.raises(TypeError):
            PartialImplementation()


class TestNotify:
    """Tests for the notify() convenience method."""

    def test_notify_simple(self):
        """Test simple notification."""
        service = ConcreteNotificationService()
        result = service.notify("Test Title", "Test body")

        assert result.success is True
        assert len(service.sent_messages) == 1

        msg = service.sent_messages[0]
        assert msg.title == "Test Title"
        assert msg.body == "Test body"
        assert msg.notification_type == NotificationType.INFO

    def test_notify_with_context(self):
        """Test notification with context."""
        service = ConcreteNotificationService()
        ctx = NotificationContext(task_id="task-123", repository="owner/repo")

        result = service.notify("Title", "Body", context=ctx)

        assert result.success is True
        assert result.thread_id == "task-123"

        msg = service.sent_messages[0]
        assert msg.context.task_id == "task-123"
        assert msg.context.repository == "owner/repo"

    def test_notify_with_notification_type(self):
        """Test notification with explicit type."""
        service = ConcreteNotificationService()

        result = service.notify(
            "Error",
            "Something failed",
            notification_type=NotificationType.ERROR,
        )

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.notification_type == NotificationType.ERROR

    def test_notify_creates_default_context(self):
        """Test that notify creates a default context if none provided."""
        service = ConcreteNotificationService()
        service.notify("Title", "Body")

        msg = service.sent_messages[0]
        assert msg.context is not None
        assert isinstance(msg.context, NotificationContext)


class TestNotifySuccess:
    """Tests for the notify_success() method."""

    def test_notify_success(self):
        """Test success notification."""
        service = ConcreteNotificationService()
        result = service.notify_success("Success!", "Task completed")

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.notification_type == NotificationType.SUCCESS

    def test_notify_success_with_context(self):
        """Test success notification with context."""
        service = ConcreteNotificationService()
        ctx = NotificationContext(task_id="success-task")

        result = service.notify_success("Done", "All good", context=ctx)

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.context.task_id == "success-task"


class TestNotifyError:
    """Tests for the notify_error() method."""

    def test_notify_error(self):
        """Test error notification."""
        service = ConcreteNotificationService()
        result = service.notify_error("Error!", "Something went wrong")

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.notification_type == NotificationType.ERROR

    def test_notify_error_with_context(self):
        """Test error notification with context."""
        service = ConcreteNotificationService()
        ctx = NotificationContext(task_id="error-task", pr_number=42)

        result = service.notify_error("Failed", "Build failed", context=ctx)

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.context.task_id == "error-task"
        assert msg.context.pr_number == 42


class TestNotifyWarning:
    """Tests for the notify_warning() method."""

    def test_notify_warning(self):
        """Test warning notification."""
        service = ConcreteNotificationService()
        result = service.notify_warning("Warning!", "Potential issue")

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.notification_type == NotificationType.WARNING

    def test_notify_warning_with_context(self):
        """Test warning notification with context."""
        service = ConcreteNotificationService()
        ctx = NotificationContext(branch="main")

        result = service.notify_warning("Heads up", "Deprecated usage", context=ctx)

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.context.branch == "main"


class TestNotifyActionRequired:
    """Tests for the notify_action_required() method."""

    def test_notify_action_required(self):
        """Test action required notification."""
        service = ConcreteNotificationService()
        result = service.notify_action_required("Review Needed", "Please review PR")

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.notification_type == NotificationType.ACTION_REQUIRED

    def test_notify_action_required_with_context(self):
        """Test action required notification with context."""
        service = ConcreteNotificationService()
        ctx = NotificationContext(pr_number=123, repository="owner/repo")

        result = service.notify_action_required(
            "Approval Needed",
            "PR needs approval",
            context=ctx,
        )

        assert result.success is True
        msg = service.sent_messages[0]
        assert msg.context.pr_number == 123
        assert msg.context.repository == "owner/repo"


class TestFailingService:
    """Tests for handling service failures."""

    def test_notify_failure_propagates(self):
        """Test that failures are properly propagated."""
        service = FailingNotificationService()
        result = service.notify("Title", "Body")

        assert result.success is False
        assert result.error_message == "Send failed"

    def test_convenience_methods_propagate_failure(self):
        """Test that convenience methods propagate failures."""
        service = FailingNotificationService()

        success_result = service.notify_success("Title", "Body")
        assert success_result.success is False

        error_result = service.notify_error("Title", "Body")
        assert error_result.success is False

        warning_result = service.notify_warning("Title", "Body")
        assert warning_result.success is False

        action_result = service.notify_action_required("Title", "Body")
        assert action_result.success is False
