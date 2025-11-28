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
    jq tree watch tmux screen \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI (gh)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Khan Academy development tools
# This includes: Python 3.11, Node.js 20, Go, Java 11, PostgreSQL, etc.
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

echo "Setting up sandboxed environment for user: ${RUNTIME_USER} (uid=${RUNTIME_UID}, gid=${RUNTIME_GID})"

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
    service postgresql start >/dev/null 2>&1 && echo "✓ PostgreSQL started" || echo "⚠ PostgreSQL failed to start"
fi

# Start Redis in container
if ! pgrep -x redis-server > /dev/null; then
    service redis-server start >/dev/null 2>&1 && echo "✓ Redis started" || echo "⚠ Redis failed to start"
fi

# Set up environment
export HOME="${USER_HOME}"
export USER="${RUNTIME_USER}"
# Add jib scripts to PATH for comment-pr-helper.py and other tools
export PATH="${USER_HOME}/khan/james-in-a-box/jib-container/scripts:/usr/local/bin:${PATH}"
# Prevent Python from creating __pycache__ directories (cleaner worktree cleanup)
export PYTHONDONTWRITEBYTECODE=1

# Configure git to commit as "jib"
gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global user.name "jib"
gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global user.email "jib@khan.org"

# CRITICAL: Prevent modification of git remote URLs
# Container has GITHUB_TOKEN for MCP server, but should NEVER embed it in git remotes
# Remote URLs are managed by the HOST and should not be modified by the container
gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global advice.pushUpdateRejected false
gosu "${RUNTIME_UID}:${RUNTIME_GID}" git config --global credential.helper ""
# Set helper to empty string - container should NOT use credential helpers that modify remotes

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
                echo "⚠ WARNING: Found token in git remote URL, cleaning it up..."
                # Extract the GitHub repo path (owner/repo.git)
                clean_url=$(echo "$remote_url" | sed -E 's|https://[^@]*@github\.com/|https://github.com/|')
                git config -f "$repo_config" remote.origin.url "$clean_url"
                echo "  Cleaned: $remote_url -> $clean_url"
            fi
        fi
    done
fi
echo "✓ Git configured to commit as jib <jib@khan.org>"
echo "✓ Git credential helper disabled (container uses MCP, not git credentials)"

# Fix worktree .git files to point to mounted git directories
# Worktrees have .git files that reference the main repo's .git directory
# We mount the main .git at ~/.git-main/{repo}/ so we need to rewrite these references
if [ -d "${USER_HOME}/khan" ]; then
    for repo_dir in "${USER_HOME}/khan"/*; do
        if [ -f "${repo_dir}/.git" ]; then
            repo_name=$(basename "$repo_dir")
            # Read the original gitdir path
            original_gitdir=$(cat "${repo_dir}/.git" | sed 's/^gitdir: //')
            # Extract the worktree admin directory name (last component of path)
            worktree_admin=$(basename "$original_gitdir")
            # Rewrite .git file to point to the mounted location
            echo "gitdir: ${USER_HOME}/.git-main/${repo_name}/worktrees/${worktree_admin}" > "${repo_dir}/.git"
            chown "${RUNTIME_UID}:${RUNTIME_GID}" "${repo_dir}/.git"
        fi
    done
    echo "✓ Khan worktrees configured (isolated from host)"
    echo "  Git metadata mounted read-write from ~/.git-main/"
else
    echo "⚠ Khan workspace not found - check mount configuration"
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

    chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/sharing"
    echo "✓ Shared directories configured:"
    echo "  ~/sharing/tmp/           (mounted from ~/.jib-sharing/tmp/)"
    echo "  ~/sharing/notifications/ (mounted from ~/.jib-sharing/notifications/)"
    echo "  ~/sharing/context/       (mounted from ~/.jib-sharing/context/)"
    echo "  Convenience symlink: ~/tmp → ~/sharing/tmp"
else
    echo "⚠ Sharing directory not found - check mount configuration"
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
    echo "✓ AI agent rules installed: ~/CLAUDE.md"
    echo "  Combined ${#RULES_ORDER[@]} rule files (index-based per LLM Doc ADR)"
    echo "  Note: Reference docs in ~/khan/james-in-a-box/docs/ (fetched on-demand)"
fi

# Set up .claude directory structure
# Note: ~/.claude is mounted from host at ~/.jib/claude/ (shared across all containers)
# We just need to ensure subdirectories exist and set permissions
mkdir -p "${USER_HOME}/.claude/commands"
mkdir -p "${USER_HOME}/.config/claude-code"

# Check authentication status
if [ -f "${USER_HOME}/.claude/.credentials.json" ]; then
    chmod 600 "${USER_HOME}/.claude/.credentials.json"
    echo "✓ Claude credentials found (shared across all containers)"
    echo "  Location: ~/.jib/claude/ on host"
else
    echo "ℹ No credentials found - this container will authenticate"
    echo "  After authentication, credentials will be saved to ~/.jib/claude/"
    echo "  All future containers will automatically use these credentials"
fi

# Note: GitHub operations now go through GitHub MCP server (configured above)
# The gh CLI is kept as fallback but primary access is via MCP
if [ -n "${GITHUB_TOKEN:-}" ]; then
    echo "✓ GitHub access configured via MCP server"
    echo "  All GitHub operations (PRs, issues, comments) go through MCP"
else
    echo "ℹ No GitHub token provided"
    echo "  GitHub MCP server not available"
    echo "  Add token with: ./setup.sh --update (on host)"
fi

# Copy custom commands to where Claude Code looks for them
if [ -d "/usr/local/share/claude-commands" ]; then
    for cmd in /usr/local/share/claude-commands/*.md; do
        # Skip README
        if [[ "$(basename "$cmd")" != "README.md" ]]; then
            cp "$cmd" "${USER_HOME}/.claude/commands/"
        fi
    done
    echo "✓ Custom commands installed:"
    ls -1 "${USER_HOME}/.claude/commands/" | sed 's/.md$//' | sed 's/^/    @/'
fi

chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.claude"
chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.config/claude-code"
chmod 700 "${USER_HOME}/.claude"

# Create settings.json with:
# - Autonomous operation (no permission prompts)
# - Normal editor mode (avoids vim mode stack overflow bug)
# Reference: https://github.com/anthropics/claude-code/issues/1992
cat > "${USER_HOME}/.claude/settings.json" << 'SETTINGS'
{
  "alwaysThinkingEnabled": true,
  "defaultPermissionMode": "bypassPermissions",
  "autoApproveEdits": true,
  "editorMode": "normal",
  "autoUpdate": false,
  "outputStyle": "default"
}
SETTINGS
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.claude/settings.json"
echo "✓ Claude settings created: ${USER_HOME}/.claude/settings.json"
cat "${USER_HOME}/.claude/settings.json"
echo ""

# Add the GitHub MCP server using the claude mcp add command
# GitHub MCP provides bi-directional access: repos, issues, PRs, comments, file operations
# This replaces direct gh CLI usage for all GitHub operations
# NOTE: Use --scope user to make it available in ALL projects (not just current dir)
if [ -n "${GITHUB_TOKEN:-}" ]; then
    # Remove any existing github MCP config to ensure clean state
    # This handles upgrades from old configs (e.g., local scope → user scope)
    gosu "${RUNTIME_UID}:${RUNTIME_GID}" claude mcp remove github -s local 2>/dev/null || true
    gosu "${RUNTIME_UID}:${RUNTIME_GID}" claude mcp remove github -s user 2>/dev/null || true

    # Add fresh config with user scope
    gosu "${RUNTIME_UID}:${RUNTIME_GID}" claude mcp add \
        --transport http \
        --scope user \
        github \
        "https://api.githubcopilot.com/mcp/" \
        --header "Authorization: Bearer ${GITHUB_TOKEN}"
    echo "✓ GitHub MCP server configured (api.githubcopilot.com)"
    echo "  All GitHub operations go through MCP: PRs, issues, repos, comments"
else
    echo "ℹ GitHub token not provided - GitHub MCP server not configured"
    echo "  Add GITHUB_TOKEN to enable GitHub MCP server"
fi

# Create alias for Claude with permissions bypassed (safe in this sandboxed environment)
# Also add jib-container/scripts to PATH
cat >> "${USER_HOME}/.bashrc" << 'BASHRC'
alias claude='claude --dangerously-skip-permissions'
export PS1='\[\033[01;32m\]\u@sandboxed\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
export PATH="${HOME}/khan/james-in-a-box/jib-container/scripts:${PATH}"
BASHRC
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.bashrc"
echo "✓ Claude alias created (bypasses permissions in sandbox)"

# Ensure tracking directory exists for processor state
if [ -d "${USER_HOME}/sharing" ]; then
    mkdir -p "${USER_HOME}/sharing/tracking"
    chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/sharing/tracking"
fi

# Validate Beads persistent memory system (initialized by setup.sh)
if [ ! -d "${USER_HOME}/sharing/beads" ]; then
    echo "❌ ERROR: Beads directory not found"
    echo ""
    echo "Beads must be initialized before starting the container."
    echo "Please run setup.sh on the host:"
    echo ""
    echo "  cd ~/khan/james-in-a-box"
    echo "  ./setup.sh"
    echo ""
    exit 1
fi

if [ ! -f "${USER_HOME}/sharing/beads/.beads/issues.jsonl" ]; then
    echo "❌ ERROR: Beads not initialized"
    echo ""
    echo "Beads repository exists but is not properly initialized."
    echo "Please run setup.sh on the host:"
    echo ""
    echo "  cd ~/khan/james-in-a-box"
    echo "  ./setup.sh"
    echo ""
    exit 1
fi

# Beads is properly initialized - set it up
chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/sharing/beads"

# Create convenience symlink: ~/beads → ~/sharing/beads
ln -sf "${USER_HOME}/sharing/beads" "${USER_HOME}/beads"

# Rebuild cache in case it's stale
cd "${USER_HOME}/sharing/beads"
gosu "${RUNTIME_UID}:${RUNTIME_GID}" bd build-cache > /dev/null 2>&1 || true

echo "✓ Beads memory system ready"
echo "  Location: ~/beads/ (symlink to ~/sharing/beads/)"
echo "  Usage: bd add 'task description' --tags feature,important"

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

echo ""
echo "📊 Analysis Pattern: Exec-based (triggered by host services)"
echo "  - Context analysis: Triggered after context-sync"
echo "  - GitHub analysis: Triggered after github-sync"
echo "  - Message processing: Triggered by slack-receiver"
echo ""

# Setup cleanup trap for container shutdown
cleanup_on_exit() {
    echo ""
    echo "🧹 Cleaning up on container exit..."

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

    echo "✓ Cleanup complete"
}

# Register cleanup trap
trap cleanup_on_exit EXIT SIGTERM SIGINT

# Drop privileges and start shell or run claude
if [ $# -eq 0 ]; then
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
    echo "  • Human reviews commits and pushes from host"
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
    echo "  • No credentials (cannot push to git or deploy to cloud)"
    echo ""
    echo "======================================================================"
    echo ""
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

