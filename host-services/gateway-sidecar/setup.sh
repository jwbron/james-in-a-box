#!/bin/bash
# Setup script for Gateway Sidecar
#
# Supports two modes:
#   --container (default): Builds Docker image for containerized gateway
#   --systemd: Installs as systemd service (backward compatibility)
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${COMPONENT_DIR}/../.." && pwd)"
SERVICE_NAME="gateway-sidecar.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
CONFIG_DIR="${HOME}/.config/jib"
SHARING_DIR="${HOME}/.jib-sharing"
SECRET_FILE="${CONFIG_DIR}/gateway-secret"
GATEWAY_IMAGE_NAME="jib-gateway"

# Parse arguments
MODE="container"  # Default to container mode
while [[ $# -gt 0 ]]; do
    case $1 in
        --container)
            MODE="container"
            shift
            ;;
        --systemd)
            MODE="systemd"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--container|--systemd]"
            echo ""
            echo "Options:"
            echo "  --container  Build Docker image for containerized gateway (default)"
            echo "  --systemd    Install as systemd user service (legacy)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Run '$0 --help' for usage"
            exit 1
            ;;
    esac
done

echo "Setting up Gateway Sidecar (${MODE} mode)..."
echo ""

# Common setup: directories and secrets
ensure_directories() {
    mkdir -p "$CONFIG_DIR"
    echo "Config directory exists: $CONFIG_DIR"

    mkdir -p "$SHARING_DIR"
    echo "Sharing directory exists: $SHARING_DIR"
}

generate_secret() {
    if [[ ! -f "$SECRET_FILE" ]]; then
        echo "Generating gateway secret..."
        python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$SECRET_FILE"
        chmod 600 "$SECRET_FILE"
        echo "Gateway secret generated: $SECRET_FILE"
    else
        echo "Gateway secret exists: $SECRET_FILE"
    fi

    # Copy secret to sharing directory for container access
    # Note: Containers mount this file directly
    echo "Gateway secret available at: $SECRET_FILE"
}

# Container mode setup
setup_container() {
    GITHUB_TOKEN_FILE="${SHARING_DIR}/.github-token"
    NETWORK_NAME="jib-network"
    CONTAINER_NAME="jib-gateway"

    # Check for GitHub token file
    if [[ ! -f "$GITHUB_TOKEN_FILE" ]]; then
        echo "WARNING: GitHub token file not found at $GITHUB_TOKEN_FILE"
        echo "The gateway requires this file for GitHub authentication."
        echo ""
        echo "Please run the github-token-refresher setup first:"
        echo "  ./host-services/utilities/github-token-refresher/setup.sh"
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Setup cancelled."
            exit 1
        fi
    else
        echo "GitHub token file exists: $GITHUB_TOKEN_FILE"
    fi

    # Check Docker is available
    if ! command -v docker &> /dev/null; then
        echo "ERROR: docker is required but not installed."
        exit 1
    fi

    # Check Dockerfile exists
    DOCKERFILE="${COMPONENT_DIR}/Dockerfile"
    if [[ ! -f "$DOCKERFILE" ]]; then
        echo "ERROR: Dockerfile not found at $DOCKERFILE"
        exit 1
    fi

    # Build the image from repo root (required for COPY context)
    echo ""
    echo "Building gateway container image..."
    echo "  Image: $GATEWAY_IMAGE_NAME"
    echo "  Dockerfile: $DOCKERFILE"
    echo "  Context: $REPO_ROOT"
    echo ""
    docker build -t "$GATEWAY_IMAGE_NAME" -f "$DOCKERFILE" "$REPO_ROOT"

    echo ""
    echo "Gateway image built successfully!"

    # Create Docker network if needed
    if ! docker network inspect "$NETWORK_NAME" &>/dev/null; then
        echo "Creating Docker network: $NETWORK_NAME"
        docker network create "$NETWORK_NAME"
    else
        echo "Docker network exists: $NETWORK_NAME"
    fi

    # Stop and remove existing container if present
    if docker container inspect "$CONTAINER_NAME" &>/dev/null; then
        echo "Removing existing gateway container..."
        docker rm -f "$CONTAINER_NAME" >/dev/null
    fi

    # Start the gateway container
    echo "Starting gateway container..."
    # Gateway needs access to repos to run git commands (remote get-url, push)
    WORKTREES_DIR="${HOME}/.jib-worktrees"
    REPOS_CONFIG="${HOME}/.config/jib/repositories.yaml"

    # Read configured repos from jib config (same source as jib launcher)
    # This ensures gateway mounts the same repos that jib uses
    REPO_MOUNTS=()
    GIT_MOUNTS=()

    if [ -f "$REPOS_CONFIG" ]; then
        echo "Reading repos from: $REPOS_CONFIG"
        # Parse YAML to get repo paths - matches jib's get_local_repos() implementation
        while IFS= read -r repo_path; do
            if [ -n "$repo_path" ] && [ -d "$repo_path" ]; then
                repo_name=$(basename "$repo_path")
                git_dir="${repo_path}/.git"

                # Mount the repo directory itself
                REPO_MOUNTS+=("-v" "${repo_path}:${repo_path}:ro,z")
                echo "  Mounting repo: $repo_name"

                # Mount .git directory at ~/.git-main/<repo> for worktree resolution
                if [ -d "$git_dir" ]; then
                    GIT_MOUNTS+=("-v" "${git_dir}:${HOME}/.git-main/${repo_name}:ro,z")
                    echo "  Mounting .git for: $repo_name"
                fi
            fi
        done < <(python3 -c "
import yaml
from pathlib import Path
import sys
try:
    with open('$REPOS_CONFIG') as f:
        config = yaml.safe_load(f) or {}
    local_repos_config = config.get('local_repos', {})
    paths = local_repos_config.get('paths', []) if isinstance(local_repos_config, dict) else []
    for p in paths:
        path = Path(p).expanduser().resolve()
        if path.exists() and path.is_dir():
            print(path)
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
")
    else
        echo "WARNING: No repos config found at $REPOS_CONFIG"
        echo "Gateway may not be able to access repos for git operations."
    fi

    docker run -d \
        --name "$CONTAINER_NAME" \
        --network "$NETWORK_NAME" \
        -p 9847:9847 \
        --restart unless-stopped \
        -v "$GITHUB_TOKEN_FILE:/secrets/.github-token:ro,z" \
        -v "$SECRET_FILE:/secrets/gateway-secret:ro,z" \
        -v "$WORKTREES_DIR:$WORKTREES_DIR:ro,z" \
        "${REPO_MOUNTS[@]}" \
        "${GIT_MOUNTS[@]}" \
        "$GATEWAY_IMAGE_NAME"

    # Wait for gateway to be ready
    echo ""
    echo "Waiting for gateway to be ready..."
    sleep 2

    # Health check
    HEALTH_URL="http://localhost:9847/api/v1/health"
    if curl -s "$HEALTH_URL" | grep -q '"status"'; then
        echo ""
        echo "Gateway is running!"
        echo ""
        curl -s "$HEALTH_URL" | python3 -m json.tool
    else
        echo ""
        echo "WARNING: Gateway health check failed."
        echo "Check container logs: docker logs $CONTAINER_NAME"
    fi

    echo ""
    echo "Container status:"
    docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

    echo ""
    echo "Setup complete!"
    echo ""
    echo "The containerized gateway sidecar:"
    echo "  - Running as container: $CONTAINER_NAME"
    echo "  - On Docker network: $NETWORK_NAME"
    echo "  - Listening on port 9847"
    echo "  - Will restart automatically (unless-stopped)"
    echo "  - Authentication secret at: $SECRET_FILE"
    echo ""
    echo "The 'jib' command will use this gateway automatically."
    echo ""
    echo "Useful commands:"
    echo "  docker ps | grep $CONTAINER_NAME     # Check if running"
    echo "  docker logs $CONTAINER_NAME          # View logs"
    echo "  docker logs -f $CONTAINER_NAME       # Follow logs"
    echo "  docker restart $CONTAINER_NAME       # Restart gateway"
    echo "  docker stop $CONTAINER_NAME          # Stop gateway"
    echo "  curl http://localhost:9847/api/v1/health  # Health check"
}

# Systemd mode setup (legacy)
setup_systemd() {
    # Check for github-token-refresher service
    if ! systemctl --user is-enabled github-token-refresher.service >/dev/null 2>&1; then
        echo "WARNING: github-token-refresher.service is not enabled."
        echo "The gateway requires this service for GitHub authentication."
        echo ""
        echo "Please run first:"
        echo "  ./host-services/utilities/github-token-refresher/setup.sh"
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Setup cancelled."
            exit 1
        fi
    fi

    # Ensure host-services venv exists with required dependencies
    HOST_SERVICES_DIR="${COMPONENT_DIR}/.."
    VENV_DIR="${HOST_SERVICES_DIR}/.venv"

    if ! command -v uv &> /dev/null; then
        echo "ERROR: uv is required but not installed."
        echo "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    echo "Syncing host-services dependencies with uv..."
    (cd "$HOST_SERVICES_DIR" && uv sync)
    echo "Dependencies installed"

    # Make the gateway script executable
    chmod +x "$COMPONENT_DIR/gateway.py"
    echo "Gateway script made executable"

    # Copy secret to sharing directory for containers (legacy path)
    SHARED_SECRET_FILE="${SHARING_DIR}/.gateway-secret"
    cp "$SECRET_FILE" "$SHARED_SECRET_FILE"
    chmod 600 "$SHARED_SECRET_FILE"
    echo "Gateway secret copied to: $SHARED_SECRET_FILE"

    # Symlink service file
    mkdir -p "$SYSTEMD_DIR"
    ln -sf "$COMPONENT_DIR/$SERVICE_NAME" "$SYSTEMD_DIR/"
    echo "Service file symlinked to $SYSTEMD_DIR/$SERVICE_NAME"

    # Reload systemd
    systemctl --user daemon-reload
    echo "Systemd daemon reloaded"

    # Enable service
    systemctl --user enable "$SERVICE_NAME"
    echo "Service enabled"

    # Start service
    systemctl --user start "$SERVICE_NAME"
    echo "Service started"

    # Wait for service to be ready
    echo ""
    echo "Waiting for gateway to be ready..."
    sleep 2

    # Health check
    HEALTH_URL="http://localhost:9847/api/v1/health"
    if curl -s "$HEALTH_URL" | grep -q '"status"'; then
        echo ""
        echo "Gateway is running!"
        echo ""
        curl -s "$HEALTH_URL" | python3 -m json.tool
    else
        echo ""
        echo "WARNING: Gateway health check failed."
        echo "Check service logs: journalctl --user -u $SERVICE_NAME -f"
    fi

    echo ""
    echo "Service status:"
    systemctl --user status "$SERVICE_NAME" --no-pager || true

    echo ""
    echo "Setup complete!"
    echo ""
    echo "The gateway sidecar:"
    echo "  - Listens on http://localhost:9847"
    echo "  - Requires authentication (secret at $SECRET_FILE)"
    echo "  - Enforces branch/PR ownership policies"
    echo "  - Blocks merge operations (human must merge via GitHub UI)"
    echo "  - Rate limits: 1000 pushes/hr, 500 PR creates/hr, 4000 total/hr"
    echo ""
    echo "Container integration:"
    echo "  - Secret shared at $SHARED_SECRET_FILE"
    echo "  - Containers use this to authenticate with gateway"
    echo ""
    echo "Useful commands:"
    echo "  systemctl --user status $SERVICE_NAME    # Check status"
    echo "  systemctl --user restart $SERVICE_NAME   # Restart service"
    echo "  systemctl --user stop $SERVICE_NAME      # Stop service"
    echo "  journalctl --user -u $SERVICE_NAME -f    # View logs"
    echo "  curl http://localhost:9847/api/v1/health # Health check"
}

# Main execution
ensure_directories
generate_secret

if [[ "$MODE" == "container" ]]; then
    setup_container
else
    setup_systemd
fi
