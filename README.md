# James-In-A-Box (JIB)

**Autonomous software engineering agent in a sandboxed Docker container**

JIB enables engineers to delegate development tasks to Claude via Slack, with the agent working in a secure, isolated environment. The agent can read code, implement features, run tests, and prepare pull requests—all while you're mobile.

## What is JIB?

JIB is an **LLM-powered autonomous software engineer** that runs in a Docker sandbox with:

- **Slack-based control**: Send tasks, receive notifications, review work from your phone
- **Secure sandbox**: No credentials, network isolation, human-in-the-loop for all PRs
- **Context-aware**: Syncs Confluence docs, JIRA tickets, and codebase knowledge
- **Persistent memory**: Beads task tracking survives restarts, enables multi-session work
- **Mobile-first**: Fully productive workflow from phone (notifications, PR reviews, approvals)
- **Cultural alignment**: Behavior matches Khan Academy L3-L4 engineering standards

## Why We Built This

**Problem**: Engineering productivity is limited by desk time. Remote work, oncall, travel, and context-switching reduce available coding hours.

**Solution**: Delegate routine engineering tasks to an autonomous agent that:
- Works 24/7 in a secure sandbox
- Follows team standards and best practices
- Prepares work for human review and approval
- Enables full engineering workflow from mobile

**Key Principle**: The agent **prepares** artifacts (code, tests, PR descriptions). Engineers **review and ship** (merge PRs, deploy). Clear separation of responsibilities.

## How It Works

```
┌─────────────────────────────────────────────────────┐
│  You (Slack Mobile)                                 │
│  • Send tasks: "Implement OAuth2 for JIRA-1234"     │
│  • Receive notifications with summaries + threads   │
│  • Review and approve PRs from phone                │
└─────────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────────┐
│  Host Machine (Your Laptop)                         │
│  • Slack notifier/receiver (systemd services)       │
│  • Context sync (Confluence, JIRA → markdown)       │
│  • Automated analyzers (code quality, conversations)│
│  • Service monitoring and failure notifications     │
└─────────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────────┐
│  Docker Container (Sandbox)                         │
│  • Claude agent with isolated worktree workspace    │
│  • No credentials (SSH keys, cloud tokens excluded) │
│  • Network isolation (outbound HTTP only)           │
│  • Ephemeral - spun up per task, auto-cleanup       │
└─────────────────────────────────────────────────────┘
```

**Workflow:**
1. Send task via Slack DM to bot
2. Container spawns with isolated git worktree (host repos stay clean)
3. Agent implements changes, writes tests, commits to branch
4. Container shuts down, worktrees auto-cleanup
5. Agent sends Slack notification with branch name
6. You review commits and create PR from phone

### Worktree Isolation

Each container gets its own ephemeral git worktree, keeping your host repositories clean:

```
Host:
~/khan/webapp/                      # Your working directory (untouched!)
~/.jib-worktrees/
  └── jib-20251123-103045-12345/    # Container's isolated workspace
      └── webapp/                   # Worktree with changes

Container:
~/khan/webapp/                      # Mounted from worktree (not host repo)
```

**Benefits:**
- **Host protection**: Your `~/khan/` repos stay clean while you work
- **True parallelism**: Multiple containers can work on same repo simultaneously
- **Isolated branches**: Each container works on its own branch
- **Auto-cleanup**: Worktrees removed when container exits
- **Orphan detection**: Watcher cleans up crashed container worktrees every 15 min

## Quick Start

### Prerequisites

- Docker installed and running
- Python 3.8+
- Slack workspace with bot token

### Setup

1. **Clone repository**:
   ```bash
   cd ~/khan
   git clone <repo-url> james-in-a-box
   cd james-in-a-box
   ```

2. **Run master setup script**:
   ```bash
   ./setup.sh
   ```

   This will:
   - Install all host services (Slack notifier/receiver, analyzers, monitoring)
   - Enable systemd services and timers
   - Create required directories
   - Verify dependencies
   - Display setup status

   **Updating existing installation:**
   ```bash
   ./setup.sh --update
   ```

   This will:
   - Re-symlink service files (pick up any changes)
   - Reload systemd daemon
   - Restart all services
   - Skip interactive prompts

   <details>
   <summary>Or set up components individually</summary>

   ```bash
   # Slack notifier (Claude → You)
   cd components/slack-notifier && ./setup.sh

   # Slack receiver (You → Claude)
   cd components/slack-receiver && ./setup.sh

   # Conversation analyzer (optional)
   cd components/conversation-analyzer && ./setup.sh

   # Codebase analyzer (optional)
   cd components/codebase-analyzer && ./setup.sh

   # Service monitor (optional)
   cd components/service-monitor && ./setup.sh
   ```
   </details>

3. **Configure Slack tokens** (if not done during setup):
   ```bash
   # Edit config file
   nano ~/.config/jib-notifier/config.json

   # Add your tokens:
   # - Bot token (xoxb-...)
   # - App token (xapp-...)
   ```

4. **Start container**:
   ```bash
   cd ~/khan/james-in-a-box
   bin/jib
   ```

5. **Send first task** (from Slack):
   ```
   DM the bot: "Implement hello world function in Python with tests"
   ```

The agent will receive your task, implement the code, and send you a notification when ready for review.

## Architecture

### Host Components (systemd services)

All host components run as systemd user services for reliability and auto-restart:

- **[slack-notifier](components/slack-notifier/README.md)** - Sends Claude's notifications to Slack (inotify-based, instant)
- **[slack-receiver](components/slack-receiver/README.md)** - Receives your messages and responses from Slack (Socket Mode)
- **[context-sync](components/context-sync/README.md)** - Syncs Confluence/JIRA to `~/context-sync/` (hourly)
- **[github-sync](components/github-sync/README.md)** - Syncs PR data and check status to `~/context-sync/github/` (every 15 min)
- **[worktree-watcher](components/worktree-watcher/README.md)** - Cleans up orphaned git worktrees (every 15 minutes)
- **[codebase-analyzer](components/codebase-analyzer/README.md)** - Weekly automated code review (Mondays 11 AM)
- **[conversation-analyzer](components/conversation-analyzer/README.md)** - Daily conversation quality analysis (2 AM)
- **[service-monitor](components/service-monitor/README.md)** - Notifies on service failures

### Container Components

- **[context-watcher](jib-container/components/context-watcher/README.md)** - Monitors `~/context-sync/` for doc updates
- **[github-watcher](jib-container/components/github-watcher/README.md)** - Monitors PR check failures, auto-fixes issues, and provides on-demand code reviews
- **[.claude](jib-container/.claude/README.md)** - Claude Code configuration (rules, commands, prompts)
- **[beads](https://github.com/steveyegge/beads)** - Persistent task memory system (git-backed, multi-container)

### Shared Directories

```
~/.jib-sharing/                      # Persists across container rebuilds
├── notifications/                   # Claude → You (Slack DMs)
│   ├── YYYYMMDD-HHMMSS-topic.md    # Summary (top-level)
│   └── RESPONSE-*.md                # Detail (threaded)
├── incoming/                        # You → Claude (tasks)
│   └── task-YYYYMMDD-HHMMSS.md
├── responses/                       # You → Claude (replies)
│   └── RESPONSE-YYYYMMDD-HHMMSS.md
├── context/                         # Persistent agent knowledge
│   └── project-name.md
└── beads/                          # Persistent task memory (git repo)
    ├── issues.jsonl                # Task database (source of truth)
    ├── .git/                       # Git history
    └── .beads.sqlite               # SQLite cache (auto-rebuilt)

~/.jib-worktrees/                    # Ephemeral (per-container workspaces)
└── jib-YYYYMMDD-HHMMSS-PID/        # Unique container ID
    ├── webapp/                      # Isolated worktree for webapp repo
    └── frontend/                    # Isolated worktree for frontend repo

~/context-sync/                      # Read-only context sources
├── confluence/                      # Confluence docs (ADRs, runbooks)
├── jira/                           # JIRA tickets (issues, epics)
└── github/                         # GitHub PR data (metadata, diffs, checks)
    ├── prs/                        # PR files and diffs
    └── checks/                     # Check status and logs
```

## Usage Patterns

### Sending Tasks to Claude

**From Slack**, DM the bot with your request:
```
Implement OAuth2 authentication for JIRA-1234
```

The bot confirms receipt and queues the task.

### Receiving Notifications

Claude sends **mobile-optimized notifications**:
- **Summary** (top-level): Key metrics, priority, 3-5 lines
- **Detail** (thread): Full report, recommendations, next steps

This keeps your Slack feed clean while providing full context when needed.

### Responding to Claude

When Claude needs guidance, **reply in the thread**:
```
Claude: 🔔 Found better caching approach - should I switch?

You: Yes, switch to session caching and update the spec
```

Your response is automatically linked by timestamp.

### Remote Control Commands

Control JIB remotely from Slack:
```
/jib restart                     - Restart container
/jib rebuild                     - Rebuild and restart
/jib status                      - Check container status
/jib logs                        - View recent logs

/service restart <name>          - Restart a service
/service status <name>           - Check service status
/service list                    - List all services

/pr create [repo]                - Create draft PR for current branch
/pr create [repo] --ready        - Create ready-for-review PR
/pr review <num> [repo]          - Generate code review for PR

help                             - Show all commands
```

Commands execute asynchronously and send results as notifications.

**PR Creation Examples:**
```
/pr create                       - Create PR in james-in-a-box
/pr create webapp                - Create PR in ~/khan/webapp
/pr create frontend --ready      - Create non-draft PR
```

PR descriptions are generated using Claude in the JIB container following Khan Academy standards. Notifications include repository, source branch, target branch, and PR URL.

**PR Review Examples:**
```
review PR 123                    - Generate code review for PR #123
review PR 123 in webapp          - Review PR in specific repository
/pr review 456                   - Alternative command syntax
```

Reviews analyze code changes for:
- Security concerns (SQL injection, XSS, eval usage)
- Performance issues
- Code quality and best practices
- Testing coverage gaps
- File-by-file detailed feedback

Reviews are sent as Slack notifications with prioritized findings (high/medium/low severity).

### Using Beads for Task Tracking

**Beads** provides persistent task memory that survives container rebuilds and enables coordination across multiple containers.

**When to use:**
- Multi-session tasks that span multiple container restarts
- Complex features with dependencies and subtasks
- Coordinating work across concurrent containers
- Tracking blockers and progress over time

**Quick start:**
```bash
# Inside container
cd ~/beads

# Create task
beads add "Implement OAuth2 authentication" --tags feature,security

# List tasks ready to work on
beads ready

# Update status
beads update bd-a3f8 --status in-progress

# Add notes
beads update bd-a3f8 --notes "Using RFC 6749 spec, per ADR-042"

# Mark complete
beads update bd-a3f8 --status done
```

**Custom commands:**
- `@beads-status` - Show current tasks, ready work, and blockers
- `@beads-sync` - Commit Beads state to git and rebuild cache

**Storage:**
- Location: `~/.jib-sharing/beads/` (git repository)
- Access: `~/beads/` in container (all containers share same database)
- Persistence: Survives container rebuilds, accessible to all containers

See [Beads documentation](https://github.com/steveyegge/beads) and container rules at `jib-container/.claude/rules/beads-usage.md` for detailed usage.

## Security Model

**5-Layer Defense Against Data Exfiltration:**

1. **Human Review** (Phase 1 - Current)
   - All PRs require human approval before merge
   - MEDIUM risk, acceptable for pilot

2. **Context Source Filtering** (Phase 2)
   - Confluence/JIRA allowlists
   - Exclude customer data (SUPPORT, SALES, etc.)

3. **Content Classification** (Phase 2)
   - Tag docs: Public/Internal/Confidential
   - Agent skips Confidential content

4. **DLP Scanning** (Phase 3)
   - Cloud DLP before Claude API calls
   - Automated redaction of PII, secrets

5. **Output Monitoring** (Phase 3)
   - Scan PRs, commits, Slack for leaks
   - Alert on sensitive data exposure

**Current Risk**: MEDIUM (human review only)
**Target Risk**: LOW (full DLP + monitoring operational)

**Sandbox Isolation:**
- No SSH keys (can't push to GitHub)
- No cloud credentials (can't deploy)
- Network: Outbound HTTP only (Claude API, packages)
- Container: No inbound ports, bridge networking

## Development Workflow

### Agent Workflow

1. **Receive task** from `~/sharing/incoming/`
2. **Load context** from Confluence docs, JIRA tickets, previous sessions
3. **Plan and implement** following team standards and ADRs
4. **Test thoroughly** (unit tests, integration tests, linters)
5. **Prepare PR artifacts** (commits, PR description, test plan)
6. **Send notification** to human for review

### Human Workflow

1. **Send task** via Slack (from anywhere)
2. **Receive notification** when work is ready
3. **Review PR** (from phone or desktop)
4. **Approve and merge** (or request changes)
5. **Deploy** when ready (human controls deployment)

**Agent does**: Generate, document, test
**Human does**: Review and ship

## Management Commands

### Service Control

```bash
# Check all services
systemctl --user list-timers | grep -E 'conversation|codebase'
systemctl --user status slack-notifier.service
systemctl --user status slack-receiver.service

# View logs
journalctl --user -u slack-notifier.service -f
journalctl --user -u codebase-analyzer.service -f

# Restart services
systemctl --user restart slack-notifier.service
systemctl --user restart slack-receiver.service
```

### Container Control

```bash
# Start container
bin/jib

# Rebuild container (if Docker config changes)
bin/jib --rebuild

# Stop container
docker stop jib-claude

# View container logs
docker logs -f jib-claude
```

## Documentation

### Architecture & Decisions

- **[ADR: Autonomous Software Engineer](docs/adr/adr-autonomous-engineer-session.md)** - Complete architectural decisions
- **[Slack Integration Architecture](docs/architecture/slack-integration.md)** - Bidirectional Slack communication
- **[Service Failure Notifications](docs/reference/service-failure-notifications.md)** - Monitoring and alerting

### Component READMEs

**Host Services:**
- [slack-notifier](components/slack-notifier/README.md) - Outgoing notifications
- [slack-receiver](components/slack-receiver/README.md) - Incoming messages
- [codebase-analyzer](components/codebase-analyzer/README.md) - Code review automation
- [conversation-analyzer](components/conversation-analyzer/README.md) - Quality analysis
- [service-monitor](components/service-monitor/README.md) - Failure monitoring

**Container Components:**
- [context-watcher](jib-container/components/context-watcher/README.md) - Document monitoring
- [.claude rules](jib-container/.claude/rules/README.md) - Agent behavior and standards

### Guides

- **[Notification Template](jib-container/.claude/rules/notification-template.md)** - How to send notifications from agent
- **[Slack Quick Reference](docs/reference/slack-quick-reference.md)** - Common Slack commands

## Roadmap

**Current (Phase 1)**:
- ✅ Docker sandbox with Slack integration
- ✅ File-based context sync (Confluence, JIRA)
- ✅ Mobile-first notification system
- ✅ Automated analyzers (code, conversations)
- ✅ Service monitoring and failure alerts

**Phase 2** (Near-term):
- Context source filtering (allowlists/blocklists)
- Content classification (Public/Internal/Confidential)
- Monitoring infrastructure (API calls, task completion)
- MCP servers for real-time context access

**Phase 3** (Future):
- Cloud Run deployment (multi-engineer)
- DLP scanning (before Claude API calls)
- Output monitoring (PR descriptions, commits)
- Workload Identity (no credential files)

## Troubleshooting

### Services Not Starting

**Check dependencies**:
```bash
systemctl --user status slack-notifier.service
journalctl --user -u slack-notifier.service --no-pager
```

**Common issues**:
- Missing Slack tokens in `~/.config/jib-notifier/config.json`
- Python dependencies not installed (`pip install slack-sdk`)
- Notification directory doesn't exist (create `~/.jib-sharing/notifications/`)

### Container Issues

**Check container is running**:
```bash
docker ps | grep jib-claude
```

**View logs**:
```bash
docker logs jib-claude
```

**Rebuild if needed**:
```bash
bin/jib --rebuild
```

### Slack Not Receiving Messages

1. Verify bot token is valid (check `~/.config/jib-notifier/config.json`)
2. Check Slack app has required scopes (`chat:write`, `im:history`)
3. Verify slack-receiver service is running (`systemctl --user status slack-receiver`)
4. Check logs: `journalctl --user -u slack-receiver.service -f`

## Contributing

This is an internal Khan Academy tool. For questions or issues:

1. Check component READMEs for specific guidance
2. Review architecture docs in `docs/`
3. Check service logs for error details

## License

Internal Khan Academy use only.
