"""Container execution for jib.

This module handles running containers in interactive and exec modes.

The gateway-managed worktree architecture:
- Gateway creates/manages worktrees before container starts
- Container mounts only working directory (no direct git metadata access)
- All git operations route through gateway API
- Gateway handles worktree cleanup when containers exit
"""

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Import statusbar for quiet mode
from statusbar import status

from .auth import get_anthropic_api_key, get_anthropic_auth_method
from .config import (
    GATEWAY_CONTAINER_NAME,
    GATEWAY_PORT,
    JIB_NETWORK_NAME,
    Config,
    get_local_repos,
)
from .container_logging import (
    extract_task_id_from_command,
    extract_thread_ts_from_task_file,
    generate_container_id,
    get_docker_log_config,
    save_container_logs,
)
from .docker import build_image, image_exists
from .gateway import (
    create_worktrees,
    delete_worktrees,
    start_gateway_container,
)
from .output import error, get_quiet_mode, info, success, warn
from .setup_flow import add_standard_mounts, setup
from .timing import _host_timer


def _setup_repo_mounts(
    container_id: str,
    mount_args: list[str],
    quiet: bool = False,
    use_gateway_worktrees: bool = True,
) -> dict:
    """Configure repository mounts for a container.

    In the gateway-managed worktree architecture:
    - Gateway creates worktrees for the container before it starts
    - Container mounts gateway-created worktrees at /home/jib/repos/{repo_name}
    - The .git directory is shadowed by a tmpfs mount (no git metadata in container)
    - All git operations must go through the gateway API

    Args:
        container_id: Unique container identifier
        mount_args: List to append mount arguments to
        quiet: Suppress output
        use_gateway_worktrees: If True, request worktrees from gateway (default)
                               If False, mount repos directly (fallback)

    Returns:
        Dict of repo_name -> repo_path for tracking
    """
    repos = {}
    local_repos = get_local_repos()

    if not local_repos:
        if not quiet:
            info("No local repositories configured.")
        return repos

    repo_names = [repo_path.name for repo_path in local_repos if repo_path.is_dir()]

    if not repo_names:
        return repos

    if use_gateway_worktrees:
        # Request gateway to create worktrees with correct ownership
        wt_success, worktrees, wt_errors = create_worktrees(
            container_id, repo_names, uid=os.getuid(), gid=os.getgid()
        )

        if wt_errors and not quiet:
            for err in wt_errors:
                warn(f"Worktree error: {err}")

        if not wt_success and not worktrees:
            # Fall back to direct mounts if gateway fails
            if not quiet:
                warn("Gateway worktree creation failed, using direct mounts")
            use_gateway_worktrees = False

    for repo_path in local_repos:
        if not repo_path.is_dir():
            continue

        repo_name = repo_path.name
        container_path = f"/home/jib/repos/{repo_name}"

        if use_gateway_worktrees and repo_name in worktrees:
            # Mount gateway-created worktree
            worktree_path = worktrees[repo_name]
            mount_args.extend(["-v", f"{worktree_path}:{container_path}:rw"])

            if not quiet:
                print(f"  • ~/repos/{repo_name} (gateway worktree)")
        else:
            # Fallback: mount repo directly
            mount_args.extend(["-v", f"{repo_path}:{container_path}:rw"])

            if not quiet:
                print(f"  • ~/repos/{repo_name} (direct mount)")

        # Shadow .git with tmpfs to prevent local git operations
        # This forces all git operations through the gateway
        mount_args.extend(["--mount", f"type=tmpfs,destination={container_path}/.git"])

        repos[repo_name] = repo_path

    return repos


def _cleanup_worktrees(container_id: str, force: bool = True) -> None:
    """Clean up gateway worktrees for a container.

    Called when container exits to release worktree resources.

    Args:
        container_id: Container identifier
        force: Force removal even with uncommitted changes
    """
    try:
        _success_flag, _deleted, errors = delete_worktrees(container_id, force=force)
        if errors:
            for err in errors:
                warn(f"Worktree cleanup warning: {err}")
    except Exception as e:
        warn(f"Worktree cleanup failed: {e}")


def run_claude() -> bool:
    """Run Claude Code CLI in the sandboxed container (interactive mode)"""
    quiet = get_quiet_mode()

    # Check if image exists
    with _host_timer.phase("check_image"):
        if quiet:
            status("Checking Docker image...")
        if not image_exists():
            info("Docker image not found. Running initial setup...")
            if not setup():
                return False

    # Check repository configuration exists
    with _host_timer.phase("check_config"):
        if not Config.REPOS_CONFIG_FILE.exists():
            info("Repository configuration not found. Running initial setup...")
            if not setup():
                return False

    # Check Anthropic API key authentication
    with _host_timer.phase("check_api_key"):
        if quiet:
            status("Checking authentication...")

        api_key = get_anthropic_api_key()

        if not quiet:
            from .config import Colors

            print()
            print(f"{Colors.BOLD}Checking Claude Code authentication...{Colors.NC}")

            if api_key:
                success("Anthropic API key configured")
                print(f"  API key: {api_key[:12]}...{api_key[-4:]}")
            else:
                warn("Anthropic API key not configured")
                print("  Set via: export ANTHROPIC_API_KEY=sk-ant-...")
                print(f"  Or save to: {Config.USER_CONFIG_DIR / 'anthropic-api-key'}")
                print()
                warn("Container will not be able to use Claude without an API key.")

            print()

    # Build/update image (Docker uses cache for unchanged layers - usually instant)
    with _host_timer.phase("build_image"):
        if quiet:
            status("Building Docker image...")
        if not build_image():
            error("Docker build failed")
            return False

    # Start gateway sidecar container (if not already running)
    with _host_timer.phase("start_gateway"):
        if quiet:
            status("Starting gateway sidecar...")
        if not start_gateway_container():
            error("Failed to start gateway sidecar")
            return False

    # Generate unique container ID
    with _host_timer.phase("prepare_container"):
        if quiet:
            status("Preparing container...")
        container_id = generate_container_id()

        if not quiet:
            info("Launching sandboxed Claude Code environment...")
            print()
            info(f"Container ID: {container_id}")
            print()

    # Build mount configuration
    _host_timer.start_phase("configure_mounts")
    if quiet:
        status("Configuring mounts...")
    else:
        info("Configuring repository mounts...")
        print()
    mount_args = []

    # Mount repositories with .git shadowed
    repos = _setup_repo_mounts(container_id, mount_args, quiet=quiet)

    if repos and not quiet:
        print()
        info(f"Mounted {len(repos)} repo(s) (all git operations via gateway)")
        print()

    # Add standard mounts (sharing, context-sync)
    add_standard_mounts(mount_args, quiet=quiet)

    # Mount host Claude configuration (interactive mode only)
    # This allows the container to use the host's Claude settings
    home = Path.home()
    claude_dir = home / ".claude"
    claude_json = home / ".claude.json"

    if claude_dir.is_dir():
        container_claude_dir = "/home/jib/.claude"
        mount_args.extend(["-v", f"{claude_dir}:{container_claude_dir}:rw"])
        if not quiet:
            print("  • ~/.claude (Claude config directory)")

    if claude_json.is_file():
        container_claude_json = "/home/jib/.claude.json"
        mount_args.extend(["-v", f"{claude_json}:{container_claude_json}:rw"])
        if not quiet:
            print("  • ~/.claude.json (Claude settings)")

    if not quiet:
        print()
    _host_timer.end_phase()  # configure_mounts

    # Remove old container if exists (cleanup any previous runs)
    with _host_timer.phase("cleanup_old_container"):
        subprocess.run(
            ["docker", "rm", "-f", container_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    # Build docker run command on jib-network (shared network with gateway sidecar)
    _host_timer.start_phase("build_docker_cmd")
    # jib-network allows container-to-container communication while isolating from host
    cmd = [
        "docker",
        "run",
        "--rm",  # Auto-remove container after exit
        "-it",  # Interactive with TTY
        "--security-opt",
        "label=disable",  # Disable SELinux labeling for faster startup
        "--name",
        container_id,
        "--network",
        JIB_NETWORK_NAME,  # Connect to jib-network for gateway access
        "-e",
        f"RUNTIME_UID={os.getuid()}",
        "-e",
        f"RUNTIME_GID={os.getgid()}",
        "-e",
        f"CONTAINER_ID={container_id}",
        "-e",
        f"JIB_QUIET={'1' if quiet else '0'}",
        "-e",
        f"JIB_TIMING={'1' if _host_timer.enabled else '0'}",
        "-e",
        f"GATEWAY_URL=http://{GATEWAY_CONTAINER_NAME}:{GATEWAY_PORT}",
    ]

    # GitHub authentication is handled by the gateway sidecar
    # The container does NOT receive GITHUB_TOKEN - all git/gh operations
    # route through the gateway which holds the credentials
    if not quiet:
        info("GitHub auth: Via gateway sidecar (credentials not in container)")

    # Add Anthropic auth configuration
    anthropic_auth_method = get_anthropic_auth_method()
    cmd.extend(["-e", f"ANTHROPIC_AUTH_METHOD={anthropic_auth_method}"])

    # Set Anthropic API key if available
    if api_key:
        cmd.extend(["-e", f"ANTHROPIC_API_KEY={api_key}"])

    if not quiet:
        info(f"Claude auth method: {anthropic_auth_method}")
        info("Network mode: Bridge (isolated from host, outbound HTTP only)")
        print("  Container can: Access Claude API, download packages")
        print("  Container cannot: Access host services, accept inbound connections")
        print()

    # Add mount arguments
    cmd.extend(mount_args)

    # Add image name
    cmd.append(Config.IMAGE_NAME)

    # End timing for command build
    _host_timer.end_phase()  # build_docker_cmd

    # Pass host timing data to container (must be after all host phases complete)
    host_timing_json = _host_timer.to_json()
    if host_timing_json:
        # Insert timing env var before the image name (last element)
        cmd.insert(-1, "-e")
        cmd.insert(-1, f"JIB_HOST_TIMING={host_timing_json}")

    # Final status update before launching
    if quiet:
        status("Launching Claude...")

    # Record launch timestamp for measuring docker startup time
    # This captures the gap between host finishing and container Python starting
    if _host_timer.enabled:
        launch_time = time.time()
        cmd.insert(-1, "-e")
        cmd.insert(-1, f"JIB_HOST_LAUNCH_TIME={launch_time}")

    # Run container
    try:
        subprocess.run(cmd, check=False)
        return True
    except KeyboardInterrupt:
        print()
        warn("Interrupted by user")
        return False
    except Exception as e:
        error(f"Failed to run container: {e}")
        return False
    finally:
        # Clean up gateway worktrees when container exits
        if repos:
            _cleanup_worktrees(container_id)


def exec_in_new_container(
    command: list[str],
    timeout_minutes: int = 30,
    task_id: str | None = None,
    thread_ts: str | None = None,
    auth_mode: str = "host",
) -> bool:
    """Execute a command in a new ephemeral container.

    In the gateway-managed worktree architecture:
    - Repos are mounted directly with .git shadowed by tmpfs
    - All git operations route through the gateway API
    - Container logs persisted to ~/.jib-sharing/container-logs/

    Args:
        command: Command to execute
        timeout_minutes: Timeout in minutes (default: 30)
        task_id: Optional task ID for log correlation (auto-detected from command if not provided)
        thread_ts: Optional Slack thread timestamp for correlation
        auth_mode: Authentication method - 'host' mounts ~/.claude, 'api-key' passes env var

    Returns:
        True if successful, False otherwise

    Raises:
        ValueError: If auth_mode is not 'host' or 'api-key'
    """
    # Validate auth_mode parameter
    valid_auth_modes = ("host", "api-key")
    if auth_mode not in valid_auth_modes:
        raise ValueError(f"Invalid auth_mode '{auth_mode}'. Must be one of: {valid_auth_modes}")

    # Check if image exists
    if not image_exists():
        info("Docker image not found. Running initial setup...")
        if not setup():
            return False

    # Check repository configuration exists
    if not Config.REPOS_CONFIG_FILE.exists():
        info("Repository configuration not found. Running initial setup...")
        if not setup():
            return False

    # Build/update image
    if not build_image():
        error("Docker build failed")
        return False

    # Start gateway sidecar container (if not already running)
    if not start_gateway_container():
        error("Failed to start gateway sidecar")
        return False

    # Generate unique container ID for this exec
    container_id = f"jib-exec-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"

    # Auto-detect task_id from command if not provided
    if not task_id:
        task_id = extract_task_id_from_command(command)

    # Auto-detect thread_ts from task file if not provided
    if not thread_ts and task_id:
        for arg in command:
            if ".md" in arg:
                thread_ts = extract_thread_ts_from_task_file(arg)
                break

    info(f"Executing command in new container: {container_id}")
    if task_id:
        info(f"Task ID: {task_id}")
    if thread_ts:
        info(f"Thread TS: {thread_ts}")
    print(f"Command: {' '.join(command)}")
    print(f"Timeout: {timeout_minutes} minutes")
    print()

    # Build mount configuration
    info("Configuring repository mounts...")
    mount_args = []

    # Mount repositories with .git shadowed
    repos = _setup_repo_mounts(container_id, mount_args, quiet=False)

    if repos:
        info(f"Mounted {len(repos)} repo(s) (all git operations via gateway)")
        print()

    # Add standard mounts (sharing, context-sync)
    add_standard_mounts(mount_args, quiet=False)

    # Mount host Claude configuration when using host auth mode
    if auth_mode == "host":
        home = Path.home()
        claude_dir = home / ".claude"
        claude_json = home / ".claude.json"

        if claude_dir.is_dir():
            container_claude_dir = "/home/jib/.claude"
            mount_args.extend(["-v", f"{claude_dir}:{container_claude_dir}:rw"])
            print("  • ~/.claude (Claude config directory)")

        if claude_json.is_file():
            container_claude_json = "/home/jib/.claude.json"
            mount_args.extend(["-v", f"{claude_json}:{container_claude_json}:rw"])
            print("  • ~/.claude.json (Claude settings)")

    print()

    # Build docker run command on jib-network (shared network with gateway sidecar)
    # Note: We don't use --rm so we can save logs before cleanup
    cmd = [
        "docker",
        "run",
        "--security-opt",
        "label=disable",  # Disable SELinux labeling for faster startup
        "--name",
        container_id,
        "--network",
        JIB_NETWORK_NAME,  # Connect to jib-network for gateway access
        "-e",
        f"RUNTIME_UID={os.getuid()}",
        "-e",
        f"RUNTIME_GID={os.getgid()}",
        "-e",
        f"CONTAINER_ID={container_id}",
        "-e",
        "PYTHONUNBUFFERED=1",  # Force Python to use unbuffered output for real-time streaming
        "-e",
        f"GATEWAY_URL=http://{GATEWAY_CONTAINER_NAME}:{GATEWAY_PORT}",
    ]

    # Add logging configuration for log persistence
    log_config = get_docker_log_config(container_id, task_id)
    cmd.extend(log_config)

    # Add correlation environment variables for log tracing
    if task_id:
        cmd.extend(["-e", f"JIB_TASK_ID={task_id}"])
    if thread_ts:
        cmd.extend(["-e", f"JIB_THREAD_TS={thread_ts}"])

    # GitHub authentication is handled by the gateway sidecar
    # The container does NOT receive GITHUB_TOKEN - all git/gh operations
    # route through the gateway which holds the credentials

    # Add Anthropic auth configuration
    anthropic_auth_method = get_anthropic_auth_method()
    cmd.extend(["-e", f"ANTHROPIC_AUTH_METHOD={anthropic_auth_method}"])

    # Set Anthropic API key only when using api-key auth mode
    # When using host auth, Claude Code will use ~/.claude for authentication
    if auth_mode == "api-key":
        api_key = get_anthropic_api_key()
        if api_key:
            cmd.extend(["-e", f"ANTHROPIC_API_KEY={api_key}"])

    # Add mount arguments
    cmd.extend(mount_args)

    # Add image name
    cmd.append(Config.IMAGE_NAME)

    # Add the command to execute
    cmd.extend(command)

    # Run container with configurable timeout
    timeout_seconds = timeout_minutes * 60
    run_success = False

    def cleanup_container():
        """Save logs, remove container, and clean up worktrees."""
        try:
            # Save container logs before removal (with correlation info)
            save_container_logs(container_id, task_id, thread_ts)
        except Exception as e:
            error(f"Failed to save container logs: {e}")
            # Don't re-raise - continue with cleanup
        finally:
            # Remove container
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception as e:
                error(f"Failed to remove container: {e}")
                # Don't re-raise - original error is more important

            # Clean up gateway worktrees
            if repos:
                _cleanup_worktrees(container_id)

    try:
        result = subprocess.run(cmd, timeout=timeout_seconds, check=False)
        run_success = result.returncode == 0
    except subprocess.TimeoutExpired:
        print()
        error(f"Container execution timed out after {timeout_minutes} minutes")
        # Kill the container if it's still running
        subprocess.run(
            ["docker", "kill", container_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except KeyboardInterrupt:
        print()
        warn("Interrupted by user")
        # Kill container on interrupt
        subprocess.run(
            ["docker", "kill", container_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception as e:
        error(f"Failed to run container: {e}")
    finally:
        # Always save logs and cleanup container
        cleanup_container()

    return run_success
