# JIB Container

Container infrastructure and components that run inside the Docker sandbox.

## Overview

The JIB container provides a secure, isolated environment for the Claude agent to work in. It includes:
- Context monitoring for Confluence/JIRA docs
- Claude Code configuration (rules, commands)
- Shared directories for communication with host

## Components

- **[context-watcher](components/context-watcher/README.md)** - Monitors `~/context-sync/` for document updates
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

**Start container**:
```bash
cd ~/khan/james-in-a-box
./jib
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
- Start watchers (context-watcher)
- Set up Claude Code

No manual setup required inside the container.

## Security

**Isolation**:
- No SSH keys (can't push to GitHub)
- No cloud credentials (can't deploy to GCP/AWS)
- Network: Outbound HTTP only (Claude API, packages)
- No inbound ports (can't accept connections)

**What the agent CAN do**:
- Read/write code in `~/khan/`
- Commit locally (no push)
- Run tests and builds
- Read context docs (Confluence, JIRA)
- Write notifications for human review

**What the agent CANNOT do**:
- Push to GitHub (no SSH keys)
- Deploy to cloud (no credentials)
- Access host services (network isolated)
- Modify host filesystem (only mounted directories)
