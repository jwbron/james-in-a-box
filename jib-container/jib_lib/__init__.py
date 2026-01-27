"""jib_lib - Modular package for the jib container launcher.

This package provides the core functionality for running Claude Code
in an isolated Docker container.

All public symbols are re-exported here for backward compatibility
with tests that use SourceFileLoader to import the jib module.
"""

# Config module exports
# Auth module exports
from .auth import (
    get_anthropic_api_key,
    get_anthropic_auth_method,
    get_github_app_token,
    get_github_readonly_token,
    get_github_token,
    write_github_token_file,
)

# CLI module exports
from .cli import main
from .config import (
    GATEWAY_CONTAINER_NAME,
    GATEWAY_IMAGE_NAME,
    GATEWAY_PORT,
    JIB_NETWORK_NAME,
    Colors,
    Config,
    get_local_repos,
    get_platform,
)

# Container logging module exports
from .container_logging import (
    CONTAINER_LOGS_DIR,
    extract_task_id_from_command,
    extract_thread_ts_from_task_file,
    generate_container_id,
    get_docker_log_config,
    save_container_logs,
    update_log_index,
)

# Docker module exports
from .docker import (
    BUILD_HASH_LABEL,
    build_image,
    check_claude_update,
    check_docker,
    check_docker_permissions,
    compute_build_hash,
    create_dockerfile,
    ensure_jib_network,
    get_installed_claude_version,
    get_latest_claude_version,
    image_exists,
    is_dangerous_dir,
    should_rebuild_image,
)

# Gateway module exports
from .gateway import (
    build_gateway_image,
    gateway_image_exists,
    is_gateway_running,
    start_gateway_container,
    wait_for_gateway_health,
)

# Output module exports
from .output import (
    error,
    get_quiet_mode,
    info,
    set_quiet_mode,
    success,
    warn,
)

# Runtime module exports
from .runtime import (
    exec_in_new_container,
    run_claude,
)

# Setup flow module exports
from .setup_flow import (
    add_standard_mounts,
    check_host_setup,
    get_setup_script_path,
    run_setup_script,
    setup,
)

# Timing module exports
from .timing import (
    StartupTimer,
    _host_timer,
)

# Worktrees module exports
from .worktrees import (
    cleanup_worktrees,
    create_worktrees,
    get_default_branch,
)


# Version info (matches jib script)
__version__ = "1.0.0"
