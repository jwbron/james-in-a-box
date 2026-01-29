#!/usr/bin/env python3
"""Log index reader for gateway-mediated log access.

This module provides thread-safe read access to the log index maintained
by container_logging.py. The index maps task_id -> container_id for
access control decisions.

The index is a JSON file at ~/.jib-sharing/container-logs/log-index.json
with structure:
{
    "task_to_container": {"task-id": "container-id", ...},
    "thread_to_task": {"thread-ts": "task-id", ...},
    "entries": [{"container_id": "...", "task_id": "...", ...}, ...]
}
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


# Add shared directory to path for jib_logging
_shared_path = Path(__file__).parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


logger = get_logger("gateway-sidecar.log_index")

# Default paths (configurable via environment)
DEFAULT_LOG_INDEX_PATH = Path.home() / ".jib-sharing" / "container-logs" / "log-index.json"
DEFAULT_CONTAINER_LOGS_DIR = Path.home() / ".jib-sharing" / "container-logs"
DEFAULT_CLAUDE_LOGS_DIR = Path.home() / ".jib-sharing" / "logs"
DEFAULT_MODEL_OUTPUT_DIR = Path("/var/log/jib/model_output")


@dataclass
class LogEntry:
    """A single log entry from the index."""

    container_id: str
    task_id: str | None
    thread_ts: str | None
    log_file: str | None
    timestamp: str


class LogIndex:
    """Thread-safe log index reader with caching.

    Uses mtime-based cache invalidation to avoid unnecessary file reads
    while ensuring fresh data when the index is updated.
    """

    def __init__(self, index_path: Path | None = None):
        self._index_path = index_path or DEFAULT_LOG_INDEX_PATH
        self._cache: dict[str, Any] | None = None
        self._cache_mtime: float = 0
        self._lock = Lock()

    def _load_index(self) -> dict[str, Any]:
        """Load index from file, using cache if file unchanged."""
        if not self._index_path.exists():
            return {"task_to_container": {}, "thread_to_task": {}, "entries": []}

        try:
            mtime = self._index_path.stat().st_mtime
            with self._lock:
                if self._cache is not None and mtime == self._cache_mtime:
                    return self._cache

            with open(self._index_path) as f:
                data = json.load(f)

            with self._lock:
                self._cache = data
                self._cache_mtime = mtime

            return data
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted log index JSON: {e}")
            return {"task_to_container": {}, "thread_to_task": {}, "entries": []}
        except Exception as e:
            logger.warning(f"Failed to load log index: {e}")
            return {"task_to_container": {}, "thread_to_task": {}, "entries": []}

    def get_container_for_task(self, task_id: str) -> str | None:
        """Look up the container ID that owns a task.

        Args:
            task_id: The task ID to look up

        Returns:
            The container_id that owns this task, or None if not found
        """
        index = self._load_index()
        return index.get("task_to_container", {}).get(task_id)

    def get_task_for_thread(self, thread_ts: str) -> str | None:
        """Look up the task ID for a Slack thread.

        Args:
            thread_ts: The Slack thread timestamp

        Returns:
            The task_id for this thread, or None if not found
        """
        index = self._load_index()
        return index.get("thread_to_task", {}).get(thread_ts)

    def list_entries(
        self,
        container_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LogEntry]:
        """List log entries, optionally filtered by container.

        Args:
            container_id: Filter to entries for this container (None for all)
            limit: Maximum number of entries to return
            offset: Number of entries to skip (for pagination)

        Returns:
            List of LogEntry objects, newest first
        """
        index = self._load_index()
        entries = index.get("entries", [])

        if container_id:
            entries = [e for e in entries if e.get("container_id") == container_id]

        # Return newest first
        entries = list(reversed(entries))
        return [
            LogEntry(
                container_id=e.get("container_id", ""),
                task_id=e.get("task_id"),
                thread_ts=e.get("thread_ts"),
                log_file=e.get("log_file"),
                timestamp=e.get("timestamp", ""),
            )
            for e in entries[offset : offset + limit]
        ]

    def get_tasks_for_container(self, container_id: str) -> list[str]:
        """Get all task IDs associated with a container.

        Args:
            container_id: The container to look up tasks for

        Returns:
            List of task_id strings belonging to this container
        """
        index = self._load_index()
        task_to_container = index.get("task_to_container", {})
        return [task_id for task_id, cid in task_to_container.items() if cid == container_id]


# Singleton instance
_log_index: LogIndex | None = None


def get_log_index() -> LogIndex:
    """Get the singleton LogIndex instance."""
    global _log_index
    if _log_index is None:
        _log_index = LogIndex()
    return _log_index
