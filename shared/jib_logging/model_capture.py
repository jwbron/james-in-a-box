"""
Model output capture for jib_logging.

Captures full Claude Code model output for:
- Debugging agent behavior
- Cost tracking (token usage)
- Performance analysis (response time)
- Quality analysis (conversation patterns)

This module implements Phase 3 of ADR-Standardized-Logging-Interface.
"""

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import get_or_create_context
from .logger import get_logger


# Default storage location for full model outputs
DEFAULT_MODEL_OUTPUT_DIR = Path("/var/log/jib/model_output")


@dataclass
class TokenUsage:
    """Token usage tracking using OpenTelemetry GenAI semantic conventions.

    Attributes:
        input_tokens: Number of tokens in the prompt
        output_tokens: Number of tokens in the response
        total_tokens: Total tokens used (computed if not provided)
        cache_read_tokens: Tokens read from cache (if applicable)
        cache_creation_tokens: Tokens used to create cache (if applicable)
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def __post_init__(self):
        if self.total_tokens is None:
            self.total_tokens = self.input_tokens + self.output_tokens

    def to_otel_dict(self) -> dict[str, Any]:
        """Convert to OpenTelemetry GenAI semantic convention fields."""
        result = {
            "gen_ai.usage.input_tokens": self.input_tokens,
            "gen_ai.usage.output_tokens": self.output_tokens,
        }
        if self.cache_read_tokens > 0:
            result["gen_ai.usage.cache_read_tokens"] = self.cache_read_tokens
        if self.cache_creation_tokens > 0:
            result["gen_ai.usage.cache_creation_tokens"] = self.cache_creation_tokens
        return result


@dataclass
class ModelResponse:
    """Captured model response with metadata.

    Attributes:
        model: Model identifier (e.g., "claude-sonnet-4-5-20250929")
        system: LLM provider (default "anthropic")
        prompt_preview: Truncated prompt for logging
        prompt_length: Full prompt length in characters
        response_preview: Truncated response for logging
        response_length: Full response length in characters
        token_usage: Token usage information
        duration_ms: Response time in milliseconds
        finish_reasons: Why generation stopped (e.g., ["end_turn"])
        session_id: Claude Code session ID if applicable
        error: Error message if request failed
        timestamp: When the response was received
        trace_id: Trace ID for correlation
        span_id: Span ID for correlation
        task_id: Beads task ID for task correlation
        output_file: Path to stored full response (if stored)
        raw_response: Full response data (for storage)
        extra: Additional metadata
    """

    model: str | None = None
    system: str = "anthropic"
    prompt_preview: str = ""
    prompt_length: int = 0
    response_preview: str = ""
    response_length: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    duration_ms: float = 0.0
    finish_reasons: list[str] = field(default_factory=list)
    session_id: str | None = None
    error: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = None
    span_id: str | None = None
    task_id: str | None = None
    output_file: str | None = None
    raw_response: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dict for structured logging."""
        result: dict[str, Any] = {
            "gen_ai.system": self.system,
            "duration_ms": round(self.duration_ms, 2),
        }

        if self.model:
            result["gen_ai.request.model"] = self.model

        if self.prompt_preview:
            result["prompt_preview"] = self.prompt_preview
        if self.prompt_length:
            result["prompt_length"] = self.prompt_length

        if self.response_preview:
            result["response_preview"] = self.response_preview
        if self.response_length:
            result["response_length"] = self.response_length

        # Token usage
        result.update(self.token_usage.to_otel_dict())

        if self.finish_reasons:
            result["gen_ai.response.finish_reasons"] = self.finish_reasons

        if self.session_id:
            result["session_id"] = self.session_id

        if self.error:
            result["error"] = self.error

        if self.trace_id:
            result["traceId"] = self.trace_id
        if self.span_id:
            result["spanId"] = self.span_id
        if self.task_id:
            result["task_id"] = self.task_id

        if self.output_file:
            result["output_file"] = self.output_file

        result.update(self.extra)

        return result


class ModelOutputCapture:
    """Captures and stores Claude Code model outputs.

    Provides:
    - Structured logging of model interactions
    - Token usage tracking for cost visibility
    - Full response storage for debugging
    - Performance metrics

    Usage:
        from jib_logging.model_capture import get_model_capture

        capture = get_model_capture()

        # Start timing
        with capture.capture_response() as response:
            # Run Claude Code here
            result = subprocess.run(["claude", "--print", "-p", "prompt"])
            response.set_output(result.stdout, result.stderr)

        # Or manually
        response = capture.start_capture(prompt="What is Python?")
        # ... run claude ...
        capture.complete_capture(response, output="Python is a programming language")
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        store_full_responses: bool = True,
        max_preview_length: int = 500,
    ):
        """Initialize the capture system.

        Args:
            output_dir: Directory for storing full responses
            store_full_responses: Whether to store full responses to disk
            max_preview_length: Max length for preview fields in logs
        """
        self._logger = get_logger("model-capture", component="capture")
        self._output_dir = Path(output_dir or DEFAULT_MODEL_OUTPUT_DIR)
        self._store_full_responses = store_full_responses
        self._max_preview_length = max_preview_length

    def _get_output_dir(self) -> Path:
        """Get the output directory, creating date-based subdirectory."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_dir = self._output_dir / today
        if self._store_full_responses:
            output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _generate_output_filename(self, trace_id: str | None) -> str:
        """Generate a unique filename for the response."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        if trace_id:
            # Use first 8 chars of trace_id for identification
            return f"{timestamp}_{trace_id[:8]}.json"
        else:
            # Generate a short random ID
            random_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]
            return f"{timestamp}_{random_id}.json"

    def _truncate(self, text: str, max_length: int | None = None) -> str:
        """Truncate text for preview."""
        max_len = max_length or self._max_preview_length
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def start_capture(
        self,
        prompt: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
        **extra: Any,
    ) -> ModelResponse:
        """Start capturing a model response.

        Call this before running Claude, then call complete_capture() after.

        Args:
            prompt: The prompt being sent
            model: Model being used
            session_id: Claude session ID if resuming
            **extra: Additional metadata

        Returns:
            ModelResponse object to pass to complete_capture()
        """
        ctx = get_or_create_context()

        response = ModelResponse(
            model=model,
            prompt_preview=self._truncate(prompt) if prompt else "",
            prompt_length=len(prompt) if prompt else 0,
            session_id=session_id,
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            task_id=ctx.task_id,
            extra=extra,
        )

        # Store start time in extra for duration calculation
        response.extra["_start_time"] = time.perf_counter()

        return response

    def complete_capture(
        self,
        response: ModelResponse,
        output: str | None = None,
        error: str | None = None,
        token_usage: TokenUsage | dict[str, int] | None = None,
        finish_reasons: list[str] | None = None,
        model: str | None = None,
    ) -> ModelResponse:
        """Complete capturing a model response.

        Args:
            response: The ModelResponse from start_capture()
            output: The model's output
            error: Error message if failed
            token_usage: Token usage (TokenUsage object or dict)
            finish_reasons: Why generation stopped
            model: Model used (if not already set)

        Returns:
            Updated ModelResponse
        """
        # Calculate duration
        start_time = response.extra.pop("_start_time", None)
        if start_time:
            response.duration_ms = (time.perf_counter() - start_time) * 1000

        # Update response fields
        if output:
            response.raw_response = output
            response.response_preview = self._truncate(output)
            response.response_length = len(output)

        if error:
            response.error = error

        if model:
            response.model = model

        if finish_reasons:
            response.finish_reasons = finish_reasons

        # Handle token usage
        if token_usage:
            if isinstance(token_usage, dict):
                response.token_usage = TokenUsage(
                    input_tokens=token_usage.get("input_tokens", 0),
                    output_tokens=token_usage.get("output_tokens", 0),
                    cache_read_tokens=token_usage.get("cache_read_tokens", 0),
                    cache_creation_tokens=token_usage.get("cache_creation_tokens", 0),
                )
            else:
                response.token_usage = token_usage

        # Store full response if enabled
        if self._store_full_responses and response.raw_response:
            self._store_response(response)

        # Log the capture
        self._log_capture(response)

        return response

    def _store_response(self, response: ModelResponse) -> None:
        """Store the full response to disk."""
        try:
            output_dir = self._get_output_dir()
            filename = self._generate_output_filename(response.trace_id)
            output_path = output_dir / filename

            # Build storage document
            doc = {
                "timestamp": response.timestamp.isoformat(),
                "model": response.model,
                "system": response.system,
                "prompt_length": response.prompt_length,
                "response": response.raw_response,
                "response_length": response.response_length,
                "token_usage": {
                    "input_tokens": response.token_usage.input_tokens,
                    "output_tokens": response.token_usage.output_tokens,
                    "total_tokens": response.token_usage.total_tokens,
                    "cache_read_tokens": response.token_usage.cache_read_tokens,
                    "cache_creation_tokens": response.token_usage.cache_creation_tokens,
                },
                "duration_ms": response.duration_ms,
                "finish_reasons": response.finish_reasons,
                "error": response.error,
                "trace_id": response.trace_id,
                "span_id": response.span_id,
                "task_id": response.task_id,
                "session_id": response.session_id,
                "extra": response.extra,
            }

            with open(output_path, "w") as f:
                json.dump(doc, f, indent=2)

            response.output_file = str(output_path)

            # Also append to daily index
            self._append_to_index(output_dir, response, filename)

        except OSError as e:
            self._logger.warning(
                "Failed to store model output",
                error=str(e),
                trace_id=response.trace_id,
            )

    def _append_to_index(
        self,
        output_dir: Path,
        response: ModelResponse,
        filename: str,
    ) -> None:
        """Append metadata to the daily index file."""
        try:
            index_path = output_dir / "index.jsonl"

            index_entry = {
                "timestamp": response.timestamp.isoformat(),
                "filename": filename,
                "model": response.model,
                "input_tokens": response.token_usage.input_tokens,
                "output_tokens": response.token_usage.output_tokens,
                "duration_ms": round(response.duration_ms, 2),
                "trace_id": response.trace_id,
                "task_id": response.task_id,
                "error": response.error is not None,
            }

            with open(index_path, "a") as f:
                f.write(json.dumps(index_entry) + "\n")

        except OSError:
            # Non-critical, just skip indexing
            pass

    def _log_capture(self, response: ModelResponse) -> None:
        """Log the captured response."""
        log_data = response.to_log_dict()

        if response.error:
            self._logger.error("Claude Code response failed", **log_data)
        else:
            self._logger.info("Claude Code response captured", **log_data)

    def capture_response(
        self,
        prompt: str | None = None,
        model: str | None = None,
        **extra: Any,
    ) -> "CaptureContext":
        """Context manager for capturing a model response.

        Usage:
            with capture.capture_response(prompt="Hello") as ctx:
                result = subprocess.run(["claude", ...])
                ctx.set_output(result.stdout)
                ctx.set_token_usage({"input_tokens": 100, "output_tokens": 50})
        """
        return CaptureContext(self, prompt, model, extra)

    def parse_claude_output(
        self,
        stdout: str,
        stderr: str = "",
    ) -> dict[str, Any]:
        """Parse Claude Code JSON output for token usage and other metadata.

        Args:
            stdout: Standard output from Claude
            stderr: Standard error from Claude

        Returns:
            Dict with parsed fields (token_usage, model, finish_reasons, etc.)
        """
        result: dict[str, Any] = {}

        # Try to parse JSON output (from --output-format json)
        if stdout.strip().startswith("{"):
            try:
                data = json.loads(stdout)

                # Extract usage info
                if "usage" in data:
                    usage = data["usage"]
                    result["token_usage"] = {
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
                        "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
                    }

                # Extract model
                if "model" in data:
                    result["model"] = data["model"]

                # Extract finish reason
                if "stop_reason" in data:
                    result["finish_reasons"] = [data["stop_reason"]]

                # Check for error
                if "error" in data:
                    result["error"] = str(data["error"])

            except json.JSONDecodeError:
                pass

        # Check stderr for errors
        if stderr and "error" not in result:
            # Common error patterns
            if "rate limit" in stderr.lower():
                result["error"] = "Rate limit exceeded"
            elif "timeout" in stderr.lower():
                result["error"] = "Request timeout"
            elif "api key" in stderr.lower():
                result["error"] = "API key issue"
            elif stderr.strip():
                result["error"] = stderr.strip()[:200]

        return result


class CaptureContext:
    """Context manager for model response capture."""

    def __init__(
        self,
        capture: ModelOutputCapture,
        prompt: str | None,
        model: str | None,
        extra: dict[str, Any],
    ):
        self._capture = capture
        self._prompt = prompt
        self._model = model
        self._extra = extra
        self._response: ModelResponse | None = None
        self._output: str | None = None
        self._error: str | None = None
        self._token_usage: TokenUsage | dict[str, int] | None = None
        self._finish_reasons: list[str] | None = None

    def __enter__(self) -> "CaptureContext":
        self._response = self._capture.start_capture(
            prompt=self._prompt,
            model=self._model,
            **self._extra,
        )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_val:
            self._error = str(exc_val)

        if self._response:
            self._capture.complete_capture(
                self._response,
                output=self._output,
                error=self._error,
                token_usage=self._token_usage,
                finish_reasons=self._finish_reasons,
                model=self._model,
            )

    def set_output(self, output: str, stderr: str = "") -> None:
        """Set the model output and parse for metadata."""
        self._output = output

        # Try to parse Claude output for token usage etc.
        parsed = self._capture.parse_claude_output(output, stderr)

        if "token_usage" in parsed and self._token_usage is None:
            self._token_usage = parsed["token_usage"]
        if "model" in parsed and self._model is None:
            self._model = parsed["model"]
        if "finish_reasons" in parsed and self._finish_reasons is None:
            self._finish_reasons = parsed["finish_reasons"]
        if "error" in parsed and self._error is None:
            self._error = parsed["error"]

    def set_error(self, error: str) -> None:
        """Set an error message."""
        self._error = error

    def set_token_usage(self, usage: TokenUsage | dict[str, int]) -> None:
        """Set token usage information."""
        self._token_usage = usage

    def set_finish_reasons(self, reasons: list[str]) -> None:
        """Set finish reasons."""
        self._finish_reasons = reasons

    def set_model(self, model: str) -> None:
        """Set the model used."""
        self._model = model

    @property
    def response(self) -> ModelResponse | None:
        """Get the response object (available after context exit)."""
        return self._response


# Singleton instance with thread-safe initialization
_model_capture: ModelOutputCapture | None = None
_model_capture_lock = threading.Lock()


def get_model_capture(
    output_dir: Path | str | None = None,
    store_full_responses: bool | None = None,
) -> ModelOutputCapture:
    """Get or create the global ModelOutputCapture instance.

    This function provides access to a singleton ModelOutputCapture instance.
    The singleton is lazily initialized on first call and reused thereafter.

    **Thread Safety**: The singleton initialization is thread-safe.

    **Configuration Behavior**:
    - If called without parameters: returns the singleton (creates it if needed)
    - If called with parameters: creates and returns a NEW instance (not the singleton)
      This allows creating custom instances while preserving the global singleton.

    Example:
        # Get/create the global singleton
        capture = get_model_capture()

        # Create a separate instance with custom config (does NOT modify singleton)
        custom = get_model_capture(output_dir="/custom/path", store_full_responses=False)

        # This still returns the original singleton
        same_capture = get_model_capture()  # same_capture is capture

    Args:
        output_dir: Override output directory. If provided, creates a new instance.
        store_full_responses: Override storage setting. If provided, creates a new instance.

    Returns:
        ModelOutputCapture instance (singleton if no params, new instance otherwise)
    """
    global _model_capture

    # If parameters provided, create new instance (not the singleton)
    # This allows creating custom-configured instances for specific use cases
    if output_dir is not None or store_full_responses is not None:
        env_dir = os.environ.get("JIB_MODEL_OUTPUT_DIR")
        env_store = os.environ.get("JIB_STORE_MODEL_OUTPUT", "true").lower() == "true"

        return ModelOutputCapture(
            output_dir=output_dir or env_dir,
            store_full_responses=store_full_responses
            if store_full_responses is not None
            else env_store,
        )

    # Thread-safe singleton initialization
    if _model_capture is None:
        with _model_capture_lock:
            # Double-checked locking pattern
            if _model_capture is None:
                env_dir = os.environ.get("JIB_MODEL_OUTPUT_DIR")
                env_store = os.environ.get("JIB_STORE_MODEL_OUTPUT", "true").lower() == "true"

                _model_capture = ModelOutputCapture(
                    output_dir=env_dir,
                    store_full_responses=env_store,
                )

    return _model_capture


def reset_model_capture() -> None:
    """Reset the global ModelOutputCapture singleton.

    This is primarily useful for testing. In production, the singleton
    should persist for the lifetime of the process.
    """
    global _model_capture
    with _model_capture_lock:
        _model_capture = None


def capture_model_response(
    prompt: str | None = None,
    model: str | None = None,
    **extra: Any,
) -> CaptureContext:
    """Convenience function to capture a model response.

    Usage:
        from jib_logging.model_capture import capture_model_response

        with capture_model_response(prompt="Hello") as ctx:
            result = subprocess.run(["claude", ...])
            ctx.set_output(result.stdout)
    """
    return get_model_capture().capture_response(prompt, model, **extra)
