# Sandboxed Environment

You run in a sandboxed Docker container. Network: outbound HTTP/HTTPS only. No SSH keys, cloud creds, or production access.

## Capabilities

**CAN**: Read/edit `~/khan/`, run tests, `git push` (HTTPS), `gh` CLI (PRs, issues), PostgreSQL, Redis, Python, Node.js, Go, Java

**CANNOT**: Merge PRs, SSH push, deploy to GCP/AWS, access production

## Git Push

Use `git push origin <branch>` (HTTPS, GitHub App token). NEVER modify remote URLs or embed tokens.

If push fails: Check `git remote -v` is HTTPS, check `GITHUB_TOKEN` is set.

## File System

| Path | Purpose |
|------|---------|
| `~/khan/` | Code workspace (RW) |
| `~/context-sync/` | Confluence/JIRA (RO) |
| `~/sharing/` | Persistent data, notifications, context |
| `~/beads/` | Task memory |

## Available Commands

- `discover-tests`, `@load-context`, `@save-context`, `@create-pr`
- PostgreSQL and Redis start automatically
