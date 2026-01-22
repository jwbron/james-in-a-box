"""
GitHub Client - Wraps gh CLI with token management.

Reads the GitHub App token from the shared token file (written by github-token-refresher)
and executes gh CLI commands with proper authentication.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# Add shared directory to path for jib_logging
# In container, jib_logging is at /app/jib_logging
# On host, it's at ../../shared/jib_logging
_shared_path = Path(__file__).parent.parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


logger = get_logger("gateway-sidecar.github-client")

# Token file written by github-token-refresher
# In container: mounted at /secrets/.github-token
# On host (systemd mode): at ~/.jib-gateway/.github-token
TOKEN_FILE = Path("/secrets/.github-token")
if not TOKEN_FILE.exists():
    # Fallback for host/systemd mode
    TOKEN_FILE = Path.home() / ".jib-gateway" / ".github-token"
GH_CLI = "/usr/bin/gh"

# Incognito token from environment variable
INCOGNITO_TOKEN_VAR = "GITHUB_INCOGNITO_TOKEN"


@dataclass
class GitHubToken:
    """GitHub App installation token with metadata."""

    token: str
    expires_at_unix: float
    expires_at: str
    generated_at: str

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 5 minute buffer)."""
        now = datetime.now(UTC).timestamp()
        return now > (self.expires_at_unix - 5 * 60)

    @property
    def minutes_until_expiry(self) -> float:
        """Minutes until token expires."""
        now = datetime.now(UTC).timestamp()
        return (self.expires_at_unix - now) / 60


@dataclass
class GitHubResult:
    """Result from a gh CLI command."""

    success: bool
    stdout: str
    stderr: str
    returncode: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
        }


class GitHubClient:
    """Client for executing gh CLI commands with token management."""

    def __init__(self, token_file: Path = TOKEN_FILE, mode: str = "bot"):
        """
        Initialize the GitHub client.

        Args:
            token_file: Path to the bot token file (for mode="bot")
            mode: Authentication mode - "bot" (default) or "incognito"
        """
        self.token_file = token_file
        self.mode = mode
        self._cached_token: GitHubToken | None = None
        self._cached_incognito_token: str | None = None

    def get_token(self) -> GitHubToken | None:
        """
        Get the current GitHub token.

        Returns cached token if still valid, otherwise reads from file.
        """
        # Return cached token if still valid
        if self._cached_token and not self._cached_token.is_expired:
            return self._cached_token

        # Read fresh token from file
        if not self.token_file.exists():
            logger.warning("Token file not found", token_file=str(self.token_file))
            return None

        try:
            data = json.loads(self.token_file.read_text())
            self._cached_token = GitHubToken(
                token=data["token"],
                expires_at_unix=data["expires_at_unix"],
                expires_at=data["expires_at"],
                generated_at=data["generated_at"],
            )

            if self._cached_token.is_expired:
                logger.warning(
                    "Token from file is expired",
                    expires_at=self._cached_token.expires_at,
                )
                return None

            logger.debug(
                "Token loaded from file",
                minutes_until_expiry=f"{self._cached_token.minutes_until_expiry:.1f}",
            )
            return self._cached_token

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                "Failed to parse token file",
                error=str(e),
                token_file=str(self.token_file),
            )
            return None

    def is_token_valid(self) -> bool:
        """Check if we have a valid (non-expired) token."""
        token = self.get_token()
        return token is not None and not token.is_expired

    def get_incognito_token(self) -> str | None:
        """
        Get the incognito mode token from environment.

        The incognito token is a Personal Access Token (PAT) that attributes
        git/gh operations to a personal GitHub account instead of the bot.

        Returns:
            PAT string or None if not configured
        """
        if self._cached_incognito_token:
            return self._cached_incognito_token

        import os

        token = os.environ.get(INCOGNITO_TOKEN_VAR, "").strip()
        if not token:
            logger.warning(
                "Incognito token not configured",
                env_var=INCOGNITO_TOKEN_VAR,
            )
            return None

        self._cached_incognito_token = token
        return token

    def is_incognito_token_valid(self) -> bool:
        """Check if incognito token is configured."""
        return bool(self.get_incognito_token())

    def get_authenticated_user(self, mode: str = "bot") -> str | None:
        """
        Get the GitHub username for the authenticated token.

        Args:
            mode: "bot" or "incognito"

        Returns:
            GitHub username or None if request fails
        """
        result = self.execute(["api", "/user", "--jq", ".login"], mode=mode)
        if result.success and result.stdout:
            return result.stdout.strip()
        return None

    def validate_incognito_config(self) -> tuple[bool, str]:
        """
        Validate that the incognito token matches the configured github_user.

        Returns:
            Tuple of (is_valid, message)
        """
        # Get configured incognito user
        try:
            import sys
            from pathlib import Path

            _config_path = Path(__file__).parent.parent / "config"
            if _config_path.exists() and str(_config_path) not in sys.path:
                sys.path.insert(0, str(_config_path))
            from repo_config import get_incognito_config

            config = get_incognito_config()
            configured_user = config.get("github_user", "").strip()
        except ImportError:
            return False, "Could not load incognito config from repo_config"

        if not configured_user:
            # No incognito user configured - that's fine, incognito mode just won't be used
            return True, "No incognito user configured (incognito mode disabled)"

        # Check if token is configured
        token = self.get_incognito_token()
        if not token:
            return False, f"Incognito user '{configured_user}' configured but {INCOGNITO_TOKEN_VAR} not set"

        # Get the actual user from the token
        actual_user = self.get_authenticated_user(mode="incognito")
        if not actual_user:
            return False, f"Could not authenticate with {INCOGNITO_TOKEN_VAR} - token may be invalid"

        # Compare users (case-insensitive)
        if actual_user.lower() != configured_user.lower():
            logger.error(
                "Incognito token/user mismatch",
                configured_user=configured_user,
                actual_user=actual_user,
            )
            return False, (
                f"Token/user mismatch: {INCOGNITO_TOKEN_VAR} belongs to '{actual_user}' "
                f"but incognito.github_user is '{configured_user}'"
            )

        logger.info(
            "Incognito config validated",
            github_user=actual_user,
        )
        return True, f"Incognito mode configured for user '{actual_user}'"

    def get_token_for_mode(self, mode: str | None = None) -> str | None:
        """
        Get the appropriate token string for the specified mode.

        Args:
            mode: "bot" or "incognito" (defaults to self.mode)

        Returns:
            Token string or None if not available
        """
        mode = mode or self.mode

        if mode == "incognito":
            return self.get_incognito_token()
        else:
            token = self.get_token()
            return token.token if token else None

    def execute(
        self,
        args: list[str],
        timeout: int = 60,
        cwd: str | Path | None = None,
        mode: str | None = None,
    ) -> GitHubResult:
        """
        Execute a gh CLI command with authentication.

        Args:
            args: Command arguments (without 'gh' prefix)
            timeout: Command timeout in seconds
            cwd: Working directory for the command
            mode: Auth mode override ("bot" or "incognito"), defaults to self.mode

        Returns:
            GitHubResult with command output
        """
        effective_mode = mode or self.mode
        token_str = self.get_token_for_mode(effective_mode)

        if not token_str:
            if effective_mode == "incognito":
                return GitHubResult(
                    success=False,
                    stdout="",
                    stderr=f"Incognito token not available. Set {INCOGNITO_TOKEN_VAR} environment variable.",
                    returncode=1,
                )
            else:
                return GitHubResult(
                    success=False,
                    stdout="",
                    stderr="GitHub token not available. Check github-token-refresher service.",
                    returncode=1,
                )

        # Build environment with token
        # Include git safe.directory config for worktree paths - gh uses git internally
        # and would otherwise fail with "dubious ownership" on container worktree paths
        env = {
            "GH_TOKEN": token_str,
            "PATH": "/usr/bin:/bin",
            # Pass git config via environment to allow any directory
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": "*",
        }

        cmd = [GH_CLI, *args]
        logger.debug("Executing gh command", command_args=args, cwd=str(cwd) if cwd else None)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
                check=False,
            )

            success = result.returncode == 0
            if not success:
                logger.warning(
                    "gh command failed",
                    command_args=args,
                    returncode=result.returncode,
                    stderr=result.stderr[:500] if result.stderr else None,
                )

            return GitHubResult(
                success=success,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        except subprocess.TimeoutExpired:
            logger.error("gh command timed out", command_args=args, timeout=timeout)
            return GitHubResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                returncode=-1,
            )
        except Exception as e:
            logger.error("gh command failed", command_args=args, error=str(e))
            return GitHubResult(
                success=False,
                stdout="",
                stderr=str(e),
                returncode=-1,
            )

    def get_pr_info(self, repo: str, pr_number: int) -> dict[str, Any] | None:
        """
        Get information about a PR.

        Args:
            repo: Repository in "owner/repo" format
            pr_number: PR number

        Returns:
            PR info dict or None on error
        """
        result = self.execute(
            [
                "pr",
                "view",
                str(pr_number),
                "--repo",
                repo,
                "--json",
                "number,title,author,state,headRefName,baseRefName",
            ]
        )

        if not result.success:
            return None

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.error("Failed to parse PR info", stdout=result.stdout[:500])
            return None

    def list_prs_for_branch(
        self, repo: str, branch: str, state: str = "open"
    ) -> list[dict[str, Any]]:
        """
        List PRs for a specific head branch.

        Args:
            repo: Repository in "owner/repo" format
            branch: Head branch name
            state: PR state filter (open, closed, all)

        Returns:
            List of PR info dicts
        """
        result = self.execute(
            [
                "pr",
                "list",
                "--repo",
                repo,
                "--head",
                branch,
                "--state",
                state,
                "--json",
                "number,title,author,state,headRefName",
            ]
        )

        if not result.success:
            return []

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

    def branch_exists(self, repo: str, branch: str) -> bool:
        """
        Check if a branch exists in the remote repository.

        Args:
            repo: Repository in "owner/repo" format
            branch: Branch name

        Returns:
            True if the branch exists, False otherwise
        """
        # Use gh api to check if branch exists
        # GET /repos/{owner}/{repo}/branches/{branch} returns 200 if exists, 404 if not
        result = self.execute(
            [
                "api",
                f"repos/{repo}/branches/{branch}",
                "--silent",
            ]
        )
        return result.success


# Global client instances (one per mode)
_clients: dict[str, GitHubClient] = {}


def get_github_client(mode: str = "bot") -> GitHubClient:
    """
    Get a GitHub client instance for the specified mode.

    Args:
        mode: Authentication mode - "bot" (default) or "incognito"

    Returns:
        GitHubClient configured for the specified mode
    """
    global _clients
    if mode not in _clients:
        _clients[mode] = GitHubClient(mode=mode)
    return _clients[mode]


def get_incognito_client() -> GitHubClient:
    """
    Get a GitHub client configured for incognito mode.

    Convenience function equivalent to get_github_client(mode="incognito").

    Returns:
        GitHubClient configured for incognito mode
    """
    return get_github_client(mode="incognito")
