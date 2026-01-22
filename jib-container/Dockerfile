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
    jq tree watch tmux screen inotify-tools ripgrep \
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

# Install pyyaml early - required by docker-setup.py for reading config
RUN pip3 install --no-cache-dir pyyaml

# Install development tools (configurable via repositories.yaml)
COPY docker-setup.py /tmp/docker-setup.py
RUN chmod +x /tmp/docker-setup.py && \
    apt-get update && \
    python3 /tmp/docker-setup.py && \
    rm /tmp/docker-setup.py

# Install Python dependencies for jib components
# These are required by scripts in /opt/jib-runtime/ (copied from jib-container/)
RUN pip3 install --no-cache-dir \
    pyyaml \
    requests \
    claude-agent-sdk

# Install beads llm issue tracker
# When running as root, the install script puts bd directly in /usr/local/bin
RUN curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash && \
    which bd

# Install Node.js 20.x (required for npm packages: claude-code, claude-code-router, gemini-cli)
RUN mkdir -p /usr/share/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

# Replace bundled ripgrep with system ripgrep to avoid ARM64 crashes on Asahi Linux
# The bundled arm64-linux binary crashes; system ripgrep from apt works correctly
RUN ln -sf /usr/bin/rg /usr/lib/node_modules/@anthropic-ai/claude-code/vendor/ripgrep/arm64-linux/rg

# Install claude-code-router for multi-provider support
# Allows routing to OpenAI, Gemini, DeepSeek, etc. while using Claude Code tooling
RUN npm install -g @musistudio/claude-code-router

# Install Gemini CLI for native Google Gemini support
# Bypasses claude-code-router for direct Gemini access (avoids thought_signature issues)
# https://github.com/google-gemini/gemini-cli
RUN npm install -g @anthropic-ai/claude-code @google/gemini-cli || \
    echo "Gemini CLI install may have failed - will be retried at runtime if needed"

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
COPY .claude/hooks/ /opt/claude-hooks/
RUN chmod 755 /opt/claude-hooks/*.sh 2>/dev/null || true

# Copy jib-container runtime scripts and tools to /opt/jib-runtime
# This provides container-resident executables available in PATH
# The bin/ directory contains symlinks to all executables (maintained by bin/maintain-bin-symlinks)
# Structure: /opt/jib-runtime/jib-container/{bin,jib-tasks,scripts} + /opt/jib-runtime/shared/
COPY . /opt/jib-runtime/
RUN chmod +x /opt/jib-runtime/jib-container/bin/* 2>/dev/null || true && \
    chmod +x /opt/jib-runtime/jib-container/scripts/* 2>/dev/null || true && \
    chmod +x /opt/jib-runtime/jib-container/jib-tools/* 2>/dev/null || true && \
    find /opt/jib-runtime/jib-container/jib-tasks -name "*.py" -exec chmod +x {} \; 2>/dev/null || true

# Make jib-container and shared modules importable via PYTHONPATH
# This is simpler than pip install and doesn't require pyproject.toml
ENV PYTHONPATH="/opt/jib-runtime/jib-container:/opt/jib-runtime/shared"

# Create tmp directory in image (not mounted - container-only scratch space)
RUN mkdir -p /tmp/agent-tmp && chmod 1777 /tmp/agent-tmp

# Note: User will be created dynamically at runtime to match host UID/GID

# Copy entrypoint script (Python for maintainability)
COPY entrypoint.py /usr/local/bin/entrypoint.py
RUN chmod +x /usr/local/bin/entrypoint.py

# WORKDIR is set dynamically in entrypoint based on RUNTIME_USER

ENTRYPOINT ["python3", "/usr/local/bin/entrypoint.py"]

# =============================================================================
# END OF DOCKERFILE
# =============================================================================
# The entrypoint script (entrypoint.py) handles:
# - User creation to match host UID/GID
# - Git configuration and worktree setup
# - Claude Code router configuration (multi-provider support)
# - Agent rules installation (CLAUDE.md, GEMINI.md)
# - Beads persistent memory initialization
# - Interactive/exec mode handling
# =============================================================================
