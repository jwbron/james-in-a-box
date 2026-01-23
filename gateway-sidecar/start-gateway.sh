#!/bin/bash
# Dynamic startup script for gateway-sidecar
# Generates container mounts at startup rather than relying on stale config files
#
# This is similar to how the main jib script handles mounts dynamically,
# ensuring the gateway always has access to current configuration.

set -e

# Get home directory (works with systemd %h substitution)
HOME_DIR="${HOME:-$(eval echo ~)}"

# Container paths - must match what jib containers use (fixed /home/jib user)
# This is critical for path consistency between jib containers and gateway
CONTAINER_HOME="/home/jib"

CONFIG_FILE="$HOME_DIR/.config/jib/repositories.yaml"
SECRETS_DIR="$HOME_DIR/.jib-gateway"
REPOS_DIR="$HOME_DIR/repos"
WORKTREES_DIR="$HOME_DIR/.jib-worktrees"
GIT_MAIN_DIR="$HOME_DIR/.git-main"

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
MOUNTS+=(-v "$CONFIG_FILE:/config/repositories.yaml:ro,z")

# Secrets directory (contains .github-token and gateway-secret)
MOUNTS+=(-v "$SECRETS_DIR:/secrets:ro,z")

# Repos directory - mount at /home/jib/repos to match container paths
if [ -d "$REPOS_DIR" ]; then
    MOUNTS+=(-v "$REPOS_DIR:$CONTAINER_HOME/repos:ro,z")
fi

# Worktrees directory - mount at /home/jib/.jib-worktrees
if [ -d "$WORKTREES_DIR" ]; then
    MOUNTS+=(-v "$WORKTREES_DIR:$CONTAINER_HOME/.jib-worktrees:ro,z")
fi

# Git main directory - mount at /home/jib/.git-main
if [ -d "$GIT_MAIN_DIR" ]; then
    MOUNTS+=(-v "$GIT_MAIN_DIR:$CONTAINER_HOME/.git-main:ro,z")
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

# Run the container
exec /usr/bin/docker run --rm \
    --name jib-gateway \
    --network jib-network \
    -p 9847:9847 \
    -e JIB_REPO_CONFIG=/config/repositories.yaml \
    "${MOUNTS[@]}" \
    jib-gateway
