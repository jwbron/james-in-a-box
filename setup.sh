#!/bin/bash
# Master setup script for james-in-a-box host components
set -e

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

# Check if running on host (not in container)
if [ -f "/.dockerenv" ]; then
    print_error "This script must be run on the host machine, not inside the container"
    exit 1
fi

print_header "James-In-A-Box Host Setup"

echo "This script will:"
echo "  • Install and configure Slack integration (notifier and receiver)"
echo "  • Set up automated analyzers (codebase and conversation)"
echo "  • Configure service failure monitoring"
echo "  • Enable and start all systemd services"
echo ""

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

# Check if Docker is running
if ! docker ps &> /dev/null; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi
print_success "Docker is running"

echo ""
read -p "Continue with setup? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Setup cancelled"
    exit 0
fi

# Setup components
print_header "Setting Up Components"

components=(
    "slack-notifier:Slack Notifier (Claude → You)"
    "slack-receiver:Slack Receiver (You → Claude)"
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

# Summary of services
print_header "Service Status"

services=(
    "slack-notifier.service:Slack Notifier"
    "slack-receiver.service:Slack Receiver"
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

# Container setup info
print_header "Next Steps"

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
echo "   systemctl --user list-timers | grep -E 'conversation|codebase'"
echo ""
echo "5. View logs:"
echo "   journalctl --user -u slack-notifier.service -f"
echo "   journalctl --user -u slack-receiver.service -f"
echo ""

print_header "Useful Commands"
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

print_success "Setup complete!"
