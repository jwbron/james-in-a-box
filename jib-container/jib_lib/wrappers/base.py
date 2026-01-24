"""
Base classes for tool wrappers.

Provides common functionality for wrapping command-line tools with logging.
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


def get_logger(name: str, component: str = "wrapper") -> logging.Logger:
    """Get a logger for the given name."""
    return logging.getLogger(f"jib.{component}.{name}")


def get_current_context():
    """Get the current logging context (stub - returns None in jib-container).

    The full context implementation is in shared/jib_logging/context.py.
    This stub allows the wrappers to work without the full logging infrastructure.
    """
    return None


@dataclass
class ToolResult:
    """Result from a wrapped tool invocation.

    Attributes:
        command: The full command that was executed
        exit_code: Process exit code (0 = success)
        stdout: Standard output as string
        stderr: Standard error as string
        duration_ms: Execution time in milliseconds
        success: Whether the command succeeded (exit_code == 0)
        extra: Additional context captured by the wrapper
    """

    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    success: bool = field(init=False)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.success = self.exit_code == 0

    def check(self) -> "ToolResult":
        """Raise an exception if the command failed.

        Returns:
            self if successful

        Raises:
            subprocess.CalledProcessError: If command failed
        """
        if not self.success:
            raise subprocess.CalledProcessError(
                self.exit_code,
                self.command,
                self.stdout,
                self.stderr,
            )
        return self


class ToolWrapper:
    """Base class for tool wrappers.

    Subclasses should:
    1. Set self.tool_name in __init__
    2. Override _extract_context() to capture tool-specific metadata
    3. Implement convenience methods for common operations
    """

    tool_name: str = "unknown"

    def __init__(self):
        """Initialize the wrapper with a dedicated logger."""
        self._logger = get_logger(f"tool-{self.tool_name}", component="wrapper")

    def run(
        self,
        *args: str,
        check: bool = False,
        capture_output: bool = True,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
    ) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            *args: Command arguments (tool name will be prepended)
            check: If True, raise exception on non-zero exit
            capture_output: If True, capture stdout/stderr
            timeout: Timeout in seconds (None = no timeout)
            cwd: Working directory for the command
            env: Environment variables to set (merged with current environment)
            input_text: Text to send to stdin

        Returns:
            ToolResult with command output and metadata

        Raises:
            subprocess.CalledProcessError: If check=True and command fails
            subprocess.TimeoutExpired: If timeout exceeded
        """
        command = [self.tool_name, *args]
        start_time = time.perf_counter()

        # Merge provided env with current environment to preserve PATH, etc.
        effective_env = None
        if env is not None:
            effective_env = os.environ.copy()
            effective_env.update(env)

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=effective_env,
                input=input_text,
            )

            duration_ms = (time.perf_counter() - start_time) * 1000

            tool_result = ToolResult(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                duration_ms=duration_ms,
                extra=self._extract_context(args, result.stdout, result.stderr),
            )

            self._log_invocation(tool_result)

            if check and not tool_result.success:
                tool_result.check()

            return tool_result

        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._log_timeout(command, duration_ms, timeout)
            raise

    def _extract_context(
        self,
        args: tuple[str, ...],
        stdout: str,
        stderr: str,
    ) -> dict[str, Any]:
        """Extract tool-specific context from command and output.

        Subclasses should override this to capture meaningful metadata.

        Args:
            args: Command arguments (without tool name)
            stdout: Standard output
            stderr: Standard error

        Returns:
            Dict of context fields to include in logs
        """
        return {}

    def _log_invocation(self, result: ToolResult) -> None:
        """Log a tool invocation."""
        ctx = get_current_context()

        log_kwargs: dict[str, Any] = {
            "tool": self.tool_name,
            "command": result.command,
            "exit_code": result.exit_code,
            "duration_ms": round(result.duration_ms, 2),
        }

        # Add context from current scope
        if ctx:
            if ctx.task_id:
                log_kwargs["task_id"] = ctx.task_id
            if ctx.repository:
                log_kwargs["repository"] = ctx.repository

        # Add tool-specific context
        log_kwargs.update(result.extra)

        if result.success:
            self._logger.info(
                f"{self.tool_name} command completed",
                **log_kwargs,
            )
        else:
            # Include stderr for failed commands
            log_kwargs["stderr"] = result.stderr[:500] if result.stderr else ""
            self._logger.error(
                f"{self.tool_name} command failed",
                **log_kwargs,
            )

    def _log_timeout(
        self,
        command: list[str],
        duration_ms: float,
        timeout: float | None,
    ) -> None:
        """Log a command timeout."""
        self._logger.error(
            f"{self.tool_name} command timed out",
            tool=self.tool_name,
            command=command,
            duration_ms=round(duration_ms, 2),
            timeout_seconds=timeout,
        )
