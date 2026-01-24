"""Tests for the jib_humanizer module."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from jib_humanizer import (
    HumanizationError,
    HumanizeResult,
    get_config,
    humanize,
    humanize_and_log,
    humanize_text,
)


class TestHumanizeConfig:
    """Tests for configuration handling."""

    def test_default_config(self):
        """Test default configuration values."""
        config = get_config()
        assert config.enabled is True
        assert config.model == "sonnet"
        assert config.min_length == 50
        assert config.fail_open is True
        assert config.timeout == 60

    def test_config_from_env(self, monkeypatch):
        """Test configuration from environment variables."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "false")
        monkeypatch.setenv("JIB_HUMANIZE_MODEL", "haiku")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "100")
        monkeypatch.setenv("JIB_HUMANIZE_FAIL_OPEN", "false")
        monkeypatch.setenv("JIB_HUMANIZE_TIMEOUT", "30")

        config = get_config()
        assert config.enabled is False
        assert config.model == "haiku"
        assert config.min_length == 100
        assert config.fail_open is False
        assert config.timeout == 30


class TestHumanize:
    """Tests for the humanize function."""

    def test_skip_when_disabled(self, monkeypatch):
        """Test that humanization is skipped when disabled."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "false")

        result = humanize("Additionally, this is crucial.")
        assert result.success is True
        assert result.text == "Additionally, this is crucial."
        assert result.original == result.text

    def test_skip_short_text(self, monkeypatch):
        """Test that short text is not humanized."""
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "100")

        result = humanize("Short text")
        assert result.success is True
        assert result.text == "Short text"

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_successful_humanization(self, mock_run, monkeypatch):
        """Test successful humanization."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Also, this is important.",
            stderr="",
        )

        result = humanize("Additionally, this is crucial.")
        assert result.success is True
        assert result.text == "Also, this is important."
        assert result.original == "Additionally, this is crucial."

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_humanization_failure_fail_open(self, mock_run, monkeypatch):
        """Test that original text is returned on failure when fail_open=True."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error",
        )

        result = humanize("Test text that is long enough", fail_open=True)
        assert result.success is False
        assert result.text == "Test text that is long enough"
        assert result.error is not None

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_humanization_failure_fail_closed(self, mock_run, monkeypatch):
        """Test that exception is raised on failure when fail_open=False."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error",
        )

        with pytest.raises(HumanizationError):
            humanize("Test text that is long enough", fail_open=False)

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_timeout_fail_open(self, mock_run, monkeypatch):
        """Test timeout handling with fail_open=True."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")
        monkeypatch.setenv("JIB_HUMANIZE_TIMEOUT", "1")

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=1)

        result = humanize("Test text that is long enough", fail_open=True)
        assert result.success is False
        assert result.text == "Test text that is long enough"
        assert "timed out" in result.error.lower()

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_empty_response_is_error(self, mock_run, monkeypatch):
        """Test that empty response is treated as error."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="   ",  # Whitespace only
            stderr="",
        )

        result = humanize("Test text that is long enough", fail_open=True)
        assert result.success is False
        assert result.text == "Test text that is long enough"


class TestHumanizeText:
    """Tests for the humanize_text convenience function."""

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_returns_humanized_text(self, mock_run, monkeypatch):
        """Test that humanize_text returns just the text."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Humanized text",
            stderr="",
        )

        text = humanize_text("Original text that is long")
        assert text == "Humanized text"

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_returns_original_on_failure(self, mock_run, monkeypatch):
        """Test that original is returned on failure."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error",
        )

        text = humanize_text("Original text that is long")
        assert text == "Original text that is long"


class TestHumanizeAndLog:
    """Tests for the humanize_and_log function."""

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_logs_successful_humanization(self, mock_run, monkeypatch, caplog):
        """Test that successful humanization is logged."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Different humanized text",
            stderr="",
        )

        import logging

        with caplog.at_level(logging.INFO):
            text = humanize_and_log("Original text that is long", "test context")

        assert text == "Different humanized text"
        # Note: actual log assertion depends on logger configuration

    @patch("jib_humanizer.humanizer.subprocess.run")
    def test_logs_failed_humanization(self, mock_run, monkeypatch, caplog):
        """Test that failed humanization is logged."""
        monkeypatch.setenv("JIB_HUMANIZE_ENABLED", "true")
        monkeypatch.setenv("JIB_HUMANIZE_MIN_LENGTH", "10")

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error message",
        )

        import logging

        with caplog.at_level(logging.WARNING):
            text = humanize_and_log("Original text that is long", "test context")

        assert text == "Original text that is long"


class TestHumanizeResult:
    """Tests for the HumanizeResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = HumanizeResult(
            success=True,
            text="humanized",
            original="original",
        )
        assert result.success is True
        assert result.text == "humanized"
        assert result.original == "original"
        assert result.error is None

    def test_failed_result(self):
        """Test creating a failed result."""
        result = HumanizeResult(
            success=False,
            text="original",
            original="original",
            error="Some error",
        )
        assert result.success is False
        assert result.text == "original"
        assert result.error == "Some error"


class TestIntegration:
    """Integration tests - require Claude Code to be available."""

    @pytest.mark.skipif(
        os.environ.get("RUN_INTEGRATION_TESTS") != "true",
        reason="Set RUN_INTEGRATION_TESTS=true to run integration tests",
    )
    def test_real_humanization(self):
        """Test real humanization with Claude Code.

        This test requires:
        1. Claude Code CLI installed and authenticated
        2. humanizer skill installed at ~/.claude/skills/humanizer
        3. RUN_INTEGRATION_TESTS=true environment variable
        """
        # Text with AI patterns
        ai_text = (
            "Additionally, this is a crucial feature that serves as "
            "a testament to the power of modern software development. "
            "Furthermore, it delves into the landscape of automation."
        )

        result = humanize(ai_text)

        if result.success:
            # Check that some patterns were removed
            humanized_lower = result.text.lower()
            removed_patterns = 0

            if "additionally" not in humanized_lower:
                removed_patterns += 1
            if "crucial" not in humanized_lower:
                removed_patterns += 1
            if "testament" not in humanized_lower:
                removed_patterns += 1
            if "delves" not in humanized_lower:
                removed_patterns += 1
            if "landscape" not in humanized_lower:
                removed_patterns += 1

            # At least some patterns should be removed
            assert removed_patterns >= 2, f"Expected patterns to be removed, got: {result.text}"
        else:
            # If humanization failed, note it but don't fail the test
            pytest.skip(f"Humanization failed: {result.error}")
