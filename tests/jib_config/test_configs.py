"""
Tests for service-specific configuration classes.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jib_config.configs.confluence import ConfluenceConfig
from jib_config.configs.gateway import GatewayConfig, RateLimitConfig
from jib_config.configs.github import GitHubConfig
from jib_config.configs.jira import JiraConfig
from jib_config.configs.llm import LLMConfig, LLMProvider
from jib_config.configs.slack import SlackConfig


class TestSlackConfig:
    """Tests for SlackConfig."""

    def test_valid_config(self):
        """Test valid Slack configuration."""
        config = SlackConfig(
            bot_token="xoxb-1234567890-abcdefghijklmnop",
            app_token="xapp-1-A12345678-1234567890-abcdef",
            channel="C12345678",
        )
        result = config.validate()
        assert result.is_valid

    def test_missing_bot_token(self):
        """Test validation fails with missing bot token."""
        config = SlackConfig(channel="C12345678")
        result = config.validate()
        assert not result.is_valid
        assert any("bot_token" in e for e in result.errors)

    def test_invalid_bot_token_prefix(self):
        """Test validation fails with invalid token prefix."""
        config = SlackConfig(
            bot_token="invalid-token-format",
            channel="C12345678",
        )
        result = config.validate()
        assert not result.is_valid
        assert any("xoxb-" in e or "xoxp-" in e for e in result.errors)

    def test_missing_channel_warning(self):
        """Test warning when channel is not set."""
        config = SlackConfig(bot_token="xoxb-1234567890-abcdefghijklmnop")
        result = config.validate()
        assert result.is_valid  # Still valid, just warns
        assert any("channel" in w for w in result.warnings)

    def test_to_dict_masks_tokens(self):
        """Test that to_dict masks sensitive values."""
        config = SlackConfig(
            bot_token="xoxb-secret-token-here",
            app_token="xapp-secret-app-token",
            channel="C12345678",
        )
        d = config.to_dict()
        assert "xoxb" in d["bot_token"]
        assert "secret" not in d["bot_token"]
        assert "*" in d["bot_token"]

    def test_from_env(self, monkeypatch, temp_dir):
        """Test loading from environment variables."""
        monkeypatch.setenv("SLACK_TOKEN", "xoxb-from-env-token12345")
        monkeypatch.setenv("SLACK_CHANNEL", "C99999999")
        monkeypatch.setenv("HOME", str(temp_dir))

        config = SlackConfig.from_env()
        assert config.bot_token == "xoxb-from-env-token12345"
        assert config.channel == "C99999999"

    def test_from_secrets_file(self, monkeypatch, temp_dir):
        """Test loading from secrets.env file."""
        monkeypatch.setenv("HOME", str(temp_dir))
        monkeypatch.delenv("SLACK_TOKEN", raising=False)

        secrets_dir = temp_dir / ".config" / "jib"
        secrets_dir.mkdir(parents=True)
        secrets_file = secrets_dir / "secrets.env"
        secrets_file.write_text('SLACK_TOKEN="xoxb-from-file-token123"')

        config = SlackConfig.from_env()
        assert config.bot_token == "xoxb-from-file-token123"


class TestGitHubConfig:
    """Tests for GitHubConfig."""

    def test_valid_config(self):
        """Test valid GitHub configuration."""
        config = GitHubConfig(token="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        result = config.validate()
        assert result.is_valid

    def test_missing_token(self):
        """Test validation fails with missing token."""
        config = GitHubConfig()
        result = config.validate()
        assert not result.is_valid
        assert any("token" in e for e in result.errors)

    def test_invalid_token_prefix(self):
        """Test validation fails with invalid token prefix."""
        config = GitHubConfig(token="invalid-token-format")
        result = config.validate()
        assert not result.is_valid

    def test_all_token_prefixes_valid(self):
        """Test all valid GitHub token prefixes."""
        valid_prefixes = ["ghp_", "github_pat_", "ghs_", "gho_", "ghu_"]
        for prefix in valid_prefixes:
            token = prefix + "x" * 30
            config = GitHubConfig(token=token)
            result = config.validate()
            assert result.is_valid, f"Token with prefix {prefix} should be valid"

    def test_expired_token_error(self):
        """Test validation fails with expired token."""
        from datetime import datetime, timedelta

        config = GitHubConfig(
            token="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            token_expires_at=datetime.now() - timedelta(hours=1),
        )
        result = config.validate()
        assert not result.is_valid
        assert any("expired" in e.lower() for e in result.errors)

    def test_expiring_soon_warning(self):
        """Test warning when token expires soon."""
        from datetime import datetime, timedelta

        config = GitHubConfig(
            token="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            token_expires_at=datetime.now() + timedelta(minutes=2),
        )
        result = config.validate()
        assert result.is_valid
        assert any("5 minutes" in w for w in result.warnings)

    def test_to_dict_masks_tokens(self):
        """Test that to_dict masks all tokens."""
        config = GitHubConfig(
            token="ghp_secret_token_here",
            readonly_token="ghp_readonly_secret",
            incognito_token="ghp_incognito_secret",
        )
        d = config.to_dict()
        assert "secret" not in d["token"]
        assert "*" in d["token"]

    def test_is_token_expired_property(self):
        """Test is_token_expired property."""
        from datetime import datetime, timedelta

        # Not expired
        config = GitHubConfig(
            token="ghp_test",
            token_expires_at=datetime.now() + timedelta(hours=1),
        )
        assert not config.is_token_expired

        # Expired
        config.token_expires_at = datetime.now() - timedelta(hours=1)
        assert config.is_token_expired

        # No expiration set
        config.token_expires_at = None
        assert not config.is_token_expired


class TestLLMConfig:
    """Tests for LLMConfig."""

    def test_valid_anthropic_config(self):
        """Test valid Anthropic configuration."""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx",
        )
        result = config.validate()
        assert result.is_valid

    def test_missing_anthropic_key(self):
        """Test validation fails with missing Anthropic key."""
        config = LLMConfig(provider=LLMProvider.ANTHROPIC)
        result = config.validate()
        assert not result.is_valid

    def test_invalid_anthropic_key_prefix(self):
        """Test validation fails with invalid Anthropic key prefix."""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="invalid-key-format",
        )
        result = config.validate()
        assert not result.is_valid

    def test_valid_google_config(self):
        """Test valid Google configuration."""
        config = LLMConfig(
            provider=LLMProvider.GOOGLE,
            google_api_key="AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxx",
        )
        result = config.validate()
        assert result.is_valid

    def test_missing_google_key(self):
        """Test validation fails with missing Google key."""
        config = LLMConfig(provider=LLMProvider.GOOGLE)
        result = config.validate()
        assert not result.is_valid

    def test_custom_base_url_warning(self):
        """Test warning when custom base URL is set."""
        config = LLMConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx",
            anthropic_base_url="https://custom.proxy.example.com",
        )
        result = config.validate()
        assert result.is_valid
        assert any("custom" in w.lower() for w in result.warnings)

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("LLM_PROVIDER", "google")
        monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSy-test-key-123")

        config = LLMConfig.from_env()
        assert config.provider == LLMProvider.GOOGLE
        assert config.google_api_key == "AIzaSy-test-key-123"


class TestConfluenceConfig:
    """Tests for ConfluenceConfig."""

    def test_valid_config(self):
        """Test valid Confluence configuration."""
        config = ConfluenceConfig(
            base_url="https://mycompany.atlassian.net",
            username="user@example.com",
            api_token="atlassian-api-token-here",
            space_keys="DOCS,WIKI",
        )
        result = config.validate()
        assert result.is_valid

    def test_missing_base_url(self):
        """Test validation fails with missing base URL."""
        config = ConfluenceConfig(
            username="user@example.com",
            api_token="token",
            space_keys="DOCS",
        )
        result = config.validate()
        assert not result.is_valid
        assert any("base_url" in e for e in result.errors)

    def test_http_url_fails(self):
        """Test validation fails with HTTP URL."""
        config = ConfluenceConfig(
            base_url="http://mycompany.atlassian.net",
            username="user@example.com",
            api_token="token",
            space_keys="DOCS",
        )
        result = config.validate()
        assert not result.is_valid
        assert any("HTTPS" in e for e in result.errors)

    def test_invalid_username_email(self):
        """Test validation fails with non-email username."""
        config = ConfluenceConfig(
            base_url="https://mycompany.atlassian.net",
            username="notanemail",
            api_token="token",
            space_keys="DOCS",
        )
        result = config.validate()
        assert not result.is_valid
        assert any("username" in e for e in result.errors)

    def test_invalid_output_format(self):
        """Test validation fails with invalid output format."""
        config = ConfluenceConfig(
            base_url="https://mycompany.atlassian.net",
            username="user@example.com",
            api_token="token",
            space_keys="DOCS",
            output_format="pdf",  # Invalid
        )
        result = config.validate()
        assert not result.is_valid
        assert any("output_format" in e for e in result.errors)

    def test_space_keys_list(self):
        """Test space_keys_list property."""
        config = ConfluenceConfig(space_keys="DOCS, WIKI, DEV")
        assert config.space_keys_list == ["DOCS", "WIKI", "DEV"]

        config = ConfluenceConfig(space_keys="")
        assert config.space_keys_list == []


class TestJiraConfig:
    """Tests for JiraConfig."""

    def test_valid_config(self):
        """Test valid JIRA configuration."""
        config = JiraConfig(
            base_url="https://mycompany.atlassian.net",
            username="user@example.com",
            api_token="atlassian-api-token-here",
        )
        result = config.validate()
        assert result.is_valid

    def test_missing_base_url(self):
        """Test validation fails with missing base URL."""
        config = JiraConfig(
            username="user@example.com",
            api_token="token",
        )
        result = config.validate()
        assert not result.is_valid

    def test_empty_jql_warning(self):
        """Test warning when JQL is empty."""
        config = JiraConfig(
            base_url="https://mycompany.atlassian.net",
            username="user@example.com",
            api_token="token",
            jql_query="",
        )
        result = config.validate()
        assert result.is_valid
        assert any("jql_query" in w for w in result.warnings)

    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("JIRA_BASE_URL", "https://test.atlassian.net")
        monkeypatch.setenv("JIRA_USERNAME", "test@example.com")
        monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
        monkeypatch.setenv("JIRA_MAX_TICKETS", "100")

        config = JiraConfig.from_env()
        assert config.base_url == "https://test.atlassian.net"
        assert config.username == "test@example.com"
        assert config.max_tickets == 100


class TestGatewayConfig:
    """Tests for GatewayConfig."""

    def test_valid_config(self):
        """Test valid gateway configuration."""
        config = GatewayConfig(
            host="0.0.0.0",
            port=9847,
            secret="a" * 32,
        )
        result = config.validate()
        assert result.is_valid

    def test_missing_secret(self):
        """Test validation fails with missing secret."""
        config = GatewayConfig(port=9847)
        result = config.validate()
        assert not result.is_valid
        assert any("secret" in e for e in result.errors)

    def test_short_secret_warning(self):
        """Test warning when secret is too short."""
        config = GatewayConfig(
            port=9847,
            secret="short",
        )
        result = config.validate()
        assert result.is_valid
        assert any("32" in w for w in result.warnings)

    def test_invalid_port(self):
        """Test validation fails with invalid port."""
        config = GatewayConfig(
            port=70000,  # Invalid
            secret="a" * 32,
        )
        result = config.validate()
        assert not result.is_valid
        assert any("port" in e for e in result.errors)

    def test_all_interfaces_warning(self):
        """Test warning when bound to all interfaces."""
        config = GatewayConfig(
            host="0.0.0.0",
            port=9847,
            secret="a" * 32,
        )
        result = config.validate()
        assert any("0.0.0.0" in w for w in result.warnings)

    def test_from_env_generates_secret(self, monkeypatch, temp_dir):
        """Test that from_env generates secret if missing."""
        monkeypatch.setenv("HOME", str(temp_dir))
        monkeypatch.delenv("JIB_GATEWAY_SECRET", raising=False)

        config = GatewayConfig.from_env()
        assert config.secret  # Should be auto-generated
        assert len(config.secret) >= 32
        assert config._secret_source == "auto-generated"

    def test_from_env_uses_env_var(self, monkeypatch, temp_dir):
        """Test that from_env prefers environment variable."""
        monkeypatch.setenv("HOME", str(temp_dir))
        monkeypatch.setenv("JIB_GATEWAY_SECRET", "env-secret-here")

        config = GatewayConfig.from_env()
        assert config.secret == "env-secret-here"
        assert config._secret_source == "environment"

    def test_to_dict_masks_secret(self):
        """Test that to_dict masks the secret."""
        config = GatewayConfig(
            secret="super-secret-gateway-token",
        )
        d = config.to_dict()
        assert "super" not in d["secret"]
        assert "*" in d["secret"]

    def test_rate_limits_in_dict(self):
        """Test that rate limits are included in to_dict."""
        config = GatewayConfig(
            secret="a" * 32,
            rate_limits=RateLimitConfig(git_push=500),
        )
        d = config.to_dict()
        assert d["rate_limits"]["git_push"] == 500


class TestConfigHealthChecks:
    """Tests for health check methods (mocked network calls)."""

    def test_slack_health_no_token(self):
        """Test Slack health check with no token."""
        config = SlackConfig()
        result = config.health_check()
        assert not result.healthy
        assert "not configured" in result.message.lower()

    def test_github_health_no_token(self):
        """Test GitHub health check with no token."""
        config = GitHubConfig()
        result = config.health_check()
        assert not result.healthy
        assert "not configured" in result.message.lower()

    def test_confluence_health_no_config(self):
        """Test Confluence health check with no config."""
        config = ConfluenceConfig()
        result = config.health_check()
        assert not result.healthy
        assert "not configured" in result.message.lower()

    def test_jira_health_no_config(self):
        """Test JIRA health check with no config."""
        config = JiraConfig()
        result = config.health_check()
        assert not result.healthy
        assert "not configured" in result.message.lower()

    def test_gateway_health_no_secret(self):
        """Test Gateway health check with no secret."""
        config = GatewayConfig()
        result = config.health_check()
        assert not result.healthy
        assert "not configured" in result.message.lower()

    def test_llm_health_no_key(self):
        """Test LLM health check with no API key."""
        config = LLMConfig(provider=LLMProvider.ANTHROPIC)
        result = config.health_check()
        assert not result.healthy
        assert "not configured" in result.message.lower()
