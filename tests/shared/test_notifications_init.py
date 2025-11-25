"""
Tests for the notifications module init and convenience functions.
"""

import pytest

from notifications import (
    # Types
    NotificationType,
    NotificationChannel,
    NotificationContext,
    NotificationMessage,
    NotificationResult,
    # Base class
    NotificationService,
    # Slack implementation
    SlackNotificationService,
    get_slack_service,
    # Convenience functions
    slack_notify,
)


class TestModuleExports:
    """Test that all expected items are exported from the module."""

    def test_exports_notification_type(self):
        assert NotificationType is not None
        assert hasattr(NotificationType, "INFO")

    def test_exports_notification_channel(self):
        assert NotificationChannel is not None
        assert hasattr(NotificationChannel, "SLACK_DM")

    def test_exports_notification_context(self):
        assert NotificationContext is not None
        ctx = NotificationContext()
        assert hasattr(ctx, "task_id")

    def test_exports_notification_message(self):
        assert NotificationMessage is not None
        msg = NotificationMessage(title="Test", body="Body")
        assert hasattr(msg, "to_markdown")

    def test_exports_notification_result(self):
        assert NotificationResult is not None
        result = NotificationResult(success=True)
        assert hasattr(result, "success")

    def test_exports_notification_service(self):
        assert NotificationService is not None

    def test_exports_slack_notification_service(self):
        assert SlackNotificationService is not None

    def test_exports_get_slack_service(self):
        assert callable(get_slack_service)

    def test_exports_slack_notify(self):
        assert callable(slack_notify)


class TestSlackNotifyConvenience:
    """Test the slack_notify convenience function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset the singleton before each test."""
        import notifications.slack as slack_module
        slack_module._default_instance = None
        yield
        slack_module._default_instance = None

    def test_slack_notify_simple(self, mock_home, notifications_dir):
        """Test simple notification via convenience function."""
        result = slack_notify("Test Title", "Test body")

        assert result.success is True
        assert result.thread_id is not None

        files = list(notifications_dir.glob("*.md"))
        assert len(files) == 1

    def test_slack_notify_with_context(self, mock_home, notifications_dir):
        """Test notification with context."""
        ctx = NotificationContext(
            task_id="my-task",
            repository="owner/repo",
        )
        result = slack_notify("Title", "Body", context=ctx)

        assert result.success is True
        assert result.thread_id == "my-task"

    def test_slack_notify_with_type(self, mock_home, notifications_dir):
        """Test notification with specific type."""
        result = slack_notify(
            "Error",
            "Something failed",
            notification_type=NotificationType.ERROR,
        )

        assert result.success is True

        files = list(notifications_dir.glob("*.md"))
        content = files[0].read_text()
        assert "Error" in content
