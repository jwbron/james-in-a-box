"""
Tests for comment-pr-helper.py.

These tests focus on the testable parts of the PR comment helper:
- Utility functions (signature handling, etc.)
- Error handling
- Non-git operations

Git/subprocess operations are mocked since they require a real git repo.
"""

import json
import subprocess

# Load modules with hyphenated filenames
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import MagicMock, patch


comment_pr_helper_path = (
    Path(__file__).parent.parent.parent / "jib-container" / "jib-tools" / "comment-pr-helper.py"
)

loader = SourceFileLoader("comment_pr_helper", str(comment_pr_helper_path))
comment_pr_helper = loader.load_module()


class TestPRCommenterSignature:
    """Tests for comment signature handling."""

    @patch("subprocess.run")
    def test_add_signature(self, mock_run, mock_home):
        """Test adding signature to comment."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")

        commenter = comment_pr_helper.PRCommenter()
        result = commenter.add_signature("Hello world")

        assert "-- Authored by jib" in result
        assert result.startswith("Hello world")

    @patch("subprocess.run")
    def test_no_double_signature(self, mock_run, mock_home):
        """Test that signature isn't added twice."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")

        commenter = comment_pr_helper.PRCommenter()
        body = "Hello\n\n---\n*-- Authored by jib*"
        result = commenter.add_signature(body)

        # Should return unchanged
        assert result == body
        assert result.count("-- Authored by jib") == 1

    @patch("subprocess.run")
    def test_alternative_signature_format(self, mock_run, mock_home):
        """Test that alternative signature format is recognized."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")

        commenter = comment_pr_helper.PRCommenter()
        body = "Hello\n\n-- jib"
        result = commenter.add_signature(body)

        # Should not add duplicate signature
        assert result.count("jib") == 1


class TestPRCommenterRepoName:
    """Tests for repo name parsing in commenter."""

    @patch("subprocess.run")
    def test_parse_ssh_url(self, mock_run, mock_home):
        """Test parsing SSH git remote URL."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            MagicMock(returncode=0, stdout="git@github.com:khan/webapp.git\n"),
        ]

        commenter = comment_pr_helper.PRCommenter()
        repo_name = commenter.get_repo_name()

        assert repo_name == "khan/webapp"

    @patch("subprocess.run")
    def test_parse_https_url(self, mock_run, mock_home):
        """Test parsing HTTPS git remote URL."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            MagicMock(returncode=0, stdout="https://github.com/owner/repo-name.git\n"),
        ]

        commenter = comment_pr_helper.PRCommenter()
        repo_name = commenter.get_repo_name()

        assert repo_name == "owner/repo-name"


class TestPRCommenterOperations:
    """Tests for PR commenter operations."""

    @patch("subprocess.run")
    def test_get_pr_info(self, mock_run, mock_home):
        """Test getting PR info from gh CLI."""
        pr_info = {
            "number": 123,
            "title": "Test PR",
            "url": "https://github.com/owner/repo/pull/123",
            "author": {"login": "user"},
            "headRefName": "feature",
            "baseRefName": "main",
        }
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            MagicMock(returncode=0, stdout=json.dumps(pr_info)),
        ]

        commenter = comment_pr_helper.PRCommenter()
        result = commenter.get_pr_info(123)

        assert result["number"] == 123
        assert result["title"] == "Test PR"

    @patch("subprocess.run")
    def test_get_pr_info_not_found(self, mock_run, mock_home):
        """Test getting PR info when PR doesn't exist."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            subprocess.CalledProcessError(1, "gh"),
        ]

        commenter = comment_pr_helper.PRCommenter()
        result = commenter.get_pr_info(9999)

        assert result is None
