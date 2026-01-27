# Plan: Refactor jib script into multiple modules

## Overview

The `jib-container/jib` script has grown to 2936 lines and needs to be split into logical modules for maintainability. This plan breaks it into a package structure while preserving all functionality.

## Current State

The jib script is a single monolithic Python file containing:
- 2936 lines of code
- 12+ distinct functional areas
- Multiple classes and ~60 functions
- Mixed concerns (config, auth, docker, git, runtime)

## Target Structure

```
jib-container/
├── jib                          # Main entrypoint (slim wrapper, ~50 lines)
└── jib_lib/                     # Package directory
    ├── __init__.py              # Package exports
    ├── cli.py                   # Argument parsing, main() (~150 lines)
    ├── config.py                # Config, Colors, constants (~100 lines)
    ├── output.py                # info/success/warn/error (~50 lines)
    ├── auth.py                  # API keys, GitHub tokens (~260 lines)
    ├── docker.py                # Image building, hash caching (~400 lines)
    ├── gateway.py               # Gateway sidecar management (~170 lines)
    ├── container_logging.py     # Log persistence, correlation (~280 lines)
    ├── worktrees.py             # Git worktree management (~290 lines)
    ├── setup_flow.py            # Interactive setup (~210 lines)
    ├── runtime.py               # run_claude(), exec_in_new_container() (~550 lines)
    └── timing.py                # StartupTimer class (~80 lines)
```

## Module Breakdown

### 1. `jib` (main entrypoint)
**Purpose**: Minimal wrapper that imports and runs the CLI
**Contents**:
- Shebang and docstring
- Import `jib_lib.cli`
- Call `main()`

### 2. `jib_lib/config.py`
**Purpose**: Configuration and constants
**Contents** (from lines 120-341):
- `Colors` class
- `Config` class (paths, constants, dangerous dirs)
- Gateway constants (`GATEWAY_CONTAINER_NAME`, `GATEWAY_PORT`, etc.)
- Platform detection (`get_platform()`)

**Exports**: `Colors`, `Config`, `GATEWAY_*`, `JIB_NETWORK_NAME`, `get_platform`

### 3. `jib_lib/output.py`
**Purpose**: Output utilities (statusbar integration)
**Contents** (from lines 34-163):
- Global `_quiet_mode` flag
- `info()`, `success()`, `warn()`, `error()` functions

**Dependencies**: `statusbar` module, `config.Colors`
**Exports**: `info`, `success`, `warn`, `error`, `_quiet_mode`

### 4. `jib_lib/timing.py`
**Purpose**: Startup timing for debugging
**Contents** (from lines 37-117):
- `StartupTimer` class
- Global `_host_timer` instance

**Exports**: `StartupTimer`, `_host_timer`

### 5. `jib_lib/auth.py`
**Purpose**: Authentication and API key management
**Contents** (from lines 166-523):
- `get_anthropic_api_key()`
- `get_google_api_key()`
- `get_openai_api_key()`
- `get_llm_provider()`
- `get_anthropic_auth_method()`
- `get_github_token()`
- `get_github_readonly_token()`
- `get_github_app_token()`
- `write_github_token_file()`

**Dependencies**: `config.Config`, `output.warn`
**Exports**: All auth functions

### 6. `jib_lib/docker.py`
**Purpose**: Docker image management
**Contents** (from lines 525-1287):
- `check_docker_permissions()`
- `check_docker()`
- `_copy_directory_atomic()`
- `is_dangerous_dir()`
- `create_dockerfile()`
- `get_installed_claude_version()`
- `get_latest_claude_version()`
- `check_claude_update()`
- Build hash functions (`_hash_file`, `_hash_directory`, `compute_build_hash`, etc.)
- `build_image()`
- `image_exists()`
- `ensure_jib_network()`

**Dependencies**: `config.Config`, `output.*`, `timing._host_timer`
**Exports**: All docker functions

### 7. `jib_lib/gateway.py`
**Purpose**: Gateway sidecar container management
**Contents** (from lines 1317-1447):
- `is_gateway_running()`
- `gateway_image_exists()`
- `build_gateway_image()`
- `wait_for_gateway_health()`
- `start_gateway_container()`

**Dependencies**: `config.*`, `output.*`
**Exports**: All gateway functions

### 8. `jib_lib/container_logging.py`
**Purpose**: Container log persistence and correlation
**Contents** (from lines 1450-1722):
- `CONTAINER_LOGS_DIR` constant
- `generate_container_id()`
- `get_docker_log_config()`
- `extract_task_id_from_command()`
- `extract_thread_ts_from_task_file()`
- `update_log_index()`
- `save_container_logs()`

**Dependencies**: `config.Config`, `output.*`
**Exports**: All logging functions

### 9. `jib_lib/worktrees.py`
**Purpose**: Git worktree management
**Contents** (from lines 1725-2013):
- `get_default_branch()`
- `_acquire_git_lock()`
- `_release_git_lock()`
- `create_worktrees()`
- `cleanup_worktrees()`

**Dependencies**: `config.Config`, `output.*`, `jib_config.get_local_repos`
**Exports**: `get_default_branch`, `create_worktrees`, `cleanup_worktrees`

### 10. `jib_lib/setup_flow.py`
**Purpose**: Interactive setup process
**Contents** (from lines 557-694, 2016-2220):
- `get_setup_script_path()`
- `run_setup_script()`
- `check_host_setup()`
- `setup()` (main interactive setup)
- `add_standard_mounts()`

**Dependencies**: `config.*`, `output.*`, `auth.*`, `docker.*`
**Exports**: `check_host_setup`, `setup`, `add_standard_mounts`, `run_setup_script`

### 11. `jib_lib/runtime.py`
**Purpose**: Container execution (interactive and exec modes)
**Contents** (from lines 2244-2785):
- `run_claude()` - interactive mode
- `exec_in_new_container()` - exec mode

**Dependencies**: All other modules
**Exports**: `run_claude`, `exec_in_new_container`

### 12. `jib_lib/cli.py`
**Purpose**: CLI argument parsing and entry point
**Contents** (from lines 2788-2936):
- `main()` function
- Argument parser setup

**Dependencies**: All other modules
**Exports**: `main`

### 13. `jib_lib/__init__.py`
**Purpose**: Package initialization and exports
**Contents**:
- Import and re-export key functions for external use
- Version info (if any)

## Implementation Steps

### Step 1: Create package structure
- Create `jib_lib/` directory
- Create empty `__init__.py`

### Step 2: Extract modules (in dependency order)
1. `config.py` - no internal dependencies
2. `output.py` - depends on config
3. `timing.py` - no internal dependencies
4. `auth.py` - depends on config, output
5. `docker.py` - depends on config, output, timing
6. `gateway.py` - depends on config, output
7. `container_logging.py` - depends on config, output
8. `worktrees.py` - depends on config, output
9. `setup_flow.py` - depends on config, output, auth, docker
10. `runtime.py` - depends on all above
11. `cli.py` - depends on all above

### Step 3: Update main `jib` script
- Replace all code with minimal wrapper
- Import and call `jib_lib.cli.main()`

### Step 4: Update `__init__.py`
- Export commonly used functions
- Maintain backward compatibility

### Step 5: Testing
1. Run `jib --help` to verify CLI works
2. Run `jib` to test interactive mode
3. Run `jib --exec echo test` to test exec mode
4. Run `jib --setup` to verify setup flow

## Critical Files

- `/home/jib/repos/james-in-a-box/jib-container/jib` - Main script to refactor
- `/home/jib/repos/james-in-a-box/jib-container/jib_lib/` - New package directory

## Risks and Mitigations

1. **Import cycles**: Mitigated by careful dependency ordering
2. **Global state**: `_quiet_mode` and `_host_timer` need careful handling - will use module-level singletons
3. **Backward compatibility**: The `jib` script interface remains unchanged

## Test Compatibility

The existing test file at `tests/jib/test_jib.py` loads the jib module using `SourceFileLoader` and expects these imports to work:
- `jib.Colors`
- `jib.Config`
- `jib.get_platform()`
- `jib.get_github_token()`
- `jib.is_dangerous_dir()`
- `jib.generate_container_id()`
- `jib.check_docker_permissions()`
- `jib.image_exists()`
- `jib.cleanup_worktrees()`
- `jib.get_local_repos`
- `jib.get_default_branch()`
- `jib.build_image()`
- `jib.create_dockerfile()`
- `jib.check_claude_update()`
- `jib.should_rebuild_image()`
- `jib.compute_build_hash()`

**Solution**: The main `jib` script will re-export all public symbols from `jib_lib` so that `SourceFileLoader("jib", ...)` continues to work:

```python
#!/usr/bin/env python3
# Re-export all public symbols for backward compatibility (tests use SourceFileLoader)
from jib_lib import *
from jib_lib.cli import main

if __name__ == "__main__":
    main()
```

## Verification

After implementation:
1. `jib --help` - CLI help should work
2. `jib -v` - Verbose mode should show all startup output
3. `jib --setup` - Should delegate to setup.py
4. `jib --exec echo hello` - Should execute in ephemeral container
5. Run tests: `pytest tests/jib/test_jib.py -v`
