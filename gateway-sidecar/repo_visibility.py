"""
Repository visibility checking with caching.

Provides GitHub API integration to check whether repositories are public,
private, or internal. Used by Private Repo Mode to restrict operations
to private repositories only.

Security Properties:
- Fail-closed: If visibility cannot be determined, assume public (deny access)
- Two-tier caching: Short TTL for reads, no caching for writes
- Thread-safe: Uses locks for cache access
"""

import os
import sys
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import requests


# Add shared directory to path for jib_logging
_shared_path = Path(__file__).parent.parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


logger = get_logger("gateway-sidecar.repo-visibility")

# GitHub API configuration
GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"

# Default cache TTLs (in seconds)
# Read operations use a short cache, write operations always verify
DEFAULT_VISIBILITY_CACHE_TTL_READ = 60
DEFAULT_VISIBILITY_CACHE_TTL_WRITE = 0

# Type alias for visibility values
VisibilityType = Literal["public", "private", "internal"]


@dataclass
class CachedVisibility:
    """Cached repository visibility with TTL."""

    owner: str
    repo: str
    visibility: VisibilityType
    fetched_at: float

    def is_stale(self, ttl: int) -> bool:
        """Check if cache entry is stale based on TTL."""
        if ttl <= 0:
            return True
        return (datetime.now(UTC).timestamp() - self.fetched_at) > ttl


class RepoVisibilityChecker:
    """
    Repository visibility checker with caching.

    Uses GitHub API to check repository visibility and caches results
    to reduce API calls. Supports two-tier caching with different TTLs
    for read and write operations.
    """

    def __init__(
        self,
        token_file: Path | None = None,
        read_ttl: int | None = None,
        write_ttl: int | None = None,
    ):
        """
        Initialize the visibility checker.

        Args:
            token_file: Path to the GitHub token file (for API calls)
            read_ttl: Cache TTL for read operations (seconds)
            write_ttl: Cache TTL for write operations (seconds, 0 = no cache)
        """
        # Token file for API authentication
        self._token_file = token_file or self._default_token_file()

        # Cache TTLs from environment or defaults
        self._read_ttl = read_ttl if read_ttl is not None else self._get_read_ttl()
        self._write_ttl = write_ttl if write_ttl is not None else self._get_write_ttl()

        # Cache: (owner, repo) -> CachedVisibility
        self._cache: dict[tuple[str, str], CachedVisibility] = {}
        self._cache_lock = threading.Lock()

    @staticmethod
    def _default_token_file() -> Path:
        """Get the default token file path."""
        token_file = Path("/secrets/.github-token")
        if not token_file.exists():
            token_file = Path.home() / ".jib-gateway" / ".github-token"
        return token_file

    @staticmethod
    def _get_read_ttl() -> int:
        """Get read cache TTL from environment or default."""
        return int(os.environ.get("VISIBILITY_CACHE_TTL_READ", DEFAULT_VISIBILITY_CACHE_TTL_READ))

    @staticmethod
    def _get_write_ttl() -> int:
        """Get write cache TTL from environment or default."""
        return int(os.environ.get("VISIBILITY_CACHE_TTL_WRITE", DEFAULT_VISIBILITY_CACHE_TTL_WRITE))

    def _get_token(self) -> str | None:
        """
        Get GitHub token for API calls.

        Returns:
            Token string or None if not available
        """
        # Try environment variable first
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if token:
            return token

        # Try token file (JSON format from github-token-refresher)
        if self._token_file.exists():
            try:
                import json

                data = json.loads(self._token_file.read_text())
                return data.get("token", "")
            except (json.JSONDecodeError, KeyError, OSError):
                pass

        return None

    def _fetch_visibility(self, owner: str, repo: str) -> VisibilityType | None:
        """
        Fetch repository visibility from GitHub API.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            'public', 'private', 'internal', or None on error
        """
        token = self._get_token()
        if not token:
            logger.warning("No GitHub token available for visibility check")
            return None

        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                visibility = data.get("visibility", "public")
                logger.debug(
                    "Fetched repository visibility",
                    owner=owner,
                    repo=repo,
                    visibility=visibility,
                )
                return visibility

            elif response.status_code == 404:
                # Repository not found - could be:
                # 1. Actually doesn't exist
                # 2. Private and token doesn't have access
                # FAIL CLOSED: Treat as public (deny access in private mode)
                logger.warning(
                    "Repository not found or inaccessible",
                    owner=owner,
                    repo=repo,
                    status_code=response.status_code,
                )
                return None

            elif response.status_code == 403:
                # Rate limited or forbidden
                logger.warning(
                    "GitHub API forbidden/rate-limited",
                    owner=owner,
                    repo=repo,
                    status_code=response.status_code,
                )
                return None

            else:
                logger.warning(
                    "GitHub API unexpected status",
                    owner=owner,
                    repo=repo,
                    status_code=response.status_code,
                )
                return None

        except requests.Timeout:
            logger.warning(
                "GitHub API timeout",
                owner=owner,
                repo=repo,
            )
            return None
        except requests.RequestException as e:
            logger.warning(
                "GitHub API request failed",
                owner=owner,
                repo=repo,
                error=str(e),
            )
            return None

    def get_visibility(
        self,
        owner: str,
        repo: str,
        for_write: bool = False,
    ) -> VisibilityType | None:
        """
        Get repository visibility with tiered caching.

        Args:
            owner: Repository owner
            repo: Repository name
            for_write: If True, use write TTL (stricter caching)

        Returns:
            'public', 'private', 'internal', or None on error
        """
        cache_key = (owner.lower(), repo.lower())
        ttl = self._write_ttl if for_write else self._read_ttl

        # Check cache
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and not cached.is_stale(ttl):
                logger.debug(
                    "Cache hit for visibility",
                    owner=owner,
                    repo=repo,
                    visibility=cached.visibility,
                    for_write=for_write,
                )
                return cached.visibility

        # Fetch from API
        visibility = self._fetch_visibility(owner, repo)

        # Cache the result if we got a valid response
        if visibility:
            with self._cache_lock:
                self._cache[cache_key] = CachedVisibility(
                    owner=owner.lower(),
                    repo=repo.lower(),
                    visibility=visibility,
                    fetched_at=datetime.now(UTC).timestamp(),
                )

        return visibility

    def is_private(
        self,
        owner: str,
        repo: str,
        for_write: bool = False,
    ) -> bool | None:
        """
        Check if a repository is private (or internal).

        Args:
            owner: Repository owner
            repo: Repository name
            for_write: If True, use write TTL (stricter caching)

        Returns:
            True if private/internal, False if public, None on error
        """
        visibility = self.get_visibility(owner, repo, for_write=for_write)
        if visibility is None:
            return None
        return visibility in ("private", "internal")

    def clear_cache(self) -> None:
        """Clear the visibility cache."""
        with self._cache_lock:
            self._cache.clear()

    def invalidate(self, owner: str, repo: str) -> None:
        """
        Invalidate cache entry for a specific repository.

        Args:
            owner: Repository owner
            repo: Repository name
        """
        cache_key = (owner.lower(), repo.lower())
        with self._cache_lock:
            self._cache.pop(cache_key, None)


# Global visibility checker instance
_checker: RepoVisibilityChecker | None = None


def get_visibility_checker() -> RepoVisibilityChecker:
    """Get the global visibility checker instance."""
    global _checker
    if _checker is None:
        _checker = RepoVisibilityChecker()
    return _checker


def get_repo_visibility(
    owner: str,
    repo: str,
    for_write: bool = False,
) -> VisibilityType | None:
    """
    Get repository visibility (convenience function).

    Args:
        owner: Repository owner
        repo: Repository name
        for_write: If True, use stricter caching for write operations

    Returns:
        'public', 'private', 'internal', or None on error
    """
    return get_visibility_checker().get_visibility(owner, repo, for_write=for_write)


def is_repo_private(
    owner: str,
    repo: str,
    for_write: bool = False,
) -> bool | None:
    """
    Check if a repository is private (convenience function).

    Args:
        owner: Repository owner
        repo: Repository name
        for_write: If True, use stricter caching for write operations

    Returns:
        True if private/internal, False if public, None on error
    """
    return get_visibility_checker().is_private(owner, repo, for_write=for_write)
