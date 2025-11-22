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
- Saves PR description to `.git/PR_EDITMSG+<branch-name>.save`
- Human opens PR on GitHub using this description

**File**: `create-pr.md`

### /check-staging
Review and apply staged changes from ~/sharing/staged-changes/

**Usage**: `/check-staging`

**What it does**:
- Reviews all staged code changes
- Archives previous staged changes
- Prepares changes for human to apply to source

**File**: `check-staging.md`

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

**SECURITY FIX**: Previous documentation incorrectly referenced `/usr/local/share/claude-commands/`. The actual location is `~/.claude/commands/`.

## Adding New Commands

1. Create a new `.md` file in `/home/jwies/khan/james-in-a-box/claude-commands/`
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

## Differences from Other AI Assistants

Claude Code uses a slash command system similar to other AI coding assistants:

- **Syntax**: `/command-name args`
- **Storage**: `~/.claude/commands/`
- **Format**: Markdown instruction files
- **Execution**: Claude interprets the markdown and executes the workflow

---

**Last Updated**: 2025-11-22
**Security Note**: All paths and syntax have been verified against actual Claude Code behavior
