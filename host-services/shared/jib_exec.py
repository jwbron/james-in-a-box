"""
Host-side jib execution wrapper for running container-side tasks.

This module provides a standardized way for host services to invoke container-side
processors via `jib --exec`. All host services that need to run code inside the
container should use this module instead of directly calling Claude or other
container-only resources.

The pattern:
1. Host service detects a task (file, event, etc.)
2. Host service calls jib_exec() with task type and context
3. Container-side processor handles the task (may call Claude, access tools, etc.)
4. Result is returned to host service

IMPORTANT: This is the ONLY way host services should interact with container code.
Do NOT import container modules directly (they won't work on the host).

Usage:
    from jib_exec import jib_exec, JibResult

    # Run a container-side processor
    result = jib_exec(
        processor="github-processor",
        task_type="pr_review",
        context={"pr_number": 123, "repo": "james-in-a-box"},
        timeout=300,
    )

    if result.success:
        data = result.json_output  # Parsed JSON from processor
    else:
        print(f"Failed: {result.error}")

See also:
- slack-receiver.py: Example of triggering processing via jib --exec
- github-watcher.py: Example of parallel task execution via jib --exec
"""

import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class JibResult:
    """Result from a jib --exec invocation.

    Attributes:
        success: True if jib and the processor both exited with code 0
        stdout: Raw stdout from the process
        stderr: Raw stderr from the process
        returncode: Exit code from the process
        error: Human-readable error message if something went wrong
        json_output: Parsed JSON from stdout if processor returned JSON
    """

    success: bool
    stdout: str
    stderr: str
    returncode: int
    error: str | None = None
    json_output: dict | None = None


def get_container_username() -> str:
    """Get the username used inside the container.

    The container mirrors the host user, so we use the current user.

    Raises:
        RuntimeError: If USER environment variable is not set.
    """
    username = os.environ.get("USER")
    if not username:
        raise RuntimeError("USER environment variable not set")
    return username


def get_jib_path() -> Path:
    """Get the path to the jib executable.

    First checks if 'jib' is available in PATH (consistent with other host services),
    then falls back to the standard location in ~/repos/james-in-a-box/bin/jib.
    """
    # Check PATH first for consistency with other host services
    jib_in_path = shutil.which("jib")
    if jib_in_path:
        return Path(jib_in_path)

    # Fall back to standard location
    return Path.home() / "repos" / "james-in-a-box" / "bin" / "jib"


def host_to_container_path(host_path: str | Path) -> str:
    """Convert a host path to the equivalent container path.

    Host paths like ~/.jib-sharing/... become ~/sharing/... in the container.
    Host paths like ~/repos/... remain the same (mounted at same location).

    Args:
        host_path: Path on the host system

    Returns:
        Equivalent path inside the container
    """
    host_path = str(Path(host_path).expanduser())
    username = get_container_username()

    # ~/.jib-sharing on host -> ~/sharing in container
    jib_sharing = str(Path.home() / ".jib-sharing")
    if host_path.startswith(jib_sharing):
        return host_path.replace(jib_sharing, f"/home/{username}/sharing")

    # ~/khan is mounted at same location
    return host_path


def jib_exec(
    processor: str,
    task_type: str,
    context: dict[str, Any],
    *,
    timeout: int | None = None,
    stream_to_log: Path | None = None,
) -> JibResult:
    """Execute a container-side processor via jib --exec.

    This is the standard way for host services to run tasks inside the container.
    The processor receives the task type and context as command-line arguments.

    Args:
        processor: Name of the processor executable (must be in container PATH via
                  /opt/jib-runtime/bin), or a relative path like
                  "jib-container/jib-tasks/github/github-processor.py" for backwards
                  compatibility.
                  Examples:
                    - "github-processor" (preferred - uses PATH)
                    - "analysis-processor" (preferred - uses PATH)
                    - "jib-container/jib-tasks/github/github-processor.py" (legacy)
        task_type: Type of task for the processor (e.g., "check_failure", "doc_generation")
        context: Dictionary of context data for the processor
        timeout: Optional timeout in seconds. If None, waits indefinitely.
        stream_to_log: Optional path to stream stdout to a log file in real-time.

    Returns:
        JibResult with success status, output, and any errors.

    Example:
        # Preferred - processor is in PATH inside container
        result = jib_exec(
            processor="github-processor",
            task_type="pr_review",
            context={"pr_number": 123, "repo": "james-in-a-box"},
        )

        # Legacy - still works for backwards compatibility
        result = jib_exec(
            processor="jib-container/jib-tasks/github/github-processor.py",
            task_type="pr_review",
            context={"pr_number": 123, "repo": "james-in-a-box"},
        )
    """
    jib_path = get_jib_path()
    username = get_container_username()

    # Determine if processor is a simple name (in PATH) or a path
    # Simple names don't contain "/" or end with ".py"
    is_simple_name = "/" not in processor and not processor.endswith(".py")

    if is_simple_name:
        # Processor is in PATH inside container via /opt/jib-runtime/bin
        container_processor = processor
    elif processor.startswith("/"):
        # Absolute path inside container
        container_processor = processor
    else:
        # Legacy: relative path from ~/repos/james-in-a-box/
        container_processor = f"/home/{username}/repos/james-in-a-box/{processor}"

    # Serialize context to JSON
    context_json = json.dumps(context)

    # Build command - only include "python3" for legacy full paths
    if is_simple_name:
        cmd = [
            str(jib_path),
            "--exec",
            container_processor,
            "--task",
            task_type,
            "--context",
            context_json,
        ]
    else:
        cmd = [
            str(jib_path),
            "--exec",
            "python3",
            container_processor,
            "--task",
            task_type,
            "--context",
            context_json,
        ]

    try:
        if stream_to_log:
            # Stream output to log file while capturing stderr
            return _run_with_streaming(cmd, stream_to_log, timeout)
        else:
            # Simple capture mode
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )

            return _process_result(result)

    except subprocess.TimeoutExpired:
        return JibResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error=f"jib --exec timed out after {timeout} seconds",
        )

    except FileNotFoundError:
        return JibResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error=f"jib command not found at {jib_path}",
        )

    except Exception as e:
        return JibResult(
            success=False,
            stdout="",
            stderr="",
            returncode=-1,
            error=f"Error running jib: {e}",
        )


def _run_with_streaming(cmd: list[str], log_file: Path, timeout: int | None) -> JibResult:
    """Run command with stdout streaming to a log file.

    This allows real-time monitoring of long-running tasks.
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    stdout_lines = []
    stderr_lines = []

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Thread to read stderr
    def read_stderr():
        if process.stderr:
            for line in process.stderr:
                stderr_lines.append(line)

    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

    # Stream stdout to log file
    with open(log_file, "w") as f:
        if process.stdout:
            for line in process.stdout:
                stdout_lines.append(line)
                f.write(line)
                f.flush()

    # Wait for completion
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        return JibResult(
            success=False,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            returncode=-1,
            error=f"Process timed out after {timeout} seconds",
        )

    stderr_thread.join(timeout=5)

    stdout = "".join(stdout_lines)
    stderr = "".join(stderr_lines)

    return _process_result_from_parts(process.returncode, stdout, stderr)


def _process_result(result: subprocess.CompletedProcess) -> JibResult:
    """Process a completed subprocess result into a JibResult."""
    return _process_result_from_parts(result.returncode, result.stdout, result.stderr)


def _extract_json_from_output(stdout: str) -> dict | None:
    """Extract JSON object from stdout that may contain status/progress messages.

    The jib command outputs status bar messages before the actual JSON output
    from the processor. This function searches for JSON in the output.

    Strategies:
    1. Try parsing the entire output as JSON (clean output case)
    2. Find JSON by looking for the processor's output format ({"success": ...})
    3. Find any complete JSON object by matching braces
    4. Try each line that looks like JSON

    Args:
        stdout: Raw stdout from jib command

    Returns:
        Parsed JSON dict if found, None otherwise
    """
    stripped = stdout.strip()
    if not stripped:
        return None

    # Strategy 1: Try entire output (handles clean case)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Find JSON by looking for the processor's output format
    # analysis-processor.py outputs: {"success": ..., "result": ..., "error": ...}
    # This is the most reliable pattern for our use case
    success_match = re.search(r'\{"success":\s*(true|false)', stdout)
    if success_match:
        # Find the full JSON object by matching braces
        start = success_match.start()
        brace_count = 0
        end = start
        for i in range(start, len(stdout)):
            if stdout[i] == "{":
                brace_count += 1
            elif stdout[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        if end > start:
            try:
                return json.loads(stdout[start:end])
            except json.JSONDecodeError:
                pass

    # Strategy 3: Find the largest complete JSON object by matching braces
    # Start from each { and find its matching }
    candidates = []
    for i, char in enumerate(stdout):
        if char == "{":
            brace_count = 0
            for j in range(i, len(stdout)):
                if stdout[j] == "{":
                    brace_count += 1
                elif stdout[j] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        candidate = stdout[i : j + 1]
                        try:
                            parsed = json.loads(candidate)
                            candidates.append((len(candidate), parsed))
                        except json.JSONDecodeError:
                            pass
                        break

    # Return the largest valid JSON object (most likely to be the full processor output)
    if candidates:
        candidates.sort(reverse=True)  # Sort by size, largest first
        return candidates[0][1]

    # Strategy 4: Try each line that looks like JSON
    for line in stdout.split("\n"):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    return None


def _process_result_from_parts(returncode: int, stdout: str, stderr: str) -> JibResult:
    """Build a JibResult from return code and output strings."""
    success = returncode == 0
    error = None
    json_output = None

    if not success:
        # Extract error message from stderr
        error = f"jib --exec exited with code {returncode}"
        if stderr:
            # Look for error patterns
            for line in stderr.split("\n"):
                line_lower = line.lower()
                if any(kw in line_lower for kw in ["error:", "failed:", "exception:"]):
                    error = f"{error}: {line.strip()[:200]}"
                    break

    # Try to extract JSON from stdout (handles mixed output with status messages)
    if stdout.strip():
        json_output = _extract_json_from_output(stdout)

        # If we expected JSON but couldn't extract it, add a warning
        if json_output is None:
            stripped = stdout.strip()
            # Check if there's any hint that JSON was expected
            if '{"success"' in stripped or stripped.startswith(("{", "[")):
                if error:
                    error = f"{error}; Could not extract JSON from output"
                else:
                    error = f"Could not extract JSON from output (length: {len(stdout)} chars)"

    return JibResult(
        success=success,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        error=error,
        json_output=json_output,
    )


def is_jib_available() -> bool:
    """Check if jib is available and working.

    Returns:
        True if `jib --help` succeeds, False otherwise.
    """
    jib_path = get_jib_path()
    try:
        result = subprocess.run(
            [str(jib_path), "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False
