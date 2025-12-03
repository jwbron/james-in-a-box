#!/usr/bin/env python3
"""
GitHub Token Refresher - Automatically refresh GitHub App installation tokens.

GitHub App installation tokens expire after 1 hour. This service runs periodically
(every 45 minutes) to generate a fresh token and write it to a shared file that
running containers can read.

Token Flow:
1. This service generates a fresh token using github-app-token.py
2. Token is written to ~/.jib-sharing/.github-token (JSON with metadata)
3. Containers read from this file instead of relying on stale env vars
4. Git credential helper and MCP server use the refreshed token

Usage:
    github-token-refresher.py [--once] [--verbose]

Options:
    --once      Run once and exit (for testing)
    --verbose   Enable verbose logging
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


# Add shared directory to path for jib_logging
sys.path.insert(0, "/opt/jib-runtime/shared")
from jib_logging import get_logger


# Configuration
CONFIG_DIR = Path.home() / ".config" / "jib"
SHARING_DIR = Path.home() / ".jib-sharing"
TOKEN_FILE = SHARING_DIR / ".github-token"
REFRESH_INTERVAL_SECONDS = 45 * 60  # 45 minutes
TOKEN_VALIDITY_SECONDS = 60 * 60  # 1 hour (GitHub's limit)

# Initialize logger
logger = get_logger("github-token-refresher")


def find_token_script() -> Path | None:
    """Find the github-app-token.py script."""
    # Try relative to this script (in james-in-a-box)
    script_dir = Path(__file__).resolve().parent

    # Navigate up to find jib-container/jib-tools/github-app-token.py
    candidates = [
        script_dir.parent.parent.parent / "jib-container" / "jib-tools" / "github-app-token.py",
        script_dir.parent.parent.parent / "bin" / "jib-tools" / "github-app-token.py",
        Path.home()
        / "khan"
        / "james-in-a-box"
        / "jib-container"
        / "jib-tools"
        / "github-app-token.py",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def find_python() -> str:
    """Find Python with cryptography support."""
    # Try the host-services venv first (has cryptography installed)
    script_dir = Path(__file__).resolve().parent
    venv_python = script_dir.parent.parent / ".venv" / "bin" / "python"

    if venv_python.exists():
        return str(venv_python)

    # Fall back to system python
    return "python3"


def has_app_credentials() -> bool:
    """Check if GitHub App credentials are configured."""
    app_id_file = CONFIG_DIR / "github-app-id"
    installation_id_file = CONFIG_DIR / "github-app-installation-id"
    private_key_file = CONFIG_DIR / "github-app.pem"

    return all(f.exists() for f in [app_id_file, installation_id_file, private_key_file])


def generate_token() -> tuple[str | None, str | None]:
    """
    Generate a fresh GitHub App installation token.

    Returns:
        Tuple of (token, error_message). Token is None on failure.
    """
    token_script = find_token_script()
    if not token_script:
        return None, "github-app-token.py script not found"

    python_cmd = find_python()

    try:
        result = subprocess.run(
            [python_cmd, str(token_script), "--config-dir", str(CONFIG_DIR)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            token = result.stdout.strip()
            if token:
                return token, None
            return None, "Empty token returned"

        return None, result.stderr.strip() or f"Exit code {result.returncode}"

    except subprocess.TimeoutExpired:
        return None, "Token generation timed out"
    except Exception as e:
        return None, str(e)


def write_token_file(token: str) -> bool:
    """
    Write token to the shared file with metadata.

    The file format is JSON with:
    - token: The actual GitHub token
    - generated_at: ISO timestamp when token was generated
    - expires_at: ISO timestamp when token expires (1 hour from generation)
    - generated_by: Service identifier
    """
    # Ensure sharing directory exists
    SHARING_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    expires_at = now.timestamp() + TOKEN_VALIDITY_SECONDS

    data = {
        "token": token,
        "generated_at": now.isoformat(),
        "expires_at_unix": expires_at,
        "expires_at": datetime.fromtimestamp(expires_at, UTC).isoformat(),
        "generated_by": "github-token-refresher",
        "validity_seconds": TOKEN_VALIDITY_SECONDS,
    }

    try:
        # Write atomically using temp file
        temp_file = TOKEN_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2) + "\n")
        temp_file.chmod(0o600)  # Restrict permissions
        temp_file.rename(TOKEN_FILE)
        logger.debug(
            "Token file written",
            token_file=str(TOKEN_FILE),
            expires_at=data["expires_at"],
        )
        return True
    except Exception as e:
        logger.error(
            "Failed to write token file",
            token_file=str(TOKEN_FILE),
            error=str(e),
            error_type=type(e).__name__,
        )
        return False


def read_current_token() -> dict | None:
    """Read the current token file if it exists."""
    if not TOKEN_FILE.exists():
        return None

    try:
        return json.loads(TOKEN_FILE.read_text())
    except Exception:
        return None


def token_needs_refresh(token_data: dict | None) -> bool:
    """Check if the token needs to be refreshed."""
    if not token_data:
        return True

    expires_at = token_data.get("expires_at_unix")
    if not expires_at:
        return True

    # Refresh if token expires within the next 20 minutes
    # This gives us a safety margin
    now = datetime.now(UTC).timestamp()
    return now > (expires_at - 20 * 60)


def refresh_token() -> bool:
    """Generate a new token and write it to the shared file."""
    logger.info("Generating new GitHub App token")

    token, error = generate_token()
    if error:
        logger.error(
            "Token generation failed",
            error=error,
        )
        return False

    if not write_token_file(token):
        return False

    # Verify the write
    token_data = read_current_token()
    if not token_data or token_data.get("token") != token:
        logger.error(
            "Token verification failed",
            token_file=str(TOKEN_FILE),
        )
        return False

    logger.info(
        "Token refreshed successfully",
        expires_at=token_data.get("expires_at"),
        validity_seconds=TOKEN_VALIDITY_SECONDS,
    )
    return True


def run_once() -> bool:
    """Run a single token refresh cycle."""
    if not has_app_credentials():
        logger.warning(
            "GitHub App credentials not configured",
            config_dir=str(CONFIG_DIR),
            required_files=["github-app-id", "github-app-installation-id", "github-app.pem"],
        )
        return False

    current = read_current_token()

    if not token_needs_refresh(current):
        logger.info(
            "Token is still valid, no refresh needed",
            expires_at=current.get("expires_at") if current else None,
        )
        return True

    return refresh_token()


def run_daemon(interval: int = REFRESH_INTERVAL_SECONDS) -> None:
    """Run as a daemon, refreshing tokens periodically."""
    logger.info(
        "Starting GitHub Token Refresher daemon",
        refresh_interval_minutes=interval // 60,
        token_file=str(TOKEN_FILE),
        config_dir=str(CONFIG_DIR),
    )

    if not has_app_credentials():
        logger.error(
            "GitHub App credentials not configured, exiting",
            config_dir=str(CONFIG_DIR),
        )
        sys.exit(1)

    # Initial refresh
    refresh_token()

    refresh_count = 0
    while True:
        try:
            time.sleep(interval)

            current = read_current_token()
            if token_needs_refresh(current):
                refresh_token()
                refresh_count += 1
            else:
                logger.debug(
                    "Token still valid, skipping refresh",
                    expires_at=current.get("expires_at") if current else None,
                )

        except KeyboardInterrupt:
            logger.info(
                "Received interrupt, shutting down",
                total_refreshes=refresh_count,
            )
            break
        except Exception as e:
            logger.error(
                "Error during refresh cycle",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Continue running even on errors


def main():
    parser = argparse.ArgumentParser(
        description="Automatically refresh GitHub App installation tokens"
    )
    parser.add_argument(
        "--once", action="store_true", help="Run once and exit (for testing or cron)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--interval",
        type=int,
        default=REFRESH_INTERVAL_SECONDS,
        help=f"Refresh interval in seconds (default: {REFRESH_INTERVAL_SECONDS})",
    )

    args = parser.parse_args()

    # Note: jib_logging handles log levels via environment variables (LOG_LEVEL)
    # --verbose flag can be used to remind users about this
    if args.verbose:
        logger.info("Verbose mode requested - set LOG_LEVEL=DEBUG for debug logging")

    if args.once:
        success = run_once()
        sys.exit(0 if success else 1)
    else:
        run_daemon(args.interval)


if __name__ == "__main__":
    main()
