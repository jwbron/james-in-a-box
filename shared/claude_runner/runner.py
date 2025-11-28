"""
Claude Runner - Core implementation for invoking Claude CLI.

This module provides a consistent way to invoke Claude Code CLI in
non-interactive mode across all jib tasks. It passes the prompt via
stdin (NOT --print mode, which creates a restricted session).

Key features:
- Consistent invocation pattern across all callers
- Automatic timeout handling
- Structured result with success/failure indication
- Optional interactive mode for real-time output
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClaudeResult:
    """Result of a Claude CLI invocation.

    Attributes:
        success: True if Claude exited with code 0
        returncode: The process return code
        stdout: Standard output (empty string if not captured)
        stderr: Standard error (empty string if not captured)
        error: Human-readable error message if failed
        timed_out: True if the process timed out
    """

    success: bool
    returncode: int
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    timed_out: bool = False


def check_claude_cli() -> bool:
    """Check if the claude CLI is available.

    Returns:
        True if claude CLI is installed and responds to --version
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


def run_claude(
    prompt: str,
    *,
    timeout: int = 300,
    cwd: str | Path | None = None,
    capture_output: bool = True,
    interactive: bool = False,
) -> ClaudeResult:
    """Run Claude in non-interactive mode with the given prompt.

    This function passes the prompt via stdin, which gives Claude full
    access to tools and filesystem. DO NOT use --print mode, which
    creates a restricted session.

    Args:
        prompt: The prompt to send to Claude
        timeout: Maximum time in seconds to wait (default: 300)
        cwd: Working directory for Claude (default: current directory)
        capture_output: Whether to capture stdout/stderr (default: True)
            Set to False for interactive mode or when streaming output
        interactive: If True, don't capture output (real-time display)
            This is mutually exclusive with capture_output

    Returns:
        ClaudeResult with success status and output

    Examples:
        # Basic usage
        result = run_claude("Analyze this code and suggest fixes")
        if result.success:
            print(result.stdout)

        # With timeout and working directory
        result = run_claude(
            prompt="Fix the lint errors in this file",
            timeout=600,
            cwd="/path/to/repo",
        )

        # Interactive mode (output streams to console)
        result = run_claude(
            prompt="Help me debug this issue",
            interactive=True,
        )
    """
    # Validate arguments
    if interactive:
        capture_output = False

    # Convert cwd to string if Path
    cwd_str = str(cwd) if cwd else None

    try:
        # Run Claude via stdin (NOT --print which creates restricted session)
        # --dangerously-skip-permissions allows tool use without interactive prompts
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions"],
            check=False,
            input=prompt,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            cwd=cwd_str,
        )

        if result.returncode == 0:
            return ClaudeResult(
                success=True,
                returncode=0,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
            )
        else:
            error_msg = f"Claude exited with code {result.returncode}"
            if capture_output and result.stderr:
                error_msg += f": {result.stderr[:200]}"

            return ClaudeResult(
                success=False,
                returncode=result.returncode,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
                error=error_msg,
            )

    except subprocess.TimeoutExpired:
        return ClaudeResult(
            success=False,
            returncode=-1,
            error=f"Claude timed out after {timeout} seconds",
            timed_out=True,
        )

    except FileNotFoundError:
        return ClaudeResult(
            success=False,
            returncode=-1,
            error="Claude CLI not found - is it installed?",
        )

    except Exception as e:
        return ClaudeResult(
            success=False,
            returncode=-1,
            error=f"Error invoking Claude: {e}",
        )
