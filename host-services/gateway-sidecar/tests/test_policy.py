"""Tests for policy enforcement logic."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import UTC, datetime

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from host_services.gateway_sidecar.policy import (
    PolicyEngine,
    PolicyResult,
    CachedPRInfo,
    extract_repo_from_remote,
    extract_branch_from_refspec,
    JIB_IDENTITIES,
    JIB_BRANCH_PREFIXES,
)


class TestExtractRepoFromRemote:
    """Tests for extract_repo_from_remote function."""

    def test_https_url_with_git_suffix(self):
        url = "https://github.com/owner/repo.git"
        assert extract_repo_from_remote(url) == "owner/repo"

    def test_https_url_without_git_suffix(self):
        url = "https://github.com/owner/repo"
        assert extract_repo_from_remote(url) == "owner/repo"

    def test_ssh_url(self):
        url = "git@github.com:owner/repo.git"
        assert extract_repo_from_remote(url) == "owner/repo"

    def test_ssh_url_without_git_suffix(self):
        url = "git@github.com:owner/repo"
        assert extract_repo_from_remote(url) == "owner/repo"

    def test_invalid_url(self):
        url = "not-a-valid-url"
        assert extract_repo_from_remote(url) is None

    def test_non_github_url(self):
        url = "https://gitlab.com/owner/repo.git"
        assert extract_repo_from_remote(url) is None


class TestExtractBranchFromRefspec:
    """Tests for extract_branch_from_refspec function."""

    def test_simple_branch(self):
        assert extract_branch_from_refspec("main") == "main"

    def test_refs_heads_prefix(self):
        assert extract_branch_from_refspec("refs/heads/feature") == "feature"

    def test_local_remote_format(self):
        assert extract_branch_from_refspec("local:remote") == "remote"

    def test_full_refspec(self):
        refspec = "+refs/heads/local:refs/heads/remote"
        assert extract_branch_from_refspec(refspec) == "remote"

    def test_empty_refspec(self):
        assert extract_branch_from_refspec("") is None

    def test_force_push_prefix(self):
        assert extract_branch_from_refspec("+main") == "main"


class TestJibIdentities:
    """Tests for jib identity checking."""

    def test_jib_identities_include_expected(self):
        assert "jib" in JIB_IDENTITIES
        assert "jib[bot]" in JIB_IDENTITIES
        assert "app/jib" in JIB_IDENTITIES
        assert "apps/jib" in JIB_IDENTITIES

    def test_jib_branch_prefixes(self):
        assert "jib-" in JIB_BRANCH_PREFIXES
        assert "jib/" in JIB_BRANCH_PREFIXES


class TestCachedPRInfo:
    """Tests for CachedPRInfo class."""

    def test_is_stale_fresh_entry(self):
        info = CachedPRInfo(
            pr_number=1,
            author="jib",
            state="open",
            head_branch="feature",
            fetched_at=datetime.now(UTC).timestamp(),
        )
        assert not info.is_stale

    def test_is_stale_old_entry(self):
        # 10 minutes ago
        old_time = datetime.now(UTC).timestamp() - 600
        info = CachedPRInfo(
            pr_number=1,
            author="jib",
            state="open",
            head_branch="feature",
            fetched_at=old_time,
        )
        assert info.is_stale


class TestPolicyEngine:
    """Tests for PolicyEngine class."""

    @pytest.fixture
    def mock_github_client(self):
        """Create a mock GitHub client."""
        return MagicMock()

    @pytest.fixture
    def policy_engine(self, mock_github_client):
        """Create a policy engine with mocked GitHub client."""
        return PolicyEngine(github_client=mock_github_client)

    # Branch ownership tests

    def test_branch_ownership_jib_prefix_dash(self, policy_engine):
        """jib- prefixed branches are always owned by jib."""
        result = policy_engine.check_branch_ownership("owner/repo", "jib-feature")
        assert result.allowed
        assert "jib-prefixed" in result.reason

    def test_branch_ownership_jib_prefix_slash(self, policy_engine):
        """jib/ prefixed branches are always owned by jib."""
        result = policy_engine.check_branch_ownership("owner/repo", "jib/feature")
        assert result.allowed
        assert "jib-prefixed" in result.reason

    def test_branch_ownership_with_jib_pr(self, policy_engine, mock_github_client):
        """Branch with open jib-authored PR is owned by jib."""
        # Mock PR list
        mock_github_client.list_prs_for_branch.return_value = [
            {"number": 123, "author": {"login": "jib"}, "state": "open", "headRefName": "feature"}
        ]
        mock_github_client.get_pr_info.return_value = {
            "number": 123,
            "author": {"login": "jib"},
            "state": "open",
            "headRefName": "feature",
        }

        result = policy_engine.check_branch_ownership("owner/repo", "feature")
        assert result.allowed
        assert "PR #123" in result.reason

    def test_branch_ownership_no_pr(self, policy_engine, mock_github_client):
        """Branch without PR is not owned by jib."""
        mock_github_client.list_prs_for_branch.return_value = []

        result = policy_engine.check_branch_ownership("owner/repo", "feature")
        assert not result.allowed
        assert "not owned by jib" in result.reason

    def test_branch_ownership_other_author_pr(self, policy_engine, mock_github_client):
        """Branch with PR by non-jib author is not owned by jib."""
        mock_github_client.list_prs_for_branch.return_value = [
            {"number": 123, "author": {"login": "human"}, "state": "open", "headRefName": "feature"}
        ]
        mock_github_client.get_pr_info.return_value = {
            "number": 123,
            "author": {"login": "human"},
            "state": "open",
            "headRefName": "feature",
        }

        result = policy_engine.check_branch_ownership("owner/repo", "feature")
        assert not result.allowed

    # PR ownership tests

    def test_pr_ownership_jib_author(self, policy_engine, mock_github_client):
        """PR authored by jib is owned by jib."""
        mock_github_client.get_pr_info.return_value = {
            "number": 123,
            "author": {"login": "jib"},
            "state": "open",
            "headRefName": "feature",
        }

        result = policy_engine.check_pr_ownership("owner/repo", 123)
        assert result.allowed
        assert "owned by jib" in result.reason

    def test_pr_ownership_jib_bot_author(self, policy_engine, mock_github_client):
        """PR authored by jib[bot] is owned by jib."""
        mock_github_client.get_pr_info.return_value = {
            "number": 123,
            "author": {"login": "jib[bot]"},
            "state": "open",
            "headRefName": "feature",
        }

        result = policy_engine.check_pr_ownership("owner/repo", 123)
        assert result.allowed

    def test_pr_ownership_other_author(self, policy_engine, mock_github_client):
        """PR authored by non-jib is not owned by jib."""
        mock_github_client.get_pr_info.return_value = {
            "number": 123,
            "author": {"login": "human"},
            "state": "open",
            "headRefName": "feature",
        }

        result = policy_engine.check_pr_ownership("owner/repo", 123)
        assert not result.allowed
        assert "not owned by jib" in result.reason

    def test_pr_ownership_not_found(self, policy_engine, mock_github_client):
        """PR that doesn't exist returns not allowed."""
        mock_github_client.get_pr_info.return_value = None

        result = policy_engine.check_pr_ownership("owner/repo", 999)
        assert not result.allowed
        assert "not found" in result.reason

    # Merge policy tests

    def test_merge_always_blocked(self, policy_engine):
        """Merge operations are always blocked."""
        result = policy_engine.check_merge_allowed("owner/repo", 123)
        assert not result.allowed
        assert "not supported" in result.reason
        assert "Human must merge" in result.reason


class TestPolicyResult:
    """Tests for PolicyResult class."""

    def test_to_dict_allowed(self):
        result = PolicyResult(allowed=True, reason="Test reason")
        d = result.to_dict()
        assert d["allowed"] is True
        assert d["reason"] == "Test reason"
        assert "details" not in d

    def test_to_dict_with_details(self):
        result = PolicyResult(
            allowed=False,
            reason="Test reason",
            details={"key": "value"},
        )
        d = result.to_dict()
        assert d["allowed"] is False
        assert d["details"] == {"key": "value"}
