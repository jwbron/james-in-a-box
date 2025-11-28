#!/bin/bash
# Setup script for the index generator service
# Creates symlinks and sets up weekly regeneration via systemd timer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create bin symlinks for easy access
setup_bin_links() {
    log_info "Setting up bin symlinks..."

    mkdir -p "${PROJECT_ROOT}/bin"

    # Create symlink for index-generator
    ln -sf "${SCRIPT_DIR}/index-generator.py" "${PROJECT_ROOT}/bin/generate-index"
    chmod +x "${SCRIPT_DIR}/index-generator.py"

    # Create symlink for query-index
    ln -sf "${SCRIPT_DIR}/query-index.py" "${PROJECT_ROOT}/bin/query-index"
    chmod +x "${SCRIPT_DIR}/query-index.py"

    log_info "Created: bin/generate-index → index-generator.py"
    log_info "Created: bin/query-index → query-index.py"
}

# Install systemd timer for weekly regeneration
install_systemd_timer() {
    log_info "Installing systemd timer for weekly index regeneration..."

    local user_systemd_dir="${HOME}/.config/systemd/user"
    mkdir -p "${user_systemd_dir}"

    # Create service file
    cat > "${user_systemd_dir}/index-generator.service" << EOF
[Unit]
Description=Codebase Index Generator for LLM Navigation
Documentation=docs/adr/ADR-LLM-Documentation-Index-Strategy.md

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_ROOT}
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/index-generator.py
StandardOutput=journal
StandardError=journal

# Security hardening
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${PROJECT_ROOT}/docs/generated
NoNewPrivileges=true
EOF

    # Create timer file (weekly on Sunday at 3am)
    cat > "${user_systemd_dir}/index-generator.timer" << EOF
[Unit]
Description=Weekly Codebase Index Generation
Documentation=docs/adr/ADR-LLM-Documentation-Index-Strategy.md

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true
RandomizedDelaySec=1800

[Install]
WantedBy=timers.target
EOF

    # Reload systemd
    systemctl --user daemon-reload

    # Auto-enable the timer (per ADR: should update automatically)
    if systemctl --user enable --now index-generator.timer 2>/dev/null; then
        log_info "Weekly index regeneration timer enabled and started"
    else
        log_warn "Could not auto-enable timer (systemd user session may not be available)"
        log_info "To enable manually: systemctl --user enable --now index-generator.timer"
    fi
}

# Run initial index generation
run_initial_generation() {
    log_info "Running initial index generation..."

    python3 "${SCRIPT_DIR}/index-generator.py"
}

# Show usage
show_usage() {
    echo "Index Generator Setup"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  install    Install bin symlinks and systemd timer"
    echo "  generate   Run index generation now"
    echo "  enable     Enable weekly timer"
    echo "  disable    Disable weekly timer"
    echo "  status     Show timer status"
    echo "  help       Show this help"
    echo ""
    echo "After installation, use:"
    echo "  bin/generate-index           # Generate/update indexes"
    echo "  bin/query-index summary      # Query codebase summary"
    echo "  bin/query-index component X  # Find component by name"
    echo "  bin/query-index pattern      # List code patterns"
}

# Main
case "${1:-install}" in
    install)
        setup_bin_links
        install_systemd_timer
        run_initial_generation
        log_info "Setup complete!"
        echo ""
        echo "Quick start:"
        echo "  bin/query-index summary      # View codebase summary"
        echo "  bin/query-index pattern      # List detected patterns"
        echo "  bin/query-index search X     # Search for something"
        ;;
    generate)
        run_initial_generation
        ;;
    enable)
        systemctl --user enable --now index-generator.timer
        log_info "Weekly index regeneration enabled"
        ;;
    disable)
        systemctl --user disable --now index-generator.timer
        log_info "Weekly index regeneration disabled"
        ;;
    status)
        systemctl --user status index-generator.timer || true
        systemctl --user list-timers index-generator.timer || true
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        log_error "Unknown command: $1"
        show_usage
        exit 1
        ;;
esac
