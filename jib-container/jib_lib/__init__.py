"""jib_lib - Modular package for the jib container launcher.

This package provides the core functionality for running Claude Code
in an isolated Docker container.

All public symbols are re-exported here for backward compatibility
with tests that use SourceFileLoader to import the jib module.
"""

# Config module exports
from .config import (
    Colors,
    Config,
    GATEWAY_CONTAINER_NAME,
    GATEWAY_IMAGE_NAME,
    GATEWAY_PORT,
    JIB_NETWORK_NAME,
    get_platform,
    get_local_repos,
)

# Output module exports
from .output import (
    info,
    success,
    warn,
    error,
    set_quiet_mode,
    get_quiet_mode,
)

# Timing module exports
from .timing import (
    StartupTimer,
    _host_timer,
)

# Auth module exports
from .auth import (
    get_anthropic_api_key,
    get_anthropic_auth_method,
    get_github_token,
    get_github_readonly_token,
    get_github_app_token,
    write_github_token_file,
)

# Docker module exports
from .docker import (
    check_docker_permissions,
    check_docker,
    is_dangerous_dir,
    create_dockerfile,
    get_installed_claude_version,
    get_latest_claude_version,
    check_claude_update,
    compute_build_hash,
    should_rebuild_image,
    build_image,
    image_exists,
    ensure_jib_network,
    BUILD_HASH_LABEL,
    CONTAINER_LOGS_DIR,
)

# Gateway module exports
from .gateway import (
    is_gateway_running,
    gateway_image_exists,
    build_gateway_image,
    wait_for_gateway_health,
    start_gateway_container,
)

# Container logging module exports
from .container_logging import (
    generate_container_id,
    get_docker_log_config,
    extract_task_id_from_command,
    extract_thread_ts_from_task_file,
    update_log_index,
    save_container_logs,
)

# Worktrees module exports
from .worktrees import (
    get_default_branch,
    create_worktrees,
    cleanup_worktrees,
)

# Setup flow module exports
from .setup_flow import (
    get_setup_script_path,
    run_setup_script,
    check_host_setup,
    setup,
    add_standard_mounts,
)

# Runtime module exports
from .runtime import (
    run_claude,
    exec_in_new_container,
)

# CLI module exports
from .cli import main

# Version info (matches jib script)
__version__ = "1.0.0"
