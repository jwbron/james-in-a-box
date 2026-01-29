"""
Tests for private_repo_policy module.

Tests the binary repo visibility mode:
- PRIVATE_REPO_MODE=true: Only private/internal repos accessible
- PRIVATE_REPO_MODE=false (default): Only public repos accessible
"""

import os
from unittest.mock import patch

# Import from conftest-loaded module
from private_repo_policy import (
    PRIVATE_REPO_MODE_VAR,
    PrivateRepoPolicy,
    PrivateRepoPolicyResult,
    check_private_repo_access,
    get_private_repo_policy,
    is_private_repo_mode_enabled,
)


class TestPrivateRepoPolicyResult:
    """Tests for PrivateRepoPolicyResult dataclass."""

    def test_to_dict_allowed(self):
        result = PrivateRepoPolicyResult(
            allowed=True,
            reason="Test reason",
            visibility="private",
        )
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["reason"] == "Test reason"
        assert d["visibility"] == "private"
        assert d["policy"] == "private_repo_mode"

    def test_to_dict_denied(self):
        result = PrivateRepoPolicyResult(
            allowed=False,
            reason="Access denied",
            visibility="public",
            details={"hint": "Use private repo"},
        )
        d = result.to_dict()
        assert d["allowed"] is False
        assert d["reason"] == "Access denied"
        assert d["visibility"] == "public"
        assert d["details"]["hint"] == "Use private repo"


class TestIsPrivateRepoModeEnabled:
    """Tests for is_private_repo_mode_enabled function."""

    def test_enabled_with_true(self):
        with patch.dict(os.environ, {PRIVATE_REPO_MODE_VAR: "true"}):
            assert is_private_repo_mode_enabled() is True

    def test_enabled_with_1(self):
        with patch.dict(os.environ, {PRIVATE_REPO_MODE_VAR: "1"}):
            assert is_private_repo_mode_enabled() is True

    def test_enabled_with_yes(self):
        with patch.dict(os.environ, {PRIVATE_REPO_MODE_VAR: "yes"}):
            assert is_private_repo_mode_enabled() is True

    def test_enabled_case_insensitive(self):
        with patch.dict(os.environ, {PRIVATE_REPO_MODE_VAR: "TRUE"}):
            assert is_private_repo_mode_enabled() is True

    def test_disabled_with_false(self):
        with patch.dict(os.environ, {PRIVATE_REPO_MODE_VAR: "false"}):
            assert is_private_repo_mode_enabled() is False

    def test_disabled_when_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_private_repo_mode_enabled() is False

    def test_disabled_with_empty_string(self):
        with patch.dict(os.environ, {PRIVATE_REPO_MODE_VAR: ""}):
            assert is_private_repo_mode_enabled() is False


class TestPrivateRepoModeEnabled:
    """Tests for Private Repo Mode (PRIVATE_REPO_MODE=true)."""

    @patch("private_repo_policy.get_repo_visibility")
    def test_allows_private_repo(self, mock_visibility):
        """When enabled, private repos should be allowed."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="private-repo",
        )
        assert result.allowed is True
        assert result.visibility == "private"
        assert result.details.get("private_repo_mode") is True

    @patch("private_repo_policy.get_repo_visibility")
    def test_allows_internal_repo(self, mock_visibility):
        """When enabled, internal repos should be allowed."""
        mock_visibility.return_value = "internal"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="internal-repo",
        )
        assert result.allowed is True
        assert result.visibility == "internal"

    @patch("private_repo_policy.get_repo_visibility")
    def test_denies_public_repo(self, mock_visibility):
        """When enabled, public repos should be denied."""
        mock_visibility.return_value = "public"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="public-repo",
        )
        assert result.allowed is False
        assert result.visibility == "public"
        assert result.details.get("private_repo_mode") is True

    @patch("private_repo_policy.get_repo_visibility")
    def test_fail_closed_on_unknown_visibility(self, mock_visibility):
        """When visibility is unknown, should deny (fail closed)."""
        mock_visibility.return_value = None

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="unknown-repo",
        )
        assert result.allowed is False
        assert result.visibility is None

    def test_fail_closed_on_unknown_repo(self):
        """When repo cannot be determined, should deny."""
        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_repository_access(
            operation="push",
            owner=None,
            repo=None,
        )
        assert result.allowed is False


class TestPublicRepoModeDefault:
    """Tests for Public Repo Mode (PRIVATE_REPO_MODE=false, the default)."""

    @patch("private_repo_policy.get_repo_visibility")
    def test_allows_public_repo(self, mock_visibility):
        """When disabled (default), public repos should be allowed."""
        mock_visibility.return_value = "public"

        policy = PrivateRepoPolicy(private_repo_mode=False)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="public-repo",
        )
        assert result.allowed is True
        assert result.visibility == "public"
        assert result.details.get("private_repo_mode") is False

    @patch("private_repo_policy.get_repo_visibility")
    def test_denies_private_repo(self, mock_visibility):
        """When disabled (default), private repos should be denied."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=False)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="private-repo",
        )
        assert result.allowed is False
        assert result.visibility == "private"
        assert "public repo mode" in result.reason.lower()
        assert result.details.get("private_repo_mode") is False

    @patch("private_repo_policy.get_repo_visibility")
    def test_denies_internal_repo(self, mock_visibility):
        """When disabled (default), internal repos should be denied."""
        mock_visibility.return_value = "internal"

        policy = PrivateRepoPolicy(private_repo_mode=False)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="internal-repo",
        )
        assert result.allowed is False
        assert result.visibility == "internal"

    @patch("private_repo_policy.get_repo_visibility")
    def test_fail_closed_on_unknown_visibility(self, mock_visibility):
        """When visibility is unknown in public mode, should deny (fail closed)."""
        mock_visibility.return_value = None

        policy = PrivateRepoPolicy(private_repo_mode=False)
        result = policy.check_repository_access(
            operation="push",
            owner="owner",
            repo="unknown-repo",
        )
        assert result.allowed is False
        assert result.visibility is None

    def test_fail_closed_on_unknown_repo(self):
        """When repo cannot be determined in public mode, should deny."""
        policy = PrivateRepoPolicy(private_repo_mode=False)
        result = policy.check_repository_access(
            operation="push",
            owner=None,
            repo=None,
        )
        assert result.allowed is False


class TestPolicyProperties:
    """Tests for policy property accessors."""

    def test_private_repo_mode_property_true(self):
        """Check private_repo_mode property when enabled."""
        policy = PrivateRepoPolicy(private_repo_mode=True)
        assert policy.private_repo_mode is True
        assert policy.public_repo_mode is False

    def test_private_repo_mode_property_false(self):
        """Check private_repo_mode property when disabled."""
        policy = PrivateRepoPolicy(private_repo_mode=False)
        assert policy.private_repo_mode is False
        assert policy.public_repo_mode is True


class TestPolicyOperations:
    """Tests for specific policy operations (push, fetch, clone, etc.)."""

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_push(self, mock_visibility):
        """check_push should work correctly."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_push(owner="owner", repo="repo")
        assert result.allowed is True

        # Verify for_write=True was used (stricter caching)
        mock_visibility.assert_called_once_with("owner", "repo", for_write=True)

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_fetch(self, mock_visibility):
        """check_fetch should work correctly."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_fetch(owner="owner", repo="repo")
        assert result.allowed is True

        # Verify for_write=False was used (read operation)
        mock_visibility.assert_called_once_with("owner", "repo", for_write=False)

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_clone(self, mock_visibility):
        """check_clone should work correctly."""
        mock_visibility.return_value = "public"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_clone(owner="owner", repo="repo")
        assert result.allowed is False

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_pr_create(self, mock_visibility):
        """check_pr_create should work correctly."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_pr_create(owner="owner", repo="repo")
        assert result.allowed is True

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_pr_comment(self, mock_visibility):
        """check_pr_comment should work correctly."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_pr_comment(owner="owner", repo="repo")
        assert result.allowed is True

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_issue(self, mock_visibility):
        """check_issue should work correctly."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_issue(owner="owner", repo="repo")
        assert result.allowed is True

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_gh_execute(self, mock_visibility):
        """check_gh_execute should work correctly."""
        mock_visibility.return_value = "private"

        policy = PrivateRepoPolicy(private_repo_mode=True)
        result = policy.check_gh_execute(owner="owner", repo="repo")
        assert result.allowed is True


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_private_repo_policy_returns_singleton(self):
        """get_private_repo_policy should return a singleton."""
        # Reset the global
        import private_repo_policy

        private_repo_policy._policy = None

        policy1 = get_private_repo_policy()
        policy2 = get_private_repo_policy()
        assert policy1 is policy2

    @patch("private_repo_policy.get_repo_visibility")
    def test_check_private_repo_access(self, mock_visibility):
        """check_private_repo_access convenience function should work."""
        mock_visibility.return_value = "private"

        # Reset singleton
        import private_repo_policy

        private_repo_policy._policy = None

        with patch.dict(os.environ, {PRIVATE_REPO_MODE_VAR: "true"}):
            # Create new singleton with mode enabled
            private_repo_policy._policy = None
            private_repo_policy._policy = PrivateRepoPolicy(private_repo_mode=True)

            result = check_private_repo_access(
                operation="push",
                owner="owner",
                repo="repo",
            )
            assert result.allowed is True
