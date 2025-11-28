"""Tests for jib_logging.wrappers.base module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from jib_logging.wrappers.base import ToolResult, ToolWrapper


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_success_true_when_exit_code_zero(self):
        """Test that success is True when exit_code is 0."""
        result = ToolResult(
            command=["test"],
            exit_code=0,
            stdout="output",
            stderr="",
            duration_ms=100.0,
        )
        assert result.success is True

    def test_success_false_when_exit_code_nonzero(self):
        """Test that success is False when exit_code is non-zero."""
        result = ToolResult(
            command=["test"],
            exit_code=1,
            stdout="",
            stderr="error",
            duration_ms=100.0,
        )
        assert result.success is False

    def test_check_returns_self_on_success(self):
        """Test that check() returns self when successful."""
        result = ToolResult(
            command=["test"],
            exit_code=0,
            stdout="output",
            stderr="",
            duration_ms=100.0,
        )
        assert result.check() is result

    def test_check_raises_on_failure(self):
        """Test that check() raises CalledProcessError on failure."""
        result = ToolResult(
            command=["test", "arg"],
            exit_code=1,
            stdout="out",
            stderr="err",
            duration_ms=100.0,
        )
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            result.check()

        assert exc_info.value.returncode == 1
        assert exc_info.value.cmd == ["test", "arg"]

    def test_extra_defaults_to_empty_dict(self):
        """Test that extra field defaults to empty dict."""
        result = ToolResult(
            command=["test"],
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=100.0,
        )
        assert result.extra == {}

    def test_extra_can_be_set(self):
        """Test that extra field can be provided."""
        result = ToolResult(
            command=["test"],
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=100.0,
            extra={"key": "value"},
        )
        assert result.extra == {"key": "value"}


class TestToolWrapper:
    """Tests for ToolWrapper base class."""

    def setup_method(self):
        """Create a concrete wrapper for testing."""

        class TestWrapper(ToolWrapper):
            tool_name = "echo"

        self.wrapper = TestWrapper()

    def test_tool_name_attribute(self):
        """Test that tool_name is set correctly."""
        assert self.wrapper.tool_name == "echo"

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_prepends_tool_name(self, mock_run):
        """Test that run() prepends tool name to command."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="hello",
            stderr="",
        )

        self.wrapper.run("hello", "world")

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["echo", "hello", "world"]

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_captures_output(self, mock_run):
        """Test that run() captures stdout and stderr."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="standard output",
            stderr="standard error",
        )

        result = self.wrapper.run("test")

        assert result.stdout == "standard output"
        assert result.stderr == "standard error"

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_captures_exit_code(self, mock_run):
        """Test that run() captures exit code."""
        mock_run.return_value = MagicMock(
            returncode=42,
            stdout="",
            stderr="",
        )

        result = self.wrapper.run("test")

        assert result.exit_code == 42

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_measures_duration(self, mock_run):
        """Test that run() measures command duration."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        result = self.wrapper.run("test")

        assert result.duration_ms >= 0

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_with_check_raises_on_failure(self, mock_run):
        """Test that run() with check=True raises on failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error",
        )

        with pytest.raises(subprocess.CalledProcessError):
            self.wrapper.run("test", check=True)

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_passes_cwd(self, mock_run):
        """Test that run() passes cwd to subprocess."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        self.wrapper.run("test", cwd="/tmp")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_passes_timeout(self, mock_run):
        """Test that run() passes timeout to subprocess."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        self.wrapper.run("test", timeout=30.0)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 30.0

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_passes_input_text(self, mock_run):
        """Test that run() passes input to subprocess."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        self.wrapper.run("test", input_text="hello")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["input"] == "hello"

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_handles_timeout_exception(self, mock_run):
        """Test that run() re-raises timeout exceptions."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["echo"], timeout=30)

        with pytest.raises(subprocess.TimeoutExpired):
            self.wrapper.run("test", timeout=30)

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_run_returns_tool_result(self, mock_run):
        """Test that run() returns a ToolResult."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output",
            stderr="",
        )

        result = self.wrapper.run("test")

        assert isinstance(result, ToolResult)
        assert result.command == ["echo", "test"]
        assert result.stdout == "output"
        assert result.exit_code == 0


class TestToolWrapperContextExtraction:
    """Tests for context extraction in ToolWrapper."""

    def setup_method(self):
        """Create a wrapper with custom context extraction."""

        class ContextWrapper(ToolWrapper):
            tool_name = "test"

            def _extract_context(self, args, stdout, stderr):
                return {"custom_field": "value", "arg_count": len(args)}

        self.wrapper = ContextWrapper()

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_extract_context_adds_to_extra(self, mock_run):
        """Test that _extract_context() output is added to result.extra."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output",
            stderr="",
        )

        result = self.wrapper.run("arg1", "arg2")

        assert result.extra["custom_field"] == "value"
        assert result.extra["arg_count"] == 2


class TestToolWrapperLogging:
    """Tests for logging behavior in ToolWrapper."""

    def setup_method(self):
        """Create a wrapper for testing."""

        class TestWrapper(ToolWrapper):
            tool_name = "echo"

        self.wrapper = TestWrapper()

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_logs_successful_invocation(self, mock_run):
        """Test that successful commands log info message."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="success",
            stderr="",
        )

        # Just verify no exception is raised during logging
        result = self.wrapper.run("hello")
        assert result.success

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_logs_failed_invocation(self, mock_run):
        """Test that failed commands log error message."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="error message",
        )

        # Just verify no exception is raised during logging
        result = self.wrapper.run("fail")
        assert not result.success


class TestToolWrapperEnvironment:
    """Tests for environment variable handling in ToolWrapper."""

    def setup_method(self):
        """Create a wrapper for testing."""

        class TestWrapper(ToolWrapper):
            tool_name = "echo"

        self.wrapper = TestWrapper()

    @patch("jib_logging.wrappers.base.subprocess.run")
    @patch.dict("os.environ", {"PATH": "/usr/bin", "HOME": "/home/test"}, clear=True)
    def test_env_merges_with_current_environment(self, mock_run):
        """Test that custom env is merged with current environment."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        self.wrapper.run("test", env={"CUSTOM_VAR": "custom_value"})

        call_kwargs = mock_run.call_args[1]
        passed_env = call_kwargs["env"]
        # Custom var should be present
        assert passed_env["CUSTOM_VAR"] == "custom_value"
        # Original env vars should be preserved
        assert passed_env["PATH"] == "/usr/bin"
        assert passed_env["HOME"] == "/home/test"

    @patch("jib_logging.wrappers.base.subprocess.run")
    def test_none_env_passes_none_to_subprocess(self, mock_run):
        """Test that None env passes None to subprocess (inherits current)."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        self.wrapper.run("test")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["env"] is None

    @patch("jib_logging.wrappers.base.subprocess.run")
    @patch.dict("os.environ", {"EXISTING": "original"}, clear=True)
    def test_env_can_override_existing_vars(self, mock_run):
        """Test that custom env can override existing environment vars."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        self.wrapper.run("test", env={"EXISTING": "overridden"})

        call_kwargs = mock_run.call_args[1]
        passed_env = call_kwargs["env"]
        assert passed_env["EXISTING"] == "overridden"
