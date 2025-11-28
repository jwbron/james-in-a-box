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
        "github-watcher.timer"
        "worktree-watcher.timer"
        "codebase-analyzer.timer"
        "conversation-analyzer.timer"
    )

    for service in "${services[@]}"; do
        if is_service_installed "$service"; then
            installed_count=$((installed_count + 1))
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

print_header "james-in-a-box Host Setup"

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
        print_success "jib is already installed!"
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
    echo "  • Clean up any broken symlinks in systemd user directory"
    echo "  • Re-symlink all service files (pick up changes)"
    echo "  • Reload systemd daemon"
    echo "  • Restart all jib services"
    echo ""
else
    echo "This script will:"
    echo "  • Install and configure Slack integration (notifier and receiver)"
    echo "  • Set up automated analyzers (codebase and conversation)"
    echo "  • Configure worktree cleanup"
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
        missing_deps=$((missing_deps + 1))
    fi
done

if [ $missing_deps -gt 0 ]; then
    print_error "Missing required dependencies. Please install them first."
    exit 1
fi

# Check and install uv - Python package manager
print_info "Checking for uv..."
if command -v uv &> /dev/null; then
    print_success "uv found"
else
    print_warning "uv not found"
    echo "Install from: https://docs.astral.sh/uv/"
    read -p "Install now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installing uv..."
        if curl -LsSf https://astral.sh/uv/install.sh | sh; then
            # Add uv to PATH for current session
            export PATH="$HOME/.local/bin:$PATH"
            if command -v uv &> /dev/null; then
                print_success "uv installed successfully"
            else
                print_error "uv installation failed - uv command not found"
                echo "You may need to add ~/.local/bin to your PATH"
                exit 1
            fi
        else
            print_error "uv installation failed"
            exit 1
        fi
    else
        print_error "uv is required for Python dependency management"
        exit 1
    fi
fi

# Set up host-services Python virtual environment
print_info "Setting up host-services Python environment..."
host_services_dir="$SCRIPT_DIR/host-services"
if [ -f "$host_services_dir/.venv/bin/python" ]; then
    print_success "host-services venv exists"
    # Sync dependencies in case pyproject.toml changed
    print_info "Syncing dependencies..."
    cd "$host_services_dir"
    if uv sync; then
        print_success "Dependencies synced"
    else
        print_warning "uv sync failed, trying fresh install..."
        rm -rf .venv
        uv sync
        print_success "Fresh venv created and synced"
    fi
    cd "$SCRIPT_DIR"
else
    print_info "Creating host-services venv with uv..."
    cd "$host_services_dir"
    if uv sync; then
        print_success "host-services venv created and dependencies installed"
    else
        print_error "Failed to create host-services venv"
        exit 1
    fi
    cd "$SCRIPT_DIR"
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

# Clean up broken symlinks in update mode
if [ "$UPDATE_MODE" = true ]; then
    print_info "Cleaning up broken symlinks in systemd user directory..."

    systemd_dir="$HOME/.config/systemd/user"
    broken_count=0

    # Find and remove broken symlinks
    while IFS= read -r -d '' symlink; do
        if [ ! -e "$symlink" ]; then
            service_name=$(basename "$symlink")
            # Only remove jib-related services (safety check)
            if [[ "$service_name" =~ (slack|github|context|codebase|conversation|worktree) ]]; then
                print_info "Removing broken symlink: $service_name"
                rm -f "$symlink"
                broken_count=$((broken_count + 1))
            fi
        fi
    done < <(find "$systemd_dir" -maxdepth 1 -type l -print0 2>/dev/null)

    if [ $broken_count -gt 0 ]; then
        print_success "Removed $broken_count broken symlink(s)"
    else
        print_success "No broken symlinks found"
    fi

    echo ""
fi

# Setup components
print_header "Setting Up Components"

# Component descriptions for pretty output
declare -A component_descriptions=(
    ["slack-notifier"]="Slack Notifier (Claude → You)"
    ["slack-receiver"]="Slack Receiver (You → Claude)"
    ["context-sync"]="Context Sync (Confluence, JIRA → Local)"
    ["github-watcher"]="GitHub Watcher (PR/issue monitoring)"
    ["worktree-watcher"]="Worktree Watcher (cleanup orphaned worktrees)"
    ["codebase-analyzer"]="Codebase Analyzer (weekly)"
    ["conversation-analyzer"]="Conversation Analyzer (daily)"
)

# Desired installation order (optional components will be skipped if not found)
component_order=(
    "slack/slack-notifier"
    "slack/slack-receiver"
    "sync/context-sync"
    "analysis/github-watcher"
    "utilities/worktree-watcher"
    "analysis/codebase-analyzer"
    "analysis/conversation-analyzer"
)

# Find all setup scripts dynamically as a fallback
# This ensures we catch any new components even if not in the order list
mapfile -t all_setup_scripts < <(find "$SCRIPT_DIR/host-services" -name "setup.sh" -type f | sort)

# Process components in preferred order first
for component_path in "${component_order[@]}"; do
    component_name=$(basename "$component_path")
    setup_script="$SCRIPT_DIR/host-services/$component_path/setup.sh"

    if [ ! -f "$setup_script" ]; then
        print_warning "Setup script not found (skipping): $component_path"
        continue
    fi

    description="${component_descriptions[$component_name]:-$component_name}"

    echo ""
    print_info "Setting up: $description"

    component_dir=$(dirname "$setup_script")
    cd "$component_dir"

    if bash setup.sh; then
        print_success "$description configured"
    else
        print_error "$description setup failed"
        exit 1
    fi
done

# Process any components not in the order list (newly added components)
for setup_script in "${all_setup_scripts[@]}"; do
    component_dir=$(dirname "$setup_script")
    component_name=$(basename "$component_dir")

    # Check if this component was already processed
    already_processed=false
    for ordered_path in "${component_order[@]}"; do
        if [[ "$setup_script" == *"$ordered_path/setup.sh" ]]; then
            already_processed=true
            break
        fi
    done

    if [ "$already_processed" = true ]; then
        continue
    fi

    description="${component_descriptions[$component_name]:-$component_name}"

    echo ""
    print_info "Setting up: $description (newly discovered)"

    cd "$component_dir"

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
        "github-watcher.timer"
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
    "github-watcher.timer:GitHub Watcher"
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

jib_config_dir="$HOME/.config/jib"
jib_secrets_file="$jib_config_dir/secrets.env"
jib_repos_file="$jib_config_dir/repositories.yaml"

# Check for legacy configs that need migration
legacy_notifier="$HOME/.config/jib-notifier/config.json"
legacy_context_sync="$HOME/.config/context-sync/.env"

if [ -f "$legacy_notifier" ] || [ -f "$legacy_context_sync" ]; then
    if [ ! -f "$jib_secrets_file" ]; then
        print_warning "Legacy configs found - migration required!"
        echo "   Run: python3 $SCRIPT_DIR/config/host_config.py --migrate"
        echo ""
    fi
fi

# Check consolidated config
if [ -f "$jib_secrets_file" ]; then
    print_success "Config directory: $jib_config_dir/"

    # Check if tokens are set
    if grep -q "^SLACK_TOKEN=\"xoxb-" "$jib_secrets_file" 2>/dev/null; then
        print_success "Slack bot token configured"
    else
        print_warning "Slack bot token not configured"
    fi

    if grep -q "^SLACK_APP_TOKEN=\"xapp-" "$jib_secrets_file" 2>/dev/null; then
        print_success "Slack app token configured"
    else
        print_warning "Slack app token not configured"
    fi

    # Check GitHub token (PAT fallback when GitHub App not configured)
    if grep -q "^GITHUB_TOKEN=\"gh" "$jib_secrets_file" 2>/dev/null; then
        print_success "GitHub PAT configured (fallback for GitHub App)"
    else
        # Check if GitHub App is configured (primary method)
        if [ -f "$jib_config_dir/github-app-id" ] && [ -f "$jib_config_dir/github-app-installation-id" ] && [ -f "$jib_config_dir/github-app.pem" ]; then
            print_info "GitHub auth: App configured (GITHUB_TOKEN generated dynamically)"
        else
            print_warning "GitHub auth: Not configured"
            echo "   Container will not be able to push code or use GitHub MCP"
            echo "   Configure either:"
            echo "     1. GitHub App (recommended): Run setup.sh and follow prompts"
            echo "     2. Personal Access Token: Add GITHUB_TOKEN to $jib_secrets_file"
        fi
    fi
else
    print_warning "No configuration found"
    echo "   Configure secrets in: $jib_secrets_file"
    echo "   Templates available in: $SCRIPT_DIR/config/"
fi

# Copy repositories.yaml to host config if not present
if [ ! -f "$jib_repos_file" ]; then
    if [ -f "$SCRIPT_DIR/config/repositories.yaml" ]; then
        print_info "Copying repositories.yaml to host config..."
        mkdir -p "$jib_config_dir"
        cp "$SCRIPT_DIR/config/repositories.yaml" "$jib_repos_file"
        print_success "Copied repositories.yaml to $jib_repos_file"
    fi
else
    print_success "repositories.yaml found"
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
            print_success "Beads initialized: $beads_dir"
            echo "   Usage in container: bd --allow-stale create 'task description' --labels feature"
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

# Configure GitHub username
print_info "Configuring GitHub username..."

repo_config_file="$SCRIPT_DIR/config/repositories.yaml"
current_username=""

# Try to get current username from config
if [ -f "$repo_config_file" ]; then
    current_username=$(grep "^github_username:" "$repo_config_file" | sed 's/github_username: *//' | tr -d '"' | tr -d "'")
fi

# Try to detect from gh CLI if not set
if [ -z "$current_username" ] && command -v gh &> /dev/null; then
    detected_username=$(gh api user --jq '.login' 2>/dev/null || true)
    if [ -n "$detected_username" ]; then
        current_username="$detected_username"
        print_info "Detected GitHub username from gh CLI: $current_username"
    fi
fi

if [ -n "$current_username" ]; then
    echo "Current GitHub username: $current_username"
    read -p "Keep this username? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        current_username=""
    fi
fi

if [ -z "$current_username" ]; then
    echo ""
    echo "Enter your GitHub username (used for PR creation and review requests):"
    read -p "GitHub username: " github_username
    if [ -z "$github_username" ]; then
        print_error "GitHub username is required"
        exit 1
    fi
    current_username="$github_username"
fi

# Update repositories.yaml with the username
if [ -f "$repo_config_file" ]; then
    # Update github_username
    sed -i "s/^github_username:.*/github_username: $current_username/" "$repo_config_file"
    # Update default_reviewer
    sed -i "s/^default_reviewer:.*/default_reviewer: $current_username/" "$repo_config_file"
    # Update writable_repos (the james-in-a-box repo)
    sed -i "s|  - .*/james-in-a-box|  - $current_username/james-in-a-box|" "$repo_config_file"
    print_success "Updated repositories.yaml with username: $current_username"
else
    print_warning "repositories.yaml not found, skipping config update"
fi

# GitHub App configuration (required for container GitHub access)
print_info "Checking GitHub App configuration..."

jib_user_config_dir="$HOME/.config/jib"
github_app_id_file="$jib_user_config_dir/github-app-id"
github_app_installation_file="$jib_user_config_dir/github-app-installation-id"
github_app_pem_file="$jib_user_config_dir/github-app.pem"

mkdir -p "$jib_user_config_dir"
chmod 700 "$jib_user_config_dir"

if [ -f "$github_app_id_file" ] && [ -f "$github_app_installation_file" ] && [ -f "$github_app_pem_file" ]; then
    print_success "GitHub App configured"
    echo "   App ID: $(cat "$github_app_id_file")"
    echo "   Installation ID: $(cat "$github_app_installation_file")"
    echo "   Private key: $github_app_pem_file"
else
    echo ""
    print_warning "GitHub App not configured"
    echo ""
    echo "A GitHub App is required for container GitHub access."
    echo ""
    echo "Benefits of GitHub App:"
    echo "  • Full GitHub API access (PRs, issues, checks)"
    echo "  • Query CI/CD workflow status (pass/fail)"
    echo "  • Granular permissions (can request only what's needed)"
    echo "  • Higher API rate limits"
    echo ""
    read -p "Set up GitHub App now? (y/n) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "GitHub App Setup"
        echo "================"
        echo ""
        echo "If you haven't created a GitHub App yet:"
        echo "  1. Go to: https://github.com/settings/apps/new"
        echo "  2. Name: james-in-a-box (or similar)"
        echo "  3. Homepage URL: https://github.com/$current_username/james-in-a-box"
        echo "  4. Uncheck 'Webhook Active' (unless setting up webhooks)"
        echo "  5. Permissions → Repository:"
        echo "     - Checks: Read-only"
        echo "     - Contents: Read and write"
        echo "     - Pull requests: Read and write"
        echo "     - Commit statuses: Read-only"
        echo "  6. Click 'Create GitHub App'"
        echo "  7. Note the App ID shown on the next page"
        echo "  8. Scroll down and click 'Generate a private key' (downloads .pem file)"
        echo "  9. Go to 'Install App' in left sidebar → Install on your account"
        echo "     - Select 'Only select repositories' → choose james-in-a-box"
        echo "  10. Note the Installation ID from the URL after installation"
        echo "      (URL will be: github.com/settings/installations/XXXXX)"
        echo ""

        # Get App ID
        read -p "Enter App ID (numeric): " app_id
        if [[ ! "$app_id" =~ ^[0-9]+$ ]]; then
            print_error "Invalid App ID (must be numeric)"
        else
            echo "$app_id" > "$github_app_id_file"
            print_success "App ID saved"

            # Get Installation ID
            read -p "Enter Installation ID (numeric): " installation_id
            if [[ ! "$installation_id" =~ ^[0-9]+$ ]]; then
                print_error "Invalid Installation ID (must be numeric)"
                rm -f "$github_app_id_file"
            else
                echo "$installation_id" > "$github_app_installation_file"
                print_success "Installation ID saved"

                # Get Private Key
                echo ""
                echo "Enter the path to your private key .pem file"
                echo "(downloaded when you clicked 'Generate a private key')"
                read -p "Path to .pem file: " pem_path

                # Expand ~ and check file
                pem_path="${pem_path/#\~/$HOME}"

                if [ -f "$pem_path" ]; then
                    cp "$pem_path" "$github_app_pem_file"
                    chmod 600 "$github_app_pem_file"
                    print_success "Private key copied to $github_app_pem_file"

                    # Test token generation
                    echo ""
                    print_info "Testing GitHub App token generation..."
                    token_script="$SCRIPT_DIR/jib-container/jib-tools/github-app-token.py"
                    # Use the host-services venv Python which has cryptography installed
                    venv_python="$SCRIPT_DIR/host-services/.venv/bin/python"

                    if [ -f "$token_script" ]; then
                        if token_output=$("$venv_python" "$token_script" --config-dir "$jib_user_config_dir" 2>&1); then
                            if [[ "$token_output" == ghs_* ]] || [ -n "$token_output" ]; then
                                print_success "GitHub App token generation works!"
                                echo "   Container will use App authentication for full API access"
                            else
                                print_warning "Token generation returned unexpected output"
                                echo "   Output: $token_output"
                            fi
                        else
                            print_error "Token generation failed"
                            echo "   Error: $token_output"
                            echo ""
                            echo "   Check that:"
                            echo "   - App ID and Installation ID are correct"
                            echo "   - Private key matches the App"
                            echo "   - App is installed on your repository"
                        fi
                    else
                        print_warning "Token script not found, skipping test"
                        echo "   Script should be at: $token_script"
                    fi
                else
                    print_error "Private key file not found: $pem_path"
                    rm -f "$github_app_id_file" "$github_app_installation_file"
                fi
            fi
        fi
    else
        print_warning "Skipping GitHub App setup"
        echo ""
        echo "   To enable GitHub access, choose one option:"
        echo "   Option 1: Run setup.sh again and configure GitHub App (recommended)"
        echo "   Option 2: Add GITHUB_TOKEN to ~/.config/jib/secrets.env"
        echo "             Create a fine-grained PAT at https://github.com/settings/tokens?type=beta"
        echo "             Required scopes: Contents (R/W), Pull requests (R/W)"
    fi
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
    echo "1. Configure secrets (if not done):"
    echo "   Copy template:  cp $SCRIPT_DIR/config/secrets.template.env ~/.config/jib/secrets.env"
    echo "   Edit secrets:   ~/.config/jib/secrets.env"
    echo "   Add your Slack bot token (xoxb-...) and app token (xapp-...)"
    echo ""
    echo "   For GitHub access (if you skipped GitHub App setup):"
    echo "   Add GITHUB_TOKEN with a fine-grained PAT (ghp_... or github_pat_...)"
    echo "   Required scopes: Contents (R/W), Pull requests (R/W)"
    echo ""
    echo "   Or migrate from legacy config:"
    echo "   python3 $SCRIPT_DIR/config/host_config.py --migrate"
    echo ""
    echo "2. Start the jib container:"
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
echo "Update jib (reload configs and restart services):"
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
