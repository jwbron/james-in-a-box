#!/bin/bash
# Master setup script for james-in-a-box host components
set -e

# Parse arguments
UPDATE_MODE=false
FORCE_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --update)
            UPDATE_MODE=true
            shift
            ;;
        --force)
            FORCE_MODE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --update    Update existing installation (reload configs, restart services)"
            echo "  --force     Force reinstall even if already installed"
            echo "  --help      Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0              # Initial setup (interactive)"
            echo "  $0 --update     # Update/reload all components"
            echo "  $0 --force      # Force reinstall everything"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Run '$0 --help' for usage information"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        print_error "$1 is not installed"
        return 1
    fi
    return 0
}

is_service_installed() {
    local service_name=$1
    systemctl --user list-unit-files "$service_name" &>/dev/null
}

check_installation_status() {
    local installed_count=0
    local services=(
        "slack-notifier.service"
        "slack-receiver.service"
        "context-sync.timer"
        "github-sync.timer"
        "worktree-watcher.timer"
        "codebase-analyzer.timer"
        "conversation-analyzer.timer"
    )

    for service in "${services[@]}"; do
        if is_service_installed "$service"; then
            ((installed_count++))
        fi
    done

    if [ $installed_count -eq ${#services[@]} ]; then
        return 0  # Fully installed
    elif [ $installed_count -gt 0 ]; then
        return 1  # Partially installed
    else
        return 2  # Not installed
    fi
}

# Check if running on host (not in container)
if [ -f "/.dockerenv" ]; then
    print_error "This script must be run on the host machine, not inside the container"
    exit 1
fi

print_header "James-In-A-Box Host Setup"

# Check installation status
if check_installation_status; then
    ALREADY_INSTALLED=true
    if [ "$UPDATE_MODE" = true ]; then
        print_info "Update mode: Reloading configurations and restarting services"
        echo ""
    elif [ "$FORCE_MODE" = true ]; then
        print_warning "Force mode: Reinstalling all components"
        echo ""
    else
        print_success "JIB is already installed!"
        echo ""
        echo "What would you like to do?"
        echo "  1) Update/reload (refresh configs and restart services)"
        echo "  2) Force reinstall (clean install)"
        echo "  3) Exit"
        echo ""
        read -p "Choose [1-3]: " -n 1 -r
        echo
        case $REPLY in
            1)
                UPDATE_MODE=true
                print_info "Switching to update mode"
                echo ""
                ;;
            2)
                FORCE_MODE=true
                print_warning "Switching to force reinstall mode"
                echo ""
                ;;
            3)
                print_info "Exiting"
                exit 0
                ;;
            *)
                print_error "Invalid choice"
                exit 1
                ;;
        esac
    fi
else
    ALREADY_INSTALLED=false
fi

if [ "$UPDATE_MODE" = true ]; then
    echo "This will:"
    echo "  • Re-symlink all service files (pick up changes)"
    echo "  • Reload systemd daemon"
    echo "  • Restart all JIB services"
    echo ""
else
    echo "This script will:"
    echo "  • Install and configure Slack integration (notifier and receiver)"
    echo "  • Set up automated analyzers (codebase and conversation)"
    echo "  • Configure service failure monitoring and worktree cleanup"
    echo "  • Enable and start all systemd services"
    echo ""
fi

# Check for required dependencies
print_info "Checking dependencies..."
missing_deps=0

dependencies=("python3" "systemctl" "docker")
for dep in "${dependencies[@]}"; do
    if check_dependency "$dep"; then
        print_success "$dep found"
    else
        ((missing_deps++))
    fi
done

if [ $missing_deps -gt 0 ]; then
    print_error "Missing required dependencies. Please install them first."
    exit 1
fi

# Check Python packages
print_info "Checking Python packages..."
if python3 -c "import slack_sdk" 2>/dev/null; then
    print_success "slack-sdk found"
else
    print_warning "slack-sdk not found"
    echo "Install with: pip install slack-sdk"
    read -p "Install now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip install slack-sdk || pip install --user slack-sdk
        print_success "slack-sdk installed"
    else
        print_error "slack-sdk required for Slack integration"
        exit 1
    fi
fi

# Check and install Beads (bd) - persistent task memory system
print_info "Checking for Beads (bd)..."
if command -v bd &> /dev/null; then
    print_success "beads (bd) found"
else
    print_warning "beads (bd) not found"

    # Check if Go is installed (required for beads)
    if ! command -v go &> /dev/null; then
        print_error "Go is required to install beads"
        echo "Install Go first: https://go.dev/doc/install"
        exit 1
    fi

    echo "Install from: https://github.com/steveyegge/beads"
    read -p "Install now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installing beads..."
        # Use the same installation command as Dockerfile
        if curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash; then
            # Add Go bin to PATH for current session if not already there
            export PATH="$HOME/go/bin:$PATH"
            if command -v bd &> /dev/null; then
                print_success "beads installed successfully"
            else
                print_error "beads installation failed - bd command not found"
                echo "You may need to add ~/go/bin to your PATH"
                exit 1
            fi
        else
            print_error "beads installation failed"
            exit 1
        fi
    else
        print_error "beads (bd) required for persistent task memory"
        exit 1
    fi
fi

# Check if Docker is running
if ! docker ps &> /dev/null; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi
print_success "Docker is running"

# Skip confirmation in update mode
if [ "$UPDATE_MODE" = false ]; then
    echo ""
    read -p "Continue with setup? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Setup cancelled"
        exit 0
    fi
fi

# Setup components
print_header "Setting Up Components"

components=(
    "slack-notifier:Slack Notifier (Claude → You)"
    "slack-receiver:Slack Receiver (You → Claude)"
    "context-sync:Context Sync (Confluence, JIRA → Local)"
    "github-sync:GitHub Sync (PR data → Local)"
    "service-monitor:Service Failure Monitor"
    "worktree-watcher:Worktree Watcher (cleanup orphaned worktrees)"
    "codebase-analyzer:Codebase Analyzer (weekly)"
    "conversation-analyzer:Conversation Analyzer (daily)"
)

for component_info in "${components[@]}"; do
    IFS=: read -r component description <<< "$component_info"

    echo ""
    print_info "Setting up: $description"

    setup_script="$SCRIPT_DIR/components/$component/setup.sh"

    if [ ! -f "$setup_script" ]; then
        print_warning "Setup script not found: $setup_script"
        continue
    fi

    cd "$SCRIPT_DIR/components/$component"

    if bash setup.sh; then
        print_success "$description configured"
    else
        print_error "$description setup failed"
        exit 1
    fi
done

# Reload systemd to pick up any changes
print_header "Finalizing Setup"
systemctl --user daemon-reload
print_success "Systemd daemon reloaded"

# Restart services if in update mode
if [ "$UPDATE_MODE" = true ]; then
    echo ""
    print_info "Restarting services to pick up changes..."

    services_to_restart=(
        "slack-notifier.service"
        "slack-receiver.service"
        "context-sync.timer"
        "github-sync.timer"
        "worktree-watcher.timer"
        "codebase-analyzer.timer"
        "conversation-analyzer.timer"
    )

    for service in "${services_to_restart[@]}"; do
        if systemctl --user is-active --quiet "$service" 2>/dev/null; then
            echo -n "  Restarting $service... "
            if systemctl --user restart "$service" 2>/dev/null; then
                print_success "done"
            else
                print_warning "failed (may not be enabled)"
            fi
        elif systemctl --user is-enabled --quiet "$service" 2>/dev/null; then
            echo -n "  Starting $service... "
            if systemctl --user start "$service" 2>/dev/null; then
                print_success "done"
            else
                print_warning "failed"
            fi
        fi
    done

    echo ""
    print_success "All services restarted/reloaded"
fi

# Summary of services
print_header "Service Status"

services=(
    "slack-notifier.service:Slack Notifier"
    "slack-receiver.service:Slack Receiver"
    "context-sync.timer:Context Sync"
    "github-sync.timer:GitHub Sync"
    "worktree-watcher.timer:Worktree Watcher"
    "codebase-analyzer.timer:Codebase Analyzer"
    "conversation-analyzer.timer:Conversation Analyzer"
)

echo "Active services:"
for service_info in "${services[@]}"; do
    IFS=: read -r service description <<< "$service_info"

    if systemctl --user is-active --quiet "$service"; then
        print_success "$description is running"
    else
        print_warning "$description is not running"
        echo "   Start with: systemctl --user start $service"
    fi
done

echo ""
echo "Enabled services:"
for service_info in "${services[@]}"; do
    IFS=: read -r service description <<< "$service_info"

    if systemctl --user is-enabled --quiet "$service" 2>/dev/null; then
        print_success "$description will start on boot"
    else
        print_info "$description not enabled for auto-start"
    fi
done

# Check for Slack configuration
print_header "Configuration Status"

config_file="$HOME/.config/jib-notifier/config.json"
if [ -f "$config_file" ]; then
    print_success "Slack configuration found: $config_file"

    # Check if tokens are set
    if grep -q "\"slack_token\": \"xoxb-" "$config_file" 2>/dev/null; then
        print_success "Bot token configured"
    else
        print_warning "Bot token not configured"
    fi

    if grep -q "\"slack_app_token\": \"xapp-" "$config_file" 2>/dev/null; then
        print_success "App token configured"
    else
        print_warning "App token not configured"
    fi
else
    print_warning "Slack configuration not found"
    echo "   Configure with your Slack tokens in: $config_file"
fi

# Check for shared directories
print_info "Checking shared directories..."

shared_dir="$HOME/.jib-sharing"
if [ -d "$shared_dir" ]; then
    print_success "Shared directory exists: $shared_dir"
else
    print_info "Creating shared directory: $shared_dir"
    mkdir -p "$shared_dir"/{notifications,incoming,responses,context}
    print_success "Shared directory created"
fi

# Initialize Beads persistent memory system
print_info "Setting up Beads persistent memory system..."

beads_dir="$shared_dir/beads"
if [ -f "$beads_dir/.beads/issues.jsonl" ]; then
    print_success "Beads already initialized: $beads_dir"
else
    print_info "Initializing Beads repository..."
    mkdir -p "$beads_dir"
    cd "$beads_dir"

    # Initialize git repo (required by beads)
    if git init; then
        # Initialize beads (allow user input for git hooks prompt)
        if bd init; then
            # Build SQLite cache for fast queries
            bd build-cache || true
            print_success "Beads initialized: $beads_dir"
            echo "   Usage in container: bd add 'task description' --tags feature"
        else
            print_error "Failed to initialize beads"
            exit 1
        fi
    else
        print_error "Failed to initialize git repository for beads"
        exit 1
    fi

    # Return to script directory
    cd "$SCRIPT_DIR"
fi

# Container setup info
print_header "Next Steps"

if [ "$UPDATE_MODE" = true ]; then
    echo "Update complete! Services have been reloaded and restarted."
    echo ""
    echo "What was updated:"
    echo "  ✓ Service files re-symlinked (picks up any changes)"
    echo "  ✓ Systemd daemon reloaded"
    echo "  ✓ All services restarted"
    echo ""
    echo "To verify:"
    echo "  systemctl --user status slack-notifier.service"
    echo "  systemctl --user list-timers | grep -E 'conversation|codebase|worktree'"
    echo ""
else
    echo "Host setup complete! Next steps:"
    echo ""
    echo "1. Configure Slack tokens (if not done):"
    echo "   Edit: ~/.config/jib-notifier/config.json"
    echo "   Add your Slack bot token (xoxb-...) and app token (xapp-...)"
    echo ""
    echo "2. Start the JIB container:"
    echo "   cd $SCRIPT_DIR"
    echo "   bin/jib"
    echo ""
    echo "3. Test Slack integration:"
    echo "   Send a DM to your Slack bot"
    echo ""
    echo "4. Monitor services:"
    echo "   systemctl --user status slack-notifier.service"
    echo "   systemctl --user list-timers | grep -E 'conversation|codebase|worktree'"
    echo ""
    echo "5. View logs:"
    echo "   journalctl --user -u slack-notifier.service -f"
    echo "   journalctl --user -u slack-receiver.service -f"
    echo ""
fi

print_header "Useful Commands"
echo "Update JIB (reload configs and restart services):"
echo "  cd $SCRIPT_DIR && ./setup.sh --update"
echo ""
echo "Check all services:"
echo "  systemctl --user status slack-notifier slack-receiver"
echo "  systemctl --user list-timers"
echo ""
echo "Restart a service:"
echo "  systemctl --user restart slack-notifier.service"
echo ""
echo "View logs:"
echo "  journalctl --user -u <service-name> -f"
echo ""
echo "Start container:"
echo "  bin/jib"
echo ""

if [ "$UPDATE_MODE" = true ]; then
    print_success "Update complete!"
else
    print_success "Setup complete!"
fi
