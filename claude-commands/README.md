# Claude Code Commands

This directory contains command documentation for Claude Code CLI in the sandboxed environment.

## Available Commands

### @load-context <filename>
Load accumulated knowledge from a context-sharing document.

**Usage**: `@load-context terraform-migration`

**What it does**:
- Reads context document from `~/.claude/context-sharing/<filename>.md`
- Loads all sessions, playbooks, anti-patterns, and decision logs
- Applies accumulated wisdom to current work

**File**: `load-context.md`

### @save-context <filename>
Save current session knowledge to a context document using ACE methodology.

**Usage**: `@save-context tf-hackathon`

**What it does**:
- Analyzes current session work
- Generates structured content (Generation → Reflection → Curation)
- Appends to existing document or creates new one
- Preserves all historical content

**File**: `save-context.md`

### @create-pr [audit] [draft]
Automated pull request creation with smart description generation.

**Usage**: 
- `@create-pr`
- `@create-pr audit`
- `@create-pr draft`

**What it does**:
- Analyzes git branch and commits
- Generates comprehensive PR description
- Extracts Jira issue from branch name
- Executes `git pr` command

**File**: `create-pr.md`

## How Commands Work

These commands are **documentation files**, not executable scripts. They instruct Claude Code CLI on how to respond when you use the command syntax in conversation.

When you say `@load-context myproject` in Claude Code:
1. Claude reads the instructions from `load-context.md`
2. Executes the workflow described in the file
3. Uses terminal commands and file operations to complete the task

## Differences from Cursor

| Cursor | Claude Code |
|--------|-------------|
| `/command` syntax | `@command` syntax |
| Stored in `~/.cursor/commands/` | Documentation in `/usr/local/share/claude-commands/` |
| Auto-loaded by IDE | Reference documentation for AI |

## Viewing Command Details

Inside the container:
```bash
# List all commands
ls /usr/local/share/claude-commands/

# View a specific command
cat /usr/local/share/claude-commands/load-context.md

# Or use less for easier reading
less /usr/local/share/claude-commands/create-pr.md
```

## Location in Container

These files are copied to `/usr/local/share/claude-commands/` during Docker image build and are available to Claude Code CLI when running in the sandboxed environment.

## Adding New Commands

1. Create a new `.md` file in `/home/jwies/khan/james-in-a-box/claude-commands/`
2. Follow the format of existing commands
3. Rebuild the Docker image: `./claude-sandboxed --rebuild`
4. New command will be available in the container

## Command Format

Each command file should include:
- **Purpose**: What the command does
- **Usage**: Example syntax
- **Workflow**: Step-by-step instructions
- **Critical Rules**: DO's and DON'Ts
- **Examples**: Sample interactions

Claude Code CLI will follow these instructions when users invoke the command syntax.

