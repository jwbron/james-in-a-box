"""
Tests for Gateway Sidecar REST API.

Tests cover:
- Health check endpoint
- Authentication (valid/invalid tokens)
- Git push endpoint with policy enforcement
- gh PR endpoints (create, comment, edit, close)
- Blocked commands (merge)
- Generic gh execute endpoint
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest


# conftest.py sets up the module loading and TEST_SECRET
# Modules are loaded via importlib in conftest.py

# Import the test secret and modules (loaded by conftest.py)
TEST_SECRET = os.environ.get("JIB_GATEWAY_SECRET", "test-secret-token-12345")
import gateway
from policy import PolicyResult


@pytest.fixture
def client():
    """Create test client for Flask app."""
    gateway.app.config["TESTING"] = True
    with gateway.app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"Authorization": f"Bearer {TEST_SECRET}"}


class TestHealthCheck:
    """Tests for /api/v1/health endpoint."""

    def test_health_check_returns_status(self, client):
        """Health check returns status info without auth."""
        with patch.object(gateway, "get_github_client") as mock_gh:
            mock_gh.return_value.is_token_valid.return_value = True

            response = client.get("/api/v1/health")

            assert response.status_code == 200
            data = json.loads(response.data)
            assert "status" in data
            assert data["service"] == "gateway-sidecar"

    def test_health_check_no_auth_required(self, client):
        """Health check does not require authentication."""
        with patch.object(gateway, "get_github_client") as mock_gh:
            mock_gh.return_value.is_token_valid.return_value = True

            response = client.get("/api/v1/health")

            # Should succeed without auth headers
            assert response.status_code == 200

    def test_health_check_degraded_when_token_invalid(self, client):
        """Health check shows degraded when GitHub token invalid."""
        with patch.object(gateway, "get_github_client") as mock_gh:
            mock_gh.return_value.is_token_valid.return_value = False

            response = client.get("/api/v1/health")

            data = json.loads(response.data)
            assert data["status"] == "degraded"
            assert data["github_token_valid"] is False


class TestAuthentication:
    """Tests for authentication."""

    def test_missing_auth_header_returns_401(self, client):
        """Requests without auth header return 401."""
        response = client.post(
            "/api/v1/gh/pr/create",
            data=json.dumps({"repo": "test/repo", "title": "Test", "head": "branch"}),
            content_type="application/json",
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert data["success"] is False
        assert "Authorization" in data["message"]

    def test_invalid_auth_header_format_returns_401(self, client):
        """Requests with malformed auth header return 401."""
        response = client.post(
            "/api/v1/gh/pr/create",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
            data=json.dumps({"repo": "test/repo", "title": "Test", "head": "branch"}),
            content_type="application/json",
        )

        assert response.status_code == 401

    def test_wrong_token_returns_401(self, client):
        """Requests with wrong token return 401."""
        response = client.post(
            "/api/v1/gh/pr/create",
            headers={"Authorization": "Bearer wrong-token"},
            data=json.dumps({"repo": "test/repo", "title": "Test", "head": "branch"}),
            content_type="application/json",
        )

        assert response.status_code == 401
        data = json.loads(response.data)
        assert "Invalid" in data["message"]

    def test_valid_token_succeeds(self, client, auth_headers):
        """Requests with valid token pass authentication."""
        with patch.object(gateway, "get_github_client") as mock_gh:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.stdout = "https://github.com/test/repo/pull/1"
            mock_result.stderr = ""
            mock_gh.return_value.execute.return_value = mock_result

            response = client.post(
                "/api/v1/gh/pr/create",
                headers=auth_headers,
                data=json.dumps({"repo": "test/repo", "title": "Test PR", "head": "feature"}),
                content_type="application/json",
            )

            # Should not be 401 (may fail for other reasons)
            assert response.status_code != 401


class TestGitPush:
    """Tests for /api/v1/git/push endpoint."""

    def test_push_requires_repo_path(self, client, auth_headers):
        """Push requires repo_path parameter."""
        response = client.post(
            "/api/v1/git/push",
            headers=auth_headers,
            data=json.dumps({"remote": "origin"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "repo_path" in data["message"]

    def test_push_denied_by_policy(self, client, auth_headers):
        """Push denied when policy check fails."""
        with (
            patch("subprocess.run") as mock_run,
            patch.object(gateway, "get_policy_engine") as mock_policy,
        ):
            # Mock git remote get-url
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="https://github.com/owner/repo.git\n",
                stderr="",
            )

            # Mock policy denial
            mock_engine = MagicMock()
            mock_engine.check_branch_ownership.return_value = PolicyResult(
                allowed=False,
                reason="Branch 'main' is not owned by jib",
                details={"branch": "main"},
            )
            mock_policy.return_value = mock_engine

            response = client.post(
                "/api/v1/git/push",
                headers=auth_headers,
                data=json.dumps(
                    {
                        "repo_path": "/tmp/repo",
                        "remote": "origin",
                        "refspec": "main",
                    }
                ),
                content_type="application/json",
            )

            assert response.status_code == 403
            data = json.loads(response.data)
            assert "denied" in data["message"].lower()
            assert data["success"] is False

    def test_push_allowed_for_jib_branch(self, client, auth_headers):
        """Push allowed for jib-prefixed branch."""
        with (
            patch("subprocess.run") as mock_run,
            patch.object(gateway, "get_policy_engine") as mock_policy,
            patch.object(gateway, "get_github_client") as mock_gh,
        ):
            # Configure subprocess.run to return different values based on args
            def run_side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                result = MagicMock()
                result.returncode = 0
                result.stderr = ""

                if "remote" in cmd and "get-url" in cmd:
                    result.stdout = "https://github.com/owner/repo.git\n"
                elif "branch" in cmd and "--show-current" in cmd:
                    result.stdout = "jib-feature\n"
                elif "push" in cmd:
                    result.stdout = "Everything up-to-date\n"
                else:
                    result.stdout = ""
                return result

            mock_run.side_effect = run_side_effect

            # Mock policy approval
            mock_engine = MagicMock()
            mock_engine.check_branch_ownership.return_value = PolicyResult(
                allowed=True,
                reason="Branch is owned by jib",
                details={"branch": "jib-feature"},
            )
            mock_policy.return_value = mock_engine

            # Mock GitHub client
            mock_token = MagicMock()
            mock_token.token = "test-token"
            mock_gh.return_value.get_token.return_value = mock_token

            response = client.post(
                "/api/v1/git/push",
                headers=auth_headers,
                data=json.dumps(
                    {
                        "repo_path": "/tmp/repo",
                        "remote": "origin",
                        "refspec": "jib-feature",
                    }
                ),
                content_type="application/json",
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True


class TestGhPrCreate:
    """Tests for /api/v1/gh/pr/create endpoint."""

    def test_pr_create_requires_repo(self, client, auth_headers):
        """PR create requires repo parameter."""
        response = client.post(
            "/api/v1/gh/pr/create",
            headers=auth_headers,
            data=json.dumps({"title": "Test", "head": "branch"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "repo" in data["message"]

    def test_pr_create_requires_title(self, client, auth_headers):
        """PR create requires title parameter."""
        response = client.post(
            "/api/v1/gh/pr/create",
            headers=auth_headers,
            data=json.dumps({"repo": "test/repo", "head": "branch"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "title" in data["message"]

    def test_pr_create_requires_head(self, client, auth_headers):
        """PR create requires head parameter."""
        response = client.post(
            "/api/v1/gh/pr/create",
            headers=auth_headers,
            data=json.dumps({"repo": "test/repo", "title": "Test"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "head" in data["message"]

    def test_pr_create_success(self, client, auth_headers):
        """PR create succeeds with valid parameters."""
        with patch.object(gateway, "get_github_client") as mock_gh:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.stdout = "https://github.com/test/repo/pull/42"
            mock_result.stderr = ""
            mock_gh.return_value.execute.return_value = mock_result

            response = client.post(
                "/api/v1/gh/pr/create",
                headers=auth_headers,
                data=json.dumps(
                    {
                        "repo": "test/repo",
                        "title": "Add feature",
                        "body": "Description",
                        "base": "main",
                        "head": "feature-branch",
                    }
                ),
                content_type="application/json",
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            assert "pull/42" in data["data"]["stdout"]


class TestGhPrComment:
    """Tests for /api/v1/gh/pr/comment endpoint."""

    def test_pr_comment_requires_pr_number(self, client, auth_headers):
        """PR comment requires pr_number parameter."""
        response = client.post(
            "/api/v1/gh/pr/comment",
            headers=auth_headers,
            data=json.dumps({"repo": "test/repo", "body": "Comment"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "pr_number" in data["message"]

    def test_pr_comment_denied_when_not_owner(self, client, auth_headers):
        """PR comment denied when jib doesn't own the PR."""
        with patch.object(gateway, "get_policy_engine") as mock_policy:
            mock_engine = MagicMock()
            mock_engine.check_pr_ownership.return_value = PolicyResult(
                allowed=False,
                reason="PR #123 is not owned by jib",
                details={"author": "someone-else"},
            )
            mock_policy.return_value = mock_engine

            response = client.post(
                "/api/v1/gh/pr/comment",
                headers=auth_headers,
                data=json.dumps({"repo": "test/repo", "pr_number": 123, "body": "Comment"}),
                content_type="application/json",
            )

            assert response.status_code == 403
            data = json.loads(response.data)
            assert data["success"] is False
            assert "denied" in data["message"].lower()

    def test_pr_comment_allowed_when_owner(self, client, auth_headers):
        """PR comment allowed when jib owns the PR."""
        with (
            patch.object(gateway, "get_policy_engine") as mock_policy,
            patch.object(gateway, "get_github_client") as mock_gh,
        ):
            mock_engine = MagicMock()
            mock_engine.check_pr_ownership.return_value = PolicyResult(
                allowed=True,
                reason="PR is owned by jib",
                details={"author": "jib"},
            )
            mock_policy.return_value = mock_engine

            mock_result = MagicMock()
            mock_result.success = True
            mock_result.stdout = "Comment added"
            mock_result.stderr = ""
            mock_gh.return_value.execute.return_value = mock_result

            response = client.post(
                "/api/v1/gh/pr/comment",
                headers=auth_headers,
                data=json.dumps({"repo": "test/repo", "pr_number": 123, "body": "Thanks!"}),
                content_type="application/json",
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True


class TestGhPrEdit:
    """Tests for /api/v1/gh/pr/edit endpoint."""

    def test_pr_edit_requires_title_or_body(self, client, auth_headers):
        """PR edit requires either title or body."""
        response = client.post(
            "/api/v1/gh/pr/edit",
            headers=auth_headers,
            data=json.dumps({"repo": "test/repo", "pr_number": 123}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "title or body" in data["message"]

    def test_pr_edit_denied_when_not_owner(self, client, auth_headers):
        """PR edit denied when jib doesn't own the PR."""
        with patch.object(gateway, "get_policy_engine") as mock_policy:
            mock_engine = MagicMock()
            mock_engine.check_pr_ownership.return_value = PolicyResult(
                allowed=False,
                reason="PR #123 is not owned by jib",
                details={"author": "someone-else"},
            )
            mock_policy.return_value = mock_engine

            response = client.post(
                "/api/v1/gh/pr/edit",
                headers=auth_headers,
                data=json.dumps({"repo": "test/repo", "pr_number": 123, "title": "New title"}),
                content_type="application/json",
            )

            assert response.status_code == 403


class TestGhPrClose:
    """Tests for /api/v1/gh/pr/close endpoint."""

    def test_pr_close_requires_pr_number(self, client, auth_headers):
        """PR close requires pr_number parameter."""
        response = client.post(
            "/api/v1/gh/pr/close",
            headers=auth_headers,
            data=json.dumps({"repo": "test/repo"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "pr_number" in data["message"]

    def test_pr_close_denied_when_not_owner(self, client, auth_headers):
        """PR close denied when jib doesn't own the PR."""
        with patch.object(gateway, "get_policy_engine") as mock_policy:
            mock_engine = MagicMock()
            mock_engine.check_pr_ownership.return_value = PolicyResult(
                allowed=False,
                reason="PR #123 is not owned by jib",
                details={"author": "someone-else"},
            )
            mock_policy.return_value = mock_engine

            response = client.post(
                "/api/v1/gh/pr/close",
                headers=auth_headers,
                data=json.dumps({"repo": "test/repo", "pr_number": 123}),
                content_type="application/json",
            )

            assert response.status_code == 403


class TestGhExecute:
    """Tests for /api/v1/gh/execute endpoint."""

    def test_execute_requires_args(self, client, auth_headers):
        """Execute requires args parameter."""
        response = client.post(
            "/api/v1/gh/execute",
            headers=auth_headers,
            data=json.dumps({}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        # Empty dict means missing request body or missing args
        assert "Missing" in data["message"]

    def test_execute_blocks_merge(self, client, auth_headers):
        """Execute blocks pr merge command."""
        response = client.post(
            "/api/v1/gh/execute",
            headers=auth_headers,
            data=json.dumps({"args": ["pr", "merge", "123"]}),
            content_type="application/json",
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert "not allowed" in data["message"].lower()

    def test_execute_blocks_repo_delete(self, client, auth_headers):
        """Execute blocks repo delete command."""
        response = client.post(
            "/api/v1/gh/execute",
            headers=auth_headers,
            data=json.dumps({"args": ["repo", "delete", "test/repo"]}),
            content_type="application/json",
        )

        assert response.status_code == 403

    def test_execute_allows_read_operations(self, client, auth_headers):
        """Execute allows read-only operations."""
        with patch.object(gateway, "get_github_client") as mock_gh:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.stdout = "PR #1: Feature"
            mock_result.stderr = ""
            mock_result.to_dict.return_value = {
                "success": True,
                "stdout": "PR #1: Feature",
                "stderr": "",
            }
            mock_gh.return_value.execute.return_value = mock_result

            response = client.post(
                "/api/v1/gh/execute",
                headers=auth_headers,
                data=json.dumps({"args": ["pr", "list"]}),
                content_type="application/json",
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True


class TestGitFetch:
    """Tests for /api/v1/git/fetch endpoint."""

    def test_fetch_requires_repo_path(self, client, auth_headers):
        """Fetch requires repo_path parameter."""
        response = client.post(
            "/api/v1/git/fetch",
            headers=auth_headers,
            data=json.dumps({"remote": "origin"}),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "repo_path" in data["message"]

    def test_fetch_path_traversal_blocked(self, client, auth_headers):
        """Fetch blocked for path traversal attempts."""
        response = client.post(
            "/api/v1/git/fetch",
            headers=auth_headers,
            data=json.dumps(
                {
                    "repo_path": "/home/jib/repos/../../../etc/passwd",
                    "remote": "origin",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data["success"] is False

    def test_fetch_invalid_args_rejected(self, client, auth_headers):
        """Fetch rejects invalid arguments."""
        response = client.post(
            "/api/v1/git/fetch",
            headers=auth_headers,
            data=json.dumps(
                {
                    "repo_path": "/home/jib/repos/test",
                    "remote": "origin",
                    "args": ["--upload-pack=/bin/evil"],
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "not allowed" in data["message"]

    def test_fetch_success(self, client, auth_headers):
        """Fetch succeeds with valid parameters."""
        with (
            patch("subprocess.run") as mock_run,
            patch.object(gateway, "get_github_client") as mock_gh,
        ):
            # Configure subprocess.run to return different values based on args
            def run_side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                result = MagicMock()
                result.returncode = 0
                result.stderr = ""

                if "remote" in cmd and "get-url" in cmd:
                    result.stdout = "https://github.com/owner/repo.git\n"
                elif "fetch" in cmd:
                    result.stdout = ""
                else:
                    result.stdout = ""
                return result

            mock_run.side_effect = run_side_effect

            # Mock GitHub client for token
            mock_token = MagicMock()
            mock_token.token = "test-token"
            mock_gh.return_value.get_token.return_value = mock_token
            mock_gh.return_value.get_incognito_token.return_value = None

            response = client.post(
                "/api/v1/git/fetch",
                headers=auth_headers,
                data=json.dumps(
                    {
                        "repo_path": "/home/jib/repos/test",
                        "remote": "origin",
                    }
                ),
                content_type="application/json",
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True

    def test_ls_remote_success(self, client, auth_headers):
        """ls-remote succeeds with valid parameters."""
        with (
            patch("subprocess.run") as mock_run,
            patch.object(gateway, "get_github_client") as mock_gh,
        ):
            # Configure subprocess.run
            def run_side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                result = MagicMock()
                result.returncode = 0
                result.stderr = ""

                if "remote" in cmd and "get-url" in cmd:
                    result.stdout = "https://github.com/owner/repo.git\n"
                elif "ls-remote" in cmd:
                    result.stdout = "abc123\trefs/heads/main\n"
                else:
                    result.stdout = ""
                return result

            mock_run.side_effect = run_side_effect

            # Mock GitHub client for token
            mock_token = MagicMock()
            mock_token.token = "test-token"
            mock_gh.return_value.get_token.return_value = mock_token
            mock_gh.return_value.get_incognito_token.return_value = None

            response = client.post(
                "/api/v1/git/fetch",
                headers=auth_headers,
                data=json.dumps(
                    {
                        "repo_path": "/home/jib/repos/test",
                        "operation": "ls-remote",
                        "remote": "origin",
                    }
                ),
                content_type="application/json",
            )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["success"] is True
            assert "refs/heads/main" in data["data"]["stdout"]

    def test_fetch_unsupported_operation_rejected(self, client, auth_headers):
        """Unsupported operations are rejected."""
        response = client.post(
            "/api/v1/git/fetch",
            headers=auth_headers,
            data=json.dumps(
                {
                    "repo_path": "/home/jib/repos/test",
                    "operation": "clone",
                    "remote": "origin",
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Unsupported" in data["message"]


class TestBlockedCommands:
    """Tests for blocked commands."""

    @pytest.mark.parametrize(
        "args",
        [
            ["pr", "merge", "123"],
            ["repo", "delete", "test/repo"],
            ["repo", "archive", "test/repo"],
            ["release", "delete", "v1.0"],
            ["auth", "logout"],
            ["auth", "login"],
            ["config", "set", "key", "value"],
        ],
    )
    def test_blocked_commands_return_403(self, client, auth_headers, args):
        """Blocked commands return 403 Forbidden."""
        response = client.post(
            "/api/v1/gh/execute",
            headers=auth_headers,
            data=json.dumps({"args": args}),
            content_type="application/json",
        )

        assert response.status_code == 403
        data = json.loads(response.data)
        assert data["success"] is False
        assert "not allowed" in data["message"].lower()
