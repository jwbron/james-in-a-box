# Sandboxed Environment - Technical Constraints

## Security Model

You run in a **sandboxed Docker container** with "Bypass Permissions" mode because multiple security boundaries protect the system:

| Boundary | Protection |
|----------|------------|
| Network | Bridge mode, outbound HTTP/HTTPS only, no inbound |
| Credentials | No SSH keys, cloud creds, or production access |
| Container | Cannot access host services or directories |

**You CAN**: Interact with GitHub via the GitHub MCP server (all reads, writes, PR operations)

## GitHub MCP Server (Primary GitHub Interface)

All GitHub operations go through the **GitHub MCP server**. This provides real-time, bi-directional access and replaces direct `gh` CLI usage.

**Available Tools:**
| Category | Tools |
|----------|-------|
| **Repositories** | `search_repositories`, `get_file_contents`, `push_files`, `create_or_update_file` |
| **Issues** | `search_issues`, `get_issue`, `create_issue`, `update_issue` |
| **Pull Requests** | `create_pull_request`, `get_pull_request`, `list_pull_requests`, `merge_pull_request` |
| **Comments** | `add_issue_comment`, `list_issue_comments` |
| **Branches** | `create_branch`, `list_branches` |
| **Commits** | `list_commits`, `get_commit` |

**When to use MCP vs local git:**
- **MCP**: All GitHub API operations (PRs, issues, comments, file reads from remote, pushing)
- **Local git**: Local commits, staging, diff viewing

**Authentication**: Configured automatically via `GITHUB_TOKEN` environment variable.

## Capabilities

**CAN do:**
- Read/edit code in `~/khan/`
- Run tests, dev servers, install packages
- Git commits locally
- Create/manage PRs via GitHub MCP
- Query issues, repos, comments via GitHub MCP
- Push files/changes via GitHub MCP
- Use PostgreSQL, Redis, Python, Node.js, Go, Java

**CANNOT do:**
- Merge PRs (human must approve first)
- Deploy to GCP/AWS (no credentials)
- Access production systems
- Accept inbound connections

## File System

| Path | Access | Purpose |
|------|--------|---------|
| `~/khan/` | RW | Code workspace (mounted from host) |
| `~/context-sync/confluence/` | RO | ADRs, runbooks, docs |
| `~/context-sync/jira/` | RO | JIRA tickets |
| `~/sharing/` | RW | Persistent data (survives rebuilds) |
| `~/sharing/tmp/` | RW | Scratch space (symlinked from `~/tmp/`) |
| `~/sharing/notifications/` | RW | Async messages → Slack DM (use notifications lib) |
| `~/sharing/context/` | RW | @save-context / @load-context data |
| `~/beads/` | RW | Persistent task memory |

## Custom Commands

| Command | Purpose |
|---------|---------|
| `@load-context <name>` | Load knowledge from `~/sharing/context/` |
| `@save-context <name>` | Save learnings to `~/sharing/context/` |
| `@create-pr [audit] [draft]` | Generate PR description |
| `@update-confluence-doc <path>` | Prepare Confluence updates |

## Services

PostgreSQL and Redis start automatically. Check status:
```bash
service postgresql status
service redis-server status
```

## Error Handling

**GitHub MCP fails** - Check `GITHUB_TOKEN` environment variable is set. MCP authentication is automatic.

**Cloud operations fail** - Expected. No credentials. Document what user needs to do on host.

**File not found** - Check `pwd`, verify mount exists.

## Package Installation

```bash
# System packages (NOT persisted on rebuild)
apt-get update && apt-get install -y package-name
pip install package-name
npm install -g package-name

# Project deps (persisted in code)
npm install --save package-name
pip install package >> requirements.txt
```
