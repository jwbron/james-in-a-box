"""
jib_logging - Structured logging library for jib components.

Provides a unified logging interface with JSON output, context propagation,
and GCP Cloud Logging compatibility.

Usage:
    from jib_logging import get_logger, ContextScope

    # Get a logger
    logger = get_logger("github-watcher")

    # Simple logging
    logger.info("Processing PR", pr_number=123, repository="owner/repo")

    # With context scope (all logs in scope include context)
    with ContextScope(task_id="bd-abc123", repository="owner/repo"):
        logger.info("Starting task")
        logger.info("Task completed")

    # Bound logger (all logs include bound fields)
    bound = logger.with_context(task_id="bd-abc123")
    bound.info("Processing step 1")
    bound.info("Processing step 2")

    # Tool wrappers (Phase 2)
    from jib_logging.wrappers import bd, git, gh

    result = git.push("origin", "main")
    # Automatically logs with timing and context

    # Model output capture (Phase 3)
    from jib_logging.model_capture import capture_model_response

    with capture_model_response(prompt="Explain Python") as ctx:
        result = subprocess.run(["claude", "--print", "-p", "Explain Python"])
        ctx.set_output(result.stdout)
    # Automatically logs token usage, timing, and stores full response

Features:
    - Structured JSON logs for production/GCP Cloud Logging
    - Human-readable console output for development
    - OpenTelemetry trace context propagation
    - Beads task ID correlation
    - File handler with rotation support
    - Tool wrappers for bd, git, gh, claude (Phase 2)
    - Model output capture with token tracking (Phase 3)
"""

from .context import (
    ContextScope,
    LogContext,
    context_from_env,
    get_current_context,
    get_or_create_context,
    set_current_context,
)
from .formatters import ConsoleFormatter, JsonFormatter
from .logger import BoundLogger, JibLogger, configure_root_logging, get_logger
from .model_capture import (
    CaptureContext,
    ModelOutputCapture,
    ModelResponse,
    TokenUsage,
    capture_model_response,
    get_model_capture,
)


__all__ = [
    "BoundLogger",
    # Model capture (Phase 3)
    "CaptureContext",
    "ConsoleFormatter",
    "ContextScope",
    # Logger classes
    "JibLogger",
    # Formatters (for advanced use)
    "JsonFormatter",
    # Context management
    "LogContext",
    "ModelOutputCapture",
    "ModelResponse",
    "TokenUsage",
    # Model capture functions
    "capture_model_response",
    # Configuration
    "configure_root_logging",
    "context_from_env",
    "get_current_context",
    # Primary API
    "get_logger",
    "get_model_capture",
    "get_or_create_context",
    "set_current_context",
]

__version__ = "0.2.0"
