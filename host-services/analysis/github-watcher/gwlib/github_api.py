#!/usr/bin/env python3
"""GitHub API wrapper using gh CLI with rate limiting."""

import json
import subprocess
import time
from typing import Any

from jib_logging import get_logger

logger = get_logger("github-api")

# Rate limiting configuration
RATE_LIMIT_DELAY = 0.5  # 500ms between API calls
RATE_LIMIT_MAX_RETRIES = 3
RATE_LIMIT_BASE_WAIT = 60  # Base wait for exponential backoff


def gh_json(args: list[str], repo: str | None = None) -> dict | list | None:
    """Run gh CLI command and return JSON output with rate limit handling.

    Args:
        args: Arguments to pass to gh CLI (e.g., ["pr", "view", "123"])
        repo: Optional repository context for logging

    Returns:
        Parsed JSON response, or None on failure

    Example:
        >>> gh_json(["pr", "view", "123", "--repo", "owner/repo", "--json", "number,title"])
        {"number": 123, "title": "My PR"}
    """
    time.sleep(RATE_LIMIT_DELAY)

    log_ctx = {"command": " ".join(args)}
    if repo:
        log_ctx["repo"] = repo

    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            if "rate limit" in e.stderr.lower():
                if attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    wait_time = RATE_LIMIT_BASE_WAIT * (2**attempt)
                    logger.warning("Rate limited, retrying", wait_seconds=wait_time, attempt=attempt + 1, **log_ctx)
                    time.sleep(wait_time)
                    continue
                logger.error("Rate limit exceeded after max retries", **log_ctx)
            else:
                logger.error("gh command failed", stderr=e.stderr.strip(), **log_ctx)
            return None
        except json.JSONDecodeError as e:
            logger.error("Failed to parse gh output as JSON", error=str(e), **log_ctx)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("gh command timed out", **log_ctx)
            return None

    return None


def gh_text(args: list[str], repo: str | None = None) -> str | None:
    """Run gh CLI command and return text output with rate limit handling.

    Args:
        args: Arguments to pass to gh CLI
        repo: Optional repository context for logging

    Returns:
        Raw text output, or None on failure

    Example:
        >>> gh_text(["pr", "diff", "123", "--repo", "owner/repo"])
        "diff --git a/file.py b/file.py\\n..."
    """
    time.sleep(RATE_LIMIT_DELAY)

    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            if "rate limit" in e.stderr.lower():
                if attempt < RATE_LIMIT_MAX_RETRIES - 1:
                    wait_time = RATE_LIMIT_BASE_WAIT * (2**attempt)
                    logger.warning("Rate limited, retrying", wait_seconds=wait_time, attempt=attempt + 1)
                    time.sleep(wait_time)
                    continue
                logger.error("Rate limit exceeded after max retries")
            else:
                logger.error("gh command failed", stderr=e.stderr)
            return None
        except subprocess.TimeoutExpired:
            logger.warning("gh command timed out")
            return None

    return None


def check_gh_auth() -> bool:
    """Check if gh CLI is authenticated.

    Returns:
        True if authenticated, False otherwise
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n") + result.stderr.split("\n"):
                if "Logged in to" in line:
                    logger.info("gh CLI authenticated", auth_info=line.strip())
                    return True
            logger.info("gh CLI authenticated")
            return True
        else:
            logger.error("gh CLI is not authenticated. Please run: gh auth login")
            return False
    except FileNotFoundError:
        logger.error("gh CLI not found. Please install GitHub CLI")
        return False
    except subprocess.TimeoutExpired:
        logger.error("gh auth status timed out")
        return False
