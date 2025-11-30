# jib Feature List

> **Purpose:** This list enables automated codebase and document analyzers to systematically assess each feature for quality, security, and improvement opportunities.
>
> **Automation Strategy:** See [Maintaining This List](#maintaining-this-list) below.

## Core Architecture

### 1. Docker Sandbox Environment
**Category:** Infrastructure
**Location:** `jib-container/Dockerfile`, `jib-container/docker-setup.py`
**Description:** Isolated containerized environment for running the Claude agent with network restrictions, no credentials, and ephemeral execution.
**Key Components:**
- Network isolation (outbound HTTP only)
- Credential exclusion (no SSH keys, cloud tokens)
- Ephemeral containers (per-task spawning)

### 2. Git Worktree Isolation
**Category:** Infrastructure
**Location:** `jib-container/jib` (worktree management), `host-services/utilities/worktree-watcher/`
**Description:** Each container gets isolated git worktree to prevent cross-contamination of host repositories while enabling parallel work.
**Key Components:**
- Isolated workspace per container
- Temporary branch per task (`jib-temp-{container-id}`)
- Auto-cleanup with orphan detection
- Host repository protection

### 3. Claude Agent Integration
**Category:** Core Agent
**Location:** `jib-container/jib`, `jib-container/.claude/`
**Description:** LLM-powered autonomous software engineer using Claude API with custom rules, commands, and behavior configuration.
**Key Components:**
- Custom slash commands
- Agent behavior rules
- Status bar integration
- MCP (Model Context Protocol) server support

## Slack Integration

### 4. Slack Notifier (Claude → Human)
**Category:** Communication
**Location:** `host-services/slack/slack-notifier/`
**Description:** Watches notification directory and sends formatted messages to Slack with thread support.
**Key Components:**
- File-based notification watching
- Thread context preservation
- Python library interface
- Summary/detail splitting

### 5. Slack Receiver (Human → Claude)
**Category:** Communication
**Location:** `host-services/slack/slack-receiver/`
**Description:** Listens for Slack DMs and thread replies, converts to tasks for agent processing.
**Key Components:**
- Socket mode connection
- Thread tracking with `task_id`
- YAML frontmatter metadata
- Task queuing

### 6. Bidirectional Slack Workflow
**Category:** Communication
**Location:** `host-services/slack/`, `docs/architecture/slack-integration.md`
**Description:** Fully async workflow enabling task delegation and review via Slack.
**Key Components:**
- Task submission via DM
- Threaded notifications
- Progress updates
- Question/answer flow

## Context Management

### 7. Beads Task Tracking
**Category:** Persistence
**Location:** `~/.jib-sharing/beads/`, `docs/reference/beads.md`
**Description:** Git-backed persistent task memory preserving Slack thread context, PR state, and multi-session work across container restarts.
**Key Components:**
- SQLite database with git persistence
- Task status tracking (open, in_progress, blocked, closed)
- Dependency relationships
- Label-based searching
- Notes and progress tracking

### 8. Context Sync System
**Category:** Knowledge Integration
**Location:** `host-services/sync/context-sync/`
**Description:** Syncs external data sources (Confluence, JIRA, GitHub) to local markdown for agent access.
**Key Components:**
- Confluence connector (ADRs, runbooks)
- JIRA connector (tickets, sprints)
- GitHub connector (PRs, issues)
- Scheduled syncing

### 9. Context Load/Save Commands
**Category:** Knowledge Integration
**Location:** `jib-container/.claude/commands/load-context.md`, `jib-container/.claude/commands/save-context.md`
**Description:** Custom commands to persist and restore learned context across sessions.
**Key Components:**
- Project-specific context storage
- Accumulated knowledge preservation
- Session continuity

## GitHub Integration

### 10. GitHub MCP Server
**Category:** Version Control
**Location:** Container runtime, configured via `docker-setup.py`
**Description:** Model Context Protocol server enabling GitHub API operations (PRs, issues, comments) from within container.
**Key Components:**
- PR creation and management
- Issue tracking
- Comment operations
- Branch management

### 11. GitHub Token Management
**Category:** Authentication
**Location:** `host-services/utilities/github-token-refresher/`
**Description:** Refreshes GitHub App installation tokens and maintains git credential helper for HTTPS push.
**Key Components:**
- Token refresh automation
- Credential helper integration
- Secure token storage

### 12. GitHub Watcher
**Category:** Automation
**Location:** `host-services/analysis/github-watcher/`
**Description:** Monitors GitHub for events requiring agent attention (new PRs, check failures, comments).
**Key Components:**
- PR auto-review triggering
- Check failure detection
- Comment response suggestions

### 13. PR Auto-Review
**Category:** Automation
**Location:** `host-services/analysis/analyze-pr/`
**Description:** Automatically reviews PRs from other developers, analyzing code quality, security, and performance.
**Key Components:**
- Automated PR scanning
- Code quality analysis
- Security vulnerability detection
- Notification generation

## Self-Improvement System

### 14. Conversation Analyzer
**Category:** Analysis
**Location:** `host-services/analysis/conversation-analyzer/`
**Description:** Daily analysis of agent-human interactions to assess quality, alignment with standards, and identify improvement areas.
**Key Components:**
- Behavioral analysis
- Engineering standard compliance
- Communication quality assessment
- Prompt improvement suggestions

### 15. Trace Collection System
**Category:** Analysis
**Location:** `host-services/analysis/trace-collector/`
**Description:** Captures structured traces of LLM interactions for inefficiency analysis.
**Key Components:**
- Tool call tracking
- Token usage monitoring
- Decision pattern detection
- Inefficiency categorization

### 16. Codebase Analyzer
**Category:** Analysis
**Location:** Planned (referenced in ADR-Autonomous-Software-Engineer.md)
**Description:** Weekly automated codebase scanning for quality issues, security vulnerabilities, and structural problems.
**Key Components:**
- Code quality assessment
- Security scanning
- Structural analysis
- Actionable recommendations

## Documentation System

### 17. LLM-Optimized Documentation
**Category:** Documentation
**Location:** `docs/index.md`, `docs/generated/`
**Description:** Structured documentation following llms.txt standard with navigation indexes and machine-readable metadata.
**Key Components:**
- Documentation index (docs/index.md)
- Task-specific guides
- Machine-readable indexes (JSON)
- Multi-level hierarchy

### 18. Documentation Index Generator
**Category:** Documentation
**Location:** `host-services/analysis/index-generator/`
**Description:** Auto-generates machine-readable indexes (codebase.json, patterns.json, dependencies.json) for efficient querying.
**Key Components:**
- Codebase structure analysis
- Pattern extraction
- Dependency mapping
- JSON index generation

### 19. ADR Researcher
**Category:** Documentation
**Location:** `host-services/analysis/adr-researcher/`
**Description:** Helps generate Architecture Decision Records by researching best practices and alternatives.
**Key Components:**
- Research automation
- ADR template generation
- Best practice identification
- Alternative analysis

### 20. Document Generator
**Category:** Documentation
**Location:** `host-services/analysis/doc-generator/`
**Description:** Multi-agent pipeline for drafting, reviewing, and validating documentation.
**Key Components:**
- Context analysis
- Draft generation
- Review process
- Validation

### 21. Spec Enricher
**Category:** Documentation
**Location:** `host-services/analysis/spec-enricher/`
**Description:** Enhances technical specifications with implementation details and edge cases.
**Key Components:**
- Specification analysis
- Detail enrichment
- Edge case identification

## Custom Commands

### 22. PR Creation Command
**Category:** Development Workflow
**Location:** `jib-container/.claude/commands/create-pr.md`
**Description:** Auto-generates PR descriptions from commits with audit trails.
**Key Components:**
- Commit analysis
- PR body generation
- Audit mode support
- Draft PR creation

### 23. Beads Status/Sync Commands
**Category:** Task Management
**Location:** `jib-container/.claude/commands/beads-status.md`, `beads-sync.md`
**Description:** Quick access to Beads task status and synchronization.
**Key Components:**
- Status overview
- Task synchronization
- Quick updates

### 24. Confluence Update Command
**Category:** Documentation
**Location:** `jib-container/.claude/commands/update-confluence-doc.md`
**Description:** Prepares Confluence documentation updates for human review.
**Key Components:**
- Document preparation
- Change tracking
- Update staging

### 25. Metrics Display Command
**Category:** Monitoring
**Location:** `jib-container/.claude/commands/show-metrics.md`
**Description:** Displays system metrics and performance data.
**Key Components:**
- Metric collection
- Display formatting
- Performance tracking

## Container Customization

### 26. Custom Claude Rules
**Category:** Agent Behavior
**Location:** `jib-container/.claude/rules/`
**Description:** Behavior rules defining agent personality, communication style, and decision-making.
**Key Components:**
- Engineering standards
- Communication guidelines
- Decision frameworks
- Quality standards

### 27. Test Discovery System
**Category:** Development Workflow
**Location:** `jib-container/scripts/discover-tests.py`
**Description:** Auto-discovers test frameworks and commands across different codebases.
**Key Components:**
- Multi-language support (Python, JS, Go, Java)
- Test command detection
- Configuration parsing
- JSON output

### 28. Container Setup Script
**Category:** Infrastructure
**Location:** `jib-container/docker-setup.py`
**Description:** Configures container environment, installs dependencies, sets up services.
**Key Components:**
- Service initialization
- Dependency installation
- MCP server configuration
- Environment setup

## Utilities

### 29. Worktree Watcher
**Category:** Infrastructure
**Location:** `host-services/utilities/worktree-watcher/`
**Description:** Monitors and cleans up orphaned git worktrees from crashed containers.
**Key Components:**
- Orphan detection (15-minute intervals)
- Cleanup automation
- State tracking

### 30. Notifications Library
**Category:** Communication
**Location:** `jib-container/shared/notifications.py`
**Description:** Python library for sending structured notifications from container to Slack.
**Key Components:**
- Simple notification API
- Thread context support
- Priority levels
- Action-required notifications

### 31. Status Bar
**Category:** User Interface
**Location:** `jib-container/statusbar.py`
**Description:** Displays real-time status information in Claude interface.
**Key Components:**
- Status tracking
- Visual indicators
- Progress display

## Security Features

### 32. Network Isolation
**Category:** Security
**Location:** Container configuration
**Description:** Restricts container network access to outbound HTTP/HTTPS only.
**Key Components:**
- Bridge networking
- Outbound-only rules
- API access control

### 33. Credential Exclusion
**Category:** Security
**Location:** Container configuration, `jib-container/jib`
**Description:** Ensures no sensitive credentials are mounted in container.
**Key Components:**
- SSH key exclusion
- Cloud token exclusion
- Credential validation

### 34. Human-in-the-Loop Review
**Category:** Security
**Location:** Workflow design
**Description:** All code changes require human review before merge.
**Key Components:**
- PR approval requirement
- Manual merge enforcement
- Review tracking

## Configuration

### 35. Master Setup Script
**Category:** Installation
**Location:** `setup.sh`
**Description:** One-command setup for all host services and dependencies.
**Key Components:**
- Service installation
- Systemd integration
- Dependency verification
- Update mode

### 36. Git Credential Helper
**Category:** Authentication
**Location:** `jib-container/scripts/git-credential-github-token`
**Description:** Custom git credential helper using GitHub App token for HTTPS operations.
**Key Components:**
- Token-based authentication
- HTTPS git support
- Secure credential handling

---

## Maintaining This List

### Automated Maintenance Strategy

**Problem:** Feature lists become stale as code evolves. Manual maintenance is error-prone and time-consuming.

**Solution:** Multi-layered automation with human oversight.

#### Tier 1: Automated Detection (Weekly)

A dedicated analyzer service scans the codebase to detect:

1. **New Features**
   - New directories in `host-services/`
   - New Claude commands in `.claude/commands/`
   - New systemd service files
   - New Python packages with standalone functionality

2. **Removed Features**
   - Features in this list with missing source locations
   - Deleted directories or moved code

3. **Changed Features**
   - Modified README files for host services
   - Updated ADR references
   - New configuration options

**Detection Signals:**
```python
# Pseudocode for detection logic
features_detected = {
    "new": scan_for_new_services() + scan_for_new_commands() + scan_for_new_systemd(),
    "removed": validate_feature_locations(current_list),
    "changed": detect_readme_changes() + detect_adr_updates()
}
```

#### Tier 2: LLM Analysis (On Detection)

When changes are detected, an LLM analyzes:

1. **For New Features:**
   - Read README, source code, and related docs
   - Generate feature description
   - Identify category and key components
   - Suggest insertion point in list

2. **For Removed Features:**
   - Verify feature is truly removed (not relocated)
   - Check for replacement features
   - Suggest removal or update

3. **For Changed Features:**
   - Compare old vs. new descriptions
   - Update key components if significant changes
   - Flag major changes for human review

#### Tier 3: Human Review (On Proposal)

Automated system creates PR with:
- Proposed additions/removals/updates
- Justification for each change
- Links to source code evidence
- Diff showing before/after

Human reviews and merges (or requests revisions).

#### Tier 4: Validation (Post-Merge)

After merge, validation runs:
- All listed features have valid source locations
- No duplicate entries
- Categories are consistent
- Links are not broken

### Implementation Plan

**Phase 1: Static Validation (Immediate)**
```bash
# Script: scripts/validate-features.py
# - Verify all source locations exist
# - Check for broken links
# - Ensure consistent formatting
# Run: Weekly via cron
```

**Phase 2: Detection Service (Next)**
```bash
# Service: host-services/analysis/feature-detector/
# - Scan for new/removed/changed features
# - Generate change report
# - Run: Weekly via systemd timer
```

**Phase 3: LLM Analysis (Follow-up)**
```bash
# Service: host-services/analysis/feature-analyzer/
# - Analyze detected changes with LLM
# - Generate PR with proposed updates
# - Run: Triggered by feature-detector
```

**Phase 4: Continuous Integration (Future)**
```yaml
# GitHub Actions: .github/workflows/feature-list-check.yml
# - Run on every PR
# - Flag if new services added without feature list update
# - Auto-suggest feature description
```

### Maintenance Checklist

When adding a new feature manually:

- [ ] Add entry to appropriate category
- [ ] Include Location (file paths)
- [ ] Write Description (1-2 sentences)
- [ ] List Key Components (3-5 items)
- [ ] Verify source locations exist
- [ ] Update table of contents if adding category
- [ ] Run validation: `make validate-features`

### Feature Discovery Heuristics

The automated system uses these patterns to detect features:

| Pattern | Indicates | Confidence |
|---------|-----------|------------|
| New directory in `host-services/*/` | New host service | High |
| New `.md` file in `.claude/commands/` | New slash command | High |
| New `.service` file in `host-services/*/systemd/` | New systemd service | High |
| New Python package with `__main__.py` | Standalone tool | Medium |
| New directory in `jib-container/scripts/` | Container utility | Medium |
| ADR in `implemented/` status | Completed feature | Medium |
| Significant README changes | Feature update | Low |

### Stakeholders

- **Primary Maintainer:** Automated feature analyzer service
- **Review Approver:** Human (you)
- **Validation:** CI/CD pipeline (future)

---

**Last Updated:** 2025-11-30 (Initial creation)
**Next Review:** Weekly automated scan + human review of proposals
