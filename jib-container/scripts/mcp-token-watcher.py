#!/usr/bin/env python3
"""
MCP Token Watcher - Monitor for GitHub token changes and refresh MCP configuration.

This script watches the shared GitHub token file and reconfigures the GitHub MCP
server when the token changes. This ensures the MCP server always uses a valid token.

Usage:
    # Run once (check and update if needed)
    mcp-token-watcher.py --once

    # Run as daemon (continuous monitoring)
    mcp-token-watcher.py

    # Force reconfiguration
    mcp-token-watcher.py --force

The watcher can be:
1. Run periodically via cron/systemd timer
2. Run as a background daemon
3. Called manually when token issues occur
"""

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


# Add shared directory to path for jib_logging
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from jib_logging import get_logger


# Configuration
TOKEN_FILE = Path.home() / "sharing" / ".github-token"
STATE_FILE = Path.home() / ".claude" / ".mcp-token-state"
CHECK_INTERVAL_SECONDS = 60  # How often to check for changes in daemon mode

# Initialize logger
logger = get_logger("mcp-token-watcher")


def read_token_file() -> dict | None:
    """Read and parse the token file."""
    if not TOKEN_FILE.exists():
        return None

    try:
        return json.loads(TOKEN_FILE.read_text())
    except Exception as e:
        logger.warning("Failed to read token file", error=str(e))
        return None


def get_token_hash(token_data: dict | None) -> str:
    """Get a hash of the token for change detection."""
    if not token_data or "token" not in token_data:
        return ""
    return hashlib.sha256(token_data["token"].encode()).hexdigest()[:16]


def read_state() -> dict:
    """Read the last known state."""
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def write_state(state: dict) -> None:
    """Write the current state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def reconfigure_mcp(token: str) -> bool:
    """Reconfigure the GitHub MCP server with a new token."""
    logger.info("Reconfiguring GitHub MCP server...")

    # Remove existing MCP config (ignore errors if it doesn't exist)
    with contextlib.suppress(Exception):
        subprocess.run(
            ["claude", "mcp", "remove", "github", "-s", "user"],
            check=False,
            capture_output=True,
            timeout=30,
        )

    # Add new MCP config
    try:
        result = subprocess.run(
            [
                "claude",
                "mcp",
                "add",
                "--transport",
                "http",
                "--scope",
                "user",
                "github",
                "https://api.githubcopilot.com/mcp/",
                "--header",
                f"Authorization: Bearer {token}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.info("GitHub MCP server reconfigured successfully")
            return True
        else:
            logger.error("MCP add failed", stderr=result.stderr)
            return False

    except subprocess.TimeoutExpired:
        logger.error("MCP reconfiguration timed out")
        return False
    except Exception as e:
        logger.error("MCP reconfiguration error", error=str(e))
        return False


def check_and_update(force: bool = False) -> bool:
    """
    Check if token has changed and update MCP if needed.

    Returns True if MCP was reconfigured.
    """
    token_data = read_token_file()
    if not token_data:
        logger.debug("No token file found")
        return False

    token = token_data.get("token")
    if not token:
        logger.warning("Token file exists but contains no token")
        return False

    # Check if token has changed
    current_hash = get_token_hash(token_data)
    state = read_state()
    last_hash = state.get("token_hash", "")

    if current_hash == last_hash and not force:
        logger.debug("Token unchanged, no update needed")
        return False

    logger.info("Token changed", old_hash=last_hash[:8] + "...", new_hash=current_hash[:8] + "...")

    # Reconfigure MCP
    if reconfigure_mcp(token):
        # Update state
        write_state(
            {
                "token_hash": current_hash,
                "updated_at": token_data.get("generated_at"),
                "expires_at": token_data.get("expires_at"),
            }
        )
        return True

    return False


def run_daemon(interval: int = CHECK_INTERVAL_SECONDS) -> None:
    """Run as a daemon, continuously monitoring for token changes."""
    logger.info("Starting MCP Token Watcher daemon")
    logger.info("Monitoring token file", path=str(TOKEN_FILE))
    logger.info("Check interval configured", seconds=interval)

    # Initial check
    check_and_update()

    while True:
        try:
            time.sleep(interval)
            check_and_update()
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
            break
        except Exception as e:
            logger.error("Error during check cycle", error=str(e))


def main():
    parser = argparse.ArgumentParser(
        description="Monitor GitHub token changes and refresh MCP configuration"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run once and exit (check and update if needed)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force MCP reconfiguration even if token hasn't changed",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--interval",
        type=int,
        default=CHECK_INTERVAL_SECONDS,
        help=f"Check interval in seconds for daemon mode (default: {CHECK_INTERVAL_SECONDS})",
    )

    args = parser.parse_args()

    # Configure logging level based on verbose flag
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")

    if args.once or args.force:
        updated = check_and_update(force=args.force)
        sys.exit(0 if updated or not args.force else 1)
    else:
        run_daemon(interval=args.interval)


if __name__ == "__main__":
    main()
