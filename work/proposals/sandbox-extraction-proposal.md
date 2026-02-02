# Sandbox Extraction Proposal: Creating a Reusable LLM Containerization Tool

**Status:** Draft for Review
**Version:** 1.1
**Date:** 2026-02-02
**Task:** beads-94eqz

## Executive Summary

This document proposes extracting the sandboxing and gateway sidecar functionality from james-in-a-box into a standalone, reusable repository. The goal is to create a high-quality, well-documented tool that enables safe, unsupervised LLM code execution with infrastructure-level security controls.

**The core principle:** Security through infrastructure, not instructions. An LLM cannot bypass controls that don't exist in its environment.

---

## Table of Contents

1. [Goals and Non-Goals](#1-goals-and-non-goals)
2. [Naming Proposal](#2-naming-proposal)
3. [Components to Extract](#3-components-to-extract)
4. [Components Remaining in james-in-a-box](#4-components-remaining-in-james-in-a-box)
5. [Architecture of the New Tool](#5-architecture-of-the-new-tool)
6. [Integration Model](#6-integration-model)
7. [Quality Standards](#7-quality-standards)
8. [Decisions](#8-decisions)
9. [Implementation Phases](#9-implementation-phases)

---

## 1. Goals and Non-Goals

### Goals

1. **Clean extraction** - Extract sandboxing code from james-in-a-box into a standalone, well-organized repository
2. **Gateway sidecar with policy enforcement** - All git/gh operations routed through a policy-enforcing gateway
3. **Network isolation and allowlisting** - Configurable domain allowlists for both public and private modes
4. **Session-based, per-container access controls** - Support for multi-container environments with isolated sessions
5. **Comprehensive audit logging** - Structured logs for all operations with correlation IDs
6. **Worktree isolation** - Per-container git worktrees preventing cross-contamination
7. **High quality standards** - Comprehensive tests, documentation, and CI/CD
8. **Claude support** - Initial focus on Claude Code (other LLMs can be added later)

### Non-Goals

1. **Slack integration** - Remains in james-in-a-box
2. **Confluence/JIRA sync** - Remains in james-in-a-box
3. **Context sharing directories** - Remains in james-in-a-box
4. **Beads task tracking** - Remains in james-in-a-box
5. **LLM-specific configuration** (e.g., .claude/ rules) - Remains in james-in-a-box
6. **Host services for notifications** - Remains in james-in-a-box

---

## 2. Naming

**Repository:** `egg`
**CLI command:** `egg`
**Config file:** `egg.yaml`

Inspired by Andy Weir's short story "The Egg" - a contained environment where development happens before emerging into the world. The AI works inside the egg; when ready, it "hatches" via human review and merge.

---

## 3. Components to Extract

### 3.1 Gateway Sidecar (Full Extraction)

**Source:** `gateway-sidecar/`

| Component | Description | Modifications Needed |
|-----------|-------------|---------------------|
| `gateway.py` | Flask REST API server | Remove james-specific endpoints |
| `policy.py` | Branch ownership, merge blocking | Generalize user/agent naming |
| `github_client.py` | GitHub token management | Keep as-is |
| `git_client.py` | Git command validation | Keep as-is |
| `session_manager.py` | Per-container session tokens | Keep as-is |
| `token_refresher.py` | GitHub App token refresh | Keep as-is |
| `rate_limiter.py` | Request rate limiting | Keep as-is |
| `worktree_manager.py` | Per-container worktrees | Keep as-is |
| `squid.conf` | Proxy configuration | Make configurable |
| `allowed_domains.txt` | Domain allowlist | Make configurable |
| `Dockerfile` | Gateway container image | Simplify and strip down as needed |
| `entrypoint.py` | Container startup (Python script for maintainability) | Simplify and strip down as needed |

**New additions needed:**
- Configurable domain allowlists (not hardcoded)
- Comprehensive test suite

### 3.2 Container Runtime (Full Extraction)

**Source:** `jib-container/`

| Component | Description | Modifications Needed |
|-----------|-------------|---------------------|
| `Dockerfile` | Container image | Remove james-specific tooling |
| `entrypoint.py` | Container startup | Generalize |
| `scripts/git` | Git wrapper | Keep as-is |
| `scripts/gh` | gh CLI wrapper | Keep as-is |
| `scripts/git-credential-github-token` | Credential helper | Keep as-is |

**Remove:**
- `jib-tasks/` - james-specific task handlers
- `jib-tools/` - james-specific interactive tools
- `.claude/` - Claude-specific configuration
- Beads integration
- Notification integration
- Context sync mounts

### 3.3 Shared Libraries (Selective Extraction)

**Source:** `shared/`

| Component | Extract? | Notes |
|-----------|----------|-------|
| `jib_config/` | Yes | Rename to `egg_config` |
| `jib_logging/` | Yes | Rename to `egg_logging` |
| `git_utils/` | Yes | Keep as-is |
| `notifications/` | No | James-specific |
| `beads/` | No | James-specific |
| `enrichment/` | No | James-specific |
| `text_utils/` | Partial | Basic utilities only |

### 3.4 Documentation (Separate Phase)

Documentation extraction is handled in its own phase (Phase 1.5). Strategy:

| Document Type | Action |
|---------------|--------|
| Gateway architecture | Extract and update for new repo |
| Security proposal | Extract as foundation |
| Implementation plans | **Do not extract** - regenerate as needed |
| README | **Regenerate** - new repo-specific README |
| Package-level docs | **Regenerate** - new package documentation |
| Setup guides | **Regenerate** - new setup flow |
| ADRs | Extract only security-relevant ADRs |

### 3.5 Configuration (New)

**New configuration structure:**

```yaml
# egg.yaml - main configuration (no secrets here)
egg:
  name: "my-sandbox"

  # Git policies
  git:
    branch_prefix: "egg-"  # Branches must start with this
    protected_branches:
      - "main"
      - "master"
    allow_force_push: false
    merge_blocking: true  # Gateway has no merge endpoint

  # Authentication (references secrets.yaml)
  # Supports multiple auth sources, each labeled for traceability
  auth:
    sources:
      - name: "bot-account"
        type: "github_app"  # or "pat"
        # Credentials stored in secrets.yaml
      - name: "personal"
        type: "pat"
    # Associate repos with specific auth sources
    repo_auth:
      "owner/repo1": "bot-account"
      "owner/repo2": "personal"
      "owner/*": "bot-account"  # Wildcard support

  # Repository configuration
  repositories:
    # Which repos are allowed (similar to repositories.yaml)
    allowed:
      - "owner/repo1"
      - "owner/repo2"
      - "owner/*"

  # Audit logging
  logging:
    level: "INFO"
    format: "json"  # or "text"
    output: "stdout"  # or file path
    include_request_body: false  # For debugging

  # Container settings (images built and run locally only)
  container:
    mounts:
      - source: "./workspace"
        target: "/workspace"
        read_only: false
```

```yaml
# secrets.yaml - sensitive credentials (gitignored)
secrets:
  github_app:
    app_id: "123456"
    private_key_path: "/path/to/key.pem"

  pats:
    personal: "ghp_xxxxxxxxxxxx"

  api_keys:
    anthropic: "sk-ant-xxxxxxxxxxxx"
```

**Note:** Network mode (public/private) is configured via CLI parameter only, not in config file, matching current jib behavior.


---

## 4. Components Remaining in james-in-a-box

### 4.1 Host Services

All host services remain in james-in-a-box:

| Service | Purpose | Integration with Sandbox |
|---------|---------|-------------------------|
| `slack-receiver` | Listen for Slack messages | Calls sandbox CLI |
| `slack-notifier` | Send notifications to Slack | Watches output directory |
| `context-sync` | Confluence/JIRA sync | Mounts into container |

### 4.2 Task Processing

| Component | Purpose |
|-----------|---------|
| `jib-tasks/` | Slack/GitHub/JIRA/Confluence processors |
| `jib-tools/` | Interactive tools (discover-tests, etc.) |

### 4.3 Configuration

| Component | Purpose |
|-----------|---------|
| `config/context-filters.yaml` | Content filtering for context sync |
| `.claude/rules/` | Claude Code rules and configuration |
| `.claude/commands/` | Claude Code custom commands |

### 4.4 Beads Integration

The beads task tracking system remains entirely within james-in-a-box.

---

## 5. Architecture of the New Tool

### 5.1 Component Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           egg                                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Gateway Sidecar                               │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │ REST API    │  │ Policy      │  │ Session     │  │ Audit      │  │   │
│  │  │ Server      │  │ Engine      │  │ Manager     │  │ Logger     │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │ Git Client  │  │ GitHub      │  │ Worktree    │  │ Rate       │  │   │
│  │  │             │  │ Client      │  │ Manager     │  │ Limiter    │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │ HTTP Proxy (Squid) - Domain Allowlist                       │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Sandbox Container                               │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │   │
│  │  │ git wrapper │  │ gh wrapper  │  │ LLM CLI (any)               │  │   │
│  │  │ → gateway   │  │ → gateway   │  │ (Claude, Cursor, etc.)      │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────────┘  │   │
│  │                                                                      │   │
│  │  NO: GitHub tokens, SSH keys, direct network access                  │   │
│  │  YES: Workspace files, LLM API access (via proxy)                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         CLI Tool                                     │   │
│  │                                                                      │   │
│  │  egg start [--config egg.yaml] [--private] [--headless]            │   │
│  │  egg stop                                                           │   │
│  │  egg exec <command>                                                 │   │
│  │  egg logs [--follow]                                                │   │
│  │  egg status                                                         │   │
│  │  egg config validate                                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 CLI Commands

The `egg` CLI provides the following commands:

| Command | Description |
|---------|-------------|
| `egg start` | Start the sandbox environment (gateway + container) |
| `egg stop` | Stop the sandbox environment |
| `egg exec <cmd>` | Execute a command inside the sandbox container |
| `egg logs [--follow]` | View container logs |
| `egg status` | Show running containers and health status |
| `egg config validate` | Validate configuration files |

**CLI Flags for `egg start`:**

| Flag | Description |
|------|-------------|
| `--config <path>` | Path to egg.yaml config file (default: `./egg.yaml`) |
| `--private` | Enable private network mode (blocks all external network except Claude API) |
| `--headless` | Run in non-interactive/headless mode (for automation, CI, or scripted workflows) |

**Modes:**

- **Interactive mode (default):** Starts Claude Code in interactive terminal mode
- **Headless mode (`--headless`):** Runs without interactive terminal, suitable for:
  - Automated workflows
  - CI/CD pipelines
  - Scripted task execution
  - Background processing

**Network modes (mutually exclusive):**

- **Public mode (default):** Full internet access, domain allowlist not enforced
- **Private mode (`--private`):** Network locked to Claude API only, strict domain allowlist

### 5.3 API Design

**REST API Endpoints:**

```
# Health
GET  /api/v1/health

# Git Operations
POST /api/v1/git/push          # Push with policy checks
POST /api/v1/git/fetch         # Fetch (read-only)
POST /api/v1/git/clone         # Clone (read-only)
POST /api/v1/git/status        # Status
POST /api/v1/git/execute       # Generic git command (filtered)

# GitHub CLI Operations
POST /api/v1/gh/pr/create      # Create PR
POST /api/v1/gh/pr/list        # List PRs
POST /api/v1/gh/pr/view        # View PR
POST /api/v1/gh/pr/comment     # Comment on PR
POST /api/v1/gh/pr/edit        # Edit PR (ownership check)
POST /api/v1/gh/pr/close       # Close PR (ownership check)
POST /api/v1/gh/execute        # Generic gh command (filtered)
# NOTE: No /api/v1/gh/pr/merge - merge is blocked by design

# Session Management
POST /api/v1/session/create    # Create new session (returns token)
POST /api/v1/session/validate  # Validate session token
DELETE /api/v1/session         # End session

# Configuration
GET  /api/v1/config            # Get current config (sanitized)
GET  /api/v1/config/domains    # Get allowed domains
GET  /api/v1/config/repos      # Get allowed repos
```

---

## 6. Integration Model

### 6.1 How james-in-a-box Uses egg

james-in-a-box will depend on egg and layer additional functionality on top:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           james-in-a-box                                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      Custom Layers                                   │   │
│  │                                                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │ Slack       │  │ Context     │  │ Beads       │  │ .claude/   │  │   │
│  │  │ Integration │  │ Sync        │  │ Tasks       │  │ Rules      │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  │                                                                      │   │
│  └────────────────────────────────────────────────────────────────┬────┘   │
│                                                                   │        │
│                                                                   │        │
│  ┌────────────────────────────────────────────────────────────────▼────┐   │
│  │                      egg (dependency)                       │   │
│  │                                                                      │   │
│  │  Gateway Sidecar │ Sandbox Container │ CLI Tool                     │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Configuration Inheritance

james-in-a-box extends the base sandbox configuration:

```yaml
# james-in-a-box/config.yaml
extends: egg  # Base sandbox config

# james-specific additions
james:
  slack:
    bot_token: "${SLACK_BOT_TOKEN}"
    app_token: "${SLACK_APP_TOKEN}"
    channel: "james-notifications"

  context_sync:
    confluence:
      url: "https://company.atlassian.net/wiki"
      spaces: ["TEAM", "DEV"]
    jira:
      url: "https://company.atlassian.net"
      projects: ["PROJ"]

  beads:
    enabled: true
    path: "~/beads"

  claude:
    rules_dir: ".claude/rules"
    commands_dir: ".claude/commands"

# Override sandbox settings
sandbox:
  container:
    mounts:
      # Base mounts from egg
      - source: "./workspace"
        target: "/workspace"
      # james-specific additions
      - source: "~/context-sync"
        target: "/home/user/context-sync"
        read_only: true
      - source: "~/beads"
        target: "/home/user/beads"
      - source: "~/sharing"
        target: "/home/user/sharing"
```

### 6.3 Container Extension

james-in-a-box extends the base container image:

```dockerfile
# james-in-a-box/Dockerfile
FROM egg:latest

# Add james-specific tools
COPY jib-tools/ /opt/jib-tools/
COPY jib-tasks/ /opt/jib-tasks/

# Add Claude configuration
COPY .claude/ /home/user/.claude/

# Additional dependencies
RUN pip install beads-cli notifications-lib

# Override entrypoint to include james setup
COPY entrypoint.py /opt/james/entrypoint.py
ENTRYPOINT ["/opt/james/entrypoint.py"]
```

---

## 7. Quality Standards

### 7.1 Testing Requirements

**Unit Tests:**
- All policy logic with edge cases
- All API endpoints
- Configuration parsing
- Session management

**Integration Tests:**
- Docker container startup/shutdown
- Gateway → Container communication
- Git operations through gateway
- Network isolation verification
- Policy enforcement end-to-end
- **Full workflow tests with mocked Claude** - ensure secrets propagation, worktrees function, git operations work end-to-end

**Security Tests:**
- Credential isolation verification
- Network escape attempts
- Policy bypass attempts
- Session token security

**Test Framework:**
- pytest for Python tests
- Docker containers for integration tests
- GitHub Actions for CI

**Coverage Requirements:**
- Minimum 80% code coverage
- 100% coverage for security-critical code (policy.py, session_manager.py)

### 7.2 Documentation Requirements

**README.md:**
- Quick start guide
- Architecture overview
- Configuration reference
- CLI reference

**Dedicated Docs:**
- Security model and threat analysis
- Setup guide (detailed)
- Configuration reference (detailed)
- API reference
- Troubleshooting guide

**In-Code Documentation:**
- All public APIs documented
- Type hints throughout
- Docstrings for all modules

### 7.3 Linting and Formatting

**Python:**
- ruff (linting + formatting)
- mypy (type checking)
- bandit (security linting)

**Shell:**
- shellcheck
- shfmt

**Docker:**
- hadolint

**YAML:**
- yamllint

**Markdown:**
- markdownlint

### 7.4 CI/CD Pipeline

```yaml
# .github/workflows/ci.yaml
name: CI

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run linters
        run: make lint

  test-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run unit tests
        run: make test-unit

  test-integration:
    runs-on: ubuntu-latest
    services:
      docker:
        image: docker:dind
    steps:
      - uses: actions/checkout@v4
      - name: Build images
        run: make build
      - name: Run integration tests
        run: make test-integration

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run security scan
        run: make security-scan

  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build docs
        run: make docs
```

### 7.5 Release Process

**For MVP:** No formal release process. Updates are obtained by pulling latest main:
```bash
cd egg && git pull origin main
```

**Future (post-MVP):**
- Semantic versioning (semver)
- Changelog maintained
- GitHub releases (tags only, no binaries)
- Local Docker image builds only (no registry publishing)

---

## 8. Decisions

### 8.1 Naming
- **Repository:** `egg`
- **CLI command:** `egg`
- **Config file:** `egg.yaml`

### 8.2 Scope
- **Proxy:** Keep Squid (maintain consistency with working implementation)
- **Container runtime:** Docker only
- **Host OS:** Linux only initially (macOS support planned for later; Docker-based approach should make this relatively straightforward)
- **LLM support:** Claude only for now

### 8.3 Integration
- **Plugin API:** Not needed yet - keep simple
- **Configuration:** YAML split into `egg.yaml` (config) and `secrets.yaml` (credentials)
- **Secrets:** Local secrets.yaml file only (no Vault/external stores), gitignored

### 8.4 Security
- **Multi-tenancy:** Keep existing behavior (no changes)
- **Audit logging:** Keep existing behavior (local logs)
- **Token handling:** Keep existing behavior (no changes)

### 8.5 Distribution
- **Installation:** Clone repo + run setup script (same as current jib)
- **Setup script:** Should be idempotent and support re-running for updates
- **Docker images:** Local builds only (no registry publishing initially)
- **License:** MIT

### 8.6 Migration Philosophy

**Key principle: Minimize functional changes.**

This is NOT a feature release. The goal is:
- Extract cleanly from james-in-a-box
- Clean up and polish the code
- Add comprehensive test coverage
- Add CI checks and quality gates
- Improve documentation

What we are NOT doing:
- Adding new features (aside from configurable allowed_domains.txt)
- Changing existing behavior
- Supporting additional platforms/tools
- Building distribution infrastructure

**Important:** During extraction, verify we're not missing any policy defaults or behaviors currently in jib. Do a thorough audit of existing policy.py and gateway.py to ensure parity.

---

## 9. Implementation Phases

### Phase 1: Repository Setup and CI

**Goal:** Establish repo with quality infrastructure before any code

**Tasks:**
1. Create new repository with proper structure
2. Set up CI pipeline (GitHub Actions)
   - Linting (ruff, shellcheck, hadolint, yamllint)
   - Type checking (mypy)
   - Security scanning (bandit)
   - Test runner (pytest)
3. Set up pre-commit hooks
4. Create initial README and CONTRIBUTING docs
5. Add MIT license

**Deliverable:** Empty repo with full CI infrastructure

### Phase 1.5: Documentation Extraction

**Goal:** Extract and regenerate documentation for new repo

**Tasks:**
1. Extract gateway architecture documentation
2. Extract security proposal documentation
3. **Do NOT extract** implementation plans (regenerate as needed)
4. Regenerate main README for egg
5. Regenerate package-level documentation
6. Create new setup guide
7. Extract only security-relevant ADRs

**Deliverable:** Clean documentation tailored to egg repository

### Phase 2: Gateway Extraction

**Goal:** Extract and thoroughly test gateway sidecar

**Tasks:**
1. Port gateway-sidecar code (gateway.py, policy.py, session_manager.py, etc.)
2. Port shared libraries (config, logging, git_utils)
3. Review and clean up all ported code
4. Write comprehensive unit tests (target: 90%+ coverage for gateway)
5. Write integration tests for gateway API endpoints
6. Ensure all CI checks pass

**Deliverable:** Gateway sidecar with thorough test coverage

### Phase 3: Container Extraction

**Goal:** Extract container runtime and test end-to-end

**Tasks:**
1. Port container Dockerfile and entrypoint
2. Port git/gh wrappers and credential helpers
3. Port Squid proxy configuration
4. Write integration tests (spin up real containers, test isolation)
5. Write security tests (credential isolation, network escape attempts)
6. Document container architecture

**Deliverable:** Full sandbox with integration test suite

### Phase 4: CLI and Setup

**Goal:** Port CLI and setup scripts

**Tasks:**
1. Port CLI tool (start/stop/exec/logs)
2. Port setup script
3. Port configuration handling
4. Write CLI tests
5. Write setup flow tests
6. Create user documentation (README, setup guide)

**Deliverable:** Working CLI with documentation

### Phase 5: james-in-a-box Integration

**Goal:** Refactor james-in-a-box to depend on egg

**Tasks:**
1. Remove extracted code from james-in-a-box
2. Add egg as a dependency (git submodule or local path)
3. Create james-specific extensions (Dockerfile, entrypoint)
4. Update james configuration to use egg
5. Test full james-in-a-box workflow
6. Update james documentation

**Deliverable:** james-in-a-box working with egg dependency

### Phase 6: Final Polish

**Goal:** Documentation, cleanup, and final testing

**Tasks:**
1. Complete all documentation
2. Code review of entire codebase
3. Final integration testing
4. Security review
5. Performance baseline testing
6. Tag v1.0.0 release

**Deliverable:** Production-ready egg v1.0.0

---

## Appendix A: File Structure for New Repository

**Two-container architecture:**
- **`sandbox/`** - The sandbox container where Claude runs (isolated, no credentials)
- **`gateway/`** - The gateway container running the proxy, git wrappers, and policy enforcement

```
egg/
├── .github/
│   └── workflows/
│       └── ci.yaml              # Lint, test, security scan
├── docs/
│   ├── architecture.md
│   ├── configuration.md
│   ├── security.md
│   ├── api.md
│   ├── setup.md
│   └── troubleshooting.md
├── gateway/
│   ├── __init__.py
│   ├── gateway.py               # Flask REST API server
│   ├── policy.py                # Branch ownership, merge blocking
│   ├── session_manager.py       # Per-container session tokens
│   ├── github_client.py         # GitHub API interactions
│   ├── git_client.py            # Git command execution
│   ├── worktree_manager.py      # Per-container worktrees
│   ├── rate_limiter.py          # Request rate limiting
│   ├── token_refresher.py       # GitHub App token refresh
│   └── config.py                # Configuration loading
├── sandbox/
│   ├── Dockerfile               # Sandbox container image (where Claude runs)
│   ├── entrypoint.py            # Container startup
│   └── scripts/
│       ├── git                  # Git wrapper → gateway
│       ├── gh                   # gh wrapper → gateway
│       └── git-credential-github-token
├── gateway/
│   ├── ... (Python modules)
│   ├── Dockerfile               # Gateway container image (proxy + git wrappers)
│   ├── squid.conf               # Network lockdown config
│   ├── squid-allow-all.conf     # Public mode config
│   └── allowed_domains.txt      # Domain allowlist
├── cli/
│   ├── __init__.py
│   ├── main.py                  # CLI entry point
│   └── commands/
│       ├── start.py
│       ├── stop.py
│       ├── exec.py
│       ├── logs.py
│       └── status.py
├── shared/
│   ├── config/
│   │   ├── __init__.py
│   │   └── loader.py            # Configuration loading
│   └── logging/
│       ├── __init__.py
│       └── structured.py        # Structured JSON logging
├── tests/
│   ├── unit/
│   │   ├── test_policy.py
│   │   ├── test_session.py
│   │   ├── test_git_client.py
│   │   └── test_config.py
│   ├── integration/
│   │   ├── test_gateway_container.py
│   │   ├── test_network_isolation.py
│   │   ├── test_git_operations.py
│   │   └── test_policy_enforcement.py
│   └── security/
│       ├── test_credential_isolation.py
│       ├── test_network_escape.py
│       └── test_policy_bypass.py
├── scripts/
│   └── setup.py                 # Setup script
├── CHANGELOG.md
├── LICENSE                      # MIT
├── Makefile                     # Build, test, lint targets
├── pyproject.toml
├── README.md
├── egg.yaml.example
└── secrets.yaml.example
```

---

## Appendix B: Migration Checklist for james-in-a-box

When integrating egg into james-in-a-box:

**File Path Mappings (james-in-a-box → egg):**

| james-in-a-box | egg |
|----------------|-----|
| `gateway-sidecar/gateway.py` | `gateway/gateway.py` |
| `gateway-sidecar/policy.py` | `gateway/policy.py` |
| `gateway-sidecar/session_manager.py` | `gateway/session_manager.py` |
| `gateway-sidecar/github_client.py` | `gateway/github_client.py` |
| `gateway-sidecar/git_client.py` | `gateway/git_client.py` |
| `gateway-sidecar/worktree_manager.py` | `gateway/worktree_manager.py` |
| `gateway-sidecar/rate_limiter.py` | `gateway/rate_limiter.py` |
| `gateway-sidecar/token_refresher.py` | `gateway/token_refresher.py` |
| `gateway-sidecar/Dockerfile` | `proxy/Dockerfile` |
| `gateway-sidecar/squid.conf` | `proxy/squid.conf` |
| `jib-container/Dockerfile` | `sandbox/Dockerfile` |
| `jib-container/entrypoint.py` | `sandbox/entrypoint.py` |
| `jib-container/scripts/git` | `sandbox/scripts/git` |
| `jib-container/scripts/gh` | `sandbox/scripts/gh` |
| `jib-container/scripts/git-credential-github-token` | `sandbox/scripts/git-credential-github-token` |
| `shared/jib_config/` | `shared/egg_config/` |
| `shared/jib_logging/` | `shared/egg_logging/` |
| `shared/git_utils/` | `shared/git_utils/` |

**Remove from james-in-a-box:**
- [ ] `gateway-sidecar/` directory (except james-specific extensions)
- [ ] `jib-container/Dockerfile` (replace with extension)
- [ ] `jib-container/scripts/git`, `gh`, `git-credential-github-token`
- [ ] `jib-container/entrypoint.py` (replace with extension)
- [ ] `shared/jib_config/` (use egg_config)
- [ ] `shared/jib_logging/` (use egg_logging)
- [ ] Network/proxy configuration

**Keep in james-in-a-box:**
- [ ] `host-services/` (all host services)
- [ ] `jib-container/jib-tasks/`
- [ ] `jib-container/jib-tools/`
- [ ] `jib-container/.claude/`
- [ ] `shared/notifications/`
- [ ] `shared/beads/`
- [ ] `shared/enrichment/`
- [ ] `config/context-filters.yaml`
- [ ] Documentation (james-specific)

**Create new in james-in-a-box:**
- [ ] Dependency on egg
- [ ] Extended Dockerfile inheriting from egg
- [ ] Extended configuration file
- [ ] Migration guide for existing users

---

## Next Steps

1. **Review this proposal** - Final review before implementation begins
2. **Create egg repository** - New repo with CI infrastructure
3. **Begin Phase 1** - Repository setup and CI configuration
4. **Iterate** - Adjust plan as needed during implementation

---

## Appendix C: Future Extensibility

While not implementing plugins in v1.0, the architecture should be designed to allow future extension:

- Policy customization (branch naming rules, allowed operations)
- Additional service connectors (Jira, Confluence, etc.)
- Alternative authentication mechanisms
- Log shipping to external systems

These can be added in future versions without breaking the core API.

---

*This proposal is ready for final approval before implementation begins.*
