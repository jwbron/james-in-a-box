#!/bin/bash
# Quick Setup Script for Host-Side Slack Notifier
# Checks dependencies and helps configure the system

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

check_mark() {
    echo -e "${GREEN}✓${NC} $1"
}

cross_mark() {
    echo -e "${RED}✗${NC} $1"
}

warn_mark() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_header "Claude Sandbox Host Notifier - Setup"

echo "This script will check your system and help set up the Slack notifier."
echo ""

# Check OS
print_header "System Check"

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    check_mark "Running on Linux"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    warn_mark "Running on macOS - script may need modifications (uses fswatch instead of inotifywait)"
else
    cross_mark "Unknown OS: $OSTYPE"
    exit 1
fi

# Check dependencies
print_header "Dependency Check"

MISSING_DEPS=()

if command -v inotifywait &> /dev/null; then
    check_mark "inotifywait is installed"
else
    cross_mark "inotifywait is NOT installed"
    MISSING_DEPS+=("inotify-tools")
fi

if command -v jq &> /dev/null; then
    check_mark "jq is installed"
else
    cross_mark "jq is NOT installed"
    MISSING_DEPS+=("jq")
fi

if command -v curl &> /dev/null; then
    check_mark "curl is installed"
else
    cross_mark "curl is NOT installed"
    MISSING_DEPS+=("curl")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}Missing dependencies!${NC}"
    echo ""
    echo "To install on Fedora/RHEL:"
    echo -e "  ${YELLOW}sudo dnf install ${MISSING_DEPS[*]}${NC}"
    echo ""
    echo "To install on Ubuntu/Debian:"
    echo -e "  ${YELLOW}sudo apt install ${MISSING_DEPS[*]}${NC}"
    echo ""
    exit 1
fi

# Check directories
print_header "Directory Check"

DIRS=(
    "${HOME}/.jib-sharing"
    "${HOME}/.jib-tools"
)

for dir in "${DIRS[@]}"; do
    if [ -d "$dir" ]; then
        check_mark "$dir exists"
    else
        warn_mark "$dir does not exist yet (will be created when container starts)"
    fi
done

# Check Slack token
print_header "Slack Configuration"

if [ -n "${SLACK_TOKEN:-}" ]; then
    check_mark "SLACK_TOKEN environment variable is set"
    echo -e "  Value: ${SLACK_TOKEN:0:10}...${SLACK_TOKEN: -5}"
else
    cross_mark "SLACK_TOKEN environment variable is NOT set"
    echo ""
    echo "You need to set your Slack bot token:"
    echo ""
    echo "1. Get a token from: https://api.slack.com/apps"
    echo "   - Create a new app or select existing"
    echo "   - Go to 'OAuth & Permissions'"
    echo "   - Add scope: chat:write"
    echo "   - Install app to workspace"
    echo "   - Copy the 'Bot User OAuth Token' (starts with xoxb-)"
    echo ""
    echo "2. Set the environment variable:"
    echo -e "   ${YELLOW}export SLACK_TOKEN=\"xoxb-your-token-here\"${NC}"
    echo ""
    echo "3. Make it permanent by adding to ~/.bashrc:"
    echo -e "   ${YELLOW}echo 'export SLACK_TOKEN=\"xoxb-your-token-here\"' >> ~/.bashrc${NC}"
    echo ""
    exit 1
fi

# Check scripts
print_header "Script Check"

SCRIPT_DIR="${HOME}/khan/james-in-a-box/scripts"

if [ -f "$SCRIPT_DIR/host-notify-slack.sh" ]; then
    check_mark "host-notify-slack.sh exists"
    if [ -x "$SCRIPT_DIR/host-notify-slack.sh" ]; then
        check_mark "host-notify-slack.sh is executable"
    else
        warn_mark "host-notify-slack.sh is not executable"
        chmod +x "$SCRIPT_DIR/host-notify-slack.sh"
        check_mark "Made executable"
    fi
else
    cross_mark "host-notify-slack.sh not found at $SCRIPT_DIR"
    exit 1
fi

if [ -f "$SCRIPT_DIR/host-notify-ctl.sh" ]; then
    check_mark "host-notify-ctl.sh exists"
    if [ -x "$SCRIPT_DIR/host-notify-ctl.sh" ]; then
        check_mark "host-notify-ctl.sh is executable"
    else
        warn_mark "host-notify-ctl.sh is not executable"
        chmod +x "$SCRIPT_DIR/host-notify-ctl.sh"
        check_mark "Made executable"
    fi
else
    cross_mark "host-notify-ctl.sh not found at $SCRIPT_DIR"
    exit 1
fi

# Test Slack connection
print_header "Slack Connection Test"

echo "Testing Slack API connection..."

RESPONSE=$(curl -s -X POST https://slack.com/api/auth.test \
    -H "Authorization: Bearer $SLACK_TOKEN")

OK=$(echo "$RESPONSE" | jq -r '.ok')

if [ "$OK" = "true" ]; then
    check_mark "Slack authentication successful"
    BOT_USER=$(echo "$RESPONSE" | jq -r '.user')
    TEAM=$(echo "$RESPONSE" | jq -r '.team')
    echo -e "  Bot user: ${GREEN}$BOT_USER${NC}"
    echo -e "  Team: ${GREEN}$TEAM${NC}"
else
    ERROR=$(echo "$RESPONSE" | jq -r '.error')
    cross_mark "Slack authentication failed: $ERROR"
    echo ""
    echo "Please check your SLACK_TOKEN and try again."
    exit 1
fi

# All checks passed
print_header "Setup Complete!"

echo -e "${GREEN}All checks passed!${NC} You're ready to use the host notifier."
echo ""
echo "Next steps:"
echo ""
echo "1. Start the notifier:"
echo -e "   ${YELLOW}~/khan/james-in-a-box/scripts/host-notify-ctl.sh start${NC}"
echo ""
echo "2. Check status:"
echo -e "   ${YELLOW}~/khan/james-in-a-box/scripts/host-notify-ctl.sh status${NC}"
echo ""
echo "3. Test by creating a file:"
echo -e "   ${YELLOW}mkdir -p ~/.jib-sharing${NC}"
echo -e "   ${YELLOW}echo 'test' > ~/.jib-sharing/test.txt${NC}"
echo ""
echo "4. Wait 30 seconds and check your Slack DM from the bot"
echo ""
echo "5. View logs:"
echo -e "   ${YELLOW}~/khan/james-in-a-box/scripts/host-notify-ctl.sh tail${NC}"
echo ""
echo "For more information, see:"
echo -e "   ${BLUE}~/khan/james-in-a-box/HOST-SLACK-NOTIFIER.md${NC}"
echo ""
