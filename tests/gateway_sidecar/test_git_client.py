"""Tests for gateway-sidecar git_client module."""

import sys
from pathlib import Path


# Add gateway-sidecar to path for imports
gateway_path = Path(__file__).parent.parent.parent / "gateway-sidecar"
if str(gateway_path) not in sys.path:
    sys.path.insert(0, str(gateway_path))

from git_client import is_ssh_url, ssh_url_to_https


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
