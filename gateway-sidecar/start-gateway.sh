#!/bin/bash
# Dynamic startup script for gateway-sidecar
# Generates container mounts at startup rather than relying on stale config files
#
# This script supports both Phase 1 (legacy) and Phase 2 (network lockdown) modes:
# - Phase 1: Single jib-network, no proxy filtering
# - Phase 2: Dual network (jib-isolated + jib-external), Squid proxy filtering
#
# Mode is controlled by JIB_NETWORK_MODE environment variable:
# - "lockdown" = Phase 2 (network lockdown enabled)
# - anything else = Phase 1 (legacy mode)

set -e

# Get home directory (works with systemd %h substitution)
HOME_DIR="${HOME:-$(eval echo ~)}"

# Container paths - must match what jib containers use (fixed /home/jib user)
# This is critical for path consistency between jib containers and gateway
CONTAINER_HOME="/home/jib"

# Network configuration
# Phase 1: jib-network (single network, legacy)
# Phase 2: jib-isolated + jib-external (dual network, lockdown)
NETWORK_MODE="${JIB_NETWORK_MODE:-legacy}"

# Network names and IPs for Phase 2
ISOLATED_NETWORK="jib-isolated"
EXTERNAL_NETWORK="jib-external"
GATEWAY_ISOLATED_IP="172.30.0.2"
GATEWAY_EXTERNAL_IP="172.31.0.2"

# Load secrets from secrets.env if it exists
# This file contains sensitive environment variables like GITHUB_INCOGNITO_TOKEN
SECRETS_ENV_FILE="$HOME_DIR/.config/jib/secrets.env"
if [ -f "$SECRETS_ENV_FILE" ]; then
    # shellcheck source=/dev/null
    set -a  # Automatically export all variables
    source "$SECRETS_ENV_FILE"
    set +a
fi

CONFIG_FILE="$HOME_DIR/.config/jib/repositories.yaml"
SECRETS_DIR="$HOME_DIR/.jib-gateway"
REPOS_DIR="$HOME_DIR/repos"
WORKTREES_DIR="$HOME_DIR/.jib-worktrees"
GIT_MAIN_DIR="$HOME_DIR/.git-main"
LOCAL_OBJECTS_DIR="$HOME_DIR/.jib-local-objects"

# Verify required files exist
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file not found: $CONFIG_FILE" >&2
    echo "Run ./setup.py to create the configuration." >&2
    exit 1
fi

if [ ! -d "$SECRETS_DIR" ]; then
    echo "ERROR: Secrets directory not found: $SECRETS_DIR" >&2
    echo "Ensure github-token-refresher service is running." >&2
    exit 1
fi

# Build mount arguments as an array (handles paths with spaces safely)
MOUNTS=()

# Config file mount (required for repo_config.py)
MOUNTS+=(-v "$CONFIG_FILE:/config/repositories.yaml:ro")

# Secrets directory (contains .github-token and gateway-secret)
MOUNTS+=(-v "$SECRETS_DIR:/secrets:ro")

# Repos directory - mount at /home/jib/repos to match container paths
# Needs RW for git worktree add (writes to .git/worktrees/)
if [ -d "$REPOS_DIR" ]; then
    MOUNTS+=(-v "$REPOS_DIR:$CONTAINER_HOME/repos")
fi

# Worktrees directory - mount at /home/jib/.jib-worktrees
# Needs RW for git fetch to update refs
if [ -d "$WORKTREES_DIR" ]; then
    MOUNTS+=(-v "$WORKTREES_DIR:$CONTAINER_HOME/.jib-worktrees")
fi

# Git main directory - mount at /home/jib/.git-main
# Needs RW for git fetch (FETCH_HEAD, refs) and object sync after push
if [ -d "$GIT_MAIN_DIR" ]; then
    MOUNTS+=(-v "$GIT_MAIN_DIR:$CONTAINER_HOME/.git-main")
fi

# Local objects directory - mount at /home/jib/.jib-local-objects
# Used to read container-created objects for sync to shared store
if [ -d "$LOCAL_OBJECTS_DIR" ]; then
    MOUNTS+=(-v "$LOCAL_OBJECTS_DIR:$CONTAINER_HOME/.jib-local-objects:ro")
fi

# Dynamic git mounts from local_repos in repositories.yaml
# Parse local_repos.paths from YAML and generate git directory mounts
# NOTE: We pass CONTAINER_HOME as the destination path base so mounts match
# what jib containers expect (fixed /home/jib user since PR #538)
SCRIPT_DIR="$(dirname "$0")"
if command -v python3 &> /dev/null; then
    GIT_MOUNTS_OUTPUT=$(python3 "$SCRIPT_DIR/parse-git-mounts.py" "$CONFIG_FILE" "$CONTAINER_HOME" 2>&1) || true

    # Parse output line by line (handles paths with spaces)
    while IFS= read -r mount_spec; do
        # Skip warning lines (sent to stderr but captured due to 2>&1)
        if [[ "$mount_spec" == Warning:* ]]; then
            echo "$mount_spec" >&2
            continue
        fi
        # Skip empty lines
        if [ -n "$mount_spec" ]; then
            MOUNTS+=(-v "$mount_spec")
        fi
    done <<< "$GIT_MOUNTS_OUTPUT"
fi

# Build environment variable arguments
ENV_ARGS=(-e JIB_REPO_CONFIG=/config/repositories.yaml)

# Pass host home directory for path translation in API responses
# The gateway runs with CONTAINER_HOME=/home/jib but needs to return
# host paths to the jib launcher for Docker mount sources
ENV_ARGS+=(-e "HOST_HOME=$HOME_DIR")

# Pass network mode to gateway (for conditional Squid startup)
ENV_ARGS+=(-e "JIB_NETWORK_MODE=$NETWORK_MODE")

# Pass incognito token if configured (for personal GitHub account attribution)
if [ -n "${GITHUB_INCOGNITO_TOKEN:-}" ]; then
    ENV_ARGS+=(-e "GITHUB_INCOGNITO_TOKEN=$GITHUB_INCOGNITO_TOKEN")
fi

# =============================================================================
# Network Configuration
# =============================================================================

run_phase1_legacy() {
    # Phase 1: Single network (jib-network), no proxy filtering
    echo "Starting gateway in Phase 1 (legacy) mode..."
    echo "  Network: jib-network"
    echo "  Proxy: disabled"

    # Ensure jib-network exists
    if ! docker network inspect jib-network &>/dev/null; then
        echo "Creating jib-network..."
        docker network create jib-network
    fi

    exec /usr/bin/docker run --rm \
        --name jib-gateway \
        --network jib-network \
        --security-opt label=disable \
        --user "$(id -u):$(id -g)" \
        -p 9847:9847 \
        "${ENV_ARGS[@]}" \
        "${MOUNTS[@]}" \
        jib-gateway
}

run_phase2_lockdown() {
    # Phase 2: Dual network (jib-isolated + jib-external), Squid proxy filtering
    echo "Starting gateway in Phase 2 (network lockdown) mode..."
    echo "  Networks: $ISOLATED_NETWORK (internal) + $EXTERNAL_NETWORK (external)"
    echo "  Gateway IPs: $GATEWAY_ISOLATED_IP (isolated), $GATEWAY_EXTERNAL_IP (external)"
    echo "  Proxy: enabled (port 3128)"

    # Verify networks exist
    if ! docker network inspect "$ISOLATED_NETWORK" &>/dev/null; then
        echo "ERROR: $ISOLATED_NETWORK network not found" >&2
        echo "Run create-networks.sh first to set up Phase 2 networks" >&2
        exit 1
    fi
    if ! docker network inspect "$EXTERNAL_NETWORK" &>/dev/null; then
        echo "ERROR: $EXTERNAL_NETWORK network not found" >&2
        echo "Run create-networks.sh first to set up Phase 2 networks" >&2
        exit 1
    fi

    # Remove existing gateway container if present
    docker rm -f jib-gateway 2>/dev/null || true

    # Start gateway on isolated network first (with fixed IP)
    echo "Starting gateway container on $ISOLATED_NETWORK..."
    docker run -d \
        --name jib-gateway \
        --network "$ISOLATED_NETWORK" \
        --ip "$GATEWAY_ISOLATED_IP" \
        --security-opt label=disable \
        --user "$(id -u):$(id -g)" \
        -p 9847:9847 \
        -p 3128:3128 \
        "${ENV_ARGS[@]}" \
        "${MOUNTS[@]}" \
        jib-gateway

    # Connect to external network (dual-homed)
    echo "Connecting gateway to $EXTERNAL_NETWORK..."
    docker network connect --ip "$GATEWAY_EXTERNAL_IP" "$EXTERNAL_NETWORK" jib-gateway

    echo "Gateway started in lockdown mode (dual-homed)"
    echo ""
    echo "Container topology:"
    echo "  jib container (172.30.0.10) -> gateway (172.30.0.2:3128) -> Internet (allowlisted)"
    echo ""

    # Follow logs (similar to exec behavior)
    exec docker logs -f jib-gateway
}

# =============================================================================
# Main Execution
# =============================================================================

echo "=== Gateway Sidecar Startup ==="
echo "Mode: $NETWORK_MODE"
echo ""

case "$NETWORK_MODE" in
    lockdown)
        run_phase2_lockdown
        ;;
    *)
        run_phase1_legacy
        ;;
esac
