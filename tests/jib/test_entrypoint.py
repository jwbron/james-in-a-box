"""
Tests for the container entrypoint module.

Tests the container initialization logic:
- Config dataclass and property methods
- Logger with quiet mode
- Utility functions (run_cmd, chown_recursive)
- Setup functions with mocked filesystem

Note: Most setup functions require root and container environment,
so we focus on testing logic that can be unit tested.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# Load the entrypoint module
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "jib-container"))
import entrypoint


class TestConfig:
    """Tests for the Config dataclass."""

    def test_default_values(self, monkeypatch):
        """Test default configuration values."""
        # Clear environment variables to test defaults
        monkeypatch.delenv("RUNTIME_UID", raising=False)
        monkeypatch.delenv("RUNTIME_GID", raising=False)
        monkeypatch.delenv("JIB_QUIET", raising=False)

        config = entrypoint.Config()

        assert config.container_user == "jib"  # Fixed user, not configurable
        assert config.runtime_uid == 1000
        assert config.runtime_gid == 1000
        assert config.quiet is False

    def test_environment_overrides(self, monkeypatch):
        """Test that environment variables override defaults."""
        # Note: container_user is fixed as "jib", only UID/GID can be overridden
        monkeypatch.setenv("RUNTIME_UID", "2000")
        monkeypatch.setenv("RUNTIME_GID", "2000")
        monkeypatch.setenv("JIB_QUIET", "1")

        config = entrypoint.Config()

        assert config.container_user == "jib"  # Always fixed
        assert config.runtime_uid == 2000
        assert config.runtime_gid == 2000
        assert config.quiet is True

    def test_api_keys_from_environment(self, monkeypatch):
        """Test that API keys are read from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")

        config = entrypoint.Config()

        assert config.anthropic_api_key == "test-anthropic-key"
        assert config.github_token == "test-github-token"

    def test_user_home_property(self, monkeypatch):
        """Test the user_home property - always /home/jib with fixed user."""
        config = entrypoint.Config()

        assert config.user_home == Path("/home/jib")

    def test_repos_dir_property(self, monkeypatch):
        """Test the repos_dir property - always under /home/jib."""
        config = entrypoint.Config()

        assert config.repos_dir == Path("/home/jib/repos")

    def test_sharing_dir_property(self, monkeypatch):
        """Test the sharing_dir property - always under /home/jib."""
        config = entrypoint.Config()

        assert config.sharing_dir == Path("/home/jib/sharing")

    def test_derived_paths(self, monkeypatch):
        """Test all derived path properties - all under /home/jib."""
        config = entrypoint.Config()

        assert config.git_main_dir == Path("/home/jib/.git-main")
        assert config.claude_dir == Path("/home/jib/.claude")
        assert config.beads_dir == Path("/home/jib/sharing/beads")


class TestLogger:
    """Tests for the Logger class."""

    def test_info_shown_when_not_quiet(self, capsys):
        """Test that info messages are shown when not quiet."""
        logger = entrypoint.Logger(quiet=False)

        logger.info("test message")
        captured = capsys.readouterr()

        assert "test message" in captured.out

    def test_info_hidden_when_quiet(self, capsys):
        """Test that info messages are hidden when quiet."""
        logger = entrypoint.Logger(quiet=True)

        logger.info("test message")
        captured = capsys.readouterr()

        assert captured.out == ""

    def test_success_shown_when_not_quiet(self, capsys):
        """Test that success messages are shown with checkmark."""
        logger = entrypoint.Logger(quiet=False)

        logger.success("task completed")
        captured = capsys.readouterr()

        assert "task completed" in captured.out

    def test_success_hidden_when_quiet(self, capsys):
        """Test that success messages are hidden when quiet."""
        logger = entrypoint.Logger(quiet=True)

        logger.success("task completed")
        captured = capsys.readouterr()

        assert captured.out == ""

    def test_warn_always_shown(self, capsys):
        """Test that warnings are always shown, even in quiet mode."""
        logger = entrypoint.Logger(quiet=True)

        logger.warn("warning message")
        captured = capsys.readouterr()

        assert "warning message" in captured.out

    def test_error_always_shown(self, capsys):
        """Test that errors are always shown to stderr."""
        logger = entrypoint.Logger(quiet=True)

        logger.error("error message")
        captured = capsys.readouterr()

        assert "error message" in captured.err


class TestRunCmd:
    """Tests for the run_cmd utility function."""

    @patch("subprocess.run")
    def test_run_cmd_basic(self, mock_run):
        """Test basic command execution."""
        mock_run.return_value = MagicMock(returncode=0)

        result = entrypoint.run_cmd(["echo", "hello"])

        mock_run.assert_called_once()
        assert result.returncode == 0

    @patch("subprocess.run")
    def test_run_cmd_with_gosu(self, mock_run):
        """Test command execution as different user via gosu."""
        mock_run.return_value = MagicMock(returncode=0)

        entrypoint.run_cmd(["echo", "hello"], as_user=(1000, 1000))

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "gosu"
        assert call_args[1] == "1000:1000"
        assert call_args[2:] == ["echo", "hello"]

    @patch("subprocess.run")
    def test_run_cmd_with_capture(self, mock_run):
        """Test command execution with output capture."""
        mock_run.return_value = MagicMock(returncode=0, stdout="output")

        entrypoint.run_cmd(["cat", "file"], capture=True)

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True

    @patch("subprocess.run")
    def test_run_cmd_timeout(self, mock_run):
        """Test command execution with custom timeout."""
        mock_run.return_value = MagicMock(returncode=0)

        entrypoint.run_cmd(["sleep", "1"], timeout=60)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 60


class TestChownRecursive:
    """Tests for the chown_recursive utility function."""

    @patch.object(entrypoint, "run_cmd")
    def test_chown_recursive_calls_chown(self, mock_run_cmd):
        """Test that chown_recursive calls chown with correct args."""
        test_path = Path("/test/path")

        entrypoint.chown_recursive(test_path, 1000, 1000)

        mock_run_cmd.assert_called_once_with(["chown", "-R", "1000:1000", "/test/path"])


class TestSetupEnvironment:
    """Tests for the setup_environment function."""

    def test_sets_home_and_user(self, monkeypatch):
        """Test that HOME and USER are set correctly - always jib."""
        config = entrypoint.Config()

        entrypoint.setup_environment(config)

        assert os.environ["HOME"] == "/home/jib"
        assert os.environ["USER"] == "jib"

    def test_sets_python_flags(self, monkeypatch):
        """Test that Python environment flags are set."""
        config = entrypoint.Config()

        entrypoint.setup_environment(config)

        assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
        assert os.environ["PYTHONUNBUFFERED"] == "1"

    def test_sets_disable_autoupdater(self, monkeypatch):
        """Test that Claude autoupdater is disabled."""
        config = entrypoint.Config()

        entrypoint.setup_environment(config)

        assert os.environ["DISABLE_AUTOUPDATER"] == "1"

    def test_sets_beads_dir(self, monkeypatch):
        """Test that BEADS_DIR is set correctly - always under /home/jib."""
        config = entrypoint.Config()

        entrypoint.setup_environment(config)

        assert os.environ["BEADS_DIR"] == "/home/jib/sharing/beads/.beads"

    def test_updates_path(self, monkeypatch):
        """Test that PATH is updated with jib runtime scripts and local bin."""
        monkeypatch.setenv("PATH", "/usr/bin")
        config = entrypoint.Config()

        entrypoint.setup_environment(config)

        assert "/opt/jib-runtime/jib-container/bin" in os.environ["PATH"]
        assert "/home/jib/.local/bin" in os.environ["PATH"]


class TestFixRepoConfig:
    """Tests for the _fix_repo_config function."""

    @patch.object(entrypoint, "run_cmd")
    def test_sets_git_identity(self, mock_run_cmd):
        """Test that git identity is set in repo config."""
        mock_run_cmd.return_value = MagicMock(returncode=1, stdout="")

        logger = entrypoint.Logger(quiet=True)
        entrypoint._fix_repo_config(Path("/test/config"), logger)

        # Check that user.name and user.email were set
        calls = mock_run_cmd.call_args_list
        name_call = [c for c in calls if "user.name" in str(c)]
        email_call = [c for c in calls if "user.email" in str(c)]
        assert len(name_call) == 1
        assert len(email_call) == 1

    @patch.object(entrypoint, "run_cmd")
    def test_cleans_token_from_url(self, mock_run_cmd, capsys):
        """Test that tokens are stripped from git remote URLs."""
        # First two calls set identity, third gets URL with token
        mock_run_cmd.side_effect = [
            MagicMock(returncode=0),  # set user.name
            MagicMock(returncode=0),  # set user.email
            MagicMock(
                returncode=0, stdout="https://x-access-token:ghp_xxx@github.com/owner/repo.git"
            ),  # get URL
            MagicMock(returncode=0),  # set cleaned URL
        ]

        logger = entrypoint.Logger(quiet=False)
        entrypoint._fix_repo_config(Path("/test/config"), logger)

        # Check that the URL was cleaned
        calls = mock_run_cmd.call_args_list
        set_url_calls = [
            c for c in calls if "remote.origin.url" in str(c) and "https://github.com" in str(c)
        ]
        assert len(set_url_calls) == 1

    @patch.object(entrypoint, "run_cmd")
    def test_converts_ssh_to_https(self, mock_run_cmd, capsys):
        """Test that SSH URLs are converted to HTTPS."""
        mock_run_cmd.side_effect = [
            MagicMock(returncode=0),  # set user.name
            MagicMock(returncode=0),  # set user.email
            MagicMock(returncode=0, stdout="git@github.com:owner/repo.git"),  # get URL
            MagicMock(returncode=0),  # set HTTPS URL
        ]

        logger = entrypoint.Logger(quiet=False)
        entrypoint._fix_repo_config(Path("/test/config"), logger)

        # Check that URL was converted to HTTPS
        calls = mock_run_cmd.call_args_list
        set_url_calls = [c for c in calls if "https://github.com/owner/repo.git" in str(c)]
        assert len(set_url_calls) == 1


class TestSetupWorktrees:
    """Tests for the setup_worktrees function."""

    def test_returns_true_if_repos_dir_missing(self, temp_dir, monkeypatch):
        """Test that function returns True if repos directory doesn't exist."""
        # Create a fake home dir structure where repos doesn't exist
        fake_home = temp_dir / "home" / "testuser"
        fake_home.mkdir(parents=True)
        monkeypatch.setenv("RUNTIME_USER", "testuser")

        # Create a mock config that uses the temp paths
        config = MagicMock()
        config.repos_dir = fake_home / "repos"  # Doesn't exist
        config.git_main_dir = fake_home / ".git-main"

        logger = entrypoint.Logger(quiet=True)
        result = entrypoint.setup_worktrees(config, logger)

        assert result is True

    def test_returns_true_if_no_worktrees(self, temp_dir, monkeypatch):
        """Test that function returns True if no worktrees exist."""
        fake_home = temp_dir / "home" / "testuser"
        fake_home.mkdir(parents=True)
        repos_dir = fake_home / "repos"
        repos_dir.mkdir()

        config = MagicMock()
        config.repos_dir = repos_dir
        config.git_main_dir = fake_home / ".git-main"

        logger = entrypoint.Logger(quiet=True)
        result = entrypoint.setup_worktrees(config, logger)

        assert result is True

    def test_returns_false_if_git_main_missing(self, temp_dir, monkeypatch, capsys):
        """Test that function returns False if .git-main is missing but worktrees exist."""
        fake_home = temp_dir / "home" / "testuser"
        fake_home.mkdir(parents=True)

        repos_dir = fake_home / "repos"
        repos_dir.mkdir()
        repo_dir = repos_dir / "repo"
        repo_dir.mkdir()
        (repo_dir / ".git").write_text("gitdir: /original/path")

        config = MagicMock()
        config.repos_dir = repos_dir
        config.git_main_dir = fake_home / ".git-main-nonexistent"  # Doesn't exist

        logger = entrypoint.Logger(quiet=False)
        result = entrypoint.setup_worktrees(config, logger)

        assert result is False
        captured = capsys.readouterr()
        assert "FATAL" in captured.err


class TestSetupSharing:
    """Tests for the setup_sharing function."""

    @patch.object(entrypoint, "chown_recursive")
    def test_creates_subdirectories(self, mock_chown, temp_dir, monkeypatch):
        """Test that subdirectories are created."""
        sharing_dir = temp_dir / "sharing"
        sharing_dir.mkdir()

        config = MagicMock()
        config.sharing_dir = sharing_dir
        config.user_home = temp_dir
        config.runtime_uid = 1000
        config.runtime_gid = 1000

        logger = entrypoint.Logger(quiet=True)
        entrypoint.setup_sharing(config, logger)

        # Check subdirectories exist
        assert (sharing_dir / "tmp").exists()
        assert (sharing_dir / "notifications").exists()
        assert (sharing_dir / "context").exists()
        assert (sharing_dir / "tracking").exists()
        assert (sharing_dir / "traces").exists()
        assert (sharing_dir / "logs").exists()

    @patch.object(entrypoint, "chown_recursive")
    def test_creates_tmp_symlink(self, mock_chown, temp_dir, monkeypatch):
        """Test that ~/tmp symlink is created."""
        sharing_dir = temp_dir / "sharing"
        sharing_dir.mkdir()

        config = MagicMock()
        config.sharing_dir = sharing_dir
        config.user_home = temp_dir
        config.runtime_uid = 1000
        config.runtime_gid = 1000

        logger = entrypoint.Logger(quiet=True)
        entrypoint.setup_sharing(config, logger)

        # Check symlink exists
        tmp_link = temp_dir / "tmp"
        assert tmp_link.is_symlink()
        assert tmp_link.resolve() == (sharing_dir / "tmp").resolve()


class TestSetupBeads:
    """Tests for the setup_beads function."""

    def test_returns_false_if_beads_dir_missing(self, temp_dir, monkeypatch, capsys):
        """Test that function returns False if beads directory doesn't exist."""
        config = MagicMock()
        config.beads_dir = temp_dir / "nonexistent"

        logger = entrypoint.Logger(quiet=False)
        result = entrypoint.setup_beads(config, logger)

        assert result is False
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_returns_false_if_beads_not_initialized(self, temp_dir, monkeypatch, capsys):
        """Test that function returns False if beads not initialized."""
        beads_dir = temp_dir / "beads"
        beads_dir.mkdir()
        # Don't create the .beads/issues.jsonl file

        config = MagicMock()
        config.beads_dir = beads_dir

        logger = entrypoint.Logger(quiet=False)
        result = entrypoint.setup_beads(config, logger)

        assert result is False
        captured = capsys.readouterr()
        assert "not initialized" in captured.err

    @patch.object(entrypoint, "run_cmd")
    @patch.object(entrypoint, "chown_recursive")
    def test_returns_true_if_beads_valid(self, mock_chown, mock_run_cmd, temp_dir, monkeypatch):
        """Test that function returns True if beads is properly initialized."""
        # Use separate paths for sharing/beads and user_home
        sharing_dir = temp_dir / "sharing"
        beads_dir = sharing_dir / "beads"
        beads_data_dir = beads_dir / ".beads"
        beads_data_dir.mkdir(parents=True)
        (beads_data_dir / "issues.jsonl").write_text("")

        user_home = temp_dir / "home"
        user_home.mkdir()

        config = MagicMock()
        config.beads_dir = beads_dir
        config.user_home = user_home
        config.runtime_uid = 1000
        config.runtime_gid = 1000

        logger = entrypoint.Logger(quiet=True)
        result = entrypoint.setup_beads(config, logger)

        assert result is True
        # Check symlink was created
        beads_link = user_home / "beads"
        assert beads_link.is_symlink()
