# Internal Automation Scripts

Internal scripts used by services and automation. Not intended for direct user invocation.

## Scripts

### codebase-analyzer.py
Analyzes codebase for improvements using Claude Code CLI.

**Used by:** `systemd/analyzers/codebase-analyzer.service`  
**Invoked via:** `bin/analyzer-ctl`

### context-watcher.sh
Monitors context directories and triggers Claude analysis.

**Used by:** `bin/context-watcher-ctl`  
**Purpose:** Auto-analyze new context files

### host-notify-slack.py
Python implementation of Slack notifier.

**Used by:** `systemd/slack-notifier/slack-notifier.service`  
**Purpose:** Send notifications to Slack

### host-notify-slack.sh
Shell wrapper for Slack notifier.

**Used by:** `host-notify-slack.py`  
**Purpose:** Process and format notifications

### host-receive-slack.py
Receives messages from Slack.

**Used by:** `bin/host-receive-ctl`  
**Purpose:** Handle incoming Slack messages

### incoming-watcher.sh
Watches for incoming tasks from Slack.

**Used by:** Slack integration  
**Purpose:** Monitor `~/sharing/incoming/` for new tasks

### test-context-watcher.sh
Tests context watcher functionality.

**Usage:** Development and debugging only  
**Purpose:** Verify context watcher works correctly

## Note

These scripts are implementation details. Use the CLI tools in `bin/` or systemd services instead.

## See Also
- [CLI Tools](../bin/)
- [Systemd Services](../systemd/)
