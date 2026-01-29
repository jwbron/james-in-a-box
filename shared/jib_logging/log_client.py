"""Log client for gateway-mediated log access.

Use this client from within containers to access logs via the gateway API.
Direct filesystem access to logs is not available in containers.

Usage:
    from jib_logging import LogClient

    client = LogClient()
    logs = client.get_task_logs("task-20260128-123456")
    print(logs.content)

    results = client.search("error", limit=10)
    for entry in results:
        print(f"{entry.line_number}: {entry.content}")

    # List recent log entries
    entries = client.list_logs(limit=20)
    for e in entries:
        print(f"{e.timestamp}: {e.task_id}")
"""

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class LogContent:
    """Log content returned from gateway."""

    task_id: str | None
    container_id: str | None
    log_file: str | None
    content: str
    lines: int
    truncated: bool


@dataclass
class LogEntry:
    """A log entry from the list endpoint."""

    container_id: str
    task_id: str | None
    thread_ts: str | None
    log_file: str | None
    timestamp: str


@dataclass
class SearchResult:
    """A single search result."""

    log_file: str
    line_number: int
    content: str
    task_id: str | None
    container_id: str | None


class LogClientError(Exception):
    """Error from log client operations."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class LogClient:
    """Client for accessing logs via gateway API.

    Automatically reads configuration from environment variables:
    - GATEWAY_URL: Gateway base URL (default: http://jib-gateway:9847)
    - JIB_GATEWAY_SECRET: Authentication secret
    - JIB_CONTAINER_ID: Current container ID (set by orchestrator)
    - JIB_TASK_ID: Current task ID (if applicable)
    """

    def __init__(
        self,
        gateway_url: str | None = None,
        auth_secret: str | None = None,
        container_id: str | None = None,
        task_id: str | None = None,
    ):
        """Initialize the LogClient.

        Args:
            gateway_url: Gateway base URL. Defaults to GATEWAY_URL env var
                or http://jib-gateway:9847.
            auth_secret: Authentication secret. Defaults to JIB_GATEWAY_SECRET env var.
            container_id: Container ID. Defaults to JIB_CONTAINER_ID or CONTAINER_ID env var.
            task_id: Task ID. Defaults to JIB_TASK_ID env var.

        Raises:
            LogClientError: If required configuration is missing.
        """
        self.gateway_url = gateway_url or os.environ.get("GATEWAY_URL") or "http://jib-gateway:9847"
        self.auth_secret = auth_secret or os.environ.get("JIB_GATEWAY_SECRET", "")
        self.container_id = (
            container_id or os.environ.get("JIB_CONTAINER_ID") or os.environ.get("CONTAINER_ID", "")
        )
        self.task_id = task_id or os.environ.get("JIB_TASK_ID")

        if not self.auth_secret:
            raise LogClientError("JIB_GATEWAY_SECRET not set")
        if not self.container_id:
            raise LogClientError("JIB_CONTAINER_ID or CONTAINER_ID not set")

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make authenticated request to gateway.

        Args:
            endpoint: API endpoint path (e.g., /api/v1/logs/list)
            params: Query parameters

        Returns:
            Parsed JSON response

        Raises:
            LogClientError: On HTTP or connection errors
        """
        url = f"{self.gateway_url}{endpoint}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
            url = f"{url}?{query}"

        headers = {
            "Authorization": f"Bearer {self.auth_secret}",
            "X-Container-ID": self.container_id,
            "Content-Type": "application/json",
        }
        if self.task_id:
            headers["X-Task-ID"] = self.task_id

        request = Request(url, headers=headers, method="GET")

        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode())
                return data
        except HTTPError as e:
            body = e.read().decode()
            try:
                error_data = json.loads(body)
                raise LogClientError(
                    error_data.get("message", str(e)),
                    status_code=e.code,
                    details=error_data.get("details"),
                )
            except json.JSONDecodeError:
                raise LogClientError(str(e), status_code=e.code)
        except URLError as e:
            raise LogClientError(f"Connection error: {e}")

    def list_logs(self, limit: int = 50, offset: int = 0) -> list[LogEntry]:
        """List recent log entries for this container.

        Args:
            limit: Maximum entries to return (default 50, max 100)
            offset: Offset for pagination (default 0)

        Returns:
            List of LogEntry objects
        """
        response = self._make_request(
            "/api/v1/logs/list",
            params={"limit": limit, "offset": offset},
        )
        return [
            LogEntry(
                container_id=e["container_id"],
                task_id=e.get("task_id"),
                thread_ts=e.get("thread_ts"),
                log_file=e.get("log_file"),
                timestamp=e["timestamp"],
            )
            for e in response.get("data", {}).get("entries", [])
        ]

    def get_task_logs(self, task_id: str, max_lines: int = 1000) -> LogContent:
        """Get logs for a specific task.

        Args:
            task_id: The task ID to get logs for
            max_lines: Maximum lines to return (default 1000, max 10000)

        Returns:
            LogContent object with the log data

        Raises:
            LogClientError: If task not found or access denied
        """
        response = self._make_request(
            f"/api/v1/logs/task/{task_id}",
            params={"lines": max_lines},
        )
        data = response.get("data", {})
        return LogContent(
            task_id=data.get("task_id"),
            container_id=data.get("container_id"),
            log_file=data.get("log_file"),
            content=data.get("content", ""),
            lines=data.get("lines", 0),
            truncated=data.get("truncated", False),
        )

    def get_container_logs(self, max_lines: int = 1000) -> LogContent:
        """Get logs for this container.

        Args:
            max_lines: Maximum lines to return (default 1000, max 10000)

        Returns:
            LogContent object with the log data
        """
        response = self._make_request(
            f"/api/v1/logs/container/{self.container_id}",
            params={"lines": max_lines},
        )
        data = response.get("data", {})
        return LogContent(
            task_id=data.get("task_id"),
            container_id=data.get("container_id"),
            log_file=data.get("log_file"),
            content=data.get("content", ""),
            lines=data.get("lines", 0),
            truncated=data.get("truncated", False),
        )

    def search(self, pattern: str, limit: int = 100) -> list[SearchResult]:
        """Search logs for a pattern.

        Args:
            pattern: Regex pattern to search for
            limit: Maximum results to return (default 100, max 1000)

        Returns:
            List of SearchResult objects
        """
        response = self._make_request(
            "/api/v1/logs/search",
            params={"pattern": pattern, "limit": limit, "scope": "self"},
        )
        return [
            SearchResult(
                log_file=r["log_file"],
                line_number=r["line_number"],
                content=r["content"],
                task_id=r.get("task_id"),
                container_id=r.get("container_id"),
            )
            for r in response.get("data", {}).get("results", [])
        ]

    def get_model_output(self, task_id: str) -> LogContent:
        """Get model output for a specific task.

        Args:
            task_id: The task ID to get model output for

        Returns:
            LogContent object with the model output

        Raises:
            LogClientError: If task not found or access denied
        """
        response = self._make_request(f"/api/v1/logs/model/{task_id}")
        data = response.get("data", {})
        return LogContent(
            task_id=data.get("task_id"),
            container_id=data.get("container_id"),
            log_file=data.get("log_file"),
            content=data.get("content", ""),
            lines=data.get("lines", 0),
            truncated=data.get("truncated", False),
        )


def is_in_container() -> bool:
    """Detect if running inside a jib container.

    Uses a three-tier detection strategy:
    1. Check for JIB_CONTAINER environment variable (primary)
    2. Check for absence of ~/.jib-sharing/ (filesystem isolation)
    3. Check for /.dockerenv (fallback)

    Returns:
        True if running inside a container, False otherwise
    """
    # Primary: Check for JIB_CONTAINER environment variable
    if os.environ.get("JIB_CONTAINER") == "1":
        return True

    # Secondary: Check for absence of ~/.jib-sharing/
    # In container, this directory is not mounted
    from pathlib import Path

    sharing_dir = Path.home() / ".jib-sharing"
    if not sharing_dir.exists():
        return True

    # Tertiary: Check for /.dockerenv
    return bool(Path("/.dockerenv").exists())
