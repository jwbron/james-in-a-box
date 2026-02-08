# This project is no longer maintained. See https://github.com/jwbron/egg for its successor

# james-in-a-box (jib)

**AI Software Development Collaborator**

jib is a sandboxed environment for running Claude Code as an autonomous software engineering agent. It handles the infrastructure so you can focus on directing the work: send tasks via Slack, get PRs back for review.

## How It Works

1. **You send a task via Slack** - "Add input validation to the signup form"
2. **jib receives the task** and starts Claude Code in a sandboxed container
3. **Claude implements the change** - writes code, runs tests, commits
4. **jib creates a PR** and notifies you via Slack
5. **You review and merge** - the agent never merges its own work

## Key Features

- **Sandboxed execution** - Claude runs in a Docker container with controlled access
- **Credential isolation** - GitHub tokens held by gateway sidecar, not accessible to agent
- **Merge blocked** - Agent cannot merge PRs; human review is enforced
- **Bidirectional Slack** - Send tasks in, receive updates and PRs out
- **Persistent memory** - Beads tracks tasks across container restarts
- **Context sync** - Confluence/JIRA docs available to agent

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  You (via Slack)                                            │
│  • Send tasks: "review PR 123" / "fix the login bug"        │
│  • Receive notifications and PR links                       │
│  • Review and merge changes                                 │
└─────────────────────────────────────────────────────────────┘
                          ↕
┌─────────────────────────────────────────────────────────────┐
│  Host Services                                              │
│  ├── slack-receiver      (Slack → container tasks)         │
│  ├── slack-notifier      (notifications → Slack)           │
│  ├── gateway-sidecar     (git/gh policy enforcement)       │
│  └── context-sync        (Confluence/JIRA sync)            │
└─────────────────────────────────────────────────────────────┘
                          ↕
┌─────────────────────────────────────────────────────────────┐
│  Docker Container (Sandbox)                                 │
│  ├── Claude Code agent                                      │
│  ├── Git worktree (isolated branch)                         │
│  ├── Beads task memory                                      │
│  └── git/gh → routed through gateway sidecar                │
└─────────────────────────────────────────────────────────────┘
```

## Requirements

- Linux with systemd
- Docker
- Python 3.11+
- Slack workspace with bot configured
- GitHub (App or PAT)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/jwbron/james-in-a-box.git
cd james-in-a-box
./setup.py

# Enable services
./setup.py --enable-services

# Start the container
bin/jib
```

The setup script guides you through configuring Slack tokens, GitHub authentication, and repository access.

## Configuration

| File | Purpose |
|------|---------|
| `~/.config/jib/secrets.env` | API keys and tokens |
| `~/.config/jib/repositories.yaml` | Repository access |
| `~/.config/jib/config.yaml` | Settings |

## Security Model

| Control | Implementation |
|---------|----------------|
| **Credential isolation** | Tokens held by gateway sidecar, not in container |
| **Push restrictions** | Only to jib-owned branches |
| **Merge blocked** | `gh pr merge` blocked at gateway level |
| **PR restrictions** | Can only edit/close PRs it authored |

The agent cannot merge its own PRs. Human review and merge via GitHub UI is required.

## Common Commands

```bash
# Container
bin/jib                    # Start interactive session
bin/jib --rebuild          # Rebuild container image
bin/jib --exec "cmd"       # Run command in container

# Services
systemctl --user status slack-notifier slack-receiver
journalctl --user -u slack-receiver -f

# Task tracking (inside container)
bd --allow-stale list                    # Show all tasks
bd --allow-stale list -s in_progress     # Show active tasks
```

## Slack Commands

Send these as DMs to the jib bot:

- `review PR 123` - Review a specific PR
- `review PR 123 in repo-name` - Review PR in a specific repo
- Any task description - jib will work on it

## Documentation

- [Setup Guide](docs/setup/README.md) - Installation and configuration
- [Architecture](docs/architecture/README.md) - System design
- [Beads Reference](docs/reference/beads.md) - Task tracking
- [Gateway Sidecar](gateway-sidecar/README.md) - Security enforcement

## Limitations

- **Linux only** - Requires systemd
- **Single user** - Designed for individual use
- **Claude-focused** - Built for Anthropic's Claude Code
- **Slack required** - Primary communication channel

## License

MIT License
