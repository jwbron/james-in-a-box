# Claude Agent Rules

This directory contains instructions for the AI agent (Claude Code) operating in this sandboxed environment.

## How These Files Are Used

Claude Code reads `CLAUDE.md` files automatically when starting. During container startup, all rule files are combined into a single `CLAUDE.md`:

**Installation:**
- `~/CLAUDE.md` → All rules combined

**Why one file?** Since `~/khan/` is mounted from the host (not copied), we can't reliably write to it during container startup. Combining all rules into `~/CLAUDE.md` ensures they're always available.

**Note**: `CLAUDE.md` is the [official Claude Code format](https://www.anthropic.com/engineering/claude-code-best-practices) for providing context and instructions to the agent.

## File Guide

### Core Agent Instructions

- **mission.md** - Start here
  - Your role as autonomous software engineering agent
  - Operating model (you do implementation, human does review/deploy)
  - Workflow: beads → gather context → plan → implement → test → PR
  - Decision-making framework (when to proceed vs ask)
  - Quality standards and communication style

- **environment.md** - Technical constraints
  - Sandbox security model
  - GitHub MCP server configuration
  - File system layout and access
  - Services and package installation
  - Error handling patterns

- **beads-usage.md** - Persistent task tracking (MANDATORY)
  - Automatic task management workflow
  - Commands and common patterns
  - Integration with Slack and GitHub

### Context Tracking

- **slack-thread-context.md** - Slack message memory
  - Using task IDs for persistent context
  - Thread continuity across containers

- **github-pr-context.md** - PR context tracking
  - PR lifecycle in Beads
  - Maintaining context across PR events

### Khan Academy Standards

- **khan-academy.md** - Tech stack and code standards
  - Technologies (Python, React, TypeScript)
  - Code style guidelines
  - Common commands
  - File organization

- **khan-academy-culture.md** - Engineering culture
  - Engineering principles (quality, nurturing, collaboration)
  - L3-L4 competency framework
  - Behavioral guidelines for the agent

### Quality & Communication

- **pr-descriptions.md** - PR writing guidelines
  - Khan Academy PR format
  - Content guidelines and examples

- **test-workflow.md** - Test discovery and execution
  - Dynamic test discovery
  - Testing workflow integration

- **notification-template.md** - Async notification formatting
  - Guidance requests
  - Automated reports with threading
  - Work completed notifications

- **conversation-analysis-criteria.md** - Performance assessment
  - Assessment dimensions
  - Scoring criteria

## Maintenance

When updating rules:
- Keep files focused on their specific domain
- Avoid redundancy across files
- Use markdown for consistency
- Rebuild container to apply changes: `./jib`

