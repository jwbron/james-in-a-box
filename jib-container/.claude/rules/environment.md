# Sandboxed Environment - Technical Constraints

## Security Model

You run in a **sandboxed Docker container** with "Bypass Permissions" mode because multiple security boundaries protect the system:

| Boundary | Protection |
|----------|------------|
| Network | Bridge mode, outbound HTTP/HTTPS only, no inbound |
| Credentials | No SSH keys, cloud creds, or production access |
| Container | Cannot access host services or directories |

**You CAN**:
- Push code via `git push` (authenticated via GitHub App token)
- Interact with GitHub via the GitHub MCP server (PRs, issues, comments)

## Git Push (Primary Method for Pushing Code)

**Use `git push` for pushing commits to GitHub.** The container is configured with a GitHub App token that authenticates via a git credential helper.

**How to push:**
```bash
# 1. Commit your changes locally
git add <files>
git commit -m "Your commit message"

# 2. Push to remote
git push origin <branch>
```

**Requirements:**
- Remote URL must be HTTPS (not SSH) - the container has no SSH keys
- `GITHUB_TOKEN` environment variable must be set (handled by jib launcher)

**If push fails:**
- Check the remote URL: `git remote -v` (must be `https://github.com/...`)
- If it's SSH (`git@github.com:...`), ask the user to change it on the HOST

**CRITICAL - Git Remote URLs:**
- **NEVER** modify git remote URLs using `git remote set-url` or similar commands
- **NEVER** embed tokens in git remote URLs (e.g., `https://token@github.com/...`)
- Remote URLs are managed by the HOST and must remain clean HTTPS URLs
- Authentication is handled automatically by the git credential helper
- If you see a remote URL with an embedded token, DO NOT modify it - report it to the user

## GitHub MCP Server (For PRs, Issues, Comments)

The **GitHub MCP server** (api.githubcopilot.com) provides access to GitHub API operations. Use it for creating PRs, managing issues, and adding comments.

**Configuration**: The MCP server is configured at container startup via `claude mcp add`:
```bash
claude mcp add --transport http github "https://api.githubcopilot.com/mcp/" \
    --header "Authorization: Bearer ${GITHUB_TOKEN}"
```

**Available Tools:**
| Category | Tools |
|----------|-------|
| **Repositories** | `search_repositories`, `get_file_contents` |
| **Issues** | `search_issues`, `get_issue`, `create_issue`, `update_issue` |
| **Pull Requests** | `create_pull_request`, `get_pull_request`, `list_pull_requests`, `merge_pull_request` |
| **Comments** | `add_issue_comment`, `list_issue_comments` |
| **Branches** | `create_branch`, `list_branches` |
| **Commits** | `list_commits`, `get_commit` |

**When to use git vs MCP:**
- **git push**: Pushing commits to GitHub (preferred for large files/many files)
- **MCP**: Creating PRs, managing issues, adding comments, reading remote files

**IMPORTANT - Get owner/repo from local git first:**
Before any GitHub MCP operation, check the actual remote to get the correct owner/repo:
```bash
git remote -v   # e.g., origin https://github.com/jwbron/james-in-a-box.git
```
Do NOT assume owner from context (e.g., don't assume `Khan/` just because you're working on Khan Academy code). The local repo knows its origin - use that.

**Authentication**: Configured automatically via `GITHUB_TOKEN` environment variable.

## Capabilities

**CAN do:**
- Read/edit code in `~/khan/`
- Run tests, dev servers, install packages
- Git commits and push via `git push` (HTTPS only)
- Create/manage PRs via GitHub MCP
- Query issues, repos, comments via GitHub MCP
- Use PostgreSQL, Redis, Python, Node.js, Go, Java

**CANNOT do:**
- Merge PRs (human must approve first)
- Git push via SSH (no SSH keys - use HTTPS)
- Deploy to GCP/AWS (no credentials)
- Access production systems
- Accept inbound connections

## File System

| Path | Access | Purpose |
|------|--------|---------|n| `~/khan/` | RW | Code workspace (mounted from host) |
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

**Git push fails** - Check:
1. Remote is HTTPS (not SSH): `git remote -v`
2. `GITHUB_TOKEN` is set (should be automatic)
3. If SSH remote, ask user to change it on HOST to HTTPS

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
