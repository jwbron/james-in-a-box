"""
Claude CLI runner for non-interactive mode.

This module provides functions for running Claude in non-interactive (stdin) mode,
which allows full access to tools and filesystem unlike the --print flag.

Supports both buffered and streaming output modes.
"""

import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Callable, TextIO


@dataclass
class ClaudeResult:
    """Result of a Claude CLI invocation.

    Attributes:
        success: True if Claude exited with code 0
        stdout: Standard output from Claude
        stderr: Standard error from Claude
        returncode: Exit code from Claude
        error: Human-readable error message if something went wrong
    """

    success: bool
    stdout: str
    stderr: str
    returncode: int
    error: str | None = None


def is_claude_available() -> bool:
    """Check if Claude CLI is available and working.

    Returns:
        True if `claude --version` succeeds, False otherwise.

    Example:
        if not is_claude_available():
            print("Claude CLI not found - is it installed?")
            return
    """
    try:
        result = subprocess.run(
            ["claude", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _stream_pipe(
    pipe: TextIO,
    buffer: StringIO,
    output_stream: TextIO | None,
    prefix: str = "",
) -> None:
    """Read from a pipe and write to buffer and optionally to an output stream.

    Args:
        pipe: Input pipe to read from (stdout or stderr from process)
        buffer: StringIO buffer to capture output
        output_stream: Optional stream to write to (e.g., sys.stdout)
        prefix: Optional prefix to add to each line when streaming
    """
    for line in pipe:
        buffer.write(line)
        if output_stream is not None:
            if prefix:
                output_stream.write(f"{prefix}{line}")
            else:
                output_stream.write(line)
            output_stream.flush()


def run_claude(
    prompt: str,
    *,
    timeout: int = 1800,
    cwd: Path | str | None = None,
    capture_output: bool = True,
    stream: bool = True,
    stream_to: TextIO | None = None,
    stream_prefix: str = "",
    on_output: Callable[[str], None] | None = None,
) -> ClaudeResult:
    """Run Claude CLI in non-interactive mode.

    Runs Claude with input via stdin (not --print flag which creates a restricted
    session). This allows full access to tools and filesystem.

    By default, output is streamed line-by-line to stdout as it arrives, which
    provides visibility into long-running tasks. Output is always captured in
    ClaudeResult regardless of streaming.

    Args:
        prompt: The prompt to send to Claude via stdin.
        timeout: Maximum time in seconds to wait for Claude (default: 1800 = 30 min).
        cwd: Working directory for Claude. If None, uses current directory.
        capture_output: If True, capture stdout/stderr. If False, let them
            pass through to the console (ignored if stream=True).
        stream: If True (default), stream output line-by-line as it arrives.
            Output is still captured in ClaudeResult.stdout/stderr.
            Set to False for buffered (silent) mode.
        stream_to: Where to stream output. Defaults to sys.stdout if stream=True.
            Can be any file-like object (e.g., sys.stderr, open file).
        stream_prefix: Optional prefix to add to each line when streaming.
            Useful for distinguishing Claude output, e.g., "[claude] ".
        on_output: Optional callback function called for each line of stdout.
            Receives the line as a string. Useful for custom processing/logging.

    Returns:
        ClaudeResult with success status, output, and any error information.

    Example:
        # Default usage - streams to stdout in real-time
        result = run_claude(
            prompt="Analyze this code and fix the bug",
            cwd=Path.home() / "khan" / "my-repo",
        )

        if result.success:
            print(f"Claude completed successfully")
        else:
            print(f"Error: {result.error}")

        # Silent/buffered mode (no streaming)
        result = run_claude(
            prompt="Fix the bug in main.py",
            stream=False,  # Buffer output, don't print
        )
        print(result.stdout)  # Access output after completion

        # Streaming with prefix
        result = run_claude(
            prompt="Analyze the codebase",
            stream_prefix="[claude] ",  # Prefix each line
        )

        # Custom callback for each line (e.g., for logging)
        def log_line(line: str):
            logger.info("Claude output", line=line.strip())

        result = run_claude(
            prompt="Run tests",
            on_output=log_line,
        )

    Raises:
        No exceptions are raised. All errors are captured in ClaudeResult.error.
    """
    # Normalize cwd to string if provided
    cwd_str = str(cwd) if cwd else None

    # Set up environment with auto-update disabled to prevent prompts in automation
    env = os.environ.copy()
    env["DISABLE_AUTOUPDATER"] = "1"

    # Determine output stream for streaming mode
    if stream and stream_to is None:
        stream_to = sys.stdout

    try:
        if stream:
            # Streaming mode: use Popen for real-time output
            return _run_claude_streaming(
                prompt=prompt,
                timeout=timeout,
                cwd_str=cwd_str,
                env=env,
                stream_to=stream_to,
                stream_prefix=stream_prefix,
                on_output=on_output,
            )
        else:
            # Buffered mode: use subprocess.run
            result = subprocess.run(
                ["claude", "--dangerously-skip-permissions"],
                check=False,
                input=prompt,
                text=True,
                capture_output=capture_output,
                timeout=timeout,
                cwd=cwd_str,
                env=env,
            )

            return ClaudeResult(
                success=result.returncode == 0,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
                returncode=result.returncode,
                error=None
                if result.returncode == 0
                else f"Claude exited with code {result.returncode}",
            )

    except subprocess.TimeoutExpired:
        return ClaudeResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error=f"Claude timed out after {timeout} seconds",
        )

    except FileNotFoundError:
        return ClaudeResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error="Claude CLI not found - is it installed?",
        )

    except Exception as e:
        return ClaudeResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error=f"Error running Claude: {e}",
        )


def _run_claude_streaming(
    prompt: str,
    timeout: int,
    cwd_str: str | None,
    env: dict[str, str],
    stream_to: TextIO | None,
    stream_prefix: str,
    on_output: Callable[[str], None] | None,
) -> ClaudeResult:
    """Internal implementation for streaming mode.

    Uses Popen to read output line-by-line as it arrives.
    """
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()

    process = subprocess.Popen(
        ["claude", "--dangerously-skip-permissions"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd_str,
        env=env,
    )

    # Send prompt to stdin and close it
    if process.stdin:
        process.stdin.write(prompt)
        process.stdin.close()

    # Create threads to read stdout and stderr concurrently
    def read_stdout():
        if process.stdout:
            for line in process.stdout:
                stdout_buffer.write(line)
                if stream_to is not None:
                    if stream_prefix:
                        stream_to.write(f"{stream_prefix}{line}")
                    else:
                        stream_to.write(line)
                    stream_to.flush()
                if on_output is not None:
                    on_output(line)

    def read_stderr():
        if process.stderr:
            for line in process.stderr:
                stderr_buffer.write(line)
                # Optionally stream stderr too (to stderr)
                if stream_to is not None:
                    sys.stderr.write(line)
                    sys.stderr.flush()

    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)

    stdout_thread.start()
    stderr_thread.start()

    # Wait for process to complete with timeout
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        # Wait for threads to finish reading any remaining output
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        return ClaudeResult(
            success=False,
            stdout=stdout_buffer.getvalue(),
            stderr=stderr_buffer.getvalue(),
            returncode=-1,
            error=f"Claude timed out after {timeout} seconds",
        )

    # Wait for reader threads to complete
    stdout_thread.join()
    stderr_thread.join()

    return ClaudeResult(
        success=returncode == 0,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
        returncode=returncode,
        error=None if returncode == 0 else f"Claude exited with code {returncode}",
    )


