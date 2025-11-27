# Archived Connectors

This directory contains deprecated connectors that have been replaced by MCP servers.

## JIRA Connector (Deprecated November 2025)

**Replaced by**: Atlassian MCP Server

**Migration Details**: See [ADR-Context-Sync-Strategy-Custom-vs-MCP](../../../../docs/adr/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)

**Why Deprecated**:
- File-based sync had up to 60-minute latency
- One-way only (could not update tickets)
- ~636 lines of custom code to maintain

**New Approach**:
- Real-time access via Atlassian MCP server
- Bi-directional: read, search, update, comment, transition
- OAuth 2.1 authentication with user-scoped permissions
- Maintained by Atlassian

**To Re-enable (if needed)**:
1. Move `jira/` back to `../jira/`
2. Add import in `context-sync.py`
3. Add connector initialization in `get_all_connectors()`
4. Add processor back to `context-sync.service`

Note: This is NOT recommended. MCP provides better functionality.
