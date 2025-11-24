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

# Install Khan Academy development tools
# This includes: Python 3.11, Node.js 20, Go, Java 11, PostgreSQL, etc.
COPY docker-setup.py /tmp/docker-setup.py
RUN chmod +x /tmp/docker-setup.py && \
    apt-get update && \
    python3 /tmp/docker-setup.py && \
    rm /tmp/docker-setup.py

# Install beads llm issue tracker
# Add Go bin to PATH for beads installation
ENV PATH="/root/go/bin:${PATH}"
RUN curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash && \
    which bd || (echo "ERROR: beads (bd) installation failed" && exit 1)

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Note: Claude authentication is mounted at runtime from host (not baked into image)
# This ensures container always uses host's current credentials (no stale OAuth tokens)
# See entrypoint script for runtime credential copy from /tmp/host-claude mount

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
export PATH="/usr/local/bin:${PATH}"
# Prevent Python from creating __pycache__ directories (cleaner worktree cleanup)
export PYTHONDONTWRITEBYTECODE=1

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
    echo "  Git metadata mounted read-only from ~/.git-main/"
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
# Combine all rules into one file: mission + environment + Khan Academy standards
if [ -f "/opt/claude-rules/mission.md" ] && [ -f "/opt/claude-rules/environment.md" ] && [ -f "/opt/claude-rules/khan-academy.md" ]; then
    cat /opt/claude-rules/mission.md > "${USER_HOME}/CLAUDE.md"
    echo "" >> "${USER_HOME}/CLAUDE.md"
    echo "---" >> "${USER_HOME}/CLAUDE.md"
    echo "" >> "${USER_HOME}/CLAUDE.md"
    cat /opt/claude-rules/environment.md >> "${USER_HOME}/CLAUDE.md"
    echo "" >> "${USER_HOME}/CLAUDE.md"
    echo "---" >> "${USER_HOME}/CLAUDE.md"
    echo "" >> "${USER_HOME}/CLAUDE.md"
    cat /opt/claude-rules/khan-academy.md >> "${USER_HOME}/CLAUDE.md"
    chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/CLAUDE.md"
    echo "✓ AI agent rules installed: ~/CLAUDE.md (mission + environment + Khan standards)"
    echo "  Note: All rules combined in one file since ~/khan/ is mounted from host"
fi

# Set up .claude directory with settings that avoid known bugs
mkdir -p "${USER_HOME}/.claude"
mkdir -p "${USER_HOME}/.claude/commands"
mkdir -p "${USER_HOME}/.config/claude-code"

# Copy FRESH credentials from mounted host .claude (not stale image credentials)
# Mount point: /tmp/host-claude (read-only mount from host ~/.claude)
if [ -d "/tmp/host-claude" ] && [ -f "/tmp/host-claude/.credentials.json" ]; then
    echo "✓ Copying FRESH Claude credentials from host..."
    # Copy credentials file
    cp /tmp/host-claude/.credentials.json "${USER_HOME}/.claude/.credentials.json"
    chmod 600 "${USER_HOME}/.claude/.credentials.json"
    echo "  ✓ OAuth credentials copied (always current from host)"

    # Check if credentials have full scopes
    if command -v jq &> /dev/null; then
        SCOPES=$(jq -r '.claudeAiOauth.scopes[]' "${USER_HOME}/.claude/.credentials.json" 2>/dev/null || echo "")
        if echo "$SCOPES" | grep -q "user:sessions:claude_code"; then
            echo "  ✓ Credentials have full scopes (interactive mode supported)"
        else
            echo "  ⚠ Credentials missing 'user:sessions:claude_code' scope"
            echo "    Interactive 'claude' mode may not work"
            echo "    'claude --print' commands will work fine"
            echo "    To fix: Run 'claude' on host to trigger re-authentication"
        fi
    fi

    # Copy other auth-related files if they exist (statsig, session-env)
    if [ -d "/tmp/host-claude/statsig" ]; then
        cp -r /tmp/host-claude/statsig "${USER_HOME}/.claude/" 2>/dev/null || true
        echo "  ✓ Statsig data copied"
    fi
    if [ -d "/tmp/host-claude/session-env" ]; then
        cp -r /tmp/host-claude/session-env "${USER_HOME}/.claude/" 2>/dev/null || true
        echo "  ✓ Session environment copied"
    fi

    # Handle auth.json if it exists in .config location
    if [ -f "/tmp/host-claude/auth.json" ]; then
        cp /tmp/host-claude/auth.json "${USER_HOME}/.config/claude-code/auth.json"
        echo "  ✓ Auth config copied"
    fi
else
    echo "ℹ No host Claude auth mounted - will authenticate with browser on first run"
    echo "  To fix: Ensure ~/.claude/.credentials.json exists on host"
    echo "  Run: claude (and let interactive session start)"
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

# Create alias for Claude with permissions bypassed (safe in this sandboxed environment)
cat >> "${USER_HOME}/.bashrc" << 'BASHRC'
alias claude='claude --dangerously-skip-permissions'
export PS1='\[\033[01;32m\]\u@sandboxed\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '
BASHRC
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.bashrc"
echo "✓ Claude alias created (bypasses permissions in sandbox)"

# Ensure tracking directory exists for watcher logs
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

# NOTE: Background watchers have been removed in favor of exec-based pattern
# Analysis scripts are now triggered by host-side systemd services via `jib --exec`
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
# Analysis scripts location: ~/khan/james-in-a-box/jib-container/components/
#   - context-watcher/jira-watcher.py (triggered by context-sync)
#   - context-watcher/confluence-watcher.py (triggered by context-sync)
#   - github-watcher/check-monitor.py (triggered by github-sync)
#   - incoming-processor.py (triggered by slack-receiver)

echo ""
echo "📊 Analysis Pattern: Exec-based (triggered by host services)"
echo "  - Context analysis: Triggered after context-sync"
echo "  - GitHub analysis: Triggered after github-sync"
echo "  - Message processing: Triggered by slack-receiver"
echo ""

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
    echo "  • ~/CLAUDE.md                      (all rules: mission, environment, Khan)"
    echo "  Note: ~/khan/ is mounted from host - all code changes persist immediately"
    echo ""
    echo "🚀 Quick Start:"
    echo "  1. claude                          # Start Claude (no permissions prompts)"
    echo "  2. @load-context <project>         # Load accumulated knowledge"
    echo "  3. [work on task]"
    echo "  4. @create-pr audit                # Create PR for review"
    echo "  5. @save-context <project>         # Save learnings"
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
    exec gosu "${RUNTIME_UID}:${RUNTIME_GID}" /bin/bash
else
    exec gosu "${RUNTIME_UID}:${RUNTIME_GID}" "$@"
fi
EOF

RUN chmod +x /usr/local/bin/entrypoint.sh

# WORKDIR is set dynamically in entrypoint based on RUNTIME_USER

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

