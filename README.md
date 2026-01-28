# james-in-a-box (jib)

**Guided Autonomous Development Tooling for LLM-Powered Software Engineering**

jib is a suite of tools designed to enable guided autonomous software development between humans and LLM agents. Built as the reference implementation for the [Collaborative Development Framework](https://github.com/jwbron/collaborative-development-framework), it provides the infrastructure needed to run autonomous coding agents in sandboxed environments with human oversight.

> **Developed with and for the [Collaborative Development Framework](https://github.com/jwbron/collaborative-development-framework)** - a methodology for human-AI collaborative software development.

## Beta Software Warning

**This project is in active beta development.**

- **Expect breaking changes**: APIs, configurations, and workflows may change without notice
- **Active bugs**: Known and unknown issues exist throughout the codebase
- **Limited documentation**: Some features may be undocumented or have outdated docs

**Use at your own risk in production environments.**

## What jib Does

jib provides infrastructure for LLM agents to:

- **Develop features**: Implement code changes with tests and documentation
- **Handle tasks**: Receive work via Slack and execute autonomously
- **Track work**: Persistent task memory across container sessions
- **Communicate**: Bidirectional Slack messaging for async workflows

### Key Components

| Component | Purpose |
|-----------|---------|
| **jib container** | Sandboxed Docker environment running Claude Code |
| **Gateway sidecar** | Policy enforcement for git/gh operations (credential isolation) |
| **Slack services** | Bidirectional messaging for human-agent communication |
| **Context sync** | Pulls Confluence/JIRA documentation for agent context |
| **Beads** | Git-backed persistent task tracking |

## Feature Overview

jib includes 25 top-level features across these categories:

- **Communication**: Slack notifier/receiver, container notifications
- **Context Management**: Confluence/JIRA sync, Beads task tracking
- **GitHub Integration**: Command handling, PR workflows
- **Container Infrastructure**: Docker sandbox, custom commands, rules

For the complete feature list with implementation status, see [docs/FEATURES.md](docs/FEATURES.md).

## Platform Requirements

jib is designed for and tested on Linux systems only. Requires systemd for service management and docker to run.

## Security Considerations

jib runs an unsupervised LLM with unlimited network access and the ability to run arbitrary commands in a container. Do not use with sensitive codebases.

## Quick Start

### Prerequisites

- Linux with systemd
- Docker installed and running
- Python 3.11+
- GitHub CLI (`gh`) authenticated
- Slack workspace with bot configured

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/jwbron/james-in-a-box.git
   cd james-in-a-box
   ```

2. **Run the setup script**:
   ```bash
   ./setup.py
   ```

   The setup script will interactively guide you through:
   - Checking dependencies (docker, git, gh)
   - Configuring GitHub authentication (App or PAT)
   - Setting up Slack integration tokens
   - Specifying repositories to monitor
   - Creating shared directories
   - Initializing Beads task tracking

3. **Enable services** (after setup completes):
   ```bash
   ./setup.py --enable-services    # Enable all services
   ./setup.py --enable-core-services  # Enable only non-LLM services
   ./setup.py --status             # Check service status
   ```

4. **Start the container**:
   ```bash
   bin/jib
   ```

### Setup Script Options

```bash
./setup.py                    # Full interactive setup
./setup.py --update           # Update existing configuration
./setup.py --enable-services  # Enable all systemd services
./setup.py --disable-services # Disable all systemd services
./setup.py --enable SERVICE   # Enable specific service
./setup.py --disable SERVICE  # Disable specific service
./setup.py --status           # Show service status
./setup.py --force            # Force reinstall
./setup.py --skip-deps        # Skip dependency checks
```

### Configuration Files

After setup, configuration is stored in:

| File | Purpose |
|------|---------|
| `~/.config/jib/secrets.env` | API keys and tokens (600 permissions) |
| `~/.config/jib/config.yaml` | Non-secret settings |
| `~/.config/jib/repositories.yaml` | Repository access configuration |
| `~/.cache/jib/` | Docker staging and build cache (auto-managed) |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Human (via Slack)                                          │
│  • Send tasks and questions                                 │
│  • Review PRs and notifications                             │
│  • Approve and merge changes                                │
└─────────────────────────────────────────────────────────────┘
                          ↕
┌─────────────────────────────────────────────────────────────┐
│  Host Machine (Linux)                                       │
│  ├── gateway-sidecar           (git/gh policy enforcement)  │
│  ├── slack-notifier.service    (notifications → Slack)      │
│  ├── slack-receiver.service    (Slack → container tasks)    │
│  ├── context-sync.timer        (Confluence/JIRA sync)       │
│  └── github-token-refresher    (credential management)      │
└─────────────────────────────────────────────────────────────┘
                          ↕
┌─────────────────────────────────────────────────────────────┐
│  Docker Container (Sandbox)                                 │
│  ├── Claude Code agent                                      │
│  ├── Isolated git worktree                                  │
│  ├── Read-only context (Confluence, JIRA)                   │
│  ├── Beads task memory                                      │
│  └── git/gh wrappers (route to gateway sidecar)             │
└─────────────────────────────────────────────────────────────┘
```

**Key Principles:**
- **Credential isolation**: GitHub tokens held by gateway sidecar, not in container
- **Policy enforcement**: git push/gh operations validated by gateway before execution
- **Merge blocked**: Agent cannot merge PRs - human must merge via GitHub UI
- Container is sandboxed with limited network access
- All code changes require human review before merge
- Communication flows through Slack and file-based messaging

### Gateway Sidecar

The gateway sidecar enforces policies on all git/gh operations:

| Operation | Policy |
|-----------|--------|
| `git push` | Only to jib-owned branches (jib-prefixed or has jib's open PR) |
| `gh pr create` | Always allowed |
| `gh pr comment/edit/close` | Only on PRs authored by jib |
| `gh pr merge` | **Blocked** - human must merge via GitHub UI |

**Setup:**
```bash
bin/setup-gateway-sidecar  # Install and configure gateway
systemctl --user enable --now gateway-sidecar  # Start service
```

See [gateway-sidecar/README.md](gateway-sidecar/README.md) for detailed documentation.

## Operating Model

jib follows the Collaborative Development Framework's operating model:

| Role | Responsibilities |
|------|------------------|
| **Agent (jib)** | Plan, implement, test, document, create PRs |
| **Human** | Review, approve, merge, deploy |

**The agent NEVER:**
- Merges PRs
- Deploys to production
- Modifies credentials
- Accesses production systems

## Documentation

- **[Documentation Index](docs/index.md)** - Navigation hub for all docs
- **[Features List](docs/FEATURES.md)** - Complete feature inventory
- **[ADR Index](docs/adr/README.md)** - Architecture decisions
- **[Beads Reference](docs/reference/beads.md)** - Task tracking system

## Service Management

```bash
# Check service status
systemctl --user status slack-notifier slack-receiver
systemctl --user list-timers | grep context

# View logs
journalctl --user -u slack-notifier -f

# Restart services
systemctl --user restart slack-notifier slack-receiver
```

## Container Management

```bash
bin/jib              # Start interactive container
bin/jib --rebuild    # Rebuild container image
bin/jib --exec "python script.py"  # Execute command in container
docker logs jib-claude -f  # View container logs
```

## Known Limitations

- **Linux only**: No macOS or Windows native support
- **Single user**: Designed for individual developer use
- **Claude-focused**: Primary support for Anthropic's Claude, other providers experimental
- **Slack-dependent**: Requires Slack for human-agent communication
- **Manual PR merge**: Agent cannot merge its own PRs

## Contributing

This project is in active development. Before contributing:

1. Review open issues and PRs
2. Check the [ADR Index](docs/adr/README.md) for architectural decisions
3. Run `make lint` before submitting changes
4. Note that APIs may change without deprecation notices during beta

## Related Projects

- **[Collaborative Development Framework](https://github.com/jwbron/collaborative-development-framework)** - The methodology this project implements
- **[Claude Code](https://docs.anthropic.com/claude-code)** - The underlying LLM coding agent
- **[Beads](https://github.com/steveyegge/beads)** - Git-backed task tracking

## License

MIT License
