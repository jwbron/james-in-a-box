#!/bin/bash
#
# Codebase Analyzer Control Script
#
# Manages the codebase analyzer systemd service and timer
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="codebase-analyzer"
SERVICE_FILE="${SCRIPT_DIR}/${SERVICE_NAME}.service"
TIMER_FILE="${SCRIPT_DIR}/${SERVICE_NAME}.timer"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    log_info "Checking requirements..."

    # Check Python 3
    if ! command -v python3 &> /dev/null; then
        log_error "python3 not found"
        exit 1
    fi

    # Check if requests package is installed
    if ! python3 -c "import requests" 2>/dev/null; then
        log_warning "requests package not found"
        log_info "Install with: pip install requests"
        exit 1
    fi

    # Check for claude CLI (uses same auth as Claude Code)
    if ! command -v claude &> /dev/null; then
        log_warning "claude CLI not found in PATH"
        log_info "The analyzer uses 'claude --print' for analysis"
        log_info "Install Claude Code CLI: npm install -g @anthropic-ai/claude-code"
    fi

    log_success "Requirements check complete"
}

install_service() {
    log_info "Installing codebase analyzer service..."

    # SECURITY FIX: Validate service files exist before attempting to copy
    if [ ! -f "$SERVICE_FILE" ]; then
        log_error "Service file not found: $SERVICE_FILE"
        exit 1
    fi
    if [ ! -f "$TIMER_FILE" ]; then
        log_error "Timer file not found: $TIMER_FILE"
        exit 1
    fi

    # Create systemd user directory
    mkdir -p "$SYSTEMD_USER_DIR"

    # Copy service and timer files
    cp "$SERVICE_FILE" "$SYSTEMD_USER_DIR/"
    cp "$TIMER_FILE" "$SYSTEMD_USER_DIR/"

    log_success "Service files copied to $SYSTEMD_USER_DIR"

    # Reload systemd
    systemctl --user daemon-reload

    log_success "Service installed successfully"
    log_info "To enable and start: ./analyzer-ctl.sh enable"
}

uninstall_service() {
    log_info "Uninstalling codebase analyzer service..."

    # Stop and disable if running
    systemctl --user stop "${SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user disable "${SERVICE_NAME}.timer" 2>/dev/null || true

    # Remove service files
    rm -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
    rm -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.timer"

    # Reload systemd
    systemctl --user daemon-reload

    log_success "Service uninstalled successfully"
}

enable_service() {
    log_info "Enabling codebase analyzer timer..."

    systemctl --user enable "${SERVICE_NAME}.timer"
    systemctl --user start "${SERVICE_NAME}.timer"

    log_success "Timer enabled and started"
    log_info "Next run times:"
    systemctl --user list-timers "${SERVICE_NAME}.timer"
}

disable_service() {
    log_info "Disabling codebase analyzer timer..."

    systemctl --user stop "${SERVICE_NAME}.timer"
    systemctl --user disable "${SERVICE_NAME}.timer"

    log_success "Timer disabled and stopped"
}

start_service() {
    log_info "Starting codebase analyzer (one-time run)..."

    systemctl --user start "${SERVICE_NAME}.service"

    log_success "Service started"
    log_info "Check status with: ./analyzer-ctl.sh status"
}

status_service() {
    log_info "Service status:"
    systemctl --user status "${SERVICE_NAME}.service" --no-pager || true

    echo ""
    log_info "Timer status:"
    systemctl --user status "${SERVICE_NAME}.timer" --no-pager || true

    echo ""
    log_info "Next scheduled runs:"
    systemctl --user list-timers "${SERVICE_NAME}.timer" --no-pager || true
}

show_logs() {
    log_info "Recent logs (press Ctrl+C to exit):"
    journalctl --user -u "${SERVICE_NAME}.service" -f
}

test_run() {
    log_info "Running analyzer test (manual execution)..."

    cd "$SCRIPT_DIR"
    python3 "${SCRIPT_DIR}/codebase-analyzer.py"

    log_success "Test run complete"
}

show_usage() {
    cat << EOF
Codebase Analyzer Control Script

Usage: $0 <command>

Commands:
    check       Check requirements and configuration
    install     Install systemd service and timer
    uninstall   Uninstall systemd service and timer
    enable      Enable and start the timer
    disable     Disable and stop the timer
    start       Run analyzer once (manual trigger)
    status      Show service and timer status
    logs        Show recent logs (follow mode)
    test        Test run the analyzer manually
    help        Show this help message

Examples:
    # First time setup
    $0 check
    $0 install
    $0 enable

    # Check status
    $0 status

    # Manual run
    $0 start

    # View logs
    $0 logs

Configuration:
    The analyzer reads ANTHROPIC_API_KEY from environment.

    To set permanently, add to ${HOME}/.config/environment.d/anthropic.conf:
        ANTHROPIC_API_KEY=your-key-here

Schedule:
    - Daily at 11:00 AM (system local time)
    - 5 minutes after system boot
    - Results sent via Slack notification system

EOF
}

# Main command dispatcher
case "${1:-}" in
    check)
        check_requirements
        ;;
    install)
        check_requirements
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    enable)
        enable_service
        ;;
    disable)
        disable_service
        ;;
    start)
        start_service
        ;;
    status)
        status_service
        ;;
    logs)
        show_logs
        ;;
    test)
        test_run
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        log_error "Unknown command: ${1:-}"
        echo ""
        show_usage
        exit 1
        ;;
esac
