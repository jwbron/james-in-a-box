#!/bin/bash
#
# Fix Host Claude Credentials - Force Re-authentication with Correct Scopes
#
# PROBLEM: Host credentials at ~/.claude/.credentials.json are missing the
#          'user:sessions:claude_code' scope required by Claude Code CLI.
#
# SOLUTION: Clear credentials and session cache to force re-authentication
#           with the correct scopes on next Claude Code run.
#
# USAGE: Run this script on the HOST machine (not in container):
#        ./scripts/fix-host-credentials.sh
#

set -euo pipefail

echo "=================================================="
echo "Fix Host Claude Credentials"
echo "=================================================="
echo ""
echo "This script will clear your Claude authentication"
echo "to force re-authentication with correct scopes."
echo ""
echo "Current credential scopes (if exists):"
if [ -f ~/.claude/.credentials.json ]; then
    cat ~/.claude/.credentials.json | jq -r '.claudeAiOauth.scopes | join(", ")' 2>/dev/null || echo "  (unable to parse)"
else
    echo "  (no credentials file found)"
fi
echo ""
echo "Required scopes:"
echo "  - user:inference"
echo "  - user:profile"
echo "  - user:sessions:claude_code  ← often missing"
echo ""
read -p "Continue? This will log you out of Claude Code. [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
fi

echo ""
echo "Step 1: Backing up current credentials..."
if [ -f ~/.claude/.credentials.json ]; then
    cp ~/.claude/.credentials.json ~/.claude/.credentials.json.backup.$(date +%Y%m%d-%H%M%S)
    echo "  ✓ Backed up to ~/.claude/.credentials.json.backup.*"
else
    echo "  ⚠ No credentials file to backup"
fi

echo ""
echo "Step 2: Removing credentials file..."
rm -f ~/.claude/.credentials.json
echo "  ✓ Removed ~/.claude/.credentials.json"

echo ""
echo "Step 3: Clearing session cache..."
if [ -d ~/.claude/session-env ]; then
    rm -rf ~/.claude/session-env/*
    echo "  ✓ Cleared ~/.claude/session-env/"
else
    echo "  ⚠ No session-env directory found"
fi

echo ""
echo "=================================================="
echo "✓ Cleanup Complete!"
echo "=================================================="
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Run Claude Code on the HOST:"
echo "   claude"
echo ""
echo "2. You will be prompted to authenticate in browser"
echo ""
echo "3. After authentication, verify scopes:"
echo "   cat ~/.claude/.credentials.json | jq '.claudeAiOauth.scopes'"
echo ""
echo "4. You should see all three scopes:"
echo "   - user:inference"
echo "   - user:profile"
echo "   - user:sessions:claude_code"
echo ""
echo "5. Once verified, restart the container:"
echo "   cd ~/khan/james-in-a-box"
echo "   ./jib --rebuild"
echo ""
echo "The container will now copy the corrected credentials!"
echo ""
