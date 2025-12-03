"""
Git utilities for host-services.

Shared functions for working with git repositories from host-side services.
"""

import re
import subprocess
from pathlib import Path


def get_repo_name_from_remote(repo_path: Path | None = None) -> str | None:
    """Get the full repo name (owner/repo) from git remote.

    Parses the git remote URL to extract the owner/repo string.
    Handles both HTTPS and SSH URL formats:
    - https://github.com/owner/repo.git
    - git@github.com:owner/repo.git

    Args:
        repo_path: Path to the repository root. If None, uses current directory.

    Returns:
        The repo name in "owner/repo" format, or None if not found.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        # Parse repo name from URL (https://github.com/owner/repo.git or git@github.com:owner/repo.git)
        match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
        if match:
            return match.group(1)
    except subprocess.CalledProcessError:
        pass
    return None
