"""Tests for jib_logging.wrappers.git module."""

from unittest.mock import MagicMock, patch

import pytest
from jib_logging.wrappers.git import GitWrapper


class TestGitWrapper:
    """Tests for GitWrapper class."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    def test_tool_name_is_git(self):
        """Test that tool_name is 'git'."""
        assert self.wrapper.tool_name == "git"


class TestGitStatus:
    """Tests for GitWrapper.status() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_status_basic(self, mock_run):
        """Test basic status command."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.status()

        mock_run.assert_called_once()
        args = mock_run.call_args[0]
        assert "status" in args
        assert "--porcelain" in args

    @patch.object(GitWrapper, "run")
    def test_status_with_cwd(self, mock_run):
        """Test status with working directory."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.status(cwd="/path/to/repo")

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == "/path/to/repo"


class TestGitAdd:
    """Tests for GitWrapper.add() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_add_files(self, mock_run):
        """Test adding specific files."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.add("file1.py", "file2.py")

        args = mock_run.call_args[0]
        assert "add" in args
        assert "file1.py" in args
        assert "file2.py" in args

    @patch.object(GitWrapper, "run")
    def test_add_all(self, mock_run):
        """Test adding all files."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.add(all=True)

        args = mock_run.call_args[0]
        assert "add" in args
        assert "-A" in args


class TestGitCommit:
    """Tests for GitWrapper.commit() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_commit_basic(self, mock_run):
        """Test basic commit."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.commit("Add feature")

        args = mock_run.call_args[0]
        assert "commit" in args
        assert "-m" in args
        assert "Add feature" in args

    @patch.object(GitWrapper, "run")
    def test_commit_with_all(self, mock_run):
        """Test commit with -a flag."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.commit("Fix bug", all=True)

        args = mock_run.call_args[0]
        assert "-a" in args

    @patch.object(GitWrapper, "run")
    def test_commit_amend(self, mock_run):
        """Test amending commit."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.commit("Updated message", amend=True)

        args = mock_run.call_args[0]
        assert "--amend" in args


class TestGitPush:
    """Tests for GitWrapper.push() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_push_basic(self, mock_run):
        """Test basic push."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.push()

        args = mock_run.call_args[0]
        assert "push" in args
        assert "origin" in args

    @patch.object(GitWrapper, "run")
    def test_push_to_remote_branch(self, mock_run):
        """Test push to specific remote/branch."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.push("upstream", "feature-branch")

        args = mock_run.call_args[0]
        assert "upstream" in args
        assert "feature-branch" in args

    @patch.object(GitWrapper, "run")
    def test_push_set_upstream(self, mock_run):
        """Test push with -u flag."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.push(set_upstream=True)

        args = mock_run.call_args[0]
        assert "-u" in args

    @patch.object(GitWrapper, "run")
    def test_push_force_with_lease(self, mock_run):
        """Test push with force-with-lease."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.push(force_with_lease=True)

        args = mock_run.call_args[0]
        assert "--force-with-lease" in args


class TestGitPull:
    """Tests for GitWrapper.pull() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_pull_basic(self, mock_run):
        """Test basic pull."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pull()

        args = mock_run.call_args[0]
        assert "pull" in args
        assert "origin" in args

    @patch.object(GitWrapper, "run")
    def test_pull_with_rebase(self, mock_run):
        """Test pull with rebase."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.pull(rebase=True)

        args = mock_run.call_args[0]
        assert "--rebase" in args


class TestGitFetch:
    """Tests for GitWrapper.fetch() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_fetch_basic(self, mock_run):
        """Test basic fetch."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.fetch()

        args = mock_run.call_args[0]
        assert "fetch" in args
        assert "origin" in args

    @patch.object(GitWrapper, "run")
    def test_fetch_all(self, mock_run):
        """Test fetch all remotes."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.fetch(all=True)

        args = mock_run.call_args[0]
        assert "--all" in args

    @patch.object(GitWrapper, "run")
    def test_fetch_with_prune(self, mock_run):
        """Test fetch with prune."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.fetch(prune=True)

        args = mock_run.call_args[0]
        assert "--prune" in args


class TestGitCheckout:
    """Tests for GitWrapper.checkout() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_checkout_branch(self, mock_run):
        """Test checkout existing branch."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.checkout("feature-branch")

        args = mock_run.call_args[0]
        assert "checkout" in args
        assert "feature-branch" in args

    @patch.object(GitWrapper, "run")
    def test_checkout_create_branch(self, mock_run):
        """Test checkout with new branch creation."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.checkout("new-branch", create=True)

        args = mock_run.call_args[0]
        assert "-b" in args
        assert "new-branch" in args

    @patch.object(GitWrapper, "run")
    def test_checkout_create_from_base(self, mock_run):
        """Test checkout with new branch from base."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.checkout("new-branch", create=True, base="origin/main")

        args = mock_run.call_args[0]
        assert "-b" in args
        assert "new-branch" in args
        assert "origin/main" in args


class TestGitBranch:
    """Tests for GitWrapper.branch() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_branch_show_current(self, mock_run):
        """Test showing current branch."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="main")

        self.wrapper.branch(show_current=True)

        args = mock_run.call_args[0]
        assert "--show-current" in args

    @patch.object(GitWrapper, "run")
    def test_branch_list_all(self, mock_run):
        """Test listing all branches."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.branch(list_all=True)

        args = mock_run.call_args[0]
        assert "-a" in args

    @patch.object(GitWrapper, "run")
    def test_branch_delete(self, mock_run):
        """Test deleting a branch."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.branch("old-branch", delete=True)

        args = mock_run.call_args[0]
        assert "-d" in args
        assert "old-branch" in args

    @patch.object(GitWrapper, "run")
    def test_branch_force_delete(self, mock_run):
        """Test force deleting a branch."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.branch("old-branch", force_delete=True)

        args = mock_run.call_args[0]
        assert "-D" in args
        assert "old-branch" in args

    def test_branch_delete_without_name_raises(self):
        """Test that delete without name raises ValueError."""
        with pytest.raises(ValueError, match="Branch name is required for delete"):
            self.wrapper.branch(delete=True)

    def test_branch_force_delete_without_name_raises(self):
        """Test that force_delete without name raises ValueError."""
        with pytest.raises(ValueError, match="Branch name is required for force_delete"):
            self.wrapper.branch(force_delete=True)


class TestGitLog:
    """Tests for GitWrapper.log() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    @patch.object(GitWrapper, "run")
    def test_log_basic(self, mock_run):
        """Test basic log."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.log()

        args = mock_run.call_args[0]
        assert "log" in args

    @patch.object(GitWrapper, "run")
    def test_log_oneline(self, mock_run):
        """Test log with oneline format."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.log(oneline=True, count=5)

        args = mock_run.call_args[0]
        assert "--oneline" in args
        assert "-5" in args


class TestGitContextExtraction:
    """Tests for context extraction in GitWrapper."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = GitWrapper()

    def test_extracts_subcommand(self):
        """Test that subcommand is extracted."""
        context = self.wrapper._extract_context(
            ("push", "origin", "main"),
            "",
            "",
        )
        assert context.get("subcommand") == "push"

    def test_extracts_commit_sha(self):
        """Test that commit SHA is extracted from output."""
        context = self.wrapper._extract_context(
            ("commit", "-m", "Add feature"),
            "[main abc1234] Add feature\n",
            "",
        )
        assert context.get("commit_sha") == "abc1234"

    def test_extracts_branch_from_checkout(self):
        """Test that branch is extracted from checkout."""
        context = self.wrapper._extract_context(
            ("checkout", "feature-branch"),
            "",
            "",
        )
        assert context.get("branch") == "feature-branch"

    def test_extracts_remote_from_push(self):
        """Test that remote is extracted from push."""
        context = self.wrapper._extract_context(
            ("push", "upstream", "main"),
            "",
            "",
        )
        assert context.get("remote") == "upstream"
