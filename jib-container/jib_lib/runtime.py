"""Container execution for jib.

This module handles running containers in interactive and exec modes.
"""

import atexit
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .config import (
    Config,
    JIB_NETWORK_NAME,
    GATEWAY_CONTAINER_NAME,
    GATEWAY_PORT,
)
from .output import info, success, warn, error, get_quiet_mode
from .auth import get_anthropic_api_key, get_anthropic_auth_method
from .docker import build_image, image_exists
from .gateway import start_gateway_container
from .container_logging import (
    generate_container_id,
    get_docker_log_config,
    extract_task_id_from_command,
    extract_thread_ts_from_task_file,
    save_container_logs,
)
from .worktrees import create_worktrees, cleanup_worktrees
from .setup_flow import setup, add_standard_mounts
from .timing import _host_timer

# Import statusbar for quiet mode
from statusbar import status


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
                print(f"  Set via: export ANTHROPIC_API_KEY=sk-ant-...")
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

    # Create worktrees for repos (isolates container from host repos)
    with _host_timer.phase("create_worktrees"):
        if quiet:
            status("Creating isolated worktrees...")
        else:
            info("Creating isolated worktrees...")
            print()
        worktrees = create_worktrees(container_id)

    if worktrees and not quiet:
        print()
        info(f"Created {len(worktrees)} worktree(s)")
        print()

    # Register cleanup on exit
    def cleanup_on_exit():
        cleanup_worktrees(container_id)

    atexit.register(cleanup_on_exit)

    # Build mount configuration dynamically (no mounts.conf file needed)
    _host_timer.start_phase("configure_mounts")
    if quiet:
        status("Configuring mounts...")
    mount_args = []

    # Add worktree mounts for configured local repositories
    # worktrees dict has structure: {repo_name: {"worktree": path, "source": path}}
    for repo_name, repo_info in worktrees.items():
        worktree_path = repo_info["worktree"]
        source_path = repo_info["source"]
        container_path = f"/home/jib/repos/{repo_name}"
        mount_args.extend(["-v", f"{worktree_path}:{container_path}:rw"])
        if not quiet:
            print(f"  • ~/repos/{repo_name} (WORKTREE, isolated from host)")

        # Mount main repo .git directories (read-write) so worktrees can commit changes
        git_path = source_path / ".git"
        if git_path.is_dir():
            # Normal repo - mount .git directory directly
            git_container_path = f"/home/jib/.git-main/{repo_name}"
            mount_args.extend(["-v", f"{git_path}:{git_container_path}:rw"])
            if not quiet:
                print(f"  • ~/.git-main/{repo_name} (git metadata for worktree, read-write)")
        elif git_path.is_file():
            # Host repo is a worktree - read .git file to find actual git directory
            # Format is: "gitdir: /path/to/repo.git/worktrees/name"
            try:
                gitdir_content = git_path.read_text().strip()
                if gitdir_content.startswith("gitdir:"):
                    gitdir_path = Path(gitdir_content[7:].strip())
                    # Navigate up from worktrees/<name> to the main .git directory
                    # e.g., /path/.git/worktrees/foo -> /path/.git
                    if "worktrees" in gitdir_path.parts:
                        worktrees_idx = gitdir_path.parts.index("worktrees")
                        main_git_path = Path(*gitdir_path.parts[:worktrees_idx])
                        if main_git_path.is_dir():
                            git_container_path = f"/home/jib/.git-main/{repo_name}"
                            mount_args.extend(["-v", f"{main_git_path}:{git_container_path}:rw"])
                            if not quiet:
                                print(f"  • ~/.git-main/{repo_name} (git metadata, from host worktree)")
                        else:
                            warn(f"Could not find git directory for {repo_name}: {main_git_path}")
                    else:
                        warn(f"Unexpected gitdir format for {repo_name}: {gitdir_path}")
                else:
                    warn(f"Invalid .git file format for {repo_name}")
            except Exception as e:
                warn(f"Error reading .git file for {repo_name}: {e}")

    # Mount worktree base directory (used by both interactive and --exec modes)
    worktree_base_container = f"/home/jib/.jib-worktrees"
    mount_args.extend(["-v", f"{Config.WORKTREE_BASE}:{worktree_base_container}:rw"])
    if not quiet:
        print(f"  • ~/.jib-worktrees/ (worktree base directory)")

    # Add standard mounts (sharing, context-sync)
    add_standard_mounts(mount_args, quiet=quiet)

    # Mount host Claude configuration (interactive mode only)
    # This allows the container to use the host's Claude settings
    home = Path.home()
    claude_dir = home / ".claude"
    claude_json = home / ".claude.json"

    if claude_dir.is_dir():
        container_claude_dir = f"/home/jib/.claude"
        mount_args.extend(["-v", f"{claude_dir}:{container_claude_dir}:rw"])
        if not quiet:
            print(f"  • ~/.claude (Claude config directory)")

    if claude_json.is_file():
        container_claude_json = f"/home/jib/.claude.json"
        mount_args.extend(["-v", f"{claude_json}:{container_claude_json}:rw"])
        if not quiet:
            print(f"  • ~/.claude.json (Claude settings)")

    if not quiet:
        print()
    _host_timer.end_phase()  # configure_mounts

    # Remove old container if exists (cleanup any previous runs)
    with _host_timer.phase("cleanup_old_container"):
        subprocess.run(["docker", "rm", "-f", container_id],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)

    # Build docker run command on jib-network (shared network with gateway sidecar)
    _host_timer.start_phase("build_docker_cmd")
    # jib-network allows container-to-container communication while isolating from host
    worktree_host_path = Config.WORKTREE_BASE / container_id
    cmd = [
        "docker", "run",
        "--rm",  # Auto-remove container after exit
        "-it",   # Interactive with TTY
        "--security-opt", "label=disable",  # Disable SELinux labeling for faster startup
        "--name", container_id,
        "--network", JIB_NETWORK_NAME,  # Connect to jib-network for gateway access
        "-e", f"RUNTIME_UID={os.getuid()}",
        "-e", f"RUNTIME_GID={os.getgid()}",
        "-e", f"CONTAINER_ID={container_id}",
        "-e", f"JIB_QUIET={'1' if quiet else '0'}",
        "-e", f"JIB_TIMING={'1' if _host_timer.enabled else '0'}",
        "-e", f"GATEWAY_URL=http://{GATEWAY_CONTAINER_NAME}:{GATEWAY_PORT}",
        # Host worktree path - needed by git wrapper to translate container paths
        # Container sees /home/user/repos/X, but gateway needs ~/.jib-worktrees/<id>/X
        "-e", f"JIB_WORKTREE_HOST_PATH={worktree_host_path}",
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
        subprocess.run(cmd)
        return True
    except KeyboardInterrupt:
        print()
        warn("Interrupted by user")
        return False
    except Exception as e:
        error(f"Failed to run container: {e}")
        return False


def exec_in_new_container(
    command: List[str],
    timeout_minutes: int = 30,
    task_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
    auth_mode: str = "host",
) -> bool:
    """Execute a command in a new ephemeral container with isolated worktrees.

    Creates worktrees for all repos to isolate changes (same as interactive mode):
    - Total isolation from interactive sessions and main repos
    - Worktrees allow parallel work without conflicts
    - Automatic cleanup (--rm)
    - All commits go to temporary branches (jib-temp-jib-exec-*)
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

    # Create worktrees for repos (isolates container from host repos)
    info("Creating isolated worktrees...")
    worktrees = create_worktrees(container_id)

    if worktrees:
        info(f"Created {len(worktrees)} worktree(s)")
        print()

    # Register cleanup on exit (even if container fails)
    def cleanup_on_exit():
        cleanup_worktrees(container_id)

    atexit.register(cleanup_on_exit)

    # Build mount configuration dynamically (no mounts.conf file needed)
    mount_args = []

    # Add worktree mounts for configured local repositories
    # worktrees dict has structure: {repo_name: {"worktree": path, "source": path}}
    for repo_name, repo_info in worktrees.items():
        worktree_path = repo_info["worktree"]
        source_path = repo_info["source"]
        container_path = f"/home/jib/repos/{repo_name}"
        mount_args.extend(["-v", f"{worktree_path}:{container_path}:rw"])
        print(f"  • ~/repos/{repo_name} (WORKTREE, isolated)")

        # Mount main repo .git directories (read-write) so worktrees can commit changes
        git_path = source_path / ".git"
        if git_path.is_dir():
            # Normal repo - mount .git directory directly
            git_container_path = f"/home/jib/.git-main/{repo_name}"
            mount_args.extend(["-v", f"{git_path}:{git_container_path}:rw"])
            print(f"  • ~/.git-main/{repo_name} (git metadata)")
        elif git_path.is_file():
            # Host repo is a worktree - read .git file to find actual git directory
            try:
                gitdir_content = git_path.read_text().strip()
                if gitdir_content.startswith("gitdir:"):
                    gitdir_path = Path(gitdir_content[7:].strip())
                    if "worktrees" in gitdir_path.parts:
                        worktrees_idx = gitdir_path.parts.index("worktrees")
                        main_git_path = Path(*gitdir_path.parts[:worktrees_idx])
                        if main_git_path.is_dir():
                            git_container_path = f"/home/jib/.git-main/{repo_name}"
                            mount_args.extend(["-v", f"{main_git_path}:{git_container_path}:rw"])
                            print(f"  • ~/.git-main/{repo_name} (git metadata, from host worktree)")
                        else:
                            warn(f"Could not find git directory for {repo_name}: {main_git_path}")
                    else:
                        warn(f"Unexpected gitdir format for {repo_name}: {gitdir_path}")
                else:
                    warn(f"Invalid .git file format for {repo_name}")
            except Exception as e:
                warn(f"Error reading .git file for {repo_name}: {e}")

    # Add standard mounts (sharing, context-sync)
    add_standard_mounts(mount_args, quiet=False)

    # Mount host Claude configuration when using host auth mode
    if auth_mode == "host":
        home = Path.home()
        claude_dir = home / ".claude"
        claude_json = home / ".claude.json"

        if claude_dir.is_dir():
            container_claude_dir = f"/home/jib/.claude"
            mount_args.extend(["-v", f"{claude_dir}:{container_claude_dir}:rw"])
            print(f"  • ~/.claude (Claude config directory)")

        if claude_json.is_file():
            container_claude_json = f"/home/jib/.claude.json"
            mount_args.extend(["-v", f"{claude_json}:{container_claude_json}:rw"])
            print(f"  • ~/.claude.json (Claude settings)")

    print()

    # Build docker run command on jib-network (shared network with gateway sidecar)
    # Note: We don't use --rm so we can save logs before cleanup
    worktree_host_path = Config.WORKTREE_BASE / container_id
    cmd = [
        "docker", "run",
        "--security-opt", "label=disable",  # Disable SELinux labeling for faster startup
        "--name", container_id,
        "--network", JIB_NETWORK_NAME,  # Connect to jib-network for gateway access
        "-e", f"RUNTIME_UID={os.getuid()}",
        "-e", f"RUNTIME_GID={os.getgid()}",
        "-e", f"CONTAINER_ID={container_id}",
        "-e", "PYTHONUNBUFFERED=1",  # Force Python to use unbuffered output for real-time streaming
        "-e", f"GATEWAY_URL=http://{GATEWAY_CONTAINER_NAME}:{GATEWAY_PORT}",
        # Host worktree path - needed by git wrapper to translate container paths
        # Container sees /home/user/repos/X, but gateway needs ~/.jib-worktrees/<id>/X
        "-e", f"JIB_WORKTREE_HOST_PATH={worktree_host_path}",
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
        """Save logs and remove container."""
        try:
            # Save container logs before removal (with correlation info)
            save_container_logs(container_id, task_id, thread_ts)
        except Exception as e:
            error(f"Failed to save container logs: {e}")
            # Don't re-raise - continue with container removal
        finally:
            # Remove container
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                error(f"Failed to remove container: {e}")
                # Don't re-raise - original error is more important

    try:
        result = subprocess.run(cmd, timeout=timeout_seconds)
        run_success = result.returncode == 0
    except subprocess.TimeoutExpired:
        print()
        error(f"Container execution timed out after {timeout_minutes} minutes")
        # Kill the container if it's still running
        subprocess.run(["docker", "kill", container_id],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)
    except KeyboardInterrupt:
        print()
        warn("Interrupted by user")
        # Kill container on interrupt
        subprocess.run(["docker", "kill", container_id],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)
    except Exception as e:
        error(f"Failed to run container: {e}")
    finally:
        # Always save logs and cleanup container
        cleanup_container()

    return run_success
