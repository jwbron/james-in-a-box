#!/usr/bin/env python3
"""
Gateway Sidecar - REST API for policy-enforced git/gh operations.

Provides a REST API that jib containers call to perform git push and gh operations.
The gateway holds GitHub credentials and enforces ownership policies.

Security:
    - Authentication via shared secret (JIB_GATEWAY_SECRET)
    - Listens on all interfaces (containers access via host.docker.internal)

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
        get_authenticated_remote_target,
        get_token_for_repo,
        git_cmd,
        is_repos_parent_directory,
        validate_git_args,
        validate_repo_path,
    )
    from .github_client import (
        BLOCKED_GH_COMMANDS,
        READONLY_GH_COMMANDS,
        get_github_client,
        validate_gh_api_path,
    )
    from .log_index import get_log_index
    from .log_policy import get_log_policy
    from .log_reader import (
        PathTraversalError,
        PatternValidationError,
        SearchTimeoutError,
        read_container_logs,
        read_model_output,
        read_task_logs,
        search_logs,
    )
    from .policy import (
        extract_branch_from_refspec,
        extract_repo_from_remote,
        get_policy_engine,
    )
    from .private_repo_policy import (
        check_private_repo_access,
        is_private_repo_mode_enabled,
        is_public_repo_only_mode_enabled,
    )
    from .repo_parser import parse_owner_repo
    from .worktree_manager import WorktreeManager, startup_cleanup
except ImportError:
    from git_client import (
        GIT_ALLOWED_COMMANDS,
        cleanup_credential_helper,
        create_credential_helper,
        get_authenticated_remote_target,
        get_token_for_repo,
        git_cmd,
        is_repos_parent_directory,
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
    from log_index import get_log_index
    from log_policy import get_log_policy
    from log_reader import (
        PathTraversalError,
        PatternValidationError,
        SearchTimeoutError,
        read_container_logs,
        read_model_output,
        read_task_logs,
        search_logs,
    )
    from policy import (
        extract_branch_from_refspec,
        extract_repo_from_remote,
        get_policy_engine,
    )
    from private_repo_policy import (
        check_private_repo_access,
        is_private_repo_mode_enabled,
        is_public_repo_only_mode_enabled,
    )
    from repo_parser import parse_owner_repo
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

# Host home directory for path translation
# The gateway container uses /home/jib internally, but needs to return
# host paths to the jib launcher for Docker mount sources
HOST_HOME = os.environ.get("HOST_HOME", "")
CONTAINER_HOME = "/home/jib"


def translate_to_host_path(container_path: str) -> str:
    """
    Translate a container path to the corresponding host path.

    The gateway runs with paths like /home/jib/.jib-worktrees/...
    but the jib launcher needs host paths like /home/user/.jib-worktrees/...
    for Docker mount sources.

    Args:
        container_path: Path inside the gateway container

    Returns:
        The corresponding host path, or original path if translation not possible
    """
    if not HOST_HOME:
        # No host home configured - return as-is (may cause mount issues)
        return container_path

    if container_path.startswith(CONTAINER_HOME):
        return container_path.replace(CONTAINER_HOME, HOST_HOME, 1)

    return container_path


# Authentication - shared secret from environment
GATEWAY_SECRET = os.environ.get("JIB_GATEWAY_SECRET", "")
SECRET_FILE = Path.home() / ".config" / "jib" / "gateway-secret"


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
            "private_repo_mode": is_private_repo_mode_enabled(),
            "public_repo_only_mode": is_public_repo_only_mode_enabled(),
            "service": "gateway-sidecar",
        }
    )


@app.route("/api/v1/git/push", methods=["POST"])
@require_auth
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
    container_id = data.get("container_id")

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

    # Map container path to worktree path if container_id is provided
    exec_path = map_container_path_to_worktree(repo_path, container_id, "push")

    # Get remote URL to determine repo
    try:
        result = subprocess.run(
            git_cmd("remote", "get-url", remote),
            cwd=exec_path,
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
                cwd=exec_path,
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

    # Check Private Repo Mode policy (if enabled)
    repo_info = parse_owner_repo(repo)
    if repo_info:
        priv_result = check_private_repo_access(
            operation="push",
            owner=repo_info.owner,
            repo=repo_info.repo,
            for_write=True,
        )
        if not priv_result.allowed:
            audit_log(
                "push_denied_private_mode",
                "git_push",
                success=False,
                details={
                    "repo": repo,
                    "branch": branch,
                    "reason": priv_result.reason,
                    "visibility": priv_result.visibility,
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                priv_result.reason,
                status_code=403,
                details=priv_result.to_dict(),
            )

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
    # Convert SSH URLs to HTTPS since gateway uses token auth
    push_target = get_authenticated_remote_target(remote, remote_url)
    if push_target != remote:
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
            cwd=exec_path,
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
            operation,
            success=False,
            details={
                "repo_path": repo_path,
                "git_args": args,
                "container_id": container_id,
                "reason": path_error,
            },
        )
        return make_error(path_error, status_code=403)

    # Check if this is a "repos parent" directory (contains repos but isn't one)
    # Git operations in these directories are expected to fail - this is commonly
    # caused by tools like Claude Code running `git rev-parse` to detect if they're
    # in a repo. Return a clear error without logging a warning (since this is
    # expected behavior, not an error condition).
    if is_repos_parent_directory(repo_path):
        logger.debug(
            "Git operation in repos parent directory",
            operation=operation,
            repo_path=repo_path,
            container_id=container_id,
        )
        return make_error(
            f"Path '{repo_path}' is a directory containing repositories, not a git repository. "
            "Run git commands from within a specific repository directory.",
            status_code=400,
            details={
                "hint": "This directory contains repositories but is not itself a git repository.",
                "repo_path": repo_path,
            },
        )

    # Validate operation is in allowlist
    if operation not in GIT_ALLOWED_COMMANDS:
        audit_log(
            "git_execute_blocked",
            operation,
            success=False,
            details={
                "repo_path": repo_path,
                "git_args": args,
                "container_id": container_id,
                "reason": "Operation not allowed",
            },
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
            operation,
            success=False,
            details={
                "repo_path": repo_path,
                "git_args": args,
                "container_id": container_id,
                "reason": args_error,
            },
        )
        return make_error(args_error, status_code=400)

    # Map container path to worktree path if container_id is provided
    exec_path = map_container_path_to_worktree(repo_path, container_id, operation)

    # Build command
    cmd = git_cmd(operation, *validated_args)

    try:
        result = subprocess.run(
            cmd,
            cwd=exec_path,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        if result.returncode == 0:
            audit_log(
                "git_execute_success",
                operation,
                success=True,
                details={
                    "repo_path": repo_path,
                    "git_args": validated_args,
                    "container_id": container_id,
                },
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
            # Check if this is an expected failure (e.g., repo detection queries)
            # These happen when tools check if a directory is a git repo
            is_expected_failure = result.stderr and (
                "not a git repository" in result.stderr
                or "not inside a git repository" in result.stderr
            )

            if is_expected_failure:
                # Log at debug level for expected failures - these are typically
                # from tools probing to detect if they're in a git repo
                logger.debug(
                    "Git operation failed (expected - not a git repository)",
                    operation=operation,
                    repo_path=repo_path,
                    container_id=container_id,
                )
            else:
                # Log at warning level for unexpected failures
                audit_log(
                    "git_execute_failed",
                    operation,
                    success=False,
                    details={
                        "repo_path": repo_path,
                        "git_args": validated_args,
                        "returncode": result.returncode,
                        "container_id": container_id,
                        "stderr": result.stderr[:500] if result.stderr else None,
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
    container_id = data.get("container_id")

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

    # Map container path to worktree path if container_id is provided
    exec_path = map_container_path_to_worktree(repo_path, container_id, operation)

    # Get remote URL to determine repo
    try:
        result = subprocess.run(
            git_cmd("remote", "get-url", remote),
            cwd=exec_path,
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

    # Check Private Repo Mode policy (if enabled)
    repo_info = parse_owner_repo(repo)
    if repo_info:
        priv_result = check_private_repo_access(
            operation=operation,
            owner=repo_info.owner,
            repo=repo_info.repo,
            for_write=False,
        )
        if not priv_result.allowed:
            audit_log(
                f"{operation}_denied_private_mode",
                f"git_{operation}",
                success=False,
                details={
                    "repo": repo,
                    "reason": priv_result.reason,
                    "visibility": priv_result.visibility,
                },
            )
            return make_error(
                priv_result.reason,
                status_code=403,
                details=priv_result.to_dict(),
            )

    # Get authentication token using shared helper
    token_str, auth_mode, token_error = get_token_for_repo(repo)
    if not token_str:
        return make_error(token_error, status_code=503)

    # Convert SSH URLs to HTTPS since gateway uses token auth
    fetch_target = get_authenticated_remote_target(remote, remote_url)
    if fetch_target != remote:
        logger.debug(
            f"Converting SSH URL to HTTPS for {operation}",
            original_url=remote_url,
            https_url=fetch_target,
        )

    # Build command using validated args
    if operation == "fetch":
        # Don't include remote when --all is specified (fetches from all remotes)
        if "--all" in validated_args:
            cmd_args = ["fetch"] + validated_args
        else:
            cmd_args = ["fetch", fetch_target] + validated_args
    else:  # ls-remote
        cmd_args = ["ls-remote", fetch_target] + validated_args

    cmd = git_cmd(*cmd_args)

    # Create credential helper and execute operation
    credential_helper_path = None
    try:
        credential_helper_path, env = create_credential_helper(token_str, os.environ.copy())

        result = subprocess.run(
            cmd,
            cwd=exec_path,
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

    # Check Private Repo Mode policy (if enabled)
    repo_info = parse_owner_repo(repo)
    if repo_info:
        priv_result = check_private_repo_access(
            operation="pr_create",
            owner=repo_info.owner,
            repo=repo_info.repo,
            for_write=True,
        )
        if not priv_result.allowed:
            audit_log(
                "pr_create_denied_private_mode",
                "gh_pr_create",
                success=False,
                details={
                    "repo": repo,
                    "reason": priv_result.reason,
                    "visibility": priv_result.visibility,
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                priv_result.reason,
                status_code=403,
                details=priv_result.to_dict(),
            )

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

    # Check Private Repo Mode policy (if enabled)
    repo_info = parse_owner_repo(repo)
    if repo_info:
        priv_result = check_private_repo_access(
            operation="pr_comment",
            owner=repo_info.owner,
            repo=repo_info.repo,
            for_write=True,
        )
        if not priv_result.allowed:
            audit_log(
                "pr_comment_denied_private_mode",
                "gh_pr_comment",
                success=False,
                details={
                    "repo": repo,
                    "pr_number": pr_number,
                    "reason": priv_result.reason,
                    "visibility": priv_result.visibility,
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                priv_result.reason,
                status_code=403,
                details=priv_result.to_dict(),
            )

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

    # Check Private Repo Mode policy (if enabled)
    repo_info = parse_owner_repo(repo)
    if repo_info:
        priv_result = check_private_repo_access(
            operation="pr_edit",
            owner=repo_info.owner,
            repo=repo_info.repo,
            for_write=True,
        )
        if not priv_result.allowed:
            audit_log(
                "pr_edit_denied_private_mode",
                "gh_pr_edit",
                success=False,
                details={
                    "repo": repo,
                    "pr_number": pr_number,
                    "reason": priv_result.reason,
                    "visibility": priv_result.visibility,
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                priv_result.reason,
                status_code=403,
                details=priv_result.to_dict(),
            )

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

    # Check Private Repo Mode policy (if enabled)
    repo_info = parse_owner_repo(repo)
    if repo_info:
        priv_result = check_private_repo_access(
            operation="pr_close",
            owner=repo_info.owner,
            repo=repo_info.repo,
            for_write=True,
        )
        if not priv_result.allowed:
            audit_log(
                "pr_close_denied_private_mode",
                "gh_pr_close",
                success=False,
                details={
                    "repo": repo,
                    "pr_number": pr_number,
                    "reason": priv_result.reason,
                    "visibility": priv_result.visibility,
                    "auth_mode": auth_mode,
                },
            )
            return make_error(
                priv_result.reason,
                status_code=403,
                details=priv_result.to_dict(),
            )

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

    # If no --repo in args but container passed repo in payload, use it for auth mode
    if not has_repo_flag and payload_repo:
        repo = payload_repo
        # Inject --repo into args so gh command uses it
        # NOTE: Don't inject for 'gh repo' commands - they take repo as positional arg
        is_repo_command = args and args[0] == "repo"
        if not is_repo_command:
            args = ["--repo", payload_repo] + list(args)

    # Determine auth mode (default to bot if repo not specified)
    auth_mode = get_auth_mode(repo) if repo else "bot"

    # Check Private Repo Mode policy (if enabled and repo is known)
    if repo:
        repo_info = parse_owner_repo(repo)
        if repo_info:
            priv_result = check_private_repo_access(
                operation="gh_execute",
                owner=repo_info.owner,
                repo=repo_info.repo,
                for_write=False,  # Assume read for generic gh execute
            )
            if not priv_result.allowed:
                audit_log(
                    "gh_execute_denied_private_mode",
                    "gh_execute",
                    success=False,
                    details={
                        "repo": repo,
                        "command_args": args[:3] if len(args) > 3 else args,
                        "reason": priv_result.reason,
                        "visibility": priv_result.visibility,
                        "auth_mode": auth_mode,
                    },
                )
                return make_error(
                    priv_result.reason,
                    status_code=403,
                    details=priv_result.to_dict(),
                )

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


def map_container_path_to_worktree(
    repo_path: str, container_id: str | None, operation: str = "git"
) -> str:
    """
    Map a container's repo path to the corresponding worktree path.

    Container sends paths like /home/jib/repos/{repo} or subdirectories like
    /home/jib/repos/{repo}/src/foo, but the gateway needs to run git in the
    worktree at /home/jib/.jib-worktrees/{container_id}/{repo}[/subdir].

    Args:
        repo_path: The path sent by the container (e.g., /home/jib/repos/myrepo/src)
        container_id: The container's unique identifier
        operation: Name of the operation for logging purposes

    Returns:
        The worktree path if mapping succeeds, otherwise the original repo_path.
    """
    if not container_id:
        return repo_path

    # Extract repo name and any subdirectory from paths like:
    # /home/jib/repos/myrepo -> repo_name=myrepo, subdir=""
    # /home/jib/repos/myrepo/src/foo -> repo_name=myrepo, subdir="src/foo"
    repos_prefix = "/home/jib/repos/"
    if not repo_path.startswith(repos_prefix):
        return repo_path

    # Get the path relative to /home/jib/repos/
    relative_path = repo_path[len(repos_prefix) :].rstrip("/")
    if not relative_path:
        # Path is exactly /home/jib/repos/ - not a repo
        return repo_path

    # Split into repo name and subdirectory
    parts = relative_path.split("/", 1)
    repo_name = parts[0]
    subdir = parts[1] if len(parts) > 1 else ""

    if not repo_name:
        return repo_path

    manager = get_worktree_manager()
    try:
        worktree_path, _main_repo = manager.get_worktree_paths(container_id, repo_name)
        if worktree_path.exists():
            # Append subdirectory if present
            final_path = worktree_path / subdir if subdir else worktree_path
            logger.debug(
                f"Mapped container path to worktree for {operation}",
                container_path=repo_path,
                worktree_path=str(final_path),
                container_id=container_id,
            )
            return str(final_path)
    except ValueError as e:
        logger.debug(
            f"Failed to map container path to worktree for {operation}",
            error=str(e),
            container_id=container_id,
            repo_name=repo_name,
        )

    return repo_path


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
            "repos": ["owner/repo1", "owner/repo2"],
            "uid": 1000,  // optional, defaults to 1000 (jib user)
            "gid": 1000   // optional, defaults to 1000 (jib group)
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
    # UID/GID for worktree ownership (default: 1000 for jib user)
    uid = data.get("uid")
    gid = data.get("gid")

    if not container_id:
        return make_error("Missing container_id")
    if not repos:
        return make_error("Missing repos list")

    # Validate uid/gid if provided
    if uid is not None and (not isinstance(uid, int) or uid < 0):
        return make_error("Invalid uid: must be a non-negative integer")
    if gid is not None and (not isinstance(gid, int) or gid < 0):
        return make_error("Invalid gid: must be a non-negative integer")

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
                uid=uid,
                gid=gid,
            )
            # Translate container path to host path for jib launcher mount sources
            worktrees[repo_name] = translate_to_host_path(str(info.worktree_path))
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
            elif result.uncommitted_changes and not force:
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


# =============================================================================
# Log Access Endpoints
# =============================================================================


def _extract_requester_identity() -> tuple[str | None, str | None]:
    """Extract container_id and task_id from request headers.

    In the full implementation, these are validated against session state.
    The headers serve as defense-in-depth to detect bugs/misconfigurations.

    Uses Flask's request.headers which supports case-insensitive access.

    Returns:
        Tuple of (container_id, task_id), either may be None
    """
    # Flask's request.headers supports case-insensitive access
    container_id = request.headers.get("X-Container-ID")
    task_id = request.headers.get("X-Task-ID")
    return container_id, task_id


@app.route("/api/v1/logs/list", methods=["GET"])
@require_auth
def logs_list():
    """
    List recent log entries for the requester's container.

    Request headers:
        Authorization: Bearer <gateway-secret>
        X-Container-ID: <container-id>

    Query parameters:
        limit: Maximum entries to return (default 50, max 100)
        offset: Offset for pagination (default 0)

    Returns:
        List of log entries belonging to the requester's container.
    """
    container_id, _task_id = _extract_requester_identity()

    if not container_id:
        audit_log(
            "log_access",
            "list",
            success=False,
            details={"error": "missing_container_id"},
        )
        return make_error("Missing X-Container-ID header", 400)

    limit = min(int(request.args.get("limit", 50)), 100)
    offset = int(request.args.get("offset", 0))

    log_index = get_log_index()
    entries = log_index.list_entries(container_id=container_id, limit=limit, offset=offset)

    audit_log(
        "log_access",
        "list",
        success=True,
        details={"container_id": container_id, "count": len(entries)},
    )

    return make_success(
        message=f"Found {len(entries)} log entries",
        data={
            "entries": [
                {
                    "container_id": e.container_id,
                    "task_id": e.task_id,
                    "thread_ts": e.thread_ts,
                    "log_file": e.log_file,
                    "timestamp": e.timestamp,
                }
                for e in entries
            ],
            "limit": limit,
            "offset": offset,
        },
    )


@app.route("/api/v1/logs/task/<task_id>", methods=["GET"])
@require_auth
def logs_task(task_id: str):
    """
    Get logs for a specific task.

    Request headers:
        Authorization: Bearer <gateway-secret>
        X-Container-ID: <container-id>
        X-Task-ID: <task-id> (optional, for identity matching)

    Path parameters:
        task_id: The task ID to get logs for

    Query parameters:
        lines: Maximum lines to return (default 1000, max 10000)

    Policy:
        Task must belong to the requesting container.
    """
    container_id, requester_task_id = _extract_requester_identity()

    if not container_id:
        audit_log(
            "log_access",
            "read_task",
            success=False,
            details={"error": "missing_container_id", "target_task_id": task_id},
        )
        return make_error("Missing X-Container-ID header", 400)

    # Policy check
    log_policy = get_log_policy()
    policy_result = log_policy.check_task_access(
        requester_container_id=container_id,
        requester_task_id=requester_task_id,
        target_task_id=task_id,
    )

    if not policy_result.allowed:
        audit_log(
            "log_access",
            "read_task",
            success=False,
            details={
                "container_id": container_id,
                "target_task_id": task_id,
                "policy_reason": policy_result.reason,
            },
        )
        return make_error(policy_result.reason, 403, policy_result.details)

    # Read logs
    max_lines = min(int(request.args.get("lines", 1000)), 10000)
    try:
        log_content = read_task_logs(task_id, max_lines=max_lines)
    except PathTraversalError as e:
        audit_log(
            "log_access",
            "read_task",
            success=False,
            details={
                "container_id": container_id,
                "target_task_id": task_id,
                "error": "path_traversal",
            },
        )
        return make_error(str(e), 400)

    if log_content is None:
        audit_log(
            "log_access",
            "read_task",
            success=False,
            details={
                "container_id": container_id,
                "target_task_id": task_id,
                "error": "not_found",
            },
        )
        return make_error(f"No logs found for task {task_id}", 404)

    audit_log(
        "log_access",
        "read_task",
        success=True,
        details={
            "container_id": container_id,
            "target_task_id": task_id,
            "lines": log_content.lines,
            "truncated": log_content.truncated,
        },
    )

    return make_success(
        message=f"Retrieved logs for task {task_id}",
        data={
            "task_id": log_content.task_id,
            "container_id": log_content.container_id,
            "log_file": log_content.log_file,
            "content": log_content.content,
            "lines": log_content.lines,
            "truncated": log_content.truncated,
        },
    )


@app.route("/api/v1/logs/container/<target_container_id>", methods=["GET"])
@require_auth
def logs_container(target_container_id: str):
    """
    Get logs for a specific container (self-access only).

    Request headers:
        Authorization: Bearer <gateway-secret>
        X-Container-ID: <container-id>

    Path parameters:
        target_container_id: The container ID to get logs for

    Query parameters:
        lines: Maximum lines to return (default 1000, max 10000)

    Policy:
        Requester must be the same container (self-access only).
    """
    container_id, _task_id = _extract_requester_identity()

    if not container_id:
        audit_log(
            "log_access",
            "read_container",
            success=False,
            details={"error": "missing_container_id", "target_container": target_container_id},
        )
        return make_error("Missing X-Container-ID header", 400)

    # Policy check
    log_policy = get_log_policy()
    policy_result = log_policy.check_container_access(
        requester_container_id=container_id,
        target_container_id=target_container_id,
    )

    if not policy_result.allowed:
        audit_log(
            "log_access",
            "read_container",
            success=False,
            details={
                "container_id": container_id,
                "target_container": target_container_id,
                "policy_reason": policy_result.reason,
            },
        )
        return make_error(policy_result.reason, 403, policy_result.details)

    # Read logs
    max_lines = min(int(request.args.get("lines", 1000)), 10000)
    try:
        log_content = read_container_logs(target_container_id, max_lines=max_lines)
    except PathTraversalError as e:
        audit_log(
            "log_access",
            "read_container",
            success=False,
            details={
                "container_id": container_id,
                "target_container": target_container_id,
                "error": "path_traversal",
            },
        )
        return make_error(str(e), 400)

    if log_content is None:
        audit_log(
            "log_access",
            "read_container",
            success=False,
            details={"container_id": container_id, "error": "not_found"},
        )
        return make_error(f"No logs found for container {target_container_id}", 404)

    audit_log(
        "log_access",
        "read_container",
        success=True,
        details={"container_id": container_id, "lines": log_content.lines},
    )

    return make_success(
        message=f"Retrieved logs for container {target_container_id}",
        data={
            "container_id": log_content.container_id,
            "log_file": log_content.log_file,
            "content": log_content.content,
            "lines": log_content.lines,
            "truncated": log_content.truncated,
        },
    )


@app.route("/api/v1/logs/search", methods=["GET"])
@require_auth
def logs_search():
    """
    Search logs with a pattern (scoped to requester's logs).

    Request headers:
        Authorization: Bearer <gateway-secret>
        X-Container-ID: <container-id>

    Query parameters:
        pattern: Regex pattern to search for (required)
        scope: Search scope, must be 'self' (default: 'self')
        limit: Maximum results to return (default 100, max 1000)

    Policy:
        Search is always scoped to the requester's own logs.

    Notes:
        - Pattern must be a valid regex
        - Search has a 5-second timeout to prevent ReDoS
        - Results are limited to prevent large responses
    """
    container_id, _task_id = _extract_requester_identity()

    if not container_id:
        audit_log(
            "log_access",
            "search",
            success=False,
            details={"error": "missing_container_id"},
        )
        return make_error("Missing X-Container-ID header", 400)

    pattern = request.args.get("pattern")
    if not pattern:
        return make_error("Missing 'pattern' query parameter", 400)

    scope = request.args.get("scope", "self")
    max_results = min(int(request.args.get("limit", 100)), 1000)

    # Policy check
    log_policy = get_log_policy()
    policy_result = log_policy.check_search_access(
        requester_container_id=container_id,
        scope=scope,
    )

    if not policy_result.allowed:
        audit_log(
            "log_access",
            "search",
            success=False,
            details={
                "container_id": container_id,
                "pattern": pattern,
                "policy_reason": policy_result.reason,
            },
        )
        return make_error(policy_result.reason, 403, policy_result.details)

    # Perform search
    try:
        results = search_logs(
            pattern=pattern,
            container_id=container_id,
            max_results=max_results,
        )
    except PathTraversalError as e:
        audit_log(
            "log_access",
            "search",
            success=False,
            details={
                "container_id": container_id,
                "pattern": pattern,
                "error": "path_traversal",
            },
        )
        return make_error(str(e), 400)
    except PatternValidationError as e:
        return make_error(f"Invalid search pattern: {e}", 400)
    except SearchTimeoutError as e:
        return make_error(f"Search timed out: {e}", 408)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return make_error(f"Search failed: {e}", 500)

    audit_log(
        "log_access",
        "search",
        success=True,
        details={
            "container_id": container_id,
            "pattern": pattern,
            "results_count": len(results),
        },
    )

    return make_success(
        message=f"Found {len(results)} matches",
        data={
            "pattern": pattern,
            "scope": scope,
            "results": [
                {
                    "log_file": r.log_file,
                    "line_number": r.line_number,
                    "content": r.content,
                    "task_id": r.task_id,
                    "container_id": r.container_id,
                }
                for r in results
            ],
            "limit": max_results,
            "truncated": len(results) == max_results,
        },
    )


@app.route("/api/v1/logs/model/<task_id>", methods=["GET"])
@require_auth
def logs_model(task_id: str):
    """
    Get model output for a specific task.

    Request headers:
        Authorization: Bearer <gateway-secret>
        X-Container-ID: <container-id>
        X-Task-ID: <task-id> (optional, for identity matching)

    Path parameters:
        task_id: The task ID to get model output for

    Policy:
        Task must belong to the requesting container.
    """
    container_id, requester_task_id = _extract_requester_identity()

    if not container_id:
        audit_log(
            "log_access",
            "read_model",
            success=False,
            details={"error": "missing_container_id", "target_task_id": task_id},
        )
        return make_error("Missing X-Container-ID header", 400)

    # Policy check (same as task access)
    log_policy = get_log_policy()
    policy_result = log_policy.check_task_access(
        requester_container_id=container_id,
        requester_task_id=requester_task_id,
        target_task_id=task_id,
    )

    if not policy_result.allowed:
        audit_log(
            "log_access",
            "read_model",
            success=False,
            details={
                "container_id": container_id,
                "target_task_id": task_id,
                "policy_reason": policy_result.reason,
            },
        )
        return make_error(policy_result.reason, 403, policy_result.details)

    # Read model output
    try:
        log_content = read_model_output(task_id)
    except PathTraversalError as e:
        audit_log(
            "log_access",
            "read_model",
            success=False,
            details={
                "container_id": container_id,
                "target_task_id": task_id,
                "error": "path_traversal",
            },
        )
        return make_error(str(e), 400)

    if log_content is None:
        audit_log(
            "log_access",
            "read_model",
            success=False,
            details={
                "container_id": container_id,
                "target_task_id": task_id,
                "error": "not_found",
            },
        )
        return make_error(f"No model output found for task {task_id}", 404)

    audit_log(
        "log_access",
        "read_model",
        success=True,
        details={
            "container_id": container_id,
            "target_task_id": task_id,
            "size_bytes": log_content.size_bytes,
        },
    )

    return make_success(
        message=f"Retrieved model output for task {task_id}",
        data={
            "task_id": task_id,
            "log_file": log_content.log_file,
            "content": log_content.content,
            "size_bytes": log_content.size_bytes,
            "truncated": log_content.truncated,
        },
    )


def main():
    """Run the gateway server."""
    # Safety check: refuse to run as root to prevent permission issues
    # When the gateway runs as root, git objects are created with root:root ownership,
    # which breaks git operations on the host (permission denied on .git/objects).
    if os.getuid() == 0:
        print(
            "ERROR: gateway-sidecar must not run as root.\n"
            "\n"
            "Running as root causes git objects to be created with root:root ownership,\n"
            "which breaks git operations on the host with 'permission denied' errors.\n"
            "\n"
            "To fix this:\n"
            "  1. Check the service file path in gateway-sidecar.service\n"
            "  2. Ensure ExecStart points to the correct start-gateway.sh location\n"
            "  3. Restart the service: systemctl --user restart gateway-sidecar\n"
            "  4. Verify the gateway is running as your user: ps aux | grep gateway\n"
            "\n"
            "If .git/objects already has root-owned files, fix with:\n"
            "  sudo chown -R $(id -u):$(id -g) ~/repos/*/.git",
            file=sys.stderr,
        )
        sys.exit(1)

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

    # Log repository visibility mode status
    private_mode = is_private_repo_mode_enabled()
    public_only_mode = is_public_repo_only_mode_enabled()
    if private_mode:
        logger.info(
            "Private Repo Mode ENABLED - operations restricted to private repositories",
            private_repo_mode=True,
        )
    elif public_only_mode:
        logger.info(
            "Public Repo Only Mode ENABLED - operations restricted to public repositories",
            public_repo_only_mode=True,
        )
    else:
        logger.debug(
            "Repository visibility policies disabled",
            private_repo_mode=False,
            public_repo_only_mode=False,
        )

    logger.info(
        "Starting Gateway Sidecar",
        host=args.host,
        port=args.port,
        debug=args.debug,
        auth_enabled=True,
        private_repo_mode=private_mode,
        public_repo_only_mode=public_only_mode,
    )

    # Run with production server in production, debug server in debug mode
    if args.debug:
        app.run(host=args.host, port=args.port, debug=True)
    else:
        # Use waitress for production
        serve(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
