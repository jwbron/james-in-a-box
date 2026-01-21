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
    POST /api/v1/git/push       - Push to remote (policy: branch_ownership)
    POST /api/v1/gh/pr/create   - Create PR (policy: none)
    POST /api/v1/gh/pr/comment  - Comment on PR (policy: pr_ownership)
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
import secrets
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request


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


logger = get_logger("gateway-sidecar")

app = Flask(__name__)

# Configuration
DEFAULT_HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")  # Listen on all interfaces by default
DEFAULT_PORT = 9847
GIT_CLI = "/usr/bin/git"

# Authentication - shared secret from environment
GATEWAY_SECRET = os.environ.get("JIB_GATEWAY_SECRET", "")
SECRET_FILE = Path.home() / ".config" / "jib" / "gateway-secret"

# Rate limiting configuration (per hour)
# These limits are set high to support jib's high-velocity workflow while staying
# below GitHub's 5,000 requests/hour limit for authenticated users. The combined
# limit of 4,000/hr provides a safety buffer. See ADR-Internet-Tool-Access-Lockdown.
RATE_LIMITS = {
    "git_push": 1000,
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

    # Get remote URL to determine repo
    try:
        result = subprocess.run(
            [GIT_CLI, "remote", "get-url", remote],
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
                [GIT_CLI, "branch", "--show-current"],
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

    # Check branch ownership policy
    policy = get_policy_engine()
    policy_result = policy.check_branch_ownership(repo, branch)

    if not policy_result.allowed:
        audit_log(
            "push_denied",
            "git_push",
            success=False,
            details={"repo": repo, "branch": branch, "reason": policy_result.reason},
        )
        return make_error(
            f"Push denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    # Execute git push with authentication
    github = get_github_client()
    token = github.get_token()
    if not token:
        return make_error("GitHub token not available", status_code=503)

    # Build push command
    cmd = [GIT_CLI, "push"]
    if force:
        cmd.append("--force")
    cmd.extend([remote, refspec] if refspec else [remote])

    # Configure git to use token via GIT_ASKPASS
    # Create a secure credential helper using a file descriptor instead of temp file
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    # Use environment variable for credential helper to avoid temp file
    # Git credential helper protocol: respond with username and password
    env["GIT_USERNAME"] = "x-access-token"
    env["GIT_PASSWORD"] = token.token

    # Create inline credential helper script that reads from env
    # This avoids writing token to disk
    askpass_script = """#!/bin/bash
if [[ "$1" == *"Username"* ]]; then
    echo "$GIT_USERNAME"
elif [[ "$1" == *"Password"* ]]; then
    echo "$GIT_PASSWORD"
fi
"""

    try:
        import tempfile

        # Create temp file with restrictive permissions BEFORE writing
        fd, credential_helper_path = tempfile.mkstemp(suffix=".sh", prefix="git-askpass-")
        try:
            os.fchmod(fd, 0o700)  # Set permissions on fd before writing
            os.write(fd, askpass_script.encode())
        finally:
            os.close(fd)

        env["GIT_ASKPASS"] = credential_helper_path

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )

        # Clean up immediately
        os.unlink(credential_helper_path)

        if result.returncode == 0:
            audit_log(
                "push_success",
                "git_push",
                success=True,
                details={"repo": repo, "branch": branch, "force": force},
            )
            return make_success(
                "Push successful",
                {
                    "repo": repo,
                    "branch": branch,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
        else:
            audit_log(
                "push_failed",
                "git_push",
                success=False,
                details={"repo": repo, "branch": branch, "returncode": result.returncode},
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

    Policy: none (always allowed - jib can create PRs)
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

    github = get_github_client()
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

    result = github.execute(args, timeout=60)

    if result.success:
        audit_log(
            "pr_created",
            "gh_pr_create",
            success=True,
            details={"repo": repo, "title": title, "base": base, "head": head},
        )
        return make_success(
            "PR created",
            {"stdout": result.stdout, "stderr": result.stderr},
        )
    else:
        audit_log(
            "pr_create_failed",
            "gh_pr_create",
            success=False,
            details={"repo": repo, "error": result.stderr[:200]},
        )
        return make_error(
            f"Failed to create PR: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


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

    Policy: pr_ownership
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

    # Check PR ownership
    policy = get_policy_engine()
    policy_result = policy.check_pr_ownership(repo, pr_number)

    if not policy_result.allowed:
        audit_log(
            "pr_comment_denied",
            "gh_pr_comment",
            success=False,
            details={"repo": repo, "pr_number": pr_number, "reason": policy_result.reason},
        )
        return make_error(
            f"Comment denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    github = get_github_client()
    args = [
        "pr",
        "comment",
        str(pr_number),
        "--repo",
        repo,
        "--body",
        body,
    ]

    result = github.execute(args, timeout=30)

    if result.success:
        audit_log(
            "pr_comment_added",
            "gh_pr_comment",
            success=True,
            details={"repo": repo, "pr_number": pr_number},
        )
        return make_success("Comment added", {"stdout": result.stdout})
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

    # Check PR ownership
    policy = get_policy_engine()
    policy_result = policy.check_pr_ownership(repo, pr_number)

    if not policy_result.allowed:
        audit_log(
            "pr_edit_denied",
            "gh_pr_edit",
            success=False,
            details={"repo": repo, "pr_number": pr_number, "reason": policy_result.reason},
        )
        return make_error(
            f"Edit denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    github = get_github_client()
    args = ["pr", "edit", str(pr_number), "--repo", repo]
    if title:
        args.extend(["--title", title])
    if body:
        args.extend(["--body", body])

    result = github.execute(args, timeout=30)

    if result.success:
        audit_log(
            "pr_edited",
            "gh_pr_edit",
            success=True,
            details={"repo": repo, "pr_number": pr_number},
        )
        return make_success("PR edited", {"stdout": result.stdout})
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

    # Check PR ownership
    policy = get_policy_engine()
    policy_result = policy.check_pr_ownership(repo, pr_number)

    if not policy_result.allowed:
        audit_log(
            "pr_close_denied",
            "gh_pr_close",
            success=False,
            details={"repo": repo, "pr_number": pr_number, "reason": policy_result.reason},
        )
        return make_error(
            f"Close denied: {policy_result.reason}",
            status_code=403,
            details=policy_result.details,
        )

    github = get_github_client()
    args = ["pr", "close", str(pr_number), "--repo", repo]

    result = github.execute(args, timeout=30)

    if result.success:
        audit_log(
            "pr_closed",
            "gh_pr_close",
            success=True,
            details={"repo": repo, "pr_number": pr_number},
        )
        return make_success("PR closed", {"stdout": result.stdout})
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
                f"Command '{blocked}' is not allowed through the gateway",
                status_code=403,
                details={"blocked_command": blocked, "command_args": args},
            )

    # Execute the command
    github = get_github_client()
    result = github.execute(args, timeout=60, cwd=cwd)

    if result.success:
        return make_success("Command executed", result.to_dict())
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
        try:
            from waitress import serve

            serve(app, host=args.host, port=args.port)
        except ImportError:
            logger.warning("waitress not installed, using Flask development server")
            app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
