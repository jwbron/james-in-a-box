#!/bin/bash
# Dynamic startup script for gateway-sidecar
# Generates container mounts at startup rather than relying on stale config files
#
# This is similar to how the main jib script handles mounts dynamically,
# ensuring the gateway always has access to current configuration.

set -e

# Get home directory (works with systemd %h substitution)
HOME_DIR="${HOME:-$(eval echo ~)}"

CONFIG_FILE="$HOME_DIR/.config/jib/repositories.yaml"
SECRETS_DIR="$HOME_DIR/.jib-gateway"
REPOS_DIR="$HOME_DIR/repos"
WORKTREES_DIR="$HOME_DIR/.jib-worktrees"

# Verify required files exist
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file not found: $CONFIG_FILE"
    echo "Run ./setup.py to create the configuration."
    exit 1
fi

if [ ! -d "$SECRETS_DIR" ]; then
    echo "ERROR: Secrets directory not found: $SECRETS_DIR"
    echo "Ensure github-token-refresher service is running."
    exit 1
fi

# Build mount arguments
MOUNTS=""

# Config file mount (required for repo_config.py)
MOUNTS="$MOUNTS -v $CONFIG_FILE:/config/repositories.yaml:ro,z"

# Secrets directory (contains .github-token and gateway-secret)
MOUNTS="$MOUNTS -v $SECRETS_DIR:/secrets:ro,z"

# Repos directory (if exists)
if [ -d "$REPOS_DIR" ]; then
    MOUNTS="$MOUNTS -v $REPOS_DIR:$REPOS_DIR:ro,z"
fi

# Worktrees directory (if exists)
if [ -d "$WORKTREES_DIR" ]; then
    MOUNTS="$MOUNTS -v $WORKTREES_DIR:$WORKTREES_DIR:ro,z"
fi

# Dynamic git mounts from local_repos in repositories.yaml
# Parse local_repos.paths from YAML and generate git directory mounts
if command -v python3 &> /dev/null; then
    GIT_MOUNTS=$(python3 -c "
import yaml
import os
from pathlib import Path

config_path = '$CONFIG_FILE'
home = '$HOME_DIR'

try:
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    local_repos = config.get('local_repos', {})
    paths = local_repos.get('paths', [])

    mounts = []
    for repo_path in paths:
        repo_path = Path(repo_path).expanduser()
        if not repo_path.exists():
            continue

        repo_name = repo_path.name
        git_dir = repo_path / '.git'

        if git_dir.is_file():
            # Worktree - read the actual git dir location
            with open(git_dir) as f:
                content = f.read().strip()
                if content.startswith('gitdir:'):
                    actual_git = content[7:].strip()
                    git_dir = Path(actual_git)

        if git_dir.exists():
            # Mount git directory to a known location
            container_git_path = f'{home}/.git-main/{repo_name}'
            mounts.append(f'-v {git_dir}:{container_git_path}:ro,z')

    print(' '.join(mounts))
except Exception as e:
    # Silently fail - git mounts are optional
    pass
" 2>/dev/null) || true
    MOUNTS="$MOUNTS $GIT_MOUNTS"
fi

# Run the container
exec /usr/bin/docker run --rm \
    --name jib-gateway \
    --network jib-network \
    -p 9847:9847 \
    -e JIB_REPO_CONFIG=/config/repositories.yaml \
    $MOUNTS \
    jib-gateway
