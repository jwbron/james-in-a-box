"""Tests for jib_logging.wrappers.gh module."""

from unittest.mock import MagicMock, patch

import pytest
from jib_logging.wrappers.gh import GhWrapper


class TestGhWrapper:
    """Tests for GhWrapper class."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    def test_tool_name_is_gh(self):
        """Test that tool_name is 'gh'."""
        assert self.wrapper.tool_name == "gh"


class TestGhPrCreate:
    """Tests for GhWrapper.pr_create() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    @patch.object(GhWrapper, "run")
    def test_pr_create_basic(self, mock_run):
        """Test basic PR creation."""
        mock_run.return_value = MagicMock(
            exit_code=0,
            stdout="https://github.com/owner/repo/pull/123",
        )

        self.wrapper.pr_create(title="Add feature", body="Description")

        args = mock_run.call_args[0]
        assert "pr" in args
        assert "create" in args
        assert "--title" in args
        assert "Add feature" in args
        assert "--body" in args
        assert "Description" in args

    @patch.object(GhWrapper, "run")
    def test_pr_create_draft(self, mock_run):
        """Test draft PR creation."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pr_create(title="WIP", body="Work in progress", draft=True)

        args = mock_run.call_args[0]
        assert "--draft" in args

    @patch.object(GhWrapper, "run")
    def test_pr_create_with_base_and_head(self, mock_run):
        """Test PR creation with base and head branches."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pr_create(
            title="Feature",
            body="Add feature",
            base="main",
            head="feature-branch",
        )

        args = mock_run.call_args[0]
        assert "--base" in args
        assert "main" in args
        assert "--head" in args
        assert "feature-branch" in args

    @patch.object(GhWrapper, "run")
    def test_pr_create_with_repo(self, mock_run):
        """Test PR creation with explicit repository."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pr_create(
            title="Feature",
            body="Add feature",
            repo="owner/repo",
        )

        args = mock_run.call_args[0]
        assert "--repo" in args
        assert "owner/repo" in args


class TestGhPrView:
    """Tests for GhWrapper.pr_view() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    @patch.object(GhWrapper, "run")
    def test_pr_view_basic(self, mock_run):
        """Test viewing a PR."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="PR details...")

        self.wrapper.pr_view(123)

        args = mock_run.call_args[0]
        assert "pr" in args
        assert "view" in args
        assert "123" in args

    @patch.object(GhWrapper, "run")
    def test_pr_view_json(self, mock_run):
        """Test viewing a PR with JSON output."""
        mock_run.return_value = MagicMock(
            exit_code=0,
            stdout='{"number": 123, "state": "open"}',
        )

        self.wrapper.pr_view(123, json_fields=["number", "state", "title"])

        args = mock_run.call_args[0]
        assert "--json" in args
        assert "number,state,title" in args


class TestGhPrList:
    """Tests for GhWrapper.pr_list() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    @patch.object(GhWrapper, "run")
    def test_pr_list_basic(self, mock_run):
        """Test listing PRs."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pr_list()

        args = mock_run.call_args[0]
        assert "pr" in args
        assert "list" in args

    @patch.object(GhWrapper, "run")
    def test_pr_list_filtered(self, mock_run):
        """Test listing PRs with filters."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pr_list(
            state="open",
            author="username",
            label="bug",
            limit=10,
        )

        args = mock_run.call_args[0]
        assert "--state" in args
        assert "open" in args
        assert "--author" in args
        assert "--label" in args
        assert "--limit" in args


class TestGhPrMerge:
    """Tests for GhWrapper.pr_merge() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    @patch.object(GhWrapper, "run")
    def test_pr_merge_basic(self, mock_run):
        """Test merging a PR."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pr_merge(123)

        args = mock_run.call_args[0]
        assert "pr" in args
        assert "merge" in args
        assert "123" in args

    @patch.object(GhWrapper, "run")
    def test_pr_merge_squash(self, mock_run):
        """Test squash merging a PR."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pr_merge(123, squash=True, delete_branch=True)

        args = mock_run.call_args[0]
        assert "--squash" in args
        assert "--delete-branch" in args


class TestGhIssueCreate:
    """Tests for GhWrapper.issue_create() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    @patch.object(GhWrapper, "run")
    def test_issue_create_basic(self, mock_run):
        """Test creating an issue."""
        mock_run.return_value = MagicMock(
            exit_code=0,
            stdout="https://github.com/owner/repo/issues/456",
        )

        self.wrapper.issue_create(title="Bug report", body="Description")

        args = mock_run.call_args[0]
        assert "issue" in args
        assert "create" in args
        assert "--title" in args
        assert "--body" in args

    @patch.object(GhWrapper, "run")
    def test_issue_create_with_labels(self, mock_run):
        """Test creating an issue with labels."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.issue_create(
            title="Bug",
            body="Description",
            labels=["bug", "urgent"],
        )

        args = mock_run.call_args[0]
        # Each label gets its own --label flag
        assert args.count("--label") == 2


class TestGhIssueList:
    """Tests for GhWrapper.issue_list() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    @patch.object(GhWrapper, "run")
    def test_issue_list_basic(self, mock_run):
        """Test listing issues."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.issue_list()

        args = mock_run.call_args[0]
        assert "issue" in args
        assert "list" in args

    @patch.object(GhWrapper, "run")
    def test_issue_list_filtered(self, mock_run):
        """Test listing issues with filters."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.issue_list(state="open", assignee="me")

        args = mock_run.call_args[0]
        assert "--state" in args
        assert "--assignee" in args


class TestGhApi:
    """Tests for GhWrapper.api() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    @patch.object(GhWrapper, "run")
    def test_api_basic(self, mock_run):
        """Test basic API call."""
        mock_run.return_value = MagicMock(exit_code=0, stdout='{"key": "value"}')

        self.wrapper.api("/repos/owner/repo")

        args = mock_run.call_args[0]
        assert "api" in args
        assert "/repos/owner/repo" in args

    @patch.object(GhWrapper, "run")
    def test_api_with_method(self, mock_run):
        """Test API call with HTTP method."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.api("/repos/owner/repo/issues", method="POST")

        args = mock_run.call_args[0]
        assert "--method" in args
        assert "POST" in args

    @patch.object(GhWrapper, "run")
    def test_api_with_fields(self, mock_run):
        """Test API call with form fields."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.api(
            "/repos/owner/repo/issues",
            method="POST",
            field={"title": "New issue"},
        )

        args = mock_run.call_args[0]
        assert "-f" in args
        assert "title=New issue" in args


class TestGhContextExtraction:
    """Tests for context extraction in GhWrapper."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GhWrapper()

    def test_extracts_resource_and_subcommand(self):
        """Test that resource and subcommand are extracted."""
        context = self.wrapper._extract_context(
            ("pr", "create", "--title", "Test"),
            "",
            "",
        )
        assert context.get("resource") == "pr"
        assert context.get("subcommand") == "create"

    def test_extracts_pr_number_from_args(self):
        """Test that PR number is extracted from args."""
        context = self.wrapper._extract_context(
            ("pr", "view", "123"),
            "",
            "",
        )
        assert context.get("pr_number") == 123

    def test_extracts_pr_url_from_output(self):
        """Test that PR URL is extracted from output."""
        context = self.wrapper._extract_context(
            ("pr", "create", "--title", "Test", "--body", "Body"),
            "https://github.com/owner/repo/pull/456\n",
            "",
        )
        assert context.get("pr_url") == "https://github.com/owner/repo/pull/456"
        assert context.get("pr_number") == 456

    def test_extracts_issue_url_from_output(self):
        """Test that issue URL is extracted from output."""
        context = self.wrapper._extract_context(
            ("issue", "create", "--title", "Bug"),
            "https://github.com/owner/repo/issues/789\n",
            "",
        )
        assert context.get("issue_url") == "https://github.com/owner/repo/issues/789"
        assert context.get("issue_number") == 789

    def test_extracts_repository_from_repo_flag(self):
        """Test that repository is extracted from --repo flag."""
        context = self.wrapper._extract_context(
            ("pr", "list", "--repo", "owner/repo"),
            "",
            "",
        )
        assert context.get("repository") == "owner/repo"

    def test_parses_json_output(self):
        """Test that JSON output is parsed for context."""
        context = self.wrapper._extract_context(
            ("pr", "view", "123", "--json", "number,state,title"),
            '{"number": 123, "state": "open", "title": "Test PR"}',
            "",
        )
        assert context.get("number") == 123
        assert context.get("state") == "open"
        assert context.get("title") == "Test PR"
