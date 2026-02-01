"""Tests for the network_mode module.

Tests private mode configuration and environment variable generation.
Mode is now determined purely from CLI flags with no persistent state.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


jib_container_path = Path(__file__).parent.parent.parent / "jib-container"
sys.path.insert(0, str(jib_container_path))

from jib_lib.network_mode import (
    PrivateMode,
    _write_network_env_file,
    ensure_gateway_mode,
    get_gateway_current_mode,
    get_private_mode_env_vars,
)


class TestPrivateMode:
    """Tests for PrivateMode enum."""

    def test_private_mode_value(self):
        """Test PRIVATE mode has correct value."""
        assert PrivateMode.PRIVATE.value == "private"

    def test_public_mode_value(self):
        """Test PUBLIC mode has correct value."""
        assert PrivateMode.PUBLIC.value == "public"


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


class TestWriteNetworkEnvFile:
    """Tests for _write_network_env_file function."""

    def test_writes_env_file_public_mode(self, tmp_path, monkeypatch):
        """Test writes environment file for public mode."""
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        result = _write_network_env_file(PrivateMode.PUBLIC)

        assert result is True
        env_file = tmp_path / "network.env"
        content = env_file.read_text()
        assert "PRIVATE_MODE=false" in content
        assert "public" in content  # Mode in comment

    def test_writes_env_file_private_mode(self, tmp_path, monkeypatch):
        """Test writes environment file for private mode."""
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        result = _write_network_env_file(PrivateMode.PRIVATE)

        assert result is True
        env_file = tmp_path / "network.env"
        content = env_file.read_text()
        assert "PRIVATE_MODE=true" in content
        assert "private" in content  # Mode in comment

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        """Test creates parent directory if it doesn't exist."""
        nested_dir = tmp_path / "nested" / "config"
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", nested_dir)

        result = _write_network_env_file(PrivateMode.PUBLIC)

        assert result is True
        assert (nested_dir / "network.env").exists()


class TestGetGatewayCurrentMode:
    """Tests for get_gateway_current_mode function."""

    def test_returns_private_when_gateway_reports_private(self):
        """Test returns PRIVATE when gateway health reports private_mode=true."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"private_mode": True}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("jib_lib.network_mode.urllib.request.urlopen", return_value=mock_response):
            result = get_gateway_current_mode()

        assert result == PrivateMode.PRIVATE

    def test_returns_public_when_gateway_reports_public(self):
        """Test returns PUBLIC when gateway health reports private_mode=false."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"private_mode": False}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("jib_lib.network_mode.urllib.request.urlopen", return_value=mock_response):
            result = get_gateway_current_mode()

        assert result == PrivateMode.PUBLIC

    def test_returns_none_when_gateway_not_reachable(self):
        """Test returns None when gateway is not reachable."""
        with patch(
            "jib_lib.network_mode.urllib.request.urlopen",
            side_effect=Exception("Connection refused"),
        ):
            result = get_gateway_current_mode()

        assert result is None


class TestEnsureGatewayMode:
    """Tests for ensure_gateway_mode function."""

    def test_no_restart_when_mode_matches(self, tmp_path, monkeypatch):
        """Test does not restart gateway when mode already matches."""
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        with (
            patch(
                "jib_lib.network_mode.get_gateway_current_mode",
                return_value=PrivateMode.PUBLIC,
            ),
            patch("jib_lib.network_mode.subprocess.run") as mock_run,
        ):
            result = ensure_gateway_mode(PrivateMode.PUBLIC, quiet=True)

        assert result is True
        # Should not have called systemctl or docker
        mock_run.assert_not_called()

    def test_restarts_when_mode_differs(self, tmp_path, monkeypatch):
        """Test restarts gateway when mode differs."""
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch(
                "jib_lib.network_mode.get_gateway_current_mode",
                return_value=PrivateMode.PUBLIC,
            ),
            patch("jib_lib.network_mode.subprocess.run", return_value=mock_result) as mock_run,
        ):
            result = ensure_gateway_mode(PrivateMode.PRIVATE, quiet=True)

        assert result is True
        # Should have called systemctl to restart
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "systemctl" in call_args
        assert "restart" in call_args

    def test_falls_back_to_docker_restart(self, tmp_path, monkeypatch):
        """Test falls back to docker restart if systemctl fails."""
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        systemctl_result = MagicMock()
        systemctl_result.returncode = 1

        docker_result = MagicMock()
        docker_result.returncode = 0

        with (
            patch(
                "jib_lib.network_mode.get_gateway_current_mode",
                return_value=PrivateMode.PUBLIC,
            ),
            patch(
                "jib_lib.network_mode.subprocess.run",
                side_effect=[systemctl_result, docker_result],
            ) as mock_run,
        ):
            result = ensure_gateway_mode(PrivateMode.PRIVATE, quiet=True)

        assert result is True
        assert mock_run.call_count == 2
        # Second call should be docker restart
        docker_call = mock_run.call_args_list[1][0][0]
        assert "docker" in docker_call
        assert "restart" in docker_call

    def test_gateway_not_running_succeeds(self, tmp_path, monkeypatch):
        """Test succeeds when gateway is not running (will start with correct mode)."""
        monkeypatch.setattr("jib_lib.network_mode.Config.USER_CONFIG_DIR", tmp_path)

        with patch("jib_lib.network_mode.get_gateway_current_mode", return_value=None):
            result = ensure_gateway_mode(PrivateMode.PRIVATE, quiet=True)

        assert result is True
        # Should have written env file
        env_file = tmp_path / "network.env"
        assert env_file.exists()
        assert "PRIVATE_MODE=true" in env_file.read_text()
