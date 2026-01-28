"""
Private Repository Policy Enforcement.

Restricts git/gh operations to private repositories only when Private Repo Mode
is enabled. This prevents the agent from interacting with public repositories,
reducing the risk of:
- Accidental code sharing to public repositories
- Data leakage via forks
- Cross-contamination with public dependencies

Security Properties:
- FAIL CLOSED: If visibility cannot be determined, treat as public (deny access)
- Per-operation checking: Every operation validates the target repository
- Audit logging: All policy decisions are logged
"""

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# Add shared directory to path for jib_logging
_shared_path = Path(__file__).parent.parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


# Import using try/except for both module and standalone script mode
try:
    from .repo_visibility import get_repo_visibility, is_repo_private
    from .repo_parser import (
        RepoInfo,
        extract_repo_from_request,
        parse_owner_repo,
    )
    from .error_messages import get_error_message
except ImportError:
    from repo_visibility import get_repo_visibility, is_repo_private
    from repo_parser import (
        RepoInfo,
        extract_repo_from_request,
        parse_owner_repo,
    )
    from error_messages import get_error_message


logger = get_logger("gateway-sidecar.private-repo-policy")


# Environment variable to enable/disable Private Repo Mode
PRIVATE_REPO_MODE_VAR = "PRIVATE_REPO_MODE"


@dataclass
class PrivateRepoPolicyResult:
    """Result of a private repo policy check."""

    allowed: bool
    reason: str
    visibility: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {
            "allowed": self.allowed,
            "reason": self.reason,
            "policy": "private_repo_mode",
        }
        if self.visibility:
            result["visibility"] = self.visibility
        if self.details:
            result["details"] = self.details
        return result


def is_private_repo_mode_enabled() -> bool:
    """
    Check if Private Repo Mode is enabled.

    Returns:
        True if PRIVATE_REPO_MODE environment variable is set to true/1/yes
    """
    value = os.environ.get(PRIVATE_REPO_MODE_VAR, "false").lower().strip()
    return value in ("true", "1", "yes")


class PrivateRepoPolicy:
    """
    Policy engine for Private Repo Mode.

    When enabled, restricts all git/gh operations to private repositories only.
    """

    def __init__(self, enabled: bool | None = None):
        """
        Initialize the policy.

        Args:
            enabled: Force enable/disable mode (default: read from environment)
        """
        self._enabled = enabled if enabled is not None else is_private_repo_mode_enabled()

    @property
    def enabled(self) -> bool:
        """Check if Private Repo Mode is enabled."""
        return self._enabled

    def _log_policy_event(
        self,
        operation: str,
        repo: RepoInfo | str | None,
        visibility: str | None,
        allowed: bool,
        reason: str,
    ) -> None:
        """Log a policy decision."""
        repo_str = str(repo) if repo else "unknown"

        log_data = {
            "event_type": "private_repo_policy",
            "operation": operation,
            "repository": repo_str,
            "visibility": visibility,
            "decision": "allowed" if allowed else "denied",
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        if allowed:
            logger.info("Private repo policy check passed", **log_data)
        else:
            logger.warning("Private repo policy check failed", **log_data)

    def check_repository_access(
        self,
        operation: str,
        owner: str | None = None,
        repo: str | None = None,
        repo_path: str | None = None,
        url: str | None = None,
        for_write: bool = False,
    ) -> PrivateRepoPolicyResult:
        """
        Check if access to a repository is allowed under Private Repo Mode.

        Args:
            operation: Name of the operation (push, fetch, clone, etc.)
            owner: Repository owner (if known)
            repo: Repository name (if known)
            repo_path: Local repository path
            url: GitHub URL
            for_write: If True, use stricter caching (always verify)

        Returns:
            PrivateRepoPolicyResult with allowed status and reason
        """
        # If Private Repo Mode is disabled, allow everything
        if not self._enabled:
            return PrivateRepoPolicyResult(
                allowed=True,
                reason="Private Repo Mode is disabled",
                details={"private_repo_mode": False},
            )

        # Try to determine the repository
        repo_info: RepoInfo | None = None

        # If owner and repo are provided directly
        if owner and repo:
            repo_info = RepoInfo(owner=owner, repo=repo)
        # Try full repo string (owner/repo format)
        elif repo and "/" in repo:
            repo_info = parse_owner_repo(repo)
        # Try to extract from other sources
        else:
            repo_str = f"{owner}/{repo}" if owner and repo else repo
            repo_info = extract_repo_from_request(
                repo=repo_str,
                repo_path=repo_path,
                url=url,
            )

        if not repo_info:
            # Cannot determine repository - FAIL CLOSED
            reason = get_error_message(
                "visibility_unknown",
                operation=operation,
                hint="Could not determine target repository",
            )
            self._log_policy_event(operation, None, None, False, reason)
            return PrivateRepoPolicyResult(
                allowed=False,
                reason=reason,
                details={
                    "error": "Could not determine target repository",
                    "repo": repo,
                    "repo_path": repo_path,
                    "url": url,
                },
            )

        # Check repository visibility
        visibility = get_repo_visibility(
            repo_info.owner,
            repo_info.repo,
            for_write=for_write,
        )

        if visibility is None:
            # Cannot determine visibility - FAIL CLOSED
            reason = get_error_message(
                "visibility_unknown",
                repo=str(repo_info),
                operation=operation,
            )
            self._log_policy_event(operation, repo_info, None, False, reason)
            return PrivateRepoPolicyResult(
                allowed=False,
                reason=reason,
                visibility=None,
                details={
                    "error": "Could not determine repository visibility",
                    "repository": str(repo_info),
                    "hint": "GitHub API may be unavailable or token may lack permissions",
                },
            )

        if visibility == "public":
            # Public repository - DENY
            reason = get_error_message(
                f"{operation}_public",
                repo=str(repo_info),
            )
            self._log_policy_event(operation, repo_info, visibility, False, reason)
            return PrivateRepoPolicyResult(
                allowed=False,
                reason=reason,
                visibility=visibility,
                details={
                    "repository": str(repo_info),
                    "visibility": visibility,
                    "hint": "Private Repo Mode only allows interaction with private repositories",
                },
            )

        # Private or internal - ALLOW
        self._log_policy_event(
            operation,
            repo_info,
            visibility,
            True,
            f"Repository is {visibility}",
        )
        return PrivateRepoPolicyResult(
            allowed=True,
            reason=f"Repository '{repo_info}' is {visibility}",
            visibility=visibility,
            details={"repository": str(repo_info), "visibility": visibility},
        )

    def check_push(
        self,
        owner: str | None = None,
        repo: str | None = None,
        repo_path: str | None = None,
    ) -> PrivateRepoPolicyResult:
        """Check if push is allowed."""
        return self.check_repository_access(
            operation="push",
            owner=owner,
            repo=repo,
            repo_path=repo_path,
            for_write=True,
        )

    def check_fetch(
        self,
        owner: str | None = None,
        repo: str | None = None,
        repo_path: str | None = None,
    ) -> PrivateRepoPolicyResult:
        """Check if fetch is allowed."""
        return self.check_repository_access(
            operation="fetch",
            owner=owner,
            repo=repo,
            repo_path=repo_path,
            for_write=False,
        )

    def check_clone(
        self,
        url: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> PrivateRepoPolicyResult:
        """Check if clone is allowed."""
        return self.check_repository_access(
            operation="clone",
            owner=owner,
            repo=repo,
            url=url,
            for_write=False,
        )

    def check_pr_create(
        self,
        owner: str | None = None,
        repo: str | None = None,
    ) -> PrivateRepoPolicyResult:
        """Check if PR creation is allowed."""
        return self.check_repository_access(
            operation="pr_create",
            owner=owner,
            repo=repo,
            for_write=True,
        )

    def check_pr_comment(
        self,
        owner: str | None = None,
        repo: str | None = None,
    ) -> PrivateRepoPolicyResult:
        """Check if PR comment is allowed."""
        return self.check_repository_access(
            operation="pr_comment",
            owner=owner,
            repo=repo,
            for_write=True,
        )

    def check_issue(
        self,
        owner: str | None = None,
        repo: str | None = None,
    ) -> PrivateRepoPolicyResult:
        """Check if issue operations are allowed."""
        return self.check_repository_access(
            operation="issue",
            owner=owner,
            repo=repo,
            for_write=True,
        )

    def check_gh_execute(
        self,
        owner: str | None = None,
        repo: str | None = None,
    ) -> PrivateRepoPolicyResult:
        """Check if generic gh execute is allowed."""
        return self.check_repository_access(
            operation="gh_execute",
            owner=owner,
            repo=repo,
            for_write=False,
        )


# Global policy instance
_policy: PrivateRepoPolicy | None = None


def get_private_repo_policy() -> PrivateRepoPolicy:
    """Get the global private repo policy instance."""
    global _policy
    if _policy is None:
        _policy = PrivateRepoPolicy()
    return _policy


def check_private_repo_access(
    operation: str,
    owner: str | None = None,
    repo: str | None = None,
    repo_path: str | None = None,
    url: str | None = None,
    for_write: bool = False,
) -> PrivateRepoPolicyResult:
    """
    Check private repo access (convenience function).

    Args:
        operation: Name of the operation
        owner: Repository owner
        repo: Repository name or owner/repo
        repo_path: Local repository path
        url: GitHub URL
        for_write: If True, use stricter caching

    Returns:
        PrivateRepoPolicyResult
    """
    return get_private_repo_policy().check_repository_access(
        operation=operation,
        owner=owner,
        repo=repo,
        repo_path=repo_path,
        url=url,
        for_write=for_write,
    )
