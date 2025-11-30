#!/usr/bin/env python3
"""
GitHub Authentication Utilities

Provides utilities for refreshing GitHub tokens from the shared token file.
This ensures long-running containers (like Slack processors) stay authenticated
even when tokens expire.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Add jib_logging to path if not already there
_shared_dir = Path(__file__).parent
if str(_shared_dir) not in sys.path:
    sys.path.insert(0, str(_shared_dir))

from jib_logging import get_logger

logger = get_logger("github_auth")

# Token file location
TOKEN_FILE = Path.home() / "sharing" / ".github-token"


def read_current_token() -> str | None:
    """
    Read the current GitHub token from the shared token file.

    Returns:
        The current token string, or None if file doesn't exist or is invalid
    """
    if not TOKEN_FILE.exists():
        logger.debug("Token file not found", path=str(TOKEN_FILE))
        return None

    try:
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        token = data.get("token")
        if not token:
            logger.warning("Token file exists but contains no token")
            return None
        logger.debug("Token read from file", length=len(token))
        return token
    except Exception as e:
        logger.warning("Failed to read token file", error=str(e))
        return None


def refresh_environment_token() -> bool:
    """
    Refresh the GITHUB_TOKEN environment variable from the shared token file.

    This is needed for gh CLI authentication, which reads from GITHUB_TOKEN.
    Note: This only updates the environment for the current process and its children.

    Returns:
        True if token was refreshed successfully, False otherwise
    """
    token = read_current_token()
    if not token:
        logger.warning("Cannot refresh environment token - no valid token found")
        return False

    old_token = os.environ.get("GITHUB_TOKEN", "")
    if old_token == token:
        logger.debug("Environment token already up to date")
        return True

    os.environ["GITHUB_TOKEN"] = token
    logger.info("Refreshed GITHUB_TOKEN environment variable")
    return True


def refresh_mcp_config(force: bool = False) -> bool:
    """
    Refresh the GitHub MCP server configuration with the current token.

    Uses the mcp-token-watcher script to check for token changes and
    reconfigure MCP if needed.

    Args:
        force: If True, reconfigure even if token hasn't changed

    Returns:
        True if MCP was refreshed successfully, False otherwise
    """
    watcher_script = (
        Path.home() / "khan" / "james-in-a-box" / "jib-container" / "scripts" /
        "mcp-token-watcher.py"
    )

    if not watcher_script.exists():
        logger.warning("MCP token watcher script not found", path=str(watcher_script))
        return False

    try:
        cmd = ["python3", str(watcher_script), "--once"]
        if force:
            cmd.append("--force")

        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.info("MCP configuration refreshed successfully")
            return True
        else:
            logger.warning("MCP refresh had no changes or failed",
                         returncode=result.returncode)
            return False

    except subprocess.TimeoutExpired:
        logger.error("MCP refresh timed out")
        return False
    except Exception as e:
        logger.error("MCP refresh failed", error=str(e))
        return False


def refresh_all_auth(force_mcp: bool = False) -> tuple[bool, bool]:
    """
    Refresh all GitHub authentication mechanisms.

    Refreshes both:
    1. GITHUB_TOKEN environment variable (for gh CLI)
    2. GitHub MCP server configuration

    Args:
        force_mcp: If True, force MCP reconfiguration even if token unchanged

    Returns:
        Tuple of (env_refreshed, mcp_refreshed)
    """
    logger.info("Refreshing GitHub authentication...")

    env_success = refresh_environment_token()
    mcp_success = refresh_mcp_config(force=force_mcp)

    if env_success and mcp_success:
        logger.info("All GitHub authentication refreshed successfully")
    elif env_success:
        logger.warning("Environment token refreshed but MCP refresh failed/skipped")
    elif mcp_success:
        logger.warning("MCP refreshed but environment token refresh failed")
    else:
        logger.error("Failed to refresh GitHub authentication")

    return env_success, mcp_success


def start_token_watcher_daemon(interval: int = 60) -> subprocess.Popen | None:
    """
    Start the MCP token watcher as a background daemon process.

    This is useful for long-running containers to automatically refresh
    MCP configuration when tokens are rotated by the host service.

    Args:
        interval: Check interval in seconds (default: 60)

    Returns:
        The Popen process object if started successfully, None otherwise
    """
    watcher_script = (
        Path.home() / "khan" / "james-in-a-box" / "jib-container" / "scripts" /
        "mcp-token-watcher.py"
    )

    if not watcher_script.exists():
        logger.warning("Cannot start token watcher - script not found",
                      path=str(watcher_script))
        return None

    try:
        # Start as background daemon
        proc = subprocess.Popen(
            ["python3", str(watcher_script), "--interval", str(interval)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True  # Detach from parent process
        )
        logger.info("Started MCP token watcher daemon",
                   pid=proc.pid, interval=interval)
        return proc
    except Exception as e:
        logger.error("Failed to start token watcher daemon", error=str(e))
        return None
