"""Gateway sidecar management for jib.

This module handles the gateway sidecar container that provides
policy enforcement for git/gh operations.
"""

import subprocess
import time
from pathlib import Path

from .config import (
    Config,
    GATEWAY_CONTAINER_NAME,
    GATEWAY_IMAGE_NAME,
    GATEWAY_PORT,
)
from .output import info, success, warn, error


def is_gateway_running() -> bool:
    """Check if the gateway container is running.

    Returns:
        True if gateway container is running, False otherwise
    """
    result = subprocess.run(
        ["docker", "container", "inspect", "-f", "{{.State.Running}}", GATEWAY_CONTAINER_NAME],
        capture_output=True,
        text=True
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def gateway_image_exists() -> bool:
    """Check if gateway Docker image exists."""
    return subprocess.run(
        ["docker", "image", "inspect", GATEWAY_IMAGE_NAME],
        capture_output=True
    ).returncode == 0


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
        [
            "docker", "build",
            "-t", GATEWAY_IMAGE_NAME,
            "-f", str(dockerfile_path),
            str(repo_root)
        ],
        capture_output=True,
        text=True
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
    import urllib.request
    import urllib.error

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
        text=True
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
