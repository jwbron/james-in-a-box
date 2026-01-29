"""Tests for the network_mode module.

Tests network mode configuration and environment variable generation.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
import sys

jib_container_path = Path(__file__).parent.parent.parent / "jib-container"
sys.path.insert(0, str(jib_container_path))

from jib_lib.network_mode import (
    NetworkMode,
    get_network_mode,
    get_network_mode_env_vars,
    set_network_mode,
    write_network_env_file,
)


class TestNetworkMode:
    """Tests for NetworkMode enum."""

    def test_default_mode_value(self):
        """Test DEFAULT mode has correct value."""
        assert NetworkMode.DEFAULT.value == "default"

    def test_allow_all_mode_value(self):
        """Test ALLOW_ALL mode has correct value."""
        assert NetworkMode.ALLOW_ALL.value == "allow-all"

    def test_private_only_mode_value(self):
        """Test PRIVATE_ONLY mode has correct value."""
        assert NetworkMode.PRIVATE_ONLY.value == "private-only"


class TestGetNetworkMode:
    """Tests for get_network_mode function."""

    def test_default_when_file_not_exists(self, tmp_path, monkeypatch):
        """Test returns DEFAULT when config file doesn't exist."""
        monkeypatch.setattr(
            "jib_lib.network_mode.NETWORK_MODE_FILE",
            tmp_path / "nonexistent" / "network-mode",
        )
        assert get_network_mode() == NetworkMode.DEFAULT

    def test_reads_allow_all_mode(self, tmp_path, monkeypatch):
        """Test reads ALLOW_ALL mode from file."""
        mode_file = tmp_path / "network-mode"
        mode_file.write_text("allow-all")
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)
        assert get_network_mode() == NetworkMode.ALLOW_ALL

    def test_reads_private_only_mode(self, tmp_path, monkeypatch):
        """Test reads PRIVATE_ONLY mode from file."""
        mode_file = tmp_path / "network-mode"
        mode_file.write_text("private-only")
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)
        assert get_network_mode() == NetworkMode.PRIVATE_ONLY

    def test_reads_default_mode(self, tmp_path, monkeypatch):
        """Test reads DEFAULT mode from file."""
        mode_file = tmp_path / "network-mode"
        mode_file.write_text("default")
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)
        assert get_network_mode() == NetworkMode.DEFAULT

    def test_returns_default_for_invalid_value(self, tmp_path, monkeypatch):
        """Test returns DEFAULT for invalid mode value."""
        mode_file = tmp_path / "network-mode"
        mode_file.write_text("invalid-mode")
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)
        assert get_network_mode() == NetworkMode.DEFAULT

    def test_strips_whitespace(self, tmp_path, monkeypatch):
        """Test strips whitespace from mode value."""
        mode_file = tmp_path / "network-mode"
        mode_file.write_text("  allow-all  \n")
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)
        assert get_network_mode() == NetworkMode.ALLOW_ALL


class TestSetNetworkMode:
    """Tests for set_network_mode function."""

    def test_writes_mode_to_file(self, tmp_path, monkeypatch):
        """Test writes mode value to file."""
        mode_file = tmp_path / "jib" / "network-mode"
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)

        result = set_network_mode(NetworkMode.ALLOW_ALL)

        assert result is True
        assert mode_file.read_text() == "allow-all"

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        """Test creates parent directory if it doesn't exist."""
        mode_file = tmp_path / "nested" / "dir" / "network-mode"
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)

        result = set_network_mode(NetworkMode.PRIVATE_ONLY)

        assert result is True
        assert mode_file.parent.exists()
        assert mode_file.read_text() == "private-only"


class TestGetNetworkModeEnvVars:
    """Tests for get_network_mode_env_vars function."""

    def test_default_mode_env_vars(self):
        """Test DEFAULT mode returns correct env vars."""
        env_vars = get_network_mode_env_vars(NetworkMode.DEFAULT)
        assert env_vars == {
            "ALLOW_ALL_NETWORK": "false",
            "PUBLIC_REPO_ONLY_MODE": "false",
            "PRIVATE_REPO_MODE": "false",
        }

    def test_allow_all_mode_env_vars(self):
        """Test ALLOW_ALL mode returns correct env vars."""
        env_vars = get_network_mode_env_vars(NetworkMode.ALLOW_ALL)
        assert env_vars == {
            "ALLOW_ALL_NETWORK": "true",
            "PUBLIC_REPO_ONLY_MODE": "true",
            "PRIVATE_REPO_MODE": "false",
        }

    def test_private_only_mode_env_vars(self):
        """Test PRIVATE_ONLY mode returns correct env vars."""
        env_vars = get_network_mode_env_vars(NetworkMode.PRIVATE_ONLY)
        assert env_vars == {
            "ALLOW_ALL_NETWORK": "false",
            "PUBLIC_REPO_ONLY_MODE": "false",
            "PRIVATE_REPO_MODE": "true",
        }

    def test_allow_all_enables_public_repo_only(self):
        """Test ALLOW_ALL mode enables PUBLIC_REPO_ONLY_MODE for security."""
        env_vars = get_network_mode_env_vars(NetworkMode.ALLOW_ALL)
        assert env_vars["ALLOW_ALL_NETWORK"] == "true"
        assert env_vars["PUBLIC_REPO_ONLY_MODE"] == "true"


class TestWriteNetworkEnvFile:
    """Tests for write_network_env_file function."""

    def test_writes_env_file(self, tmp_path, monkeypatch):
        """Test writes environment file with correct content."""
        mode_file = tmp_path / "network-mode"
        mode_file.write_text("allow-all")
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)

        env_file = tmp_path / "network.env"
        monkeypatch.setattr(
            "jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path
        )

        result = write_network_env_file()

        assert result is True
        content = env_file.read_text()
        assert "ALLOW_ALL_NETWORK=true" in content
        assert "PUBLIC_REPO_ONLY_MODE=true" in content
        assert "PRIVATE_REPO_MODE=false" in content

    def test_includes_mode_comment(self, tmp_path, monkeypatch):
        """Test env file includes mode in comment."""
        mode_file = tmp_path / "network-mode"
        mode_file.write_text("private-only")
        monkeypatch.setattr("jib_lib.network_mode.NETWORK_MODE_FILE", mode_file)
        monkeypatch.setattr(
            "jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path
        )

        write_network_env_file()

        env_file = tmp_path / "network.env"
        content = env_file.read_text()
        assert "private-only" in content
