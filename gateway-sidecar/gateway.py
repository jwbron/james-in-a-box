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
    from .git_client import (
        GIT_ALLOWED_COMMANDS,
        cleanup_credential_helper,
        create_credential_helper,
        get_token_for_repo,
        git_cmd,
        is_ssh_url,
        ssh_url_to_https,
        validate_git_args,
        validate_repo_path,
    )
    from .github_client import (
        BLOCKED_GH_COMMANDS,
        READONLY_GH_COMMANDS,
        get_github_client,
        validate_gh_api_path,
    )
    from .policy import (
        extract_branch_from_refspec,
        extract_repo_from_remote,
        get_policy_engine,
    )
    from .worktree_manager import WorktreeManager, startup_cleanup
except ImportError:
    from git_client import (
        GIT_ALLOWED_COMMANDS,
        cleanup_credential_helper,
        create_credential_helper,
        get_token_for_repo,
        git_cmd,
        is_ssh_url,
        ssh_url_to_https,
        validate_git_args,
        validate_repo_path,
    )
    from github_client import (
        BLOCKED_GH_COMMANDS,
        READONLY_GH_COMMANDS,
        get_github_client,
        parse_gh_api_args,
        validate_gh_api_path,
    )
    from policy import (
        extract_branch_from_refspec,
        extract_repo_from_remote,
        get_policy_engine,
    )
    from worktree_manager import WorktreeManager, startup_cleanup

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
    # If remote URL is SSH, convert to HTTPS since gateway uses token auth
    push_target = remote
    if is_ssh_url(remote_url):
        push_target = ssh_url_to_https(remote_url)
        logger.debug(
            "Converting SSH URL to HTTPS for push",
            original_url=remote_url,
            https_url=push_target,
        )
    push_args = ["push"]
    if force:
        push_args.append("--force")
    push_args.extend([push_target, refspec] if refspec else [push_target])
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


@app.route("/api/v1/git/execute", methods=["POST"])
@require_auth
@require_rate_limit("git_fetch")  # Use fetch rate limit for general git ops
def git_execute():
    """
    Execute a git command in the gateway's worktree.

    This is the primary endpoint for all git operations in the gateway-managed
    worktree architecture. The container has no direct git access (its .git is
    shadowed by tmpfs), so all git commands route through this endpoint.

    Request body:
        {
            "repo_path": "/home/jib/repos/myrepo",
            "operation": "status",
            "args": ["--porcelain"],
            "container_id": "jib-xxx"  # For path mapping
        }

    Supported operations: status, add, commit, log, diff, show, branch,
    checkout, switch, reset, restore, stash, merge, rebase, cherry-pick,
    tag, clean, config, rev-parse, remote

    Network operations (push, fetch, ls-remote) should use dedicated endpoints.
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    repo_path = data.get("repo_path")
    operation = data.get("operation")
    args = data.get("args", [])
    container_id = data.get("container_id")

    if not repo_path:
        return make_error("Missing repo_path")
    if not operation:
        return make_error("Missing operation")

    # Validate repo_path
    path_valid, path_error = validate_repo_path(repo_path)
    if not path_valid:
        audit_log(
            "git_execute_blocked",
            "git_execute",
            success=False,
            details={"repo_path": repo_path, "operation": operation, "reason": path_error},
        )
        return make_error(path_error, status_code=403)

    # Validate operation is in allowlist
    if operation not in GIT_ALLOWED_COMMANDS:
        audit_log(
            "git_execute_blocked",
            "git_execute",
            success=False,
            details={"operation": operation, "reason": "Operation not allowed"},
        )
        return make_error(
            f"Operation '{operation}' not allowed. "
            f"Allowed: {', '.join(sorted(GIT_ALLOWED_COMMANDS.keys()))}",
            status_code=403,
        )

    # Network operations should use dedicated endpoints
    if operation in ("push", "fetch", "ls-remote"):
        return make_error(
            f"Use dedicated endpoint for {operation}: /api/v1/git/{operation}",
            status_code=400,
        )

    # Validate args against allowlist
    args_valid, args_error, validated_args = validate_git_args(operation, args)
    if not args_valid:
        audit_log(
            "git_execute_blocked",
            "git_execute",
            success=False,
            details={"operation": operation, "args": args, "reason": args_error},
        )
        return make_error(args_error, status_code=400)

    # Build command
    cmd = git_cmd(operation, *validated_args)

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        if result.returncode == 0:
            audit_log(
                "git_execute_success",
                "git_execute",
                success=True,
                details={"operation": operation, "container_id": container_id},
            )
            return make_success(
                f"git {operation} successful",
                {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
            )
        else:
            audit_log(
                "git_execute_failed",
                "git_execute",
                success=False,
                details={
                    "operation": operation,
                    "returncode": result.returncode,
                    "container_id": container_id,
                },
            )
            return make_error(
                f"git {operation} failed",
                status_code=500,
                details={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                },
            )

    except subprocess.TimeoutExpired:
        return make_error(f"git {operation} timed out", status_code=504)
    except Exception as e:
        return make_error(f"git {operation} failed: {e}", status_code=500)


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
        # Don't include remote when --all is specified (fetches from all remotes)
        if "--all" in validated_args:
            cmd_args = ["fetch"] + validated_args
        else:
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
    # Repo passed from container - container can detect repo from worktree,
    # but gateway can't (different git structure)
    payload_repo = data.get("repo")

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
        # Parse arguments to find the actual API path (skip flags like -X, --method, etc.)
        api_path, method = parse_gh_api_args(args[1:])
        if api_path is None:
            audit_log(
                "api_path_missing",
                "gh_execute",
                success=False,
                details={"command_args": args},
            )
            return make_error("No API path provided in gh api command", status_code=400)

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
    has_repo_flag = False
    for i, arg in enumerate(args):
        if arg in ("--repo", "-R") and i + 1 < len(args):
            repo = args[i + 1]
            has_repo_flag = True
            break

    # If no --repo in args but container passed repo in payload, inject it
    # This is needed because the gateway can't auto-detect repo from worktree structure
    if not has_repo_flag and payload_repo:
        repo = payload_repo
        # Inject --repo into args so gh command uses it
        args = ["--repo", payload_repo] + list(args)

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


# =============================================================================
# Worktree Lifecycle Endpoints
# =============================================================================

# Global WorktreeManager instance
_worktree_manager: WorktreeManager | None = None


def get_worktree_manager() -> WorktreeManager:
    """Get or create the global WorktreeManager instance."""
    global _worktree_manager
    if _worktree_manager is None:
        _worktree_manager = WorktreeManager()
    return _worktree_manager


@app.route("/api/v1/worktree/create", methods=["POST"])
@require_auth
def worktree_create():
    """
    Create worktrees for a container.

    Called by the jib launcher before starting a container. Creates isolated
    worktrees for each repository the container needs access to.

    Request body:
        {
            "container_id": "jib-xxx-yyy",
            "repos": ["owner/repo1", "owner/repo2"]
        }

    Returns:
        {
            "success": true,
            "message": "Worktrees created",
            "data": {
                "worktrees": {
                    "repo1": "/home/user/.jib-worktrees/jib-xxx-yyy/repo1",
                    "repo2": "/home/user/.jib-worktrees/jib-xxx-yyy/repo2"
                }
            }
        }
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    container_id = data.get("container_id")
    repos = data.get("repos", [])
    base_branch = data.get("base_branch", "HEAD")

    if not container_id:
        return make_error("Missing container_id")
    if not repos:
        return make_error("Missing repos list")

    manager = get_worktree_manager()
    worktrees = {}
    errors = []

    for repo in repos:
        # Extract repo name from owner/repo format
        if "/" in repo:
            repo_name = repo.split("/")[-1]
        else:
            repo_name = repo

        try:
            info = manager.create_worktree(
                repo_name=repo_name,
                container_id=container_id,
                base_branch=base_branch,
            )
            worktrees[repo_name] = str(info.worktree_path)
        except ValueError as e:
            errors.append(f"{repo_name}: {e}")
        except RuntimeError as e:
            errors.append(f"{repo_name}: {e}")
        except Exception as e:
            errors.append(f"{repo_name}: unexpected error - {e}")

    if errors and not worktrees:
        return make_error(
            "Failed to create any worktrees",
            status_code=500,
            details={"errors": errors},
        )

    audit_log(
        "worktrees_created",
        "worktree_create",
        success=True,
        details={
            "container_id": container_id,
            "repos": list(worktrees.keys()),
            "errors": errors,
        },
    )

    return make_success(
        "Worktrees created",
        {
            "worktrees": worktrees,
            "errors": errors if errors else None,
        },
    )


@app.route("/api/v1/worktree/delete", methods=["POST"])
@require_auth
def worktree_delete():
    """
    Delete worktrees for a container.

    Called by the jib launcher when a container exits. Removes the worktrees
    and associated branches.

    Request body:
        {
            "container_id": "jib-xxx-yyy",
            "force": false  # optional, force remove even with uncommitted changes
        }

    Returns:
        {
            "success": true,
            "message": "Worktrees deleted",
            "data": {
                "deleted": ["repo1", "repo2"],
                "warnings": ["repo1: had uncommitted changes"]
            }
        }
    """
    data = request.get_json()
    if not data:
        return make_error("Missing request body")

    container_id = data.get("container_id")
    force = data.get("force", False)

    if not container_id:
        return make_error("Missing container_id")

    manager = get_worktree_manager()

    # Get list of worktrees for this container
    worktree_dir = manager.worktree_base / container_id
    if not worktree_dir.exists():
        return make_success("No worktrees to delete", {"deleted": []})

    deleted = []
    errors = []
    warnings = []

    # Iterate through worktree directories
    for repo_dir in list(worktree_dir.iterdir()):
        if not repo_dir.is_dir():
            continue

        repo_name = repo_dir.name

        try:
            result = manager.remove_worktree(
                container_id=container_id,
                repo_name=repo_name,
                force=force,
            )

            if result.success:
                deleted.append(repo_name)
                if result.warning:
                    warnings.append(f"{repo_name}: {result.warning}")
            else:
                if result.uncommitted_changes and not force:
                    errors.append(f"{repo_name}: has uncommitted changes (use force=true)")
                elif result.error:
                    errors.append(f"{repo_name}: {result.error}")
                else:
                    errors.append(f"{repo_name}: removal failed")
        except Exception as e:
            errors.append(f"{repo_name}: unexpected error - {e}")

    audit_log(
        "worktrees_deleted",
        "worktree_delete",
        success=True,
        details={
            "container_id": container_id,
            "deleted": deleted,
            "errors": errors,
        },
    )

    return make_success(
        "Worktrees deleted",
        {
            "deleted": deleted,
            "errors": errors if errors else None,
            "warnings": warnings if warnings else None,
        },
    )


@app.route("/api/v1/worktree/list", methods=["GET"])
@require_auth
def worktree_list():
    """
    List all active worktrees.

    Returns information about all worktrees managed by the gateway.
    """
    manager = get_worktree_manager()
    worktrees = manager.list_worktrees()
    return make_success("Worktrees listed", {"worktrees": worktrees})


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
    is_valid, validation_msg = github.validate_incognito_config()
    if not is_valid:
        logger.warning("Incognito config validation failed", reason=validation_msg)
    else:
        logger.info("Incognito config", status=validation_msg)

    # Clean up orphaned worktrees from crashed containers
    try:
        orphans_removed = startup_cleanup()
        if orphans_removed > 0:
            logger.info(f"Startup cleanup removed {orphans_removed} orphaned worktree(s)")
    except Exception as e:
        logger.warning("Startup worktree cleanup failed", error=str(e))

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
