"""
Tests for the notifications types module.
"""

import pytest
from datetime import datetime

from notifications.types import (
    NotificationType,
    NotificationChannel,
    NotificationContext,
    NotificationMessage,
    NotificationResult,
)


class TestNotificationType:
    """Tests for NotificationType enum."""

    def test_info_type(self):
        assert NotificationType.INFO.value == "info"

    def test_success_type(self):
        assert NotificationType.SUCCESS.value == "success"

    def test_warning_type(self):
        assert NotificationType.WARNING.value == "warning"

    def test_error_type(self):
        assert NotificationType.ERROR.value == "error"

    def test_action_required_type(self):
        assert NotificationType.ACTION_REQUIRED.value == "action_required"


class TestNotificationChannel:
    """Tests for NotificationChannel enum."""

    def test_slack_dm_channel(self):
        assert NotificationChannel.SLACK_DM.value == "slack_dm"

    def test_slack_thread_channel(self):
        assert NotificationChannel.SLACK_THREAD.value == "slack_thread"


class TestNotificationContext:
    """Tests for NotificationContext dataclass."""

    def test_default_context(self):
        ctx = NotificationContext()
        assert ctx.task_id is None
        assert ctx.thread_id is None
        assert ctx.source is None
        assert ctx.repository is None
        assert ctx.pr_number is None
        assert ctx.branch is None
        assert ctx.metadata == {}

    def test_context_with_values(self):
        ctx = NotificationContext(
            task_id="task-123",
            thread_id="1234567890.123456",
            source="test-source",
            repository="owner/repo",
            pr_number=42,
            branch="feature-branch",
            metadata={"custom": "value"},
        )
        assert ctx.task_id == "task-123"
        assert ctx.thread_id == "1234567890.123456"
        assert ctx.source == "test-source"
        assert ctx.repository == "owner/repo"
        assert ctx.pr_number == 42
        assert ctx.branch == "feature-branch"
        assert ctx.metadata == {"custom": "value"}


class TestNotificationMessage:
    """Tests for NotificationMessage dataclass."""

    def test_default_message(self):
        msg = NotificationMessage(title="Test", body="Test body")
        assert msg.title == "Test"
        assert msg.body == "Test body"
        assert msg.notification_type == NotificationType.INFO
        assert isinstance(msg.context, NotificationContext)
        assert isinstance(msg.timestamp, datetime)

    def test_message_with_type(self):
        msg = NotificationMessage(
            title="Error",
            body="Something went wrong",
            notification_type=NotificationType.ERROR,
        )
        assert msg.notification_type == NotificationType.ERROR

    def test_to_markdown_simple(self):
        msg = NotificationMessage(title="Test Title", body="Test body content")
        md = msg.to_markdown()
        assert "Test Title" in md
        assert "Test body content" in md

    def test_to_markdown_with_context(self):
        ctx = NotificationContext(
            repository="owner/repo",
            pr_number=42,
            branch="main",
            source="test",
        )
        msg = NotificationMessage(title="Test", body="Body", context=ctx)
        md = msg.to_markdown()
        assert "Repo: owner/repo" in md
        assert "PR: #42" in md
        assert "Branch: `main`" in md
        assert "Source: test" in md

    def test_to_markdown_no_context_footer_when_empty(self):
        msg = NotificationMessage(title="Test", body="Body")
        md = msg.to_markdown()
        # Should not have a footer when context is empty
        assert "Repo:" not in md
        assert "PR:" not in md


class TestNotificationResult:
    """Tests for NotificationResult dataclass."""

    def test_success_result(self):
        result = NotificationResult(
            success=True,
            thread_id="task-123",
            message_id="msg-456",
        )
        assert result.success is True
        assert result.error_message is None
        assert result.thread_id == "task-123"
        assert result.message_id == "msg-456"
        assert result.data == {}

    def test_failure_result(self):
        result = NotificationResult(
            success=False,
            error_message="Connection failed",
        )
        assert result.success is False
        assert result.error_message == "Connection failed"
        assert result.thread_id is None
        assert result.message_id is None

    def test_result_with_data(self):
        result = NotificationResult(
            success=True,
            data={"filepath": "/path/to/file.md"},
        )
        assert result.data == {"filepath": "/path/to/file.md"}
