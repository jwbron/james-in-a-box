#!/usr/bin/env python3
"""Log file reading utilities for gateway.

This module provides functions to read log files from the filesystem
with appropriate size limits and pagination. It handles multiple log
locations:
- Container logs (~/.jib-sharing/container-logs/)
- Claude output logs (~/.jib-sharing/logs/)
- Model output files (/var/log/jib/model_output/)
"""

import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Add shared directory to path for jib_logging
_shared_path = Path(__file__).parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger

try:
    from .log_index import (
        DEFAULT_CONTAINER_LOGS_DIR,
        DEFAULT_CLAUDE_LOGS_DIR,
        DEFAULT_MODEL_OUTPUT_DIR,
        get_log_index,
    )
except ImportError:
    from log_index import (
        DEFAULT_CONTAINER_LOGS_DIR,
        DEFAULT_CLAUDE_LOGS_DIR,
        DEFAULT_MODEL_OUTPUT_DIR,
        get_log_index,
    )

logger = get_logger("gateway-sidecar.log_reader")

# Limits
MAX_LOG_LINES = 10000  # Maximum lines to return
MAX_LOG_SIZE_BYTES = 50 * 1024 * 1024  # 50MB max file size to read
MAX_SEARCH_RESULTS = 1000  # Maximum search results
SEARCH_TIMEOUT_SECONDS = 5  # Timeout for regex searches
MAX_PATTERN_LENGTH = 500  # Maximum regex pattern length
MAX_PATTERN_GROUPS = 10  # Maximum regex groups


@dataclass
class LogContent:
    """Log content with metadata."""

    task_id: str | None
    container_id: str | None
    log_file: str | None
    content: str
    lines: int
    truncated: bool
    size_bytes: int


@dataclass
class SearchResult:
    """A single search result."""

    log_file: str
    line_number: int
    content: str
    task_id: str | None
    container_id: str | None


class SearchTimeoutError(Exception):
    """Raised when search exceeds timeout."""

    pass


class PatternValidationError(Exception):
    """Raised when pattern fails validation."""

    pass


def validate_search_pattern(pattern: str) -> None:
    """Validate a search pattern for safety.

    Args:
        pattern: The regex pattern to validate

    Raises:
        PatternValidationError: If the pattern is invalid or potentially dangerous
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise PatternValidationError(f"Pattern too long (max {MAX_PATTERN_LENGTH} chars)")

    # Count groups (rough heuristic for complexity)
    group_count = pattern.count("(") - pattern.count("\\(")
    if group_count > MAX_PATTERN_GROUPS:
        raise PatternValidationError(f"Too many groups (max {MAX_PATTERN_GROUPS})")

    # Check for known ReDoS patterns (basic detection)
    # This is not exhaustive but catches common cases
    dangerous_patterns = [
        r"\(\.\*\)\+",  # (.*)+
        r"\(\.\+\)\+",  # (.+)+
        r"\([^)]*\+\)\+",  # (a+)+
        r"\([^)]*\*\)\+",  # (a*)+
    ]
    for dangerous in dangerous_patterns:
        if re.search(dangerous, pattern):
            raise PatternValidationError("Pattern may cause excessive backtracking")


def read_task_logs(task_id: str, max_lines: int = 1000) -> LogContent | None:
    """Read logs for a specific task.

    Looks for:
    1. Symlink at {task_id}.log -> {container_id}.log
    2. Container log with task_id content
    3. Claude output log at ~/.jib-sharing/logs/{task_id}.log

    Args:
        task_id: The task ID to read logs for
        max_lines: Maximum number of lines to return

    Returns:
        LogContent if logs found, None otherwise
    """
    max_lines = min(max_lines, MAX_LOG_LINES)

    # Try symlink first
    symlink_path = DEFAULT_CONTAINER_LOGS_DIR / f"{task_id}.log"
    if symlink_path.exists():
        return _read_log_file(symlink_path, task_id=task_id, max_lines=max_lines)

    # Look up container from index
    log_index = get_log_index()
    container_id = log_index.get_container_for_task(task_id)
    if container_id:
        container_log = DEFAULT_CONTAINER_LOGS_DIR / f"{container_id}.log"
        if container_log.exists():
            return _read_log_file(
                container_log,
                task_id=task_id,
                container_id=container_id,
                max_lines=max_lines,
            )

    # Try Claude output log
    claude_log = DEFAULT_CLAUDE_LOGS_DIR / f"{task_id}.log"
    if claude_log.exists():
        return _read_log_file(claude_log, task_id=task_id, max_lines=max_lines)

    return None


def read_container_logs(container_id: str, max_lines: int = 1000) -> LogContent | None:
    """Read logs for a specific container.

    Args:
        container_id: The container ID to read logs for
        max_lines: Maximum number of lines to return

    Returns:
        LogContent if logs found, None otherwise
    """
    max_lines = min(max_lines, MAX_LOG_LINES)
    container_log = DEFAULT_CONTAINER_LOGS_DIR / f"{container_id}.log"
    if container_log.exists():
        return _read_log_file(container_log, container_id=container_id, max_lines=max_lines)
    return None


def read_model_output(task_id: str) -> LogContent | None:
    """Read model output for a specific task.

    Args:
        task_id: The task ID to read model output for

    Returns:
        LogContent if model output found, None otherwise
    """
    # Model output files are named by task_id
    model_output_path = DEFAULT_MODEL_OUTPUT_DIR / f"{task_id}.json"
    if model_output_path.exists():
        return _read_log_file(model_output_path, task_id=task_id, max_lines=MAX_LOG_LINES)

    # Also check for .log extension
    model_output_path = DEFAULT_MODEL_OUTPUT_DIR / f"{task_id}.log"
    if model_output_path.exists():
        return _read_log_file(model_output_path, task_id=task_id, max_lines=MAX_LOG_LINES)

    return None


def search_logs(
    pattern: str,
    container_id: str,
    max_results: int = 100,
) -> list[SearchResult]:
    """Search logs for a pattern, scoped to a specific container.

    Only searches logs belonging to the specified container.

    Args:
        pattern: Regex pattern to search for
        container_id: Container to scope the search to
        max_results: Maximum number of results to return

    Returns:
        List of SearchResult objects

    Raises:
        PatternValidationError: If the pattern is invalid
        SearchTimeoutError: If the search exceeds the timeout
    """
    max_results = min(max_results, MAX_SEARCH_RESULTS)

    # Validate pattern
    validate_search_pattern(pattern)

    results: list[SearchResult] = []

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise PatternValidationError(f"Invalid regex pattern: {e}")

    # Get all tasks for this container from the index
    log_index = get_log_index()
    container_entries = log_index.list_entries(container_id=container_id, limit=1000)

    searched_files: set[str] = set()

    # Set up timeout handler
    def timeout_handler(signum, frame):
        raise SearchTimeoutError("Search timed out")

    # Only use SIGALRM on Unix systems
    use_timeout = hasattr(signal, "SIGALRM")
    if use_timeout:
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(SEARCH_TIMEOUT_SECONDS)

    try:
        for entry in container_entries:
            if len(results) >= max_results:
                break

            if not entry.log_file or entry.log_file in searched_files:
                continue

            searched_files.add(entry.log_file)
            log_path = Path(entry.log_file)

            if not log_path.exists():
                continue

            try:
                file_size = log_path.stat().st_size
                if file_size > MAX_LOG_SIZE_BYTES:
                    logger.warning(f"Skipping large log file: {log_path} ({file_size} bytes)")
                    continue

                with open(log_path) as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(
                                SearchResult(
                                    log_file=str(log_path),
                                    line_number=line_num,
                                    content=line.rstrip()[:500],  # Truncate long lines
                                    task_id=entry.task_id,
                                    container_id=entry.container_id,
                                )
                            )
                            if len(results) >= max_results:
                                break
            except Exception as e:
                logger.warning(f"Error searching log file {log_path}: {e}")

        # Also search the container's main log file
        container_log = DEFAULT_CONTAINER_LOGS_DIR / f"{container_id}.log"
        if container_log.exists() and str(container_log) not in searched_files:
            try:
                file_size = container_log.stat().st_size
                if file_size <= MAX_LOG_SIZE_BYTES:
                    with open(container_log) as f:
                        for line_num, line in enumerate(f, 1):
                            if len(results) >= max_results:
                                break
                            if regex.search(line):
                                results.append(
                                    SearchResult(
                                        log_file=str(container_log),
                                        line_number=line_num,
                                        content=line.rstrip()[:500],
                                        task_id=None,
                                        container_id=container_id,
                                    )
                                )
            except Exception as e:
                logger.warning(f"Error searching container log {container_log}: {e}")

    finally:
        if use_timeout:
            signal.alarm(0)  # Cancel alarm
            signal.signal(signal.SIGALRM, old_handler)

    return results


def _read_log_file(
    path: Path,
    task_id: str | None = None,
    container_id: str | None = None,
    max_lines: int = 1000,
) -> LogContent:
    """Read a log file with size limits.

    Args:
        path: Path to the log file
        task_id: Task ID to include in result (optional)
        container_id: Container ID to include in result (optional)
        max_lines: Maximum number of lines to read

    Returns:
        LogContent with file contents and metadata
    """
    # Resolve symlinks
    actual_path = path.resolve() if path.is_symlink() else path

    try:
        file_size = actual_path.stat().st_size
    except Exception as e:
        logger.error(f"Cannot stat log file {actual_path}: {e}")
        return LogContent(
            task_id=task_id,
            container_id=container_id,
            log_file=str(actual_path),
            content=f"Error reading log file: {e}",
            lines=0,
            truncated=False,
            size_bytes=0,
        )

    truncated = False

    if file_size > MAX_LOG_SIZE_BYTES:
        logger.warning(f"Log file exceeds size limit: {actual_path} ({file_size} bytes)")
        truncated = True

    lines: list[str] = []
    try:
        with open(actual_path) as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    truncated = True
                    break
                lines.append(line)
    except Exception as e:
        logger.error(f"Error reading log file {actual_path}: {e}")
        return LogContent(
            task_id=task_id,
            container_id=container_id,
            log_file=str(actual_path),
            content=f"Error reading log file: {e}",
            lines=0,
            truncated=False,
            size_bytes=0,
        )

    return LogContent(
        task_id=task_id,
        container_id=container_id,
        log_file=str(actual_path),
        content="".join(lines),
        lines=len(lines),
        truncated=truncated,
        size_bytes=file_size,
    )
