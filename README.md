# Claude Code Sandboxed - Autonomous Software Engineering Agent

**Status**: Production - v1.0

Run Claude Code CLI as an autonomous software engineering agent in a sandboxed Docker environment that prevents access to credentials while providing full development capabilities.

## What Is This?

An isolated Docker environment where Claude Code operates as an **autonomous agent**. Claude plans, implements, tests, documents, and prepares PR artifacts while you review and ship the work.

### The Operating Model

```
┌─────────────────────────────────────────────────────────┐
│  YOU (Engineer)                                         │
│  • Open and manage PRs                                  │
│  • Review and merge                                     │
│  • Deploy to production                                 │
│  • Handle credentials and secrets                       │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │ PR for review
                           │
┌─────────────────────────────────────────────────────────┐
│  CLAUDE (Autonomous Agent)                              │
│  • Plan implementation                                  │
│  • Write code and tests                                 │
│  • Create documentation                                 │
│  • Generate PR artifacts (code, descriptions)           │
│  • Build accumulated knowledge                          │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# First time: Build and start
./claude-sandboxed

# Inside container: Start Claude
claude

# Work with Claude
@load-context myproject        # Load accumulated knowledge
# [work on task naturally]
@create-pr audit               # Create PR when done
@save-context myproject        # Save learnings

# Exit and review PR on host
exit
```

## Key Features

### ✅ What Claude CAN Do
- Edit code in `~/khan/` workspace
- Run tests, linters, development servers
- Make local git commits
- Read context sources: Confluence docs, JIRA tickets, and more
- Install packages and tools
- Build reusable scripts in `~/tools/`
- Save work to `~/sharing/` (persists across rebuilds)
- Prepare PR artifacts (code, commits, descriptions)

### ❌ What Claude CANNOT Do
- Push to git remotes (no SSH keys)
- Deploy to GCP (no gcloud credentials)
- Access Google Secret Manager (no auth)
- Access any cloud credentials (AWS, Kubernetes, etc.)
- Modify host system

## Architecture

### Security Model

**Mounted from Host:**
- `~/khan/` - Main workspace (read-write, live sync with host)
- `~/.claude/.credentials.json` - OAuth only (read-only)
- `~/context-sync/` - Context sources (read-only)
  - `confluence/` - Documentation (ADRs, runbooks, best practices)
  - `jira/` - JIRA tickets and issue context
  - (future: GitHub PRs, Slack, email)
- `~/tools/` - Reusable scripts (read-write, persists)
- `~/sharing/` - Work products and context docs (read-write, persists)

**Blocked (Never Accessible):**
- `~/.ssh` - No git push capability
- `~/.config/gcloud` - No cloud deployments
- All other credential directories

**Result:**
- ✅ Claude can implement features and prepare PR artifacts
- ❌ Claude cannot push to git or deploy to production
- ✅ You open PRs, review, and approve all changes
- ❌ No accidental credential exposure

### Container Structure

```
Inside Container:
  ~/khan/                      Code workspace (MOUNTED rw)
  ~/context-sync/              Context sources (MOUNTED ro)
    ├── confluence/            Confluence docs (ADRs, runbooks)
    ├── jira/                  JIRA tickets and issues
    └── logs/                  Sync logs
  ~/tools/                     Reusable scripts (MOUNTED rw)
  ~/sharing/                   Persistent data (MOUNTED rw)
    └── context/               Context documents
  ~/tmp/                       Scratch space (ephemeral)
  ~/CLAUDE.md                  Mission + environment rules
  ~/khan/CLAUDE.md             Khan Academy standards
```

### Development Environment

**Languages & Runtimes:**
- Python 3.11, Node.js 20.x, Go, Java 11

**Services:**
- PostgreSQL 14, Redis

**Command-Line Tools:**
- **Text processing**: grep, sed, awk, cut, sort, uniq, tr, less, vim, nano
- **Build tools**: make, cmake, gcc, g++, autoconf, automake
- **Network**: curl, wget, netcat, telnet, ping, dig, nslookup
- **File ops**: find, xargs, rsync, tar, gzip, zip, unzip
- **Process mgmt**: ps, top, htop, lsof, kill, pkill
- **System info**: df, du, free, uptime
- **Debugging**: strace, ltrace, gdb
- **Other**: jq, tree, watch, tmux, screen

**Development Tools:**
- Git, mkcert, watchman, Fastly CLI
- Image processing libraries

**NOT Included (by design):**
- SSH keys, gcloud, cloud credentials

### Network & Security Model

**Network Mode:** Bridge networking (isolated from host network)

**Internet Access:** Outbound HTTP/HTTPS only (for Claude API and package downloads)

**No Exposed Ports:** Container cannot accept inbound connections from host or network

**Security Boundaries:**
- ✅ **Credential isolation** - No SSH keys, cloud credentials, or production access
- ✅ **Network isolation** - Cannot access host services (databases, APIs running on host)
- ✅ **No inbound access** - Container cannot be reached from outside
- ✅ **Containerization** - Cannot damage host system

**What the agent CAN do:**
- Access the internet (Claude API, package downloads via HTTP/HTTPS)
- Use PostgreSQL and Redis (running inside container)
- Make outbound HTTP requests

**What the agent CANNOT do:**
- Access host services (host's PostgreSQL, APIs, etc.)
- Accept inbound connections (no ports exposed)
- Push to git (no SSH keys)
- Deploy to cloud (no credentials)
- Access production databases (no credentials)

**Result:** Multiple layers of isolation - credential-based, network-based, and port-based - make this safe for autonomous operation with "Bypass Permissions" mode.

## Context Sources

### Available Now (v1.0)
- ✅ **Confluence Documentation** (`~/context-sync/confluence/`)
  - ADRs (Architecture Decision Records)
  - Runbooks and operational docs
  - Best practices and team standards
  - Process documentation

- ✅ **JIRA Tickets** (`~/context-sync/jira/`)
  - Issue descriptions and comments
  - Sprint and epic context
  - Bug reports and feature requests
  - Project tracking data

### Roadmap (v1.1+)
- 🔄 GitHub PR integration (`~/context-sync/github/`)
- 🔄 Slack messages (`~/context-sync/slack/`)
- 🔄 Email threads (`~/context-sync/email/`)

## Custom Commands

### @load-context <filename>
Load accumulated knowledge from previous sessions.

```bash
@load-context auth-refactor
# Claude: "✅ Loaded 3 sessions, 5 playbooks, 2 anti-patterns"
```

Saves to: `~/sharing/context/<filename>.md` (persists across rebuilds)

### @save-context <filename>
Save current session using ACE (Agentic Context Engineering) methodology.

```bash
@save-context auth-refactor
# Claude: "✅ Saved Session 4 - captured implementation, lessons, playbooks"
```

**ACE Methodology:**
- **Generation**: What was implemented
- **Reflection**: What was learned
- **Curation**: Playbooks and anti-patterns

### @create-pr [audit] [draft]
Prepare pull request artifacts (analyzes commits, generates description file).

```bash
@create-pr audit
# Claude: [Analyzes commits, generates PR description]
# You: Open PR on GitHub using the generated description
```

## Typical Workflow

```bash
# 1. Start container
./claude-sandboxed
claude

# 2. Load context
@load-context auth-service

# 3. Give Claude a task
You: "Implement OAuth2 flow following ADR-012 for JIRA-1234"

# Claude works autonomously:
# - Reads ADR-012 from context-sync/confluence/
# - Reviews JIRA-1234 from context-sync/jira/
# - Implements feature
# - Writes tests
# - Updates documentation
# - Commits locally

# 4. Generate PR description
You: "Prepare the PR"
@create-pr audit

# 5. Save learnings
@save-context auth-service

# 6. Exit, open PR, and review (on host)
exit
cd ~/khan/
git log  # Review Claude's commits
git push origin feature-branch
# Open PR on GitHub with generated description
# Review, approve, and merge
```

## Philosophy

### Force Multiplier, Not Replacement

Claude handles implementation while you focus on:
- Architecture and design decisions
- Opening and managing PRs
- Code review and quality assurance
- Deployment and operations
- Team coordination and communication

### Accumulating Wisdom

Each session builds on the last through context documents:
- **Generation**: Capture what was implemented
- **Reflection**: Analyze what was learned
- **Curation**: Create reusable playbooks

Knowledge compounds over time - Claude becomes more effective as it learns project patterns.

### Responsible Autonomy

Claude works independently on clear tasks but asks when:
- Requirements are ambiguous
- Architecture decisions are needed
- Cross-team coordination is required
- Security implications are unclear

## Example: Building Knowledge Over Time

**Session 1** (Initial Redis implementation):
```bash
You: "Migrate user service to Redis caching"
Claude: [Implements, encounters connection issues, resolves them]
@save-context redis-migration
# Saves: Connection setup steps, common pitfalls
```

**Session 2** (Weeks later, different service):
```bash
@load-context redis-migration
You: "Migrate auth service to Redis"
Claude: "Based on Session 1, I'll validate Redis connectivity in 
staging before updating production config. That prevented issues 
last time..."
# Applies accumulated wisdom automatically
```

**Result**: Faster implementation, fewer mistakes, compounding knowledge.

## Requirements

- Docker (script will offer to install on Linux)
- Claude Code CLI with OAuth authentication
- Linux (tested on Ubuntu, Fedora, Asahi ARM64) or macOS

## Security Notes

### Threat Model

**Goal**: Prevent accidental or intentional access to production credentials.

**Accept**: Claude can read/write sandboxed code and prepare PR artifacts for human review.

### Defense Layers

1. **Filesystem isolation** - Blocked credential directories
2. **No cloud authentication** - gcloud, AWS, kubectl not available
3. **Human-in-the-loop** - All deployments require human action
4. **Audit trail** - Git commits and PRs track all changes

### What Could Go Wrong?

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Buggy code | Medium | Tests + PR review |
| Bad architecture | Low | ADR review + human judgment |
| Credential leak | Very Low | No credentials in container |
| ✅ Cannot deploy | N/A | Design goal achieved |

## Files Structure

```
cursor-sandboxed/
├── claude-sandboxed              # Main orchestration script
├── Dockerfile                    # Container definition
├── docker-setup.py               # Dev environment installer
├── README.md                     # This file
├── QUICKSTART.md                 # Practical daily reference
├── claude-rules/                 # Agent instructions
│   ├── README.md                 # Rules system guide
│   ├── mission.md                # Role and workflow
│   ├── environment.md            # Technical constraints
│   ├── khan-academy.md           # Project standards
│   └── tools-guide.md            # Building reusable tools
└── claude-commands/              # Custom commands
    ├── README.md
    ├── load-context.md
    ├── save-context.md
    └── create-pr.md
```

## Commands Reference

```bash
# Run agent (builds on first use)
./claude-sandboxed

# Inside container
claude                          # Start Claude Code CLI
exit                            # Exit container

# Management (if needed)
./claude-sandboxed --setup      # Reconfigure mounts
./claude-sandboxed --reset      # Complete reset
```

## Troubleshooting

See **QUICKSTART.md** for common issues and solutions.

**Quick fixes:**
- Not authenticated: OAuth credentials should be copied automatically
- Container won't start: Check Docker is running
- Changes disappeared: Only `~/sharing/` persists across rebuilds

## Contributing

This is an early-stage personal tool. Ideas and contributions welcome for:
- Additional context sources (GitHub, Slack, JIRA)
- Enhanced autonomy patterns
- Team collaboration features
- Security improvements

## Credits

**Based on research:**
- Paper: "Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models"
- Authors: Zhang et al., 2025
- ArXiv: https://arxiv.org/abs/2510.04618

**Inspired by:**
- ACE (Agentic Context Engineering) methodology
- Autonomous AI pair programming concepts

## License

MIT

---

**See also:**
- **QUICKSTART.md** - Practical daily reference
- **claude-rules/README.md** - Agent instructions system
- **claude-commands/README.md** - Custom commands guide
