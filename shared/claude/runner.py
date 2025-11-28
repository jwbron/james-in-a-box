"""
Claude CLI runner for non-interactive mode.

This module provides functions for running Claude in non-interactive (stdin) mode,
which allows full access to tools and filesystem unlike the --print flag.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


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


def run_claude(
    prompt: str,
    *,
    timeout: int = 300,
    cwd: Path | str | None = None,
    capture_output: bool = True,
) -> ClaudeResult:
    """Run Claude CLI in non-interactive mode.

    Runs Claude with input via stdin (not --print flag which creates a restricted
    session). This allows full access to tools and filesystem.

    Args:
        prompt: The prompt to send to Claude via stdin.
        timeout: Maximum time in seconds to wait for Claude (default: 300 = 5 min).
            Common values:
            - 120: Simple analysis tasks
            - 300: Standard tasks (default)
            - 600: Complex tasks (10 min)
            - 900: Very complex tasks (15 min)
        cwd: Working directory for Claude. If None, uses current directory.
        capture_output: If True, capture stdout/stderr. If False, let them
            pass through to the console.

    Returns:
        ClaudeResult with success status, output, and any error information.

    Example:
        result = run_claude(
            prompt="Analyze this code and fix the bug",
            timeout=600,
            cwd=Path.home() / "khan" / "my-repo",
        )

        if result.success:
            print(f"Claude output: {result.stdout}")
        else:
            print(f"Error: {result.error}")

    Raises:
        No exceptions are raised. All errors are captured in ClaudeResult.error.
    """
    # Normalize cwd to string if provided
    cwd_str = str(cwd) if cwd else None

    try:
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions"],
            check=False,
            input=prompt,
            text=True,
            capture_output=capture_output,
            timeout=timeout,
            cwd=cwd_str,
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
