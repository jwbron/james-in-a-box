# ADR: Slack Integration Strategy - MCP Server vs Custom Services

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Proposed

## Table of Contents

- [Current Implementation Status](#current-implementation-status)
- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Implementation Details](#implementation-details)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)

## Current Implementation Status

**Custom Slack Integration (Phase 1 - Complete):**
- `host-notify-slack.py` (~567 lines): Watches `~/sharing/notifications/`, sends to Slack
- `host-receive-slack.py` (~764 lines): Socket Mode listener, writes to `~/sharing/incoming/`
- `notifications/` library (~777 lines): Container-side notification helpers
- **Total: ~2,100 lines of custom code**

**Proposed Enhancements:**
- [ADR: Message Queue for Slack Integration](./ADR-Message-Queue-Slack-Integration.md): Replace file-based transport with Cloud Pub/Sub

**Current Architecture:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Container (jib / Claude Code)                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  notifications library                                           │    │
│  │  • slack_notify("title", "body")                                │    │
│  │  • Writes markdown to ~/sharing/notifications/                   │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ file write
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Host Machine                                      │
│  ┌──────────────────────────┐      ┌──────────────────────────────────┐  │
│  │ host-notify-slack.py    │      │ host-receive-slack.py            │  │
│  │ • inotify watcher       │      │ • Socket Mode listener           │  │
│  │ • 15s batch window      │      │ • Writes to ~/sharing/incoming/  │  │
│  │ • Thread management     │      │ • Command handling (/jib, etc.)  │  │
│  └───────────┬──────────────┘      └─────────────┬────────────────────┘  │
│              │                                   │                        │
└──────────────┼───────────────────────────────────┼────────────────────────┘
               │                                   │
               ▼                                   ▼
         Slack API (send)                  Slack API (receive)
```

## Context

### Background

The current Slack integration was designed for **Phase 1 laptop deployment** with these characteristics:
- File-based communication for simplicity and debuggability
- Host-side services handle Slack API interaction
- Container is isolated from direct Slack access (security boundary)

Two related decisions are in progress:
1. **Pub/Sub ADR:** Proposes replacing file-based transport with Cloud Pub/Sub for GCP deployment
2. **MCP Context Sync ADR:** Proposes using MCP servers for Jira/GitHub integration

This ADR evaluates whether **Slack MCP servers** could simplify or replace the current architecture.

### MCP Server Ecosystem for Slack

**Available Options:**

| Server | Maintainer | Status | Capabilities |
|--------|------------|--------|--------------|
| [@modelcontextprotocol/server-slack](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack) | Anthropic (archived) | Archived | Basic channel/messaging |
| [zencoderai/slack-mcp-server](https://github.com/zencoderai/slack-mcp-server) | Zencoder | Active | Fork of official, maintained |
| [korotovsky/slack-mcp-server](https://github.com/korotovsky/slack-mcp-server) | Community | Active | Advanced: DMs, search, pagination |
| Slack Official (upcoming) | Salesforce/Slack | Summer 2025 | Enterprise-grade, OAuth |

**Slack MCP Server Capabilities (typical):**

| Tool | Description |
|------|-------------|
| `slack_list_channels` | List public/private channels |
| `slack_get_channel_history` | Read recent messages from channel |
| `slack_post_message` | Send message to channel |
| `slack_reply_to_thread` | Reply in existing thread |
| `slack_add_reaction` | Add emoji reaction |
| `slack_get_thread_replies` | Fetch all replies in thread |
| `slack_get_user_profile` | Get user details |
| `slack_search_messages` | Search messages (advanced servers) |

### What We're Deciding

This ADR evaluates three approaches:

1. **Keep Current + Pub/Sub:** File-based → Pub/Sub transport (per existing ADR)
2. **Replace with Slack MCP:** Direct Claude → Slack via MCP server
3. **Hybrid:** MCP for reading, custom service for notifications

### Key Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Bidirectional communication | High | Agent sends and receives messages |
| Thread continuity | High | Conversations stay in threads |
| Mobile notifications | High | Push notifications to phone |
| Low latency | Medium | < 5 seconds for notifications |
| GCP deployment ready | High | Must work in Cloud Run |
| Audit trail | Medium | Track what agent sent/received |
| Rate limit handling | Medium | Slack has 1 msg/sec limit |
| Error recovery | Medium | Retry failed messages |

### Current Pain Points

1. **Complexity:** ~2,100 LOC across 4 components for basic messaging
2. **Latency:** 15-second batch window for notifications
3. **GCP Blocker:** File-based approach needs replacement for Cloud Run
4. **Indirect Access:** Agent can't read Slack history or search messages
5. **Thread Fragility:** Thread tracking via JSON file can drift

### Potential Benefits of MCP

1. **Direct Access:** Agent reads/writes Slack directly
2. **Richer Capabilities:** Search messages, read history, get user profiles
3. **Simpler Architecture:** No intermediate services
4. **Standard Protocol:** MCP is industry standard

## Decision

**We will adopt a hybrid approach: Slack MCP server for reading + enhanced notification service for sending.**

### Rationale

| Operation | Approach | Why |
|-----------|----------|-----|
| **Reading** (history, threads, search) | Slack MCP Server | Direct access, richer capabilities |
| **Sending** (notifications, replies) | Enhanced service (Pub/Sub → Slack) | Better control, rate limiting, audit |
| **Receiving** (human → agent) | Keep Socket Mode receiver | Real-time, established pattern |

**Why not full MCP for sending?**

1. **Rate Limiting:** Custom service can batch and throttle (Slack: 1 msg/sec per channel)
2. **Retry Logic:** Pub/Sub provides at-least-once delivery with dead letter handling
3. **Audit Trail:** Central service logs all outbound messages
4. **Thread Management:** Service maintains thread state reliably
5. **Notification Patterns:** Summary + detail pattern (two-file) needs orchestration

**Why MCP for reading?**

1. **On-Demand:** Agent queries when needed, not continuous sync
2. **Context Building:** Can read conversation history for context
3. **Search:** Can find relevant past discussions
4. **User Lookup:** Can identify who said what

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Outbound Messages** | Pub/Sub → slack-worker | Rate limiting, retry, audit | Direct MCP (no rate control) |
| **Reading History** | Slack MCP Server | On-demand, rich capabilities | No access (current) |
| **Thread Management** | Firestore (per Pub/Sub ADR) | Reliable, survives restarts | JSON file (fragile) |
| **Inbound Messages** | Socket Mode receiver | Real-time, established | Polling (latency) |
| **Search/Lookup** | Slack MCP Server | Native capability | Custom sync (overkill) |

## Implementation Details

### 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Container (jib / Claude Code)                          │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                         Claude Code                                  │ │
│  │                                                                      │ │
│  │  ┌─────────────────────┐         ┌─────────────────────────────┐   │ │
│  │  │   Slack MCP Server  │         │  notifications library      │   │ │
│  │  │   (read operations) │         │  (send operations)          │   │ │
│  │  │                     │         │                             │   │ │
│  │  │  • list_channels    │         │  • slack_notify()           │   │ │
│  │  │  • get_history      │         │  • notify_pr_created()      │   │ │
│  │  │  • search_messages  │         │  • notify_action_required() │   │ │
│  │  │  • get_thread       │         │                             │   │ │
│  │  │  • get_user_profile │         │  Publishes to Pub/Sub       │   │ │
│  │  └──────────┬──────────┘         └──────────────┬──────────────┘   │ │
│  │             │                                    │                  │ │
│  └─────────────┼────────────────────────────────────┼──────────────────┘ │
└────────────────┼────────────────────────────────────┼────────────────────┘
                 │                                    │
                 │ Direct API                         │ Pub/Sub
                 ▼                                    ▼
┌────────────────────────────┐      ┌─────────────────────────────────────┐
│       Slack API            │      │         Cloud Pub/Sub               │
│   (read operations)        │      │      slack-outgoing topic           │
└────────────────────────────┘      └─────────────────┬───────────────────┘
                                                      │
                                                      │ Push subscription
                                                      ▼
                                    ┌─────────────────────────────────────┐
                                    │         slack-worker                 │
                                    │  • Rate limiting (1 msg/sec)        │
                                    │  • Thread management (Firestore)    │
                                    │  • Retry logic                      │
                                    │  • Audit logging                    │
                                    └─────────────────┬───────────────────┘
                                                      │
                                                      ▼
                                    ┌─────────────────────────────────────┐
                                    │       Slack API                      │
                                    │   (write operations)                 │
                                    └─────────────────────────────────────┘
```

### 2. Slack MCP Server Configuration

```json
// ~/.claude/settings.json (or claude_desktop_config.json)
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
        "SLACK_TEAM_ID": "${SLACK_TEAM_ID}"
      }
    }
  }
}
```

**Alternative: korotovsky/slack-mcp-server (more features):**
```json
{
  "mcpServers": {
    "slack": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "SLACK_BOT_TOKEN",
        "-e", "SLACK_TEAM_ID",
        "ghcr.io/korotovsky/slack-mcp-server:latest"
      ],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
        "SLACK_TEAM_ID": "${SLACK_TEAM_ID}"
      }
    }
  }
}
```

### 3. Required Slack Bot Scopes

**For MCP Server (read operations):**
```
channels:history      - Read public channel messages
channels:read         - List public channels
groups:history        - Read private channel messages
groups:read           - List private channels
im:history           - Read DM messages
im:read              - List DMs
mpim:history         - Read group DM messages
mpim:read            - List group DMs
users:read           - View user info
users.profile:read   - View user profiles
search:read          - Search messages (if supported)
```

**For slack-worker (write operations):**
```
chat:write           - Send messages
reactions:write      - Add reactions
files:write          - Upload files (future)
```

### 4. Use Cases Enabled by MCP

**Use Case 1: Contextual Responses**
```
Human: "What did we decide about the auth approach last week?"

Agent (via MCP):
1. slack_search_messages("auth approach", last_7_days)
2. slack_get_thread_replies(relevant_thread_ts)
3. Summarize findings
```

**Use Case 2: Thread Continuation**
```
Human replies to agent's notification

Agent (via MCP):
1. slack_get_thread_replies(thread_ts)  # Get full context
2. Understand conversation history
3. Generate informed response
4. notifications.reply_to_thread()       # Send via Pub/Sub
```

**Use Case 3: User Context**
```
Agent receives task assignment

Agent (via MCP):
1. slack_get_user_profile(assigner_user_id)
2. Understand role, timezone, preferences
3. Tailor communication style
```

**Use Case 4: Find Related Discussions**
```
Agent working on feature X

Agent (via MCP):
1. slack_search_messages("feature X")
2. Find past decisions, concerns, requirements
3. Incorporate into implementation
```

### 5. Notification Library Updates

The existing `notifications` library continues to handle outbound messages, but now publishes to Pub/Sub:

```python
# notifications/slack.py (updated)

class SlackNotificationService:
    def __init__(self):
        # Use Pub/Sub for sending (per ADR-Message-Queue)
        self.pubsub = PubSubNotificationService()

    def slack_notify(self, title: str, body: str, context: NotificationContext = None):
        """Send notification via Pub/Sub → slack-worker → Slack."""
        return self.pubsub.send(title, body, context)

    def reply_to_thread(self, thread_ts: str, message: str):
        """Reply to existing thread via Pub/Sub."""
        context = NotificationContext(thread_ts=thread_ts)
        return self.pubsub.send("", message, context)

    # MCP handles reading - agent uses tools directly:
    # - slack_get_channel_history
    # - slack_get_thread_replies
    # - slack_search_messages
```

### 6. Inbound Message Handling

The Socket Mode receiver (`host-receive-slack.py`) remains largely unchanged for GCP:

**Local (current):**
```
Slack Socket Mode → host-receive-slack.py → ~/sharing/incoming/ → jib --exec
```

**GCP (Cloud Run):**
```
Slack Events API → Cloud Run (slack-receiver) → Pub/Sub (slack-incoming) → Cloud Run (jib)
```

The receiver service writes to Pub/Sub instead of files, but the message format stays compatible.

## Migration Strategy

### Phase 1: Add Slack MCP Server (Read-Only)

**Goal:** Enable agent to read Slack history without breaking existing flows

1. Configure Slack MCP server in Claude Code settings
2. Add required bot scopes (read-only)
3. Test MCP read operations:
   - `slack_list_channels`
   - `slack_get_channel_history`
   - `slack_get_thread_replies`
4. Update CLAUDE.md with new capabilities

**Duration:** 1 week
**Risk:** Low (additive, no changes to existing flows)

### Phase 2: Integrate MCP with Workflows

**Goal:** Agent uses MCP to build context before responding

1. Update watcher scripts to use MCP for thread context
2. Enable search capabilities for finding related discussions
3. Test contextual response generation

**Duration:** 1-2 weeks
**Success Criteria:** Agent responses show awareness of conversation history

### Phase 3: Deploy Pub/Sub + slack-worker

**Goal:** Replace file-based notifications with Pub/Sub (per ADR-Message-Queue)

1. Deploy slack-worker service
2. Update notifications library to use Pub/Sub
3. Migrate thread state to Firestore
4. Validate end-to-end flow

**Duration:** 2-3 weeks (covered by ADR-Message-Queue)

### Phase 4: GCP Deployment

**Goal:** Full system running in Cloud Run

1. MCP server runs as sidecar or remote service
2. Pub/Sub handles all message transport
3. Socket Mode receiver runs as Cloud Run service
4. Firestore manages thread state

**Duration:** As part of broader Cloud Run migration

### Phase 5: Deprecate File-Based Components

**Goal:** Remove host-side services

1. Disable host-notify-slack.py (replaced by Pub/Sub)
2. Disable host-receive-slack.py (replaced by Cloud Run service)
3. Remove file-based notification code from container
4. Archive deprecated code

**Duration:** 1 week
**Code Removed:** ~1,300 lines (host services)

## Consequences

### Benefits

1. **Richer Agent Capabilities:**
   - Read conversation history
   - Search past discussions
   - Understand thread context
   - Look up user information

2. **Simplified Architecture:**
   - MCP handles reads directly
   - No custom sync for Slack history
   - Standard protocol

3. **Better Context:**
   - Agent can find related discussions
   - Understand who said what
   - Build on past decisions

4. **GCP Ready:**
   - MCP works over network
   - Pub/Sub for reliable messaging
   - No file dependencies

5. **Maintained Reliability:**
   - Pub/Sub for outbound (rate limiting, retry)
   - Firestore for thread state
   - Audit trail preserved

### Drawbacks

1. **Split Architecture:** Read (MCP) vs Write (Pub/Sub) uses different paths
2. **Additional Bot Scopes:** Need more Slack permissions
3. **MCP Server Dependency:** Another component to configure/maintain
4. **Token Usage:** MCP queries consume Claude tokens

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| MCP server unavailable | Graceful degradation; agent works without history |
| Slack rate limits on reads | Cache recent queries; batch where possible |
| Bot scope creep | Document minimum required scopes; regular audit |
| Thread state inconsistency | Firestore as source of truth; MCP for verification |

### Cost Estimate

| Component | Usage | Monthly Cost |
|-----------|-------|--------------|
| Pub/Sub (per ADR) | ~15,000 msgs | Free tier |
| Firestore (per ADR) | ~30,000 ops | Free tier |
| MCP server | Runs in container | $0 |
| Slack API | Read operations | Free (within limits) |
| **Total** | | **$0** |

## Decision Permanence

**Medium permanence.**

- **MCP for reading:** Low permanence - can disable without breaking core functionality
- **Pub/Sub for sending:** Medium permanence - part of GCP deployment strategy
- **Hybrid architecture:** Can evolve to full MCP if their write capabilities mature

## Alternatives Considered

### Alternative 1: Full Slack MCP (Read + Write)

**Description:** Use MCP server for all Slack operations, no custom services.

**Pros:**
- Simplest architecture
- Single protocol for all operations
- Maximum code reduction

**Cons:**
- No rate limiting control
- No retry/dead letter handling
- No audit trail
- Thread management in agent (unreliable)
- MCP write is optional/disabled in some servers

**Rejected because:** Loses reliability guarantees for outbound messages. Rate limiting and retry are critical for production use.

### Alternative 2: Keep File-Based + Add MCP Read

**Description:** Keep current file-based notifications, add MCP for reading only.

**Pros:**
- Minimal migration
- Proven notification path
- MCP only additive

**Cons:**
- File-based blocks GCP deployment
- Still need to solve transport problem
- Two ADRs solving same problem differently

**Rejected because:** File-based approach is a GCP blocker regardless. Better to solve transport (Pub/Sub) and reading (MCP) together.

### Alternative 3: Pub/Sub Only (No MCP)

**Description:** Use Pub/Sub for transport, no MCP for Slack.

**Pros:**
- Single transport mechanism
- Already planned (ADR-Message-Queue)
- No additional dependencies

**Cons:**
- Agent can't read Slack history
- Can't search past discussions
- Can't build context from threads
- Misses MCP ecosystem benefits

**Rejected because:** Reading capabilities are valuable and MCP provides them with minimal additional complexity.

### Alternative 4: Custom Slack Sync (Like Jira/Confluence)

**Description:** Build custom sync to download Slack history to files.

**Pros:**
- Consistent with other context syncs
- Offline access
- Full control

**Cons:**
- Significant development effort
- Storage overhead for chat history
- Sync latency issues
- Reinventing what MCP provides

**Rejected because:** Slack's conversational nature suits on-demand MCP access better than periodic sync. Chat history is voluminous and mostly irrelevant.

### Alternative 5: Wait for Official Slack MCP Server

**Description:** Wait for Salesforce/Slack's official MCP server (Summer 2025).

**Pros:**
- Enterprise-grade support
- Official OAuth integration
- Best-in-class capabilities

**Cons:**
- Delays progress by months
- Current servers are functional
- Can migrate when available

**Rejected because:** Community servers work now. Can evaluate official server when released and migrate if beneficial.

## References

- [ADR: Message Queue for Slack Integration](./ADR-Message-Queue-Slack-Integration.md)
- [ADR: Context Sync Strategy - Custom vs MCP](../in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)
- [Slack MCP Server (archived)](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/slack)
- [korotovsky/slack-mcp-server](https://github.com/korotovsky/slack-mcp-server)
- [Slack MCP Announcement](https://slack.dev/secure-data-connectivity-for-the-modern-ai-era/)
- [Current Slack Integration Architecture](../../architecture/slack-integration.md)

---

**Last Updated:** 2025-11-28
**Next Review:** 2025-12-28 (Monthly)
**Status:** Proposed
