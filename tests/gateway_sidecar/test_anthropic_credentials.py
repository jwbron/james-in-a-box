"""Tests for Anthropic credentials manager."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add gateway-sidecar to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "gateway-sidecar"))

from anthropic_credentials import (
    AnthropicCredential,
    AnthropicCredentialsManager,
    reset_credentials_manager,
)


class TestAnthropicCredential:
    """Test AnthropicCredential dataclass."""

    def test_api_key_type(self):
        """Test API key credential type."""
        cred = AnthropicCredential(token="sk-ant-test", token_type="api_key")
        assert cred.is_api_key
        assert not cred.is_oauth
        assert cred.token == "sk-ant-test"

    def test_oauth_type(self):
        """Test OAuth credential type."""
        cred = AnthropicCredential(token="oauth-token", token_type="oauth")
        assert cred.is_oauth
        assert not cred.is_api_key
        assert cred.token == "oauth-token"


class TestAnthropicCredentialsManager:
    """Test AnthropicCredentialsManager."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset global manager before each test."""
        reset_credentials_manager()
        yield
        reset_credentials_manager()

    def test_load_api_key_from_file(self, tmp_path):
        """Test loading API key from config file."""
        # Create config file
        api_key_file = tmp_path / "anthropic-api-key"
        api_key_file.write_text("sk-ant-test-key-123")

        # Clear any existing auth method env var
        env = {"ANTHROPIC_AUTH_METHOD": "api_key"}
        if "ANTHROPIC_API_KEY" in os.environ:
            env["ANTHROPIC_API_KEY"] = ""  # Clear so file is used

        with patch.dict(os.environ, env, clear=False):
            # Need to clear ANTHROPIC_API_KEY entirely to test file loading
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
                manager = AnthropicCredentialsManager(config_dir=tmp_path)
                cred = manager.get_credential()

        assert cred is not None
        assert cred.is_api_key
        assert cred.token == "sk-ant-test-key-123"

    def test_load_api_key_from_env(self, tmp_path):
        """Test loading API key from environment variable."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-env-key",
            "ANTHROPIC_AUTH_METHOD": "api_key",
        }
        with patch.dict(os.environ, env, clear=False):
            manager = AnthropicCredentialsManager(config_dir=tmp_path)
            cred = manager.get_credential()

            assert cred is not None
            assert cred.is_api_key
            assert cred.token == "sk-ant-env-key"

    def test_env_takes_precedence_over_file(self, tmp_path):
        """Test that environment variable takes precedence over file."""
        # Create config file
        api_key_file = tmp_path / "anthropic-api-key"
        api_key_file.write_text("sk-ant-file-key")

        env = {
            "ANTHROPIC_API_KEY": "sk-ant-env-key",
            "ANTHROPIC_AUTH_METHOD": "api_key",
        }
        with patch.dict(os.environ, env, clear=False):
            manager = AnthropicCredentialsManager(config_dir=tmp_path)
            cred = manager.get_credential()

            assert cred is not None
            assert cred.token == "sk-ant-env-key"  # Env takes precedence

    def test_oauth_mode_returns_none(self, tmp_path):
        """Test that OAuth mode returns None (tokens managed by Claude Code)."""
        with patch.dict(os.environ, {"ANTHROPIC_AUTH_METHOD": "oauth"}):
            manager = AnthropicCredentialsManager(config_dir=tmp_path)
            cred = manager.get_credential()

            assert cred is None  # OAuth tokens not managed by gateway

    def test_missing_api_key_returns_none(self, tmp_path):
        """Test that missing API key returns None."""
        manager = AnthropicCredentialsManager(config_dir=tmp_path)
        cred = manager.get_credential()

        assert cred is None

    def test_caching(self, tmp_path):
        """Test that credentials are cached."""
        api_key_file = tmp_path / "anthropic-api-key"
        api_key_file.write_text("sk-ant-cached-key")

        env = {"ANTHROPIC_AUTH_METHOD": "api_key", "ANTHROPIC_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            manager = AnthropicCredentialsManager(config_dir=tmp_path)

            # First access loads
            cred1 = manager.get_credential()
            assert cred1.token == "sk-ant-cached-key"

            # Modify file (should not affect cached value)
            api_key_file.write_text("sk-ant-new-key")

            # Second access uses cache
            cred2 = manager.get_credential()
            assert cred2.token == "sk-ant-cached-key"

    def test_reload(self, tmp_path):
        """Test that reload clears cache."""
        api_key_file = tmp_path / "anthropic-api-key"
        api_key_file.write_text("sk-ant-original-key")

        env = {"ANTHROPIC_AUTH_METHOD": "api_key", "ANTHROPIC_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            manager = AnthropicCredentialsManager(config_dir=tmp_path)

            # First access
            cred1 = manager.get_credential()
            assert cred1.token == "sk-ant-original-key"

            # Modify file and reload
            api_key_file.write_text("sk-ant-new-key")
            manager.reload()

            # Should get new value
            cred2 = manager.get_credential()
            assert cred2.token == "sk-ant-new-key"

    def test_auth_method_from_config_yaml(self, tmp_path):
        """Test reading auth method from config.yaml."""
        # Create config.yaml with oauth method
        config_file = tmp_path / "config.yaml"
        config_file.write_text("anthropic_auth_method: oauth\n")

        manager = AnthropicCredentialsManager(config_dir=tmp_path)
        cred = manager.get_credential()

        assert cred is None  # OAuth mode returns None

    def test_auth_method_env_overrides_config(self, tmp_path):
        """Test that env var overrides config.yaml for auth method."""
        # Create config.yaml with oauth method
        config_file = tmp_path / "config.yaml"
        config_file.write_text("anthropic_auth_method: oauth\n")

        # Create API key file
        api_key_file = tmp_path / "anthropic-api-key"
        api_key_file.write_text("sk-ant-test-key")

        # Set env to api_key mode
        with patch.dict(os.environ, {"ANTHROPIC_AUTH_METHOD": "api_key"}):
            manager = AnthropicCredentialsManager(config_dir=tmp_path)
            cred = manager.get_credential()

            assert cred is not None  # Should load API key
            assert cred.is_api_key
