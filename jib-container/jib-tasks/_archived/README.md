# Archived JIB Tasks

This directory contains deprecated task processors that have been replaced by MCP servers.

## JIRA Processor (Deprecated November 2025)

**Replaced by**: Atlassian MCP Server with real-time access

**Files**:
- `jira/jira-processor.py` - Post-sync JIRA ticket analysis
- `jira/analyze-sprint.py` - Sprint analysis utilities

**Migration Details**: See [ADR-Context-Sync-Strategy-Custom-vs-MCP](../../../docs/adr/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)

**Why Deprecated**:
- Relied on file-based sync (up to 60-minute latency)
- Could not update tickets or add comments
- Required separate analysis pass after sync

**New Approach**:
- Direct JIRA access via Atlassian MCP server tools
- Real-time queries: `jira_search`, `jira_get_issue`
- Bi-directional: `jira_update_issue`, `jira_add_comment`, `jira_transition_issue`
- No separate processor needed - Claude queries JIRA directly when needed

**Reference**: The patterns in these files may be useful for understanding:
- How JIRA ticket analysis was structured
- State tracking for processed items
- Notification generation from ticket data
