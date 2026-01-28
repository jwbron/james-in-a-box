"""Tests for gateway-sidecar git_client module."""

import sys
from pathlib import Path


# Add gateway-sidecar to path for imports
gateway_path = Path(__file__).parent.parent.parent / "gateway-sidecar"
if str(gateway_path) not in sys.path:
    sys.path.insert(0, str(gateway_path))

from git_client import get_authenticated_remote_target, is_ssh_url, ssh_url_to_https


class TestIsSshUrl:
    """Tests for is_ssh_url function."""

    def test_git_at_url_is_ssh(self):
        """git@github.com URLs are SSH."""
        assert is_ssh_url("git@github.com:owner/repo.git") is True

    def test_ssh_protocol_is_ssh(self):
        """ssh:// URLs are SSH."""
        assert is_ssh_url("ssh://git@github.com/owner/repo.git") is True

    def test_https_url_is_not_ssh(self):
        """HTTPS URLs are not SSH."""
        assert is_ssh_url("https://github.com/owner/repo.git") is False

    def test_http_url_is_not_ssh(self):
        """HTTP URLs are not SSH."""
        assert is_ssh_url("http://github.com/owner/repo.git") is False

    def test_empty_string(self):
        """Empty string is not SSH."""
        assert is_ssh_url("") is False


class TestSshUrlToHttps:
    """Tests for ssh_url_to_https function."""

    def test_convert_git_at_with_dot_git(self):
        """Convert git@github.com:owner/repo.git to HTTPS."""
        result = ssh_url_to_https("git@github.com:owner/repo.git")
        assert result == "https://github.com/owner/repo.git"

    def test_convert_git_at_without_dot_git(self):
        """Convert git@github.com:owner/repo (no .git) to HTTPS."""
        result = ssh_url_to_https("git@github.com:owner/repo")
        assert result == "https://github.com/owner/repo.git"

    def test_convert_ssh_protocol_with_dot_git(self):
        """Convert ssh://git@github.com/owner/repo.git to HTTPS."""
        result = ssh_url_to_https("ssh://git@github.com/owner/repo.git")
        assert result == "https://github.com/owner/repo.git"

    def test_convert_ssh_protocol_without_dot_git(self):
        """Convert ssh://git@github.com/owner/repo (no .git) to HTTPS."""
        result = ssh_url_to_https("ssh://git@github.com/owner/repo")
        assert result == "https://github.com/owner/repo.git"

    def test_https_url_unchanged(self):
        """HTTPS URLs are returned unchanged."""
        url = "https://github.com/owner/repo.git"
        assert ssh_url_to_https(url) == url

    def test_http_url_unchanged(self):
        """HTTP URLs are returned unchanged."""
        url = "http://github.com/owner/repo.git"
        assert ssh_url_to_https(url) == url

    def test_preserves_owner_and_repo(self):
        """Owner and repo names are preserved in conversion."""
        result = ssh_url_to_https("git@github.com:jwbron/james-in-a-box.git")
        assert result == "https://github.com/jwbron/james-in-a-box.git"

    def test_preserves_nested_owner(self):
        """Handles nested paths like org/repo correctly."""
        result = ssh_url_to_https("git@github.com:Khan/webapp.git")
        assert result == "https://github.com/Khan/webapp.git"


class TestGetAuthenticatedRemoteTarget:
    """Tests for get_authenticated_remote_target function."""

    def test_ssh_url_returns_https(self):
        """SSH URLs are converted to HTTPS."""
        result = get_authenticated_remote_target("origin", "git@github.com:owner/repo.git")
        assert result == "https://github.com/owner/repo.git"

    def test_ssh_protocol_returns_https(self):
        """ssh:// URLs are converted to HTTPS."""
        result = get_authenticated_remote_target("origin", "ssh://git@github.com/owner/repo.git")
        assert result == "https://github.com/owner/repo.git"

    def test_https_url_returns_remote_name(self):
        """HTTPS URLs return the remote name (no conversion needed)."""
        result = get_authenticated_remote_target("origin", "https://github.com/owner/repo.git")
        assert result == "origin"

    def test_http_url_returns_remote_name(self):
        """HTTP URLs return the remote name."""
        result = get_authenticated_remote_target("upstream", "http://github.com/owner/repo.git")
        assert result == "upstream"

    def test_custom_remote_name_returned_for_https(self):
        """Custom remote names are preserved for HTTPS URLs."""
        result = get_authenticated_remote_target("my-remote", "https://github.com/owner/repo.git")
        assert result == "my-remote"

    def test_ssh_url_ignores_remote_name(self):
        """For SSH URLs, the remote name is ignored in favor of HTTPS URL."""
        result = get_authenticated_remote_target(
            "my-custom-remote", "git@github.com:owner/repo.git"
        )
        assert result == "https://github.com/owner/repo.git"
