"""
Policy Engine - Ownership and access control checks.

Enforces policies for git/gh operations:
- Branch ownership: jib can push to branches it owns OR branches owned by trusted users
- PR comments: jib can comment on any PR
- PR edit/close: jib can only modify PRs it created
- Merge blocked: No merge operations allowed (human must merge)

Configuration:
- GATEWAY_TRUSTED_USERS: Comma-separated list of GitHub usernames whose branches
  jib is allowed to push to (e.g., "jwbron,octocat")
"""

import os
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


# Add shared directory to path for jib_logging
# Add shared directory to path for jib_logging
# In container, jib_logging is at /app/jib_logging
# On host, it's at ../../shared/jib_logging
_shared_path = Path(__file__).parent.parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


# Import github_client - try relative import first (module mode),
# fall back to absolute import (standalone script mode in container)
try:
    from .github_client import GitHubClient, get_github_client
except ImportError:
    from github_client import GitHubClient, get_github_client


logger = get_logger("gateway-sidecar.policy")

# Cache size limits
MAX_PR_CACHE_SIZE = 500
MAX_BRANCH_PR_CACHE_SIZE = 200

# Bot identity variants that count as "jib"
# Includes both short name (jib) and full GitHub App name (james-in-a-box)
JIB_IDENTITIES = frozenset(
    {
        # Short name variants
        "jib",
        "jib[bot]",
        "app/jib",
        "apps/jib",
        # Full GitHub App name variants
        "james-in-a-box",
        "james-in-a-box[bot]",
        "app/james-in-a-box",
        "apps/james-in-a-box",
    }
)

# Branch prefixes that indicate jib ownership
JIB_BRANCH_PREFIXES = ("jib-", "jib/")


# Trusted GitHub users whose branches jib can push to
# Loaded from GATEWAY_TRUSTED_USERS environment variable (comma-separated)
# Example: GATEWAY_TRUSTED_USERS="jwbron,octocat"
def _load_trusted_users() -> frozenset[str]:
    """Load trusted users from environment variable."""
    env_value = os.environ.get("GATEWAY_TRUSTED_USERS", "")
    if not env_value.strip():
        return frozenset()
    users = [u.strip().lower() for u in env_value.split(",") if u.strip()]
    return frozenset(users)


TRUSTED_BRANCH_OWNERS: frozenset[str] = _load_trusted_users()


@dataclass
class PolicyResult:
    """Result of a policy check."""

    allowed: bool
    reason: str
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {"allowed": self.allowed, "reason": self.reason}
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class CachedPRInfo:
    """Cached PR information with TTL."""

    pr_number: int
    author: str
    state: str
    head_branch: str
    fetched_at: float

    @property
    def is_stale(self) -> bool:
        """Check if cache entry is stale (> 5 minutes old)."""
        return (datetime.now(UTC).timestamp() - self.fetched_at) > 300


class BoundedCache(OrderedDict):
    """An OrderedDict with a maximum size that evicts oldest entries."""

    def __init__(self, max_size: int):
        super().__init__()
        self.max_size = max_size

    def __setitem__(self, key, value):
        if key in self:
            # Move to end if updating existing key
            self.move_to_end(key)
        super().__setitem__(key, value)
        # Evict oldest entries if over max size
        while len(self) > self.max_size:
            self.popitem(last=False)


class PolicyEngine:
    """
    Policy enforcement engine for git/gh operations.

    Caches PR info to reduce GitHub API calls.
    Uses bounded caches to prevent unbounded memory growth.
    """

    def __init__(self, github_client: GitHubClient | None = None):
        self.github = github_client or get_github_client()
        # Cache: (repo, pr_number) -> CachedPRInfo (bounded)
        self._pr_cache: BoundedCache = BoundedCache(MAX_PR_CACHE_SIZE)
        # Cache: (repo, branch) -> (list of PR numbers, timestamp) (bounded)
        self._branch_pr_cache: BoundedCache = BoundedCache(MAX_BRANCH_PR_CACHE_SIZE)

    def _is_jib_author(self, author: str | dict[str, Any]) -> bool:
        """Check if author is a jib identity."""
        if isinstance(author, dict):
            # GitHub API returns author as {"login": "username"}
            login = author.get("login", "")
        else:
            login = author

        return login.lower() in JIB_IDENTITIES

    def _is_jib_branch(self, branch: str) -> bool:
        """Check if branch name indicates jib ownership."""
        return branch.startswith(JIB_BRANCH_PREFIXES)

    def _is_trusted_author(self, author: str | dict[str, Any]) -> bool:
        """Check if author is a trusted user (whose branches jib can push to)."""
        if not TRUSTED_BRANCH_OWNERS:
            return False
        if isinstance(author, dict):
            login = author.get("login", "")
        else:
            login = author
        return login.lower() in TRUSTED_BRANCH_OWNERS

    def _get_incognito_user(self) -> str | None:
        """Get the configured incognito GitHub username."""
        try:
            # Import here to avoid circular imports and handle missing config
            _config_path = Path(__file__).parent.parent / "config"
            if _config_path.exists() and str(_config_path) not in sys.path:
                sys.path.insert(0, str(_config_path))
            from repo_config import get_incognito_config

            config = get_incognito_config()
            return config.get("github_user", "").lower() or None
        except ImportError:
            return None

    def _is_incognito_author(self, author: str | dict[str, Any], incognito_user: str) -> bool:
        """Check if author matches the incognito user."""
        if isinstance(author, dict):
            login = author.get("login", "")
        else:
            login = author
        return login.lower() == incognito_user.lower()

    def _get_pr_info(self, repo: str, pr_number: int) -> CachedPRInfo | None:
        """Get PR info, using cache if available and fresh."""
        cache_key = (repo, pr_number)

        # Check cache
        cached = self._pr_cache.get(cache_key)
        if cached and not cached.is_stale:
            return cached

        # Fetch from GitHub
        pr_data = self.github.get_pr_info(repo, pr_number)
        if not pr_data:
            return None

        # Cache the result
        author = pr_data.get("author", {})
        cached_info = CachedPRInfo(
            pr_number=pr_number,
            author=author.get("login", "") if isinstance(author, dict) else str(author),
            state=pr_data.get("state", ""),
            head_branch=pr_data.get("headRefName", ""),
            fetched_at=datetime.now(UTC).timestamp(),
        )
        self._pr_cache[cache_key] = cached_info
        return cached_info

    def _get_prs_for_branch(self, repo: str, branch: str) -> list[int]:
        """Get open PR numbers for a branch, using cache if available."""
        cache_key = (repo, branch)

        # Check cache (2 minute TTL for branch->PR mapping)
        cached = self._branch_pr_cache.get(cache_key)
        if cached:
            pr_numbers, fetched_at = cached
            if (datetime.now(UTC).timestamp() - fetched_at) < 120:
                return pr_numbers

        # Fetch from GitHub
        prs = self.github.list_prs_for_branch(repo, branch, state="open")
        pr_numbers = [pr.get("number") for pr in prs if pr.get("number")]
        self._branch_pr_cache[cache_key] = (pr_numbers, datetime.now(UTC).timestamp())

        # Also cache individual PR info
        for pr in prs:
            pr_number = pr.get("number")
            if pr_number:
                author = pr.get("author", {})
                self._pr_cache[(repo, pr_number)] = CachedPRInfo(
                    pr_number=pr_number,
                    author=author.get("login", "") if isinstance(author, dict) else str(author),
                    state=pr.get("state", ""),
                    head_branch=pr.get("headRefName", ""),
                    fetched_at=datetime.now(UTC).timestamp(),
                )

        return pr_numbers

    def check_pr_ownership(self, repo: str, pr_number: int, auth_mode: str = "bot") -> PolicyResult:
        """
        Check if the current identity owns a PR.

        In bot mode: A PR is owned if the author is a jib identity.
        In incognito mode: A PR is owned if the author is the incognito user.

        Args:
            repo: Repository in "owner/repo" format
            pr_number: PR number
            auth_mode: "bot" (default) or "incognito"
        """
        pr_info = self._get_pr_info(repo, pr_number)

        if not pr_info:
            logger.warning(
                "PR not found or inaccessible",
                repo=repo,
                pr_number=pr_number,
            )
            return PolicyResult(
                allowed=False,
                reason=f"PR #{pr_number} not found or inaccessible",
                details={"repo": repo, "pr_number": pr_number},
            )

        # In incognito mode, check if PR is owned by the incognito user
        if auth_mode == "incognito":
            incognito_user = self._get_incognito_user()
            if incognito_user and self._is_incognito_author(pr_info.author, incognito_user):
                logger.debug(
                    "PR ownership verified (incognito mode)",
                    repo=repo,
                    pr_number=pr_number,
                    author=pr_info.author,
                    incognito_user=incognito_user,
                )
                return PolicyResult(
                    allowed=True,
                    reason=f"PR is owned by incognito user ({incognito_user})",
                    details={"author": pr_info.author, "auth_mode": "incognito"},
                )

        if self._is_jib_author(pr_info.author):
            logger.debug(
                "PR ownership verified",
                repo=repo,
                pr_number=pr_number,
                author=pr_info.author,
            )
            return PolicyResult(
                allowed=True,
                reason="PR is owned by jib",
                details={"author": pr_info.author},
            )

        logger.info(
            "PR ownership denied - not owned by jib or incognito user",
            repo=repo,
            pr_number=pr_number,
            author=pr_info.author,
            auth_mode=auth_mode,
        )
        expected = list(JIB_IDENTITIES)
        if auth_mode == "incognito":
            incognito_user = self._get_incognito_user()
            if incognito_user:
                expected.append(incognito_user)
        return PolicyResult(
            allowed=False,
            reason=f"PR #{pr_number} is not owned by the authorized identity (author: {pr_info.author})",
            details={"author": pr_info.author, "expected": expected, "auth_mode": auth_mode},
        )

    def check_pr_comment_allowed(self, repo: str, pr_number: int) -> PolicyResult:
        """
        Check if jib can comment on a PR.

        Jib can comment on ANY PR - this enables collaboration on PRs owned by others.
        """
        pr_info = self._get_pr_info(repo, pr_number)

        if not pr_info:
            logger.warning(
                "PR not found or inaccessible for comment",
                repo=repo,
                pr_number=pr_number,
            )
            return PolicyResult(
                allowed=False,
                reason=f"PR #{pr_number} not found or inaccessible",
                details={"repo": repo, "pr_number": pr_number},
            )

        logger.debug(
            "PR comment allowed",
            repo=repo,
            pr_number=pr_number,
            author=pr_info.author,
        )
        return PolicyResult(
            allowed=True,
            reason="Comments are allowed on any PR",
            details={"pr_number": pr_number, "author": pr_info.author},
        )

    def check_branch_ownership(
        self, repo: str, branch: str, auth_mode: str = "bot"
    ) -> PolicyResult:
        """
        Check if the current identity can push to a branch.

        In bot mode, jib can push to a branch if:
        1. Branch name starts with jib- or jib/ (allows pushing before PR exists), OR
        2. Branch has an open PR authored by jib, OR
        3. Branch has an open PR authored by a trusted user (from GATEWAY_TRUSTED_USERS)

        In incognito mode, the incognito user can push to any branch they own
        (branch has an open PR authored by the incognito user).

        Args:
            repo: Repository in "owner/repo" format
            branch: Branch name
            auth_mode: "bot" (default) or "incognito"
        """
        # In incognito mode, check for incognito user ownership
        if auth_mode == "incognito":
            incognito_user = self._get_incognito_user()
            if incognito_user:
                # Check if branch has an open PR by the incognito user
                pr_numbers = self._get_prs_for_branch(repo, branch)
                for pr_number in pr_numbers:
                    pr_info = self._get_pr_info(repo, pr_number)
                    if pr_info and self._is_incognito_author(pr_info.author, incognito_user):
                        logger.debug(
                            "Branch push allowed (incognito mode)",
                            repo=repo,
                            branch=branch,
                            pr_number=pr_number,
                            author=pr_info.author,
                            incognito_user=incognito_user,
                        )
                        return PolicyResult(
                            allowed=True,
                            reason=f"Branch '{branch}' has open PR #{pr_number} owned by incognito user '{incognito_user}'",
                            details={
                                "branch": branch,
                                "pr_number": pr_number,
                                "author": pr_info.author,
                                "reason": "incognito_pr",
                                "auth_mode": "incognito",
                            },
                        )

                # In incognito mode, also allow pushing to any branch without PR
                # (user is authenticated as themselves, so they own their pushes)
                logger.debug(
                    "Branch push allowed (incognito mode - user authenticated)",
                    repo=repo,
                    branch=branch,
                    incognito_user=incognito_user,
                )
                return PolicyResult(
                    allowed=True,
                    reason=f"Incognito mode: push allowed as user '{incognito_user}'",
                    details={
                        "branch": branch,
                        "reason": "incognito_auth",
                        "auth_mode": "incognito",
                        "incognito_user": incognito_user,
                    },
                )

        # Bot mode: Check 1: Branch prefix
        if self._is_jib_branch(branch):
            logger.debug(
                "Branch ownership verified by prefix",
                repo=repo,
                branch=branch,
            )
            return PolicyResult(
                allowed=True,
                reason=f"Branch '{branch}' is owned by jib (jib-prefixed branch)",
                details={"branch": branch, "reason": "jib_prefix"},
            )

        # Check 2 & 3: Open PR by jib or trusted user
        pr_numbers = self._get_prs_for_branch(repo, branch)

        for pr_number in pr_numbers:
            pr_info = self._get_pr_info(repo, pr_number)
            if not pr_info:
                continue

            # Check if PR is owned by jib
            if self._is_jib_author(pr_info.author):
                logger.debug(
                    "Branch ownership verified by PR",
                    repo=repo,
                    branch=branch,
                    pr_number=pr_number,
                    author=pr_info.author,
                )
                return PolicyResult(
                    allowed=True,
                    reason=f"Branch '{branch}' has open PR #{pr_number} owned by jib",
                    details={
                        "branch": branch,
                        "pr_number": pr_number,
                        "author": pr_info.author,
                        "reason": "jib_pr",
                    },
                )

            # Check if PR is owned by a trusted user
            if self._is_trusted_author(pr_info.author):
                logger.debug(
                    "Branch push allowed - PR owned by trusted user",
                    repo=repo,
                    branch=branch,
                    pr_number=pr_number,
                    author=pr_info.author,
                )
                return PolicyResult(
                    allowed=True,
                    reason=f"Branch '{branch}' has open PR #{pr_number} owned by trusted user '{pr_info.author}'",
                    details={
                        "branch": branch,
                        "pr_number": pr_number,
                        "author": pr_info.author,
                        "reason": "trusted_user_pr",
                    },
                )

        # Not allowed
        logger.info(
            "Branch push denied - not owned by jib or trusted user",
            repo=repo,
            branch=branch,
            open_prs=pr_numbers,
            trusted_users=list(TRUSTED_BRANCH_OWNERS) if TRUSTED_BRANCH_OWNERS else [],
            auth_mode=auth_mode,
        )
        hint = "Use 'jib-' or 'jib/' prefix, or create a PR from this branch first"
        if TRUSTED_BRANCH_OWNERS:
            hint += f". Trusted users: {', '.join(sorted(TRUSTED_BRANCH_OWNERS))}"
        return PolicyResult(
            allowed=False,
            reason=f"Branch '{branch}' is not owned by jib or a trusted user. "
            "Either use a jib-prefixed branch (jib-* or jib/*) or create a PR first.",
            details={
                "branch": branch,
                "open_prs": pr_numbers,
                "hint": hint,
                "auth_mode": auth_mode,
            },
        )

    def check_merge_allowed(self, repo: str, pr_number: int) -> PolicyResult:
        """
        Check if merge is allowed.

        ALWAYS returns False - merging is not supported. Human must merge via GitHub UI.
        """
        logger.info(
            "Merge operation blocked by policy",
            repo=repo,
            pr_number=pr_number,
        )
        return PolicyResult(
            allowed=False,
            reason="Merge operations are not supported. Human must merge via GitHub UI.",
            details={
                "repo": repo,
                "pr_number": pr_number,
                "action": "Use GitHub web UI or 'gh pr merge' from a non-jib environment",
            },
        )


# Global policy engine instance
_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    """Get the global policy engine instance."""
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
    return _engine


def extract_repo_from_remote(remote_url: str) -> str | None:
    """
    Extract owner/repo from a git remote URL.

    Supports:
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo
    - git@github.com:owner/repo.git
    """
    patterns = [
        r"github\.com[/:]([^/]+)/([^/\.]+?)(?:\.git)?$",
    ]

    for pattern in patterns:
        match = re.search(pattern, remote_url)
        if match:
            return f"{match.group(1)}/{match.group(2)}"

    return None


def extract_branch_from_refspec(refspec: str) -> str | None:
    """
    Extract branch name from a git refspec.

    Supports:
    - branch
    - refs/heads/branch
    - local:remote (returns remote)
    - +refs/heads/local:refs/heads/remote (returns remote)
    """
    # Handle empty refspec
    if not refspec:
        return None

    # Handle local:remote format
    if ":" in refspec:
        remote_ref = refspec.split(":")[-1]
    else:
        remote_ref = refspec

    # Strip refs/heads/ prefix
    if remote_ref.startswith("refs/heads/"):
        return remote_ref[len("refs/heads/") :]

    # Strip leading + (force push indicator)
    if remote_ref.startswith("+"):
        remote_ref = remote_ref[1:]

    return remote_ref
