# Phase 1: Codebase Inventory

> **Generated:** 2026-01-23
> **Status:** Complete
> **Bead:** beads-g37a

## 1.1 Directory Structure Catalog

| Directory | Purpose | Key Contents |
|-----------|---------|--------------|
| `bin/` | Executable symlinks | 31 commands (symlinks to host-services and scripts) |
| `config/` | Configuration templates | host_config.py, repo_config.py |
| `docs/` | Documentation | 108 markdown files across 15 subdirectories |
| `gateway-sidecar/` | Policy enforcement gateway | gateway.py (1,066 lines), policy.py (733 lines) |
| `host-services/` | Host-side services | 4 categories: analysis/, slack/, sync/, utilities/ |
| `jib-container/` | Container contents | entrypoint.py, .claude/, jib-tasks/, jib-tools/, llm/ |
| `scripts/` | Utility scripts | fix-doc-links.py, migrate-config.py, validation |
| `shared/` | Shared Python modules | beads/, jib_config/, jib_logging/, notifications/ |
| `tests/` | Test suite | 49 test files across 11 subdirectories |

### Host Services Breakdown

| Service Category | Services |
|-----------------|----------|
| `analysis/` | adr-researcher, analyze-pr, beads-analyzer, doc-generator, feature-analyzer, index-generator, inefficiency-detector, repo-onboarding, spec-enricher, trace-collector |
| `slack/` | slack-notifier, slack-receiver |
| `sync/` | context-sync (with connectors/) |
| `utilities/` | jib-logs, service-failure-notify, worktree-watcher |

### Container Structure

| Directory | Purpose |
|-----------|---------|
| `.claude/` | Agent configuration (commands/, hooks/, rules/) |
| `bin/` | Container-internal binaries |
| `jib-tasks/` | Task processors (adr/, analysis/, confluence/, github/, jira/, slack/) |
| `jib-tools/` | Interactive tools |
| `llm/` | LLM interface (claude/, gemini/) |
| `scripts/` | Container utility scripts |

## 1.2 Feature Inventory

**Total Features:** 53 top-level (127 with sub-features)

| Category | Count | Status Notes |
|----------|-------|--------------|
| Communication | 4 | Core functionality |
| Context Management | 8 | Core functionality |
| GitHub Integration | 7 | Core functionality |
| Self-Improvement System | 3 | **Experimental** |
| Documentation System | 10 | **Mostly experimental** |
| Custom Commands | 1 | 3 sub-commands |
| LLM Providers | 3 | **2 confirmed for removal** (#35 Gemini, #36 Router) |
| Container Infrastructure | 5 | Core functionality |
| Utilities | 7 | Core functionality |
| Security Features | 1 | Core functionality |
| Configuration | 3 | Core functionality |

### Features Confirmed for Removal (Phase 4)

| Feature # | Name | Reason |
|-----------|------|--------|
| 35 | Gemini CLI Integration | Simplify to single provider |
| 36 | Claude Code Router Support | Simplify to single provider |
| 34 | Multi-Provider LLM Module | Simplify after #35/#36 removal |

## 1.3 Documentation Inventory

**Total Documentation Files:** 108 markdown files

| Location | Type | Count |
|----------|------|-------|
| `docs/` root | Main docs | 4 (index.md, FEATURES.md, DEEP-CLEAN-PLAN.md, README.md) |
| `docs/adr/` | ADRs | 12 (4 implemented, 4 in-progress, 3 not-implemented + README) |
| `docs/analysis/` | Analysis reports | 6 |
| `docs/architecture/` | Architecture docs | 3 |
| `docs/audits/` | Feature audits | 3 |
| `docs/development/` | Dev guides | 4 |
| `docs/features/` | Feature docs | 8 |
| `docs/generated/` | Auto-generated | 7 |
| `docs/reference/` | Reference docs | 8 |
| `docs/reinforcements/` | Reinforcement docs | 1 |
| `docs/setup/` | Setup guides | 5 |
| `docs/troubleshooting/` | Troubleshooting | 0 |
| `docs/user-guide/` | User guides | 1 |
| Component READMEs | Scattered | ~40 |

### ADR Status Summary

| Status | Count | Files |
|--------|-------|-------|
| Implemented | 4 | Context-Sync-Strategy, Feature-Analyzer-Doc-Sync, LLM-Doc-Index-Strategy, LLM-Inefficiency-Reporting |
| In-Progress | 4 | Autonomous-Software-Engineer, Internet-Tool-Access-Lockdown, Jib-Repo-Onboarding, Standardized-Logging-Interface |
| Not-Implemented | 3 | Declarative-Setup-Architecture, Jib-Repo-Onboarding (duplicate?), Multi-Agent-Pipeline-Architecture |

**Note:** ADR-Jib-Repo-Onboarding appears in both in-progress and not-implemented directories.

## 1.4 Test Inventory

**Total Test Files:** 49

| Directory | Test Files | Coverage Area |
|-----------|------------|---------------|
| `tests/config/` | 1 | Repository configuration |
| `tests/context_sync/` | 7 | Sync connectors (confluence, jira, github, base) |
| `tests/host_services/` | 6 | Host services (slack, trace, conversation) |
| `tests/index_generator/` | 2 | Index generation and queries |
| `tests/jib/` | 3 | Container (docker, entrypoint, jib) |
| `tests/jib_config/` | 5 | Configuration framework |
| `tests/jib_tasks/` | 6 | Task processors (sprint, confluence, github, jira, pr, incoming) |
| `tests/jib_tools/` | 1 | Tools (discover-tests) |
| `tests/shared/` | 2 | Notifications |
| `tests/shared/jib_logging/` | 9 | Logging framework and wrappers |
| `tests/spec_enricher/` | 1 | Spec enricher |
| `tests/` root | 2 | Syntax validation (bash, python) |

## 1.5 Large File Decomposition Analysis

### Python Files > 500 Lines

| File | Lines | Responsibilities | Decomposition Priority |
|------|-------|------------------|----------------------|
| `jib-container/jib-tasks/analysis/feature_analyzer.py` | 3,765 | Feature detection, extraction, formatting | High - multiple concerns |
| `setup.py` | 2,073 | Package setup (generated) | Low - standard setup |
| `jib-container/jib-tasks/analysis/analysis-processor.py` | 1,899 | Task routing, multiple handlers | Medium - single entry point |
| `jib-container/jib-tasks/analysis/beads-analyzer-processor.py` | 1,836 | Beads analysis, reporting | Medium |
| `jib-container/jib-tasks/github/github-processor.py` | 1,559 | GitHub event handling | Medium |
| `host-services/analysis/adr-researcher/adr-researcher.py` | 1,508 | ADR research pipeline | Medium |
| `jib-container/jib-tasks/github/comment-responder.py` | 1,353 | PR comment handling | Low - focused scope |
| `jib-container/jib-tasks/analysis/doc-generator-processor.py` | 1,242 | Doc generation | Low |
| `jib-container/entrypoint.py` | 1,132 | Container startup | High - mixed concerns |
| `host-services/sync/context-sync/connectors/confluence/sync.py` | 1,067 | Confluence sync | Medium |
| `host-services/slack/slack-receiver/slack-receiver.py` | 1,066 | Slack message handling | Medium |
| `gateway-sidecar/gateway.py` | 1,066 | Policy gateway | Low - core gateway |

### Shell Scripts > 200 Lines

| File | Lines | Purpose | Decomposition Priority |
|------|-------|---------|----------------------|
| `jib-container/jib` | 2,669 | Container launcher | High - many responsibilities |
| `gateway-sidecar/tests/integration_test.sh` | 661 | Integration tests | Low - test file |
| `scripts/test-config-migration.sh` | 441 | Migration tests | Low - test file |
| `host-services/analysis/doc-generator/setup.sh` | 397 | Service setup | Low |
| `host-services/utilities/worktree-watcher/worktree-watcher.sh` | 272 | Worktree cleanup | Low |
| `gateway-sidecar/setup.sh` | 267 | Gateway setup | Low |

### Decomposition Proposals

#### High Priority: `jib-container/jib` (2,669 lines)

**Current Responsibilities:**
1. CLI argument parsing
2. Container lifecycle management (start/stop/restart)
3. Git worktree management
4. Configuration loading and validation
5. Docker command generation
6. Repository mounting
7. Environment variable management

**Proposed Split:**
- `jib` (CLI entry point): Argument parsing, command dispatch
- `jib_container.py`: Container lifecycle management
- `jib_worktree.py`: Git worktree operations
- `jib_config_loader.py`: Configuration loading
- `jib_docker.py`: Docker command generation

#### High Priority: `jib-container/entrypoint.py` (1,132 lines)

**Current Responsibilities:**
1. Environment setup
2. Tool installation
3. Service initialization
4. Git configuration
5. Directory structure setup

**Proposed Split:**
- `entrypoint.py` (main): Orchestration only
- `env_setup.py`: Environment configuration
- `tool_installer.py`: Development tool installation
- `service_init.py`: Service initialization

#### High Priority: `feature_analyzer.py` (3,765 lines)

**Current Responsibilities:**
1. File discovery
2. Feature extraction
3. Code analysis
4. Documentation formatting
5. Output generation

**Proposed Split:**
- `feature_analyzer.py` (main): Orchestration
- `file_discovery.py`: File finding and filtering
- `code_parser.py`: AST-based analysis
- `feature_extractor.py`: Feature identification
- `doc_formatter.py`: Markdown generation

## Summary

| Metric | Count |
|--------|-------|
| Total directories (depth 3) | 73 |
| Total features | 53 (127 with sub-features) |
| Documentation files | 108 |
| Test files | 49 |
| Large Python files (>500 lines) | 29 |
| Large shell scripts (>200 lines) | 6 |
| ADRs | 12 |
| Bin commands | 31 |

**Phase 1 Status:** Complete
