#!/bin/bash
#
# Setup script for LLM Documentation Generator
#
# Installs systemd timer for scheduled documentation generation and drift detection.
# Per ADR: LLM Documentation Index Strategy (Phase 4)
#
# Usage:
#   ./setup.sh enable   # Enable weekly timer
#   ./setup.sh disable  # Disable timer
#   ./setup.sh status   # Check timer status
#   ./setup.sh run      # Run immediately

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SERVICE_NAME="jib-doc-generator"

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

# Check if running as user with systemd access
check_systemd() {
    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not found. This script requires systemd."
        exit 1
    fi
}

# Create systemd service file
create_service() {
    local service_file="$HOME/.config/systemd/user/${SERVICE_NAME}.service"
    mkdir -p "$(dirname "$service_file")"

    cat > "$service_file" << EOF
[Unit]
Description=JIB Documentation Generator and Drift Detector
After=network.target

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_ROOT}
ExecStart=/bin/bash -c 'python3 ${SCRIPT_DIR}/doc-generator.py --all && python3 ${SCRIPT_DIR}/drift-detector.py'
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    log_info "Created service file: $service_file"
}

# Create systemd timer file
create_timer() {
    local timer_file="$HOME/.config/systemd/user/${SERVICE_NAME}.timer"
    mkdir -p "$(dirname "$timer_file")"

    cat > "$timer_file" << EOF
[Unit]
Description=Weekly JIB Documentation Generation

[Timer]
# Run weekly on Sunday at 4am (after index-generator at 3am)
OnCalendar=Sun *-*-* 04:00:00
Persistent=true
RandomizedDelaySec=1800

[Install]
WantedBy=timers.target
EOF

    log_info "Created timer file: $timer_file"
}

enable_timer() {
    check_systemd

    log_info "Setting up documentation generator timer..."

    # Create service and timer files
    create_service
    create_timer

    # Reload systemd
    systemctl --user daemon-reload

    # Enable and start timer
    systemctl --user enable "${SERVICE_NAME}.timer"
    systemctl --user start "${SERVICE_NAME}.timer"

    log_info "Timer enabled. Documentation will be generated weekly on Sundays at 4am."
    log_info "Run 'systemctl --user status ${SERVICE_NAME}.timer' to check status."
}

disable_timer() {
    check_systemd

    log_info "Disabling documentation generator timer..."

    systemctl --user stop "${SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user disable "${SERVICE_NAME}.timer" 2>/dev/null || true

    log_info "Timer disabled."
}

show_status() {
    check_systemd

    echo "=== Timer Status ==="
    systemctl --user status "${SERVICE_NAME}.timer" 2>/dev/null || log_warn "Timer not installed"

    echo ""
    echo "=== Service Status ==="
    systemctl --user status "${SERVICE_NAME}.service" 2>/dev/null || log_warn "Service not installed"

    echo ""
    echo "=== Next Run ==="
    systemctl --user list-timers "${SERVICE_NAME}.timer" 2>/dev/null || log_warn "Timer not scheduled"
}

run_now() {
    log_info "Running documentation generator..."

    cd "$PROJECT_ROOT"

    echo ""
    echo "=== Generating Documentation ==="
    python3 "${SCRIPT_DIR}/doc-generator.py" --all

    echo ""
    echo "=== Checking for Drift ==="
    python3 "${SCRIPT_DIR}/drift-detector.py" --suggest-fixes || true

    log_info "Done."
}

show_help() {
    cat << EOF
JIB Documentation Generator Setup

Usage: $0 <command>

Commands:
  enable    Enable weekly documentation generation timer
  disable   Disable the timer
  status    Show timer status
  run       Run documentation generator immediately
  help      Show this help message

The timer runs weekly on Sundays at 4am, after the index-generator.
EOF
}

# Main
case "${1:-help}" in
    enable)
        enable_timer
        ;;
    disable)
        disable_timer
        ;;
    status)
        show_status
        ;;
    run)
        run_now
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
