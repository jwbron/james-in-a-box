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

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

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

# Khan directory is mounted READ-ONLY from host at runtime
if [ -d "${USER_HOME}/khan" ]; then
    echo "✓ Khan workspace mounted (READ-ONLY for reference)"
    echo "  Agent stages changes in ~/sharing/ for your review"
else
    echo "⚠ Khan workspace not found - check mount configuration"
fi

# Create tmp directory in user's home (not mounted)
mkdir -p "${USER_HOME}/tmp"
chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/tmp"
echo "✓ Tmp directory created (container-only scratch space)"

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

# Copy tools guide as reference (not loaded into CLAUDE.md)
if [ -f "/opt/claude-rules/tools-guide.md" ]; then
    cp /opt/claude-rules/tools-guide.md "${USER_HOME}/tools-guide.md"
    chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/tools-guide.md"
    echo "✓ Tools guide available at ~/tools-guide.md"
fi

# Set up .claude directory with settings that avoid known bugs
mkdir -p "${USER_HOME}/.claude"
mkdir -p "${USER_HOME}/.claude/commands"

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

# Copy OAuth credentials if mounted from host
if [ -f "/opt/host-claude-credentials.json" ]; then
    cp /opt/host-claude-credentials.json "${USER_HOME}/.claude/.credentials.json"
    chown "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.claude/.credentials.json"
    chmod 600 "${USER_HOME}/.claude/.credentials.json"
    echo "✓ Claude OAuth credentials loaded from host"
else
    echo "⚠ No OAuth credentials found - you'll need to authenticate with browser"
    echo "  After authenticating on host, credentials will auto-sync on next run"
fi

chown -R "${RUNTIME_UID}:${RUNTIME_GID}" "${USER_HOME}/.claude"
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
  "autoUpdate": false
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

# Start context-watcher in background (if configured)
if [ -f "${USER_HOME}/khan/cursor-sandboxed/scripts/context-watcher.sh" ]; then
    echo "Starting context-watcher in background..."
    gosu "${RUNTIME_UID}:${RUNTIME_GID}" bash -c "nohup ${USER_HOME}/khan/cursor-sandboxed/scripts/context-watcher.sh >> ${USER_HOME}/sharing/tracking/watcher.log 2>&1 &"
    echo "✓ Context watcher started (monitoring ~/context-sync/)"
else
    echo "⚠ Context watcher script not found at ${USER_HOME}/khan/cursor-sandboxed/scripts/context-watcher.sh"
fi

# Start incoming-watcher in background (if configured)
if [ -f "${USER_HOME}/khan/cursor-sandboxed/scripts/incoming-watcher.sh" ]; then
    echo "Starting incoming message watcher in background..."
    gosu "${RUNTIME_UID}:${RUNTIME_GID}" bash -c "nohup ${USER_HOME}/khan/cursor-sandboxed/scripts/incoming-watcher.sh >> ${USER_HOME}/sharing/tracking/incoming-watcher.log 2>&1 &"
    echo "✓ Incoming watcher started (monitoring ~/sharing/incoming/ and ~/sharing/responses/)"
else
    echo "⚠ Incoming watcher script not found at ${USER_HOME}/khan/cursor-sandboxed/scripts/incoming-watcher.sh"
fi

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
    echo "  • ~/tools-guide.md                 (building reusable tools)"
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
    echo "  • Tools: ~/tools/                         (reusable scripts, MOUNTED rw)"
    echo "  • Sharing: ~/sharing/                     (persistent data, MOUNTED rw)"
    echo "    - ~/sharing/staged-changes/             (code changes for review)"
    echo "    - ~/sharing/notifications/              (Claude → You via Slack)"
    echo "    - ~/sharing/incoming/                   (You → Claude via Slack)"
    echo "    - ~/sharing/responses/                  (Your replies via Slack)"
    echo "    - ~/sharing/context/                    (context docs)"
    echo "  • Tmp: ~/tmp/                             (scratch space, ephemeral)"
    echo ""
    echo "📖 Custom Commands (type to use):"
    echo "  • @load-context <file>             Load previous sessions"
    echo "  • @save-context <file>             Save current session"
    echo "  • @create-pr [audit] [draft]       Create pull request"
    echo "  (Installed in ~/.claude/commands/)"
    echo ""
    echo "💡 Tips:"
    echo "  • ~/khan/ is READ-ONLY - stage changes in ~/sharing/staged-changes/"
    echo "  • Human reviews and applies changes from ~/sharing/ to host repos"
    echo "  • Check context-sync/ for Confluence docs, JIRA tickets, etc."
    echo "  • Send notifications to ~/sharing/notifications/ to get Slack DM"
    echo "  • Check ~/sharing/incoming/ for tasks sent via Slack"
    echo "  • Check ~/sharing/responses/ for replies to your notifications"
    echo "  • Save context after significant work to build knowledge"
    echo "  • Use ~/sharing/ for ANYTHING that must persist across rebuilds"
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

