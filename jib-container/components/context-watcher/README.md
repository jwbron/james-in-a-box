# Context Watcher

Proactively monitors and analyzes Confluence and JIRA updates.

**Status**: Operational
**Type**: Container component (runs inside Docker)
**Purpose**: Detect, analyze, and notify about JIRA tickets and Confluence doc changes

## Overview

Context Watcher consists of two active monitoring components that run every 5 minutes:

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

Both components work similarly to github-watcher: they analyze synced data and send proactive notifications.

## How It Works

```
Host context-sync (hourly)
        ↓
~/context-sync/jira/ and ~/context-sync/confluence/
        ↓
Enhanced Context Watcher (every 5 min in container)
        ↓
JIRA Watcher:
  - Detects new/updated tickets
  - Parses metadata, description, acceptance criteria
  - Analyzes scope and action items
  - Creates Beads task
  - Sends notification
        ↓
Confluence Watcher:
  - Detects new/updated docs (especially ADRs)
  - Summarizes changes
  - Identifies impact
  - Flags action items
  - Sends notification
        ↓
Slack notifications with summaries and next steps
```

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

The enhanced watcher starts automatically on container startup. Manual control:

```bash
# Inside container
cd ~/khan/james-in-a-box/jib-container/components/context-watcher

# Control enhanced watcher (JIRA + Confluence)
./enhanced-watcher-ctl start
./enhanced-watcher-ctl stop
./enhanced-watcher-ctl status
./enhanced-watcher-ctl restart

# View logs
tail -f ~/sharing/tracking/enhanced-context-watcher.log

# Check state files
cat ~/sharing/tracking/jira-watcher-state.json
cat ~/sharing/tracking/confluence-watcher-state.json
```

## Configuration

See `config/README.md` for filtering options and watch patterns.

## Files

- `context-watcher-ctl` - Control script (start/stop/status)
- `context-watcher.sh` - Main watcher script
- `config/` - Configuration files

## Troubleshooting

**Watcher not starting**:
```bash
# Check if running
ps aux | grep context-watcher

# Check logs
cat ~/sharing/tracking/watcher.log

# Restart
./context-watcher-ctl restart
```

**Directory not found**:
- Ensure `~/context-sync/` is mounted from host
- Check Docker volume mounts in `jib` script
