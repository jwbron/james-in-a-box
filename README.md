# james-in-a-box (jib)

**Autonomous codebase maintainer powered by Claude**

jib is an LLM-powered software engineering agent that acts as a tireless codebase maintainer. Running in a secure Docker sandbox, jib autonomously handles everything from feature development and refactoring to documentation generation, ADR maintenance, PR reviews, and codebase analysis—all controlled via Slack.

## What is jib?

jib is your **autonomous codebase maintainer** that:

- **Develops features**: Implements features end-to-end with tests and documentation
- **Reviews PRs**: Automatically reviews team PRs, suggests improvements, analyzes check failures
- **Maintains documentation**: Auto-generates docs, keeps ADRs current, updates runbooks
- **Analyzes codebases**: Weekly deep analysis for quality, security, and structural issues
- **Refactors autonomously**: Identifies and executes automated refactoring opportunities
- **Researches externally**: Fetches latest docs, best practices, framework updates from the web
- **Tracks work persistently**: Remembers context across sessions via git-backed task memory
- **Works asynchronously**: Fully productive workflow via Slack (notifications, reviews, approvals)

Think of jib as a **Senior Software Engineer (L3-L4)** that never sleeps, handles the routine maintenance work, and lets human engineers focus on strategic, creative problems.

## Why We Built This

**Problem**: Codebases need constant maintenance—documentation updates, refactoring, dependency updates, code reviews, ADR generation, bug fixes. Engineering time is scarce and better spent on strategic work.

**Solution**: An autonomous agent that handles routine codebase maintenance tasks:
- Works 24/7 in a secure sandbox
- Follows team standards and architectural decisions
- Generates production-quality code, tests, and documentation
- Learns and improves from every interaction
- Enables async workflow via Slack (control from anywhere)

**Key Principle**: The agent **prepares** artifacts (code, tests, docs, ADRs, analysis). Engineers **review and ship** (merge PRs, approve decisions). Clear separation of responsibilities ensures quality and safety.

## Core Capabilities

### 1. Feature Development

**Autonomous implementation of well-defined features:**
- End-to-end feature development with tests
- Follows architectural decisions and team patterns
- Generates comprehensive documentation
- Creates production-ready PRs with detailed descriptions
- Handles multi-step implementations with persistent task tracking

**Example**: "Implement OAuth2 authentication for JIRA-1234" → Designs schema per ADRs → Implements endpoints → Writes integration tests → Creates PR with migration guide

### 2. Pull Request Automation

**Comprehensive PR workflow automation:**

**Creating PRs (After Task Completion):**
- Auto-generates PR title and description from commits
- Includes test plan, migration steps, ADR references
- Requests review from configured reviewers
- Links to related JIRA tickets and design docs

**Reviewing PRs (Others' Work):**
- Automatically reviews new PRs from teammates every 15 minutes
- Analyzes code quality, security, performance, and adherence to standards
- Creates Slack notifications with findings and suggestions
- Skips self-authored PRs (no self-review)

**Responding to Comments:**
- Detects new comments on your PRs
- Classifies type (question, change request, concern)
- Generates contextual response suggestions
- Creates Beads tasks for tracking responses

**Check Failure Analysis:**
- Monitors CI/CD check failures
- Analyzes failure logs and identifies root causes
- Suggests or implements automated fixes (for auto-fixable issues like linting)
- Creates Slack notifications with analysis and recommendations

### 3. Documentation Generation & Maintenance

**Keeps documentation synchronized with code:**
- **Auto-generates documentation** from code, commits, and architectural decisions
- **ADR generation**: Drafts Architecture Decision Records from discussions and design docs
- **ADR updates**: Monitors code changes and updates ADRs when architecture evolves
- **API documentation**: Auto-generates and maintains API reference docs
- **LLM-optimized indexes**: Structures docs following [llms.txt](https://llmstxt.org/) standard for efficient navigation
- **Documentation drift detection**: Identifies when docs are out of sync with code
- **Multi-agent documentation pipeline**: Specialized agents for analysis, drafting, review, and validation

**Example**: After implementing a new authentication system, jib automatically updates the security ADR, generates API docs, and creates migration guides.

### 4. Codebase Analysis & Health Monitoring

**Weekly automated analysis for continuous improvement:**
- **Code quality scanning**: Identifies complexity, duplication, anti-patterns
- **Security vulnerability detection**: Scans for OWASP top 10, dependency vulnerabilities
- **Structural analysis**: Recommends architectural improvements
- **Performance profiling**: Identifies bottlenecks and optimization opportunities
- **Dependency health**: Tracks outdated packages, security advisories
- **Documentation gaps**: Finds undocumented functions, missing ADRs
- **Self-improvement tracking**: Agent behavior analyzed for alignment with team standards

**Output**: Prioritized recommendations (HIGH/MEDIUM/LOW) delivered via Slack

### 5. Automated Refactoring

**Safe, automated code improvements:**
- Identifies refactoring opportunities from codebase analysis
- Executes safe, automated refactorings (rename, extract method, etc.)
- Updates tests and documentation to match
- Creates PRs with before/after comparisons
- Provides rollback instructions

**Example**: "Found 15 instances of duplicated authentication logic → Extract to shared utility → Update all call sites → Create PR"

### 6. External Research & Context Integration

**Fetches latest information to inform decisions:**
- **Framework documentation**: Pulls latest docs for dependencies (React, Django, etc.)
- **Best practices**: Researches current industry standards for specific problems
- **Security advisories**: Checks for CVEs and security updates
- **Architecture patterns**: Finds examples and recommendations for design decisions
- **Migration guides**: Fetches official migration documentation for upgrades

**Context sources integrated:**
| Source | Sync Frequency | Purpose |
|--------|----------------|---------|
| **Confluence** | Hourly | ADRs, runbooks, engineering docs |
| **JIRA** | Hourly | Open tickets, epics, sprint data |
| **GitHub** | Every 15 min | PRs, checks, comments |
| **Web (on-demand)** | As needed | Latest docs, research, advisories |

**Post-Sync Intelligence:**
- **JIRA watcher**: Analyzes tickets, extracts action items, creates Beads tasks
- **Confluence watcher**: Identifies architectural decisions, detects impacts on current work
- **GitHub watcher**: Monitors check failures, auto-reviews PRs, suggests comment responses

### 7. Persistent Task Memory (Beads)

**Git-backed task tracking that survives container restarts:**
- **Automatic context preservation** across Slack threads and PR sessions
- **Dependency tracking** for complex multi-step tasks
- **Progress notes** capture decisions, blockers, and context
- **Multi-container coordination** via shared git repository
- **Automatic resumption** after crashes or container restarts

**Why it matters**: LLMs are stateless—Beads gives jib persistent memory, enabling true autonomous operation across sessions.

### 8. Conversation Analysis & Self-Improvement

**Daily automated analysis of agent behavior:**
- Evaluates agent interactions for quality and alignment with engineering standards
- Identifies patterns in errors and successful interactions
- Recommends prompt refinements and workflow optimizations
- Assesses cultural fit (communication style, problem-solving approach, collaboration quality)
- Generates actionable improvements to agent behavior

**Cultural Alignment**: Agent behavior continuously refined to match Khan Academy engineering values (clear communication, systematic problem-solving, thorough testing, user-focused decisions)

## How It Works

```
┌─────────────────────────────────────────────────────┐
│  You (Slack)                                        │
│  • Send tasks: "Refactor auth module per ADR-042"   │
│  • Receive notifications with summaries + threads   │
│  • Review and approve PRs                           │
└─────────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────────┐
│  Host Machine (Your Laptop)                         │
│  • Slack notifier/receiver (systemd services)       │
│  • Context sync (Confluence, JIRA, GitHub)          │
│  • Automated analyzers (codebase, conversations)    │
│  • Git worktree management and cleanup              │
└─────────────────────────────────────────────────────┘
                      ↕
┌─────────────────────────────────────────────────────┐
│  Docker Container (Sandbox)                         │
│  • Claude Code agent with custom rules              │
│  • No credentials (SSH keys, cloud tokens excluded) │
│  • Network isolation (outbound HTTP only)           │
│  • Ephemeral - spun up per task, auto-cleanup       │
└─────────────────────────────────────────────────────┘
```

**Workflow:**
1. Send task via Slack DM to bot
2. Container spawns with isolated git worktree
3. Agent implements changes, writes tests, generates docs, commits to branch
4. Agent creates PR with comprehensive description
5. Container shuts down and worktree is cleaned up (commits are preserved on branch)
6. You review PR and merge when satisfied

### Worktree Isolation

Each container gets its own ephemeral git worktree, keeping your host repositories clean:

- **Host protection**: Your local repos stay untouched while agent works
- **True parallelism**: Multiple containers can work on same repo simultaneously
- **Isolated branches**: Each container works on `jib-temp-{container-id}` branch
- **Git commands work**: Full git functionality inside container
- **Commits preserved**: All commits saved on branch even after container exits
- **Auto-cleanup**: Worktrees removed when container exits, commits remain accessible

## Quick Start

### Prerequisites

- Docker installed and running
- Python 3.8+
- Slack workspace with bot token

### Setup

1. **Clone repository**:
   ```bash
   git clone https://github.com/jwbron/james-in-a-box.git
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

3. **Configure Slack tokens**:
   ```bash
   nano ~/.config/jib-notifier/config.json
   # Add your bot token (xoxb-...) and app token (xapp-...)
   ```

4. **Start container**:
   ```bash
   bin/jib
   ```

5. **Send first task** (from Slack):
   ```
   DM the bot: "Analyze the authentication module and suggest improvements"
   ```

The agent will analyze your code and send you a detailed report with recommendations.

## Example Use Cases

### 1. Feature Development
```
You: "Implement rate limiting middleware for API endpoints (JIRA-1234)"
jib: → Reads relevant ADRs and existing middleware patterns
     → Implements rate limiting with Redis backend
     → Writes unit and integration tests
     → Generates API documentation
     → Creates PR with migration guide
     → Sends notification: "PR #123 ready for review"
```

### 2. Documentation Maintenance
```
You: "Generate ADR for our new caching strategy"
jib: → Analyzes recent commits and design discussions
     → Drafts ADR following template
     → Links to related decisions and code
     → Creates PR with ADR-045-Caching-Strategy.md
     → Updates documentation index
```

### 3. Codebase Analysis
```
Automated (weekly): jib runs codebase analyzer
jib: → Scans entire codebase for quality, security, structure
     → Identifies 12 issues (3 HIGH, 5 MEDIUM, 4 LOW)
     → Sends Slack notification with prioritized findings:
       - HIGH: SQL injection vulnerability in UserService
       - HIGH: Deprecated authentication method still in use
       - MEDIUM: Duplicate code in 8 components (refactor opportunity)
     → Creates Beads tasks for HIGH priority issues
```

### 4. PR Review & Feedback
```
Teammate opens PR #456
jib (automated): → Reviews code quality, tests, security
                 → Analyzes performance implications
                 → Checks ADR compliance
                 → Sends notification:
                   "PR #456 looks good overall. Suggestions:
                   - Consider adding integration test for edge case
                   - Performance: query could benefit from index
                   - Security: validate user input in line 42"
```

### 5. Automated Refactoring
```
You: "Refactor authentication logic to use new auth library"
jib: → Analyzes all auth-related code (15 files)
     → Creates migration plan with dependency graph
     → Updates each file systematically
     → Migrates tests to new patterns
     → Updates documentation and ADRs
     → Creates PR with comprehensive before/after comparison
     → Includes rollback instructions
```

### 6. External Research
```
You: "What's the recommended approach for implementing feature flags in Django?"
jib: → Researches Django feature flag libraries
     → Reads latest documentation for top options
     → Compares LaunchDarkly, django-flags, django-waffle
     → Analyzes Khan Academy's existing infrastructure
     → Recommends django-waffle with reasoning
     → Provides implementation example and migration guide
```

## Documentation

jib follows the [llms.txt](https://llmstxt.org/) standard for LLM-friendly documentation. Start with the navigation index:

**[Documentation Index](docs/index.md)** - Central hub linking all documentation

### Architecture Decision Records (ADRs)

| ADR | Description |
|-----|-------------|
| [Autonomous Software Engineer](docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md) | Core system architecture, security model, self-improvement |
| [LLM Documentation Index Strategy](docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) | How documentation is structured for efficient LLM navigation |
| [Context Sync Strategy](docs/adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | Current connectors and MCP migration plan |
| [ADR Index](docs/adr/README.md) | Full list of all ADRs by status |

### Quick References

- [Beads Task Tracking](docs/reference/beads.md) - Persistent memory: Slack thread context, PR state, multi-session work

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

## Security Model

**5-Layer Defense Against Data Exfiltration:**

1. **Human Review** (✅ Implemented - Phase 1)
   - All PRs require human approval before merge
   - MEDIUM risk, acceptable for pilot

2. **Context Source Filtering** (Planned - Phase 2)
   - Confluence/JIRA allowlists
   - Exclude customer data (SUPPORT, SALES, etc.)

3. **Content Classification** (Planned - Phase 2)
   - Tag docs: Public/Internal/Confidential
   - Agent skips Confidential content

4. **DLP Scanning** (Planned - Phase 3)
   - Cloud DLP before Claude API calls
   - Automated redaction of PII, secrets

5. **Output Monitoring** (Planned - Phase 3)
   - Scan PRs, commits, Slack for leaks
   - Alert on sensitive data exposure

**Current State**: Layer 1 (Human Review) + Sandbox Isolation
**Current Risk**: MEDIUM (acceptable for pilot phase)
**Target State**: All 5 layers operational
**Target Risk**: LOW (full DLP + monitoring operational)

**Sandbox Isolation:**
- No SSH keys (can't push to GitHub directly)
- No cloud credentials (can't deploy)
- Network: Outbound HTTP only (Claude API, packages)
- Container: No inbound ports, bridge networking

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
make install-linters   # Install linting tools
make check-linters     # Verify installation
```

## Troubleshooting

### Services Not Starting

**Check dependencies**:
```bash
systemctl --user status slack-notifier.service
journalctl --user -u slack-notifier.service --no-pager
```

**Common issues**:
- Missing Slack tokens in `~/.config/jib-notifier/config.json`
- Python dependencies not installed (run `uv sync` or re-run `setup.sh`)
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

For questions or issues:

1. Check component READMEs for specific guidance
2. Review architecture docs in `docs/`
3. Check service logs for error details

## License

MIT License
