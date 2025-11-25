# Context Watcher

Proactively monitors and analyzes Confluence and JIRA updates.

**Status**: Operational
**Type**: Container component (runs inside Docker)
**Purpose**: Detect, analyze, and notify about JIRA tickets and Confluence doc changes

## Overview

Context Watcher consists of two analysis components triggered after context-sync completes:

### 1. JIRA Watcher
- **Detects** new or updated JIRA tickets assigned to you
- **Analyzes** requirements and extracts action items
- **Estimates** scope (small/medium/large)
- **Identifies** dependencies and risks
- **Creates** Beads tasks automatically
- **Sends** Slack notifications with summaries

### 2. Confluence Watcher
- **Monitors** high-value docs (ADRs, runbooks)
- **Detects** new or updated documentation
- **Summarizes** changes and key points
- **Identifies** impact on current work
- **Flags** action items and deprecations
- **Sends** Slack notifications with analysis

Both components use an exec-based pattern: they run once after context-sync completes, analyze the data, and exit. This ensures analysis only happens when new data is available.

## How It Works

```
Host context-sync (hourly via systemd timer)
        ↓
~/context-sync/jira/ and ~/context-sync/confluence/
        ↓
context-sync.service completes → Triggers watchers via `jib --exec`
        ↓
jib Container (one-time analysis):

  jira-watcher.py:
    - Detects new/updated tickets
    - Parses metadata, description, acceptance criteria
    - Analyzes scope and action items
    - Creates Beads task
    - Sends notification
    - Exits

  confluence-watcher.py:
    - Detects new/updated docs (especially ADRs)
    - Summarizes changes
    - Identifies impact
    - Flags action items
    - Sends notification
    - Exits
        ↓
Slack notifications with summaries and next steps
```

This exec-based pattern ensures analysis only runs after context data is synced (event-driven, not continuous polling).

### JIRA Ticket Workflow

```
New ticket assigned: INFRA-12345
        ↓
Parse ticket file:
  - Title, status, priority
  - Description
  - Acceptance criteria
  - Comments
        ↓
Analyze:
  - Extract action items from description
  - Estimate scope (criteria count + description length)
  - Identify dependencies ("depends on", "requires")
  - Flag risks ("concern", "breaking change")
        ↓
Create Beads task: "INFRA-12345: Task title"
        ↓
Send Slack notification:
  📊 Quick Summary
  📄 Description (truncated if long)
  ✅ Acceptance Criteria
  🎯 Extracted Action Items
  🔗 Dependencies/Blockers
  ⚠️ Potential Risks
  📋 Suggested Next Steps
```

### Confluence Doc Workflow

```
New ADR detected: ADR #123
        ↓
Parse document:
  - Title
  - Content summary
  - Key sections
        ↓
Analyze:
  - Extract decision keywords
  - Identify deprecations/migrations
  - Find related technologies
  - Flag action items
        ↓
Create Beads task (if ADR): "Review ADR: {title}"
        ↓
Send Slack notification:
  📝 Summary
  💡 Impact
  🎯 Key Points
  🔧 Related Technologies
  ⚠️ Important Changes
  ⚡ Action Required (if applicable)
  📋 Suggested Next Steps
```

## Management

The watchers are triggered automatically by context-sync.service after each sync. Manual triggering:

```bash
# From host - trigger after context sync
systemctl --user start context-sync.service

# Or trigger watchers directly via jib --exec
cd ~/khan/james-in-a-box
bin/jib --exec python3 ~/khan/james-in-a-box/jib-container/watchers/context-watcher/jira-watcher.py
bin/jib --exec python3 ~/khan/james-in-a-box/jib-container/watchers/context-watcher/confluence-watcher.py

# Inside container - run analysis scripts directly
cd ~/khan/james-in-a-box/jib-container/watchers/context-watcher
python3 jira-watcher.py
python3 confluence-watcher.py

# Check state files
cat ~/sharing/tracking/jira-watcher-state.json
cat ~/sharing/tracking/confluence-watcher-state.json
```

## Configuration

See `config/README.md` for filtering options and watch patterns.

## Files

- `jira-watcher.py` - JIRA ticket analysis script
- `confluence-watcher.py` - Confluence doc analysis script
- `config/` - Configuration files

## Troubleshooting

**Watchers not running**:
```bash
# From host - check if context-sync service is working
systemctl --user status context-sync.service
journalctl --user -u context-sync.service -n 50

# Manually trigger sync + analysis
systemctl --user start context-sync.service

# Or trigger analysis directly
cd ~/khan/james-in-a-box
bin/jib --exec python3 ~/khan/james-in-a-box/jib-container/watchers/context-watcher/jira-watcher.py
```

**Directory not found**:
- Ensure `~/context-sync/` is mounted from host
- Check Docker volume mounts in `jib` script
- Verify context-sync has run at least once

**No notifications sent**:
- Check state files in `~/sharing/tracking/`
- Ensure slack-notifier is running on host
- Verify jib container has write access to `~/sharing/notifications/`
