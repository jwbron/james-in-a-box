"""Tests for the network_mode module.

Tests private mode configuration and environment variable generation.
"""

# Import the module under test
import sys
from pathlib import Path


jib_container_path = Path(__file__).parent.parent.parent / "jib-container"
sys.path.insert(0, str(jib_container_path))

from jib_lib.network_mode import (
    PrivateMode,
    get_private_mode,
    get_private_mode_env_vars,
    set_private_mode,
    write_private_mode_env_file,
)


class TestPrivateMode:
    """Tests for PrivateMode enum."""

    def test_private_mode_value(self):
        """Test PRIVATE mode has correct value."""
        assert PrivateMode.PRIVATE.value == "private"

    def test_public_mode_value(self):
        """Test PUBLIC mode has correct value."""
        assert PrivateMode.PUBLIC.value == "public"


class TestGetPrivateMode:
    """Tests for get_private_mode function."""

    def test_public_when_file_not_exists(self, tmp_path, monkeypatch):
        """Test returns PUBLIC when config file doesn't exist."""
        monkeypatch.setattr(
            "jib_lib.network_mode.PRIVATE_MODE_FILE",
            tmp_path / "nonexistent" / "private-mode",
        )
        assert get_private_mode() == PrivateMode.PUBLIC

    def test_reads_private_mode(self, tmp_path, monkeypatch):
        """Test reads PRIVATE mode from file."""
        mode_file = tmp_path / "private-mode"
        mode_file.write_text("private")
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)
        assert get_private_mode() == PrivateMode.PRIVATE

    def test_reads_public_mode(self, tmp_path, monkeypatch):
        """Test reads PUBLIC mode from file."""
        mode_file = tmp_path / "private-mode"
        mode_file.write_text("public")
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)
        assert get_private_mode() == PrivateMode.PUBLIC

    def test_returns_public_for_invalid_value(self, tmp_path, monkeypatch):
        """Test returns PUBLIC for invalid mode value."""
        mode_file = tmp_path / "private-mode"
        mode_file.write_text("invalid-mode")
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)
        assert get_private_mode() == PrivateMode.PUBLIC

    def test_strips_whitespace(self, tmp_path, monkeypatch):
        """Test strips whitespace from mode value."""
        mode_file = tmp_path / "private-mode"
        mode_file.write_text("  private  \n")
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)
        assert get_private_mode() == PrivateMode.PRIVATE


class TestSetPrivateMode:
    """Tests for set_private_mode function."""

    def test_writes_mode_to_file(self, tmp_path, monkeypatch):
        """Test writes mode value to file."""
        mode_file = tmp_path / "jib" / "private-mode"
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)

        result = set_private_mode(PrivateMode.PRIVATE)

        assert result is True
        assert mode_file.read_text() == "private"

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        """Test creates parent directory if it doesn't exist."""
        mode_file = tmp_path / "nested" / "dir" / "private-mode"
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)

        result = set_private_mode(PrivateMode.PUBLIC)

        assert result is True
        assert mode_file.parent.exists()
        assert mode_file.read_text() == "public"


class TestGetPrivateModeEnvVars:
    """Tests for get_private_mode_env_vars function."""

    def test_public_mode_env_vars(self):
        """Test PUBLIC mode returns PRIVATE_MODE=false."""
        env_vars = get_private_mode_env_vars(PrivateMode.PUBLIC)
        assert env_vars == {"PRIVATE_MODE": "false"}

    def test_private_mode_env_vars(self):
        """Test PRIVATE mode returns PRIVATE_MODE=true."""
        env_vars = get_private_mode_env_vars(PrivateMode.PRIVATE)
        assert env_vars == {"PRIVATE_MODE": "true"}


class TestWritePrivateModeEnvFile:
    """Tests for write_private_mode_env_file function."""

    def test_writes_env_file_public_mode(self, tmp_path, monkeypatch):
        """Test writes environment file for public mode."""
        mode_file = tmp_path / "private-mode"
        mode_file.write_text("public")
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        result = write_private_mode_env_file()

        assert result is True
        env_file = tmp_path / "network.env"
        content = env_file.read_text()
        assert "PRIVATE_MODE=false" in content

    def test_writes_env_file_private_mode(self, tmp_path, monkeypatch):
        """Test writes environment file for private mode."""
        mode_file = tmp_path / "private-mode"
        mode_file.write_text("private")
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        result = write_private_mode_env_file()

        assert result is True
        env_file = tmp_path / "network.env"
        content = env_file.read_text()
        assert "PRIVATE_MODE=true" in content

    def test_includes_mode_comment(self, tmp_path, monkeypatch):
        """Test env file includes mode in comment."""
        mode_file = tmp_path / "private-mode"
        mode_file.write_text("private")
        monkeypatch.setattr("jib_lib.network_mode.PRIVATE_MODE_FILE", mode_file)
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        write_private_mode_env_file()

        env_file = tmp_path / "network.env"
        content = env_file.read_text()
        assert "private" in content
