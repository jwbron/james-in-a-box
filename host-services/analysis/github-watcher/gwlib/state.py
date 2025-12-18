#!/usr/bin/env python3
"""State management for GitHub watcher services."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from jib_logging import get_logger


logger = get_logger("github-state")

STATE_DIR = Path.home() / ".local" / "share" / "github-watcher"
STATE_FILE = STATE_DIR / "state.json"


def utc_now_iso() -> str:
    """Get current UTC time in ISO format with Z suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state() -> dict:
    """Load previous notification state to avoid duplicate processing.

    Returns:
        State dict with all expected keys initialized
    """
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open() as f:
                state = json.load(f)
                # Ensure all expected keys exist
                state.setdefault("processed_failures", {})
                state.setdefault("processed_comments", {})
                state.setdefault("processed_reviews", {})
                state.setdefault("processed_conflicts", {})
                state.setdefault("processed_review_responses", {})
                state.setdefault("failed_tasks", {})
                state.setdefault("last_run_start", None)
                return state
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to load state file", error=str(e))

    return {
        "processed_failures": {},
        "processed_comments": {},
        "processed_reviews": {},
        "processed_conflicts": {},
        "processed_review_responses": {},
        "failed_tasks": {},
        "last_run_start": None,
    }


def save_state(state: dict, update_last_run: bool = False) -> None:
    """Save notification state.

    Args:
        state: The state dict to save
        update_last_run: If True, update last_run_start to current time
    """
    if update_last_run:
        state["last_run_start"] = utc_now_iso()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with STATE_FILE.open("w") as f:
        json.dump(state, f, indent=2)


class ThreadSafeState:
    """Thread-safe wrapper for state management.

    Example:
        >>> state = load_state()
        >>> safe_state = ThreadSafeState(state)
        >>> safe_state.mark_processed("processed_comments", "repo-123:abc")
        >>> safe_state.mark_failed("repo-123:abc", "comment", {"repository": "owner/repo"})
    """

    def __init__(self, state: dict):
        self._state = state
        self._lock = threading.Lock()

    def mark_processed(self, key: str, signature: str) -> None:
        """Mark a task as processed (thread-safe)."""
        with self._lock:
            self._state.setdefault(key, {})[signature] = utc_now_iso()
            # Remove from failed_tasks if this was a retry
            if signature in self._state.get("failed_tasks", {}):
                del self._state["failed_tasks"][signature]
            self._save()

    def mark_failed(self, signature: str, task_type: str, context: dict) -> None:
        """Mark a task as failed for later retry (thread-safe)."""
        with self._lock:
            self._state.setdefault("failed_tasks", {})[signature] = {
                "failed_at": utc_now_iso(),
                "task_type": task_type,
                "repository": context.get("repository", "unknown"),
                "pr_number": context.get("pr_number"),
            }
            self._save()

    def is_processed(self, key: str, signature: str) -> bool:
        """Check if a signature has been processed (thread-safe)."""
        with self._lock:
            return signature in self._state.get(key, {})

    def get_state(self) -> dict:
        """Get a copy of current state."""
        with self._lock:
            return self._state.copy()

    def _save(self) -> None:
        """Save state to disk (must be called with lock held)."""
        self._state["last_run_start"] = utc_now_iso()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w") as f:
            json.dump(self._state, f, indent=2)
