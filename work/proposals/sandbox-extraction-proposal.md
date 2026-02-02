# Sandbox Extraction Proposal: Creating a Reusable LLM Containerization Tool

**Status:** Draft for Review
**Version:** 1.0
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
8. [Open Questions](#8-open-questions)
9. [Implementation Phases](#9-implementation-phases)

---

## 1. Goals and Non-Goals

### Goals

1. **Reusable containerization** - A tool that works with any LLM CLI (Claude Code, Cursor, Aider, etc.), not just Claude
2. **Gateway sidecar with policy enforcement** - All git/gh operations routed through a policy-enforcing gateway
3. **Network isolation and allowlisting** - Configurable domain allowlists for both public and private modes
4. **Session-based, per-container access controls** - Support for multi-container environments with isolated sessions
5. **Comprehensive audit logging** - Structured logs for all operations with correlation IDs
6. **Worktree isolation** - Per-container git worktrees preventing cross-contamination
7. **High quality standards** - Comprehensive tests, documentation, and CI/CD
8. **Extensibility** - Clear extension points for additional connectors (Jira, Confluence, etc.)

### Non-Goals

1. **Slack integration** - Remains in james-in-a-box
2. **Confluence/JIRA sync** - Remains in james-in-a-box
3. **Context sharing directories** - Remains in james-in-a-box
4. **Beads task tracking** - Remains in james-in-a-box
5. **LLM-specific configuration** (e.g., .claude/ rules) - Remains in james-in-a-box
6. **Host services for notifications** - Remains in james-in-a-box

---

## 2. Naming Proposal

The tool name should communicate:
- Security/isolation
- LLM/AI focus
- Containerization

### Primary Proposal: `llm-sandbox`

Simple, descriptive, and clear. Indicates both the target (LLMs) and the approach (sandboxing).

### Alternative Names

| Name | Pros | Cons |
|------|------|------|
| `llm-sandbox` | Clear, descriptive | Generic |
| `agent-sandbox` | Broader applicability | Less specific to LLMs |
| `code-sandbox` | Emphasizes code execution | Doesn't convey LLM focus |
| `llm-containment` | Security-focused | Verbose |
| `silo` | Short, evocative | May be too generic |
| `llm-cage` | Security-focused, memorable | Slightly aggressive connotation |
| `sandbox-sidecar` | Describes architecture | Technical |

**Recommendation:** `llm-sandbox` for the repo name, with `sandbox` as the CLI command.

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
| `Dockerfile` | Gateway container image | Simplify |
| `entrypoint.sh` | Container startup | Simplify |

**New additions needed:**
- Configurable domain allowlists (not hardcoded)
- Configurable repository allowlists
- Plugin system for additional connectors
- OpenAPI/Swagger documentation

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
| `jib_config/` | Yes | Rename to `sandbox_config` |
| `jib_logging/` | Yes | Rename to `sandbox_logging` |
| `git_utils/` | Yes | Keep as-is |
| `notifications/` | No | James-specific |
| `beads/` | No | James-specific |
| `enrichment/` | No | James-specific |
| `text_utils/` | Partial | Basic utilities only |

### 3.4 Documentation (Selective Extraction)

**Source:** `docs/`

| Document | Extract? | Notes |
|----------|----------|-------|
| Security proposal | Yes | Foundation for new docs |
| Gateway architecture | Yes | Update for new repo |
| Setup guides | Partial | Create new setup flow |
| ADRs (implemented) | Partial | Relevant security ADRs |

### 3.5 Configuration (New)

**New configuration structure:**

```yaml
# sandbox-config.yaml
sandbox:
  name: "my-sandbox"

  # Network mode
  network:
    mode: "private"  # or "public" or "allowlist"
    allowed_domains:
      - "api.anthropic.com"
      - "api.openai.com"
      - "github.com"
      - "api.github.com"
      - "*.githubusercontent.com"
    allowed_repos:
      - "owner/repo1"
      - "owner/repo2"
      - "owner/*"  # Wildcard support

  # Git policies
  git:
    branch_prefix: "sandbox-"  # Branches must start with this
    protected_branches:
      - "main"
      - "master"
    allow_force_push: false
    merge_blocking: true  # Gateway has no merge endpoint

  # Authentication
  auth:
    github_app_id: "${GITHUB_APP_ID}"
    github_app_private_key_path: "/path/to/key.pem"
    # Or use PAT
    github_token: "${GITHUB_TOKEN}"

  # Audit logging
  logging:
    level: "INFO"
    format: "json"  # or "text"
    output: "stdout"  # or file path
    include_request_body: false  # For debugging

  # Container settings
  container:
    image: "llm-sandbox:latest"
    network: "sandbox-isolated"
    mounts:
      - source: "./workspace"
        target: "/workspace"
        read_only: false
    environment:
      - "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}"
```

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
│                           llm-sandbox                                       │
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
│  │  sandbox start [--config sandbox.yaml] [--llm claude|cursor|aider]   │   │
│  │  sandbox stop                                                        │   │
│  │  sandbox exec <command>                                              │   │
│  │  sandbox logs [--follow]                                             │   │
│  │  sandbox status                                                      │   │
│  │  sandbox config validate                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 API Design

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

### 5.3 Extension Points

The tool should be designed with clear extension points:

1. **Policy Plugins** - Custom policy rules for specific use cases
2. **Connector Plugins** - Additional service connectors (Jira, Confluence, etc.)
3. **Authentication Providers** - Support for different auth mechanisms
4. **Audit Backends** - Log shipping to various destinations

Example plugin interface:

```python
class PolicyPlugin:
    """Base class for policy plugins."""

    def validate_git_push(self, session: Session, request: GitPushRequest) -> PolicyResult:
        """Validate a git push request."""
        raise NotImplementedError

    def validate_gh_command(self, session: Session, request: GhCommandRequest) -> PolicyResult:
        """Validate a gh CLI command."""
        raise NotImplementedError


class ConnectorPlugin:
    """Base class for service connectors."""

    def get_api_routes(self) -> list[Route]:
        """Return API routes for this connector."""
        raise NotImplementedError

    def validate_request(self, session: Session, request: Request) -> PolicyResult:
        """Validate a request to this connector."""
        raise NotImplementedError
```

---

## 6. Integration Model

### 6.1 How james-in-a-box Uses llm-sandbox

james-in-a-box will depend on llm-sandbox and layer additional functionality on top:

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
│  │                      llm-sandbox (dependency)                       │   │
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
extends: llm-sandbox  # Base sandbox config

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
      # Base mounts from llm-sandbox
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
FROM llm-sandbox:latest

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
- API reference (OpenAPI/Swagger)
- Extension guide (plugins)
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

- Semantic versioning (semver)
- Changelog maintained
- GitHub releases with binaries
- Docker images published to registry
- PyPI package (if applicable)

---

## 8. Open Questions

### 8.1 Naming

1. **Repository name:** `llm-sandbox` vs alternatives?
2. **CLI command name:** `sandbox` vs `llm-sandbox` vs something else?
3. **Package name:** Same as repo or different?

### 8.2 Scope

1. **Proxy implementation:** Keep Squid or switch to something lighter (e.g., custom Go proxy)?
2. **Container runtime:** Docker only or support Podman?
3. **Host OS support:** Linux only or also macOS/Windows?
4. **Multiple LLM support:** How to handle different LLM CLI tools in the same container?

### 8.3 Integration

1. **Plugin API stability:** What level of API stability do we commit to?
2. **Configuration format:** YAML only or also JSON/TOML?
3. **Secrets management:** Support for external secret stores (Vault, etc.)?

### 8.4 Security

1. **Multi-tenancy:** Support multiple users/orgs with isolated configs?
2. **Audit log destination:** Local only or cloud logging integration?
3. **Token rotation:** Automated rotation for long-running containers?

### 8.5 Distribution

1. **Installation method:** pip, brew, apt, docker-only?
2. **Pre-built images:** Publish to Docker Hub, ghcr.io, or both?
3. **License:** Apache 2.0, MIT, or something else?

---

## 9. Implementation Phases

### Phase 1: Foundation (Week 1-2)

**Goal:** Establish repo structure and core gateway functionality

**Tasks:**
1. Create new repository with CI/CD setup
2. Port gateway-sidecar core (gateway.py, policy.py, session_manager.py)
3. Port git/gh wrappers and credential helpers
4. Create base Dockerfile for gateway
5. Write unit tests for core functionality
6. Create initial documentation (README, architecture)

**Deliverable:** Gateway sidecar running with basic git operations

### Phase 2: Container Runtime (Week 3-4)

**Goal:** Complete container sandboxing

**Tasks:**
1. Create sandbox container Dockerfile
2. Port network isolation setup (Squid proxy)
3. Implement configurable domain allowlists
4. Create container entrypoint
5. Write integration tests (gateway ↔ container)
6. Document container setup

**Deliverable:** Full sandbox with network isolation

### Phase 3: CLI and Configuration (Week 5-6)

**Goal:** User-friendly CLI and configuration

**Tasks:**
1. Create CLI tool (`sandbox start/stop/exec/logs`)
2. Implement configuration file parsing
3. Add configuration validation
4. Create setup wizard
5. Write CLI tests
6. Document CLI and configuration

**Deliverable:** Complete CLI for sandbox management

### Phase 4: Security Hardening (Week 7-8)

**Goal:** Comprehensive security testing and hardening

**Tasks:**
1. Security audit of all components
2. Penetration testing (escape attempts, bypass attempts)
3. Add security-focused tests to CI
4. Create security documentation
5. Address any findings

**Deliverable:** Security-audited release candidate

### Phase 5: james-in-a-box Integration (Week 9-10)

**Goal:** Refactor james-in-a-box to use llm-sandbox

**Tasks:**
1. Add llm-sandbox as dependency
2. Create james-specific container extension
3. Migrate configuration to new format
4. Update host services to use new CLI
5. Integration testing
6. Documentation updates

**Deliverable:** james-in-a-box using llm-sandbox

### Phase 6: Polish and Release (Week 11-12)

**Goal:** Production-ready release

**Tasks:**
1. Performance optimization
2. Documentation review and completion
3. Create examples and tutorials
4. Publish to package registries
5. Create release notes
6. Announce release

**Deliverable:** v1.0.0 release

---

## Appendix A: File Structure for New Repository

```
llm-sandbox/
├── .github/
│   └── workflows/
│       ├── ci.yaml
│       ├── release.yaml
│       └── security.yaml
├── docs/
│   ├── architecture.md
│   ├── configuration.md
│   ├── security.md
│   ├── api.md
│   ├── setup.md
│   ├── troubleshooting.md
│   └── extensions.md
├── gateway/
│   ├── __init__.py
│   ├── gateway.py
│   ├── policy.py
│   ├── session_manager.py
│   ├── github_client.py
│   ├── git_client.py
│   ├── worktree_manager.py
│   ├── rate_limiter.py
│   ├── audit_logger.py
│   └── config.py
├── container/
│   ├── Dockerfile
│   ├── entrypoint.py
│   └── scripts/
│       ├── git
│       ├── gh
│       └── git-credential-github-token
├── proxy/
│   ├── squid.conf.template
│   └── allowed_domains.txt.example
├── cli/
│   ├── __init__.py
│   ├── main.py
│   ├── commands/
│   │   ├── start.py
│   │   ├── stop.py
│   │   ├── exec.py
│   │   ├── logs.py
│   │   ├── status.py
│   │   └── config.py
│   └── utils.py
├── shared/
│   ├── config/
│   │   ├── __init__.py
│   │   └── loader.py
│   └── logging/
│       ├── __init__.py
│       └── structured.py
├── plugins/
│   ├── __init__.py
│   └── base.py
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
├── examples/
│   ├── basic/
│   │   └── sandbox-config.yaml
│   ├── multi-repo/
│   │   └── sandbox-config.yaml
│   └── custom-policy/
│       ├── sandbox-config.yaml
│       └── custom_policy.py
├── CHANGELOG.md
├── LICENSE
├── Makefile
├── pyproject.toml
├── README.md
└── sandbox-config.yaml.example
```

---

## Appendix B: Migration Checklist for james-in-a-box

When integrating llm-sandbox into james-in-a-box:

**Remove from james-in-a-box:**
- [ ] `gateway-sidecar/` directory (except james-specific extensions)
- [ ] `jib-container/Dockerfile` (replace with extension)
- [ ] `jib-container/scripts/git`, `gh`, `git-credential-github-token`
- [ ] `jib-container/entrypoint.py` (replace with extension)
- [ ] `shared/jib_config/` (use sandbox_config)
- [ ] `shared/jib_logging/` (use sandbox_logging)
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
- [ ] Dependency on llm-sandbox
- [ ] Extended Dockerfile inheriting from llm-sandbox
- [ ] Extended configuration file
- [ ] Migration guide for existing users

---

## Feedback Requested

Please provide feedback on the following:

1. **Naming:** Preference among the proposed names?
2. **Scope:** Any features that should be added or removed?
3. **Architecture:** Concerns about the proposed structure?
4. **Quality standards:** Are the testing/documentation requirements appropriate?
5. **Timeline:** Is the phased approach realistic?
6. **Open questions:** Preferences on any of the open questions?

---

*Document generated for PR review and iteration. Comments and suggestions welcome.*
