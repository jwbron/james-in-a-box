#!/bin/bash
#
# Setup script for LLM Documentation Generator (Full 6-Agent Pipeline)
#
# Installs systemd timers for:
# - Weekly documentation generation
# - Scheduled best practice research (security weekly, others monthly)
#
# Per ADR: LLM Documentation Index Strategy (Phases 4 & 5)
#
# Usage:
#   ./setup.sh enable        # Enable all timers (docs + research)
#   ./setup.sh disable       # Disable all timers
#   ./setup.sh status        # Check timer status
#   ./setup.sh run           # Run immediately
#   ./setup.sh research      # Run research only
#   ./setup.sh enable-docs   # Enable only doc generation timer
#   ./setup.sh enable-research  # Enable only research timers

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DOC_SERVICE_NAME="jib-doc-generator"
RESEARCH_SERVICE_NAME="jib-research"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_section() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

# Check if running as user with systemd access
check_systemd() {
    if ! command -v systemctl &> /dev/null; then
        log_error "systemctl not found. This script requires systemd."
        exit 1
    fi
}

# Create systemd service for doc generation
create_doc_service() {
    local service_file="$HOME/.config/systemd/user/${DOC_SERVICE_NAME}.service"
    mkdir -p "$(dirname "$service_file")"

    cat > "$service_file" << EOF
[Unit]
Description=JIB Documentation Generator (Full 6-Agent Pipeline)
After=network.target

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_ROOT}
ExecStart=/bin/bash -c 'python3 ${SCRIPT_DIR}/doc-generator.py --all --type best-practice && python3 ${SCRIPT_DIR}/drift-detector.py'
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    log_info "Created doc service: $service_file"
}

# Create systemd timer for weekly doc generation
create_doc_timer() {
    local timer_file="$HOME/.config/systemd/user/${DOC_SERVICE_NAME}.timer"
    mkdir -p "$(dirname "$timer_file")"

    cat > "$timer_file" << EOF
[Unit]
Description=Weekly JIB Documentation Generation

[Timer]
# Run weekly on Monday at 11:30am (after research at 11am)
OnCalendar=Mon *-*-* 11:30:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

    log_info "Created doc timer: $timer_file"
}

# Create systemd service for security research
create_research_service() {
    local service_file="$HOME/.config/systemd/user/${RESEARCH_SERVICE_NAME}.service"
    mkdir -p "$(dirname "$service_file")"

    cat > "$service_file" << EOF
[Unit]
Description=JIB Best Practice Research
After=network.target

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_ROOT}
# Research multiple topics in sequence
ExecStart=/bin/bash -c 'python3 ${SCRIPT_DIR}/doc-generator.py --research security && python3 ${SCRIPT_DIR}/doc-generator.py --research auth && python3 ${SCRIPT_DIR}/doc-generator.py --research config'
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    log_info "Created research service: $service_file"
}

# Create systemd timer for weekly research
create_research_timer() {
    local timer_file="$HOME/.config/systemd/user/${RESEARCH_SERVICE_NAME}.timer"
    mkdir -p "$(dirname "$timer_file")"

    cat > "$timer_file" << EOF
[Unit]
Description=Weekly JIB Best Practice Research

[Timer]
# Run weekly on Monday at 11am (before doc generation at 11:30am)
OnCalendar=Mon *-*-* 11:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

    log_info "Created research timer: $timer_file"
}

enable_doc_timer() {
    check_systemd

    log_section "Setting up documentation generator timer"

    create_doc_service
    create_doc_timer

    systemctl --user daemon-reload
    systemctl --user enable "${DOC_SERVICE_NAME}.timer"
    systemctl --user start "${DOC_SERVICE_NAME}.timer"

    log_info "Doc generation timer enabled (weekly on Mondays at 11:30am)"
}

enable_research_timer() {
    check_systemd

    log_section "Setting up research timer"

    create_research_service
    create_research_timer

    systemctl --user daemon-reload
    systemctl --user enable "${RESEARCH_SERVICE_NAME}.timer"
    systemctl --user start "${RESEARCH_SERVICE_NAME}.timer"

    log_info "Research timer enabled (weekly on Mondays at 11am)"
}

enable_all_timers() {
    enable_research_timer
    enable_doc_timer

    log_section "All timers enabled"
    log_info "Research runs at 11am, doc generation at 11:30am (Mondays)"
    log_info "Run 'systemctl --user list-timers' to see scheduled runs"
}

disable_timer() {
    check_systemd

    log_info "Disabling all timers..."

    systemctl --user stop "${DOC_SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user disable "${DOC_SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user stop "${RESEARCH_SERVICE_NAME}.timer" 2>/dev/null || true
    systemctl --user disable "${RESEARCH_SERVICE_NAME}.timer" 2>/dev/null || true

    log_info "All timers disabled."
}

show_status() {
    check_systemd

    log_section "Documentation Generator Timer"
    systemctl --user status "${DOC_SERVICE_NAME}.timer" 2>/dev/null || log_warn "Timer not installed"

    log_section "Research Timer"
    systemctl --user status "${RESEARCH_SERVICE_NAME}.timer" 2>/dev/null || log_warn "Timer not installed"

    log_section "Scheduled Runs"
    systemctl --user list-timers "${DOC_SERVICE_NAME}.timer" "${RESEARCH_SERVICE_NAME}.timer" 2>/dev/null || log_warn "No timers scheduled"

    log_section "Research Cache"
    local cache_dir="${PROJECT_ROOT}/docs/generated/research-cache"
    if [ -d "$cache_dir" ]; then
        echo "Cache directory: $cache_dir"
        echo "Cached topics:"
        ls -la "$cache_dir"/*.json 2>/dev/null || echo "  (empty)"
    else
        echo "No research cache yet"
    fi
}

run_now() {
    log_section "Running full documentation pipeline"

    cd "$PROJECT_ROOT"

    echo ""
    log_info "Step 1: Researching best practices..."
    python3 "${SCRIPT_DIR}/doc-generator.py" --research security || true
    python3 "${SCRIPT_DIR}/doc-generator.py" --research auth || true

    echo ""
    log_info "Step 2: Generating best practice documentation..."
    python3 "${SCRIPT_DIR}/doc-generator.py" --all --type best-practice

    echo ""
    log_info "Step 3: Checking for documentation drift..."
    python3 "${SCRIPT_DIR}/drift-detector.py" --suggest-fixes || true

    log_info "Done."
}

run_research() {
    log_section "Running best practice research"

    cd "$PROJECT_ROOT"

    # Research all topics defined in schedule
    for topic in security auth testing config connector notification sync; do
        echo ""
        log_info "Researching: $topic"
        python3 "${SCRIPT_DIR}/doc-generator.py" --research "$topic" || true
    done

    log_info "Research complete. Cache updated in docs/generated/research-cache/"
}

show_help() {
    cat << EOF
JIB Documentation Generator Setup (Full 6-Agent Pipeline)

Usage: $0 <command>

Commands:
  enable           Enable all timers (research + docs)
  disable          Disable all timers
  status           Show timer status and cache info
  run              Run full pipeline now (research + docs + drift check)
  research         Run research only (updates cache)

  enable-docs      Enable only documentation generation timer
  enable-research  Enable only research timer

  help             Show this help message

Schedule:
  Research:        Mondays at 11:00am (updates best practice cache)
  Doc Generation:  Mondays at 11:30am (generates docs with external validation)

The 6-agent pipeline:
  1. Context Agent     - Analyzes code patterns
  2. Draft Agent       - Generates initial documentation
  3. Review Agent      - Validates accuracy
  4. External Agent    - Researches best practices
  5. Revise Agent      - Incorporates external feedback
  6. Output Agent      - Saves final documentation
EOF
}

# Main
case "${1:-help}" in
    enable)
        enable_all_timers
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
    research)
        run_research
        ;;
    enable-docs)
        enable_doc_timer
        ;;
    enable-research)
        enable_research_timer
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
