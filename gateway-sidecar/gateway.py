#!/usr/bin/env python3
"""
Gateway Sidecar - REST API for policy-enforced git/gh operations.

Provides a REST API that jib containers call to perform git push and gh operations.
The gateway holds GitHub credentials and enforces ownership policies.

Security:
    - Authentication via shared secret (JIB_GATEWAY_SECRET)
    - Listens on all interfaces (containers access via host.docker.internal)
    - Rate limiting per operation type

Endpoints:
    POST /api/v1/git/push       - Push to remote (policy: branch_ownership or trusted_user)
    POST /api/v1/git/fetch      - Fetch from remote (no policy - read operations allowed)
    POST /api/v1/gh/pr/create   - Create PR (policy: blocked in incognito mode)
    POST /api/v1/gh/pr/comment  - Comment on PR (policy: none - allowed on any PR)
    POST /api/v1/gh/pr/edit     - Edit PR (policy: pr_ownership)
    POST /api/v1/gh/pr/close    - Close PR (policy: pr_ownership)
    POST /api/v1/gh/execute     - Generic gh command (policy: filtered)
    GET  /api/v1/health         - Health check (no auth required)

Usage:
    gateway.py [--host HOST] [--port PORT] [--debug]
"""

import argparse
import functools
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request
from waitress import serve


# Add shared directory to path for jib_logging
# In container, jib_logging is at /app/jib_logging
# On host, it's at ../../shared/jib_logging
_shared_path = Path(__file__).parent.parent.parent / "shared"
if _shared_path.exists():
    sys.path.insert(0, str(_shared_path))
from jib_logging import get_logger


# Import gateway modules - try relative import first (module mode),
# fall back to absolute import (standalone script mode in container)
try:
    from .github_client import get_github_client
    from .policy import (
        extract_branch_from_refspec,
        extract_repo_from_remote,
        get_policy_engine,
    )
except ImportError:
    from github_client import get_github_client
    from policy import (
        extract_branch_from_refspec,
        extract_repo_from_remote,
        get_policy_engine,
    )

# Import repo_config for incognito mode support
# Path setup needed because config is in a sibling directory
_config_path = Path(__file__).parent.parent / "config"
if _config_path.exists() and str(_config_path) not in sys.path:
    sys.path.insert(0, str(_config_path))
from repo_config import get_auth_mode


logger = get_logger("gateway-sidecar")

app = Flask(__name__)

# Configuration
DEFAULT_HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")  # Listen on all interfaces by default
DEFAULT_PORT = 9847
GIT_CLI = "/usr/bin/git"


def git_cmd(*args: str) -> list[str]:
    """
    Build a git command with safe.directory=* to allow operating on worktree paths.

    The gateway runs on the host but operates on paths inside jib container worktrees
    (e.g., ~/.jib-worktrees/<container-id>/repo). Git's ownership check would reject
    these as "dubious ownership" without safe.directory=*.
    """
    return [GIT_CLI, "-c", "safe.directory=*", *args]


# Authentication - shared secret from environment
GATEWAY_SECRET = os.environ.get("JIB_GATEWAY_SECRET", "")
SECRET_FILE = Path.home() / ".config" / "jib" / "gateway-secret"

# Rate limiting configuration (per hour)
# These limits are set high to support jib's high-velocity workflow while staying
# below GitHub's 5,000 requests/hour limit for authenticated users. The combined
# limit of 4,000/hr provides a safety buffer. See ADR-Internet-Tool-Access-Lockdown.
RATE_LIMITS = {
    "git_push": 1000,
    "git_fetch": 2000,  # Higher limit for read operations
    "gh_pr_create": 500,
    "gh_pr_comment": 2000,
    "gh_pr_edit": 500,
    "gh_pr_close": 500,
    "gh_execute": 2000,
    "combined": 4000,
}


@dataclass
class RateLimitState:
    """Track rate limit state for an operation."""

    requests: list[float] = field(default_factory=list)

    def count_recent(self, window_seconds: int = 3600) -> int:
        """Count requests within the time window."""
        now = time.time()
        cutoff = now - window_seconds
        # Clean old entries
        self.requests = [t for t in self.requests if t > cutoff]
        return len(self.requests)

    def record(self) -> None:
        """Record a new request."""
        self.requests.append(time.time())


# Global rate limit tracking
_rate_limits: dict[str, RateLimitState] = defaultdict(RateLimitState)


def get_gateway_secret() -> str:
    """Get the gateway secret from environment or file."""
    global GATEWAY_SECRET

    if GATEWAY_SECRET:
        return GATEWAY_SECRET

    # Try to read from file
    if SECRET_FILE.exists():
        GATEWAY_SECRET = SECRET_FILE.read_text().strip()
        return GATEWAY_SECRET

    # Generate a new secret and save it
    GATEWAY_SECRET = secrets.token_urlsafe(32)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_FILE.write_text(GATEWAY_SECRET)
    SECRET_FILE.chmod(0o600)
    logger.info("Generated new gateway secret", secret_file=str(SECRET_FILE))

    return GATEWAY_SECRET


def check_auth() -> tuple[bool, str]:
    """
    Check if request has valid authentication.

    Returns:
        Tuple of (is_valid, error_message)
    """
    secret = get_gateway_secret()
    if not secret:
        # No secret configured - deny all
        return False, "Gateway secret not configured"

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return False, "Missing or invalid Authorization header"

    provided_token = auth_header[7:]  # Remove "Bearer " prefix

    # Constant-time comparison to prevent timing attacks
    if secrets.compare_digest(provided_token, secret):
        return True, ""

    return False, "Invalid authorization token"


def check_rate_limit(operation: str) -> tuple[bool, str]:
    """
    Check if operation is within rate limits.

    Returns:
        Tuple of (is_allowed, error_message)
    """
    # Check operation-specific limit
    op_limit = RATE_LIMITS.get(operation, 100)
    op_state = _rate_limits[operation]
    op_count = op_state.count_recent()

    if op_count >= op_limit:
        return False, f"Rate limit exceeded for {operation}: {op_count}/{op_limit} per hour"

    # Check combined limit
    combined_state = _rate_limits["combined"]
    combined_count = combined_state.count_recent()

    if combined_count >= RATE_LIMITS["combined"]:
        return (
            False,
            f"Combined rate limit exceeded: {combined_count}/{RATE_LIMITS['combined']} per hour",
        )

    # Record the request
    op_state.record()
    combined_state.record()

    return True, ""


def require_auth(f):
    """Decorator to require authentication for an endpoint."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        is_valid, error = check_auth()
        if not is_valid:
            logger.warning(
                "Authentication failed",
                endpoint=request.path,
                error=error,
                source_ip=request.remote_addr,
            )
            return make_error(error, status_code=401)
        return f(*args, **kwargs)

    return decorated


def require_rate_limit(operation: str):
    """Decorator to enforce rate limiting for an endpoint."""

    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            is_allowed, error = check_rate_limit(operation)
            if not is_allowed:
                logger.warning(
                    "Rate limit exceeded",
                    operation=operation,
                    endpoint=request.path,
                    source_ip=request.remote_addr,
                )
                return make_error(error, status_code=429)
            return f(*args, **kwargs)

        return decorated

    return decorator


# Read-only gh commands that don't require ownership checks
READONLY_GH_COMMANDS = frozenset(
    {
        "pr view",
        "pr list",
        "pr checks",
        "pr diff",
        "pr status",
        "issue view",
        "issue list",
        "issue status",
        "repo view",
        "repo list",
        "release view",
        "release list",
        "api",  # Read-only API calls (GET)
        "auth status",
        "config get",
    }
)

# Blocked gh commands (dangerous operations)
BLOCKED_GH_COMMANDS = frozenset(
    {
        "pr merge",  # Human must merge
        "repo delete",
        "repo archive",
        "release delete",
        "auth logout",
        "auth login",
        "config set",
    }
)


def make_response(
    success: bool,
    message: str,
    data: dict[str, Any] | None = None,
    status_code: int = 200,
):
    """Create a standardized JSON response."""
    response = {"success": success, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), status_code


def make_error(message: str, status_code: int = 400, details: dict[str, Any] | None = None):
    """Create an error response."""
    return make_response(False, message, details, status_code)


def make_success(message: str, data: dict[str, Any] | None = None):
    """Create a success response."""
    return make_response(True, message, data, 200)


def audit_log(
    event_type: str,
    operation: str,
    success: bool,
    details: dict[str, Any] | None = None,
) -> None:
    """Log an audit event in structured format."""
    log_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": "gateway_operation",
        "operation": operation,
        "source_ip": request.remote_addr,
        "success": success,
    }
    if details:
        log_data.update(details)

    if success:
        logger.info(f"Audit: {event_type}", **log_data)
    else:
        logger.warning(f"Audit: {event_type}", **log_data)


@app.route("/api/v1/health", methods=["GET"])
def health_check():
    """Health check endpoint (no auth required)."""
    github = get_github_client()
    token_valid = github.is_token_valid()
    secret_configured = bool(get_gateway_secret())

    return jsonify(
        {
            "status": "healthy" if (token_valid and secret_configured) else "degraded",
            "github_token_valid": token_valid,
            "auth_configured": secret_configured,
            "service": "gateway-sidecar",
        }
    )


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


# Allowlist of gh api paths that are permitted
# These patterns match GitHub API endpoints that are safe for read/write operations
GH_API_ALLOWED_PATHS = [
    # PR operations
    re.compile(r"^repos/[^/]+/[^/]+/pulls$"),  # List PRs
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+$"),  # View PR
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/comments$"),  # PR comments
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/reviews$"),  # PR reviews
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/reviews/\d+$"),  # Specific review
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/reviews/\d+/comments$"),  # Review comments
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/requested_reviewers$"),  # Requested reviewers
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/files$"),  # PR files
    re.compile(r"^repos/[^/]+/[^/]+/pulls/\d+/commits$"),  # PR commits
    # Issue operations
    re.compile(r"^repos/[^/]+/[^/]+/issues$"),  # List issues
    re.compile(r"^repos/[^/]+/[^/]+/issues/\d+$"),  # View issue
    re.compile(r"^repos/[^/]+/[^/]+/issues/\d+/comments$"),  # Issue comments
    re.compile(r"^repos/[^/]+/[^/]+/issues/\d+/labels$"),  # Issue labels
    # Repository info
    re.compile(r"^repos/[^/]+/[^/]+$"),  # Repo info
    re.compile(r"^repos/[^/]+/[^/]+/branches$"),  # List branches
    re.compile(r"^repos/[^/]+/[^/]+/branches/[^/]+$"),  # Branch info
    re.compile(r"^repos/[^/]+/[^/]+/commits$"),  # List commits
    re.compile(r"^repos/[^/]+/[^/]+/commits/[a-f0-9]+$"),  # Specific commit
    re.compile(r"^repos/[^/]+/[^/]+/contents/.*$"),  # File contents
    re.compile(r"^repos/[^/]+/[^/]+/git/refs.*$"),  # Git refs
    re.compile(r"^repos/[^/]+/[^/]+/compare/.*$"),  # Compare commits
    # User info
    re.compile(r"^user$"),  # Current user
    re.compile(r"^users/[^/]+$"),  # User info
]


def validate_gh_api_path(path: str, method: str = "GET") -> tuple[bool, str]:
    """
    Validate gh api path against allowlist.

    Args:
        path: The API path (e.g., "repos/owner/repo/pulls/123")
        method: The HTTP method (GET, POST, etc.)

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Only GET, POST, PATCH allowed - no DELETE for safety
    if method.upper() not in ("GET", "POST", "PATCH"):
        return False, f"HTTP method '{method}' not allowed for gh api"

    # Strip leading slash if present
    path = path.lstrip("/")

    # Check against allowed patterns
    for pattern in GH_API_ALLOWED_PATHS:
        if pattern.match(path):
            return True, ""

    return False, f"API path '{path}' not in allowlist"


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
# Shared Helper Functions for Git Operations
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
        try:
            os.unlink(path)
        except OSError:
            pass  # Best effort cleanup


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


@app.route("/api/v1/git/push", methods=["POST"])
@require_auth
@require_rate_limit("git_push")
def git_push():
    """
    Handle git push requests.

    Request body:
        {
            "repo_path": "/path/to/repo",
            "remote": "origin",
            "refspec": "branch-name",
            "force": false
        }

    Policy: branch_ownership
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    repo_path = data.get("repo_path")
    remote = data.get("remote", "origin")
    refspec = data.get("refspec", "")
    force = data.get("force", False)

    if not repo_path:
        return make_error("Missing repo_path")

    # Validate repo_path to prevent path traversal attacks
    path_valid, path_error = validate_repo_path(repo_path)
    if not path_valid:
        audit_log(
            "push_blocked",
            "git_push",
            success=False,
            details={"repo_path": repo_path, "reason": path_error},
        )
        return make_error(path_error, status_code=403)

    # Get remote URL to determine repo
    try:
        result = subprocess.run(
            git_cmd("remote", "get-url", remote),
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return make_error(f"Failed to get remote URL: {result.stderr}")
        remote_url = result.stdout.strip()
    except Exception as e:
        return make_error(f"Failed to get remote URL: {e}")

    # Extract repo from URL
    repo = extract_repo_from_remote(remote_url)
    if not repo:
        return make_error(f"Could not parse repository from URL: {remote_url}")

    # Extract branch from refspec
    branch = extract_branch_from_refspec(refspec)
    if not branch:
        # Try to get current branch
        try:
            result = subprocess.run(
                git_cmd("branch", "--show-current"),
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            branch = result.stdout.strip()
        except Exception:
            pass

    if not branch:
        return make_error("Could not determine branch to push")

    # Determine auth mode for this repo
    auth_mode = get_auth_mode(repo)

    # Check branch ownership policy (pass auth mode for relaxed policy in incognito)
    policy = get_policy_engine()
    policy_result = policy.check_branch_ownership(repo, branch, auth_mode=auth_mode)

    if not policy_result.allowed:
        audit_log(
            "push_denied",
            "git_push",
            success=False,
            details={
                "repo": repo,
                "branch": branch,
                "reason": policy_result.reason,
                "auth_mode": auth_mode,
            },
        )
        return make_error(
            f"Push denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    # Get authentication token using shared helper
    token_str, auth_mode, token_error = get_token_for_repo(repo)
    if not token_str:
        return make_error(token_error, status_code=503)

    # Build push command with safe.directory for worktree paths
    push_args = ["push"]
    if force:
        push_args.append("--force")
    push_args.extend([remote, refspec] if refspec else [remote])
    cmd = git_cmd(*push_args)

    # NOTE: Git author/committer info is set at COMMIT time, not push time.
    # For incognito mode, the user must configure their local git:
    #   git config user.name "Your Name"
    #   git config user.email "your@email.com"
    if auth_mode == "incognito":
        logger.debug("Incognito mode push", repo=repo)

    # Create credential helper and execute push
    credential_helper_path = None
    try:
        credential_helper_path, env = create_credential_helper(token_str, os.environ.copy())

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )

        if result.returncode == 0:
            audit_log(
                "push_success",
                "git_push",
                success=True,
                details={
                    "repo": repo,
                    "branch": branch,
                    "force": force,
                    "auth_mode": auth_mode,
                },
            )
            return make_success(
                "Push successful",
                {
                    "repo": repo,
                    "branch": branch,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "auth_mode": auth_mode,
                },
            )
        else:
            audit_log(
                "push_failed",
                "git_push",
                success=False,
                details={
                    "repo": repo,
                    "branch": branch,
                    "returncode": result.returncode,
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                f"Push failed: {result.stderr}",
                status_code=500,
                details={"stdout": result.stdout, "stderr": result.stderr},
            )

    except subprocess.TimeoutExpired:
        return make_error("Push timed out", status_code=504)
    except Exception as e:
        return make_error(f"Push failed: {e}", status_code=500)
    finally:
        cleanup_credential_helper(credential_helper_path)


@app.route("/api/v1/git/fetch", methods=["POST"])
@require_auth
@require_rate_limit("git_fetch")
def git_fetch():
    """
    Handle git fetch requests.

    Required because the container doesn't have direct access to GitHub tokens
    (they are held by the gateway sidecar). This endpoint provides authenticated
    fetch for git fetch, git ls-remote, and similar read operations.

    Request body:
        {
            "repo_path": "/path/to/repo",
            "remote": "origin",
            "args": ["--tags"]  # optional additional args
        }

    For ls-remote:
        {
            "repo_path": "/path/to/repo",
            "operation": "ls-remote",
            "remote": "origin",
            "args": ["HEAD"]  # optional refs to query
        }
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    repo_path = data.get("repo_path")
    remote = data.get("remote", "origin")
    operation = data.get("operation", "fetch")  # fetch or ls-remote
    extra_args = data.get("args", [])

    if not repo_path:
        return make_error("Missing repo_path")

    # Validate repo_path to prevent path traversal attacks
    path_valid, path_error = validate_repo_path(repo_path)
    if not path_valid:
        audit_log(
            "fetch_blocked",
            "git_fetch",
            success=False,
            details={"repo_path": repo_path, "reason": path_error},
        )
        return make_error(path_error, status_code=403)

    if operation not in ("fetch", "ls-remote"):
        return make_error(f"Unsupported operation: {operation}")

    # Validate extra args against operation-specific allowlist
    args_valid, args_error, validated_args = validate_git_args(operation, extra_args)
    if not args_valid:
        audit_log(
            "fetch_blocked",
            "git_fetch",
            success=False,
            details={"reason": args_error, "operation": operation},
        )
        return make_error(args_error, status_code=400)

    # Get remote URL to determine repo
    try:
        result = subprocess.run(
            git_cmd("remote", "get-url", remote),
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return make_error(f"Failed to get remote URL: {result.stderr}")
        remote_url = result.stdout.strip()
    except Exception as e:
        return make_error(f"Failed to get remote URL: {e}")

    # Extract repo from URL
    repo = extract_repo_from_remote(remote_url)
    if not repo:
        return make_error(f"Could not parse repository from URL: {remote_url}")

    # Get authentication token using shared helper
    token_str, auth_mode, token_error = get_token_for_repo(repo)
    if not token_str:
        return make_error(token_error, status_code=503)

    # Build command using validated args
    if operation == "fetch":
        cmd_args = ["fetch", remote] + validated_args
    else:  # ls-remote
        cmd_args = ["ls-remote", remote] + validated_args

    cmd = git_cmd(*cmd_args)

    # Create credential helper and execute operation
    credential_helper_path = None
    try:
        credential_helper_path, env = create_credential_helper(token_str, os.environ.copy())

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )

        if result.returncode == 0:
            audit_log(
                f"{operation}_success",
                f"git_{operation}",
                success=True,
                details={
                    "repo": repo,
                    "auth_mode": auth_mode,
                },
            )
            return make_success(
                f"{operation.capitalize()} successful",
                {
                    "repo": repo,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "auth_mode": auth_mode,
                },
            )
        else:
            audit_log(
                f"{operation}_failed",
                f"git_{operation}",
                success=False,
                details={
                    "repo": repo,
                    "returncode": result.returncode,
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                f"{operation.capitalize()} failed: {result.stderr}",
                status_code=500,
                details={"stdout": result.stdout, "stderr": result.stderr},
            )

    except subprocess.TimeoutExpired:
        return make_error(f"{operation.capitalize()} timed out", status_code=504)
    except Exception as e:
        return make_error(f"{operation.capitalize()} failed: {e}", status_code=500)
    finally:
        cleanup_credential_helper(credential_helper_path)


@app.route("/api/v1/gh/pr/create", methods=["POST"])
@require_auth
@require_rate_limit("gh_pr_create")
def gh_pr_create():
    """
    Create a pull request.

    Request body:
        {
            "repo": "owner/repo",
            "title": "PR title",
            "body": "PR body",
            "base": "main",
            "head": "feature-branch"
        }

    Policy:
        - Bot mode: allowed (jib can create PRs)
        - Incognito mode: blocked (user must create PRs manually via GitHub UI)
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    repo = data.get("repo")
    title = data.get("title")
    body = data.get("body", "")
    base = data.get("base", "main")
    head = data.get("head")

    if not repo:
        return make_error("Missing repo")
    if not title:
        return make_error("Missing title")
    if not head:
        return make_error("Missing head branch")

    # Determine auth mode for this repo
    auth_mode = get_auth_mode(repo)

    # Policy check: PR creation may be blocked in incognito mode
    policy = get_policy_engine()
    policy_result = policy.check_pr_create_allowed(repo, auth_mode=auth_mode)
    if not policy_result.allowed:
        audit_log(
            "pr_create_blocked",
            "gh_pr_create",
            success=False,
            details={
                "repo": repo,
                "reason": policy_result.reason,
                "auth_mode": auth_mode,
            },
        )
        return make_error(
            policy_result.reason,
            status_code=403,
            details=policy_result.details,
        )

    try:
        github = get_github_client(mode=auth_mode)
        args = [
            "pr",
            "create",
            "--repo",
            repo,
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
            "--head",
            head,
        ]

        result = github.execute(args, timeout=60, mode=auth_mode)

        if result.success:
            audit_log(
                "pr_created",
                "gh_pr_create",
                success=True,
                details={
                    "repo": repo,
                    "title": title,
                    "base": base,
                    "head": head,
                    "auth_mode": auth_mode,
                },
            )
            return make_success(
                "PR created",
                {"stdout": result.stdout, "stderr": result.stderr, "auth_mode": auth_mode},
            )
        else:
            error_msg = result.stderr or "Unknown error"
            audit_log(
                "pr_create_failed",
                "gh_pr_create",
                success=False,
                details={
                    "repo": repo,
                    "error": error_msg[:200] if error_msg else "",
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                f"Failed to create PR: {error_msg}",
                status_code=500,
                details=result.to_dict(),
            )
    except Exception as e:
        logger.exception("Unexpected error in gh_pr_create")
        return make_error(f"Internal error: {e}", status_code=500)


@app.route("/api/v1/gh/pr/comment", methods=["POST"])
@require_auth
@require_rate_limit("gh_pr_comment")
def gh_pr_comment():
    """
    Add a comment to a PR.

    Request body:
        {
            "repo": "owner/repo",
            "pr_number": 123,
            "body": "Comment text"
        }

    Policy: pr_comment (allowed on any PR)
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    repo = data.get("repo")
    pr_number = data.get("pr_number")
    body = data.get("body")

    if not repo:
        return make_error("Missing repo")
    if not pr_number:
        return make_error("Missing pr_number")
    if not body:
        return make_error("Missing body")

    # Determine auth mode for this repo
    auth_mode = get_auth_mode(repo)

    # Check if commenting is allowed (allowed on any PR)
    policy = get_policy_engine()
    policy_result = policy.check_pr_comment_allowed(repo, pr_number)

    if not policy_result.allowed:
        audit_log(
            "pr_comment_denied",
            "gh_pr_comment",
            success=False,
            details={
                "repo": repo,
                "pr_number": pr_number,
                "reason": policy_result.reason,
                "auth_mode": auth_mode,
            },
        )
        return make_error(
            f"Comment denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    github = get_github_client(mode=auth_mode)
    args = [
        "pr",
        "comment",
        str(pr_number),
        "--repo",
        repo,
        "--body",
        body,
    ]

    result = github.execute(args, timeout=30, mode=auth_mode)

    if result.success:
        audit_log(
            "pr_comment_added",
            "gh_pr_comment",
            success=True,
            details={"repo": repo, "pr_number": pr_number, "auth_mode": auth_mode},
        )
        return make_success("Comment added", {"stdout": result.stdout, "auth_mode": auth_mode})
    else:
        return make_error(
            f"Failed to add comment: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


@app.route("/api/v1/gh/pr/edit", methods=["POST"])
@require_auth
@require_rate_limit("gh_pr_edit")
def gh_pr_edit():
    """
    Edit a PR title or body.

    Request body:
        {
            "repo": "owner/repo",
            "pr_number": 123,
            "title": "New title",  # optional
            "body": "New body"      # optional
        }

    Policy: pr_ownership
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    repo = data.get("repo")
    pr_number = data.get("pr_number")
    title = data.get("title")
    body = data.get("body")

    if not repo:
        return make_error("Missing repo")
    if not pr_number:
        return make_error("Missing pr_number")
    if not title and not body:
        return make_error("Must provide title or body to edit")

    # Determine auth mode for this repo
    auth_mode = get_auth_mode(repo)

    # Check PR ownership (pass auth mode for relaxed policy in incognito)
    policy = get_policy_engine()
    policy_result = policy.check_pr_ownership(repo, pr_number, auth_mode=auth_mode)

    if not policy_result.allowed:
        audit_log(
            "pr_edit_denied",
            "gh_pr_edit",
            success=False,
            details={
                "repo": repo,
                "pr_number": pr_number,
                "reason": policy_result.reason,
                "auth_mode": auth_mode,
            },
        )
        return make_error(
            f"Edit denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    github = get_github_client(mode=auth_mode)
    args = ["pr", "edit", str(pr_number), "--repo", repo]
    if title:
        args.extend(["--title", title])
    if body:
        args.extend(["--body", body])

    result = github.execute(args, timeout=30, mode=auth_mode)

    if result.success:
        audit_log(
            "pr_edited",
            "gh_pr_edit",
            success=True,
            details={"repo": repo, "pr_number": pr_number, "auth_mode": auth_mode},
        )
        return make_success("PR edited", {"stdout": result.stdout, "auth_mode": auth_mode})
    else:
        return make_error(
            f"Failed to edit PR: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


@app.route("/api/v1/gh/pr/close", methods=["POST"])
@require_auth
@require_rate_limit("gh_pr_close")
def gh_pr_close():
    """
    Close a PR.

    Request body:
        {
            "repo": "owner/repo",
            "pr_number": 123
        }

    Policy: pr_ownership
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    repo = data.get("repo")
    pr_number = data.get("pr_number")

    if not repo:
        return make_error("Missing repo")
    if not pr_number:
        return make_error("Missing pr_number")

    # Determine auth mode for this repo
    auth_mode = get_auth_mode(repo)

    # Check PR ownership (pass auth mode for relaxed policy in incognito)
    policy = get_policy_engine()
    policy_result = policy.check_pr_ownership(repo, pr_number, auth_mode=auth_mode)

    if not policy_result.allowed:
        audit_log(
            "pr_close_denied",
            "gh_pr_close",
            success=False,
            details={
                "repo": repo,
                "pr_number": pr_number,
                "reason": policy_result.reason,
                "auth_mode": auth_mode,
            },
        )
        return make_error(
            f"Close denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    github = get_github_client(mode=auth_mode)
    args = ["pr", "close", str(pr_number), "--repo", repo]

    result = github.execute(args, timeout=30, mode=auth_mode)

    if result.success:
        audit_log(
            "pr_closed",
            "gh_pr_close",
            success=True,
            details={"repo": repo, "pr_number": pr_number, "auth_mode": auth_mode},
        )
        return make_success("PR closed", {"stdout": result.stdout, "auth_mode": auth_mode})
    else:
        return make_error(
            f"Failed to close PR: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


@app.route("/api/v1/gh/execute", methods=["POST"])
@require_auth
@require_rate_limit("gh_execute")
def gh_execute():
    """
    Execute a generic gh command.

    Request body:
        {
            "args": ["pr", "view", "123"],
            "cwd": "/path/to/repo"  # optional
        }

    Policy: Filtered - only read-only operations allowed by default.
    Blocked commands return 403.
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    args = data.get("args", [])
    cwd = data.get("cwd")

    if not args:
        return make_error("Missing args")

    # Check for blocked commands
    cmd_str = " ".join(args[:2]) if len(args) >= 2 else args[0] if args else ""

    for blocked in BLOCKED_GH_COMMANDS:
        if cmd_str.startswith(blocked):
            audit_log(
                "blocked_command",
                "gh_execute",
                success=False,
                details={"command_args": args, "blocked_command": blocked},
            )
            return make_error(
                f"Command '{blocked}' is not allowed through the gateway. "
                f"Allowed read-only commands: {', '.join(sorted(READONLY_GH_COMMANDS))}",
                status_code=403,
                details={"blocked_command": blocked, "command_args": args},
            )

    # For 'gh api' commands, validate the path against allowlist
    if args and args[0] == "api" and len(args) > 1:
        api_path = args[1]
        method = "GET"
        for i, arg in enumerate(args):
            if arg in ("-X", "--method") and i + 1 < len(args):
                method = args[i + 1].upper()
                break

        path_valid, path_error = validate_gh_api_path(api_path, method)
        if not path_valid:
            audit_log(
                "api_path_blocked",
                "gh_execute",
                success=False,
                details={"api_path": api_path, "method": method, "reason": path_error},
            )
            return make_error(path_error, status_code=403)

    # Extract repo from args to determine auth mode
    # Look for --repo flag or -R shorthand
    repo = None
    for i, arg in enumerate(args):
        if arg in ("--repo", "-R") and i + 1 < len(args):
            repo = args[i + 1]
            break

    # Determine auth mode (default to bot if repo not specified)
    auth_mode = get_auth_mode(repo) if repo else "bot"

    # Execute the command
    github = get_github_client(mode=auth_mode)
    result = github.execute(args, timeout=60, cwd=cwd, mode=auth_mode)

    if result.success:
        response_data = result.to_dict()
        response_data["auth_mode"] = auth_mode
        return make_success("Command executed", response_data)
    else:
        return make_error(
            f"Command failed: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


def main():
    """Run the gateway server."""
    parser = argparse.ArgumentParser(description="Gateway Sidecar REST API")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host to listen on (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    args = parser.parse_args()

    # Ensure secret is configured
    secret = get_gateway_secret()
    if not secret:
        logger.error("Failed to configure gateway secret")
        sys.exit(1)

    # Validate incognito config if configured
    github = get_github_client()
    is_valid, message = github.validate_incognito_config()
    if not is_valid:
        logger.warning("Incognito config validation failed", message=message)
    else:
        logger.info("Incognito config", status=message)

    logger.info(
        "Starting Gateway Sidecar",
        host=args.host,
        port=args.port,
        debug=args.debug,
        auth_enabled=True,
        rate_limiting_enabled=True,
    )

    # Run with production server in production, debug server in debug mode
    if args.debug:
        app.run(host=args.host, port=args.port, debug=True)
    else:
        # Use waitress for production
        serve(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
