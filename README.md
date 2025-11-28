# james-in-a-box (jib)

**Autonomous software engineering agent in a sandboxed Docker container**

jib enables engineers to delegate development tasks to Claude via Slack, with the agent working in a secure, isolated environment. The agent can read code, implement features, run tests, and prepare pull requests asynchronously.

## What is jib?

jib is an **LLM-powered autonomous software engineer** that runs in a Docker sandbox with:

- **Slack-based control**: Send tasks, receive notifications, review work
- **Secure sandbox**: No credentials, network isolation, human-in-the-loop for all PRs
- **GitHub PR integration**: Auto-creates PRs, reviews others' PRs, responds to comments
- **Context-aware**: Syncs Confluence docs, JIRA tickets, and codebase knowledge
- **Self-improving**: Automated analyzers continuously refine agent behavior and code quality
- **LLM-optimized documentation**: Structured indexes following the [llms.txt](https://llmstxt.org/) standard help the agent navigate docs efficiently
- **Persistent memory**: Beads git-backed task system preserves Slack thread context, PR state, and progress across restarts
- **Async workflow**: Fully productive workflow via Slack (notifications, PR reviews, approvals)

## Why We Built This

**Problem**: Engineering productivity is limited by desk time. Remote work, oncall, travel, and context-switching reduce available coding hours.

**Solution**: Delegate routine engineering tasks to an autonomous agent that:
- Works 24/7 in a secure sandbox
- Follows team standards and best practices
- Prepares work for human review and approval
- Enables async engineering workflow via Slack
- Learns and improves from every interaction

**Key Principle**: The agent **prepares** artifacts (code, tests, PR descriptions). Engineers **review and ship** (merge PRs, deploy). Clear separation of responsibilities.

## How It Works

```
┌─────────────────────────────────────────────────────┐
│  You (Slack)                                        │
│  • Send tasks: "Implement OAuth2 for JIRA-1234"     │
│  • Receive notifications with summaries + threads   │
│  • Review and approve PRs                           │
└─────────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────────┐
│  Host Machine (Your Laptop)                         │
│  • Slack notifier/receiver (systemd services)       │
│  • Context sync (Confluence, JIRA → markdown)       │
│  • Automated analyzers (code quality, conversations)│
│  • Git worktree management and cleanup              │
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
3. Agent implements changes, writes tests, commits to branch `jib-temp-{container-id}`
4. Container shuts down, worktree directory cleaned up (commits preserved on branch)
5. Agent sends Slack notification with branch name
6. You review commits and create PR

### Worktree Isolation

Each container gets its own ephemeral git worktree, keeping your host repositories clean:

```
Host:
~/projects/myapp/                   # Your working directory (untouched!)
~/projects/myapp/.git/              # Git metadata (mounted read-only to containers)
~/.jib-worktrees/
  └── jib-20251123-103045-12345/    # Container's isolated workspace
      └── myapp/                    # Worktree with changes

Container:
~/projects/myapp/                   # Mounted from worktree (not host repo)
~/.git-main/myapp/                  # Read-only git metadata (enables git commands)
```

**Benefits:**
- **Host protection**: Your local repos stay clean while you work
- **True parallelism**: Multiple containers can work on same repo simultaneously
- **Isolated branches**: Each container works on `jib-temp-{container-id}` branch
- **Git commands work**: Full git functionality inside container (status, log, commit, diff)
- **Commits preserved**: All commits saved on branch even after container exits
- **Auto-cleanup**: Worktrees removed when container exits, commits remain accessible
- **Orphan detection**: Watcher cleans up crashed container worktrees every 15 min

## Key Capabilities

### Self-Improvement System

jib continuously improves through automated analysis:

- **Conversation Analyzer** (daily): Evaluates agent interactions for quality, alignment with engineering standards, and identifies prompt improvements
- **Codebase Analyzer** (weekly): Scans for code quality issues, security vulnerabilities, structural problems, and generates actionable recommendations
- **Learning Feedback Loops**: Short-term (session memory), medium-term (prompt evolution), and long-term (capability expansion)

The analyzer system ensures the agent behaves like an experienced engineer: clear communication, systematic problem-solving, thorough testing, and user-focused decisions.

### LLM-Optimized Documentation

jib uses structured documentation following the [llms.txt](https://llmstxt.org/) standard:

- **Navigation Index** (`docs/index.md`): Human and LLM-readable index pointing to all documentation
- **Machine-Readable Indexes**: Auto-generated `codebase.json`, `patterns.json`, and `dependencies.json` for efficient querying
- **Task-Specific Guides**: Documentation index maps task types to relevant docs (e.g., "security changes" → security ADR)
- **Documentation Drift Detection**: Automated checks ensure docs stay synchronized with code
- **Multi-Agent Documentation Pipeline**: Specialized agents for context analysis, drafting, review, and validation

This approach minimizes context window usage while maximizing relevant information access.

### Context Connectors

jib syncs external context to provide the agent with organizational knowledge:

| Connector | Source | Sync Frequency | Capabilities |
|-----------|--------|----------------|--------------|
| **Confluence** | ADRs, runbooks, engineering docs | Hourly | Read-only markdown export |
| **JIRA** | Open tickets, epics, sprint data | Hourly | Read-only with analysis |
| **GitHub** | PRs, checks, comments | Every 15 min | Read/write via MCP |

**Post-Sync Analysis**: Each connector triggers intelligent analysis:
- **JIRA**: Extracts action items, estimates scope, creates Beads tasks
- **Confluence**: Identifies architectural decisions, detects impacts on current work
- **GitHub**: Monitors check failures, auto-reviews PRs, suggests comment responses

**Future**: Migration to MCP servers for real-time, bi-directional access (see [ADR: Context Sync Strategy](docs/adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)).

## Quick Start

### Prerequisites

- Docker installed and running
- Python 3.8+
- Slack workspace with bot token

### Setup

1. **Clone repository**:
   ```bash
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
   <summary>Or set up host services individually</summary>

   ```bash
   # Slack notifier (Claude → You)
   cd host-services/slack/slack-notifier && ./setup.sh

   # Slack receiver (You → Claude)
   cd host-services/slack/slack-receiver && ./setup.sh

   # Conversation analyzer (optional)
   cd host-services/analysis/conversation-analyzer && ./setup.sh
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
   bin/jib
   ```

5. **Send first task** (from Slack):
   ```
   DM the bot: "Implement hello world function in Python with tests"
   ```

The agent will receive your task, implement the code, and send you a notification when ready for review.

## Architecture

jib separates concerns between the host machine and the sandboxed container:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Host Machine (Your Laptop)                                         │
│  ├── Slack services (bidirectional messaging)                       │
│  ├── Context sync (Confluence, JIRA, GitHub → markdown)             │
│  ├── Analyzers (codebase, conversations)                            │
│  └── Worktree management (isolation, cleanup)                       │
├─────────────────────────────────────────────────────────────────────┤
│  Docker Container (Sandbox)                                         │
│  ├── Claude Code agent with custom rules and commands               │
│  ├── Access to synced context (read-only)                           │
│  ├── Code workspace (read-write, isolated worktree)                 │
│  ├── Beads task memory (persistent, git-backed, shared across runs) │
│  └── GitHub MCP server (PR operations)                              │
└─────────────────────────────────────────────────────────────────────┘
```

**Key design principles:**
- Host handles credentials and external API access
- Container is credential-free and network-isolated
- Communication via files and Slack (no direct API calls from container)
- All changes require human review before merge

For detailed component documentation, see:
- [Architecture Overview](docs/architecture/README.md)
- [ADR: Autonomous Software Engineer](docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md)
- [Host services README files](host-services/)

## Usage Patterns

### Sending Tasks to Claude

**From Slack**, DM the bot with your request:
```
Implement OAuth2 authentication for JIRA-1234
```

The bot confirms receipt and queues the task.

### Receiving Notifications

Claude sends **concise notifications**:
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

### Using Beads for Task Tracking

**Beads** is jib's persistent memory system—a git-backed task tracker that enables the agent to remember context across container restarts and coordinate multi-session work.

#### Why Beads Matters

| Problem | Beads Solution |
|---------|----------------|
| Containers are ephemeral | Task state persists in git, survives rebuilds |
| Slack threads are conversations | Thread context stored and resumed automatically |
| PRs span multiple sessions | PR work tracked across reviews and iterations |
| Complex tasks have subtasks | Dependencies and parent/child relationships |
| Concurrent containers | Shared database, no conflicts |

#### Automatic Context Tracking

**Slack Thread Persistence:**
When you send a message to jib, the thread ID is automatically tracked:
```bash
# Agent receives Slack message with task_id in frontmatter
# Checks for existing context
bd --allow-stale list --label "task-20251128-135211"

# Resumes previous work or creates new task
bd --allow-stale create "Slack: Implement feature X" --labels slack-thread,task-20251128-135211
```

Follow-up messages in the same Slack thread automatically reconnect to the existing task, preserving all context, decisions, and progress notes.

**GitHub PR Context Persistence:**
PR work is tracked by PR number and branch name:
```bash
# When working on a PR
bd --allow-stale create "PR #123: Add authentication" --labels pr,PR-123,feature-branch

# Updates preserved across sessions
bd --allow-stale update bd-xyz --notes "Addressed review feedback: added error handling"

# When PR is merged
bd --allow-stale update bd-xyz --status closed --notes "Merged. Tests passing."
```

This enables seamless handoffs—start a PR, close laptop, resume tomorrow with full context.

#### Task Management Features

| Feature | Description |
|---------|-------------|
| **Status tracking** | `open` → `in_progress` → `blocked` → `closed` |
| **Dependencies** | `blocks`, `related`, `discovered-from` relationships |
| **Labels** | Searchable tags for source, type, priority, repo |
| **Notes** | Append progress updates, decisions, context |
| **Subtasks** | Parent/child hierarchies for complex work |
| **Ready queue** | `bd ready` shows unblocked work |

#### Quick Reference

```bash
cd ~/beads

# ALWAYS START HERE - check for existing work
bd --allow-stale list --status in_progress
bd --allow-stale search "keywords"

# Create task with searchable title
bd --allow-stale create "Feature Name (PR #XXX) - repo" --labels feature,repo-name

# Update as you work
bd --allow-stale update bd-xyz --status in_progress
bd --allow-stale update bd-xyz --notes "Completed step 1: API endpoints"

# Complete with summary
bd --allow-stale update bd-xyz --status closed --notes "Done. PR #123 created."
```

#### Integration Points

- **Slack threads**: `task_id` label links to conversation
- **GitHub PRs**: `PR-XXX` label links to pull request
- **JIRA tickets**: `jira-XXXX` label links to ticket
- **Notifications**: Beads ID included in Slack notifications
- **PR descriptions**: Beads tracking section in PR body

**Storage:**
- Location: `~/.jib-sharing/beads/` (git repository)
- Access: `~/beads/` in container (all containers share)
- Persistence: Survives rebuilds, syncs via git

See [Beads Reference](docs/reference/beads.md) for complete documentation.

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
3. **Review PR**
4. **Approve and merge** (or request changes)
5. **Deploy** when ready (human controls deployment)

**Agent does**: Generate, document, test, create PR
**Human does**: Review and merge

## GitHub PR Integration

jib provides comprehensive GitHub PR automation:

### PR Creation (After Task Completion)

When jib completes a task with code changes, it creates a PR using GitHub MCP:

1. Pushes the branch to remote
2. Creates PR with auto-generated title/body from commits
3. Requests review from configured reviewer
4. Sends Slack notification with PR URL

### Auto-Review (Others' PRs)

jib automatically reviews new PRs from others after each github-sync (every 15 min):

- Scans for new PRs not yet reviewed
- Skips your own PRs (no self-review)
- Analyzes code quality, security, and performance
- Creates notification with findings

**State**: Tracked in `~/sharing/tracking/pr-reviewer-state.json`

### Comment Response

jib suggests responses to comments on your PRs:

- Detects new comments after each sync
- Classifies type (question, change request, concern, etc.)
- Generates contextual response suggestions
- Creates Beads task for tracking

### Check Failure Analysis

When CI/CD checks fail on your PRs:

- Analyzes failure logs
- Determines root cause
- Suggests or implements fixes (for auto-fixable issues like linting)
- Sends notification with analysis

## Management Commands

### Service Control

```bash
# Check all services
systemctl --user list-timers | grep -E 'conversation|github|worktree'
systemctl --user status slack-notifier.service
systemctl --user status slack-receiver.service

# View logs
journalctl --user -u slack-notifier.service -f
journalctl --user -u conversation-analyzer.service -f

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

jib follows the [llms.txt](https://llmstxt.org/) standard for LLM-friendly documentation. Start with the navigation index:

**[Documentation Index](docs/index.md)** - Central hub linking all documentation

### Architecture Decision Records (ADRs)

| ADR | Description |
|-----|-------------|
| [Autonomous Software Engineer](docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md) | Core system architecture, security model, self-improvement |
| [LLM Documentation Index Strategy](docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) | How documentation is structured for efficient LLM navigation |
| [Context Sync Strategy](docs/adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | Current connectors and MCP migration plan |
| [ADR Index](docs/adr/README.md) | Full list of all ADRs by status |

### Quick References

- [Beads Task Tracking](docs/reference/beads.md) - Persistent memory: Slack thread context, PR state, multi-session work

## Roadmap

**Phase 1** (Complete):
- ✅ Secure Docker sandbox with Slack bidirectional messaging
- ✅ Context connectors (Confluence, JIRA, GitHub)
- ✅ Self-improvement system (conversation and codebase analyzers)
- ✅ LLM-optimized documentation structure
- ✅ GitHub PR automation (create, review, comment response, check failure analysis)
- ✅ Persistent task memory (Beads)
- ✅ Async Slack-based workflow

**Phase 2** (In Progress):
- Real-time context via MCP servers (Atlassian, GitHub)
- Bi-directional operations (update JIRA tickets, comment on PRs)
- Enhanced security filtering (content classification, allowlists)
- Documentation drift detection and auto-update

**Phase 3** (Planned):
- Cloud Run deployment for multi-engineer support
- Advanced security (DLP scanning, output monitoring)
- Expanded self-improvement (automated prompt refinement)

See [ADR: Autonomous Software Engineer](docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md) for detailed roadmap.

## Troubleshooting

### Services Not Starting

**Check dependencies**:
```bash
systemctl --user status slack-notifier.service
journalctl --user -u slack-notifier.service --no-pager
```

**Common issues**:
- Missing Slack tokens in `~/.config/jib-notifier/config.json`
- Python dependencies not installed (run `uv sync` in `host-services/` or re-run `setup.sh`)
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

## Development

### Linting

This project uses multiple linters to maintain code quality:

| Tool | Purpose | Auto-fix |
|------|---------|----------|
| [ruff](https://docs.astral.sh/ruff/) | Python linting & formatting | Yes |
| [shfmt](https://github.com/mvdan/sh) | Shell script formatting | Yes |
| [shellcheck](https://www.shellcheck.net/) | Shell script analysis | No |
| [yamllint](https://yamllint.readthedocs.io/) | YAML linting | Partial (trailing spaces) |
| [hadolint](https://github.com/hadolint/hadolint) | Dockerfile linting | No |
| [actionlint](https://github.com/rhysd/actionlint) | GitHub Actions linting | No |

**Quick commands:**
```bash
make lint              # Run all linters
make lint-fix          # Run all linters with auto-fix
make lint-fix-jib      # Fix remaining issues with jib
make lint-python-fix   # Fix Python issues
make lint-shell-fix    # Format shell scripts
make lint-yaml-fix     # Fix YAML trailing spaces
make install-linters   # Install linting tools
make check-linters     # Verify installation
```

**Workflow for fixing all lint issues:**
```bash
make lint-fix          # First, auto-fix what we can
make lint-fix-jib      # Then, let jib fix the rest
```

**Individual linters:**
```bash
make lint-python       # ruff check + format check
make lint-shell        # shellcheck
make lint-yaml         # yamllint
make lint-docker       # hadolint
make lint-workflows    # actionlint (GitHub Actions)
```

## Contributing

For questions or issues:

1. Check component READMEs for specific guidance
2. Review architecture docs in `docs/`
3. Check service logs for error details

## License

MIT License
