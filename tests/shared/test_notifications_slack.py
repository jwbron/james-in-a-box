"""
Tests for the Slack notification service.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from notifications.slack import SlackNotificationService, get_slack_service
from notifications.types import (
    NotificationContext,
    NotificationMessage,
    NotificationType,
)


class TestSlackNotificationService:
    """Tests for SlackNotificationService."""

    def test_init_with_defaults(self, mock_home):
        """Test service initializes with default paths."""
        service = SlackNotificationService()
        assert service.notifications_dir == Path.home() / "sharing" / "notifications"
        assert service.threads_file == Path.home() / "sharing" / "tracking" / "slack-threads.json"

    def test_init_with_custom_paths(self, temp_dir):
        """Test service initializes with custom paths."""
        notifications_dir = temp_dir / "custom" / "notifications"
        threads_file = temp_dir / "custom" / "tracking" / "threads.json"

        notifications_dir.mkdir(parents=True)
        threads_file.parent.mkdir(parents=True, exist_ok=True)

        service = SlackNotificationService(
            notifications_dir=notifications_dir,
            threads_file=threads_file,
        )
        assert service.notifications_dir == notifications_dir
        assert service.threads_file == threads_file

    def test_creates_directories(self, temp_dir):
        """Test that service creates necessary directories."""
        notifications_dir = temp_dir / "new" / "notifications"
        threads_file = temp_dir / "new" / "tracking" / "threads.json"

        # Directories don't exist yet
        assert not notifications_dir.exists()
        assert not threads_file.parent.exists()

        service = SlackNotificationService(
            notifications_dir=notifications_dir,
            threads_file=threads_file,
        )

        # Now they should exist
        assert notifications_dir.exists()
        assert threads_file.parent.exists()


class TestThreadManagement:
    """Tests for thread loading/saving."""

    def test_load_threads_empty(self, mock_home):
        """Test loading threads when file doesn't exist."""
        service = SlackNotificationService()
        threads = service._load_threads()
        assert threads == {}

    def test_load_threads_with_data(self, mock_home):
        """Test loading threads from existing file."""
        service = SlackNotificationService()
        threads_data = {"task-123": "1234567890.123456"}
        service.threads_file.write_text(json.dumps(threads_data))

        threads = service._load_threads()
        assert threads == threads_data

    def test_load_threads_invalid_json(self, mock_home):
        """Test loading threads with invalid JSON."""
        service = SlackNotificationService()
        service.threads_file.write_text("not valid json")

        threads = service._load_threads()
        assert threads == {}

    def test_save_threads(self, mock_home):
        """Test saving thread mappings."""
        service = SlackNotificationService()
        threads = {"task-abc": "1111111111.111111"}
        service._save_threads(threads)

        loaded = json.loads(service.threads_file.read_text())
        assert loaded == threads

    def test_get_thread_ts(self, mock_home):
        """Test getting thread_ts for a task."""
        service = SlackNotificationService()
        threads_data = {"my-task": "9999999999.999999"}
        service.threads_file.write_text(json.dumps(threads_data))

        thread_ts = service._get_thread_ts("my-task")
        assert thread_ts == "9999999999.999999"

    def test_get_thread_ts_not_found(self, mock_home):
        """Test getting thread_ts for unknown task."""
        service = SlackNotificationService()
        thread_ts = service._get_thread_ts("unknown-task")
        assert thread_ts is None


class TestTaskIdGeneration:
    """Tests for task ID generation."""

    def test_generate_task_id_with_source(self, mock_home):
        """Test task ID generation with source context."""
        service = SlackNotificationService()
        ctx = NotificationContext(source="test-source")
        task_id = service._generate_task_id(ctx)
        assert "test-source" in task_id

    def test_generate_task_id_with_repository(self, mock_home):
        """Test task ID generation with repository."""
        service = SlackNotificationService()
        ctx = NotificationContext(repository="owner/my-repo")
        task_id = service._generate_task_id(ctx)
        assert "my-repo" in task_id

    def test_generate_task_id_with_pr_number(self, mock_home):
        """Test task ID generation with PR number."""
        service = SlackNotificationService()
        ctx = NotificationContext(pr_number=42)
        task_id = service._generate_task_id(ctx)
        assert "pr42" in task_id

    def test_generate_task_id_fallback(self, mock_home):
        """Test task ID generation with empty context."""
        service = SlackNotificationService()
        ctx = NotificationContext()
        task_id = service._generate_task_id(ctx)
        assert task_id.startswith("task-")


class TestFrontmatterBuilding:
    """Tests for YAML frontmatter generation."""

    def test_build_frontmatter_basic(self, mock_home):
        """Test basic frontmatter generation."""
        service = SlackNotificationService()
        frontmatter = service._build_frontmatter("task-123")
        assert "---" in frontmatter
        assert 'task_id: "task-123"' in frontmatter

    def test_build_frontmatter_with_thread(self, mock_home):
        """Test frontmatter with thread_ts."""
        service = SlackNotificationService()
        frontmatter = service._build_frontmatter("task-123", "1234567890.123456")
        assert 'thread_ts: "1234567890.123456"' in frontmatter


class TestSendNotification:
    """Tests for sending notifications."""

    def test_send_simple_notification(self, mock_home, notifications_dir):
        """Test sending a simple notification."""
        service = SlackNotificationService()
        message = NotificationMessage(
            title="Test Title",
            body="Test body",
        )

        result = service.send(message)

        assert result.success is True
        assert result.thread_id is not None
        assert result.message_id is not None

        # Check file was created
        files = list(notifications_dir.glob("*.md"))
        assert len(files) == 1

        content = files[0].read_text()
        assert "Test Title" in content
        assert "Test body" in content

    def test_send_with_context(self, mock_home, notifications_dir):
        """Test sending notification with context."""
        service = SlackNotificationService()
        ctx = NotificationContext(
            task_id="my-specific-task",
            source="test",
            repository="owner/repo",
        )
        message = NotificationMessage(
            title="PR Update",
            body="Changes pushed",
            context=ctx,
        )

        result = service.send(message)

        assert result.success is True
        assert result.thread_id == "my-specific-task"

        files = list(notifications_dir.glob("*.md"))
        content = files[0].read_text()
        assert 'task_id: "my-specific-task"' in content

    def test_send_with_notification_type(self, mock_home, notifications_dir):
        """Test sending notification with specific type."""
        service = SlackNotificationService()
        message = NotificationMessage(
            title="Error Occurred",
            body="Something went wrong",
            notification_type=NotificationType.ERROR,
        )

        result = service.send(message)
        assert result.success is True


class TestReplyNotification:
    """Tests for replying to threads."""

    def test_reply_to_thread(self, mock_home, notifications_dir):
        """Test replying to an existing thread."""
        service = SlackNotificationService()

        # Set up existing thread mapping
        threads_data = {"task-123": "1111111111.111111"}
        service.threads_file.write_text(json.dumps(threads_data))

        message = NotificationMessage(
            title="Reply",
            body="This is a follow-up",
        )

        result = service.reply("task-123", message)

        assert result.success is True
        assert result.thread_id == "task-123"

        files = list(notifications_dir.glob("*-reply.md"))
        assert len(files) == 1

        content = files[0].read_text()
        assert 'thread_ts: "1111111111.111111"' in content


class TestConvenienceMethods:
    """Tests for convenience notification methods."""

    def test_notify_pr_comment(self, mock_home, notifications_dir):
        """Test notify_pr_comment method."""
        service = SlackNotificationService()

        result = service.notify_pr_comment(
            pr_number=42,
            repo="owner/my-repo",
            comment_author="test-user",
            comment_body="Please fix the tests",
            response_text="Fixed the tests",
        )

        assert result.success is True

        files = list(notifications_dir.glob("*.md"))
        content = files[0].read_text()
        assert "PR #42" in content
        assert "owner/my-repo" in content
        assert "test-user" in content

    def test_notify_pr_created(self, mock_home, notifications_dir):
        """Test notify_pr_created method."""
        service = SlackNotificationService()

        result = service.notify_pr_created(
            pr_url="https://github.com/owner/repo/pull/1",
            title="Add new feature",
            branch="feature-branch",
            base_branch="main",
            repo="owner/repo",
        )

        assert result.success is True

        files = list(notifications_dir.glob("*.md"))
        content = files[0].read_text()
        assert "Pull Request Created" in content
        assert "feature-branch" in content
        assert "main" in content

    def test_notify_pr_created_with_reviewer(self, mock_home, notifications_dir):
        """Test notify_pr_created with reviewer."""
        service = SlackNotificationService()

        result = service.notify_pr_created(
            pr_url="https://github.com/owner/repo/pull/1",
            title="Add feature",
            branch="feature",
            base_branch="main",
            repo="owner/repo",
            reviewer="reviewer-user",
        )

        assert result.success is True

        files = list(notifications_dir.glob("*.md"))
        content = files[0].read_text()
        assert "@reviewer-user" in content

    def test_notify_code_pushed(self, mock_home, notifications_dir):
        """Test notify_code_pushed method."""
        service = SlackNotificationService()

        result = service.notify_code_pushed(
            branch="feature-branch",
            repo="owner/repo",
            commit_message="Add new functionality",
        )

        assert result.success is True

        files = list(notifications_dir.glob("*.md"))
        content = files[0].read_text()
        assert "Code Pushed" in content
        assert "feature-branch" in content

    def test_notify_code_pushed_with_pr(self, mock_home, notifications_dir):
        """Test notify_code_pushed with related PR."""
        service = SlackNotificationService()

        result = service.notify_code_pushed(
            branch="feature",
            repo="owner/repo",
            commit_message="Fix bug",
            pr_number=42,
        )

        assert result.success is True

        files = list(notifications_dir.glob("*.md"))
        content = files[0].read_text()
        assert "#42" in content


class TestGetSlackService:
    """Tests for the singleton getter."""

    def test_get_slack_service_returns_instance(self, mock_home):
        """Test that get_slack_service returns a service instance."""
        # Reset the singleton for this test
        import notifications.slack as slack_module
        slack_module._default_instance = None

        service = get_slack_service()
        assert isinstance(service, SlackNotificationService)

    def test_get_slack_service_singleton(self, mock_home):
        """Test that get_slack_service returns the same instance."""
        import notifications.slack as slack_module
        slack_module._default_instance = None

        service1 = get_slack_service()
        service2 = get_slack_service()
        assert service1 is service2
