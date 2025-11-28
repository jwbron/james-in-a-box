"""
Tests for the pr-analyzer.py module.

Tests the GitHub PR analyzer:
- Context loading
- Output formatting
- Prompt generation
"""

import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch


# Load pr-analyzer module (hyphenated filename)
pr_analyzer_path = (
    Path(__file__).parent.parent.parent
    / "jib-container"
    / "jib-tasks"
    / "github"
    / "pr-analyzer.py"
)
loader = SourceFileLoader("pr_analyzer", str(pr_analyzer_path))
pr_analyzer = loader.load_module()

load_context = pr_analyzer.load_context
format_pr_summary = pr_analyzer.format_pr_summary
format_files_changed = pr_analyzer.format_files_changed
format_checks = pr_analyzer.format_checks
format_failed_logs = pr_analyzer.format_failed_logs
format_comments = pr_analyzer.format_comments
format_reviews = pr_analyzer.format_reviews
format_review_comments = pr_analyzer.format_review_comments
format_commits = pr_analyzer.format_commits
format_diff = pr_analyzer.format_diff
build_analysis_prompt = pr_analyzer.build_analysis_prompt


class TestLoadContext:
    """Tests for loading PR context from JSON file."""

    def test_load_valid_context(self, temp_dir):
        """Test loading valid context file."""
        context_file = temp_dir / "context.json"
        context_data = {
            "owner": "test-owner",
            "repo": "test-repo",
            "pr_number": 123,
            "pr": {"title": "Test PR"},
        }
        context_file.write_text(json.dumps(context_data))

        result = load_context(context_file)

        assert result["owner"] == "test-owner"
        assert result["pr_number"] == 123

    def test_load_empty_context(self, temp_dir):
        """Test loading empty context file."""
        context_file = temp_dir / "context.json"
        context_file.write_text("{}")

        result = load_context(context_file)
        assert result == {}


class TestFormatPrSummary:
    """Tests for PR summary formatting."""

    def test_format_complete_pr(self):
        """Test formatting PR with all fields."""
        ctx = {
            "pr": {
                "title": "Add new feature",
                "author": {"login": "testuser"},
                "state": "OPEN",
                "reviewDecision": "APPROVED",
                "isDraft": False,
                "mergeable": "MERGEABLE",
                "baseRefName": "main",
                "headRefName": "feature-branch",
                "additions": 100,
                "deletions": 50,
                "changedFiles": 5,
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-02T00:00:00Z",
                "body": "This PR adds a new feature.",
            }
        }

        result = format_pr_summary(ctx)

        assert "Add new feature" in result
        assert "testuser" in result
        assert "OPEN" in result
        assert "APPROVED" in result
        assert "main" in result
        assert "feature-branch" in result
        assert "+100" in result
        assert "-50" in result

    def test_format_empty_pr(self):
        """Test formatting PR with missing fields."""
        ctx = {"pr": {}}

        result = format_pr_summary(ctx)

        assert "N/A" in result
        assert "## PR Summary" in result


class TestFormatFilesChanged:
    """Tests for files changed formatting."""

    def test_format_with_files(self):
        """Test formatting file changes."""
        ctx = {
            "files": [
                {"path": "src/app.py", "additions": 10, "deletions": 5},
                {"path": "tests/test_app.py", "additions": 20, "deletions": 0},
            ]
        }

        result = format_files_changed(ctx)

        assert "src/app.py" in result
        assert "+10" in result
        assert "-5" in result
        assert "tests/test_app.py" in result

    def test_format_no_files(self):
        """Test formatting when no files changed."""
        ctx = {"files": []}

        result = format_files_changed(ctx)
        assert "No files data available" in result


class TestFormatChecks:
    """Tests for CI check formatting."""

    def test_format_failed_checks(self):
        """Test formatting failed checks."""
        ctx = {
            "checks": [
                {"name": "pytest", "state": "FAILURE"},
                {"name": "lint", "state": "FAILURE"},
            ]
        }

        result = format_checks(ctx)

        assert "Failed" in result
        assert "pytest" in result
        assert "lint" in result

    def test_format_pending_checks(self):
        """Test formatting in-progress checks."""
        ctx = {"checks": [{"name": "build", "state": "IN_PROGRESS"}]}

        result = format_checks(ctx)
        assert "In Progress" in result
        assert "build" in result

    def test_format_passed_checks(self):
        """Test formatting passed checks."""
        ctx = {
            "checks": [
                {"name": "test1", "state": "SUCCESS"},
                {"name": "test2", "state": "SUCCESS"},
            ]
        }

        result = format_checks(ctx)
        assert "Passed" in result

    def test_format_no_checks(self):
        """Test formatting when no checks available."""
        ctx = {"checks": []}

        result = format_checks(ctx)
        assert "No checks data available" in result


class TestFormatFailedLogs:
    """Tests for failed check log formatting."""

    def test_format_logs(self):
        """Test formatting check logs."""
        ctx = {"failed_check_logs": {"pytest": "Test failed: AssertionError\nExpected 5, got 3"}}

        result = format_failed_logs(ctx)

        assert "pytest" in result
        assert "AssertionError" in result

    def test_format_truncated_logs(self):
        """Test that very long logs are truncated."""
        long_log = "x" * 20000
        ctx = {"failed_check_logs": {"check": long_log}}

        result = format_failed_logs(ctx)

        assert "truncated" in result
        assert len(result) < len(long_log) + 1000  # Some overhead for formatting

    def test_format_no_logs(self):
        """Test formatting when no logs available."""
        ctx = {"failed_check_logs": {}}

        result = format_failed_logs(ctx)
        assert result == ""


class TestFormatComments:
    """Tests for PR comment formatting."""

    def test_format_comments(self):
        """Test formatting PR comments."""
        ctx = {
            "comments": [
                {
                    "author": {"login": "reviewer"},
                    "createdAt": "2025-01-01T00:00:00Z",
                    "body": "This looks good!",
                }
            ]
        }

        result = format_comments(ctx)

        assert "reviewer" in result
        assert "This looks good!" in result

    def test_format_no_comments(self):
        """Test formatting when no comments."""
        ctx = {"comments": []}

        result = format_comments(ctx)
        assert "No comments" in result


class TestFormatReviews:
    """Tests for review formatting."""

    def test_format_reviews(self):
        """Test formatting PR reviews."""
        ctx = {"reviews": [{"author": {"login": "reviewer"}, "state": "APPROVED", "body": "LGTM"}]}

        result = format_reviews(ctx)

        assert "reviewer" in result
        assert "APPROVED" in result
        assert "LGTM" in result

    def test_format_no_reviews(self):
        """Test formatting when no reviews."""
        ctx = {"reviews": []}

        result = format_reviews(ctx)
        assert "No reviews" in result


class TestFormatReviewComments:
    """Tests for inline review comment formatting."""

    def test_format_review_comments(self):
        """Test formatting inline comments."""
        ctx = {
            "review_comments": [
                {
                    "path": "src/app.py",
                    "line": 42,
                    "user": {"login": "reviewer"},
                    "body": "Consider using a constant here",
                }
            ]
        }

        result = format_review_comments(ctx)

        assert "src/app.py:42" in result
        assert "reviewer" in result
        assert "constant" in result

    def test_format_no_review_comments(self):
        """Test formatting when no inline comments."""
        ctx = {"review_comments": []}

        result = format_review_comments(ctx)
        assert result == ""


class TestFormatCommits:
    """Tests for commit formatting."""

    def test_format_commits(self):
        """Test formatting commits."""
        ctx = {
            "commits": [
                {"oid": "abc123456789", "messageHeadline": "Add feature"},
                {"oid": "def987654321", "messageHeadline": "Fix bug"},
            ]
        }

        result = format_commits(ctx)

        assert "abc12345" in result
        assert "Add feature" in result
        assert "def98765" in result
        assert "Fix bug" in result

    def test_format_no_commits(self):
        """Test formatting when no commits."""
        ctx = {"commits": []}

        result = format_commits(ctx)
        assert "No commit data" in result


class TestFormatDiff:
    """Tests for diff formatting."""

    def test_format_diff(self):
        """Test formatting PR diff."""
        ctx = {"diff": "diff --git a/file.py b/file.py\n+new line\n-old line"}

        result = format_diff(ctx)

        assert "```diff" in result
        assert "+new line" in result
        assert "-old line" in result

    def test_format_truncated_diff(self):
        """Test that long diffs are truncated."""
        long_diff = "+" * 50000
        ctx = {"diff": long_diff}

        result = format_diff(ctx, max_length=1000)

        assert "truncated" in result
        assert len(result) < 50000

    def test_format_no_diff(self):
        """Test formatting when no diff available."""
        ctx = {"diff": ""}

        result = format_diff(ctx)
        assert "No diff available" in result


class TestBuildAnalysisPrompt:
    """Tests for prompt building."""

    def test_build_suggest_prompt(self):
        """Test building suggest-only prompt."""
        ctx = {
            "owner": "test-owner",
            "repo": "test-repo",
            "pr_number": 123,
            "pr": {"title": "Test PR", "state": "OPEN"},
            "files": [],
            "checks": [],
            "reviews": [],
            "comments": [],
            "commits": [],
            "diff": "",
        }

        result = build_analysis_prompt(ctx, fix_mode=False)

        assert "test-owner/test-repo#123" in result
        assert "Analyze and Suggest" in result
        assert "Understand the PR" in result

    def test_build_fix_prompt(self):
        """Test building fix-mode prompt."""
        ctx = {
            "owner": "test-owner",
            "repo": "test-repo",
            "pr_number": 123,
            "pr": {"title": "Test PR", "state": "OPEN"},
            "files": [],
            "checks": [],
            "reviews": [],
            "comments": [],
            "commits": [],
            "diff": "",
        }

        result = build_analysis_prompt(ctx, fix_mode=True)

        assert "test-owner/test-repo#123" in result
        assert "Analyze and Fix" in result
        assert "Implement fixes" in result

    def test_prompt_includes_all_sections(self):
        """Test that prompt includes all context sections."""
        ctx = {
            "owner": "owner",
            "repo": "repo",
            "pr_number": 1,
            "pr": {"title": "PR", "body": "Description"},
            "files": [{"path": "file.py", "additions": 1, "deletions": 1}],
            "checks": [{"name": "test", "state": "FAILURE"}],
            "reviews": [{"author": {"login": "user"}, "state": "CHANGES_REQUESTED"}],
            "comments": [{"author": {"login": "user"}, "body": "Comment"}],
            "commits": [{"oid": "abc", "messageHeadline": "Commit"}],
            "diff": "diff content",
        }

        result = build_analysis_prompt(ctx)

        assert "## PR Summary" in result
        assert "## Files Changed" in result
        assert "## CI Checks" in result
        assert "## Reviews" in result
        assert "## Comments" in result
        assert "## Commits" in result
        assert "## Diff" in result


class TestMain:
    """Tests for main entry point."""

    def test_missing_context_file(self, temp_dir, capsys):
        """Test error when context file doesn't exist."""
        nonexistent = temp_dir / "nonexistent.json"

        with patch.object(sys, "argv", ["pr-analyzer.py", str(nonexistent)]):
            exit_code = pr_analyzer.main()

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "not found" in captured.err.lower()

    @patch.object(pr_analyzer, "stop_background_services")
    def test_successful_analysis(self, mock_stop, temp_dir):
        """Test successful PR analysis."""
        # Import ClaudeResult for mocking
        from claude import ClaudeResult

        # Create a mock ClaudeResult for successful run
        mock_result = ClaudeResult(
            success=True,
            stdout="Analysis complete",
            stderr="",
            returncode=0,
            error=None,
        )

        context_file = temp_dir / "context.json"
        context_file.write_text(
            json.dumps(
                {
                    "owner": "owner",
                    "repo": "repo",
                    "pr_number": 123,
                    "pr": {"title": "Test"},
                    "files": [],
                    "checks": [],
                    "reviews": [],
                    "comments": [],
                    "commits": [],
                    "diff": "",
                }
            )
        )

        with patch.object(pr_analyzer, "run_claude", return_value=mock_result) as mock_claude:
            with patch.object(sys, "argv", ["pr-analyzer.py", str(context_file)]):
                exit_code = pr_analyzer.main()

        assert exit_code == 0
        mock_claude.assert_called_once()
        mock_stop.assert_called_once()
