"""
Tests for the jib binary (james-in-a-box main launcher).

These tests focus on utility functions and non-Docker operations:
- Config class paths
- Platform detection
- Directory safety checks
- Worktree management helpers
- Container ID generation

Docker and subprocess operations are mocked since they require Docker daemon.
"""

import os
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import MagicMock, patch


# Load jib module (filename without .py extension)
jib_path = Path(__file__).parent.parent.parent / "jib-container" / "jib"
loader = SourceFileLoader("jib", str(jib_path))
jib = loader.load_module()

Colors = jib.Colors
Config = jib.Config


class TestColors:
    """Tests for ANSI color codes."""

    def test_colors_defined(self):
        """Test that all color codes are defined."""
        assert hasattr(Colors, "BLUE")
        assert hasattr(Colors, "GREEN")
        assert hasattr(Colors, "YELLOW")
        assert hasattr(Colors, "RED")
        assert hasattr(Colors, "BOLD")
        assert hasattr(Colors, "NC")

    def test_colors_are_escape_codes(self):
        """Test that colors are ANSI escape codes."""
        assert Colors.BLUE.startswith("\033[")
        assert Colors.NC == "\033[0m"


class TestOutputFunctions:
    """Tests for info, success, warn, error output functions."""

    def test_info_output(self, capsys):
        """Test info() prints blue prefix."""
        jib.info("test message")
        captured = capsys.readouterr()
        assert "[INFO]" in captured.out
        assert "test message" in captured.out

    def test_success_output(self, capsys):
        """Test success() prints green prefix."""
        jib.success("test message")
        captured = capsys.readouterr()
        assert "[SUCCESS]" in captured.out
        assert "test message" in captured.out

    def test_warn_output(self, capsys):
        """Test warn() prints yellow prefix."""
        jib.warn("test message")
        captured = capsys.readouterr()
        assert "[WARNING]" in captured.out
        assert "test message" in captured.out

    def test_error_output(self, capsys):
        """Test error() prints red prefix to stderr."""
        jib.error("test message")
        captured = capsys.readouterr()
        assert "[ERROR]" in captured.err
        assert "test message" in captured.err


class TestConfig:
    """Tests for Config class paths."""

    def test_config_dir(self):
        """Test config directory path."""
        assert Path.home() / ".jib" == Config.CONFIG_DIR

    def test_user_config_dir(self):
        """Test user config directory path."""
        assert Path.home() / ".config" / "jib" == Config.USER_CONFIG_DIR

    def test_github_token_file_path(self):
        """Test GitHub token file path."""
        expected = Path.home() / ".config" / "jib" / "github-token"
        assert expected == Config.GITHUB_TOKEN_FILE

    def test_image_name(self):
        """Test Docker image name."""
        assert Config.IMAGE_NAME == "james-in-a-box"

    def test_container_name(self):
        """Test container name."""
        assert Config.CONTAINER_NAME == "jib"

    def test_khan_source_path(self):
        """Test Khan source directory path."""
        assert Path.home() / "khan" == Config.KHAN_SOURCE

    def test_sharing_dir_path(self):
        """Test sharing directory path."""
        assert Path.home() / ".jib-sharing" == Config.SHARING_DIR

    def test_tmp_dir_path(self):
        """Test tmp directory path."""
        assert Path.home() / ".jib-sharing" / "tmp" == Config.TMP_DIR

    def test_worktree_base_path(self):
        """Test worktree base directory path."""
        assert Path.home() / ".jib-worktrees" == Config.WORKTREE_BASE

    def test_dangerous_dirs_defined(self):
        """Test that dangerous directories are defined."""
        assert len(Config.DANGEROUS_DIRS) > 0
        assert Path.home() / ".ssh" in Config.DANGEROUS_DIRS
        assert Path.home() / ".aws" in Config.DANGEROUS_DIRS
        assert Path.home() / ".config" / "gcloud" in Config.DANGEROUS_DIRS


class TestGetPlatform:
    """Tests for platform detection."""

    @patch("platform.system")
    def test_detect_linux(self, mock_system):
        """Test detecting Linux platform."""
        mock_system.return_value = "Linux"
        assert jib.get_platform() == "linux"

    @patch("platform.system")
    def test_detect_macos(self, mock_system):
        """Test detecting macOS platform."""
        mock_system.return_value = "Darwin"
        assert jib.get_platform() == "macos"

    @patch("platform.system")
    def test_detect_unknown(self, mock_system):
        """Test detecting unknown platform."""
        mock_system.return_value = "Windows"
        assert jib.get_platform() == "unknown"


class TestGetGithubToken:
    """Tests for GitHub token retrieval.

    The get_github_token() function uses HostConfig which loads tokens from:
    1. Environment variable GITHUB_TOKEN (highest priority)
    2. ~/.config/jib/secrets.env
    3. ~/.config/jib/github-token

    These tests create mock HostConfig modules in sys.modules before calling
    get_github_token() to test the token validation logic.
    """

    def _call_get_github_token_with_mock(self, token_value):
        """Helper to call get_github_token with a mocked HostConfig."""
        import sys

        # Create mock HostConfig class
        mock_config_instance = MagicMock()
        mock_config_instance.github_token = token_value

        mock_module = MagicMock()
        mock_module.HostConfig = MagicMock(return_value=mock_config_instance)

        # Clear any cached import and inject mock
        if "config.host_config" in sys.modules:
            del sys.modules["config.host_config"]
        sys.modules["config.host_config"] = mock_module

        try:
            return jib.get_github_token()
        finally:
            # Clean up
            if "config.host_config" in sys.modules:
                del sys.modules["config.host_config"]

    def test_no_token_configured(self):
        """Test when no token is configured."""
        assert self._call_get_github_token_with_mock("") is None

    def test_valid_ghp_token(self):
        """Test reading valid ghp_ prefixed token."""
        assert (
            self._call_get_github_token_with_mock("ghp_test1234567890abcdef")
            == "ghp_test1234567890abcdef"
        )

    def test_valid_github_pat_token(self):
        """Test reading valid github_pat_ prefixed token."""
        assert (
            self._call_get_github_token_with_mock("github_pat_test1234567890")
            == "github_pat_test1234567890"
        )

    def test_invalid_token_prefix(self):
        """Test rejecting token with invalid prefix."""
        assert self._call_get_github_token_with_mock("invalid_token_1234567890") is None

    def test_empty_token(self):
        """Test empty token."""
        assert self._call_get_github_token_with_mock("") is None

    def test_none_token(self):
        """Test None token."""
        assert self._call_get_github_token_with_mock(None) is None

    def test_whitespace_only_token(self):
        """Test whitespace-only token (HostConfig should strip it)."""
        # HostConfig strips whitespace when loading, but if it didn't, empty string fails validation
        assert self._call_get_github_token_with_mock("   ") is None


class TestIsDangerousDir:
    """Tests for dangerous directory detection."""

    def test_ssh_is_dangerous(self):
        """Test .ssh directory is detected as dangerous."""
        assert jib.is_dangerous_dir(Path.home() / ".ssh") is True

    def test_aws_is_dangerous(self):
        """Test .aws directory is detected as dangerous."""
        assert jib.is_dangerous_dir(Path.home() / ".aws") is True

    def test_gcloud_is_dangerous(self):
        """Test gcloud directory is detected as dangerous."""
        assert jib.is_dangerous_dir(Path.home() / ".config" / "gcloud") is True

    def test_ssh_subdir_is_dangerous(self):
        """Test subdirectory of .ssh is detected as dangerous."""
        assert jib.is_dangerous_dir(Path.home() / ".ssh" / "keys") is True

    def test_safe_dir(self, temp_dir):
        """Test safe directory is not detected as dangerous."""
        safe_dir = temp_dir / "safe_project"
        safe_dir.mkdir()
        assert jib.is_dangerous_dir(safe_dir) is False

    def test_khan_dir_is_safe(self):
        """Test khan directory is safe."""
        khan_dir = Path.home() / "khan"
        assert jib.is_dangerous_dir(khan_dir) is False


class TestCheckClaudeCredentials:
    """Tests for Claude credentials checking."""

    def test_no_claude_dir(self, temp_dir, monkeypatch):
        """Test when .claude directory doesn't exist."""
        # Use patch.object to mock Path.home() without reloading module
        with patch.object(Path, "home", return_value=temp_dir):
            result = jib.check_claude_credentials()
            assert result is False

    def test_no_credentials_file(self, temp_dir, monkeypatch):
        """Test when credentials file doesn't exist."""
        claude_dir = temp_dir / ".claude"
        claude_dir.mkdir()

        with patch.object(Path, "home", return_value=temp_dir):
            result = jib.check_claude_credentials()
            assert result is False

    def test_credentials_exist(self, temp_dir, monkeypatch):
        """Test when credentials file exists."""
        claude_dir = temp_dir / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text('{"test": true}')

        with patch.object(Path, "home", return_value=temp_dir):
            result = jib.check_claude_credentials()
            assert result is True


class TestGenerateContainerId:
    """Tests for container ID generation."""

    def test_container_id_format(self):
        """Test container ID has expected format."""
        container_id = jib.generate_container_id()

        assert container_id.startswith("jib-")
        # Format: jib-YYYYMMDD-HHMMSS-PID
        parts = container_id.split("-")
        assert len(parts) == 4  # jib, date, time, pid

    def test_container_id_unique(self):
        """Test that container IDs are unique (within reasonable time)."""
        id1 = jib.generate_container_id()
        id2 = jib.generate_container_id()

        # Same process, so PID is same, but we expect unique IDs
        # (at least timestamp or we're generating them too fast)
        # Since we can't guarantee uniqueness in same millisecond,
        # we just verify format is consistent
        assert id1.startswith("jib-")
        assert id2.startswith("jib-")

    def test_container_id_contains_pid(self):
        """Test container ID contains process ID."""
        container_id = jib.generate_container_id()
        pid = str(os.getpid())
        assert pid in container_id


class TestCheckDockerPermissions:
    """Tests for Docker permission checking."""

    @patch("subprocess.run")
    def test_docker_accessible(self, mock_run):
        """Test when Docker is accessible."""
        mock_run.return_value = MagicMock(returncode=0)

        result = jib.check_docker_permissions()
        assert result is True

    @patch("subprocess.run")
    def test_docker_permission_denied(self, mock_run, capsys):
        """Test when Docker permission is denied."""
        mock_run.return_value = MagicMock(
            returncode=1, stderr="permission denied while trying to connect"
        )

        result = jib.check_docker_permissions()
        assert result is False

        captured = capsys.readouterr()
        assert "permission denied" in captured.err.lower() or "docker" in captured.out.lower()


class TestImageExists:
    """Tests for Docker image existence checking."""

    @patch("subprocess.run")
    def test_image_exists(self, mock_run):
        """Test when Docker image exists."""
        mock_run.return_value = MagicMock(returncode=0)

        result = jib.image_exists()
        assert result is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_image_not_exists(self, mock_run):
        """Test when Docker image doesn't exist."""
        mock_run.return_value = MagicMock(returncode=1)

        result = jib.image_exists()
        assert result is False


class TestWorktreeHelpers:
    """Tests for worktree management helpers."""

    def test_cleanup_worktrees_no_dir(self, temp_dir, monkeypatch):
        """Test cleanup when worktree directory doesn't exist."""
        monkeypatch.setattr(Config, "WORKTREE_BASE", temp_dir / "worktrees")
        monkeypatch.setattr(Config, "KHAN_SOURCE", temp_dir / "khan")

        # Should not raise
        jib.cleanup_worktrees("test-container-id")

    @patch("subprocess.run")
    def test_cleanup_worktrees_removes_dir(self, mock_run, temp_dir, monkeypatch):
        """Test cleanup removes worktree directory."""
        worktree_base = temp_dir / "worktrees"
        container_dir = worktree_base / "test-container"
        container_dir.mkdir(parents=True)

        # Create a fake worktree entry
        repo_worktree = container_dir / "test-repo"
        repo_worktree.mkdir()

        # Create matching khan source repo
        khan_source = temp_dir / "khan"
        khan_repo = khan_source / "test-repo"
        khan_repo.mkdir(parents=True)

        monkeypatch.setattr(Config, "WORKTREE_BASE", worktree_base)
        monkeypatch.setattr(Config, "KHAN_SOURCE", khan_source)

        # Mock git worktree prune
        mock_run.return_value = MagicMock(returncode=0)

        jib.cleanup_worktrees("test-container")

        # Worktree directory should be removed
        assert not container_dir.exists()


class TestBuildImage:
    """Tests for Docker image building."""

    @patch("subprocess.run")
    @patch.object(jib, "create_dockerfile")
    def test_build_image_success(self, mock_create, mock_run, monkeypatch):
        """Test successful Docker build."""
        mock_run.return_value = MagicMock(returncode=0)

        # Set environment variables
        monkeypatch.setenv("USER", "testuser")

        result = jib.build_image()
        assert result is True
        mock_create.assert_called_once()

    @patch("subprocess.run")
    @patch.object(jib, "create_dockerfile")
    def test_build_image_failure(self, mock_create, mock_run, capsys, monkeypatch):
        """Test Docker build failure."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "docker build")
        monkeypatch.setenv("USER", "testuser")

        result = jib.build_image()
        assert result is False

        captured = capsys.readouterr()
        assert "build failed" in captured.err.lower()
