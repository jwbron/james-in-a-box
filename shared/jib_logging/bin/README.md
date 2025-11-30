# jib_logging CLI Wrappers

Drop-in replacements for common CLI tools that add automatic logging.

## Available Commands

- `jib-bd` - Wraps the beads (bd) task tracking CLI
- `jib-git` - Wraps git operations
- `jib-gh` - Wraps the GitHub CLI (gh)
- `jib-claude` - Wraps Claude Code CLI

## Usage

### Option 1: Use jib-* prefixed commands directly

Add this directory to your PATH:

```bash
export PATH="$HOME/workspace/james-in-a-box/shared/jib_logging/bin:$PATH"
```

Then use the prefixed commands:

```bash
jib-bd --allow-stale list
jib-git status
jib-gh pr list
jib-claude -p "Hello"
```

### Option 2: Transparent replacement (model doesn't know)

To make these transparent replacements, set up shell aliases or create
symlinks that override the original commands:

```bash
# In your .bashrc or container setup
alias bd='jib-bd'
alias git='jib-git'
alias gh='jib-gh'
alias claude='jib-claude'
```

Or use the provided setup script:

```bash
source ~/workspace/james-in-a-box/shared/jib_logging/bin/setup-aliases.sh
```

### Option 3: PATH override

Create a bin directory earlier in PATH with symlinks:

```bash
mkdir -p ~/.local/bin
ln -sf ~/workspace/james-in-a-box/shared/jib_logging/bin/jib-bd ~/.local/bin/bd
ln -sf ~/workspace/james-in-a-box/shared/jib_logging/bin/jib-git ~/.local/bin/git
ln -sf ~/workspace/james-in-a-box/shared/jib_logging/bin/jib-gh ~/.local/bin/gh
ln -sf ~/workspace/james-in-a-box/shared/jib_logging/bin/jib-claude ~/.local/bin/claude
```

## Environment Variables

- `JIB_LOGGING_PASSTHROUGH=1` - Skip logging, pass through directly to tool
- `JIB_LOGGING_QUIET=1` - Suppress wrapper diagnostic messages

## How It Works

These wrappers:
1. Accept all arguments the original tool accepts
2. Pass them through to the underlying tool via Python wrappers
3. Capture timing, exit codes, and context for logging
4. Output stdout/stderr exactly as the original tool would
5. Return the same exit code as the original tool

The logging happens transparently - output and behavior match the original tools.
