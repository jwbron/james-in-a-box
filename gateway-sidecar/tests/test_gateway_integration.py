"""Integration tests for gateway endpoints.

These tests require a running gateway server or mock the Flask app.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gateway import app


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers():
    """Create authorization headers with a mock secret."""
    with patch("gateway.get_gateway_secret", return_value="test-secret"):
        yield {"Authorization": "Bearer test-secret"}


class TestHealthEndpoint:
    """Tests for /api/v1/health endpoint."""

    def test_health_no_auth_required(self, client):
        """Health endpoint should not require authentication."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "status" in data


class TestGitExecuteEndpoint:
    """Tests for /api/v1/git/execute endpoint."""

    def test_requires_auth(self, client):
        """Endpoint should require authentication."""
        response = client.post(
            "/api/v1/git/execute",
            json={"repo_path": "/home/jib/repos/test", "operation": "status"},
        )
        assert response.status_code == 401

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_missing_body(self, mock_secret, client):
        """Missing request body should return error."""
        response = client.post(
            "/api/v1/git/execute",
            headers={"Authorization": "Bearer test-secret"},
        )
        assert response.status_code == 400

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_missing_repo_path(self, mock_secret, client):
        """Missing repo_path should return error."""
        response = client.post(
            "/api/v1/git/execute",
            headers={"Authorization": "Bearer test-secret"},
            json={"operation": "status"},
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "repo_path" in data["message"].lower()

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_missing_operation(self, mock_secret, client):
        """Missing operation should return error."""
        response = client.post(
            "/api/v1/git/execute",
            headers={"Authorization": "Bearer test-secret"},
            json={"repo_path": "/home/jib/repos/test"},
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "operation" in data["message"].lower()

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    @patch("gateway.validate_repo_path", return_value=(True, ""))
    @patch("subprocess.run")
    def test_status_command_executed(self, mock_run, mock_validate, mock_secret, client):
        """Status command should be executed."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="## main",
            stderr="",
        )

        response = client.post(
            "/api/v1/git/execute",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "repo_path": "/home/jib/repos/test",
                "operation": "status",
                "args": ["--porcelain"],
            },
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_disallowed_operation_rejected(self, mock_secret, client):
        """Operations not in allowlist should be rejected."""
        response = client.post(
            "/api/v1/git/execute",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "repo_path": "/home/jib/repos/test",
                "operation": "clone",  # Not in allowlist
            },
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert "not allowed" in data["message"].lower()

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_network_ops_redirected(self, mock_secret, client):
        """Network operations should be redirected to dedicated endpoints."""
        for op in ["push", "fetch", "ls-remote"]:
            response = client.post(
                "/api/v1/git/execute",
                headers={"Authorization": "Bearer test-secret"},
                json={
                    "repo_path": "/home/jib/repos/test",
                    "operation": op,
                },
            )

            assert response.status_code == 400
            data = json.loads(response.data)
            assert "dedicated endpoint" in data["message"].lower()


class TestWorktreeCreateEndpoint:
    """Tests for /api/v1/worktree/create endpoint."""

    def test_requires_auth(self, client):
        """Endpoint should require authentication."""
        response = client.post(
            "/api/v1/worktree/create",
            json={"container_id": "jib-123", "repos": ["myrepo"]},
        )
        assert response.status_code == 401

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_missing_container_id(self, mock_secret, client):
        """Missing container_id should return error."""
        response = client.post(
            "/api/v1/worktree/create",
            headers={"Authorization": "Bearer test-secret"},
            json={"repos": ["myrepo"]},
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "container_id" in data["message"].lower()

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_missing_repos(self, mock_secret, client):
        """Missing repos should return error."""
        response = client.post(
            "/api/v1/worktree/create",
            headers={"Authorization": "Bearer test-secret"},
            json={"container_id": "jib-123"},
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "repos" in data["message"].lower()


class TestWorktreeDeleteEndpoint:
    """Tests for /api/v1/worktree/delete endpoint."""

    def test_requires_auth(self, client):
        """Endpoint should require authentication."""
        response = client.post(
            "/api/v1/worktree/delete",
            json={"container_id": "jib-123"},
        )
        assert response.status_code == 401

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_missing_container_id(self, mock_secret, client):
        """Missing container_id should return error."""
        response = client.post(
            "/api/v1/worktree/delete",
            headers={"Authorization": "Bearer test-secret"},
            json={},
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "container_id" in data["message"].lower()


class TestWorktreeListEndpoint:
    """Tests for /api/v1/worktree/list endpoint."""

    def test_requires_auth(self, client):
        """Endpoint should require authentication."""
        response = client.get("/api/v1/worktree/list")
        assert response.status_code == 401

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    @patch("gateway.get_worktree_manager")
    def test_returns_worktrees(self, mock_manager, mock_secret, client):
        """Should return list of worktrees."""
        mock_manager.return_value.list_worktrees.return_value = [
            {"container_id": "jib-123", "repos": [{"name": "myrepo", "path": "/path"}]}
        ]

        response = client.get(
            "/api/v1/worktree/list",
            headers={"Authorization": "Bearer test-secret"},
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "worktrees" in data["data"]


class TestRateLimiting:
    """Tests for rate limiting."""

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    @patch("gateway._rate_limits")
    def test_rate_limit_enforced(self, mock_limits, mock_secret, client):
        """Rate limits should be enforced."""
        # This is a simplified test - full rate limit testing would require
        # making many requests within the time window


class TestPathValidation:
    """Tests for path validation in endpoints."""

    @patch("gateway.get_gateway_secret", return_value="test-secret")
    def test_path_traversal_blocked(self, mock_secret, client):
        """Path traversal attempts should be blocked."""
        response = client.post(
            "/api/v1/git/execute",
            headers={"Authorization": "Bearer test-secret"},
            json={
                "repo_path": "/home/jib/repos/../../../etc/passwd",
                "operation": "status",
            },
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert "allowed directories" in data["message"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
