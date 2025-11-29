"""
Tests for the GitHub processor module.

Tests the GitHub Processor dispatcher:
- Command-line argument parsing
- Task dispatching to handlers
- Prompt building for Claude
- Make target detection
"""

import json
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Load github processor module
processor_path = (
    Path(__file__).parent.parent.parent
    / "jib-container"
    / "jib-tasks"
    / "github"
    / "github-processor.py"
)
loader = SourceFileLoader("github_processor", str(processor_path))
github_processor = loader.load_module()


class TestDetectMakeTargets:
    """Tests for make target detection."""

    def test_detect_targets_no_makefile(self, temp_dir):
        """Test when Makefile doesn't exist."""
        result = github_processor.detect_make_targets(temp_dir)
        assert result == {}

    def test_detect_targets_with_makefile(self, temp_dir):
        """Test detecting targets from Makefile."""
        makefile = temp_dir / "Makefile"
        makefile.write_text("""
.PHONY: all test lint fix

all: test lint

test:
	pytest tests/

lint:
	ruff check .

lint-fix:
	ruff check . --fix

fix: lint-fix
	echo "Fixed"
""")

        result = github_processor.detect_make_targets(temp_dir)

        assert "test" in result["all"]
        assert "lint" in result["all"]
        assert "lint-fix" in result["all"]
        assert "fix" in result["all"]
        assert "test" in result["test"]
        assert "lint" in result["lint"]
        assert "lint-fix" in result["lint"]
        assert "lint-fix" in result["fix"]
        assert "fix" in result["fix"]

    def test_detect_targets_ignores_special(self, temp_dir):
        """Test that special targets are ignored."""
        makefile = temp_dir / "Makefile"
        makefile.write_text("""
.PHONY: test

test:
	pytest

.DEFAULT_GOAL := test
""")

        result = github_processor.detect_make_targets(temp_dir)

        assert "test" in result["all"]
        assert ".PHONY" not in result["all"]
        assert ".DEFAULT_GOAL" not in result["all"]


class TestBuildCheckFailurePrompt:
    """Tests for check failure prompt building."""

    def test_build_prompt_basic(self, temp_dir):
        """Test building basic check failure prompt."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Fix bug",
            "pr_url": "https://github.com/owner/repo/pull/123",
            "pr_branch": "fix-branch",
            "base_branch": "main",
            "pr_body": "This PR fixes a bug.",
            "failed_checks": [{"name": "test", "state": "FAILURE", "full_log": "Test failed"}],
        }

        prompt = github_processor.build_check_failure_prompt(context)

        assert "owner/repo" in prompt
        assert "#123" in prompt
        assert "Fix bug" in prompt
        assert "test" in prompt
        assert "FAILURE" in prompt
        assert "Test failed" in prompt

    def test_build_prompt_with_log_excerpt(self, temp_dir):
        """Test prompt with long log is truncated."""
        long_log = "x" * 10000  # Very long log
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Fix bug",
            "pr_url": "",
            "pr_branch": "fix-branch",
            "base_branch": "main",
            "pr_body": "",
            "failed_checks": [{"name": "test", "state": "FAILURE", "full_log": long_log}],
        }

        prompt = github_processor.build_check_failure_prompt(context)

        # Should contain excerpts, not full log
        assert "first 2000 chars" in prompt.lower() or "log excerpt" in prompt.lower()
        assert len(prompt) < len(long_log)

    def test_build_prompt_with_make_targets(self, temp_dir):
        """Test prompt includes make targets when available."""
        # Create a makefile in the repo path
        repo_path = temp_dir / "khan" / "repo"
        repo_path.mkdir(parents=True)
        makefile = repo_path / "Makefile"
        makefile.write_text("""
lint-fix:
	ruff check . --fix

test:
	pytest
""")

        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Fix bug",
            "pr_url": "",
            "pr_branch": "fix-branch",
            "base_branch": "main",
            "pr_body": "",
            "failed_checks": [{"name": "lint", "state": "FAILURE", "full_log": "Linting failed"}],
        }

        with patch.object(Path, "home", return_value=temp_dir):
            prompt = github_processor.build_check_failure_prompt(context)

        assert "make lint-fix" in prompt or "make targets" in prompt.lower()


class TestBuildCommentPrompt:
    """Tests for comment response prompt building."""

    def test_build_comment_prompt_basic(self):
        """Test building basic comment prompt."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Fix bug",
            "pr_url": "https://github.com/owner/repo/pull/123",
            "comments": [
                {
                    "author": "reviewer",
                    "body": "Please fix the typo",
                    "type": "comment",
                    "created_at": "2025-01-01T00:00:00Z",
                    "state": "",
                }
            ],
        }

        prompt = github_processor.build_comment_prompt(context)

        assert "owner/repo" in prompt
        assert "#123" in prompt
        assert "@reviewer" in prompt
        assert "Please fix the typo" in prompt

    def test_build_comment_prompt_multiple_comments(self):
        """Test prompt with multiple comments."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Fix bug",
            "pr_url": "",
            "comments": [
                {
                    "author": "user1",
                    "body": "Comment 1",
                    "type": "comment",
                    "created_at": "",
                    "state": "",
                },
                {
                    "author": "user2",
                    "body": "Comment 2",
                    "type": "review",
                    "created_at": "",
                    "state": "CHANGES_REQUESTED",
                },
            ],
        }

        prompt = github_processor.build_comment_prompt(context)

        assert "@user1" in prompt
        assert "@user2" in prompt
        assert "Comment 1" in prompt
        assert "Comment 2" in prompt
        assert "CHANGES_REQUESTED" in prompt


class TestBuildReviewPrompt:
    """Tests for PR review prompt building."""

    def test_build_review_prompt_basic(self):
        """Test building basic review prompt."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Add feature",
            "pr_url": "https://github.com/owner/repo/pull/123",
            "pr_branch": "feature-branch",
            "base_branch": "main",
            "author": "developer",
            "additions": 100,
            "deletions": 50,
            "files": ["src/app.py", "tests/test_app.py"],
            "diff": "diff --git a/src/app.py\n+new code",
        }

        prompt = github_processor.build_review_prompt(context)

        assert "owner/repo" in prompt
        assert "#123" in prompt
        assert "Add feature" in prompt
        assert "@developer" in prompt
        assert "+100" in prompt
        assert "-50" in prompt
        assert "src/app.py" in prompt
        assert "new code" in prompt

    def test_build_review_prompt_large_diff(self):
        """Test prompt truncates large diffs."""
        large_diff = "x" * 50000
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Add feature",
            "pr_url": "",
            "pr_branch": "feature-branch",
            "base_branch": "main",
            "author": "developer",
            "additions": 1000,
            "deletions": 500,
            "files": ["file1.py"] * 30,  # Many files
            "diff": large_diff,
        }

        prompt = github_processor.build_review_prompt(context)

        # Should be truncated
        assert len(prompt) < len(large_diff)
        assert "truncated" in prompt.lower() or "..." in prompt

    def test_build_review_prompt_many_files(self):
        """Test prompt handles many files."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Add feature",
            "pr_url": "",
            "pr_branch": "feature-branch",
            "base_branch": "main",
            "author": "developer",
            "additions": 100,
            "deletions": 50,
            "files": [f"file{i}.py" for i in range(30)],
            "diff": "diff content",
        }

        prompt = github_processor.build_review_prompt(context)

        # Should show first 20 files and indicate more exist
        assert "file0.py" in prompt
        assert "file19.py" in prompt
        assert "..." in prompt


class TestCreateNotification:
    """Tests for notification creation."""

    def test_create_notification(self, temp_dir):
        """Test notification file is created."""
        notifications_dir = temp_dir / "sharing" / "notifications"
        notifications_dir.mkdir(parents=True)

        with patch.object(Path, "home", return_value=temp_dir):
            github_processor.create_notification("Test Title", "Test body content")

        notifications = list(notifications_dir.glob("*.md"))
        assert len(notifications) == 1

        content = notifications[0].read_text()
        assert "Test Title" in content
        assert "Test body content" in content


class TestHandlers:
    """Tests for task handlers."""

    def test_handle_check_failure_invokes_claude(self, temp_dir):
        """Test check failure handler invokes Claude."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Fix bug",
            "pr_url": "",
            "pr_branch": "fix-branch",
            "base_branch": "main",
            "pr_body": "",
            "failed_checks": [{"name": "test", "state": "FAILURE"}],
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("subprocess.Popen") as mock_popen:
                # Mock Popen for streaming mode (used by run_claude)
                mock_process = MagicMock()
                mock_process.stdout = iter([])
                mock_process.stderr = iter([])
                mock_process.wait.return_value = 0
                mock_process.returncode = 0
                mock_popen.return_value = mock_process

                github_processor.handle_check_failure(context)

                # Should invoke claude via Popen (streaming mode)
                mock_popen.assert_called()
                # Check that at least one call has "claude" in the command
                all_calls = mock_popen.call_args_list + mock_run.call_args_list
                claude_calls = [
                    call for call in all_calls
                    if call[0] and "claude" in call[0][0]
                ]
                assert len(claude_calls) > 0, "Expected at least one call to claude"

    def test_handle_comment_invokes_claude(self, temp_dir):
        """Test comment handler invokes Claude."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Fix bug",
            "pr_url": "",
            "comments": [{"author": "user", "body": "Please fix", "type": "comment"}],
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("subprocess.Popen") as mock_popen:
                # Mock Popen for streaming mode (used by run_claude)
                mock_process = MagicMock()
                mock_process.stdout = iter([])
                mock_process.stderr = iter([])
                mock_process.wait.return_value = 0
                mock_process.returncode = 0
                mock_popen.return_value = mock_process

                github_processor.handle_comment(context)

                # Should invoke claude via Popen (streaming mode)
                mock_popen.assert_called()
                # Check that at least one call has "claude" in the command
                all_calls = mock_popen.call_args_list + mock_run.call_args_list
                claude_calls = [
                    call for call in all_calls
                    if call[0] and "claude" in call[0][0]
                ]
                assert len(claude_calls) > 0, "Expected at least one call to claude"

    def test_handle_review_request_invokes_claude(self, temp_dir):
        """Test review handler invokes Claude."""
        context = {
            "repository": "owner/repo",
            "pr_number": 123,
            "pr_title": "Add feature",
            "pr_url": "",
            "pr_branch": "feature",
            "base_branch": "main",
            "author": "dev",
            "additions": 10,
            "deletions": 5,
            "files": ["app.py"],
            "diff": "diff content",
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("subprocess.Popen") as mock_popen:
                # Mock Popen for streaming mode (used by run_claude)
                mock_process = MagicMock()
                mock_process.stdout = iter([])
                mock_process.stderr = iter([])
                mock_process.wait.return_value = 0
                mock_process.returncode = 0
                mock_popen.return_value = mock_process

                github_processor.handle_review_request(context)

                # Should invoke claude via Popen (streaming mode)
                mock_popen.assert_called()
                # Check that at least one call has "claude" in the command
                all_calls = mock_popen.call_args_list + mock_run.call_args_list
                claude_calls = [
                    call for call in all_calls
                    if call[0] and "claude" in call[0][0]
                ]
                assert len(claude_calls) > 0, "Expected at least one call to claude"


class TestMain:
    """Tests for main entry point."""

    def test_main_requires_task(self):
        """Test main requires --task argument."""
        with patch("sys.argv", ["github-processor.py"]):
            with pytest.raises(SystemExit):
                github_processor.main()

    def test_main_requires_context(self):
        """Test main requires --context argument."""
        with patch("sys.argv", ["github-processor.py", "--task", "check_failure"]):
            with pytest.raises(SystemExit):
                github_processor.main()

    def test_main_invalid_context_json(self, capsys):
        """Test main exits on invalid JSON context."""
        with patch(
            "sys.argv",
            [
                "github-processor.py",
                "--task",
                "check_failure",
                "--context",
                "invalid{json",
            ],
        ):
            with pytest.raises(SystemExit):
                github_processor.main()

    def test_main_dispatches_to_handler(self):
        """Test main dispatches to correct handler."""
        context = json.dumps(
            {
                "repository": "owner/repo",
                "pr_number": 123,
                "pr_title": "Fix",
                "pr_url": "",
                "pr_branch": "fix",
                "base_branch": "main",
                "pr_body": "",
                "failed_checks": [],
            }
        )

        with patch(
            "sys.argv",
            [
                "github-processor.py",
                "--task",
                "check_failure",
                "--context",
                context,
            ],
        ):
            with patch.object(github_processor, "handle_check_failure") as mock_handler:
                github_processor.main()
                mock_handler.assert_called_once()

    def test_main_handles_comment_task(self):
        """Test main handles comment task."""
        context = json.dumps(
            {
                "repository": "owner/repo",
                "pr_number": 123,
                "pr_title": "Fix",
                "pr_url": "",
                "comments": [],
            }
        )

        with patch(
            "sys.argv",
            [
                "github-processor.py",
                "--task",
                "comment",
                "--context",
                context,
            ],
        ):
            with patch.object(github_processor, "handle_comment") as mock_handler:
                github_processor.main()
                mock_handler.assert_called_once()

    def test_main_handles_review_task(self):
        """Test main handles review_request task."""
        context = json.dumps(
            {
                "repository": "owner/repo",
                "pr_number": 123,
                "pr_title": "Add",
                "pr_url": "",
                "pr_branch": "feature",
                "base_branch": "main",
                "author": "dev",
                "additions": 0,
                "deletions": 0,
                "files": [],
                "diff": "",
            }
        )

        with patch(
            "sys.argv",
            [
                "github-processor.py",
                "--task",
                "review_request",
                "--context",
                context,
            ],
        ):
            with patch.object(github_processor, "handle_review_request") as mock_handler:
                github_processor.main()
                mock_handler.assert_called_once()
