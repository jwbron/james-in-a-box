# James-In-A-Box (JIB)

**Autonomous software engineering agent in a sandboxed Docker container**

JIB enables engineers to delegate development tasks to Claude via Slack, with the agent working in a secure, isolated environment. The agent can read code, implement features, run tests, and prepare pull requests—all while you're mobile.

## What is JIB?

JIB is an **LLM-powered autonomous software engineer** that runs in a Docker sandbox with:

- **Slack-based control**: Send tasks, receive notifications, review work from your phone
- **Secure sandbox**: No credentials, network isolation, human-in-the-loop for all PRs
- **Context-aware**: Syncs Confluence docs, JIRA tickets, and codebase knowledge
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
│  • Claude agent with codebase access                │
│  • No credentials (SSH keys, cloud tokens excluded) │
│  • Network isolation (outbound HTTP only)           │
│  • Context watcher (monitors doc updates)           │
└─────────────────────────────────────────────────────┘
```

**Workflow:**
1. Send task via Slack DM to bot
2. Agent receives task, gathers context (docs, code)
3. Agent implements changes, writes tests, prepares PR
4. Agent sends Slack notification with summary
5. You review PR from phone and merge

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

2. **Set up host services** (Slack integration, analyzers):
   ```bash
   # Slack notifier (Claude → You)
   cd components/slack-notifier && ./setup.sh

   # Slack receiver (You → Claude)
   cd components/slack-receiver && ./setup.sh

   # Conversation analyzer (optional, daily quality checks)
   cd components/conversation-analyzer && ./setup.sh

   # Codebase analyzer (optional, weekly code review)
   cd components/codebase-analyzer && ./setup.sh

   # Service failure notifications (optional, monitors above services)
   cd components/service-monitor && ./setup.sh
   ```

3. **Start container**:
   ```bash
   cd ~/khan/james-in-a-box
   ./jib
   ```

4. **Send first task** (from Slack):
   ```
   DM the bot: "Implement hello world function in Python with tests"
   ```

The agent will receive your task, implement the code, and send you a notification when ready for review.

## Architecture

### Host Components (systemd services)

All host components run as systemd user services for reliability and auto-restart:

- **[slack-notifier](components/slack-notifier/README.md)** - Sends Claude's notifications to Slack (inotify-based, instant)
- **[slack-receiver](components/slack-receiver/README.md)** - Receives your messages and responses from Slack (Socket Mode)
- **[codebase-analyzer](components/codebase-analyzer/README.md)** - Weekly automated code review (Mondays 11 AM)
- **[conversation-analyzer](components/conversation-analyzer/README.md)** - Daily conversation quality analysis (2 AM)
- **[service-monitor](components/service-monitor/README.md)** - Notifies on service failures

### Container Components

- **[context-watcher](jib-container/components/context-watcher/README.md)** - Monitors `~/context-sync/` for doc updates
- **[.claude](jib-container/.claude/README.md)** - Claude Code configuration (rules, commands, prompts)

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
└── context/                         # Persistent agent knowledge
    └── project-name.md

~/context-sync/                      # Read-only context sources
├── confluence/                      # Confluence docs (ADRs, runbooks)
└── jira/                           # JIRA tickets (issues, epics)
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
./jib

# Rebuild container (if Docker config changes)
./jib --rebuild

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

- **[MIGRATION.md](MIGRATION.md)** - Update instructions for host machine changes
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
./jib --rebuild
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
