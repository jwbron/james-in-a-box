"""Tests for log access endpoints.

Tests the log access policy enforcement, log reading functionality,
and all log-related gateway endpoints.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import from conftest which handles the module loading
from conftest import TEST_SECRET, gateway, log_index, log_policy, log_reader


# Test fixtures
@pytest.fixture
def client():
    """Create a test client for the gateway."""
    gateway.app.config["TESTING"] = True
    with gateway.app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers():
    """Create authentication headers for requests."""
    return {
        "Authorization": f"Bearer {TEST_SECRET}",
        "X-Container-ID": "test-container-123",
        "X-Task-ID": "task-20260128-123456",
    }


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_log_index(temp_log_dir):
    """Create a mock log index file."""
    index_data = {
        "task_to_container": {
            "task-20260128-123456": "test-container-123",
            "task-20260128-other": "other-container-456",
        },
        "thread_to_task": {
            "1234567890.123456": "task-20260128-123456",
        },
        "entries": [
            {
                "container_id": "test-container-123",
                "task_id": "task-20260128-123456",
                "thread_ts": "1234567890.123456",
                "log_file": str(temp_log_dir / "test-container-123.log"),
                "timestamp": "2026-01-28T12:00:00Z",
            },
            {
                "container_id": "other-container-456",
                "task_id": "task-20260128-other",
                "log_file": str(temp_log_dir / "other-container-456.log"),
                "timestamp": "2026-01-28T11:00:00Z",
            },
        ],
    }

    index_path = temp_log_dir / "log-index.json"
    with open(index_path, "w") as f:
        json.dump(index_data, f)

    # Create test log files
    test_log = temp_log_dir / "test-container-123.log"
    test_log.write_text("Line 1: Test log entry\nLine 2: Another entry\nLine 3: Error found\n")

    other_log = temp_log_dir / "other-container-456.log"
    other_log.write_text("Line 1: Other container log\n")

    return index_path


class TestLogPolicy:
    """Tests for log access policy enforcement."""

    def test_task_access_allowed_for_owner(self, temp_log_dir, mock_log_index):
        """Owner can access their own task's logs."""
        # Create a fresh LogIndex with custom path
        custom_index = log_index.LogIndex(index_path=mock_log_index)

        # Create policy with mocked index
        policy = log_policy.LogPolicy()
        policy._log_index = custom_index

        result = policy.check_task_access(
            requester_container_id="test-container-123",
            requester_task_id="task-20260128-123456",
            target_task_id="task-20260128-123456",
        )

        assert result.allowed is True
        assert "Owner access" in result.reason

    def test_task_access_denied_for_non_owner(self, temp_log_dir, mock_log_index):
        """Non-owner cannot access other's task logs."""
        # Create a fresh LogIndex with custom path
        custom_index = log_index.LogIndex(index_path=mock_log_index)

        # Create policy with mocked index
        policy = log_policy.LogPolicy()
        policy._log_index = custom_index

        result = policy.check_task_access(
            requester_container_id="test-container-123",
            requester_task_id="task-20260128-123456",
            target_task_id="task-20260128-other",  # Different task owned by other-container-456
        )

        assert result.allowed is False
        assert "denied" in result.reason.lower()

    def test_task_access_denied_for_unknown_task(self, temp_log_dir, mock_log_index):
        """Cannot access task that doesn't exist in index."""
        # Create a fresh LogIndex with custom path
        custom_index = log_index.LogIndex(index_path=mock_log_index)

        # Create policy with mocked index
        policy = log_policy.LogPolicy()
        policy._log_index = custom_index

        result = policy.check_task_access(
            requester_container_id="test-container-123",
            requester_task_id=None,
            target_task_id="task-nonexistent",
        )

        assert result.allowed is False
        assert "not found" in result.reason.lower()

    def test_container_access_self_only(self):
        """Container can only access its own logs."""
        log_policy._log_policy = None
        policy = log_policy.get_log_policy()

        # Self-access allowed
        result = policy.check_container_access(
            requester_container_id="container-123",
            target_container_id="container-123",
        )
        assert result.allowed is True

        # Cross-container denied
        result = policy.check_container_access(
            requester_container_id="container-123",
            target_container_id="container-456",
        )
        assert result.allowed is False

    def test_search_scope_enforced(self):
        """Search is scoped to requester's logs only."""
        log_policy._log_policy = None
        policy = log_policy.get_log_policy()

        # 'self' scope allowed
        result = policy.check_search_access(
            requester_container_id="container-123",
            scope="self",
        )
        assert result.allowed is True

        # Other scopes denied
        result = policy.check_search_access(
            requester_container_id="container-123",
            scope="all",
        )
        assert result.allowed is False


class TestLogIndex:
    """Tests for log index reading."""

    def test_get_container_for_task(self, temp_log_dir, mock_log_index):
        """Correctly look up container for a task."""
        idx = log_index.LogIndex(index_path=mock_log_index)

        container = idx.get_container_for_task("task-20260128-123456")
        assert container == "test-container-123"

        container = idx.get_container_for_task("nonexistent")
        assert container is None

    def test_list_entries_filtered(self, temp_log_dir, mock_log_index):
        """List entries filtered by container."""
        idx = log_index.LogIndex(index_path=mock_log_index)

        entries = idx.list_entries(container_id="test-container-123")
        assert len(entries) == 1
        assert entries[0].container_id == "test-container-123"

    def test_index_caching(self, temp_log_dir, mock_log_index):
        """Index is cached until file changes."""
        idx = log_index.LogIndex(index_path=mock_log_index)

        # First load
        idx.get_container_for_task("task-20260128-123456")

        # Second load should use cache
        assert idx._cache is not None

    def test_missing_index_returns_empty(self, temp_log_dir):
        """Missing index returns empty data."""
        idx = log_index.LogIndex(index_path=temp_log_dir / "nonexistent.json")

        assert idx.get_container_for_task("any-task") is None
        assert len(idx.list_entries()) == 0


class TestLogReader:
    """Tests for log file reading."""

    def test_read_container_logs(self, temp_log_dir, mock_log_index):
        """Read logs for a container."""
        with patch.object(log_reader, "DEFAULT_CONTAINER_LOGS_DIR", temp_log_dir):
            content = log_reader.read_container_logs("test-container-123")

            assert content is not None
            assert content.lines == 3
            assert "Test log entry" in content.content

    def test_read_logs_with_line_limit(self, temp_log_dir, mock_log_index):
        """Read logs with line limit."""
        with patch.object(log_reader, "DEFAULT_CONTAINER_LOGS_DIR", temp_log_dir):
            content = log_reader.read_container_logs("test-container-123", max_lines=2)

            assert content is not None
            assert content.lines == 2
            assert content.truncated is True

    def test_read_nonexistent_logs(self, temp_log_dir):
        """Reading nonexistent logs returns None."""
        with patch.object(log_reader, "DEFAULT_CONTAINER_LOGS_DIR", temp_log_dir):
            content = log_reader.read_container_logs("nonexistent")
            assert content is None

    def test_pattern_validation(self):
        """Pattern validation catches dangerous patterns."""
        # Long pattern rejected
        with pytest.raises(log_reader.PatternValidationError):
            log_reader.validate_search_pattern("a" * 600)

        # Too many groups rejected
        with pytest.raises(log_reader.PatternValidationError):
            log_reader.validate_search_pattern("(" * 15)

        # Normal patterns accepted
        log_reader.validate_search_pattern("error")
        log_reader.validate_search_pattern("error|warning")


class TestLogEndpoints:
    """Tests for log API endpoints."""

    def test_logs_list_requires_auth(self, client):
        """List endpoint requires authentication."""
        response = client.get("/api/v1/logs/list")
        assert response.status_code == 401

    def test_logs_list_requires_container_id(self, client, auth_headers):
        """List endpoint requires X-Container-ID header."""
        headers = dict(auth_headers)
        del headers["X-Container-ID"]

        response = client.get("/api/v1/logs/list", headers=headers)
        assert response.status_code == 400

    def test_logs_list_returns_entries(self, client, auth_headers, temp_log_dir, mock_log_index):
        """List returns log entries for requester's container."""
        # Create custom index and patch the gateway's singleton
        custom_index = log_index.LogIndex(index_path=mock_log_index)
        with patch.object(gateway, "get_log_index", return_value=custom_index):
            response = client.get("/api/v1/logs/list", headers=auth_headers)
            assert response.status_code == 200

            data = response.get_json()
            assert data["success"] is True
            assert "entries" in data["data"]

    def test_logs_task_policy_enforcement(self, client, auth_headers, temp_log_dir, mock_log_index):
        """Task endpoint enforces ownership policy."""
        # Create custom index and policy
        custom_index = log_index.LogIndex(index_path=mock_log_index)
        custom_policy = log_policy.LogPolicy()
        custom_policy._log_index = custom_index

        with patch.object(gateway, "get_log_policy", return_value=custom_policy):
            with patch.object(gateway, "get_log_index", return_value=custom_index):
                # Own task - should succeed (but may 404 if file not found)
                response = client.get(
                    "/api/v1/logs/task/task-20260128-123456",
                    headers=auth_headers,
                )
                # Either 200 (found) or 404 (not found), but not 403
                assert response.status_code in (200, 404)

                # Other's task - should be denied
                response = client.get(
                    "/api/v1/logs/task/task-20260128-other",
                    headers=auth_headers,
                )
                assert response.status_code == 403

    def test_logs_container_self_access_only(
        self, client, auth_headers, temp_log_dir, mock_log_index
    ):
        """Container endpoint allows self-access only."""
        with patch.object(gateway, "DEFAULT_CONTAINER_LOGS_DIR", temp_log_dir, create=True):
            with patch.object(log_reader, "DEFAULT_CONTAINER_LOGS_DIR", temp_log_dir):
                # Self-access - should succeed
                response = client.get(
                    "/api/v1/logs/container/test-container-123",
                    headers=auth_headers,
                )
                assert response.status_code == 200

                # Other container - should be denied
                response = client.get(
                    "/api/v1/logs/container/other-container-456",
                    headers=auth_headers,
                )
                assert response.status_code == 403

    def test_logs_search_requires_pattern(self, client, auth_headers):
        """Search endpoint requires pattern parameter."""
        response = client.get("/api/v1/logs/search", headers=auth_headers)
        assert response.status_code == 400

    def test_logs_search_invalid_scope(self, client, auth_headers):
        """Search endpoint rejects invalid scope."""
        response = client.get(
            "/api/v1/logs/search?pattern=error&scope=all",
            headers=auth_headers,
        )
        assert response.status_code == 403

    def test_logs_model_policy_enforcement(
        self, client, auth_headers, temp_log_dir, mock_log_index
    ):
        """Model endpoint enforces ownership policy."""
        # Create custom index and policy
        custom_index = log_index.LogIndex(index_path=mock_log_index)
        custom_policy = log_policy.LogPolicy()
        custom_policy._log_index = custom_index

        with patch.object(gateway, "get_log_policy", return_value=custom_policy):
            # Other's task - should be denied
            response = client.get(
                "/api/v1/logs/model/task-20260128-other",
                headers=auth_headers,
            )
            assert response.status_code == 403


class TestAuditLogging:
    """Tests for audit logging of log access."""

    def test_successful_access_logged(self, client, auth_headers, temp_log_dir, mock_log_index):
        """Successful log access is audited."""
        with patch.object(log_reader, "DEFAULT_CONTAINER_LOGS_DIR", temp_log_dir):
            with patch.object(gateway, "audit_log") as mock_audit:
                response = client.get(
                    "/api/v1/logs/container/test-container-123",
                    headers=auth_headers,
                )
                assert response.status_code == 200

                # Check audit_log was called with success=True
                calls = [c for c in mock_audit.call_args_list if c.kwargs.get("success")]
                assert len(calls) > 0

    def test_denied_access_logged(self, client, auth_headers, temp_log_dir, mock_log_index):
        """Denied log access is audited."""
        # Create custom index and policy
        custom_index = log_index.LogIndex(index_path=mock_log_index)
        custom_policy = log_policy.LogPolicy()
        custom_policy._log_index = custom_index

        with patch.object(gateway, "get_log_policy", return_value=custom_policy):
            with patch.object(gateway, "audit_log") as mock_audit:
                response = client.get(
                    "/api/v1/logs/task/task-20260128-other",
                    headers=auth_headers,
                )
                assert response.status_code == 403

                # Check audit_log was called with success=False
                calls = [c for c in mock_audit.call_args_list if not c.kwargs.get("success", True)]
                assert len(calls) > 0
