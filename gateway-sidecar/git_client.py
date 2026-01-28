"""
Git Client - Wraps git CLI with validation and credential management.

Provides:
- Path validation (prevent traversal attacks)
- Argument validation with per-operation allowlists
- Credential helper management for authenticated git operations
"""

import contextlib
import os
import sys
import tempfile
from pathlib import Path


# Add shared directory to path for jib_logging
_shared_path = Path(__file__).parent.parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


# Import repo_config for auth mode support
_config_path = Path(__file__).parent.parent / "config"
if _config_path.exists() and str(_config_path) not in sys.path:
    sys.path.insert(0, str(_config_path))
from repo_config import get_auth_mode


# Import using try/except for both module and standalone script mode
try:
    from .github_client import get_github_client
except ImportError:
    from github_client import get_github_client


logger = get_logger("gateway-sidecar.git-client")

GIT_CLI = "/usr/bin/git"


def git_cmd(*args: str) -> list[str]:
    """
    Build a git command with safe.directory=* to allow operating on worktree paths.

    The gateway runs on the host but operates on paths inside jib container worktrees
    (e.g., ~/.jib-worktrees/<container-id>/repo). Git's ownership check would reject
    these as "dubious ownership" without safe.directory=*.
    """
    return [GIT_CLI, "-c", "safe.directory=*", *args]


def ssh_url_to_https(url: str) -> str:
    """
    Convert SSH git URL to HTTPS URL.

    The gateway doesn't have SSH keys - it uses HTTPS with token auth.
    This converts SSH URLs so pushes work via HTTPS authentication.

    Supports:
    - git@github.com:owner/repo.git -> https://github.com/owner/repo.git
    - ssh://git@github.com/owner/repo.git -> https://github.com/owner/repo.git

    Returns the original URL if it's already HTTPS or doesn't match SSH patterns.
    """
    import re

    # Pattern 1: git@github.com:owner/repo.git
    match = re.match(r"^git@github\.com:(.+?)(?:\.git)?$", url)
    if match:
        return f"https://github.com/{match.group(1)}.git"

    # Pattern 2: ssh://git@github.com/owner/repo.git
    match = re.match(r"^ssh://git@github\.com/(.+?)(?:\.git)?$", url)
    if match:
        return f"https://github.com/{match.group(1)}.git"

    # Already HTTPS or unknown format - return as-is
    return url


def is_ssh_url(url: str) -> bool:
    """Check if a URL is an SSH git URL."""
    return url.startswith(("git@", "ssh://"))


# =============================================================================
# Path Validation
# =============================================================================

# Allowed base paths for repo_path validation
# These are the only directories where git operations are permitted
ALLOWED_REPO_PATHS = [
    "/home/jib/repos/",
    "/home/jib/.jib-worktrees/",
    "/repos/",  # Legacy path
]


def validate_repo_path(path: str) -> tuple[bool, str]:
    """
    Validate that repo_path is within allowed directories.

    Prevents path traversal attacks by ensuring the resolved path
    starts with an allowed prefix.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "repo_path is required"

    try:
        # Resolve to absolute path, following symlinks
        real_path = os.path.realpath(path)

        # Check if path is within allowed directories
        for allowed in ALLOWED_REPO_PATHS:
            if real_path.startswith(allowed):
                return True, ""

        return False, f"repo_path must be within allowed directories: {ALLOWED_REPO_PATHS}"
    except Exception as e:
        return False, f"Invalid repo_path: {e}"


# =============================================================================
# Argument Validation
# =============================================================================

# Explicitly dangerous git flags - never allowed regardless of operation
# These could be used for command injection or config override attacks
BLOCKED_GIT_FLAGS = [
    "--upload-pack",  # Can specify arbitrary command
    "--exec",  # Can specify arbitrary command
    "-u",  # Short for --upload-pack (blocked here, but -u for --set-upstream is normalized)
    "-c",  # Config override (could disable security)
    "--config",  # Config override
    "--receive-pack",  # Arbitrary command execution
]

# Per-operation allowlist of flags that are permitted
# This is more secure than a blocklist - unknown flags are rejected by default
GIT_ALLOWED_COMMANDS = {
    "fetch": {
        "allowed_flags": [
            "--all",
            "--tags",
            "--prune",
            "--depth",
            "--shallow-since",
            "--shallow-exclude",
            "--jobs",
            "--no-tags",
            "--force",
            "--verbose",
            "--quiet",
            "--dry-run",
            "--recurse-submodules",
            "--progress",
            "--no-progress",
        ],
    },
    "ls-remote": {
        "allowed_flags": [
            "--heads",
            "--tags",
            "--refs",
            "--quiet",
            "--exit-code",
            "--get-url",
            "--sort",
            "--symref",
        ],
    },
    "push": {
        "allowed_flags": [
            "--force",
            "--force-with-lease",
            "--tags",
            "--delete",
            "--set-upstream",
            "--verbose",
            "--quiet",
            "--dry-run",
            "--no-verify",
        ],
    },
}

# Flag normalization: map short flags to long form for consistent validation
FLAG_NORMALIZATION = {
    # fetch/ls-remote
    "-a": "--all",
    "-t": "--tags",
    "-p": "--prune",
    "-v": "--verbose",
    "-q": "--quiet",
    "-j": "--jobs",
    # push
    "-f": "--force",
    "-d": "--delete",
    "-u": "--set-upstream",
    "-n": "--dry-run",
}


def normalize_flag(flag: str) -> str:
    """
    Normalize short flags to long form for consistent validation.

    Args:
        flag: The flag to normalize (e.g., "-a" or "--all")

    Returns:
        The normalized long-form flag, or original if not found
    """
    # Handle -X=value format
    if "=" in flag:
        base, value = flag.split("=", 1)
        normalized = FLAG_NORMALIZATION.get(base, base)
        return f"{normalized}={value}"
    return FLAG_NORMALIZATION.get(flag, flag)


def validate_git_args(operation: str, args: list[str]) -> tuple[bool, str, list[str]]:
    """
    Validate git arguments against per-operation allowlist.

    Uses explicit allowlists instead of blocklists for better security.
    Unknown flags are rejected by default.

    Args:
        operation: The git operation (fetch, ls-remote, push)
        args: List of arguments to validate

    Returns:
        Tuple of (is_valid, error_message, normalized_args)
    """
    if not args:
        return True, "", []

    # Get operation config
    op_config = GIT_ALLOWED_COMMANDS.get(operation)
    if not op_config:
        return False, f"Unknown operation: {operation}", []

    allowed_flags = set(op_config["allowed_flags"])
    normalized = []

    i = 0
    while i < len(args):
        arg = args[i]

        # Ensure arg is a string (not a nested structure)
        if not isinstance(arg, str):
            return False, f"Invalid argument type: {type(arg)}", []

        # Skip non-flag arguments (refs, branch names, etc.)
        if not arg.startswith("-"):
            normalized.append(arg)
            i += 1
            continue

        # Normalize short flags to long form
        normalized_flag = normalize_flag(arg)

        # Check for explicitly blocked flags first
        flag_base = normalized_flag.split("=")[0] if "=" in normalized_flag else normalized_flag
        for blocked in BLOCKED_GIT_FLAGS:
            if flag_base.lower() == blocked.lower():
                return False, f"Flag '{arg}' is not allowed for git {operation}", []

        # Check against allowlist
        if flag_base not in allowed_flags:
            return (
                False,
                f"Flag '{arg}' is not allowed for git {operation}. "
                f"Allowed flags: {', '.join(sorted(allowed_flags))}",
                [],
            )

        normalized.append(normalized_flag)
        i += 1

    return True, "", normalized


# =============================================================================
# Credential Helper Management
# =============================================================================

# Credential helper script template for GIT_ASKPASS
_ASKPASS_SCRIPT = """#!/bin/bash
if [[ "$1" == *"Username"* ]]; then
    echo "$GIT_USERNAME"
elif [[ "$1" == *"Password"* ]]; then
    echo "$GIT_PASSWORD"
fi
"""


def create_credential_helper(token_str: str, env: dict) -> tuple[str, dict]:
    """
    Create a temporary credential helper script for git authentication.

    Creates a GIT_ASKPASS script that provides credentials from environment
    variables. The script is written to a temp file with restrictive permissions.

    Args:
        token_str: The GitHub token to use for authentication
        env: The environment dict to update

    Returns:
        Tuple of (credential_helper_path, updated_env)

    Note:
        Caller MUST clean up the credential file using cleanup_credential_helper()
        in a finally block to ensure the token is never left on disk.
    """
    # Update environment with credential info
    env = env.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_USERNAME"] = "x-access-token"
    env["GIT_PASSWORD"] = token_str

    # Create temp file with restrictive permissions BEFORE writing
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="git-askpass-")
    try:
        os.fchmod(fd, 0o700)  # Set permissions on fd before writing
        os.write(fd, _ASKPASS_SCRIPT.encode())
    finally:
        os.close(fd)

    env["GIT_ASKPASS"] = path
    return path, env


def cleanup_credential_helper(path: str | None) -> None:
    """
    Safely clean up a credential helper file.

    Args:
        path: Path to the credential helper file, or None if not created yet
    """
    if path and os.path.exists(path):
        with contextlib.suppress(OSError):
            os.unlink(path)


def get_token_for_repo(repo: str) -> tuple[str | None, str, str]:
    """
    Get the authentication token for a repository.

    Determines the auth mode (bot vs incognito) for the repo and retrieves
    the appropriate token.

    Args:
        repo: Repository in "owner/repo" format

    Returns:
        Tuple of (token_str, auth_mode, error_message)
        - token_str is None if token unavailable (error_message explains why)
        - auth_mode is "bot" or "incognito"
        - error_message is empty string on success
    """
    auth_mode = get_auth_mode(repo)
    github = get_github_client(mode=auth_mode)

    if auth_mode == "incognito":
        token_str = github.get_incognito_token()
        if not token_str:
            return (
                None,
                auth_mode,
                "Incognito token not available. Set GITHUB_INCOGNITO_TOKEN environment variable.",
            )
    else:
        token = github.get_token()
        if not token:
            return None, auth_mode, "GitHub token not available"
        token_str = token.token

    return token_str, auth_mode, ""
