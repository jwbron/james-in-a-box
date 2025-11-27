# Claude Code Commands

This directory contains slash command documentation for Claude Code CLI in the sandboxed environment.

## Available Commands

### /load-context <filename>
Load accumulated knowledge from a context-sharing document.

**Usage**: `/load-context terraform-migration`

**What it does**:
- Reads context document from `~/sharing/context/<filename>.md`
- Loads all sessions, playbooks, anti-patterns, and decision logs
- Applies accumulated wisdom to current work

**File**: `load-context.md`

### /save-context <filename>
Save current session knowledge to a context document using ACE methodology.

**Usage**: `/save-context tf-hackathon`

**What it does**:
- Analyzes current session work
- Generates structured content (Generation → Reflection → Curation)
- Appends to existing document or creates new one
- Preserves all historical content

**File**: `save-context.md`

### /create-pr [audit] [draft]
Automated pull request creation with smart description generation.

**Usage**:
- `/create-pr`
- `/create-pr audit`
- `/create-pr draft`

**What it does**:
- Analyzes git branch and commits
- Generates comprehensive PR description
- Extracts Jira issue from branch name
- Creates PR via GitHub MCP

**File**: `create-pr.md`

### /beads-status
Show current Beads task status.

**Usage**: `/beads-status`

**What it does**:
- Lists in-progress and pending tasks
- Shows task IDs for reference

**File**: `beads-status.md`

### /beads-sync
Sync Beads repository with git.

**Usage**: `/beads-sync`

**What it does**:
- Commits any uncommitted Beads changes
- Syncs with remote if configured

**File**: `beads-sync.md`

### /update-confluence-doc <path>
Prepare updates for a Confluence document based on inline comments.

**Usage**: `/update-confluence-doc ~/context-sync/confluence/ENG/ADRs/ADR-123.md`

**What it does**:
- Reads document and synced comments
- Generates "Changed Sections Only" document
- Formats output for copy-paste into Confluence

**File**: `update-confluence-doc.md`

### /show-metrics
Generate a monitoring report showing recent agent activity.

**Usage**: `/show-metrics`

**What it does**:
- Shows API usage metrics
- Task completion statistics
- Context source usage

**File**: `show-metrics.md`

## How Commands Work

These commands are **slash commands** for Claude Code. They are markdown files that provide instructions to Claude on how to respond when you use the command syntax.

When you say `/load-context myproject` in Claude Code:
1. Claude reads the instructions from `~/.claude/commands/load-context.md`
2. Executes the workflow described in the file
3. Uses available tools (Read, Write, Bash, etc.) to complete the task

**IMPORTANT**: Use `/` (slash) prefix, NOT `@` prefix for commands.

## Command Syntax

| Correct | Incorrect |
|---------|-----------|
| `/load-context myproject` | `@load-context myproject` |
| `/save-context feature-x` | `@save-context feature-x` |
| `/create-pr audit` | `@create-pr audit` |

## Viewing Command Details

Inside the container:
```bash
# List all commands
ls ~/.claude/commands/

# View a specific command
cat ~/.claude/commands/load-context.md

# Or use Read tool in Claude Code
# Read: ~/.claude/commands/create-pr.md
```

## Location in Container

These files are installed to `~/.claude/commands/` during Docker image build and are automatically available to Claude Code when running in the sandboxed environment.

## Adding New Commands

1. Create a new `.md` file in `jib-container/.claude/commands/`
2. Follow the format of existing commands
3. Rebuild the Docker image: `./jib --rebuild`
4. New command will be available at `~/.claude/commands/<command-name>.md`

## Command Format

Each command file should include:
- **Purpose**: What the command does
- **Usage**: Example syntax with `/` prefix
- **Workflow**: Step-by-step instructions for Claude
- **Critical Rules**: DO's and DON'Ts
- **Examples**: Sample interactions

Claude Code will follow these instructions when users invoke the slash command syntax.

---

**Last Updated**: 2025-11-26
