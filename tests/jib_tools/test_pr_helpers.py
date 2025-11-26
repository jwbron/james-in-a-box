"""
Tests for create-pr-helper.py and comment-pr-helper.py.

These tests focus on the testable parts of the PR helpers:
- Utility functions (signature, body generation, etc.)
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


create_pr_helper_path = (
    Path(__file__).parent.parent.parent / "jib-container" / "jib-tools" / "create-pr-helper.py"
)
comment_pr_helper_path = (
    Path(__file__).parent.parent.parent / "jib-container" / "jib-tools" / "comment-pr-helper.py"
)

loader = SourceFileLoader("create_pr_helper", str(create_pr_helper_path))
create_pr_helper = loader.load_module()

loader = SourceFileLoader("comment_pr_helper", str(comment_pr_helper_path))
comment_pr_helper = loader.load_module()


class TestPRCreatorRepoName:
    """Tests for repo name parsing."""

    @patch("subprocess.run")
    def test_parse_ssh_url(self, mock_run, mock_home):
        """Test parsing SSH git remote URL."""
        mock_run.side_effect = [
            # find_repo_root
            MagicMock(returncode=0, stdout="/test/repo\n"),
            # get_repo_name
            MagicMock(returncode=0, stdout="git@github.com:owner/repo-name.git\n"),
        ]

        creator = create_pr_helper.PRCreator()
        repo_name = creator.get_repo_name()

        assert repo_name == "owner/repo-name"

    @patch("subprocess.run")
    def test_parse_https_url(self, mock_run, mock_home):
        """Test parsing HTTPS git remote URL."""
        mock_run.side_effect = [
            # find_repo_root
            MagicMock(returncode=0, stdout="/test/repo\n"),
            # get_repo_name
            MagicMock(returncode=0, stdout="https://github.com/owner/repo-name.git\n"),
        ]

        creator = create_pr_helper.PRCreator()
        repo_name = creator.get_repo_name()

        assert repo_name == "owner/repo-name"


class TestPRCreatorTestPlan:
    """Tests for test plan generation."""

    @patch("subprocess.run")
    def test_generate_test_plan_python_with_tests(self, mock_run, mock_home):
        """Test generating test plan for Python files with tests."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")

        creator = create_pr_helper.PRCreator()
        test_items = creator._generate_test_plan(
            [
                "src/main.py",
                "tests/test_main.py",
            ]
        )

        assert any("pytest" in item.lower() for item in test_items)
        assert any("review" in item.lower() for item in test_items)

    @patch("subprocess.run")
    def test_generate_test_plan_javascript_with_tests(self, mock_run, mock_home):
        """Test generating test plan for JavaScript files with tests."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")

        creator = create_pr_helper.PRCreator()
        test_items = creator._generate_test_plan(
            [
                "src/app.ts",
                "src/app.test.ts",
            ]
        )

        assert any("npm test" in item.lower() for item in test_items)

    @patch("subprocess.run")
    def test_generate_test_plan_config_files(self, mock_run, mock_home):
        """Test generating test plan for config files."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")

        creator = create_pr_helper.PRCreator()
        test_items = creator._generate_test_plan(
            [
                "config/settings.yaml",
                "package.json",
            ]
        )

        assert any("configuration" in item.lower() for item in test_items)

    @patch("subprocess.run")
    def test_generate_test_plan_includes_file_list(self, mock_run, mock_home):
        """Test that small file lists are included in test plan."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/test/repo\n")

        creator = create_pr_helper.PRCreator()
        files = ["src/a.py", "src/b.py", "src/c.py"]
        test_items = creator._generate_test_plan(files)

        assert any("Files to review" in item for item in test_items)


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


class TestPRCreatorBodyGeneration:
    """Tests for PR body generation."""

    @patch("subprocess.run")
    def test_generate_pr_body_single_commit(self, mock_run, mock_home):
        """Test generating PR body for a single commit."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),  # find_repo_root
            MagicMock(returncode=0, stdout="main\n"),  # remote show origin
            MagicMock(
                returncode=0, stdout="Add feature\n\nDetails here.---COMMIT_SEPARATOR---"
            ),  # full commit messages
            MagicMock(returncode=0, stdout="src/main.py\n"),  # changed files
        ]

        creator = create_pr_helper.PRCreator()
        body = creator.generate_pr_body(["abc1234 Add feature"])

        assert "Issue: none" in body
        assert "## Test Plan" in body
        assert "authored by jib" in body.lower()

    @patch("subprocess.run")
    def test_generate_pr_body_multiple_commits(self, mock_run, mock_home):
        """Test generating PR body for multiple commits."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),  # find_repo_root
            MagicMock(returncode=0, stdout="main\n"),  # remote show origin
            MagicMock(
                returncode=0, stdout="First\n---COMMIT_SEPARATOR---Second\n---COMMIT_SEPARATOR---"
            ),
            MagicMock(returncode=0, stdout="a.py\nb.py\n"),
        ]

        creator = create_pr_helper.PRCreator()
        commits = ["abc Add feature", "def Fix bug", "ghi Update docs"]
        body = creator.generate_pr_body(commits)

        assert "## Commits" in body
        assert "abc Add feature" in body

    @patch("subprocess.run")
    def test_generate_pr_body_with_custom_body(self, mock_run, mock_home):
        """Test generating PR body with custom description."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            MagicMock(returncode=0, stdout="main\n"),
            MagicMock(returncode=0, stdout=""),
            MagicMock(returncode=0, stdout="file.py\n"),
        ]

        creator = create_pr_helper.PRCreator()
        body = creator.generate_pr_body(["abc123 Fix"], custom_body="This fixes a critical bug")

        assert "This fixes a critical bug" in body


class TestCheckWritable:
    """Tests for writable repo checking."""

    @patch("subprocess.run")
    def test_check_writable_returns_tuple(self, mock_run, mock_home):
        """Test that check_writable returns (bool, repo_name) tuple."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            MagicMock(returncode=0, stdout="git@github.com:owner/repo.git\n"),
        ]

        creator = create_pr_helper.PRCreator()
        result = creator.check_writable()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    @patch("subprocess.run")
    def test_check_writable_unknown_when_no_remote(self, mock_run, mock_home):
        """Test check_writable returns unknown when remote fails."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            subprocess.CalledProcessError(1, "git"),
        ]

        creator = create_pr_helper.PRCreator()
        is_writable, repo_name = creator.check_writable()

        assert repo_name == "unknown"
        assert is_writable is False


class TestPRCreatorGitOperations:
    """Tests for git operations."""

    @patch("subprocess.run")
    def test_get_current_branch(self, mock_run, mock_home):
        """Test getting current branch."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),  # find_repo_root
            MagicMock(returncode=0, stdout="feature-branch\n"),  # get_current_branch
        ]

        creator = create_pr_helper.PRCreator()
        branch = creator.get_current_branch()

        assert branch == "feature-branch"

    @patch("subprocess.run")
    def test_get_base_branch_main(self, mock_run, mock_home):
        """Test detecting main as base branch."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            MagicMock(returncode=0, stdout="HEAD branch: main\n"),
        ]

        creator = create_pr_helper.PRCreator()
        base = creator.get_base_branch()

        assert base == "main"

    @patch("subprocess.run")
    def test_get_base_branch_master(self, mock_run, mock_home):
        """Test detecting master as base branch (fallback)."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="/test/repo\n"),
            MagicMock(returncode=0, stdout="HEAD branch: master\n"),
        ]

        creator = create_pr_helper.PRCreator()
        base = creator.get_base_branch()

        assert base == "master"


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
