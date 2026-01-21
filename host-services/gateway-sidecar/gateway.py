#!/usr/bin/env python3
"""
Gateway Sidecar - REST API for policy-enforced git/gh operations.

Provides a REST API that jib containers call to perform git push and gh operations.
The gateway holds GitHub credentials and enforces ownership policies.

Endpoints:
    POST /api/v1/git/push       - Push to remote (policy: branch_ownership)
    POST /api/v1/gh/pr/create   - Create PR (policy: none)
    POST /api/v1/gh/pr/comment  - Comment on PR (policy: pr_ownership)
    POST /api/v1/gh/pr/edit     - Edit PR (policy: pr_ownership)
    POST /api/v1/gh/pr/close    - Close PR (policy: pr_ownership)
    POST /api/v1/gh/execute     - Generic gh command (policy: filtered)
    GET  /api/v1/health         - Health check

Usage:
    gateway.py [--host HOST] [--port PORT] [--debug]
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

# Add shared directory to path for jib_logging
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from jib_logging import get_logger

from .github_client import get_github_client
from .policy import (
    extract_branch_from_refspec,
    extract_repo_from_remote,
    get_policy_engine,
)

logger = get_logger("gateway-sidecar")

app = Flask(__name__)

# Configuration
DEFAULT_HOST = "0.0.0.0"  # Listen on all interfaces for Docker network access
DEFAULT_PORT = 9847
GIT_CLI = "/usr/bin/git"

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


@app.route("/api/v1/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    github = get_github_client()
    token_valid = github.is_token_valid()

    return jsonify(
        {
            "status": "healthy" if token_valid else "degraded",
            "github_token_valid": token_valid,
            "service": "gateway-sidecar",
        }
    )


@app.route("/api/v1/git/push", methods=["POST"])
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
        logger.warning(
            "Push denied by policy",
            repo=repo,
            branch=branch,
            reason=policy_result.reason,
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

    # Configure git credential helper to use our token
    env = os.environ.copy()
    env["GIT_ASKPASS"] = "echo"
    env["GIT_TERMINAL_PROMPT"] = "0"

    # Use credential helper via environment
    # The remote URL format: https://x-access-token:TOKEN@github.com/owner/repo.git
    # We'll set up a credential helper that provides the token
    credential_helper_script = f"""#!/bin/bash
echo "username=x-access-token"
echo "password={token.token}"
"""

    try:
        # Create temporary credential helper
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(credential_helper_script)
            credential_helper_path = f.name

        os.chmod(credential_helper_path, 0o700)
        env["GIT_ASKPASS"] = credential_helper_path

        # Configure credential helper
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )

        # Clean up
        os.unlink(credential_helper_path)

        if result.returncode == 0:
            logger.info(
                "Push successful",
                repo=repo,
                branch=branch,
                force=force,
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
            logger.warning(
                "Push failed",
                repo=repo,
                branch=branch,
                returncode=result.returncode,
                stderr=result.stderr,
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
        logger.info(
            "PR created",
            repo=repo,
            title=title,
            base=base,
            head=head,
        )
        return make_success(
            "PR created",
            {"stdout": result.stdout, "stderr": result.stderr},
        )
    else:
        return make_error(
            f"Failed to create PR: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


@app.route("/api/v1/gh/pr/comment", methods=["POST"])
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
        logger.warning(
            "PR comment denied by policy",
            repo=repo,
            pr_number=pr_number,
            reason=policy_result.reason,
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
        logger.info("PR comment added", repo=repo, pr_number=pr_number)
        return make_success("Comment added", {"stdout": result.stdout})
    else:
        return make_error(
            f"Failed to add comment: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


@app.route("/api/v1/gh/pr/edit", methods=["POST"])
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
        logger.warning(
            "PR edit denied by policy",
            repo=repo,
            pr_number=pr_number,
            reason=policy_result.reason,
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
        logger.info("PR edited", repo=repo, pr_number=pr_number)
        return make_success("PR edited", {"stdout": result.stdout})
    else:
        return make_error(
            f"Failed to edit PR: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


@app.route("/api/v1/gh/pr/close", methods=["POST"])
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
        logger.warning(
            "PR close denied by policy",
            repo=repo,
            pr_number=pr_number,
            reason=policy_result.reason,
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
        logger.info("PR closed", repo=repo, pr_number=pr_number)
        return make_success("PR closed", {"stdout": result.stdout})
    else:
        return make_error(
            f"Failed to close PR: {result.stderr}",
            status_code=500,
            details=result.to_dict(),
        )


@app.route("/api/v1/gh/execute", methods=["POST"])
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
            logger.warning(
                "Blocked gh command attempted",
                args=args,
                blocked_command=blocked,
            )
            return make_error(
                f"Command '{blocked}' is not allowed through the gateway",
                status_code=403,
                details={"blocked_command": blocked, "args": args},
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

    logger.info(
        "Starting Gateway Sidecar",
        host=args.host,
        port=args.port,
        debug=args.debug,
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
