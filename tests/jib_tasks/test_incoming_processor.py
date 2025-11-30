"""
Tests for the incoming-processor.py module.

Tests the Slack incoming message processor:
- YAML frontmatter parsing
- Notification file creation with thread context
- Task/response routing
"""

import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import MagicMock, patch


# Load incoming-processor module (hyphenated filename)
incoming_processor_path = (
    Path(__file__).parent.parent.parent
    / "jib-container"
    / "jib-tasks"
    / "slack"
    / "incoming-processor.py"
)
loader = SourceFileLoader("incoming_processor", str(incoming_processor_path))
incoming_processor = loader.load_module()

parse_frontmatter = incoming_processor.parse_frontmatter
create_notification_with_thread = incoming_processor.create_notification_with_thread
extract_thread_context = incoming_processor.extract_thread_context


class TestParseFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_no_frontmatter(self):
        """Test content without frontmatter."""
        content = "Just some plain content\nwith multiple lines"
        metadata, remaining = parse_frontmatter(content)

        assert metadata == {}
        assert remaining == content

    def test_simple_frontmatter(self):
        """Test parsing simple frontmatter."""
        content = """---
task_id: "test-123"
thread_ts: "1234567890.123456"
---

Content after frontmatter"""

        metadata, remaining = parse_frontmatter(content)

        assert metadata["task_id"] == "test-123"
        assert metadata["thread_ts"] == "1234567890.123456"
        assert remaining == "Content after frontmatter"

    def test_frontmatter_no_closing(self):
        """Test frontmatter without closing delimiter."""
        content = """---
task_id: "test-123"
some content without closing"""

        metadata, remaining = parse_frontmatter(content)

        # Should treat as no frontmatter
        assert metadata == {}
        assert remaining == content

    def test_frontmatter_with_comments(self):
        """Test frontmatter with commented lines."""
        content = """---
task_id: "test-123"
# This is a comment
thread_ts: "1234567890.123456"
---

Content"""

        metadata, _remaining = parse_frontmatter(content)

        assert metadata["task_id"] == "test-123"
        assert metadata["thread_ts"] == "1234567890.123456"
        assert "comment" not in metadata

    def test_frontmatter_empty_values(self):
        """Test frontmatter with empty values."""
        content = """---
task_id: "test-123"
empty_key:
valid_key: "value"
---

Content"""

        metadata, _remaining = parse_frontmatter(content)

        assert metadata["task_id"] == "test-123"
        assert metadata["valid_key"] == "value"
        assert "empty_key" not in metadata

    def test_frontmatter_quoted_values(self):
        """Test frontmatter with various quote styles."""
        content = """---
double_quoted: "value1"
single_quoted: 'value2'
unquoted: value3
---

Content"""

        metadata, _remaining = parse_frontmatter(content)

        assert metadata["double_quoted"] == "value1"
        assert metadata["single_quoted"] == "value2"
        assert metadata["unquoted"] == "value3"


class TestCreateNotificationWithThread:
    """Tests for notification file creation."""

    def test_creates_notification_file(self, temp_dir):
        """Test that notification file is created."""
        notifications_dir = temp_dir / "notifications"

        result = create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id="test-task",
            thread_ts="1234567890.123456",
            content="Test notification content",
        )

        assert result.exists()
        assert result.name == "test-task.md"

    def test_includes_thread_ts(self, temp_dir):
        """Test that thread_ts is included in frontmatter."""
        notifications_dir = temp_dir / "notifications"

        result = create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id="test-task",
            thread_ts="1234567890.123456",
            content="Test content",
        )

        content = result.read_text()
        assert "thread_ts:" in content
        assert "1234567890.123456" in content

    def test_includes_task_id(self, temp_dir):
        """Test that task_id is included in frontmatter."""
        notifications_dir = temp_dir / "notifications"

        result = create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id="my-task-id",
            thread_ts="",
            content="Test content",
        )

        content = result.read_text()
        assert "task_id:" in content
        assert "my-task-id" in content

    def test_creates_parent_directory(self, temp_dir):
        """Test that parent directory is created if needed."""
        notifications_dir = temp_dir / "deep" / "nested" / "notifications"

        result = create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id="test-task",
            thread_ts="",
            content="Test content",
        )

        assert result.exists()
        assert notifications_dir.exists()

    def test_empty_thread_ts(self, temp_dir):
        """Test notification without thread_ts."""
        notifications_dir = temp_dir / "notifications"

        result = create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id="test-task",
            thread_ts="",
            content="Test content",
        )

        content = result.read_text()
        # Empty thread_ts should not be included
        assert 'thread_ts: ""' not in content or "thread_ts:" not in content

    def test_content_included(self, temp_dir):
        """Test that content is included after frontmatter."""
        notifications_dir = temp_dir / "notifications"
        test_content = "# My Notification\n\nThis is the body."

        result = create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id="test-task",
            thread_ts="12345",
            content=test_content,
        )

        file_content = result.read_text()
        assert test_content in file_content


class TestMain:
    """Tests for main entry point."""

    def test_missing_argument(self, capfd):
        """Test error when no file argument provided."""
        with patch.object(sys, "argv", ["incoming-processor.py"]):
            exit_code = incoming_processor.main()

        assert exit_code == 1
        captured = capfd.readouterr()
        assert "Usage:" in captured.err

    def test_file_not_found(self, temp_dir, capfd):
        """Test error when file doesn't exist."""
        nonexistent = temp_dir / "nonexistent.md"

        with patch.object(sys, "argv", ["incoming-processor.py", str(nonexistent)]):
            exit_code = incoming_processor.main()

        assert exit_code == 1
        captured = capfd.readouterr()
        assert "not found" in captured.err.lower()

    def test_incoming_file_routing(self, temp_dir, monkeypatch):
        """Test that incoming directory triggers process_task."""
        incoming_dir = temp_dir / "incoming"
        incoming_dir.mkdir()
        task_file = incoming_dir / "task.md"
        task_file.write_text("## Current Message\n\nTest task")

        with patch.object(incoming_processor, "process_task", return_value=True) as mock_task:
            with patch.object(sys, "argv", ["incoming-processor.py", str(task_file)]):
                incoming_processor.main()

            mock_task.assert_called_once_with(task_file)

    def test_response_file_routing(self, temp_dir, monkeypatch):
        """Test that responses directory triggers process_response."""
        responses_dir = temp_dir / "responses"
        responses_dir.mkdir()
        response_file = responses_dir / "response.md"
        response_file.write_text("## Current Message\n\nTest response")

        with patch.object(
            incoming_processor, "process_response", return_value=True
        ) as mock_response:
            with patch.object(sys, "argv", ["incoming-processor.py", str(response_file)]):
                incoming_processor.main()

            mock_response.assert_called_once_with(response_file)

    def test_unknown_directory_error(self, temp_dir, capfd):
        """Test error for file in unknown directory."""
        unknown_dir = temp_dir / "unknown"
        unknown_dir.mkdir()
        unknown_file = unknown_dir / "file.md"
        unknown_file.write_text("content")

        with patch.object(sys, "argv", ["incoming-processor.py", str(unknown_file)]):
            exit_code = incoming_processor.main()

        assert exit_code == 1
        captured = capfd.readouterr()
        assert "unknown message type" in captured.err.lower()


class TestProcessTask:
    """Tests for task processing."""

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_process_task_with_thread_context(self, mock_run, mock_popen, temp_dir, monkeypatch):
        """Test that thread context is preserved in task processing."""
        # Create task file with frontmatter
        incoming_dir = temp_dir / "incoming"
        incoming_dir.mkdir()
        task_file = incoming_dir / "task.md"
        task_file.write_text("""---
thread_ts: "1234567890.123456"
task_id: "slack-task-001"
---

## Current Message

Please help with this task.
""")

        # Mock subprocess.run (for beads and other commands)
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Task completed successfully!", stderr=""
        )

        # Mock subprocess.Popen for Claude streaming mode
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = iter(["Claude output line 1\n", "Claude output line 2\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Mock home directory
        monkeypatch.setenv("HOME", str(temp_dir))

        # Create expected directories
        (temp_dir / "khan").mkdir()
        notifications_dir = temp_dir / "sharing" / "notifications"
        notifications_dir.mkdir(parents=True)

        # Need to reload to pick up HOME change for Path.home()
        with patch.object(Path, "home", return_value=temp_dir):
            result = incoming_processor.process_task(task_file)

        # Should complete successfully
        assert result is True

        # Claude should have been called via Popen (streaming mode)
        mock_popen.assert_called()


class TestProcessResponse:
    """Tests for response processing."""

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_process_response_with_reference(self, mock_run, mock_popen, temp_dir, monkeypatch):
        """Test that referenced notification is loaded."""
        # Create response file
        responses_dir = temp_dir / "responses"
        responses_dir.mkdir()
        response_file = responses_dir / "response.md"
        response_file.write_text("""---
thread_ts: "1234567890.123456"
referenced_notification: "20251124-123456"
---

## Current Message

Here is my response to your question.
""")

        # Create original notification
        notifications_dir = temp_dir / "sharing" / "notifications"
        notifications_dir.mkdir(parents=True)
        original = notifications_dir / "20251124-123456.md"
        original.write_text("# Original Notification\n\nOriginal content.")

        # Mock subprocess.run (for beads and other commands)
        mock_run.return_value = MagicMock(returncode=0, stdout="Response processed!", stderr="")

        # Mock subprocess.Popen for Claude streaming mode
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stdout = iter(["Response output\n"])
        mock_process.stderr = iter([])
        mock_process.wait.return_value = 0
        mock_popen.return_value = mock_process

        # Mock home
        (temp_dir / "khan").mkdir()
        monkeypatch.setenv("HOME", str(temp_dir))

        with patch.object(Path, "home", return_value=temp_dir):
            result = incoming_processor.process_response(response_file)

        assert result is True


class TestExtractThreadContext:
    """Tests for thread context extraction."""

    def test_no_thread_context(self):
        """Test content without thread context section."""
        content = "Just some plain content\nwith no thread context"
        thread_ctx, pr_refs = extract_thread_context(content)

        assert thread_ctx == ""
        assert pr_refs == []

    def test_extracts_pr_analysis_reference(self):
        """Test extraction of PR Analysis format references."""
        content = """
## Thread Context

Full conversation history:

**1. James in a box:**
# PR Analysis: Khan/terraform-modules#29

Some analysis content

## Current Message

User message here
"""
        thread_ctx, pr_refs = extract_thread_context(content)

        assert "Khan/terraform-modules#29" in pr_refs
        assert len(pr_refs) == 1
        assert "PR Analysis" in thread_ctx

    def test_extracts_github_url(self):
        """Test extraction of GitHub PR URLs."""
        content = """
## Thread Context

See https://github.com/Khan/webapp/pull/12345 for details.

## Current Message

Do the thing
"""
        _thread_ctx, pr_refs = extract_thread_context(content)

        assert "Khan/webapp#12345" in pr_refs

    def test_extracts_shorthand_reference(self):
        """Test extraction of owner/repo#number shorthand."""
        content = """
## Thread Context

Working on owner/repo#123

## Current Message

Update needed
"""
        _thread_ctx, pr_refs = extract_thread_context(content)

        assert "owner/repo#123" in pr_refs

    def test_multiple_pr_references(self):
        """Test extraction of multiple PR references."""
        content = """
## Thread Context

# PR Analysis: Khan/webapp#100

Also see https://github.com/Khan/other-repo/pull/200

## Current Message

Fix both
"""
        _thread_ctx, pr_refs = extract_thread_context(content)

        assert "Khan/webapp#100" in pr_refs
        assert "Khan/other-repo#200" in pr_refs
        assert len(pr_refs) == 2

    def test_deduplicates_references(self):
        """Test that duplicate references are not repeated."""
        content = """
## Thread Context

# PR Analysis: Khan/webapp#100

PR: https://github.com/Khan/webapp/pull/100

## Current Message

Same PR mentioned twice
"""
        _thread_ctx, pr_refs = extract_thread_context(content)

        assert pr_refs.count("Khan/webapp#100") == 1

    def test_thread_context_stops_at_next_section(self):
        """Test that thread context extraction stops at ## Current Message."""
        content = """
## Thread Context

Thread content here

## Current Message

This should not be in thread context
"""
        thread_ctx, _pr_refs = extract_thread_context(content)

        assert "Thread content here" in thread_ctx
        assert "should not be in thread context" not in thread_ctx
