#!/bin/bash
# Quick test script for context watcher system

set -euo pipefail

echo "=== Context Watcher System Test ==="
echo ""

# Check directories
echo "1. Checking directory access..."
for dir in ~/sharing ~/tools ~/context-sync; do
    if [ -d "$dir" ] && [ -w "$dir" ]; then
        echo "  ✓ $dir is accessible"
    else
        echo "  ✗ $dir is NOT accessible"
    fi
done
echo ""

# Check config
echo "2. Checking configuration..."
if [ -f ~/sharing/config/context-watcher.yaml ]; then
    echo "  ✓ Config file exists"
else
    echo "  ✗ Config file missing - copy from ~/khan/james-in-a-box/context-watcher/config/"
fi
echo ""

# Check scripts
echo "3. Checking scripts..."
for script in ~/khan/james-in-a-box/scripts/context-watcher.sh ~/khan/james-in-a-box/scripts/context-watcher-ctl.sh; do
    if [ -x "$script" ]; then
        echo "  ✓ $(basename $script) is executable"
    else
        echo "  ✗ $(basename $script) is NOT executable"
    fi
done
echo ""

# Check Claude
echo "4. Checking Claude CLI..."
if command -v claude &> /dev/null; then
    version=$(claude --version 2>&1 || echo "unknown")
    echo "  ✓ Claude CLI found: $version"
else
    echo "  ✗ Claude CLI not found"
fi
echo ""

# Check slash command
echo "5. Checking slash command..."
if [ -f ~/.claude/commands/analyze-context-changes.md ]; then
    echo "  ✓ Slash command installed"
else
    echo "  ✗ Slash command missing"
fi
echo ""

# Create test file
echo "6. Creating test file..."
mkdir -p ~/context-sync
cat > ~/context-sync/test-file.md << 'TESTFILE'
# Test File for Context Watcher

Author: Jacob Wiesblatt (@jwies)
Tags: @infra-platform, infrastructure platform

This is a test file to verify the context watcher is working correctly.

## Changes
- Added test content
- Tagged Jacob and infra-platform team
- Should trigger analysis

TESTFILE
echo "  ✓ Created ~/context-sync/test-file.md"
echo ""

# Check watcher status
echo "7. Checking watcher status..."
if ~/khan/james-in-a-box/scripts/context-watcher-ctl.sh status >/dev/null 2>&1; then
    echo "  ✓ Watcher is running"
    ~/khan/james-in-a-box/scripts/context-watcher-ctl.sh status | tail -5
else
    echo "  ℹ Watcher is not running"
    echo "    Start with: ~/khan/james-in-a-box/scripts/context-watcher-ctl.sh start"
fi
echo ""

echo "=== Test Complete ==="
echo ""
echo "Next steps:"
echo "1. If watcher is not running: ~/khan/james-in-a-box/scripts/context-watcher-ctl.sh start"
echo "2. Wait 5-6 minutes for next check cycle (or restart watcher)"
echo "3. Check for outputs: ls -la ~/sharing/notifications/"
echo "4. View summary: cat ~/sharing/notifications/summary-*.md"
echo ""
