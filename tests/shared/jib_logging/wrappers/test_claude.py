"""Tests for jib_logging.wrappers.claude module."""

from unittest.mock import MagicMock, patch

import pytest
from jib_logging.wrappers.claude import ClaudeWrapper


class TestClaudeWrapper:
    """Tests for ClaudeWrapper class."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = ClaudeWrapper()

    def test_tool_name_is_claude(self):
        """Test that tool_name is 'claude'."""
        assert self.wrapper.tool_name == "claude"


class TestClaudePrompt:
    """Tests for ClaudeWrapper.prompt() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = ClaudeWrapper()

    @patch.object(ClaudeWrapper, "run")
    def test_prompt_basic(self, mock_run):
        """Test basic prompt."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="Response text")

        self.wrapper.prompt("What is 2+2?")

        args = mock_run.call_args[0]
        assert "--print" in args
        assert "-p" in args
        assert "What is 2+2?" in args

    @patch.object(ClaudeWrapper, "run")
    def test_prompt_with_model(self, mock_run):
        """Test prompt with specific model."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.prompt("Test", model="claude-sonnet-4-5-20250929")

        args = mock_run.call_args[0]
        assert "--model" in args
        assert "claude-sonnet-4-5-20250929" in args

    @patch.object(ClaudeWrapper, "run")
    def test_prompt_with_output_format(self, mock_run):
        """Test prompt with output format."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.prompt("Test", output_format="json")

        args = mock_run.call_args[0]
        assert "--output-format" in args
        assert "json" in args

    @patch.object(ClaudeWrapper, "run")
    def test_prompt_with_max_turns(self, mock_run):
        """Test prompt with max turns limit."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.prompt("Test", max_turns=5)

        args = mock_run.call_args[0]
        assert "--max-turns" in args
        assert "5" in args

    @patch.object(ClaudeWrapper, "run")
    def test_prompt_with_context(self, mock_run):
        """Test prompt with context file."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.prompt("Explain this", context="file.py")

        args = mock_run.call_args[0]
        assert "--context" in args
        assert "file.py" in args

    @patch.object(ClaudeWrapper, "run")
    def test_prompt_with_timeout(self, mock_run):
        """Test prompt with timeout."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.prompt("Test", timeout=60.0)

        kwargs = mock_run.call_args[1]
        assert kwargs["timeout"] == 60.0


class TestClaudeRunWithFile:
    """Tests for ClaudeWrapper.run_with_file() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = ClaudeWrapper()

    @patch.object(ClaudeWrapper, "run")
    def test_run_with_file_basic(self, mock_run):
        """Test running with a file."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.run_with_file("code.py")

        args = mock_run.call_args[0]
        assert "--print" in args
        assert "--context" in args
        assert "code.py" in args

    @patch.object(ClaudeWrapper, "run")
    def test_run_with_file_and_prompt(self, mock_run):
        """Test running with a file and prompt."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.run_with_file("code.py", "Explain this code")

        args = mock_run.call_args[0]
        assert "-p" in args
        assert "Explain this code" in args


class TestClaudeResume:
    """Tests for ClaudeWrapper.resume() method."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = ClaudeWrapper()

    @patch.object(ClaudeWrapper, "run")
    def test_resume_basic(self, mock_run):
        """Test resuming a session."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.resume("session-abc123")

        args = mock_run.call_args[0]
        assert "--print" in args
        assert "--resume" in args
        assert "session-abc123" in args

    @patch.object(ClaudeWrapper, "run")
    def test_resume_with_prompt(self, mock_run):
        """Test resuming with new prompt."""
        mock_run.return_value = MagicMock(exit_code=0, stdout="")

        self.wrapper.resume("session-abc123", "Continue with this")

        args = mock_run.call_args[0]
        assert "-p" in args
        assert "Continue with this" in args


class TestClaudeContextExtraction:
    """Tests for context extraction in ClaudeWrapper."""

    def setup_method(self):
        """Create a wrapper for testing."""
        self.wrapper = ClaudeWrapper()

    def test_extracts_model(self):
        """Test that model is extracted from args."""
        context = self.wrapper._extract_context(
            ("--print", "--model", "claude-sonnet-4-5-20250929", "-p", "Test"),
            "",
            "",
        )
        assert context.get("model") == "claude-sonnet-4-5-20250929"

    def test_extracts_prompt_preview(self):
        """Test that prompt preview is extracted."""
        context = self.wrapper._extract_context(
            ("--print", "-p", "What is the meaning of life?"),
            "",
            "",
        )
        assert context.get("prompt_preview") == "What is the meaning of life?"
        assert context.get("prompt_length") == len("What is the meaning of life?")

    def test_truncates_long_prompt(self):
        """Test that long prompts are truncated."""
        long_prompt = "x" * 300
        context = self.wrapper._extract_context(
            ("--print", "-p", long_prompt),
            "",
            "",
        )
        assert len(context.get("prompt_preview", "")) <= 203  # 200 + "..."
        assert context.get("prompt_preview", "").endswith("...")

    def test_extracts_context_file(self):
        """Test that context file is extracted."""
        context = self.wrapper._extract_context(
            ("--print", "--context", "myfile.py", "-p", "Explain"),
            "",
            "",
        )
        assert context.get("context_file") == "myfile.py"

    def test_extracts_session_id(self):
        """Test that session ID is extracted."""
        context = self.wrapper._extract_context(
            ("--print", "--resume", "session-xyz789"),
            "",
            "",
        )
        assert context.get("session_id") == "session-xyz789"

    def test_extracts_max_turns(self):
        """Test that max_turns is extracted."""
        context = self.wrapper._extract_context(
            ("--print", "--max-turns", "10", "-p", "Test"),
            "",
            "",
        )
        assert context.get("max_turns") == 10

    def test_extracts_response_length(self):
        """Test that response length is extracted."""
        context = self.wrapper._extract_context(
            ("--print", "-p", "Test"),
            "This is the response from Claude.",
            "",
        )
        assert context.get("response_length") == len("This is the response from Claude.")

    def test_detects_stderr(self):
        """Test that stderr presence is detected."""
        context = self.wrapper._extract_context(
            ("--print", "-p", "Test"),
            "Response",
            "Some warning",
        )
        assert context.get("has_stderr") is True

    def test_parses_json_output_usage(self):
        """Test that JSON output with usage is parsed."""
        json_output = '{"usage": {"input_tokens": 100, "output_tokens": 50}, "model": "claude-3"}'
        context = self.wrapper._extract_context(
            ("--print", "-p", "Test"),
            json_output,
            "",
        )
        assert context.get("gen_ai.usage.input_tokens") == 100
        assert context.get("gen_ai.usage.output_tokens") == 50
        assert context.get("gen_ai.request.model") == "claude-3"


class TestClaudeWrapperIntegration:
    """Integration tests for ClaudeWrapper (using real echo command as mock)."""

    def setup_method(self):
        """Create a wrapper that uses echo for testing."""

        class EchoWrapper(ClaudeWrapper):
            tool_name = "echo"

        self.wrapper = EchoWrapper()

    def test_real_command_execution(self):
        """Test that commands actually execute."""
        result = self.wrapper.run("hello", "world")

        assert result.success
        assert "hello world" in result.stdout
        assert result.duration_ms >= 0
