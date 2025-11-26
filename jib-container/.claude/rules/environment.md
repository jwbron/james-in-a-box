# Sandboxed Environment - Technical Constraints

## Security Model

You run in a **sandboxed Docker container** with "Bypass Permissions" mode because multiple security boundaries protect the system:

| Boundary | Protection |
|----------|------------|
| Network | Bridge mode, outbound HTTP/HTTPS only, no inbound |
| Credentials | No SSH keys, cloud creds, or production access |
| Container | Cannot access host services or directories |

**You CAN**: Push to GitHub via `GITHUB_TOKEN` and `create-pr-helper.py`

## MCP Servers (Real-Time External Access)

You have access to Model Context Protocol (MCP) servers for real-time external data:

| Server | Capabilities | Authentication |
|--------|--------------|----------------|
| **github** | Repos, issues, PRs, search, file contents | `GITHUB_TOKEN` (auto-configured) |
| **atlassian** | Jira tickets, Confluence pages, search | OAuth (requires first-use setup) |

**GitHub MCP Tools:**
- `search_repositories`, `get_file_contents`, `push_files`
- `search_issues`, `get_issue`, `create_issue`
- `create_pull_request`, `add_issue_comment`

**Atlassian MCP Tools:**
- `jira_search`, `jira_get_issue`, `jira_create_issue`, `jira_update_issue`
- `jira_add_comment`, `jira_transition_issue`
- `confluence_search`, `confluence_get_page`

**When to use MCP vs file-based context:**
- **MCP**: Real-time data, bi-directional operations (comment, update, create)
- **File-based (~context-sync/)**: Bulk documentation, stable reference content

## Capabilities

**CAN do:**
- Read/edit code in `~/khan/`
- Run tests, dev servers, install packages
- Git commits and PRs (via helper)
- Use PostgreSQL, Redis, Python, Node.js, Go, Java
- Query GitHub/Jira/Confluence in real-time via MCP
- Create/update issues and PRs via MCP

**CANNOT do:**
- Merge PRs (human must)
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

**GitHub push fails ("could not read Username")**:
```bash
gh auth setup-git
```

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
