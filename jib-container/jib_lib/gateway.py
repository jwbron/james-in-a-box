"""Gateway sidecar management for jib.

This module handles the gateway sidecar container that provides
policy enforcement for git/gh operations.
"""

import json
import secrets
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import (
    GATEWAY_CONTAINER_NAME,
    GATEWAY_IMAGE_NAME,
    GATEWAY_PORT,
    Config,
)
from .output import error, info, success


# Gateway secret file location
GATEWAY_SECRET_FILE = Config.USER_CONFIG_DIR / "gateway-secret"


def get_gateway_secret() -> str:
    """Get the gateway authentication secret.

    Returns the shared secret used to authenticate with the gateway sidecar.
    Generates a new secret if one doesn't exist.

    Returns:
        The gateway secret string
    """
    if GATEWAY_SECRET_FILE.exists():
        return GATEWAY_SECRET_FILE.read_text().strip()

    # Generate a new secret
    new_secret = secrets.token_urlsafe(32)
    GATEWAY_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    GATEWAY_SECRET_FILE.write_text(new_secret)
    GATEWAY_SECRET_FILE.chmod(0o600)
    return new_secret


def gateway_api_call(
    endpoint: str,
    method: str = "GET",
    data: Optional[dict[str, Any]] = None,
    timeout: int = 30,
) -> tuple[bool, dict[str, Any]]:
    """Make an authenticated API call to the gateway.

    Args:
        endpoint: API endpoint path (e.g., "/api/v1/worktree/create")
        method: HTTP method (GET or POST)
        data: Optional JSON data for POST requests
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, response_data)
    """
    url = f"http://localhost:{GATEWAY_PORT}{endpoint}"
    secret = get_gateway_secret()

    headers = {
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }

    try:
        if method == "POST" and data:
            body = json.dumps(data).encode("utf-8")
            req = Request(url, data=body, headers=headers, method=method)
        else:
            req = Request(url, headers=headers, method=method)

        with urlopen(req, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            return response_data.get("success", False), response_data

    except URLError as e:
        return False, {"error": f"Gateway connection failed: {e}"}
    except json.JSONDecodeError as e:
        return False, {"error": f"Invalid JSON response: {e}"}
    except Exception as e:
        return False, {"error": f"Gateway API error: {e}"}


def create_worktrees(
    container_id: str,
    repos: list[str],
    base_branch: str = "HEAD",
) -> tuple[bool, dict[str, str], list[str]]:
    """Request the gateway to create worktrees for a container.

    Args:
        container_id: Container identifier
        repos: List of repository names (or owner/repo format)
        base_branch: Branch to base worktrees on

    Returns:
        Tuple of (success, worktrees_dict, errors_list)
        - worktrees_dict maps repo_name to worktree_path
        - errors_list contains any error messages
    """
    success_flag, response = gateway_api_call(
        "/api/v1/worktree/create",
        method="POST",
        data={
            "container_id": container_id,
            "repos": repos,
            "base_branch": base_branch,
        },
    )

    if not success_flag:
        return False, {}, [response.get("error", "Unknown error")]

    data = response.get("data", {})
    return True, data.get("worktrees", {}), data.get("errors", [])


def delete_worktrees(container_id: str, force: bool = False) -> tuple[bool, list[str], list[str]]:
    """Request the gateway to delete worktrees for a container.

    Args:
        container_id: Container identifier
        force: Force removal even with uncommitted changes

    Returns:
        Tuple of (success, deleted_repos, errors_list)
    """
    success_flag, response = gateway_api_call(
        "/api/v1/worktree/delete",
        method="POST",
        data={
            "container_id": container_id,
            "force": force,
        },
    )

    if not success_flag:
        return False, [], [response.get("error", "Unknown error")]

    data = response.get("data", {})
    return True, data.get("deleted", []), data.get("errors", [])


def is_gateway_running() -> bool:
    """Check if the gateway container is running.

    Returns:
        True if gateway container is running, False otherwise
    """
    result = subprocess.run(
        ["docker", "container", "inspect", "-f", "{{.State.Running}}", GATEWAY_CONTAINER_NAME],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def gateway_image_exists() -> bool:
    """Check if gateway Docker image exists."""
    return (
        subprocess.run(
            ["docker", "image", "inspect", GATEWAY_IMAGE_NAME], capture_output=True, check=False
        ).returncode
        == 0
    )


def build_gateway_image() -> bool:
    """Build the gateway sidecar Docker image.

    Builds from the repo root using the Dockerfile at
    host-services/gateway-sidecar/Dockerfile.

    Returns:
        True if build succeeded, False otherwise
    """
    # Find repo root (parent of jib-container directory)
    script_dir = Path(__file__).resolve().parent.parent
    repo_root = script_dir.parent

    dockerfile_path = repo_root / "host-services" / "gateway-sidecar" / "Dockerfile"
    if not dockerfile_path.exists():
        error(f"Gateway Dockerfile not found at {dockerfile_path}")
        return False

    info("Building gateway sidecar image...")
    result = subprocess.run(
        ["docker", "build", "-t", GATEWAY_IMAGE_NAME, "-f", str(dockerfile_path), str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode == 0:
        success("Gateway image built successfully")
        return True

    error(f"Gateway image build failed: {result.stderr}")
    return False


def wait_for_gateway_health(timeout: int = 30) -> bool:
    """Wait for the gateway to become healthy.

    Polls the health endpoint until it responds or timeout is reached.

    Args:
        timeout: Maximum seconds to wait for health

    Returns:
        True if gateway is healthy, False on timeout
    """
    import urllib.error
    import urllib.request

    # Use container name for health check since we're on the same network
    # But during startup from host, we need to use localhost or check via docker exec
    health_url = f"http://localhost:{GATEWAY_PORT}/api/v1/health"

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass  # Gateway not ready yet
        time.sleep(0.5)

    return False


def start_gateway_container() -> bool:
    """Ensure the gateway sidecar is available.

    The gateway is managed by systemd (gateway-sidecar.service). This function
    checks if it's running and healthy. If not, it tells the user how to start it.

    Returns:
        True if gateway is healthy, False otherwise
    """
    # Check if gateway is healthy
    if wait_for_gateway_health(timeout=5):
        return True

    # Gateway not available - check systemd service status
    service_result = subprocess.run(
        ["systemctl", "--user", "is-active", "gateway-sidecar.service"],
        capture_output=True,
        text=True,
        check=False,
    )

    if service_result.returncode != 0:
        error("Gateway sidecar service is not running")
        error("")
        error("To start the gateway:")
        error("  systemctl --user start gateway-sidecar.service")
        error("")
        error("To set up the gateway (if not installed):")
        error("  ./gateway-sidecar/setup.sh")
        return False

    # Service is active but not healthy - check logs
    error("Gateway sidecar service is running but not healthy")
    error("")
    error("Check service logs:")
    error("  journalctl --user -u gateway-sidecar.service -f")
    error("")
    error("Try restarting the service:")
    error("  systemctl --user restart gateway-sidecar.service")

    return False
