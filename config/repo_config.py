#!/usr/bin/env python3
"""
Repository Configuration Module

Provides programmatic access to repository configuration defined in repositories.yaml.
This is the single source of truth for which repos jib has access to.

Usage:
    from config.repo_config import (
        get_github_username,
        get_writable_repos,
        is_writable_repo,
        get_default_reviewer
    )

    # Get configured GitHub username
    username = get_github_username()

    # Get all writable repos
    repos = get_writable_repos()

    # Check if a specific repo is writable
    if is_writable_repo(f"{username}/james-in-a-box"):
        # Can push changes, create PRs, etc.
        pass

    # Get default reviewer for PRs
    reviewer = get_default_reviewer()
"""

import os
from pathlib import Path

import yaml


def _get_config_path() -> Path:
    """Get the path to repositories.yaml config file."""
    # Try relative to this file first (when running from repo)
    config_dir = Path(__file__).parent
    config_file = config_dir / "repositories.yaml"

    if config_file.exists():
        return config_file

    # Try relative to ~/khan/james-in-a-box (when running from container)
    home_config = Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml"
    if home_config.exists():
        return home_config

    # Try environment variable
    env_path = os.environ.get("JIB_REPO_CONFIG")
    if env_path:
        env_config = Path(env_path)
        if env_config.exists():
            return env_config

    raise FileNotFoundError(
        f"Could not find repositories.yaml. Checked:\n"
        f"  - {config_file}\n"
        f"  - {home_config}\n"
        f"  - JIB_REPO_CONFIG env var"
    )


def _load_config() -> dict:
    """Load and return the repository configuration."""
    config_path = _get_config_path()
    with config_path.open() as f:
        return yaml.safe_load(f)


def get_github_username() -> str:
    """
    Get the configured GitHub username.

    This is used to construct repo names and as the default reviewer.
    Set via setup.sh or directly in repositories.yaml.

    Returns:
        GitHub username string

    Raises:
        ValueError: If github_username is not configured
    """
    config = _load_config()
    username = config.get("github_username")
    if not username:
        raise ValueError(
            "github_username not configured in repositories.yaml. "
            "Run setup.sh to configure, or add 'github_username: your-username' to the config."
        )
    return username


def get_writable_repos() -> list[str]:
    """
    Get list of repositories where jib has write access.

    These are repos where jib can:
    - Respond to PR comments
    - Push code changes
    - Create PRs
    - Implement fixes for failed CI checks

    Returns:
        List of repo strings in "owner/repo" format
    """
    config = _load_config()
    return config.get("writable_repos", [])


def get_readable_repos() -> list[str]:
    """
    Get list of repositories where jib has read-only access.

    These are repos where jib can:
    - Sync and analyze PRs, comments, and check failures
    - Send Slack notifications with feedback/analysis

    jib CANNOT:
    - Push code, create PRs, post comments
    - Make any modifications to these repos

    Read-only repos only require a GitHub PAT with read access.

    Returns:
        List of repo strings in "owner/repo" format
    """
    config = _load_config()
    return config.get("readable_repos", [])


def is_writable_repo(repo: str) -> bool:
    """
    Check if a repository is in the writable repos list.

    Args:
        repo: Repository in "owner/repo" format

    Returns:
        True if jib has write access to this repo
    """
    writable = get_writable_repos()
    # Normalize comparison (case-insensitive)
    repo_lower = repo.lower()
    return any(r.lower() == repo_lower for r in writable)


def is_readable_repo(repo: str) -> bool:
    """
    Check if a repository is in the readable repos list.

    Args:
        repo: Repository in "owner/repo" format

    Returns:
        True if jib has read-only access to this repo
    """
    readable = get_readable_repos()
    # Normalize comparison (case-insensitive)
    repo_lower = repo.lower()
    return any(r.lower() == repo_lower for r in readable)


def get_repo_access_level(repo: str) -> str:
    """
    Get the access level for a repository.

    Args:
        repo: Repository in "owner/repo" format

    Returns:
        One of: "writable", "readable", or "none"
    """
    if is_writable_repo(repo):
        return "writable"
    if is_readable_repo(repo):
        return "readable"
    return "none"


def get_default_reviewer() -> str:
    """
    Get the default reviewer for PRs created by jib.

    Falls back to github_username if default_reviewer is not explicitly set.

    Returns:
        GitHub username of default reviewer
    """
    config = _load_config()
    reviewer = config.get("default_reviewer")
    if reviewer:
        return reviewer
    # Fall back to github_username
    return get_github_username()


def get_sync_config() -> dict:
    """
    Get GitHub sync configuration.

    Returns:
        Dictionary with sync settings:
        - sync_all_prs: bool - whether to sync all PRs or just user's
        - sync_interval_minutes: int - sync interval in minutes
    """
    config = _load_config()
    return config.get("github_sync", {"sync_all_prs": True, "sync_interval_minutes": 5})


def get_repos_for_sync() -> list[str]:
    """
    Get list of repositories to sync from GitHub.

    Returns both writable and readable repos, as both need
    to be monitored for activity.

    Returns:
        List of repo strings in "owner/repo" format
    """
    writable = get_writable_repos()
    readable = get_readable_repos()
    # Combine and deduplicate, preserving order (writable repos first)
    # Note: If a repo appears in both lists, it's treated as writable
    all_repos = list(dict.fromkeys(writable + readable))
    return all_repos


# Convenience function for shell scripts
def main():
    """CLI interface for shell scripts to query config."""
    import argparse

    parser = argparse.ArgumentParser(description="Query repository configuration")
    parser.add_argument(
        "--github-username", action="store_true", help="Print configured GitHub username"
    )
    parser.add_argument(
        "--list-writable", action="store_true", help="List all writable repos (one per line)"
    )
    parser.add_argument(
        "--list-readable", action="store_true", help="List all readable repos (one per line)"
    )
    parser.add_argument(
        "--list-all", action="store_true", help="List all repos for sync (one per line)"
    )
    parser.add_argument(
        "--check-writable",
        metavar="REPO",
        help="Check if REPO is writable (exit 0 if yes, 1 if no)",
    )
    parser.add_argument(
        "--check-readable",
        metavar="REPO",
        help="Check if REPO is readable (exit 0 if yes, 1 if no)",
    )
    parser.add_argument(
        "--access-level",
        metavar="REPO",
        help="Print access level for REPO (writable, readable, or none)",
    )
    parser.add_argument(
        "--default-reviewer", action="store_true", help="Print default reviewer username"
    )
    parser.add_argument(
        "--sync-all-prs", action="store_true", help="Print 'true' if sync_all_prs is enabled"
    )

    args = parser.parse_args()

    if args.github_username:
        print(get_github_username())
    elif args.list_writable:
        for repo in get_writable_repos():
            print(repo)
    elif args.list_readable:
        for repo in get_readable_repos():
            print(repo)
    elif args.list_all:
        for repo in get_repos_for_sync():
            print(repo)
    elif args.check_writable:
        import sys

        sys.exit(0 if is_writable_repo(args.check_writable) else 1)
    elif args.check_readable:
        import sys

        sys.exit(0 if is_readable_repo(args.check_readable) else 1)
    elif args.access_level:
        print(get_repo_access_level(args.access_level))
    elif args.default_reviewer:
        print(get_default_reviewer())
    elif args.sync_all_prs:
        config = get_sync_config()
        print("true" if config.get("sync_all_prs") else "false")
    else:
        # Default: print summary
        print("Repository Configuration")
        print("=" * 40)
        print(f"Config file: {_get_config_path()}")
        print(f"\nGitHub username: {get_github_username()}")
        print(f"\nWritable repos ({len(get_writable_repos())}):")
        for repo in get_writable_repos():
            print(f"  - {repo}")
        print(f"\nReadable repos ({len(get_readable_repos())}):")
        for repo in get_readable_repos():
            print(f"  - {repo}")
        print(f"\nDefault reviewer: {get_default_reviewer()}")
        sync = get_sync_config()
        print(f"Sync all PRs: {sync.get('sync_all_prs')}")
        print(f"Sync interval: {sync.get('sync_interval_minutes')} minutes")


if __name__ == "__main__":
    main()
