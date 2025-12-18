# james-in-a-box (jib)

**Collaborative Development Tooling for LLM-Powered Software Engineering**

jib is a suite of tools designed to enable collaborative software development between humans and LLM agents. Built as the reference implementation for the [Collaborative Development Framework](https://github.com/jwbron/collaborative-development-framework), it provides the infrastructure needed to run autonomous coding agents in sandboxed environments with human oversight.

> **Developed with and for the [Collaborative Development Framework](https://github.com/jwbron/collaborative-development-framework)** - a methodology for human-AI collaborative software development.

## Beta Software Warning

**This project is in active beta development.**

- **Expect breaking changes**: APIs, configurations, and workflows may change without notice
- **Active bugs**: Known and unknown issues exist throughout the codebase
- **Experimental features**: Many analyzers and automation systems are works in progress
- **Limited documentation**: Some features may be undocumented or have outdated docs

**Use at your own risk in production environments.**

## Platform Requirements

**jib is designed for and tested on Linux systems only.**

- Requires systemd for service management
- Tested on Ubuntu 22.04+ and Fedora 39+
- Docker required for container sandboxing
- WSL2 may work but is not officially supported
- macOS is not supported (no systemd)

## Security Considerations

**READ THIS BEFORE USING JIB WITH SENSITIVE CODEBASES**

jib runs LLM agents that have access to your code and documentation. By design, these agents communicate with external services (Claude API, Slack, GitHub). This creates potential vectors for data exfiltration:

### Data Exfiltration Risks

| Risk | Description | Current Mitigation |
|------|-------------|-------------------|
| **LLM API Calls** | All code and context is sent to Anthropic's Claude API | None - inherent to LLM operation |
| **Slack Messages** | Agent can send arbitrary content to Slack | Human review of messages |
| **GitHub PRs/Comments** | Agent can include code/data in PR descriptions | Human review before merge |
| **Web Fetches** | Agent can fetch URLs, potentially leaking via query params | URL restriction (partial) |

### Secret Exfiltration Risks

| Risk | Description | Current Mitigation |
|------|-------------|-------------------|
| **Environment Variables** | Agent has access to container environment | Secrets mounted read-only |
| **API Keys in Code** | Agent can read API keys from source files | Human review |
| **Config Files** | `.env`, credential files may be readable | Sandbox isolation (partial) |

### Recommendations

**DO NOT use jib with:**
- Repositories containing customer data
- Codebases with embedded secrets or credentials
- Proprietary algorithms you cannot share with LLM providers
- Compliance-sensitive code (HIPAA, PCI-DSS, SOC2)

**BEFORE using jib:**
- Audit your codebase for secrets and sensitive data
- Review your organization's LLM usage policies
- Understand that all code sent to agents goes to external APIs
- Configure Confluence/JIRA sync to exclude sensitive spaces

**Planned security features (not yet implemented):**
- Content classification (Public/Internal/Confidential)
- DLP scanning before API calls
- Output monitoring for sensitive data
- Allowlist-based context filtering

## What jib Does

jib provides infrastructure for LLM agents to:

- **Develop features**: Implement code changes with tests and documentation
- **Review PRs**: Automatically review team pull requests
- **Maintain docs**: Keep documentation synchronized with code
- **Track work**: Persistent task memory across container sessions
- **Communicate**: Bidirectional Slack messaging for async workflows

### Key Components

| Component | Purpose |
|-----------|---------|
| **jib container** | Sandboxed Docker environment running Claude Code |
| **Slack services** | Bidirectional messaging for human-agent communication |
| **GitHub watcher** | Monitors PRs for comments, failures, review requests |
| **Context sync** | Pulls Confluence/JIRA documentation for agent context |
| **Beads** | Git-backed persistent task tracking |
| **Analyzers** | Experimental code analysis and self-improvement tools |

## Feature Overview

jib includes 53 top-level features across these categories:

- **Communication**: Slack notifier/receiver, container notifications
- **Context Management**: Confluence/JIRA sync, Beads task tracking
- **GitHub Integration**: PR reviews, comment responses, CI failure analysis
- **Self-Improvement**: LLM trace collection, inefficiency detection (experimental)
- **Documentation**: ADR research, feature analysis, doc generation (experimental)
- **Container Infrastructure**: Docker sandbox, worktree isolation

For the complete feature list with implementation status, see [docs/FEATURES.md](docs/FEATURES.md).

**Note**: Features in the Self-Improvement and Documentation sections are experimental and may produce inconsistent results.

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
| `~/.jib/mounts.conf` | Local repository mount paths |

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
│  ├── slack-notifier.service    (notifications → Slack)      │
│  ├── slack-receiver.service    (Slack → container tasks)    │
│  ├── github-watcher.timer      (PR monitoring)              │
│  ├── context-sync.timer        (Confluence/JIRA sync)       │
│  ├── github-token-refresher    (credential management)      │
│  └── worktree-watcher.timer    (cleanup)                    │
└─────────────────────────────────────────────────────────────┘
                          ↕
┌─────────────────────────────────────────────────────────────┐
│  Docker Container (Sandbox)                                 │
│  ├── Claude Code agent                                      │
│  ├── Isolated git worktree                                  │
│  ├── Read-only context (Confluence, JIRA)                   │
│  ├── Beads task memory                                      │
│  └── GitHub CLI (via token refresh)                         │
└─────────────────────────────────────────────────────────────┘
```

**Key Principles:**
- Host manages credentials and external API access
- Container is sandboxed with limited network access
- All code changes require human review before merge
- Communication flows through Slack and file-based messaging

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
systemctl --user list-timers | grep -E 'github|context|worktree'

# View logs
journalctl --user -u slack-notifier -f
journalctl --user -u github-watcher -f

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
