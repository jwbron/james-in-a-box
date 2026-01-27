"""
Tests for git validation functions in Gateway Sidecar.

Tests cover:
- Path validation (prevent path traversal attacks)
- Git argument sanitization
- Flag normalization
- gh API path allowlist validation
"""

import os
import tempfile
from unittest.mock import patch

import pytest

import gateway


class TestRepoPathValidation:
    """Tests for validate_repo_path function."""

    def test_valid_repos_path(self):
        """Valid path under /home/jib/repos/ is accepted."""
        with patch("os.path.realpath", return_value="/home/jib/repos/myrepo"):
            valid, error = gateway.validate_repo_path("/home/jib/repos/myrepo")
            assert valid is True
            assert error == ""

    def test_valid_worktree_path(self):
        """Valid path under /home/jib/.jib-worktrees/ is accepted."""
        with patch(
            "os.path.realpath",
            return_value="/home/jib/.jib-worktrees/jib-123/repo",
        ):
            valid, error = gateway.validate_repo_path(
                "/home/jib/.jib-worktrees/jib-123/repo"
            )
            assert valid is True
            assert error == ""

    def test_valid_legacy_repos_path(self):
        """Valid path under /repos/ (legacy) is accepted."""
        with patch("os.path.realpath", return_value="/repos/myrepo"):
            valid, error = gateway.validate_repo_path("/repos/myrepo")
            assert valid is True
            assert error == ""

    def test_path_traversal_blocked(self):
        """Path traversal attempt via .. is blocked."""
        # Simulate realpath resolving the traversal
        with patch("os.path.realpath", return_value="/etc/passwd"):
            valid, error = gateway.validate_repo_path(
                "/home/jib/repos/../../../etc/passwd"
            )
            assert valid is False
            assert "allowed directories" in error

    def test_absolute_escape_blocked(self):
        """Absolute path outside allowed dirs is blocked."""
        with patch("os.path.realpath", return_value="/etc/passwd"):
            valid, error = gateway.validate_repo_path("/etc/passwd")
            assert valid is False
            assert "allowed directories" in error

    def test_empty_path_rejected(self):
        """Empty path is rejected."""
        valid, error = gateway.validate_repo_path("")
        assert valid is False
        assert "required" in error

    def test_none_path_rejected(self):
        """None path is rejected."""
        valid, error = gateway.validate_repo_path(None)
        assert valid is False
        assert "required" in error

    def test_realpath_exception_handled(self):
        """Exception during path resolution is handled gracefully."""
        with patch("os.path.realpath", side_effect=OSError("Permission denied")):
            valid, error = gateway.validate_repo_path("/some/path")
            assert valid is False
            assert "Invalid repo_path" in error


class TestGitArgsSanitization:
    """Tests for sanitize_git_args function."""

    def test_upload_pack_blocked(self):
        """--upload-pack flag is blocked."""
        valid, error, _ = gateway.sanitize_git_args(["--upload-pack=/evil/cmd"])
        assert valid is False
        assert "Blocked" in error

    def test_exec_blocked(self):
        """--exec flag is blocked."""
        valid, error, _ = gateway.sanitize_git_args(["--exec=/evil/cmd"])
        assert valid is False
        assert "Blocked" in error

    def test_short_u_blocked(self):
        """-u flag (short for --upload-pack) is blocked."""
        valid, error, _ = gateway.sanitize_git_args(["-u=/evil/cmd"])
        assert valid is False
        assert "Blocked" in error

    def test_upload_pack_case_insensitive(self):
        """Blocking is case-insensitive."""
        valid, error, _ = gateway.sanitize_git_args(["--Upload-Pack=/evil"])
        assert valid is False
        assert "Blocked" in error

    def test_normal_args_allowed(self):
        """Normal git arguments are allowed."""
        valid, error, args = gateway.sanitize_git_args(["--tags", "--prune", "main"])
        assert valid is True
        assert error == ""
        assert args == ["--tags", "--prune", "main"]

    def test_empty_args_allowed(self):
        """Empty argument list is allowed."""
        valid, error, args = gateway.sanitize_git_args([])
        assert valid is True
        assert error == ""
        assert args == []

    def test_none_args_allowed(self):
        """None argument list becomes empty."""
        valid, error, args = gateway.sanitize_git_args(None)
        assert valid is True
        assert args == []

    def test_non_string_rejected(self):
        """Non-string arguments are rejected."""
        valid, error, _ = gateway.sanitize_git_args([{"nested": "object"}])
        assert valid is False
        assert "Invalid argument type" in error

    def test_mixed_valid_and_blocked(self):
        """Mixed valid and blocked args are rejected."""
        valid, error, _ = gateway.sanitize_git_args(
            ["--tags", "--upload-pack=/evil", "--prune"]
        )
        assert valid is False
        assert "Blocked" in error


class TestFlagNormalization:
    """Tests for normalize_flag function."""

    def test_short_to_long_fetch(self):
        """Short flags are normalized to long form for fetch."""
        assert gateway.normalize_flag("-a") == "--all"
        assert gateway.normalize_flag("-t") == "--tags"
        assert gateway.normalize_flag("-p") == "--prune"
        assert gateway.normalize_flag("-v") == "--verbose"
        assert gateway.normalize_flag("-q") == "--quiet"
        assert gateway.normalize_flag("-j") == "--jobs"

    def test_short_to_long_push(self):
        """Short flags are normalized to long form for push."""
        assert gateway.normalize_flag("-f") == "--force"
        assert gateway.normalize_flag("-d") == "--delete"
        assert gateway.normalize_flag("-n") == "--dry-run"

    def test_long_flags_unchanged(self):
        """Long flags are returned unchanged."""
        assert gateway.normalize_flag("--all") == "--all"
        assert gateway.normalize_flag("--force") == "--force"
        assert gateway.normalize_flag("--verbose") == "--verbose"

    def test_unknown_flags_unchanged(self):
        """Unknown flags are returned unchanged."""
        assert gateway.normalize_flag("--unknown-flag") == "--unknown-flag"
        assert gateway.normalize_flag("-x") == "-x"

    def test_flag_with_value_normalized(self):
        """Flags with = values have base normalized."""
        assert gateway.normalize_flag("-j=4") == "--jobs=4"
        assert gateway.normalize_flag("-f=foo") == "--force=foo"

    def test_long_flag_with_value_unchanged(self):
        """Long flags with values are unchanged."""
        assert gateway.normalize_flag("--jobs=4") == "--jobs=4"


class TestGhApiPathValidation:
    """Tests for validate_gh_api_path function."""

    def test_pr_list_allowed(self):
        """PR list endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/pulls")
        assert valid is True
        assert error == ""

    def test_pr_view_allowed(self):
        """PR view endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/pulls/123")
        assert valid is True
        assert error == ""

    def test_pr_comments_allowed(self):
        """PR comments endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/pulls/123/comments")
        assert valid is True
        assert error == ""

    def test_pr_reviews_allowed(self):
        """PR reviews endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/pulls/123/reviews")
        assert valid is True
        assert error == ""

    def test_issue_list_allowed(self):
        """Issue list endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/issues")
        assert valid is True
        assert error == ""

    def test_issue_view_allowed(self):
        """Issue view endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/issues/456")
        assert valid is True
        assert error == ""

    def test_repo_info_allowed(self):
        """Repo info endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo")
        assert valid is True
        assert error == ""

    def test_branches_allowed(self):
        """Branches endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/branches")
        assert valid is True
        assert error == ""

    def test_user_info_allowed(self):
        """User info endpoint is allowed."""
        valid, error = gateway.validate_gh_api_path("user")
        assert valid is True
        assert error == ""

    def test_leading_slash_stripped(self):
        """Leading slash is stripped before validation."""
        valid, error = gateway.validate_gh_api_path("/repos/owner/repo/pulls")
        assert valid is True
        assert error == ""

    def test_unknown_path_blocked(self):
        """Unknown API paths are blocked."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/unknown")
        assert valid is False
        assert "not in allowlist" in error

    def test_admin_paths_blocked(self):
        """Admin/dangerous paths are blocked."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/hooks")
        assert valid is False
        assert "not in allowlist" in error

    def test_delete_method_blocked(self):
        """DELETE method is blocked."""
        valid, error = gateway.validate_gh_api_path(
            "repos/owner/repo/pulls/123", method="DELETE"
        )
        assert valid is False
        assert "method" in error.lower()

    def test_get_method_allowed(self):
        """GET method is allowed."""
        valid, error = gateway.validate_gh_api_path(
            "repos/owner/repo/pulls", method="GET"
        )
        assert valid is True

    def test_post_method_allowed(self):
        """POST method is allowed."""
        valid, error = gateway.validate_gh_api_path(
            "repos/owner/repo/pulls/123/comments", method="POST"
        )
        assert valid is True

    def test_patch_method_allowed(self):
        """PATCH method is allowed."""
        valid, error = gateway.validate_gh_api_path(
            "repos/owner/repo/pulls/123", method="PATCH"
        )
        assert valid is True

    def test_pr_number_must_be_numeric(self):
        """PR number must be numeric."""
        valid, error = gateway.validate_gh_api_path("repos/owner/repo/pulls/abc")
        assert valid is False
        assert "not in allowlist" in error


class TestSharedHelperFunctions:
    """Tests for shared credential helper functions."""

    def test_cleanup_credential_helper_with_none(self):
        """cleanup_credential_helper handles None gracefully."""
        # Should not raise
        gateway.cleanup_credential_helper(None)

    def test_cleanup_credential_helper_with_nonexistent(self):
        """cleanup_credential_helper handles nonexistent path gracefully."""
        # Should not raise
        gateway.cleanup_credential_helper("/nonexistent/path/to/file")

    def test_cleanup_credential_helper_removes_file(self):
        """cleanup_credential_helper removes existing file."""
        # Create a temp file
        fd, path = tempfile.mkstemp()
        os.close(fd)
        assert os.path.exists(path)

        gateway.cleanup_credential_helper(path)

        assert not os.path.exists(path)

    def test_create_credential_helper_creates_file(self):
        """create_credential_helper creates executable file."""
        env = {}
        path, updated_env = gateway.create_credential_helper("test-token", env)

        try:
            assert os.path.exists(path)
            # Check it's executable
            assert os.access(path, os.X_OK)
            # Check env was updated
            assert updated_env["GIT_ASKPASS"] == path
            assert updated_env["GIT_USERNAME"] == "x-access-token"
            assert updated_env["GIT_PASSWORD"] == "test-token"
            assert updated_env["GIT_TERMINAL_PROMPT"] == "0"
        finally:
            gateway.cleanup_credential_helper(path)

    def test_create_credential_helper_doesnt_modify_original_env(self):
        """create_credential_helper doesn't modify the original env dict."""
        original_env = {"EXISTING": "value"}
        path, updated_env = gateway.create_credential_helper("token", original_env)

        try:
            # Original should be unchanged
            assert "GIT_ASKPASS" not in original_env
            assert "EXISTING" in original_env
            # Updated should have both
            assert "GIT_ASKPASS" in updated_env
            assert "EXISTING" in updated_env
        finally:
            gateway.cleanup_credential_helper(path)
