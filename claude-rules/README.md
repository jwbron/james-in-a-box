# Claude Agent Rules

This directory contains instructions for the AI agent (Claude Code) operating in this sandboxed environment.

## How These Files Are Used

Claude Code reads `CLAUDE.md` files automatically when starting. During container startup, all rule files are combined into a single `CLAUDE.md`:

**Installation:**
- `~/CLAUDE.md` → All rules combined (mission.md + environment.md + khan-academy.md)
- `tools-guide.md` → Installed as `~/tools-guide.md` for reference

**Why one file?** Since `~/khan/` is mounted from the host (not copied), we can't reliably write to it during container startup. Combining all rules into `~/CLAUDE.md` ensures they're always available.

**Note**: `CLAUDE.md` is the [official Claude Code format](https://www.anthropic.com/engineering/claude-code-best-practices) for providing context and instructions to the agent.

## File Guide

### Core Agent Instructions

- **mission.md** - Start here
  - Your role as autonomous software engineering agent
  - Operating model (you do implementation, human does review/deploy)
  - Workflow: gather context → plan → implement → test → PR → save knowledge
  - Decision-making framework (when to proceed vs ask)
  - Quality standards and success metrics

- **environment.md** - Technical constraints
  - What you CAN and CANNOT do in the sandbox
  - File system layout and directory purposes
  - Git workflow (local commits only)
  - Testing and validation commands
  - Error handling patterns

- **khan-academy.md** - Project-specific standards
  - Tech stack (Python, React, TypeScript)
  - Code style guidelines
  - Common commands and tools
  - File organization
  - Development workflow

### Reference Documentation

- **tools-guide.md** - Building reusable utilities
  - Purpose of `~/tools/` directory
  - When to create tools vs one-off scripts
  - Examples and templates
  - Best practices for tool development

## Build Process

These rules are automatically installed during Docker image build:

1. **`jib` script** copies `claude-rules/` to build context
2. **`Dockerfile`** copies rules into image
3. **Entrypoint script** combines and installs as `CLAUDE.md` files

See `jib` and `Dockerfile` for implementation details.

## Maintenance

When updating rules:
- Keep files focused on their specific domain
- Avoid redundancy across files
- Use markdown for consistency
- Rebuild container to apply changes: `./jib`

