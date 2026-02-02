# Egg Implementation Plan: Sandbox Extraction from james-in-a-box

**Status:** Implementation Ready
**Version:** 1.0
**Date:** 2026-02-02
**Parent Task:** beads-94eqz
**Proposal:** sandbox-extraction-proposal.md

---

## Overview

This document provides the detailed implementation plan for extracting the sandbox functionality from james-in-a-box into a new repository called "egg". It expands on the proposal with specific tasks, file mappings, parameterization requirements, and test coverage needs.

### Success Criteria

1. **Repository Created**: New `egg` repository with full CI infrastructure
2. **Gateway Extracted**: All gateway-sidecar modules ported with 90%+ test coverage
3. **Container Extracted**: Sandbox container working with end-to-end tests
4. **CLI Working**: Users can run `egg start` to launch a sandbox
5. **james-in-a-box Updated**: Depends on egg, no duplicate code
6. **v1.0.0 Tagged**: Production-ready release

---

## Pre-Extraction Checklist

Before starting implementation:

- [ ] Proposal approved (sandbox-extraction-proposal.md)
- [ ] Repository name available on GitHub
- [ ] MIT license confirmed
- [ ] Phase 1 bead created and claimed

---

## Phase 1: Repository Setup

**Goal:** Establish repository with quality infrastructure before any code
**Bead:** beads-egg-phase1
**Estimated Tasks:** 10

### Task 1.1: Create Repository Structure

**Action:** Create new repository with directory structure

```bash
mkdir -p egg/{gateway,container/scripts,proxy,cli/commands,shared/{config,logging},tests/{unit,integration,security},docs,scripts,.github/workflows}
```

**Files to create:**
- `LICENSE` (MIT)
- `README.md` (initial)
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `.gitignore`

**Validation:** Repository cloned locally, all directories exist

### Task 1.2: Configure pyproject.toml

**Action:** Create Python project configuration

```toml
[project]
name = "egg"
version = "0.1.0"
description = "Sandboxed LLM code execution environment"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = [
    "flask>=3.0.0",
    "waitress>=3.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "PyJWT>=2.8.0",
    "cryptography>=41.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
    "bandit>=1.7.0",
]

[project.scripts]
egg = "cli.main:main"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "C4", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=gateway --cov=shared --cov-report=term-missing"
```

**Validation:** `pip install -e .[dev]` succeeds

### Task 1.3: Create GitHub Actions lint.yml

**Action:** Set up linting workflow

```yaml
# .github/workflows/lint.yml
name: Lint

on: [push, pull_request]

jobs:
  ruff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install ruff
      - run: ruff check .
      - run: ruff format --check .

  mypy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .[dev]
      - run: mypy gateway shared cli

  shellcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: shellcheck scripts/*.sh container/scripts/*

  hadolint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hadolint/hadolint-action@v3.1.0
        with:
          dockerfile: proxy/Dockerfile
      - uses: hadolint/hadolint-action@v3.1.0
        with:
          dockerfile: container/Dockerfile
```

**Validation:** Workflow runs successfully on empty repo

### Task 1.4: Create GitHub Actions test.yml

**Action:** Set up test workflow

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .[dev]
      - run: pytest tests/unit --cov --cov-fail-under=80

  integration:
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:dind
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .[dev]
      - run: make build
      - run: pytest tests/integration

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install bandit
      - run: bandit -r gateway shared cli -ll
```

**Validation:** All jobs pass (even if tests empty initially)

### Task 1.5: Create pre-commit configuration

**Action:** Set up pre-commit hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files

  - repo: https://github.com/koalaman/shellcheck-precommit
    rev: v0.9.0
    hooks:
      - id: shellcheck
```

**Validation:** `pre-commit run --all-files` passes

### Task 1.6: Create Makefile

**Action:** Create build automation

```makefile
.PHONY: lint test build clean

lint:
	ruff check .
	ruff format --check .
	mypy gateway shared cli
	shellcheck scripts/*.sh container/scripts/* || true
	hadolint proxy/Dockerfile container/Dockerfile || true

test:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

test-all:
	pytest tests -v

build:
	docker build -t egg-gateway -f proxy/Dockerfile .
	docker build -t egg-container -f container/Dockerfile .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

dev:
	pip install -e .[dev]
	pre-commit install
```

**Validation:** `make lint` and `make test` run without error

### Task 1.7: Write Initial README.md

**Action:** Create documentation entry point

Content should include:
- What egg does (one paragraph)
- Quick start (3 commands)
- Architecture diagram (ASCII)
- Links to detailed docs
- License

**Validation:** README renders correctly on GitHub

### Task 1.8: Write CONTRIBUTING.md

**Action:** Create contributor guide

Content:
- Development setup instructions
- Code style guidelines
- Testing requirements
- PR process

**Validation:** New contributor can follow guide to set up dev environment

### Task 1.9: Create egg.yaml.example

**Action:** Create example configuration file

```yaml
# egg.yaml.example - Sandbox configuration
sandbox:
  name: "my-sandbox"

  network:
    mode: "private"  # private, public, or allowlist
    allowed_domains:
      - "api.anthropic.com"
      - "api.openai.com"
    # allowed_repos only used when mode is "private"
    allowed_repos:
      - "owner/repo"

  git:
    branch_prefix: "sandbox-"
    protected_branches:
      - "main"
      - "master"
    merge_blocking: true  # No merge endpoint in gateway

  auth:
    # Option 1: GitHub App (recommended)
    github_app_id: "${GITHUB_APP_ID}"
    github_app_private_key_path: "${GITHUB_APP_KEY_PATH}"
    # Option 2: Personal Access Token
    # github_token: "${GITHUB_TOKEN}"

  logging:
    level: "INFO"
    format: "json"

  container:
    image: "egg:latest"
    user: "sandbox"
    home: "/home/sandbox"
```

**Validation:** Example is valid YAML, all fields documented

### Task 1.10: Create Empty Module Structure

**Action:** Create __init__.py files and module stubs

Files:
- `gateway/__init__.py`
- `cli/__init__.py`
- `cli/commands/__init__.py`
- `shared/__init__.py`
- `shared/config/__init__.py`
- `shared/logging/__init__.py`
- `tests/__init__.py`
- `tests/unit/__init__.py`
- `tests/integration/__init__.py`
- `tests/security/__init__.py`

**Validation:** `python -c "import gateway; import cli; import shared"` succeeds

### Phase 1 Gate

**Exit criteria:**
- [ ] All CI workflows pass
- [ ] `make dev` sets up development environment
- [ ] `make lint` runs all linters
- [ ] `make test` runs (empty test suite)
- [ ] README provides clear overview
- [ ] Pre-commit hooks installed and working

---

## Phase 2: Gateway Extraction

**Goal:** Extract and thoroughly test gateway sidecar
**Bead:** beads-egg-phase2
**Estimated Tasks:** 25

### Task 2.1: Create Configuration System

**Action:** Create config loading infrastructure in `shared/config/`

Port and rename from `jib_config`:
- `shared/config/loader.py` - Configuration file loading
- `shared/config/validators.py` - Validation utilities

**Key parameterization:**
- Config file path: `~/.config/egg/egg.yaml` (was `~/.config/jib/`)
- Config env var: `EGG_CONFIG` (was `JIB_CONFIG`)

**Validation:** Config loads from file and environment

### Task 2.2: Create Logging System

**Action:** Port logging infrastructure to `shared/logging/`

Port and rename from `jib_logging`:
- `shared/logging/logger.py` - Logger class
- `shared/logging/formatters.py` - JSON and console formatters
- `shared/logging/context.py` - Context propagation

**Key changes:**
- Logger name: `egg` (was `jib`)
- Import: `from shared.logging import get_logger`

**Validation:** Logs output in JSON and text formats

### Task 2.3: Port github_client.py

**Action:** Port GitHub API client

**Source:** `gateway-sidecar/github_client.py`
**Destination:** `gateway/github_client.py`

**Changes required:**
- Update imports: `from jib_logging import` → `from shared.logging import`
- Remove james-specific comments/references

**Tests to port:**
- (No existing test file - create `tests/unit/test_github_client.py`)

**Validation:** GitHub API calls work, token refresh works

### Task 2.4: Port policy.py

**Action:** Port policy engine

**Source:** `gateway-sidecar/policy.py`
**Destination:** `gateway/policy.py`

**Parameterization required:**

| Current | Parameterized | Config Key |
|---------|---------------|------------|
| `JIB_IDENTITIES` | `SANDBOX_IDENTITIES` | `sandbox.identities` |
| `JIB_BRANCH_PREFIXES = ("jib-", "jib/")` | Configurable | `git.branch_prefix` |
| `"jib[bot]"` | Configurable | `sandbox.bot_name` |

**Tests to port:**
- `tests/test_policy.py` → `tests/unit/test_policy.py`

**Validation:** All policy tests pass with parameterized values

### Task 2.5: Port session_manager.py

**Action:** Port session management

**Source:** `gateway-sidecar/session_manager.py`
**Destination:** `gateway/session_manager.py`

**Parameterization required:**

| Current | Parameterized | Config Key |
|---------|---------------|------------|
| `SESSION_PERSISTENCE_DIR = Path("/tmp/jib-sessions")` | Configurable | `session.persistence_dir` |
| `~/.jib-gateway/sessions.json` | `~/.egg/sessions.json` | - |

**Tests to port:**
- `tests/test_session_manager.py` → `tests/unit/test_session_manager.py`

**Validation:** Sessions persist and validate correctly

### Task 2.6: Port git_client.py

**Action:** Port git command execution

**Source:** `gateway-sidecar/git_client.py`
**Destination:** `gateway/git_client.py`

**Parameterization required:**

| Current | Parameterized | Config Key |
|---------|---------------|------------|
| `"/home/jib/repos/"` | Configurable | `paths.repos_dir` |
| `"/home/jib/.jib-worktrees/"` | Configurable | `paths.worktrees_dir` |
| `"/home/jib/beads/"` | Remove or make optional | - |

**Tests to port:**
- `tests/test_git_client.py` → `tests/unit/test_git_client.py`
- `tests/test_git_validation.py` → `tests/unit/test_git_validation.py`

**Validation:** Git operations execute with path validation

### Task 2.7: Port worktree_manager.py

**Action:** Port worktree management

**Source:** `gateway-sidecar/worktree_manager.py`
**Destination:** `gateway/worktree_manager.py`

**Parameterization required:**

| Current | Parameterized | Config Key |
|---------|---------------|------------|
| `WORKTREE_BASE_DIR = Path("/home/jib/.jib-worktrees")` | Configurable | `paths.worktrees_dir` |
| `REPOS_BASE_DIR = Path("/home/jib/repos")` | Configurable | `paths.repos_dir` |
| `jib/{container_id}/work` branch pattern | Configurable | `git.branch_pattern` |

**Tests to port:**
- `tests/test_worktree_manager.py` → `tests/unit/test_worktree_manager.py`

**Validation:** Worktrees created and cleaned up correctly

### Task 2.8: Port rate_limiter.py

**Action:** Port request rate limiting

**Source:** `gateway-sidecar/rate_limiter.py`
**Destination:** `gateway/rate_limiter.py`

**Changes required:**
- Update imports
- No significant parameterization needed

**Tests to port:**
- `tests/test_rate_limiter.py` → `tests/unit/test_rate_limiter.py`

**Validation:** Rate limits enforced correctly

### Task 2.9: Port token_refresher.py

**Action:** Port GitHub App token refresh

**Source:** `gateway-sidecar/token_refresher.py`
**Destination:** `gateway/token_refresher.py`

**Parameterization required:**

| Current | Parameterized | Config Key |
|---------|---------------|------------|
| `DEFAULT_CONFIG_DIR = Path.home() / ".config" / "jib"` | `~/.config/egg` | - |

**Tests to port:**
- `tests/test_token_refresher.py` → `tests/unit/test_token_refresher.py`

**Validation:** Tokens refresh before expiry

### Task 2.10: Port repo_parser.py

**Action:** Port repository path parsing

**Source:** `gateway-sidecar/repo_parser.py`
**Destination:** `gateway/repo_parser.py`

**Parameterization required:**

| Current | Parameterized | Config Key |
|---------|---------------|------------|
| `~/.jib-worktrees` | Configurable | `paths.worktrees_dir` |

**Tests to port:**
- `tests/test_repo_parser.py` → `tests/unit/test_repo_parser.py`

**Validation:** Paths parsed correctly

### Task 2.11: Port repo_visibility.py

**Action:** Port repository visibility checking

**Source:** `gateway-sidecar/repo_visibility.py`
**Destination:** `gateway/repo_visibility.py`

**Tests to port:**
- `tests/test_repo_visibility.py` → `tests/unit/test_repo_visibility.py`

**Validation:** Public/private detection works

### Task 2.12: Port private_repo_policy.py

**Action:** Port private repository policy

**Source:** `gateway-sidecar/private_repo_policy.py`
**Destination:** `gateway/private_repo_policy.py`

**Tests to port:**
- `tests/test_private_repo_policy.py` → `tests/unit/test_private_repo_policy.py`

**Validation:** Private mode restrictions enforced

### Task 2.13: Port error_messages.py

**Action:** Port error message formatting

**Source:** `gateway-sidecar/error_messages.py`
**Destination:** `gateway/error_messages.py`

**Changes required:**
- Replace "jib" references in user-facing messages
- Make agent name configurable

**Validation:** Error messages display correctly

### Task 2.14: Port fork_policy.py

**Action:** Port fork handling policy

**Source:** `gateway-sidecar/fork_policy.py`
**Destination:** `gateway/fork_policy.py`

**Validation:** Fork operations handled correctly

### Task 2.15: Port config_validator.py

**Action:** Port startup configuration validation

**Source:** `gateway-sidecar/config_validator.py`
**Destination:** `gateway/config_validator.py`

**Parameterization required:**

| Current | Parameterized |
|---------|---------------|
| `~/.jib-gateway` | `~/.egg` |

**Validation:** Startup validation catches missing config

### Task 2.16: Port proxy_monitor.py

**Action:** Port proxy health monitoring

**Source:** `gateway-sidecar/proxy_monitor.py`
**Destination:** `gateway/proxy_monitor.py`

**Validation:** Proxy status correctly reported

### Task 2.17: Port gateway.py (Core API)

**Action:** Port the main Flask API server

**Source:** `gateway-sidecar/gateway.py`
**Destination:** `gateway/gateway.py`

**Parameterization required:**

| Current | Parameterized | Config Key |
|---------|---------------|------------|
| `CONTAINER_HOME = "/home/jib"` | Configurable | `container.home` |
| `"/home/jib/repos/"` | Configurable | `paths.repos_dir` |
| `jib-xxx` container ID examples | `egg-xxx` | - |
| `jib launcher` references | `egg launcher` | - |

**Tests to port:**
- `tests/test_gateway.py` → `tests/unit/test_gateway.py`
- `tests/test_gateway_integration.py` → `tests/integration/test_gateway_api.py`

**Validation:** All API endpoints respond correctly

### Task 2.18: Port test infrastructure (conftest.py)

**Action:** Port test configuration

**Source:** `gateway-sidecar/tests/conftest.py`
**Destination:** `tests/conftest.py`

**Changes required:**
- Update module loading for new structure
- Update path references

**Validation:** All tests can import modules

### Task 2.19: Create gateway/__init__.py exports

**Action:** Define public API

```python
# gateway/__init__.py
from .gateway import app, create_app
from .policy import PolicyEngine, PolicyResult
from .session_manager import SessionManager

__all__ = [
    "app",
    "create_app",
    "PolicyEngine",
    "PolicyResult",
    "SessionManager",
]
```

**Validation:** `from gateway import app` works

### Task 2.20: Write integration tests for gateway API

**Action:** Create comprehensive API tests

**File:** `tests/integration/test_gateway_api.py`

Test scenarios:
- Health check endpoint
- Git push with policy check
- Git fetch (read-only)
- PR creation
- PR comment
- Session creation/validation
- Worktree setup/teardown

**Validation:** All endpoints tested, 90%+ coverage

### Task 2.21: Port security tests

**Action:** Port and expand security tests

**Source:** `gateway-sidecar/tests/test_proxy_security.py`
**Destination:** `tests/security/test_proxy_security.py`

Additional tests:
- Path traversal prevention
- Session token validation
- Rate limiting effectiveness

**Validation:** Security tests pass

### Task 2.22: Create gateway configuration schema

**Action:** Define configuration structure

**File:** `gateway/config.py`

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class GatewayConfig:
    """Gateway configuration."""

    # Paths
    repos_dir: Path = Path("/home/sandbox/repos")
    worktrees_dir: Path = Path("/home/sandbox/.egg-worktrees")
    container_home: Path = Path("/home/sandbox")

    # Identity
    bot_name: str = "egg"
    bot_identities: list[str] = None  # Default: [bot_name, f"{bot_name}[bot]"]
    branch_prefix: str = "egg-"

    # Network
    gateway_port: int = 9847
    proxy_port: int = 3128

    @classmethod
    def from_yaml(cls, path: Path) -> "GatewayConfig":
        """Load configuration from YAML file."""
        ...
```

**Validation:** Config loads with defaults and overrides

### Task 2.23: Update all tests for parameterization

**Action:** Update tests to use configurable values

All tests should:
- Not hardcode `/home/jib` paths
- Use fixtures for config values
- Test with different configurations

**Validation:** Tests pass with different config values

### Task 2.24: Write gateway documentation

**Action:** Create API documentation

**File:** `docs/api.md`

Content:
- All endpoints with request/response examples
- Authentication (session tokens)
- Error codes
- Rate limits

**Validation:** All endpoints documented

### Task 2.25: Verify test coverage

**Action:** Ensure coverage targets met

Run: `pytest --cov=gateway --cov-report=html`

**Targets:**
- gateway.py: 85%+
- policy.py: 95%+
- session_manager.py: 95%+
- git_client.py: 90%+
- Overall gateway/: 90%+

**Validation:** Coverage report meets targets

### Phase 2 Gate

**Exit criteria:**
- [ ] All gateway modules ported
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] 90%+ code coverage for gateway/
- [ ] API documentation complete
- [ ] No hardcoded "jib" references in code
- [ ] Configuration fully parameterized

---

## Phase 3: Container Extraction (Outlined)

**Goal:** Extract container runtime and test end-to-end
**Bead:** beads-egg-phase3

### Tasks (to be detailed)

1. **Port Dockerfile** - Base container image without james-specific tooling
2. **Port entrypoint.py** - Generalize startup, remove james references
3. **Port scripts/git** - Git wrapper calling gateway
4. **Port scripts/gh** - gh CLI wrapper calling gateway
5. **Port scripts/git-credential-github-token** - Credential helper
6. **Create container/scripts/setup.sh** - Container initialization
7. **Port squid.conf** - Proxy configuration
8. **Port squid-allow-all.conf** - Public mode proxy config
9. **Port allowed_domains.txt** - Make configurable
10. **Create proxy/Dockerfile** - Gateway/proxy image
11. **Write container integration tests** - Spin up real containers
12. **Write network isolation tests** - Verify no escape

### Key Parameterization

| Current | Parameterized |
|---------|---------------|
| `/home/jib` | `/home/sandbox` or configurable |
| `jib-gateway` container name | `egg-gateway` |
| `jib-isolated` network | `egg-isolated` |
| `jib-external` network | `egg-external` |
| `jib` user (UID 1000) | `sandbox` user (configurable UID) |

---

## Phase 4: CLI and Setup (Outlined)

**Goal:** Port CLI and setup scripts
**Bead:** beads-egg-phase4

### Tasks (to be detailed)

1. **Create cli/main.py** - Entry point with argparse
2. **Create cli/commands/start.py** - Start sandbox
3. **Create cli/commands/stop.py** - Stop sandbox
4. **Create cli/commands/exec.py** - Run command in sandbox
5. **Create cli/commands/logs.py** - View logs
6. **Create cli/commands/status.py** - Check status
7. **Port setup.sh** - Renamed to scripts/setup.py
8. **Port create-networks.sh** - Network setup
9. **Port start-gateway.sh** - Gateway startup
10. **Write CLI tests** - All commands tested

### Key Parameterization

| Current | Parameterized |
|---------|---------------|
| `jib` command | `egg` command |
| `~/.jib-gateway/` | `~/.egg/` |
| `jib-gateway` image | `egg-gateway` |

---

## Phase 5: james-in-a-box Integration (Outlined)

**Goal:** Refactor james-in-a-box to depend on egg
**Bead:** beads-egg-phase5

### Tasks (to be detailed)

1. **Remove gateway-sidecar/** - All code now in egg
2. **Remove shared/jib_config/** - Use egg's shared/config
3. **Remove shared/jib_logging/** - Use egg's shared/logging
4. **Add egg as submodule** - Or local path dependency
5. **Create james-specific Dockerfile** - Extends egg container
6. **Create james-specific entrypoint** - Adds beads, notifications, etc.
7. **Update configuration** - James config extends egg config
8. **Update jib CLI** - Wraps egg CLI
9. **Port jib-container scripts** - Keep james-specific ones
10. **Test full workflow** - Slack → jib → egg → PR
11. **Update documentation** - Reflect new architecture
12. **Create migration guide** - For existing users

### Directory Structure After

```
james-in-a-box/
├── egg/                    # Submodule or local checkout
├── host-services/          # Unchanged
├── jib-container/
│   ├── Dockerfile          # FROM egg:latest
│   ├── entrypoint.py       # Extends egg entrypoint
│   ├── jib-tasks/          # Unchanged
│   ├── jib-tools/          # Unchanged
│   └── .claude/            # Unchanged
├── shared/
│   ├── beads/              # Unchanged
│   ├── notifications/      # Unchanged
│   └── enrichment/         # Unchanged
└── config/                 # Extends egg config
```

---

## Phase 6: Final Polish (Outlined)

**Goal:** Documentation, cleanup, and final testing
**Bead:** beads-egg-phase6

### Tasks (to be detailed)

1. **Complete all documentation** - README, setup, API, security
2. **Code review** - Full codebase review
3. **Security review** - Penetration testing of isolation
4. **Performance baseline** - Startup time, request latency
5. **Create CHANGELOG** - Document all changes from james-in-a-box
6. **Tag v1.0.0** - First stable release

---

## Appendix A: Complete File Mapping

### Gateway Sidecar Files

| Source (james-in-a-box) | Destination (egg) | Changes |
|-------------------------|-------------------|---------|
| `gateway-sidecar/__init__.py` | `gateway/__init__.py` | Update exports |
| `gateway-sidecar/gateway.py` | `gateway/gateway.py` | Parameterize paths |
| `gateway-sidecar/policy.py` | `gateway/policy.py` | Parameterize identities |
| `gateway-sidecar/session_manager.py` | `gateway/session_manager.py` | Parameterize paths |
| `gateway-sidecar/github_client.py` | `gateway/github_client.py` | Update imports |
| `gateway-sidecar/git_client.py` | `gateway/git_client.py` | Parameterize paths |
| `gateway-sidecar/worktree_manager.py` | `gateway/worktree_manager.py` | Parameterize paths |
| `gateway-sidecar/rate_limiter.py` | `gateway/rate_limiter.py` | Update imports |
| `gateway-sidecar/token_refresher.py` | `gateway/token_refresher.py` | Parameterize paths |
| `gateway-sidecar/repo_parser.py` | `gateway/repo_parser.py` | Parameterize paths |
| `gateway-sidecar/repo_visibility.py` | `gateway/repo_visibility.py` | Update imports |
| `gateway-sidecar/private_repo_policy.py` | `gateway/private_repo_policy.py` | Update imports |
| `gateway-sidecar/error_messages.py` | `gateway/error_messages.py` | Parameterize names |
| `gateway-sidecar/fork_policy.py` | `gateway/fork_policy.py` | Update imports |
| `gateway-sidecar/config_validator.py` | `gateway/config_validator.py` | Parameterize paths |
| `gateway-sidecar/proxy_monitor.py` | `gateway/proxy_monitor.py` | Update imports |
| `gateway-sidecar/parse-git-mounts.py` | `gateway/parse_git_mounts.py` | Rename (no hyphen) |
| `gateway-sidecar/Dockerfile` | `proxy/Dockerfile` | Parameterize user |
| `gateway-sidecar/entrypoint.sh` | `proxy/entrypoint.sh` | Parameterize paths |
| `gateway-sidecar/squid.conf` | `proxy/squid.conf` | Parameterize hostname |
| `gateway-sidecar/squid-allow-all.conf` | `proxy/squid-allow-all.conf` | Parameterize hostname |
| `gateway-sidecar/allowed_domains.txt` | `proxy/allowed_domains.txt` | Keep as template |
| `gateway-sidecar/setup.sh` | `scripts/setup.py` | Convert to Python |
| `gateway-sidecar/create-networks.sh` | `scripts/create_networks.py` | Convert to Python |
| `gateway-sidecar/start-gateway.sh` | `scripts/start_gateway.py` | Convert to Python |
| `gateway-sidecar/gateway-sidecar.service` | `scripts/egg-gateway.service` | Rename references |

### Container Files

| Source (james-in-a-box) | Destination (egg) | Changes |
|-------------------------|-------------------|---------|
| `jib-container/Dockerfile` | `container/Dockerfile` | Remove james-specific |
| `jib-container/entrypoint.py` | `container/entrypoint.py` | Generalize |
| `jib-container/scripts/git` | `container/scripts/git` | Update gateway URL |
| `jib-container/scripts/gh` | `container/scripts/gh` | Update gateway URL |
| `jib-container/scripts/git-credential-github-token` | `container/scripts/git-credential-github-token` | Minimal changes |

### Shared Libraries

| Source (james-in-a-box) | Destination (egg) | Changes |
|-------------------------|-------------------|---------|
| `shared/jib_config/` | `shared/config/` | Rename, trim |
| `shared/jib_logging/` | `shared/logging/` | Rename, trim |
| `shared/git_utils/` | `shared/git_utils/` | Keep as-is |

### Test Files

| Source (james-in-a-box) | Destination (egg) | Changes |
|-------------------------|-------------------|---------|
| `gateway-sidecar/tests/conftest.py` | `tests/conftest.py` | Update paths |
| `gateway-sidecar/tests/test_gateway.py` | `tests/unit/test_gateway.py` | Update imports |
| `gateway-sidecar/tests/test_gateway_integration.py` | `tests/integration/test_gateway_api.py` | Update paths |
| `gateway-sidecar/tests/test_git_client.py` | `tests/unit/test_git_client.py` | Parameterize |
| `gateway-sidecar/tests/test_git_validation.py` | `tests/unit/test_git_validation.py` | Parameterize |
| `gateway-sidecar/tests/test_policy.py` | `tests/unit/test_policy.py` | Parameterize |
| `gateway-sidecar/tests/test_private_repo_policy.py` | `tests/unit/test_private_repo_policy.py` | Update imports |
| `gateway-sidecar/tests/test_proxy_security.py` | `tests/security/test_proxy_security.py` | Update imports |
| `gateway-sidecar/tests/test_rate_limiter.py` | `tests/unit/test_rate_limiter.py` | Update imports |
| `gateway-sidecar/tests/test_repo_parser.py` | `tests/unit/test_repo_parser.py` | Parameterize |
| `gateway-sidecar/tests/test_repo_visibility.py` | `tests/unit/test_repo_visibility.py` | Update imports |
| `gateway-sidecar/tests/test_session_manager.py` | `tests/unit/test_session_manager.py` | Parameterize |
| `gateway-sidecar/tests/test_token_refresher.py` | `tests/unit/test_token_refresher.py` | Parameterize |
| `gateway-sidecar/tests/test_worktree_manager.py` | `tests/unit/test_worktree_manager.py` | Parameterize |

---

## Appendix B: Parameterization Checklist

Every hardcoded value that needs configuration support:

### Paths

| Current Value | Config Key | Default |
|---------------|------------|---------|
| `/home/jib` | `container.home` | `/home/sandbox` |
| `/home/jib/repos` | `paths.repos_dir` | `{container.home}/repos` |
| `/home/jib/.jib-worktrees` | `paths.worktrees_dir` | `{container.home}/.egg-worktrees` |
| `/home/jib/beads` | (remove) | - |
| `~/.config/jib` | `paths.config_dir` | `~/.config/egg` |
| `~/.jib-gateway` | `paths.secrets_dir` | `~/.egg` |
| `/tmp/jib-sessions` | `paths.session_dir` | `/tmp/egg-sessions` |

### Identities

| Current Value | Config Key | Default |
|---------------|------------|---------|
| `"jib"` | `identity.bot_name` | `"egg"` |
| `"jib[bot]"` | `identity.bot_login` | `"{bot_name}[bot]"` |
| `"app/jib"` | (derived) | `"app/{bot_name}"` |
| `"james-in-a-box"` | `identity.github_app_name` | `"egg"` |
| `"james-in-a-box[bot]"` | (derived) | `"{github_app_name}[bot]"` |

### Branch Patterns

| Current Value | Config Key | Default |
|---------------|------------|---------|
| `"jib-"` | `git.branch_prefix` | `"egg-"` |
| `"jib/"` | `git.branch_prefix_slash` | `"{branch_prefix}/"` |
| `"jib/{container_id}/work"` | `git.branch_pattern` | `"{branch_prefix}{container_id}/work"` |

### Network

| Current Value | Config Key | Default |
|---------------|------------|---------|
| `"jib-isolated"` | `network.isolated_name` | `"egg-isolated"` |
| `"jib-external"` | `network.external_name` | `"egg-external"` |
| `"jib-gateway"` | `network.gateway_container` | `"egg-gateway"` |
| `172.30.0.0/24` | `network.isolated_subnet` | `172.30.0.0/24` |
| `172.31.0.0/24` | `network.external_subnet` | `172.31.0.0/24` |

### Ports

| Current Value | Config Key | Default |
|---------------|------------|---------|
| `9847` | `gateway.port` | `9847` |
| `3128` | `proxy.port` | `3128` |

### Container

| Current Value | Config Key | Default |
|---------------|------------|---------|
| `"jib-gateway"` | `container.gateway_image` | `"egg-gateway"` |
| `"jib"` user | `container.user` | `"sandbox"` |
| `1000` (UID) | `container.uid` | `1000` |
| `1000` (GID) | `container.gid` | `1000` |

---

## Appendix C: Test Coverage Matrix

Target coverage by module:

| Module | Target | Priority | Notes |
|--------|--------|----------|-------|
| `gateway/gateway.py` | 85% | High | Main API, many paths |
| `gateway/policy.py` | 95% | Critical | Security-critical |
| `gateway/session_manager.py` | 95% | Critical | Security-critical |
| `gateway/git_client.py` | 90% | High | Path validation critical |
| `gateway/github_client.py` | 80% | Medium | External API |
| `gateway/worktree_manager.py` | 85% | High | Isolation critical |
| `gateway/rate_limiter.py` | 90% | Medium | Simple logic |
| `gateway/token_refresher.py` | 80% | Medium | External API |
| `gateway/repo_parser.py` | 90% | High | Path handling |
| `gateway/repo_visibility.py` | 85% | Medium | External API |
| `gateway/private_repo_policy.py` | 90% | High | Policy logic |
| `gateway/error_messages.py` | 70% | Low | Display only |
| `gateway/fork_policy.py` | 85% | Medium | Policy logic |
| `gateway/config_validator.py` | 80% | Medium | Startup only |
| `gateway/proxy_monitor.py` | 70% | Low | Monitoring only |
| `shared/config/*` | 85% | Medium | Config loading |
| `shared/logging/*` | 70% | Low | Infrastructure |
| `cli/*` | 80% | Medium | User interface |

**Integration tests:**
- Gateway API endpoints: All covered
- Container startup/shutdown: Covered
- Network isolation: Covered
- Worktree lifecycle: Covered

**Security tests:**
- Path traversal: Covered
- Token isolation: Covered
- Network escape: Covered
- Session hijacking: Covered

---

## Dependencies

### Python Dependencies

From Dockerfile and module imports:

```
flask>=3.0.0
waitress>=3.0.0
pyyaml>=6.0
requests>=2.31.0
PyJWT>=2.8.0
cryptography>=41.0.0
```

### System Dependencies (Container)

```
git
gh (GitHub CLI)
squid-openssl
openssl
gosu
curl
python3.11
```

### Shared Module Dependencies

The gateway imports from `shared/`:
- `jib_logging` → `shared/logging`
- `jib_config` → `shared/config` (partial - GatewayConfig only)

Files to extract from `shared/jib_logging/`:
- `__init__.py`
- `logger.py`
- `formatters.py`
- `context.py`
- `model_capture.py` (optional - may not be needed)

---

## Phase Tracking Beads

Create the following beads for tracking:

```bash
# Phase 1
bd --allow-stale create "Egg Phase 1: Repository Setup" \
  -l "egg,phase-1,infrastructure" \
  -d "Create egg repository with CI infrastructure, linting, and project setup"

# Phase 2
bd --allow-stale create "Egg Phase 2: Gateway Extraction" \
  -l "egg,phase-2,gateway" \
  -d "Port all gateway-sidecar modules to egg with parameterization and tests"

# Phase 3
bd --allow-stale create "Egg Phase 3: Container Extraction" \
  -l "egg,phase-3,container" \
  -d "Port container Dockerfile, entrypoint, and scripts to egg"

# Phase 4
bd --allow-stale create "Egg Phase 4: CLI and Setup" \
  -l "egg,phase-4,cli" \
  -d "Create egg CLI tool and setup scripts"

# Phase 5
bd --allow-stale create "Egg Phase 5: james-in-a-box Integration" \
  -l "egg,phase-5,integration" \
  -d "Refactor james-in-a-box to depend on egg"

# Phase 6
bd --allow-stale create "Egg Phase 6: Final Polish" \
  -l "egg,phase-6,release" \
  -d "Documentation, security review, and v1.0.0 release"

# Link all to parent
bd --allow-stale update beads-94eqz --append-notes "Implementation plan created. Phase beads: beads-egg-phase1 through beads-egg-phase6"
```

---

*This implementation plan is ready for review and approval before beginning Phase 1.*
