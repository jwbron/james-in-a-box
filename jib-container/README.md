# jib Container

Container infrastructure and components that run inside the Docker sandbox.

## Overview

The jib container provides a secure, isolated environment for the Claude agent to work in. It includes:
- Task scripts called via `jib --exec` from host services
- Interactive tools for agent use
- Claude Code configuration (rules, commands)
- Shared directories for communication with host

## Components

- **[jib-tasks/](jib-tasks/)** - Scripts called via `jib --exec` (github, jira, confluence, slack)
- **[jib-tools/](jib-tools/)** - Interactive tools (PR helpers, test discovery)
- **[.claude](.claude/README.md)** - Claude Code configuration (rules, commands, prompts)

## Directory Structure

```
~/sharing/                    # Shared with host (mounted from ~/.jib-sharing/)
├── notifications/           # Agent → Human (notifications)
├── incoming/                # Human → Agent (tasks)
├── responses/               # Human → Agent (responses)
└── context/                 # Persistent knowledge across rebuilds

~/context-sync/              # Read-only context (mounted from host)
├── confluence/             # Confluence documentation
└── jira/                   # JIRA tickets

~/khan/james-in-a-box/      # This repository (mounted from host)
```

## Container Lifecycle

**Start container** (interactive mode - auto-starts Claude):
```bash
cd ~/khan/james-in-a-box
./jib
# Claude Code starts automatically in sandboxed environment
```

**Rebuild container** (if Dockerfile changes):
```bash
./jib --rebuild
```

**Access running container**:
```bash
docker exec -it jib-claude bash
```

## Configuration

Container setup is automated via `docker-setup.py`, which runs on container start to:
- Install dependencies
- Configure environment
- Set up Claude Code

Note: Task scripts are not started as background processes. They are called via `jib --exec` from host-side systemd services.

No manual setup required inside the container.

## Security

**Isolation**:
- No SSH keys
- No cloud credentials (can't deploy to GCP/AWS)
- Network: Outbound HTTP only (Claude API, packages)
- No inbound ports (can't accept connections)
- Limited GitHub token (scoped to specific repos only)

**What the agent CAN do**:
- Read/write code in `~/khan/` (isolated git worktree)
- Git commits locally
- Create/manage PRs via GitHub MCP
- Query issues, repos, comments via GitHub MCP
- Push files/changes via GitHub MCP
- Run tests and builds
- Read context docs (Confluence, JIRA)
- Write notifications for human review

**What the agent CANNOT do**:
- Merge PRs (human must approve and merge)
- Deploy to cloud (no credentials)
- Access host services (network isolated)
- Modify host filesystem (only mounted directories)
- Push to protected branches (main/master)

## GitHub MCP Server

The container uses the GitHub MCP server for all GitHub operations. This provides real-time, bi-directional access:

| Category | Tools |
|----------|-------|
| **Repositories** | `search_repositories`, `get_file_contents`, `push_files` |
| **Issues** | `search_issues`, `get_issue`, `create_issue`, `update_issue` |
| **Pull Requests** | `create_pull_request`, `get_pull_request`, `list_pull_requests` |
| **Comments** | `add_issue_comment`, `list_issue_comments` |
| **Branches** | `create_branch`, `list_branches` |

MCP server is configured in `~/.mcp.json` and authenticated via `GITHUB_TOKEN`.
