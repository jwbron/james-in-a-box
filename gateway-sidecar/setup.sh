#!/bin/bash
# Setup script for Gateway Sidecar
#
# Builds the gateway Docker image and installs a systemd service to manage it.
set -e

COMPONENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${COMPONENT_DIR}/.." && pwd)"
SERVICE_NAME="gateway-sidecar.service"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
CONFIG_DIR="${HOME}/.config/jib"
# Gateway-only secrets directory - NOT shared with jib containers
GATEWAY_SECRETS_DIR="${HOME}/.jib-gateway"
SECRET_FILE="${CONFIG_DIR}/gateway-secret"
GATEWAY_IMAGE_NAME="jib-gateway"
NETWORK_NAME="jib-network"
MOUNTS_ENV_FILE="${CONFIG_DIR}/gateway-mounts.env"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            echo "Usage: $0"
            echo ""
            echo "Builds the gateway Docker image and installs a systemd service to manage it."
            echo ""
            echo "Prerequisites:"
            echo "  - Docker must be installed and running"
            echo "  - github-token-refresher service should be running"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Run '$0 --help' for usage"
            exit 1
            ;;
    esac
done

echo "Setting up Gateway Sidecar..."
echo ""

# Common setup: directories and secrets
ensure_directories() {
    mkdir -p "$CONFIG_DIR"
    echo "Config directory exists: $CONFIG_DIR"

    mkdir -p "$GATEWAY_SECRETS_DIR"
    echo "Gateway secrets directory exists: $GATEWAY_SECRETS_DIR"
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

    # Copy secret to gateway secrets directory for gateway container
    # The gateway container mounts ~/.jib-gateway as /secrets
    GATEWAY_SECRET_COPY="${GATEWAY_SECRETS_DIR}/gateway-secret"
    cp "$SECRET_FILE" "$GATEWAY_SECRET_COPY"
    chmod 600 "$GATEWAY_SECRET_COPY"
    echo "Gateway secret copied to: $GATEWAY_SECRET_COPY"

    # Also copy to jib-sharing for jib containers
    # jib containers mount ~/.jib-sharing as ~/sharing, and the gh wrapper
    # looks for the gateway secret at ~/sharing/.gateway-secret
    JIB_SHARING_DIR="${HOME}/.jib-sharing"
    mkdir -p "$JIB_SHARING_DIR"
    JIB_SECRET_COPY="${JIB_SHARING_DIR}/.gateway-secret"
    cp "$SECRET_FILE" "$JIB_SECRET_COPY"
    chmod 600 "$JIB_SECRET_COPY"
    echo "Gateway secret copied to: $JIB_SECRET_COPY (for jib containers)"
}

# Check prerequisites
check_prerequisites() {
    GITHUB_TOKEN_FILE="${GATEWAY_SECRETS_DIR}/.github-token"

    # Check for GitHub token file
    if [[ ! -f "$GITHUB_TOKEN_FILE" ]]; then
        echo "WARNING: GitHub token file not found at $GITHUB_TOKEN_FILE"
        echo "The gateway requires this file for GitHub authentication."
        echo ""
        echo "Please run the github-token-refresher setup first:"
        echo "  ./host-services/utilities/github-token-refresher/setup.sh"
        echo ""
        echo "Or start the github-token-refresher service:"
        echo "  systemctl --user start github-token-refresher"
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
}

# Build Docker image
build_image() {
    DOCKERFILE="${COMPONENT_DIR}/Dockerfile"

    echo ""
    echo "Building gateway container image..."
    echo "  Image: $GATEWAY_IMAGE_NAME"
    echo "  Dockerfile: $DOCKERFILE"
    echo "  Context: $REPO_ROOT"
    echo ""
    docker build -t "$GATEWAY_IMAGE_NAME" -f "$DOCKERFILE" "$REPO_ROOT"

    echo ""
    echo "Gateway image built successfully!"
}

# Create Docker network
create_network() {
    if ! docker network inspect "$NETWORK_NAME" &>/dev/null; then
        echo "Creating Docker network: $NETWORK_NAME"
        docker network create "$NETWORK_NAME"
    else
        echo "Docker network exists: $NETWORK_NAME"
    fi
}

# Generate environment file with dynamic mounts
generate_mounts_env() {
    echo "Generating dynamic mount configuration..."

    # Build .git-main mounts for each repo
    # Worktree .git files point to ~/.git-main/<repo>/worktrees/<name>
    # so gateway needs the same mounts that jib containers use
    GIT_MOUNTS=""
    SHARED_DIR="${REPO_ROOT}/shared"

    while IFS= read -r repo_path; do
        if [ -n "$repo_path" ] && [ -d "$repo_path" ]; then
            repo_name=$(basename "$repo_path")
            git_dir="${repo_path}/.git"

            # Mount .git directory at ~/.git-main/<repo> for worktree resolution
            if [ -d "$git_dir" ]; then
                GIT_MOUNTS="${GIT_MOUNTS} -v ${git_dir}:${HOME}/.git-main/${repo_name}:ro,z"
                echo "  Will mount .git for: $repo_name"
            fi
        fi
    done < <(PYTHONPATH="${SHARED_DIR}:${PYTHONPATH}" python3 -m jib_config.config 2>/dev/null)

    # Write environment file for systemd
    echo "GIT_MOUNTS=${GIT_MOUNTS}" > "$MOUNTS_ENV_FILE"
    chmod 600 "$MOUNTS_ENV_FILE"
    echo "Mount configuration written to: $MOUNTS_ENV_FILE"
}

# Install and start systemd service
install_service() {
    # Verify mounts env file exists (required by systemd service)
    if [[ ! -f "$MOUNTS_ENV_FILE" ]]; then
        echo "ERROR: Mounts environment file not found at $MOUNTS_ENV_FILE"
        echo "This file is required by the systemd service for git worktree resolution."
        echo "Run generate_mounts_env or re-run this setup script."
        exit 1
    fi

    # Stop existing service if running
    if systemctl --user is-active "$SERVICE_NAME" &>/dev/null; then
        echo "Stopping existing gateway service..."
        systemctl --user stop "$SERVICE_NAME"
    fi

    # Remove any existing container
    if docker container inspect jib-gateway &>/dev/null; then
        echo "Removing existing gateway container..."
        docker rm -f jib-gateway >/dev/null
    fi

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
    sleep 3

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
}

print_summary() {
    echo ""
    echo "Setup complete!"
    echo ""
    echo "The gateway sidecar:"
    echo "  - Runs as Docker container managed by systemd"
    echo "  - Listens on http://localhost:9847"
    echo "  - On Docker network: $NETWORK_NAME"
    echo "  - Requires authentication (secret at $SECRET_FILE)"
    echo "  - Enforces branch/PR ownership policies"
    echo "  - Blocks merge operations (human must merge via GitHub UI)"
    echo ""
    echo "The 'jib' command will use this gateway automatically."
    echo ""
    echo "Incognito mode (optional):"
    echo "  To use a personal GitHub account instead of the bot:"
    echo "  1. Create ~/.config/jib/secrets.env with:"
    echo "     GITHUB_INCOGNITO_TOKEN=ghp_your_personal_access_token"
    echo "  2. Configure github_user in ~/.config/jib/repositories.yaml"
    echo "  3. Restart the gateway: systemctl --user restart $SERVICE_NAME"
    echo ""
    echo "Useful commands:"
    echo "  systemctl --user status $SERVICE_NAME    # Check status"
    echo "  systemctl --user restart $SERVICE_NAME   # Restart service"
    echo "  systemctl --user stop $SERVICE_NAME      # Stop service"
    echo "  journalctl --user -u $SERVICE_NAME -f    # View logs"
    echo "  docker logs jib-gateway                  # View container logs"
    echo "  curl http://localhost:9847/api/v1/health # Health check"
}

# Main execution
ensure_directories
generate_secret
check_prerequisites
build_image
create_network
generate_mounts_env
install_service
print_summary
