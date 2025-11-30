# Docker Layer Caching Strategy:
# - Layers are cached by checksum - unchanged layers reuse cache
# - Order: least-changing (base packages) → most-changing (scripts, configs)
# - When a layer changes, all subsequent layers rebuild
# - Copying files with COPY checks file contents, not timestamps

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install comprehensive development tools
RUN apt-get update && apt-get install -y \
    # Core utilities (includes grep, cut, sort, uniq, tr, etc.)
    coreutils findutils util-linux \
    wget curl ca-certificates software-properties-common \
    gnupg lsb-release sudo gosu git \
    # Text processing
    sed gawk less vim nano \
    # Build tools
    make cmake gcc g++ build-essential pkg-config autoconf automake libtool \
    # Network tools
    netcat-openbsd telnet iputils-ping dnsutils net-tools iproute2 \
    # File operations
    rsync tar gzip bzip2 zip unzip p7zip-full \
    # Process management
    procps htop lsof psmisc \
    # Development
    strace ltrace gdb \
    # Other useful tools
    jq tree watch tmux screen inotify-tools \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI (gh)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Python 3.11 as default (Ubuntu 22.04 ships with 3.10)
# Required for datetime.UTC and other 3.11+ features used by jib scripts
RUN add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --set python3 /usr/bin/python3.11

# Install Khan Academy development tools
# This includes: Node.js 20, Go, Java 11, PostgreSQL, etc.
COPY docker-setup.py /tmp/docker-setup.py
RUN chmod +x /tmp/docker-setup.py && \
    apt-get update && \
    python3 /tmp/docker-setup.py && \
    rm /tmp/docker-setup.py

# Install Python dependencies for jib components
# These are required by scripts in jib-container/components/ and jib-container/scripts/
RUN pip3 install --no-cache-dir \
    pyyaml \
    requests

# Install beads llm issue tracker
# When running as root, the install script puts bd directly in /usr/local/bin
RUN curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash && \
    which bd

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Note: Claude authentication is mounted at runtime from ~/.jib/claude/ on host
# This directory is shared across all containers for consistent authentication
# See entrypoint script for setup and credential detection

# Copy Claude command documentation
RUN mkdir -p /usr/local/share/claude-commands
COPY claude-commands/*.md /usr/local/share/claude-commands/
RUN chmod 644 /usr/local/share/claude-commands/*.md

# Copy Claude agent rules directory
RUN mkdir -p /opt/claude-rules
COPY claude-rules/*.md /opt/claude-rules/
RUN chmod 644 /opt/claude-rules/*.md

# Copy Claude hooks directory
RUN mkdir -p /opt/claude-hooks
COPY .claude/hooks/*.sh /opt/claude-hooks/
RUN chmod 755 /opt/claude-hooks/*.sh

# Create tmp directory in image (not mounted - container-only scratch space)
RUN mkdir -p /tmp/agent-tmp && chmod 1777 /tmp/agent-tmp

# Note: User will be created dynamically at runtime to match host UID/GID

# Create entrypoint script
RUN cat > /usr/local/bin/entrypoint.sh << 'EOF'
#!/bin/bash
set -euo pipefail

# Runtime identity from docker run
RUNTIME_USER="${RUNTIME_USER:-sandboxed}"
RUNTIME_UID="${RUNTIME_UID:-1000}"
RUNTIME_GID="${RUNTIME_GID:-1000}"
JIB_QUIET="${JIB_QUIET:-0}"

# Helper functions for quiet mode
# Note: Must use if/fi pattern (not && shorthand) to ensure return code 0
# The && pattern returns 1 when the test fails, which breaks chains like:
#   service start && log_success "ok" || log_warn "failed"
log_info() {
    if [ "$JIB_QUIET" = "0" ]; then echo "$@"; fi
}

log_success() {
    if [ "$JIB_QUIET" = "0" ]; then echo "✓ $@"; fi
}

log_warn() {
    # Warnings always shown
    echo "⚠ $@"
}

log_error() {
    # Errors always shown
    echo "✗ $@" >&2
}

[ "$JIB_QUIET" = "0" ] && echo "Setting up sandboxed environment for user: ${RUNTIME_USER} (uid=${RUNTIME_UID}, gid=${RUNTIME_GID})"

# Create user's home directory and ensure correct ownership
USER_HOME="/home/${RUNTIME_USER}"
mkdir -p "${USER_HOME}"
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}"

# Add user to /etc/group and /etc/passwd if not exists
if ! getent group "${RUNTIME_GID}" >/dev/null 2>&1; then
    echo "${RUNTIME_USER}:x:${RUNTIME_GID}:" >> /etc/group
fi
if ! getent passwd "${RUNTIME_UID}" >/dev/null 2>&1; then
    echo "${RUNTIME_USER}:x:${RUNTIME_UID}:${RUNTIME_GID}:Sandboxed User:${USER_HOME}:/bin/bash" >> /etc/passwd
    # Passwordless sudo
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "${RUNTIME_USER}" > "/etc/sudoers.d/010-${RUNTIME_USER}-nopasswd"
    chmod 0440 "/etc/sudoers.d/010-${RUNTIME_USER}-nopasswd"
fi

# Start PostgreSQL in container
if ! pgrep -x postgres > /dev/null; then
    service postgresql start >/dev/null 2>&1 && log_success "PostgreSQL started" || log_warn "PostgreSQL failed to start"
fi

# Start Redis in container
if ! pgrep -x redis-server > /dev/null; then
    service redis-server start >/dev/null 2>&1 && log_success "Redis started" || log_warn "Redis failed to start"
fi

# Set up environment
export HOME="${USER_HOME}"
export USER="${RUNTIME_USER}"
# Add jib scripts to PATH for comment-pr-helper.py and other tools
export PATH="${USER_HOME}/khan/james-in-a-box/jib-container/scripts:/usr/local/bin:${PATH}"
# Prevent Python from creating __pycache__ directories (cleaner worktree cleanup)
export PYTHONDONTWRITEBYTECODE=1
# Ensure Python output is unbuffered for real-time streaming to log files
export PYTHONUNBUFFERED=1
# Disable Claude Code auto-update prompts (prevents interrupts in automation)
export DISABLE_AUTOUPDATER=1

# Configure git to commit as "jib"
gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global user.name "jib"
gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global user.email "jib@khan.org"

# Configure git credential helper for GitHub authentication
# Uses GITHUB_TOKEN environment variable (set by jib launcher from GitHub App)
# This allows git push over HTTPS without embedding tokens in remote URLs
if [ -n "${GITHUB_TOKEN:-}" ]; then
    gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global credential.helper "${USER_HOME}/khan/james-in-a-box/jib-container/scripts/git-credential-github-token"
    log_success "Git credential helper configured for GitHub push"
else
    # No token - disable credential helper (will fail on push attempts)
    gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global credential.helper ""
fi
# CRITICAL: Never embed tokens in git remote URLs
# Remote URLs are managed by the HOST and should not be modified by the container
gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global advice.pushUpdateRejected false

# Also fix local repo configs in case they were corrupted with Claude's authorship
# Local configs override global, so we need to ensure they use jib too
if [ -d "${USER_HOME}/.git-main" ]; then
    for repo_config in "${USER_HOME}/.git-main"/*/config; do
        if [ -f "$repo_config" ]; then
            repo_dir=$(dirname "$repo_config")
            # Use git config to set local repo identity (will update the config file)
            git config -f "$repo_config" user.name "jib"
            git config -f "$repo_config" user.email "jib@khan.org"

            # CRITICAL: Verify remote URLs don't have embedded tokens
            # If they do, strip them out (tokens belong in env vars, not URLs)
            remote_url=$(git config -f "$repo_config" remote.origin.url 2>/dev/null || echo "")
            if [[ "$remote_url" =~ x-access-token:|ghs_|ghp_|github_pat_ ]]; then
                log_warn "Found token in git remote URL, cleaning it up..."
                # Extract the GitHub repo path (owner/repo.git)
                clean_url=$(echo "$remote_url" | sed -E 's|https://[^@]*@github\.com/|https://github.com/|')
                git config -f "$repo_config" remote.origin.url "$clean_url"
                log_info "  Cleaned: $remote_url -> $clean_url"
            fi
        fi
    done
fi
log_success "Git configured to commit as jib <jib@khan.org>"

# Fix worktree .git files to point to mounted git directories
# Worktrees have .git files that reference the main repo's .git directory
# We mount the main .git at ~/.git-main/{repo}/ so we need to rewrite these references
#
# FAIL FAST: If worktree setup is broken, exit immediately.
# A container with broken git is worse than no container at all.
worktree_setup_failed=false

if [ -d "${USER_HOME}/khan" ]; then
    # Check if there are any worktrees to configure
    has_worktrees=false
    for repo_dir in "${USER_HOME}/khan"/*; do
        if [ -f "${repo_dir}/.git" ]; then
            has_worktrees=true
            break
        fi
    done

    if [ "$has_worktrees" = true ]; then
        # First, verify ~/.git-main mount exists
        if [ ! -d "${USER_HOME}/.git-main" ]; then
            log_error "FATAL: ~/.git-main not mounted but worktrees exist"
            log_error "  This means jib failed to mount the git directories."
            log_error "  Container cannot start with broken git configuration."
            log_error ""
            log_error "  Possible causes:"
            log_error "    - Docker mount failed"
            log_error "    - Host .git directories don't exist"
            log_error "    - Permission issues on host"
            worktree_setup_failed=true
        else
            worktrees_configured=0
            worktrees_failed=0
            failed_repos=""

            for repo_dir in "${USER_HOME}/khan"/*; do
                if [ -f "${repo_dir}/.git" ]; then
                    repo_name=$(basename "$repo_dir")
                    # Read the original gitdir path
                    original_gitdir=$(cat "${repo_dir}/.git" | sed 's/^gitdir: //')
                    # Extract the worktree admin directory name (last component of path)
                    worktree_admin=$(basename "$original_gitdir")

                    # Build the target path
                    target_path="${USER_HOME}/.git-main/${repo_name}/worktrees/${worktree_admin}"

                    # Verify target path exists before rewriting
                    if [ -d "$target_path" ]; then
                        echo "gitdir: ${target_path}" > "${repo_dir}/.git"
                        chown "${RUNTIME_UID}:${RUNTIME_GID}" "${repo_dir}/.git"
                        worktrees_configured=$((worktrees_configured + 1))
                    else
                        log_error "FATAL: Worktree path doesn't exist for ${repo_name}"
                        log_error "  Expected: ${target_path}"
                        log_error "  Original: ${original_gitdir}"
                        worktrees_failed=$((worktrees_failed + 1))
                        failed_repos="${failed_repos} ${repo_name}"
                    fi
                fi
            done

            if [ $worktrees_failed -gt 0 ]; then
                log_error ""
                log_error "FATAL: ${worktrees_failed} worktree(s) failed to configure:${failed_repos}"
                log_error "  Container cannot start with broken git configuration."
                log_error ""
                log_error "  Possible causes:"
                log_error "    - Worktree was deleted on host"
                log_error "    - Git metadata corrupted"
                log_error "    - Mount configuration mismatch"
                worktree_setup_failed=true
            elif [ $worktrees_configured -gt 0 ]; then
                log_success "Khan worktrees configured: ${worktrees_configured} repo(s)"
                log_info "  Git metadata mounted read-write from ~/.git-main/"
            fi
        fi
    fi
else
    log_warn "Khan workspace not found - check mount configuration"
fi

# Exit if worktree setup failed - don't start a broken container
if [ "$worktree_setup_failed" = true ]; then
    log_error ""
    log_error "Container startup aborted due to worktree configuration failure."
    log_error "Please check your jib setup and try again."
    exit 1
fi

# Create convenience symlink to ~/sharing/tmp
# All shared data is now under ~/sharing/ for cleaner host organization
if [ -d "${USER_HOME}/sharing" ]; then
    # Create symlink: ~/tmp → ~/sharing/tmp
    ln -sf "${USER_HOME}/sharing/tmp" "${USER_HOME}/tmp"

    # Ensure subdirectories exist in sharing/
    mkdir -p "${USER_HOME}/sharing/tmp"
    mkdir -p "${USER_HOME}/sharing/notifications"
    mkdir -p "${USER_HOME}/sharing/context"
    mkdir -p "${USER_HOME}/sharing/tracking"
    mkdir -p "${USER_HOME}/sharing/traces"
    mkdir -p "${USER_HOME}/sharing/logs"

    chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/sharing"
    log_success "Shared directories configured:"
    log_info "  ~/sharing/tmp/           (mounted from ~/.jib-sharing/tmp/)"
    log_info "  ~/sharing/notifications/ (mounted from ~/.jib-sharing/notifications/)"
    log_info "  ~/sharing/context/       (mounted from ~/.jib-sharing/context/)"
    log_info "  ~/sharing/traces/        (LLM trace collection)"
    log_info "  ~/sharing/logs/          (trace collector logs)"
    log_info "  Convenience symlink: ~/tmp → ~/sharing/tmp"
else
    log_warn "Sharing directory not found - check mount configuration"
fi

# Set up agent rules for AI guidance using CLAUDE.md format
# Combine all rules into one file in logical order (per LLM Documentation Index Strategy ADR)
# Order: mission (core) → environment (constraints) → beads (task tracking) → context → standards → quality
RULES_DIR="/opt/claude-rules"
RULES_ORDER=(
    "mission.md"              # Core agent instructions (start here)
    "environment.md"          # Sandbox constraints
    "beads-usage.md"          # Persistent task tracking (mandatory)
    "context-tracking.md"     # Slack/PR context persistence
    "khan-academy.md"         # Tech stack and standards
    "test-workflow.md"        # Test discovery and execution
    "pr-descriptions.md"      # PR writing guidelines
    "notification-template.md" # Async notifications
)

if [ -f "${RULES_DIR}/mission.md" ]; then
    # Start fresh
    : > "${USER_HOME}/CLAUDE.md"

    # Concatenate rules in defined order
    first_file=true
    for rule_file in "${RULES_ORDER[@]}"; do
        if [ -f "${RULES_DIR}/${rule_file}" ]; then
            if [ "$first_file" = false ]; then
                echo "" >> "${USER_HOME}/CLAUDE.md"
                echo "---" >> "${USER_HOME}/CLAUDE.md"
                echo "" >> "${USER_HOME}/CLAUDE.md"
            fi
            cat "${RULES_DIR}/${rule_file}" >> "${USER_HOME}/CLAUDE.md"
            first_file=false
        fi
    done

    chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/CLAUDE.md"
    log_success "AI agent rules installed: ~/CLAUDE.md"
    log_info "  Combined ${#RULES_ORDER[@]} rule files (index-based per LLM Doc ADR)"
    log_info "  Note: Reference docs in ~/khan/james-in-a-box/docs/ (fetched on-demand)"
fi

# Set up .claude directory structure
# NOTE: ~/.claude is now container-local (ephemeral) to prevent history sharing
# Only auth files are synced from ~/.claude-auth/ (mounted from host)
# This ensures each container has isolated session history while sharing authentication
mkdir -p "${USER_HOME}/.claude/commands"
mkdir -p "${USER_HOME}/.config/claude-code"

# Sync auth files from shared auth directory (mounted at ~/.claude-auth/)
# These files are the ONLY things shared between containers
AUTH_DIR="${USER_HOME}/.claude-auth"
if [ -d "$AUTH_DIR" ]; then
    # Copy credentials if they exist
    if [ -f "${AUTH_DIR}/.credentials.json" ]; then
        cp "${AUTH_DIR}/.credentials.json" "${USER_HOME}/.claude/.credentials.json"
        chmod 600 "${USER_HOME}/.claude/.credentials.json"
        log_success "Claude credentials loaded from shared auth"
        log_info "  Auth shared via: ~/.claude-auth/ (mounted)"
        log_info "  Session history: container-local (ephemeral)"
    else
        log_info "No credentials found - this container will authenticate"
        log_info "  After authentication, credentials will be synced to ~/.claude-auth/"
        log_info "  All future containers will automatically use these credentials"
    fi
else
    log_warn "Auth directory not mounted at ~/.claude-auth/"
    log_info "  Container will authenticate but credentials won't persist"
fi

# Create credential sync script - copies new credentials back to shared auth dir
# This runs when Claude Code creates new credentials after authentication
cat > "${USER_HOME}/.claude/sync-credentials.sh" << 'SYNC_SCRIPT'
#!/bin/bash
# Sync credentials from container's .claude to shared auth directory
AUTH_DIR="$HOME/.claude-auth"
if [ -d "$AUTH_DIR" ] && [ -f "$HOME/.claude/.credentials.json" ]; then
    cp "$HOME/.claude/.credentials.json" "$AUTH_DIR/.credentials.json"
    chmod 600 "$AUTH_DIR/.credentials.json"
    echo "✓ Credentials synced to shared auth directory"
fi
SYNC_SCRIPT
chmod +x "${USER_HOME}/.claude/sync-credentials.sh"
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.claude/sync-credentials.sh"

# Note: GitHub operations now go through GitHub MCP server (configured above)
# The gh CLI is kept as fallback but primary access is via MCP
if [ -n "${GITHUB_TOKEN:-}" ]; then
    log_success "GitHub access configured via MCP server"
    log_info "  All GitHub operations (PRs, issues, comments) go through MCP"
else
    log_info "No GitHub token provided"
    log_info "  GitHub MCP server not available"
    log_info "  Add token with: ./setup.sh --update (on host)"
fi

# Copy custom commands to where Claude Code looks for them
if [ -d "/usr/local/share/claude-commands" ]; then
    for cmd in /usr/local/share/claude-commands/*.md; do
        # Skip README
        if [[ "$(basename "$cmd")" != "README.md" ]]; then
            cp "$cmd" "${USER_HOME}/.claude/commands/"
        fi
    done
    log_success "Custom commands installed:"
    [ "$JIB_QUIET" = "0" ] && ls -1 "${USER_HOME}/.claude/commands/" | sed 's/.md$//' | sed 's/^/    @/'
fi

# Copy custom hooks to where Claude Code looks for them
mkdir -p "${USER_HOME}/.claude/hooks"
if [ -d "/opt/claude-hooks" ]; then
    cp /opt/claude-hooks/*.sh "${USER_HOME}/.claude/hooks/" 2>/dev/null || true
    chmod +x "${USER_HOME}/.claude/hooks/"*.sh 2>/dev/null || true
    log_success "Custom hooks installed:"
    [ "$JIB_QUIET" = "0" ] && ls -1 "${USER_HOME}/.claude/hooks/" 2>/dev/null | sed 's/^/    /'
fi

chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.claude"
chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.config/claude-code"
chmod 700 "${USER_HOME}/.claude"

# Create settings.json with:
# - Autonomous operation (no permission prompts)
# - Normal editor mode (avoids vim mode stack overflow bug)
# - Trace collector hooks for LLM analysis
# Reference: https://github.com/anthropics/claude-code/issues/1992
TRACE_COLLECTOR="${USER_HOME}/khan/james-in-a-box/host-services/analysis/trace-collector/hook_handler.py"
BEADS_HOOK="${USER_HOME}/.claude/hooks/session-end.sh"
cat > "${USER_HOME}/.claude/settings.json" << SETTINGS
{
  "alwaysThinkingEnabled": true,
  "defaultPermissionMode": "bypassPermissions",
  "autoApproveEdits": true,
  "editorMode": "normal",
  "autoUpdate": false,
  "outputStyle": "default",
  "hooks": {
    "PostToolUse": [
      {
        "type": "command",
        "command": "python3 ${TRACE_COLLECTOR} post-tool-use"
      }
    ],
    "SessionEnd": [
      {
        "type": "command",
        "command": "python3 ${TRACE_COLLECTOR} session-end"
      },
      {
        "type": "command",
        "command": "bash ${BEADS_HOOK}"
      }
    ]
  }
}
SETTINGS
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.claude/settings.json"
log_success "Claude settings created: ${USER_HOME}/.claude/settings.json"
if [ "$JIB_QUIET" = "0" ]; then
    cat "${USER_HOME}/.claude/settings.json"
    echo ""
fi

# Add the GitHub MCP server using the claude mcp add command
# GitHub MCP provides bi-directional access: repos, issues, PRs, comments, file operations
# This replaces direct gh CLI usage for all GitHub operations
# NOTE: Use --scope user to make it available in ALL projects (not just current dir)
#
# Token sources (in priority order):
# 1. ~/sharing/.github-token file (auto-refreshed by github-token-refresher)
# 2. GITHUB_TOKEN environment variable (set at container start)

# Function to get the current GitHub token
get_github_token() {
    local TOKEN_FILE="${USER_HOME}/sharing/.github-token"
    local token=""

    # Try to read from token file first (this is refreshed by host service)
    if [ -f "$TOKEN_FILE" ]; then
        token=$(python3 -c "
import json
try:
    with open('$TOKEN_FILE') as f:
        data = json.load(f)
    print(data.get('token', ''))
except:
    pass
" 2>/dev/null)
    fi

    # Fall back to environment variable
    if [ -z "$token" ]; then
        token="${GITHUB_TOKEN:-}"
    fi

    echo "$token"
}

CURRENT_TOKEN=$(get_github_token)
if [ -n "$CURRENT_TOKEN" ]; then
    # OPTIMIZATION: Skip reconfiguration if already configured with same token
    MCP_SETTINGS="${USER_HOME}/.claude/settings.local.json"
    TOKEN_HASH=$(echo -n "${CURRENT_TOKEN}" | md5sum | cut -d' ' -f1)
    CACHE_FILE="${USER_HOME}/.claude/.mcp_token_hash"
    CACHED_HASH=""
    [ -f "$CACHE_FILE" ] && CACHED_HASH=$(cat "$CACHE_FILE" 2>/dev/null)

    # Check if MCP is already configured with same token
    if [ -f "$MCP_SETTINGS" ] && [ "$TOKEN_HASH" = "$CACHED_HASH" ] && \
       grep -q '"github"' "$MCP_SETTINGS" 2>/dev/null; then
        log_success "GitHub MCP server already configured (skipped)"
    else
        # Remove any existing github MCP config to ensure clean state
        # This handles upgrades from old configs (e.g., local scope → user scope)
        gosu "${RUNTIME_UID}:${RUNTIME_GID}" claude mcp remove github -s local >/dev/null 2>&1 || true
        gosu "${RUNTIME_UID}:${RUNTIME_GID}" claude mcp remove github -s user >/dev/null 2>&1 || true

        # Add fresh config with user scope
        # Suppress output to avoid logging the Authorization header/token
        gosu "${RUNTIME_UID}:${RUNTIME_GID}" claude mcp add \
            --transport http \
            --scope user \
            github \
            "https://api.githubcopilot.com/mcp/" \
            --header "Authorization: Bearer ${CURRENT_TOKEN}" > /dev/null 2>&1

        # Cache token hash for next startup
        echo "$TOKEN_HASH" > "$CACHE_FILE"
        chown "${RUNTIME_UID}:${RUNTIME_GID}" "$CACHE_FILE"

        # Check if token came from file (auto-refresh enabled)
        if [ -f "${USER_HOME}/sharing/.github-token" ]; then
            log_success "GitHub MCP server configured (auto-refresh enabled)"
            log_info "  Token read from ~/sharing/.github-token"
            log_info "  MCP token watcher will refresh config when token changes"
        else
            log_success "GitHub MCP server configured (api.githubcopilot.com)"
        fi
    fi
    log_info "  All GitHub operations go through MCP: PRs, issues, repos, comments"
else
    log_info "GitHub token not provided - GitHub MCP server not configured"
    log_info "  Add GITHUB_TOKEN to enable GitHub MCP server"
fi

# Create alias for Claude with permissions bypassed (safe in this sandboxed environment)
# Also add jib-container/scripts to PATH
cat >> "${USER_HOME}/.bashrc" << 'BASHRC'
alias claude='claude --dangerously-skip-permissions'
export PS1='\[\033[01;32m\]\u@sandboxed\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
export PATH="${HOME}/khan/james-in-a-box/jib-container/scripts:${PATH}"
BASHRC
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.bashrc"
log_success "Claude alias created (bypasses permissions in sandbox)"

# Ensure tracking directory exists for processor state
if [ -d "${USER_HOME}/sharing" ]; then
    mkdir -p "${USER_HOME}/sharing/tracking"
    chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/sharing/tracking"
fi

# Validate Beads persistent memory system (initialized by setup.sh)
if [ ! -d "${USER_HOME}/sharing/beads" ]; then
    log_error "ERROR: Beads directory not found"
    log_error ""
    log_error "Beads must be initialized before starting the container."
    log_error "Please run setup.sh on the host:"
    log_error ""
    log_error "  cd ~/khan/james-in-a-box"
    log_error "  ./setup.sh"
    log_error ""
    exit 1
fi

if [ ! -f "${USER_HOME}/sharing/beads/.beads/issues.jsonl" ]; then
    log_error "ERROR: Beads not initialized"
    log_error ""
    log_error "Beads repository exists but is not properly initialized."
    log_error "Please run setup.sh on the host:"
    log_error ""
    log_error "  cd ~/khan/james-in-a-box"
    log_error "  ./setup.sh"
    log_error ""
    exit 1
fi

# Beads is properly initialized - set it up
chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/sharing/beads"

# Create convenience symlink: ~/beads → ~/sharing/beads
ln -sf "${USER_HOME}/sharing/beads" "${USER_HOME}/beads"

# Import JSONL if needed (cache is auto-rebuilt)
cd "${USER_HOME}/sharing/beads"
gosu "${RUNTIME_UID}:${RUNTIME_GID}" bd sync --import-only > /dev/null 2>&1 || true

log_success "Beads memory system ready"
log_info "  Location: ~/beads/ (symlink to ~/sharing/beads/)"
log_info "  Usage: bd --allow-stale create 'task description' --labels feature,important"

# Generate documentation indexes (codebase.json, patterns.json, dependencies.json)
# These are gitignored and regenerated on container startup to avoid merge conflicts
INDEX_GENERATOR="${USER_HOME}/khan/james-in-a-box/host-services/analysis/index-generator/index-generator.py"
if [ -f "$INDEX_GENERATOR" ] && [ -d "${USER_HOME}/khan/james-in-a-box" ]; then
    log_info ""
    log_info "Generating documentation indexes..."
    if gosu "${RUNTIME_UID}:${RUNTIME_GID}" python3 "$INDEX_GENERATOR" \
        --project "${USER_HOME}/khan/james-in-a-box" \
        --output "${USER_HOME}/khan/james-in-a-box/docs/generated" > /dev/null 2>&1; then
        log_success "Documentation indexes generated"
        log_info "  Location: ~/khan/james-in-a-box/docs/generated/"
    else
        log_warn "Documentation index generation failed (non-critical)"
    fi
fi

# NOTE: All analysis uses exec-based pattern (no background processes)
# Analysis scripts are triggered by host-side systemd services via `jib --exec`
#
# Pattern:
#   Host systemd service → Syncs data → Calls `jib --exec <analysis-script>`
#   Container → Analysis script runs once → Sends notification → Exits
#
# Benefits:
#   - No continuous background processes in container
#   - Analysis only runs when data changes (triggered by sync)
#   - Simpler architecture, easier to debug
#   - Lower resource usage
#
# Analysis scripts location: ~/khan/james-in-a-box/jib-container/jib-tasks/
#   - jira/jira-processor.py (triggered by context-sync)
#   - confluence/confluence-processor.py (triggered by context-sync)
#   - github/github-processor.py (triggered by github-sync)
#   - slack/incoming-processor.py (triggered by slack-receiver)

log_info ""
log_info "📊 Analysis Pattern: Exec-based (triggered by host services)"
log_info "  - Context analysis: Triggered after context-sync"
log_info "  - GitHub analysis: Triggered after github-sync"
log_info "  - Message processing: Triggered by slack-receiver"
log_info ""

# Setup cleanup trap for container shutdown
cleanup_on_exit() {
    # Cleanup happens silently in quiet mode
    [ "$JIB_QUIET" = "0" ] && echo ""
    [ "$JIB_QUIET" = "0" ] && echo "🧹 Cleaning up on container exit..."

    # Sync credentials back to shared auth directory if they were created/updated
    AUTH_DIR="${USER_HOME}/.claude-auth"
    if [ -d "$AUTH_DIR" ] && [ -f "${USER_HOME}/.claude/.credentials.json" ]; then
        # Check if credentials are new/updated by comparing
        if [ ! -f "${AUTH_DIR}/.credentials.json" ] || \
           ! cmp -s "${USER_HOME}/.claude/.credentials.json" "${AUTH_DIR}/.credentials.json"; then
            cp "${USER_HOME}/.claude/.credentials.json" "${AUTH_DIR}/.credentials.json"
            chmod 600 "${AUTH_DIR}/.credentials.json"
            [ "$JIB_QUIET" = "0" ] && echo "✓ Credentials synced to shared auth directory"
        fi
    fi

    # Check and clean git remote URLs one final time
    if [ -d "${USER_HOME}/.git-main" ]; then
        for repo_config in "${USER_HOME}/.git-main"/*/config; do
            if [ -f "$repo_config" ]; then
                remote_url=$(git config -f "$repo_config" remote.origin.url 2>/dev/null || echo "")
                if [[ "$remote_url" =~ x-access-token:|ghs_|ghp_|github_pat_ ]]; then
                    echo "⚠ WARNING: Git remote URL was modified during session!"
                    echo "  Found token in: $repo_config"
                    # Clean it up
                    clean_url=$(echo "$remote_url" | sed -E 's|https://[^@]*@github\.com/|https://github.com/|')
                    git config -f "$repo_config" remote.origin.url "$clean_url"
                    echo "  ✓ Cleaned: $remote_url -> $clean_url"
                    echo "  Note: This should not happen. Git remote URLs should never contain tokens."
                fi
            fi
        done
    fi

    [ "$JIB_QUIET" = "0" ] && echo "✓ Cleanup complete"
}

# Register cleanup trap
trap cleanup_on_exit EXIT SIGTERM SIGINT

# Drop privileges and start shell or run claude
if [ $# -eq 0 ]; then
    # Start MCP token watcher in background for auto-refresh support
    # This watches ~/sharing/.github-token and reconfigures MCP when token changes
    MCP_WATCHER="${USER_HOME}/khan/james-in-a-box/jib-container/scripts/mcp-token-watcher.py"
    if [ -f "$MCP_WATCHER" ] && [ -f "${USER_HOME}/sharing/.github-token" ]; then
        log_info "Starting MCP token watcher in background..."
        nohup gosu "${RUNTIME_UID}:${RUNTIME_GID}" python3 "$MCP_WATCHER" \
            --interval 60 > /dev/null 2>&1 &
        log_success "MCP token watcher started (PID: $!)"
        log_info "  Will refresh GitHub MCP config when token changes"
        log_info ""
    fi

    # Start credential sync watcher in background
    # This watches ~/.claude/.credentials.json and syncs to ~/.claude-auth/ when it changes
    # Fixes the issue where /login updates local creds but jib --exec containers read from shared
    AUTH_DIR="${USER_HOME}/.claude-auth"
    CREDS_FILE="${USER_HOME}/.claude/.credentials.json"
    if [ -d "$AUTH_DIR" ]; then
        log_info "Starting credential sync watcher..."
        (
            while true; do
                # Wait for credential file changes using inotifywait if available, else poll
                if command -v inotifywait >/dev/null 2>&1; then
                    inotifywait -q -e modify -e create "$CREDS_FILE" 2>/dev/null || sleep 5
                else
                    sleep 5
                fi
                # Sync if credentials changed
                if [ -f "$CREDS_FILE" ]; then
                    if [ ! -f "${AUTH_DIR}/.credentials.json" ] || \
                       ! cmp -s "$CREDS_FILE" "${AUTH_DIR}/.credentials.json"; then
                        cp "$CREDS_FILE" "${AUTH_DIR}/.credentials.json"
                        chmod 600 "${AUTH_DIR}/.credentials.json"
                        echo "✓ Credentials synced to shared auth ($(date +%H:%M:%S))"
                    fi
                fi
            done
        ) &
        log_success "Credential sync watcher started"
        log_info "  Syncs to ~/.claude-auth/ immediately after /login"
        log_info ""
    fi

    # Show banner only in verbose mode
    if [ "$JIB_QUIET" = "0" ]; then
        echo ""
        echo "======================================================================"
        echo "  🤖 Autonomous Software Engineering Agent"
        echo "======================================================================"
        echo ""
        echo "Role: Autonomous engineer working with minimal supervision"
        echo "Mission: Plan, implement, test, document, and create PRs"
        echo "Human: Reviews and ships your work"
        echo ""
        echo "📋 Your Instructions:"
        echo "  • ~/CLAUDE.md                      (concise rules: mission, beads, context, etc.)"
        echo "  • ~/khan/james-in-a-box/docs/      (reference docs - fetch on demand)"
        echo "  Note: ~/khan/ is mounted from host - all code changes persist immediately"
        echo ""
        echo "🚀 Quick Start:"
        echo "  Claude starts automatically when container launches!"
        echo "  1. @load-context <project>         # Load accumulated knowledge"
        echo "  2. [work on task]"
        echo "  3. @create-pr audit                # Create PR for review"
        echo "  4. @save-context <project>         # Save learnings"
        echo ""
        echo "📚 Available Resources:"
        echo "  • Workspace: ~/khan/                      (code reference, MOUNTED ro)"
        echo "  • Context: ~/context-sync/                (context sources, MOUNTED ro)"
        echo "    - ~/context-sync/confluence/            (ADRs, runbooks, docs)"
        echo "    - ~/context-sync/jira/                  (JIRA tickets, issues)"
        echo "  • Sharing: ~/sharing/                     (ALL persistent data, MOUNTED rw)"
        echo "    - ~/sharing/tmp/                        (persistent scratch, symlinked to ~/tmp/)"
        echo "    - ~/sharing/notifications/              (Claude → You via Slack)"
        echo "    - ~/sharing/incoming/                   (You → Claude via Slack)"
        echo "    - ~/sharing/responses/                  (Your replies via Slack)"
        echo "    - ~/sharing/context/                    (context docs)"
        echo "    - ~/sharing/beads/                      (persistent task memory)"
        echo "    - ~/sharing/tracking/                   (background service logs)"
        echo "  • Beads: ~/beads/ → ~/sharing/beads/      (persistent task/session memory)"
        echo "  • Tmp: ~/tmp/ → ~/sharing/tmp/            (symlink for convenience)"
        echo ""
        echo "📖 Custom Commands (type to use):"
        echo "  • @load-context <file>             Load previous sessions"
        echo "  • @save-context <file>             Save current session"
        echo "  • @create-pr [audit] [draft]       Create pull request"
        echo "  (Installed in ~/.claude/commands/)"
        echo ""
        echo "💡 Tips:"
        echo "  • ~/khan/ is READ-WRITE - make changes directly, commit to git"
        echo "  • Human reviews commits - you can push directly via git push"
        echo "  • Check context-sync/ for Confluence docs, JIRA tickets, etc."
        echo "  • Send notifications to ~/sharing/notifications/ to get Slack DM"
        echo "  • Check ~/sharing/incoming/ for tasks sent via Slack"
        echo "  • Check ~/sharing/responses/ for replies to your notifications"
        echo "  • Save context after significant work to build knowledge"
        echo "  • Use ~/sharing/ for ANYTHING that must persist across rebuilds"
        echo "  • All shared data under ~/sharing/ (tmp, notifications, context, etc.)"
        echo ""
        echo "🔒 Security:"
        echo "  • Bridge network (isolated from host services)"
        echo "  • Outbound HTTP only (for Claude API and packages)"
        echo "  • No inbound ports (cannot accept connections)"
        echo "  • GitHub App token for git push (HTTPS only, no SSH keys)"
        echo "  • No cloud credentials (cannot deploy to GCP/AWS)"
        echo ""
        echo "======================================================================"
        echo ""
    else
        # Minimal output for quiet mode - show ready message
        echo ""
        echo "✓ Ready. Type /help for available commands."
        echo ""
    fi

    # Start in khan directory
    cd "${USER_HOME}/khan" 2>/dev/null || cd "${USER_HOME}"
    # Auto-start Claude Code (bypasses permissions since we're in a sandbox)
    exec gosu "${RUNTIME_UID}:${RUNTIME_GID}" claude --dangerously-skip-permissions
else
    exec gosu "${RUNTIME_UID}:${RUNTIME_GID}" "$@"
fi
EOF

RUN chmod +x /usr/local/bin/entrypoint.sh

# WORKDIR is set dynamically in entrypoint based on RUNTIME_USER

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
