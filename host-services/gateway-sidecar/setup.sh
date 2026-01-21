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
    echo "Building gateway container image..."
    echo ""

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
    echo "Building image from: $REPO_ROOT"
    echo "Using Dockerfile: $DOCKERFILE"
    docker build -t "$GATEWAY_IMAGE_NAME" -f "$DOCKERFILE" "$REPO_ROOT"

    echo ""
    echo "Gateway image built: $GATEWAY_IMAGE_NAME"
    echo ""
    echo "Setup complete!"
    echo ""
    echo "The containerized gateway sidecar:"
    echo "  - Will be started automatically by 'jib' command"
    echo "  - Runs on Docker network: jib-network"
    echo "  - Container name: jib-gateway"
    echo "  - Listens on port 9847 (internal to jib-network)"
    echo "  - Requires authentication (secret at $SECRET_FILE)"
    echo ""
    echo "To manually manage the gateway:"
    echo "  docker ps | grep jib-gateway        # Check if running"
    echo "  docker logs jib-gateway             # View logs"
    echo "  docker stop jib-gateway             # Stop gateway"
    echo "  docker rm jib-gateway               # Remove container"
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
