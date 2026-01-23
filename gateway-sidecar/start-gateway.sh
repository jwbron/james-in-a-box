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

# Repos directory (if exists)
if [ -d "$REPOS_DIR" ]; then
    MOUNTS+=(-v "$REPOS_DIR:$REPOS_DIR:ro,z")
fi

# Worktrees directory (if exists)
if [ -d "$WORKTREES_DIR" ]; then
    MOUNTS+=(-v "$WORKTREES_DIR:$WORKTREES_DIR:ro,z")
fi

# Dynamic git mounts from local_repos in repositories.yaml
# Parse local_repos.paths from YAML and generate git directory mounts
if command -v python3 &> /dev/null; then
    # Check if PyYAML is available
    if ! python3 -c "import yaml" 2>/dev/null; then
        echo "Warning: PyYAML not installed, skipping dynamic git mounts" >&2
    else
        GIT_MOUNTS_OUTPUT=$(python3 -c "
import sys
import yaml
from pathlib import Path

config_path = '$CONFIG_FILE'
home = '$HOME_DIR'

try:
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    local_repos = config.get('local_repos', {})
    paths = local_repos.get('paths', [])

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
            # Output one mount per line for safe parsing
            container_git_path = f'{home}/.git-main/{repo_name}'
            print(f'{git_dir}:{container_git_path}:ro,z')

except Exception as e:
    print(f'Warning: Failed to parse git mounts: {e}', file=sys.stderr)
" 2>&1) || true

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
fi

# Run the container
exec /usr/bin/docker run --rm \
    --name jib-gateway \
    --network jib-network \
    -p 9847:9847 \
    -e JIB_REPO_CONFIG=/config/repositories.yaml \
    "${MOUNTS[@]}" \
    jib-gateway
