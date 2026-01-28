# Sandboxed Environment

You run in a sandboxed Docker container with network lockdown. No SSH keys, cloud creds, or production access.

## Network Lockdown

Network traffic is routed through a filtering proxy. Only `api.anthropic.com` (Claude API) is allowed through the proxy.

**GitHub access** MUST go through the gateway sidecar's git/gh wrappers (not through the proxy). This ensures policy enforcement (branch ownership, merge blocking, etc.) cannot be bypassed.

You CANNOT:
- Access PyPI, npm, or any package registry (dependencies are pre-installed)
- Use web search or fetch arbitrary URLs
- Access any website not on the allowlist

## Capabilities

**CAN**: Read/edit `~/repos/`, run tests, `git push` (HTTPS), `gh` CLI (PRs, issues), PostgreSQL, Redis, Python, Node.js, Go, Java

**CANNOT**: Merge PRs, SSH push, deploy to GCP/AWS, access production, access GitHub tokens directly

## Gateway Sidecar

All git/gh operations are routed through the gateway sidecar (runs as `jib-gateway` container on the jib-isolated network). The container does NOT have direct access to GitHub tokens - credentials are held by the gateway.

**Policy enforcement:**
- `git push`: Only to branches you own (jib-prefixed or has your open PR)
- `git fetch/pull/ls-remote`: Routed through gateway for authentication
- `git remote update`: Converted to `fetch --all` via gateway
- `gh pr merge`: **Blocked** - human must merge via GitHub UI
- `gh pr comment/edit/close`: Only on PRs you authored

## Git/Gh Binary Redirection

Both `/usr/bin/git` and `/usr/bin/gh` are symlinked to the gateway wrappers. All invocations (whether `git` or `/usr/bin/git`) route through the gateway sidecar for policy enforcement. The real binaries are relocated to a hidden path.

## Git Push

Use `git push origin <branch>` (HTTPS). Operations are authenticated by the gateway sidecar.

If push fails:
- Check `git remote -v` is HTTPS
- Check gateway sidecar is running: `curl http://gateway:9847/api/v1/health`
- Ensure branch is jib-owned (jib-prefixed or has your open PR)

## File System

| Path | Purpose |
|------|---------|
| `~/repos/` | Code workspace (RW) - mounted repositories |
| `~/context-sync/` | Confluence/JIRA (RO) |
| `~/sharing/` | Persistent data, notifications, context |
| `~/beads/` | Task memory |

## Available Commands

- `discover-tests`, `@load-context`, `@save-context`, `@create-pr`
- PostgreSQL and Redis start automatically

## Working with Network Lockdown

1. **Web search/fetch will fail** - Use local codebase search instead
2. **Package installation fails** - All common dependencies are pre-installed; if you need a package that's missing, note it in your PR description
3. **External URLs blocked** - Claude API works; GitHub access goes through gateway; everything else returns HTTP 403

If a tool returns 403 Forbidden, acknowledge the limitation and proceed with local resources.
