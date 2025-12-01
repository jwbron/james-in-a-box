"""
Host-side Claude wrapper using jib --exec.

This module provides a host-side interface for running Claude CLI. Since Claude
is only available inside the jib container, this wrapper uses `jib --exec` to
invoke the container-side claude-runner.py script.

IMPORTANT: This module is for HOST-SIDE code only. Container-side code should
import directly from `claude` (shared/claude).

Usage:
    from host_services.shared.jib_claude import run_claude, ClaudeResult

    result = run_claude(
        prompt="Analyze this code",
        timeout=300,
        cwd=Path("/path/to/repo"),
    )

    if result.success:
        print(result.stdout)
    else:
        print(f"Error: {result.error}")

This mirrors the interface of shared/claude/runner.py but uses jib --exec
to run Claude inside the container.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClaudeResult:
    """Result of a Claude CLI invocation via jib.

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


def is_jib_available() -> bool:
    """Check if jib is available and working.

    Returns:
        True if `jib --help` succeeds, False otherwise.
    """
    try:
        result = subprocess.run(
            ["jib", "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def run_claude(
    prompt: str,
    *,
    timeout: int = 300,
    cwd: Path | str | None = None,
    stream: bool = False,
) -> ClaudeResult:
    """Run Claude CLI via jib container.

    This function invokes `jib --exec python3 claude-runner.py` to run Claude
    inside the container, since Claude CLI is only available there.

    Args:
        prompt: The prompt to send to Claude.
        timeout: Maximum time in seconds for Claude to respond (default: 300).
        cwd: Working directory for Claude inside the container.
        stream: If True, stream output to stderr during execution.

    Returns:
        ClaudeResult with success status, output, and any error information.
    """
    # Container path for the claude-runner script
    runner_path = (
        "/home/jwies/khan/james-in-a-box/jib-container/jib-tasks/claude-runner.py"
    )

    # Write prompt to a temp file to avoid shell escaping issues with large prompts
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="claude-prompt-"
    ) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        # Build command
        cmd = [
            "jib",
            "--exec",
            "python3",
            runner_path,
            "--prompt-file",
            prompt_file,
            "--timeout",
            str(timeout),
        ]

        if cwd:
            cmd.extend(["--cwd", str(cwd)])

        if stream:
            cmd.append("--stream")

        # Run jib --exec with generous timeout (jib startup + claude timeout)
        # Add 120 seconds for container startup overhead
        jib_timeout = timeout + 120

        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=jib_timeout,
        )

        # Parse the JSON response from claude-runner.py
        if result.returncode == 0 or result.stdout.strip():
            try:
                response = json.loads(result.stdout.strip())
                return ClaudeResult(
                    success=response.get("success", False),
                    stdout=response.get("stdout", ""),
                    stderr=response.get("stderr", ""),
                    returncode=response.get("returncode", -1),
                    error=response.get("error"),
                )
            except json.JSONDecodeError as e:
                # If we can't parse JSON, return the raw output as an error
                return ClaudeResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    returncode=result.returncode,
                    error=f"Failed to parse claude-runner response: {e}",
                )
        else:
            # jib --exec failed before claude-runner could produce output
            return ClaudeResult(
                success=False,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                error=f"jib --exec failed with code {result.returncode}",
            )

    except subprocess.TimeoutExpired:
        return ClaudeResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error=f"jib --exec timed out after {jib_timeout} seconds",
        )

    except FileNotFoundError:
        return ClaudeResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error="jib command not found - is it in PATH?",
        )

    except Exception as e:
        return ClaudeResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error=f"Error running jib: {e}",
        )

    finally:
        # Clean up temp file
        try:
            Path(prompt_file).unlink()
        except OSError:
            pass


def is_claude_available() -> bool:
    """Check if Claude is available (via jib).

    This checks if jib is available, which is a prerequisite for running Claude.
    The actual Claude availability is inside the container.

    Returns:
        True if jib is available, False otherwise.
    """
    return is_jib_available()
