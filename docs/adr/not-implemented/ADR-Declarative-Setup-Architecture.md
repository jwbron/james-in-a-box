# ADR: Declarative Setup Architecture

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, jib (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** December 2025
**Status:** Proposed (Not Implemented)

---

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Implementation Details](#implementation-details)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)

## Context

### Background

The james-in-a-box (jib) project currently uses a **hierarchical shell script approach** for setting up host services and container environments. The root `setup.sh` (1,097 lines) orchestrates 16 component-specific `setup.sh` scripts across different directories.

**Current Architecture:**

```
setup.sh (root, 1097 LOC)
├── host-services/
│   ├── analysis/
│   │   ├── adr-researcher/setup.sh
│   │   ├── beads-analyzer/setup.sh
│   │   ├── doc-generator/setup.sh
│   │   ├── feature-analyzer/setup.sh
│   │   ├── github-watcher/setup.sh
│   │   ├── index-generator/setup.sh
│   │   ├── inefficiency-detector/setup.sh
│   │   ├── spec-enricher/setup.sh
│   │   └── trace-collector/setup.sh
│   ├── slack/
│   │   ├── slack-notifier/setup.sh
│   │   └── slack-receiver/setup.sh
│   ├── sync/
│   │   └── context-sync/setup.sh
│   └── utilities/
│       ├── github-token-refresher/setup.sh
│       ├── service-failure-notify/setup.sh
│       └── worktree-watcher/setup.sh
└── jib-container/
    └── (Dockerfile handles container setup)
```

### Current Pain Points

**1. Inconsistent Setup Script Interfaces**

Different setup scripts accept different arguments:

| Script | Interface |
|--------|-----------|
| `slack-notifier/setup.sh` | No arguments, always installs |
| `doc-generator/setup.sh` | Requires `enable` argument |
| `index-generator/setup.sh` | Requires `install` argument |
| `spec-enricher/setup.sh` | Optional argument |

The root `setup.sh` must maintain a hardcoded mapping of which scripts need special arguments:

```bash
declare -A optional_components=(
    ["analysis/doc-generator"]="enable"
    ["analysis/index-generator"]="install"
    ["analysis/spec-enricher"]=""
)
```

**2. Code Duplication Across Setup Scripts**

Each of the 16 `setup.sh` scripts repeats the same boilerplate:

```bash
# Repeated in every setup.sh
mkdir -p "$SYSTEMD_DIR"
ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"
```

Estimated duplication: ~40-60 lines per script × 16 scripts = **640-960 lines of duplicated code**.

**3. High Maintenance Burden**

Adding a new host service requires:
1. Create new directory under `host-services/`
2. Write a new `setup.sh` script (copying boilerplate)
3. Update root `setup.sh` component_order array
4. Potentially update optional_components if special args needed
5. Update component_descriptions for pretty output
6. Update services array for status display
7. Update services_to_restart for update mode

**7 locations must be updated** for a single new component.

**4. No Declarative Component Registry**

Components are defined imperatively in multiple bash arrays:

```bash
# Array 1: Installation order
component_order=(
    "utilities/service-failure-notify"
    "slack/slack-notifier"
    ...
)

# Array 2: Descriptions
declare -A component_descriptions=(
    ["service-failure-notify"]="Service Failure Notify..."
    ["slack-notifier"]="Slack Notifier..."
)

# Array 3: Services for status
services=(
    "slack-notifier.service:Slack Notifier"
    ...
)

# Array 4: Services for restart
services_to_restart=(
    "slack-notifier.service"
    ...
)
```

No single source of truth exists for what components exist and their metadata.

**5. Mixed Concerns in Root setup.sh**

The 1,097-line root `setup.sh` handles:
- Argument parsing
- Dependency checking (docker, python, uv, beads)
- Python venv setup
- Configuration validation (Slack, GitHub)
- GitHub App interactive setup
- Component installation orchestration
- Systemd management
- Docker image building
- User output and formatting

These concerns are tightly coupled and difficult to test or modify independently.

**6. No Health Checks or Rollback Mechanism**

- If a component fails to start, setup continues
- No verification that services are actually healthy
- No way to rollback a partial installation
- `--update` mode restarts everything regardless of what changed

### What We're Deciding

This ADR proposes a **declarative, registry-based setup architecture** where:

1. **Components are declared in a YAML registry** with all metadata in one place
2. **A shared setup library** provides common operations (symlink, enable, start)
3. **A Python orchestrator** replaces bash for complex logic
4. **Individual setup.sh scripts become optional** (for component-specific logic only)
5. **Health checks and rollback** are built into the system

## Decision

**We will adopt a declarative registry-based setup architecture using:**
1. A `components.yaml` registry as the single source of truth
2. A shared setup library (`setup_lib.sh` or Python module)
3. A Python orchestrator for complex coordination
4. Optional component-specific hooks for custom logic

### Rationale

1. **Single Source of Truth:** All component metadata in one file reduces synchronization errors
2. **Reduced Duplication:** Shared library eliminates 600+ lines of duplicated bash
3. **Type Safety:** Python orchestrator enables better error handling and testing
4. **Extensibility:** New components require only adding an entry to the registry
5. **Observability:** Centralized orchestration enables better logging and health checks

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Registry Format** | YAML | Human-readable, widely supported | JSON (less readable), TOML (less familiar) |
| **Orchestrator Language** | Python | Already used in project, rich ecosystem | Bash (current, limited), Go (unnecessary complexity) |
| **Component Hooks** | Optional bash scripts | Backward compatible, simple | Python modules (over-engineered) |
| **Systemd Management** | Direct systemctl | Proven, reliable | D-Bus API (complexity), custom daemon (unnecessary) |

## Implementation Details

### 1. Component Registry (`config/components.yaml`)

```yaml
# config/components.yaml
# Single source of truth for all jib host-services components

version: 1

defaults:
  enabled: true
  auto_start: true
  restart_on_update: true

components:
  # Core services (required for basic functionality)
  service-failure-notify:
    path: utilities/service-failure-notify
    description: "Service Failure Notify (OnFailure notifications)"
    priority: 0  # Must be first - other services depend on this
    type: service
    systemd_units:
      - service-failure-notify@.service
    dependencies: []

  slack-notifier:
    path: slack/slack-notifier
    description: "Slack Notifier (Claude → You)"
    priority: 10
    type: service
    systemd_units:
      - slack-notifier.service
    dependencies:
      - service-failure-notify
    required_secrets:
      - SLACK_TOKEN

  slack-receiver:
    path: slack/slack-receiver
    description: "Slack Receiver (You → Claude)"
    priority: 10
    type: service
    systemd_units:
      - slack-receiver.service
    dependencies:
      - service-failure-notify
    required_secrets:
      - SLACK_TOKEN
      - SLACK_APP_TOKEN

  context-sync:
    path: sync/context-sync
    description: "Context Sync (Confluence, JIRA → Local)"
    priority: 20
    type: timer
    systemd_units:
      - context-sync.service
      - context-sync.timer
    dependencies:
      - service-failure-notify
    optional: true  # Can run without if no Confluence/JIRA

  github-watcher:
    path: analysis/github-watcher
    description: "GitHub Watcher (PR/issue monitoring)"
    priority: 20
    type: timer
    systemd_units:
      - github-watcher.service
      - github-watcher.timer
    dependencies:
      - service-failure-notify
    required_prerequisites:
      - gh_auth  # GitHub CLI must be authenticated

  github-token-refresher:
    path: utilities/github-token-refresher
    description: "GitHub Token Refresher (auto-refresh App tokens)"
    priority: 15
    type: service
    systemd_units:
      - github-token-refresher.service
    dependencies:
      - service-failure-notify
    required_files:
      - ~/.config/jib/github-app-id
      - ~/.config/jib/github-app-installation-id
      - ~/.config/jib/github-app.pem

  worktree-watcher:
    path: utilities/worktree-watcher
    description: "Worktree Watcher (cleanup orphaned worktrees)"
    priority: 30
    type: timer
    systemd_units:
      - worktree-watcher.service
      - worktree-watcher.timer
    dependencies:
      - service-failure-notify

  conversation-analyzer:
    path: analysis/conversation-analyzer
    description: "Conversation Analyzer (daily analysis)"
    priority: 40
    type: timer
    systemd_units:
      - conversation-analyzer.service
      - conversation-analyzer.timer
    dependencies:
      - slack-receiver

  doc-generator:
    path: analysis/doc-generator
    description: "Documentation Generator (weekly docs + drift check)"
    priority: 50
    type: timer
    systemd_units:
      - jib-doc-generator.service
      - jib-doc-generator.timer
    dependencies:
      - service-failure-notify
    optional: true

  adr-researcher:
    path: analysis/adr-researcher
    description: "ADR Researcher (weekly ADR research)"
    priority: 50
    type: timer
    systemd_units:
      - adr-researcher.service
      - adr-researcher.timer
    dependencies:
      - service-failure-notify
    required_prerequisites:
      - gh_auth
    optional: true

  trace-collector:
    path: analysis/trace-collector
    description: "Trace Collector (LLM tool call tracing)"
    priority: 50
    type: timer
    systemd_units:
      - trace-collector.service
      - trace-collector.timer
    dependencies:
      - service-failure-notify
    optional: true

  # Additional optional components
  index-generator:
    path: analysis/index-generator
    description: "Index Generator (codebase indexing)"
    priority: 60
    type: timer
    enabled: false  # Must be explicitly enabled
    optional: true

  spec-enricher:
    path: analysis/spec-enricher
    description: "Spec Enricher (specification enrichment)"
    priority: 60
    type: timer
    enabled: false
    optional: true

  beads-analyzer:
    path: analysis/beads-analyzer
    description: "Beads Analyzer (task pattern analysis)"
    priority: 60
    type: timer
    enabled: false
    optional: true

  feature-analyzer:
    path: analysis/feature-analyzer
    description: "Feature Analyzer (feature tracking)"
    priority: 60
    type: timer
    enabled: false
    optional: true

  inefficiency-detector:
    path: analysis/inefficiency-detector
    description: "Inefficiency Detector (workflow optimization)"
    priority: 60
    type: timer
    enabled: false
    optional: true

# Prerequisite definitions
prerequisites:
  gh_auth:
    check_command: "gh auth status"
    error_message: "GitHub CLI not authenticated. Run: gh auth login"
    install_hint: "brew install gh (macOS) or apt install gh (Linux)"
```

### 2. Shared Setup Library (`shared/setup_lib.sh`)

```bash
#!/bin/bash
# Shared setup library for jib host-services components

SYSTEMD_DIR="${HOME}/.config/systemd/user"

# Symlink a systemd unit file
# Usage: setup_symlink_unit /path/to/component service-name.service
setup_symlink_unit() {
    local component_dir=$1
    local unit_name=$2

    mkdir -p "$SYSTEMD_DIR"
    ln -sf "$component_dir/$unit_name" "$SYSTEMD_DIR/"
    echo "✓ Symlinked $unit_name"
}

# Enable a systemd unit
setup_enable_unit() {
    local unit_name=$1
    systemctl --user enable "$unit_name" 2>/dev/null || true
    echo "✓ Enabled $unit_name"
}

# Start a systemd unit
setup_start_unit() {
    local unit_name=$1
    systemctl --user start "$unit_name" 2>/dev/null || true
    echo "✓ Started $unit_name"
}

# Full setup for a simple component
# Usage: setup_simple_component /path/to/component unit1.service unit2.timer
setup_simple_component() {
    local component_dir=$1
    shift
    local units=("$@")

    for unit in "${units[@]}"; do
        setup_symlink_unit "$component_dir" "$unit"
    done

    systemctl --user daemon-reload

    for unit in "${units[@]}"; do
        setup_enable_unit "$unit"
        setup_start_unit "$unit"
    done
}

# Check if a service is healthy
# Usage: setup_check_health service-name.service [timeout_seconds]
setup_check_health() {
    local unit_name=$1
    local timeout=${2:-5}

    for i in $(seq 1 $timeout); do
        if systemctl --user is-active --quiet "$unit_name"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# Reload systemd daemon
setup_reload_daemon() {
    systemctl --user daemon-reload
    echo "✓ Systemd daemon reloaded"
}
```

### 3. Python Orchestrator (`bin/jib-setup`)

```python
#!/usr/bin/env python3
"""
jib-setup: Declarative setup orchestrator for james-in-a-box

Usage:
    jib-setup              # Interactive setup
    jib-setup --update     # Update/reload all components
    jib-setup --status     # Show status of all components
    jib-setup --enable X   # Enable optional component X
    jib-setup --disable X  # Disable component X
"""

import argparse
import subprocess
import sys
from pathlib import Path
import yaml

class ComponentRegistry:
    """Loads and manages the component registry."""

    def __init__(self, registry_path: Path):
        with open(registry_path) as f:
            self.data = yaml.safe_load(f)
        self.components = self.data.get('components', {})
        self.defaults = self.data.get('defaults', {})
        self.prerequisites = self.data.get('prerequisites', {})

    def get_install_order(self) -> list[str]:
        """Return components sorted by priority."""
        return sorted(
            self.components.keys(),
            key=lambda c: self.components[c].get('priority', 100)
        )

    def get_enabled_components(self) -> list[str]:
        """Return only enabled components."""
        return [
            name for name in self.get_install_order()
            if self.components[name].get('enabled', self.defaults.get('enabled', True))
        ]

    def check_prerequisites(self, component_name: str) -> list[str]:
        """Check prerequisites for a component, return list of failures."""
        component = self.components[component_name]
        failures = []

        for prereq_name in component.get('required_prerequisites', []):
            prereq = self.prerequisites.get(prereq_name, {})
            check_cmd = prereq.get('check_command')
            if check_cmd:
                result = subprocess.run(
                    check_cmd, shell=True, capture_output=True
                )
                if result.returncode != 0:
                    failures.append(prereq.get('error_message', f'{prereq_name} check failed'))

        return failures


class SetupOrchestrator:
    """Orchestrates component setup."""

    def __init__(self, base_dir: Path, registry: ComponentRegistry):
        self.base_dir = base_dir
        self.registry = registry
        self.setup_lib = base_dir / 'shared' / 'setup_lib.sh'

    def setup_component(self, name: str) -> bool:
        """Set up a single component. Returns True on success."""
        component = self.registry.components[name]
        component_path = self.base_dir / 'host-services' / component['path']

        print(f"\n→ Setting up: {component['description']}")

        # Check prerequisites
        failures = self.registry.check_prerequisites(name)
        if failures:
            for msg in failures:
                print(f"  ⚠ Prerequisite failed: {msg}")
            if not component.get('optional', False):
                return False
            print("  ⚠ Skipping optional component")
            return True

        # Check for custom setup.sh
        custom_setup = component_path / 'setup.sh'
        if custom_setup.exists():
            result = subprocess.run(
                ['bash', str(custom_setup)],
                cwd=component_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"  ✗ Setup failed: {result.stderr}")
                return component.get('optional', False)
        else:
            # Use shared library for simple components
            units = component.get('systemd_units', [])
            for unit in units:
                subprocess.run([
                    'bash', '-c',
                    f'source {self.setup_lib} && setup_symlink_unit {component_path} {unit}'
                ])

            subprocess.run(['systemctl', '--user', 'daemon-reload'])

            for unit in units:
                subprocess.run(['systemctl', '--user', 'enable', unit])
                subprocess.run(['systemctl', '--user', 'start', unit])

        print(f"  ✓ {name} configured")
        return True

    def setup_all(self, update_mode: bool = False) -> bool:
        """Set up all enabled components."""
        components = self.registry.get_enabled_components()

        for name in components:
            if not self.setup_component(name):
                if not self.registry.components[name].get('optional', False):
                    print(f"\n✗ Required component {name} failed, aborting")
                    return False

        return True

    def get_status(self) -> dict:
        """Get status of all components."""
        status = {}
        for name, component in self.registry.components.items():
            units = component.get('systemd_units', [])
            unit_status = {}
            for unit in units:
                result = subprocess.run(
                    ['systemctl', '--user', 'is-active', unit],
                    capture_output=True, text=True
                )
                unit_status[unit] = result.stdout.strip()
            status[name] = {
                'enabled': component.get('enabled', True),
                'units': unit_status
            }
        return status


def main():
    parser = argparse.ArgumentParser(description='jib setup orchestrator')
    parser.add_argument('--update', action='store_true', help='Update mode')
    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--enable', metavar='COMPONENT', help='Enable a component')
    parser.add_argument('--disable', metavar='COMPONENT', help='Disable a component')
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    registry_path = base_dir / 'config' / 'components.yaml'
    registry = ComponentRegistry(registry_path)
    orchestrator = SetupOrchestrator(base_dir, registry)

    if args.status:
        status = orchestrator.get_status()
        for name, info in status.items():
            enabled = "✓" if info['enabled'] else "○"
            units = ", ".join(f"{u}={s}" for u, s in info['units'].items())
            print(f"{enabled} {name}: {units}")
        return 0

    if not orchestrator.setup_all(update_mode=args.update):
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
```

### 4. Simplified Component setup.sh (Optional)

Components with simple setup can remove their `setup.sh` entirely. Complex components keep a minimal version:

```bash
#!/bin/bash
# Custom setup for github-watcher (example of component with special requirements)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source shared library
source "$SCRIPT_DIR/../../../shared/setup_lib.sh"

# Component-specific prerequisite check
if ! command -v gh &> /dev/null; then
    echo "ERROR: gh (GitHub CLI) is not installed"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo "ERROR: gh is not authenticated"
    exit 1
fi

# Create component-specific state directory
mkdir -p ~/.local/share/github-watcher

# Use shared library for standard setup
setup_simple_component "$SCRIPT_DIR" \
    "github-watcher.service" \
    "github-watcher.timer"
```

## Migration Strategy

### Phase 1: Create Registry and Library

**Goal:** Introduce new infrastructure alongside existing system.

1. Create `config/components.yaml` with all current components
2. Create `shared/setup_lib.sh` with common functions
3. Create `bin/jib-setup` orchestrator (read-only mode initially)
4. Test that registry accurately reflects current state

**Success Criteria:** `jib-setup --status` matches `systemctl --user list-units`

### Phase 2: Migrate Simple Components

**Goal:** Convert components without custom logic.

1. Identify components with standard setup patterns:
   - slack-notifier
   - slack-receiver
   - service-failure-notify
   - worktree-watcher

2. Remove boilerplate from their setup.sh
3. Update orchestrator to handle these via shared library
4. Test both old and new paths produce identical results

**Success Criteria:** 4+ components using shared library

### Phase 3: Migrate Complex Components

**Goal:** Convert components with custom prerequisites.

1. Convert components with prerequisite checks:
   - github-watcher (gh auth check)
   - adr-researcher (gh auth check)
   - github-token-refresher (credential files)

2. Move prerequisite logic to registry or minimal hooks
3. Update orchestrator for these components

**Success Criteria:** All components using declarative system

### Phase 4: Replace Root setup.sh

**Goal:** Make `jib-setup` the primary entry point.

1. Rename `setup.sh` → `setup-legacy.sh`
2. Create new `setup.sh` that wraps `jib-setup`
3. Move configuration validation to Python orchestrator
4. Add health checks and rollback capability
5. Remove legacy script after validation period

**Success Criteria:**
- `./setup.sh` uses new system
- Rollback capability tested
- Documentation updated

## Consequences

### Benefits

1. **Single Source of Truth:** Component metadata in one YAML file
2. **Reduced Duplication:** ~600 lines of bash removed
3. **Easier Maintenance:** Adding a component requires only registry entry
4. **Better Observability:** Centralized logging and status
5. **Health Checks:** Built-in verification of service health
6. **Testability:** Python orchestrator can be unit tested
7. **Rollback Capability:** Can restore previous state on failure

### Drawbacks

1. **Migration Effort:** Converting 16 components requires time
2. **Python Dependency:** Orchestrator requires Python (already present)
3. **Learning Curve:** Team must understand new system
4. **Two Systems During Migration:** Temporary complexity

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing setup | Run both systems in parallel during migration |
| Complex components don't fit pattern | Allow custom hooks for edge cases |
| YAML schema errors | Validate schema on load, fail fast |
| Orchestrator bugs | Extensive testing before replacing bash |

### Neutral

1. **Performance:** Setup runs once, performance impact negligible
2. **Systemd Dependency:** Already using systemd, no change

## Decision Permanence

**Medium permanence.**

The choice of YAML registry + Python orchestrator is reversible—we can always maintain bash scripts. However, the benefits of reduced duplication and single source of truth make this worthwhile investment.

The migration strategy allows gradual adoption with easy rollback at each phase.

## Alternatives Considered

### Alternative 1: Improve Existing Bash System

**Description:** Refactor current bash scripts without architectural change.

**Pros:**
- No new dependencies
- Familiar to maintainers
- Lower migration effort

**Cons:**
- Bash limitations remain (no proper data structures, error handling)
- Duplication harder to eliminate in bash
- Testing bash scripts is difficult

**Rejected because:** Bash is fundamentally limited for orchestration at this scale.

### Alternative 2: Full Python Rewrite

**Description:** Rewrite all setup logic in Python, no bash.

**Pros:**
- Maximum consistency
- Full type safety
- Comprehensive testing

**Cons:**
- Much larger migration effort
- Loses bash simplicity for simple tasks
- Over-engineered for component-specific hooks

**Rejected because:** Hybrid approach preserves bash simplicity while adding Python where needed.

### Alternative 3: Ansible/Terraform

**Description:** Use infrastructure-as-code tools.

**Pros:**
- Industry-standard tools
- Declarative by design
- Rich ecosystem

**Cons:**
- Heavy dependency for simple use case
- Learning curve for new tooling
- Overkill for systemd user services

**Rejected because:** These tools are designed for infrastructure provisioning, not local development setup.

### Alternative 4: Make-based System

**Description:** Use Makefile for orchestration.

**Pros:**
- Dependency tracking built-in
- Familiar to developers
- No new runtime dependencies

**Cons:**
- Make syntax is arcane
- Limited data structure support
- Poor error handling

**Rejected because:** Make shares bash's limitations without its readability.

### Alternative 5: Docker Compose for Host Services

**Description:** Run host services in containers orchestrated by Docker Compose.

**Pros:**
- Consistent environment
- Easy deployment
- Built-in dependency management

**Cons:**
- Adds container overhead for simple services
- Complicates systemd integration
- Changes the architecture significantly

**Rejected because:** Host services need direct systemd integration for user services.

## References

- [systemd User Units](https://wiki.archlinux.org/title/Systemd/User)
- [YAML Specification](https://yaml.org/spec/)
- [Python subprocess module](https://docs.python.org/3/library/subprocess.html)
- Existing jib setup: `setup.sh`, `host-services/*/setup.sh`

---

**Last Updated:** 2025-12-02
**Next Review:** After Phase 1 implementation
**Status:** Proposed (Not Implemented)
