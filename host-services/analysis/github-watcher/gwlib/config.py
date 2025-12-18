#!/usr/bin/env python3
"""Configuration loading for GitHub watcher services."""

from pathlib import Path

import yaml

from jib_logging import get_logger

logger = get_logger("github-config")


def load_config() -> dict:
    """Load repository configuration.

    Returns:
        Config dict with writable_repos, readable_repos, github_username, bot_username
    """
    config_paths = [
        Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml",
        Path(__file__).parent.parent.parent.parent.parent / "config" / "repositories.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
                config.setdefault("readable_repos", [])
                return config

    return {"writable_repos": [], "readable_repos": [], "github_username": "jib", "bot_username": "jib"}


def should_disable_auto_fix(repo: str) -> bool:
    """Check if auto-fix is disabled for a repo."""
    # Import here to avoid circular dependency
    from config.repo_config import should_disable_auto_fix as _should_disable_auto_fix
    return _should_disable_auto_fix(repo)


def should_restrict_to_configured_users(repo: str) -> bool:
    """Check if repo is restricted to configured users only."""
    from config.repo_config import should_restrict_to_configured_users as _should_restrict
    return _should_restrict(repo)
