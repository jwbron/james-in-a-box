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

All GitHub operations go through the **GitHub MCP server** (api.githubcopilot.com). This provides real-time, bi-directional access and replaces direct `gh` CLI usage.

**Configuration**: The MCP server is configured at container startup via `claude mcp add`:
```bash
claude mcp add --transport http github "https://api.githubcopilot.com/mcp/" \
    --header "Authorization: Bearer ${GITHUB_TOKEN}"
```

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

**IMPORTANT - Get owner/repo from local git first:**
Before any GitHub MCP operation, check the actual remote to get the correct owner/repo:
```bash
git remote -v   # e.g., origin https://github.com/jwbron/james-in-a-box.git
```
Do NOT assume owner from context (e.g., don't assume `Khan/` just because you're working on Khan Academy code). The local repo knows its origin - use that.

**Authentication**: Configured automatically via `GITHUB_TOKEN` environment variable.

**CRITICAL - Git Remote URLs:**
- **NEVER** modify git remote URLs using `git remote set-url` or similar commands
- **NEVER** embed tokens in git remote URLs (e.g., `https://token@github.com/...`)
- Remote URLs are managed by the HOST and must remain clean HTTPS URLs
- You have `GITHUB_TOKEN` as an environment variable for the GitHub MCP server
- The MCP server handles all GitHub authentication - you don't need to configure git credentials
- If you see a remote URL with an embedded token, DO NOT modify it - report it to the user

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
|---------|---------||
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
