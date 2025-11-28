"""
Tests for jib_logging.model_capture module.

Tests Phase 3 functionality: model output capture, token tracking, response storage.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from jib_logging.context import ContextScope, set_current_context
from jib_logging.model_capture import (
    ModelOutputCapture,
    ModelResponse,
    TokenUsage,
    capture_model_response,
    get_model_capture,
    reset_model_capture,
)


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_basic_token_usage(self):
        """Test basic token usage tracking."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_explicit_total_tokens(self):
        """Test explicit total_tokens overrides computed value."""
        usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=200)
        assert usage.total_tokens == 200

    def test_cache_tokens(self):
        """Test cache token tracking."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=20,
            cache_creation_tokens=10,
        )
        assert usage.cache_read_tokens == 20
        assert usage.cache_creation_tokens == 10

    def test_to_otel_dict(self):
        """Test conversion to OpenTelemetry format."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        otel = usage.to_otel_dict()

        assert otel["gen_ai.usage.input_tokens"] == 100
        assert otel["gen_ai.usage.output_tokens"] == 50
        assert "gen_ai.usage.cache_read_tokens" not in otel

    def test_to_otel_dict_with_cache(self):
        """Test OTEL dict includes cache tokens when non-zero."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=20,
            cache_creation_tokens=10,
        )
        otel = usage.to_otel_dict()

        assert otel["gen_ai.usage.cache_read_tokens"] == 20
        assert otel["gen_ai.usage.cache_creation_tokens"] == 10


class TestModelResponse:
    """Tests for ModelResponse dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        response = ModelResponse()
        assert response.system == "anthropic"
        assert response.token_usage.input_tokens == 0
        assert response.finish_reasons == []
        assert response.extra == {}

    def test_with_all_fields(self):
        """Test response with all fields populated."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        response = ModelResponse(
            model="claude-sonnet-4-5-20250929",
            prompt_preview="Hello...",
            prompt_length=1000,
            response_preview="Hi there...",
            response_length=500,
            token_usage=usage,
            duration_ms=1234.5,
            finish_reasons=["end_turn"],
            session_id="sess123",
            trace_id="trace123",
            task_id="bd-abc",
        )

        assert response.model == "claude-sonnet-4-5-20250929"
        assert response.duration_ms == 1234.5
        assert response.trace_id == "trace123"

    def test_to_log_dict_basic(self):
        """Test conversion to log dictionary."""
        response = ModelResponse(
            model="claude-3-opus",
            duration_ms=1000.0,
        )
        log_dict = response.to_log_dict()

        assert log_dict["gen_ai.system"] == "anthropic"
        assert log_dict["gen_ai.request.model"] == "claude-3-opus"
        assert log_dict["duration_ms"] == 1000.0
        assert log_dict["gen_ai.usage.input_tokens"] == 0

    def test_to_log_dict_with_context(self):
        """Test log dict includes context fields."""
        response = ModelResponse(
            trace_id="trace123",
            span_id="span456",
            task_id="bd-xyz",
        )
        log_dict = response.to_log_dict()

        assert log_dict["traceId"] == "trace123"
        assert log_dict["spanId"] == "span456"
        assert log_dict["task_id"] == "bd-xyz"

    def test_to_log_dict_with_error(self):
        """Test log dict includes error."""
        response = ModelResponse(error="Rate limit exceeded")
        log_dict = response.to_log_dict()

        assert log_dict["error"] == "Rate limit exceeded"


class TestModelOutputCapture:
    """Tests for ModelOutputCapture class."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def capture(self, temp_output_dir):
        """Create capture instance with temp directory."""
        return ModelOutputCapture(
            output_dir=temp_output_dir,
            store_full_responses=True,
        )

    @pytest.fixture
    def capture_no_store(self, temp_output_dir):
        """Create capture instance that doesn't store responses."""
        return ModelOutputCapture(
            output_dir=temp_output_dir,
            store_full_responses=False,
        )

    def test_start_capture(self, capture):
        """Test starting a capture."""
        response = capture.start_capture(
            prompt="What is Python?",
            model="claude-sonnet-4-5-20250929",
        )

        assert response.prompt_preview.startswith("What is Python?")
        assert response.prompt_length == 15
        assert response.model == "claude-sonnet-4-5-20250929"
        assert "_start_time" in response.extra

    def test_start_capture_truncates_long_prompt(self, capture):
        """Test that long prompts are truncated in preview."""
        long_prompt = "A" * 1000
        response = capture.start_capture(prompt=long_prompt)

        assert len(response.prompt_preview) <= 503  # 500 + "..."
        assert response.prompt_preview.endswith("...")
        assert response.prompt_length == 1000

    def test_complete_capture(self, capture):
        """Test completing a capture."""
        response = capture.start_capture(prompt="Hello")
        completed = capture.complete_capture(
            response,
            output="Hello! How can I help?",
            token_usage={"input_tokens": 10, "output_tokens": 20},
            finish_reasons=["end_turn"],
        )

        assert completed.response_preview == "Hello! How can I help?"
        assert completed.response_length == 22
        assert completed.token_usage.input_tokens == 10
        assert completed.token_usage.output_tokens == 20
        assert completed.finish_reasons == ["end_turn"]
        assert completed.duration_ms > 0

    def test_complete_capture_with_error(self, capture):
        """Test completing a capture with an error."""
        response = capture.start_capture(prompt="Hello")
        completed = capture.complete_capture(
            response,
            error="Rate limit exceeded",
        )

        assert completed.error == "Rate limit exceeded"

    def test_complete_capture_stores_response(self, capture, temp_output_dir):
        """Test that full responses are stored to disk."""
        response = capture.start_capture(prompt="Hello")
        completed = capture.complete_capture(
            response,
            output="This is a full response",
        )

        assert completed.output_file is not None
        assert Path(completed.output_file).exists()

        # Verify file contents
        with open(completed.output_file) as f:
            stored = json.load(f)

        assert stored["response"] == "This is a full response"

    def test_complete_capture_no_store(self, capture_no_store):
        """Test that storage can be disabled."""
        response = capture_no_store.start_capture(prompt="Hello")
        completed = capture_no_store.complete_capture(
            response,
            output="This is a full response",
        )

        assert completed.output_file is None

    def test_index_file_created(self, capture, temp_output_dir):
        """Test that an index file is created."""
        response = capture.start_capture(prompt="Hello")
        capture.complete_capture(response, output="Response")

        # Find the date directory
        date_dirs = list(temp_output_dir.iterdir())
        assert len(date_dirs) == 1

        index_path = date_dirs[0] / "index.jsonl"
        assert index_path.exists()

        # Verify index entry
        with open(index_path) as f:
            entry = json.loads(f.readline())

        assert "filename" in entry
        assert "timestamp" in entry

    def test_parse_claude_output_json(self, capture):
        """Test parsing Claude JSON output."""
        json_output = json.dumps(
            {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 20,
                },
                "stop_reason": "end_turn",
            }
        )

        parsed = capture.parse_claude_output(json_output)

        assert parsed["model"] == "claude-sonnet-4-5-20250929"
        assert parsed["token_usage"]["input_tokens"] == 100
        assert parsed["token_usage"]["output_tokens"] == 50
        assert parsed["token_usage"]["cache_read_tokens"] == 20
        assert parsed["finish_reasons"] == ["end_turn"]

    def test_parse_claude_output_error(self, capture):
        """Test parsing Claude error output."""
        json_output = json.dumps({"error": "Something went wrong"})
        parsed = capture.parse_claude_output(json_output)

        assert parsed["error"] == "Something went wrong"

    def test_parse_claude_output_stderr_rate_limit(self, capture):
        """Test parsing rate limit error from stderr."""
        parsed = capture.parse_claude_output("", "Error: Rate limit exceeded")

        assert "error" in parsed
        assert "Rate limit" in parsed["error"]

    def test_parse_claude_output_non_json(self, capture):
        """Test parsing non-JSON output."""
        parsed = capture.parse_claude_output("Hello, I'm Claude!")

        # Should return empty dict for non-JSON
        assert parsed == {}

    def test_context_propagation(self, capture):
        """Test that context is propagated to response."""
        with ContextScope(
            trace_id="test-trace",
            task_id="bd-test123",
            repository="owner/repo",
        ):
            response = capture.start_capture(prompt="Hello")

        assert response.trace_id == "test-trace"
        assert response.task_id == "bd-test123"

    def test_context_manager_basic(self, capture):
        """Test context manager for capture."""
        with capture.capture_response(prompt="Hello") as ctx:
            ctx.set_output("Hi there!")
            ctx.set_token_usage({"input_tokens": 5, "output_tokens": 3})

        response = ctx.response
        assert response is not None
        assert response.response_preview == "Hi there!"
        assert response.token_usage.input_tokens == 5

    def test_context_manager_with_exception(self, capture):
        """Test context manager handles exceptions."""
        try:
            with capture.capture_response(prompt="Hello") as ctx:
                raise ValueError("Test error")
        except ValueError:
            pass

        response = ctx.response
        assert response is not None
        assert response.error == "Test error"

    def test_context_manager_parses_output(self, capture):
        """Test context manager parses JSON output automatically."""
        json_output = json.dumps(
            {
                "model": "claude-sonnet-4-5-20250929",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        )

        with capture.capture_response() as ctx:
            ctx.set_output(json_output)

        response = ctx.response
        assert response.model == "claude-sonnet-4-5-20250929"
        assert response.token_usage.input_tokens == 100


class TestCaptureContext:
    """Tests for CaptureContext class."""

    @pytest.fixture
    def capture(self):
        """Create capture instance without storage."""
        return ModelOutputCapture(store_full_responses=False)

    def test_set_output(self, capture):
        """Test setting output."""
        with capture.capture_response() as ctx:
            ctx.set_output("Hello world")

        assert ctx.response.response_preview == "Hello world"

    def test_set_error(self, capture):
        """Test setting error."""
        with capture.capture_response() as ctx:
            ctx.set_error("Something failed")

        assert ctx.response.error == "Something failed"

    def test_set_token_usage_dict(self, capture):
        """Test setting token usage from dict."""
        with capture.capture_response() as ctx:
            ctx.set_token_usage({"input_tokens": 100, "output_tokens": 50})

        assert ctx.response.token_usage.input_tokens == 100
        assert ctx.response.token_usage.output_tokens == 50

    def test_set_token_usage_object(self, capture):
        """Test setting token usage from TokenUsage object."""
        usage = TokenUsage(input_tokens=200, output_tokens=100)

        with capture.capture_response() as ctx:
            ctx.set_token_usage(usage)

        assert ctx.response.token_usage.input_tokens == 200

    def test_set_finish_reasons(self, capture):
        """Test setting finish reasons."""
        with capture.capture_response() as ctx:
            ctx.set_finish_reasons(["end_turn", "max_tokens"])

        assert ctx.response.finish_reasons == ["end_turn", "max_tokens"]

    def test_set_model(self, capture):
        """Test setting model."""
        with capture.capture_response() as ctx:
            ctx.set_model("claude-3-opus")

        assert ctx.response.model == "claude-3-opus"

    def test_multiple_set_output_overwrites(self, capture):
        """Test that multiple set_output calls overwrite previous values.

        This documents the expected behavior: later calls to set_output
        replace the output from earlier calls within the same context.
        """
        with capture.capture_response() as ctx:
            ctx.set_output("First response")
            ctx.set_output("Second response")
            ctx.set_output("Final response")

        assert ctx.response.response_preview == "Final response"
        assert ctx.response.response_length == len("Final response")

    def test_set_output_preserves_manually_set_metadata(self, capture):
        """Test that set_output doesn't overwrite manually set metadata.

        If token_usage, model, etc. are set before calling set_output,
        set_output should not overwrite them with parsed values.
        """
        # JSON output with metadata
        json_output = json.dumps(
            {
                "model": "parsed-model",
                "usage": {"input_tokens": 999, "output_tokens": 888},
            }
        )

        with capture.capture_response() as ctx:
            # Set metadata manually first
            ctx.set_model("manual-model")
            ctx.set_token_usage({"input_tokens": 100, "output_tokens": 50})
            # Now set output with different metadata in JSON
            ctx.set_output(json_output)

        # Manually set values should be preserved
        assert ctx.response.model == "manual-model"
        assert ctx.response.token_usage.input_tokens == 100


class TestGlobalCapture:
    """Tests for global capture functions."""

    def test_get_model_capture_singleton(self):
        """Test that get_model_capture returns singleton."""
        # Reset singleton
        reset_model_capture()

        capture1 = get_model_capture()
        capture2 = get_model_capture()

        assert capture1 is capture2

    def test_get_model_capture_with_params(self):
        """Test creating capture with custom params."""
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = get_model_capture(
                output_dir=tmpdir,
                store_full_responses=False,
            )

            assert capture._output_dir == Path(tmpdir)
            assert capture._store_full_responses is False

    def test_get_model_capture_with_params_does_not_modify_singleton(self):
        """Test that creating capture with params doesn't modify singleton.

        When get_model_capture() is called with parameters, it returns a
        new instance without affecting the global singleton.
        """
        reset_model_capture()

        # Get the singleton
        singleton = get_model_capture()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a custom instance with params
            custom = get_model_capture(output_dir=tmpdir, store_full_responses=False)

            # Custom instance should be different
            assert custom is not singleton
            assert custom._output_dir == Path(tmpdir)

            # Singleton should still be the original
            same_singleton = get_model_capture()
            assert same_singleton is singleton

    def test_get_model_capture_env_vars(self):
        """Test capture respects environment variables."""
        reset_model_capture()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "JIB_MODEL_OUTPUT_DIR": tmpdir,
                    "JIB_STORE_MODEL_OUTPUT": "false",
                },
            ):
                # Reset singleton to pick up env vars
                reset_model_capture()
                capture = get_model_capture()

                assert str(capture._output_dir) == tmpdir
                assert capture._store_full_responses is False

    def test_capture_model_response_function(self):
        """Test convenience function."""
        with capture_model_response(prompt="Hello", model="test-model") as ctx:
            ctx.set_output("Hi!")

        assert ctx.response is not None
        assert ctx.response.response_preview == "Hi!"


class TestIntegration:
    """Integration tests for model capture."""

    @pytest.fixture(autouse=True)
    def reset_context(self):
        """Reset logging context before each test."""
        set_current_context(None)
        yield
        set_current_context(None)

    @pytest.fixture
    def capture(self):
        """Create capture instance without storage."""
        return ModelOutputCapture(store_full_responses=False)

    def test_full_workflow(self, capture):
        """Test complete capture workflow."""
        with ContextScope(task_id="bd-test", repository="owner/repo"):
            with capture.capture_response(prompt="Explain Python") as ctx:
                # Simulate Claude output
                output = json.dumps(
                    {
                        "model": "claude-sonnet-4-5-20250929",
                        "content": "Python is a programming language...",
                        "usage": {
                            "input_tokens": 50,
                            "output_tokens": 200,
                        },
                        "stop_reason": "end_turn",
                    }
                )
                ctx.set_output(output)

        response = ctx.response
        assert response.task_id == "bd-test"
        assert response.model == "claude-sonnet-4-5-20250929"
        assert response.token_usage.input_tokens == 50
        assert response.token_usage.output_tokens == 200
        assert response.finish_reasons == ["end_turn"]
        assert response.duration_ms > 0

    def test_error_workflow(self, capture):
        """Test error capture workflow."""
        with capture.capture_response(prompt="Test") as ctx:
            ctx.set_output("", "Error: API rate limit exceeded")

        response = ctx.response
        assert response.error is not None
        assert "Rate limit" in response.error

    def test_multiple_captures(self, capture):
        """Test multiple sequential captures."""
        responses = []

        for i in range(3):
            with capture.capture_response(prompt=f"Prompt {i}") as ctx:
                ctx.set_output(f"Response {i}")
            responses.append(ctx.response)

        assert len(responses) == 3
        for i, response in enumerate(responses):
            assert f"Response {i}" in response.response_preview
