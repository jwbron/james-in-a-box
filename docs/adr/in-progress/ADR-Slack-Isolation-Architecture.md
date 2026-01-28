# ADR: Slack Isolation Architecture for Autonomous AI Agents

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, jib (AI Pair Programming)
**Proposed:** January 2026
**Status:** Proposed

## Table of Contents

- [Industry Standards Reference](#industry-standards-reference)
- [Context](#context)
- [Problem Statement](#problem-statement)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
- [Security Analysis](#security-analysis)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)
- [Implementation Plan](#implementation-plan)

## Industry Standards Reference

This ADR aligns with the **OWASP Top 10 for Agentic Applications (2026)**, extending our existing security model to cover Slack communications:

| OWASP Risk | Description | Mitigation in This ADR |
|------------|-------------|------------------------|
| **ASI01** - Agentic Excessive Authority | Agents granted overly broad permissions | Agent has no direct Slack API access; gateway exposes controlled API |
| **ASI02** - Tool Misuse & Exploitation | Agents misusing available tools | Gateway enforces message destination policies |
| **ASI03** - Identity & Privilege Abuse | Credential theft or misuse | SLACK_TOKEN never enters jib container; gateway holds all credentials |
| **ASI06** - Memory/Context Poisoning | Corruption of agent memory/config | Controlled input parsing; validated message schemas |
| **ASI10** - Rogue Agents | Agent operating outside intended behavior | Infrastructure controls prevent unauthorized Slack operations |

## Context

### Background

The james-in-a-box system currently uses a **file-based bridge** for Slack communication:

**Current Architecture:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Host Machine                                   │
│                                                                         │
│  ┌─────────────────┐                    ┌─────────────────┐            │
│  │ slack-receiver  │                    │ slack-notifier  │            │
│  │ (host service)  │                    │ (host service)  │            │
│  │                 │                    │                 │            │
│  │ SLACK_TOKEN ✓   │                    │ SLACK_TOKEN ✓   │            │
│  │ SLACK_APP_TOKEN │                    │                 │            │
│  └────────┬────────┘                    └────────▲────────┘            │
│           │                                      │                      │
│           │ Writes to                 Reads from │                      │
│           │ ~/incoming/               ~/notifications/                  │
│           ▼                                      │                      │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                    ~/.jib-sharing/                                  ││
│  │   incoming/      responses/      notifications/      tracking/      ││
│  │   (RW)           (RW)            (RW)                (RW)          ││
│  └────────────────────────────────────────────────────────────────────┘│
│           │                                      ▲                      │
└───────────│──────────────────────────────────────│──────────────────────┘
            │                                      │
            │ Mounted as ~/sharing/                │
            │                                      │
┌───────────▼──────────────────────────────────────│──────────────────────┐
│                      jib Container                                       │
│                                                                         │
│  ┌─────────────────┐                    ┌─────────────────┐            │
│  │incoming-processor                    │ notification    │            │
│  │                 │                    │ library         │            │
│  │ Reads incoming/ │                    │                 │            │
│  │ Processes tasks │                    │ Writes to       │            │
│  │                 │                    │ ~/notifications/│            │
│  │ CAN SEE ALL     │◄───────────────────│                 │            │
│  │ MESSAGE FILES   │                    │                 │            │
│  └─────────────────┘                    └─────────────────┘            │
│                                                                         │
│  NO SLACK_TOKEN (good!)                                                 │
│  CAN READ ALL INCOMING MESSAGES (bad - policy relies on filesystem)    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Current Security Model

The existing [ADR-Internet-Tool-Access-Lockdown](./ADR-Internet-Tool-Access-Lockdown.md) established the gateway-sidecar pattern for git operations. The [ADR-Git-Isolation-Architecture](../implemented/ADR-Git-Isolation-Architecture.md) implements complete isolation for git metadata.

**Current Slack security:**
- **Credential isolation**: SLACK_TOKEN is on host, not in container (good)
- **File-based communication**: Messages flow through `~/sharing/` directories
- **No policy enforcement**: Agent can read/write any file in shared directories

**Gaps identified:**
1. **No message filtering**: Agent sees ALL incoming messages, not just assigned tasks
2. **No audit trail**: File access is not logged centrally
3. **Inconsistent with git model**: Git uses gateway API; Slack uses raw files
4. **No rate limiting**: Agent could flood outgoing messages
5. **Prompt injection risk**: Malicious Slack messages processed without validation

### Scope

**In Scope:**
- Slack message routing through gateway sidecar
- Controlled API for sending/receiving Slack messages
- Audit logging for all Slack operations
- Message schema validation

**Out of Scope:**
- Message content filtering (Claude needs full context to respond)
- Advanced spam detection (rely on Slack's own protections)
- Multi-workspace support (single workspace for now)

## Problem Statement

**We need defense-in-depth for Slack communication that matches our git security model.**

Specific threats to address:

1. **Unauthorized message access**: Agent could read messages from other contexts
2. **Message injection**: Agent could send messages impersonating different contexts
3. **Audit gaps**: No visibility into what messages the agent processes
4. **Inconsistent architecture**: File-based bridge is different from gateway pattern

## Decision

**Route all Slack communication through the gateway sidecar, removing direct file access.**

### Core Principles

1. **Credential isolation**: jib container has NO Slack tokens (already true, maintain this)
2. **Gateway as single choke point**: All Slack operations go through gateway REST API
3. **Context-scoped access**: Agent only sees messages relevant to its current task
4. **Audit logging**: All Slack operations logged with full context
5. **Schema validation**: All messages validated before processing

## High-Level Design

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Docker Network                                │
│                                                                         │
│  ┌───────────────────────────────┐      ┌───────────────────────────────┐
│  │        jib container          │      │       gateway-sidecar          │
│  │                               │      │                               │
│  │  - Claude Code agent          │      │  - SLACK_TOKEN                │
│  │  - No SLACK_TOKEN             │      │  - SLACK_APP_TOKEN            │
│  │  - No ~/sharing/ mount        │ REST │  - Message queue              │
│  │                               │ API  │  - Audit logging              │
│  │  Uses gateway API:            │◄────►│  - Schema validation          │
│  │  GET  /api/slack/messages     │      │                               │
│  │  POST /api/slack/send         │      │  Policy enforcement:          │
│  │  POST /api/slack/thread-reply │      │  - Task-scoped access         │
│  │                               │      │  - Rate limiting              │
│  │                               │      │  - Destination whitelist      │
│  └───────────────────────────────┘      └───────────────────────────────┘
│                                                     │
│                                                     │ Slack Socket Mode
│                                                     │ + HTTP API
│                                                     ▼
│                                              ┌─────────────┐
│                                              │ Slack API   │
│                                              └─────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Changes

| Component | Current | Target |
|-----------|---------|--------|
| slack-receiver | Host service, writes to ~/sharing/incoming/ | Integrated into gateway sidecar |
| slack-notifier | Host service, reads ~/notifications/ | Integrated into gateway sidecar |
| ~/sharing/ mount | Full read/write access from container | Removed from container |
| incoming-processor | Reads files from ~/sharing/incoming/ | Calls gateway API for messages |
| notification library | Writes files to ~/sharing/notifications/ | Calls gateway API to send |

### Gateway Slack API

The gateway exposes a controlled REST API for Slack operations:

**Receiving Messages:**
```
GET /api/slack/messages
    ?task_id=<task-id>           # Required: current task context
    &include_thread=true         # Include full thread history

Response:
{
  "messages": [
    {
      "id": "msg-123",
      "text": "User message content",
      "thread_ts": "1706123456.789000",
      "user_id": "U01234567",
      "user_name": "James",
      "received_at": "2026-01-28T21:30:00Z"
    }
  ],
  "task_context": {
    "task_id": "task-20260128-132707",
    "thread_ts": "1706123456.789000"
  }
}

POST /api/slack/ack
    {"message_id": "msg-123", "task_id": "task-20260128-132707"}

    Acknowledges message receipt (marks as processed)
```

**Sending Messages:**
```
POST /api/slack/send
{
  "task_id": "task-20260128-132707",  # Required: links to audit trail
  "thread_ts": "1706123456.789000",   # Optional: reply in thread
  "text": "Message content",
  "markdown": true
}

Response:
{
  "success": true,
  "message_ts": "1706123789.000100",
  "thread_ts": "1706123456.789000"
}

POST /api/slack/thread-reply
{
  "task_id": "task-20260128-132707",
  "thread_ts": "1706123456.789000",  # Required for replies
  "text": "Reply content"
}
```

### Message Queue Design

The gateway maintains an internal message queue that replaces the file-based system:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Gateway Message Queue                                 │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  Incoming Queue (from Slack)                                        ││
│  │                                                                     ││
│  │  task-20260128-132707:                                             ││
│  │    - msg-001: "User task request..." (unread)                      ││
│  │    - msg-002: "Follow-up question..." (unread)                     ││
│  │                                                                     ││
│  │  task-20260128-140000:                                             ││
│  │    - msg-003: "Different task..." (unread)                         ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  Thread Mapping                                                     ││
│  │                                                                     ││
│  │  task-20260128-132707 ↔ thread_ts: 1706123456.789000              ││
│  │  task-20260128-140000 ↔ thread_ts: 1706145600.123000              ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  Outgoing Queue (to Slack)                                          ││
│  │                                                                     ││
│  │  Pending: 0                                                         ││
│  │  Rate limit: 1 msg/sec, 30 msg/min                                 ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### Task-Scoped Access Control

**Key security property**: Agent can only access messages for its current task.

```python
# Gateway enforces task-scoped access
def get_messages(container_id: str, task_id: str) -> list[Message]:
    # Validate container is authorized for this task
    if not is_container_authorized(container_id, task_id):
        raise Unauthorized(f"Container {container_id} not authorized for task {task_id}")

    # Return only messages for this specific task
    return message_queue.get_by_task(task_id)
```

**How task authorization works:**
1. When a container starts, orchestrator registers it with a specific task_id
2. Gateway maintains mapping: `container_id → authorized_task_ids`
3. API requests include container identity (via shared secret from ADR-Tool-Access-Lockdown)
4. Gateway validates container is authorized before returning messages

### Audit Log Specification

All Slack operations produce structured audit logs:

```json
{
  "timestamp": "2026-01-28T21:30:00.123Z",
  "event_type": "slack_operation",
  "operation": "message_received",
  "container_id": "jib-abc123",
  "task_id": "task-20260128-132707",
  "request": {
    "thread_ts": "1706123456.789000",
    "user_id": "U01234567"
  },
  "response": {
    "status": "delivered",
    "message_id": "msg-123"
  },
  "policy_checks": {
    "task_authorized": true,
    "rate_limit_ok": true
  }
}
```

## Security Analysis

### Threat Model

| Threat | Current Risk | After Implementation | Mitigation |
|--------|-------------|---------------------|------------|
| Agent reads other tasks' messages | HIGH - full file access | VERY LOW - task-scoped API | Gateway validates task authorization |
| Agent impersonates other threads | MEDIUM - can write any thread_ts | VERY LOW - gateway validates | Gateway manages thread mapping |
| Message injection attacks | MEDIUM - raw file parsing | LOW - schema validation | Gateway validates message format |
| Credential theft | VERY LOW - already isolated | VERY LOW | Maintained: tokens only in gateway |
| Rate limiting bypass | HIGH - unlimited file writes | VERY LOW | Gateway enforces rate limits |
| Audit trail gaps | HIGH - no central logging | VERY LOW | All operations through gateway |

### Defense in Depth Summary

```
Layer 1: Behavioral (CLAUDE.md instructions)
    ↓ Can be bypassed by prompt injection
Layer 2: Credential Isolation (already implemented)
    ↓ jib has no Slack tokens
Layer 3: Gateway Policy Enforcement (this ADR)
    ↓ Gateway validates all operations
Layer 4: Task-Scoped Access (this ADR)
    ↓ Agent only sees its own task's messages
Layer 5: Audit Logging (this ADR)
    ↓ All traffic visible for review
Layer 6: Human Review
    ↓ User can review Slack threads
```

### Rate Limiting

Gateway enforces rate limits to prevent abuse:

| Operation | Limit | Rationale |
|-----------|-------|-----------|
| Send message | 1/second, 30/minute | Prevent spam |
| Fetch messages | 10/second | Prevent polling abuse |
| Thread history | 1/minute per thread | Expensive operation |

## Consequences

### Positive

- **Consistent security model**: Slack matches git gateway pattern
- **Task isolation**: Agent only sees messages for its task
- **Full audit trail**: All Slack operations logged
- **Rate limiting**: Prevents abuse
- **Simpler container**: No shared filesystem mounts needed
- **Better testability**: Gateway API is mockable

### Negative

- **Increased complexity**: Gateway handles more responsibilities
- **Migration effort**: Need to update incoming-processor and notification library
- **Latency**: HTTP overhead vs. direct file access (~1-5ms)
- **Development friction**: Need gateway running for Slack features

### Trade-offs

| Aspect | File-Based (Current) | Gateway-Based (Target) |
|--------|----------------------|------------------------|
| Setup complexity | Low | Moderate |
| Message access control | None | Task-scoped |
| Audit visibility | File timestamps only | Full structured logs |
| Rate limiting | None | Enforced |
| Latency | ~0ms (local files) | ~1-5ms (HTTP) |
| Testability | Requires real files | Mockable API |

## Alternatives Considered

### Alternative 1: Enhanced File Permissions

**Approach:** Use filesystem permissions to restrict message access

**Pros:**
- No gateway changes needed
- Simple implementation

**Cons:**
- Hard to scope per-task
- No audit trail
- Different pattern from git

**Rejected:** Does not provide task-level isolation or audit logging

### Alternative 2: Separate Slack Gateway

**Approach:** Create a dedicated Slack gateway service separate from git gateway

**Pros:**
- Separation of concerns
- Independent scaling

**Cons:**
- Additional service to maintain
- Different auth patterns
- More network hops

**Rejected:** Adds complexity without proportional benefit; gateway is already trusted

### Alternative 3: Message Encryption

**Approach:** Encrypt messages at rest with task-specific keys

**Pros:**
- Maintains file-based pattern
- Cryptographic access control

**Cons:**
- Key management complexity
- No rate limiting
- No audit trail

**Rejected:** Adds complexity without solving audit/rate-limiting gaps

## Implementation Plan

### Phase 1: Gateway Slack API (Foundation)

**Goal:** Add Slack API endpoints to existing gateway sidecar

**Changes:**
1. Add Slack SDK to gateway dependencies
2. Implement `/api/slack/send` endpoint
3. Implement `/api/slack/messages` endpoint
4. Add basic audit logging for Slack operations
5. Migrate slack-receiver Socket Mode logic to gateway

**Container changes:** None (still uses files during transition)

**Deliverables:**
- Gateway Slack API functional
- Can receive and send messages via API
- Audit logs for API operations

### Phase 2: Notification Library Migration

**Goal:** Update container to send notifications via gateway API

**Changes:**
1. Add `GatewaySlackClient` to notification library
2. Update `SlackNotificationService` to use gateway API
3. Add fallback to file-based method during transition
4. Update incoming-processor to call gateway API

**Deprecations:**
- File-based notification writing (fallback only)

**Deliverables:**
- Container sends notifications via gateway
- Container fetches messages via gateway
- Files used only as fallback

### Phase 3: File Access Removal

**Goal:** Remove direct file access from container

**Changes:**
1. Remove `~/sharing/incoming/` mount from container
2. Remove `~/sharing/notifications/` mount from container
3. Remove `~/sharing/responses/` mount from container
4. Update orchestrator to not pass file paths
5. Remove file-based fallback code

**Preserved:**
- `~/sharing/logs/` for debugging
- `~/sharing/tracking/` for beads state

**Deliverables:**
- Container has no Slack file access
- All Slack communication via gateway
- Full audit trail

### Phase 4: Task Authorization

**Goal:** Implement task-scoped message access

**Changes:**
1. Add container registration to orchestrator
2. Implement task authorization in gateway
3. Add task_id validation to all Slack endpoints
4. Update audit logs with authorization status

**Deliverables:**
- Containers authorized for specific tasks
- Messages filtered by task
- Unauthorized access attempts logged

### Migration Path

```
Current State:
  slack-receiver (host) → ~/sharing/incoming/ → container reads files
  container writes files → ~/sharing/notifications/ → slack-notifier (host)

Phase 1 (Parallel):
  slack-receiver (host) → ~/sharing/incoming/ → container reads files  [existing]
  slack-receiver (host) → gateway queue       → API available          [new]
  container writes files → ~/sharing/notifications/                     [existing]
  container → gateway API → Slack                                       [new, not used yet]

Phase 2 (Gateway Primary):
  slack-receiver → gateway queue → container calls API                  [primary]
  container → gateway API → Slack                                       [primary]
  file-based path                                                       [fallback only]

Phase 3 (Files Removed):
  gateway ↔ container (API only)
  file mounts removed from container

Phase 4 (Full Isolation):
  gateway enforces task-scoped access
  containers authorized per-task
```

## Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Internet-Tool-Access-Lockdown](./ADR-Internet-Tool-Access-Lockdown.md) | Parent ADR - establishes gateway pattern |
| [ADR-Git-Isolation-Architecture](../implemented/ADR-Git-Isolation-Architecture.md) | Reference - git isolation model |
| [ADR-Autonomous-Software-Engineer](./ADR-Autonomous-Software-Engineer.md) | Parent ADR - defines overall security model |

---

**Last Updated:** 2026-01-28
**Next Review:** 2026-02-28 (Monthly)
**Status:** Proposed
