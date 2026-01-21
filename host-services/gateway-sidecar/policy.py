"""
Policy Engine - Ownership and access control checks.

Enforces policies for git/gh operations:
- Branch ownership: jib can only push to branches it owns
- PR ownership: jib can only modify PRs it created
- Merge blocked: No merge operations allowed (human must merge)
"""

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
JIB_IDENTITIES = frozenset(
    {
        "jib",
        "jib[bot]",
        "app/jib",
        # GitHub App format: apps/app-name
        "apps/jib",
    }
)

# Branch prefixes that indicate jib ownership
JIB_BRANCH_PREFIXES = ("jib-", "jib/")


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

    def check_pr_ownership(self, repo: str, pr_number: int) -> PolicyResult:
        """
        Check if jib owns a PR.

        A PR is owned by jib if the author is a jib identity.
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
            "PR ownership denied - not owned by jib",
            repo=repo,
            pr_number=pr_number,
            author=pr_info.author,
        )
        return PolicyResult(
            allowed=False,
            reason=f"PR #{pr_number} is not owned by jib (author: {pr_info.author})",
            details={"author": pr_info.author, "expected": list(JIB_IDENTITIES)},
        )

    def check_branch_ownership(self, repo: str, branch: str) -> PolicyResult:
        """
        Check if jib owns a branch.

        A branch is owned by jib if:
        1. Branch name starts with jib- or jib/ (allows pushing before PR exists), OR
        2. Branch has an open PR authored by jib
        """
        # Check 1: Branch prefix
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

        # Check 2: Open PR by jib
        pr_numbers = self._get_prs_for_branch(repo, branch)

        for pr_number in pr_numbers:
            pr_info = self._get_pr_info(repo, pr_number)
            if pr_info and self._is_jib_author(pr_info.author):
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

        # Not owned by jib
        logger.info(
            "Branch ownership denied - not owned by jib",
            repo=repo,
            branch=branch,
            open_prs=pr_numbers,
        )
        return PolicyResult(
            allowed=False,
            reason=f"Branch '{branch}' is not owned by jib. "
            "Either use a jib-prefixed branch (jib-* or jib/*) or create a PR first.",
            details={
                "branch": branch,
                "open_prs": pr_numbers,
                "hint": "Use 'jib-' or 'jib/' prefix, or create a PR from this branch first",
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
