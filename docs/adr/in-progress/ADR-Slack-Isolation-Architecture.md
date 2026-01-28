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

The gateway maintains a persistent message queue that replaces the file-based system:

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

### Message Queue Persistence and Recovery

**Persistence Strategy: SQLite with WAL Mode**

The gateway uses SQLite (write-ahead logging) for message queue persistence. This provides:
- **Durability**: Messages survive gateway restarts
- **Simplicity**: No external database dependencies
- **Performance**: WAL mode allows concurrent reads during writes

```sql
-- Message queue schema
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    thread_ts TEXT,
    user_id TEXT,
    user_name TEXT,
    text TEXT,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP,
    acked_at TIMESTAMP,
    status TEXT CHECK(status IN ('pending', 'delivered', 'acked', 'failed')) DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0
);

CREATE TABLE thread_mappings (
    task_id TEXT PRIMARY KEY,
    thread_ts TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_task_status ON messages(task_id, status);
CREATE INDEX idx_messages_thread ON messages(thread_ts);
```

**Delivery Guarantees: At-Least-Once**

Messages are guaranteed to be delivered at least once. Containers must handle potential duplicates:

| State | Message Status | Gateway Behavior |
|-------|---------------|------------------|
| Received from Slack | `pending` | Persisted to SQLite before ACK to Slack |
| Delivered to container | `delivered` | Marked delivered, retained until ACK |
| ACKed by container | `acked` | Retained for audit, excluded from queries |
| Container disconnected | `delivered` | Re-delivered on reconnect |
| Delivery failed | `failed` | Moved to dead letter queue after 3 retries |

**Gateway Restart Recovery:**

```
1. Gateway starts up
2. Load all messages with status='pending' or status='delivered'
3. Resume Slack Socket Mode connection
4. For messages delivered before shutdown:
   - If container still active: Re-deliver (idempotent)
   - If container gone: Keep pending until new container claims task
5. Resume processing new incoming messages
```

**Dead Letter Queue (DLQ):**

Messages that fail delivery after 3 attempts are moved to the DLQ:

```sql
CREATE TABLE dead_letter_queue (
    id TEXT PRIMARY KEY,
    original_message_id TEXT REFERENCES messages(id),
    task_id TEXT,
    failure_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

DLQ messages generate alerts and require manual intervention:
- Available via admin API: `GET /internal/dlq`
- Can be replayed: `POST /internal/dlq/{id}/replay`
- Automatically purged after 7 days

**Queue Overflow Handling:**

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Messages per task | 1,000 | Reject new messages, alert |
| Total pending messages | 10,000 | Apply backpressure to Slack ingestion |
| SQLite file size | 1 GB | Archive old messages, alert |

Backpressure is applied by slowing Socket Mode ACKs, causing Slack to retry later.

### Thread Mapping Integrity

The thread mapping (`task_id ↔ thread_ts`) is critical for security. This section specifies its lifecycle and immutability constraints.

**Mapping Lifecycle:**

```
┌────────────────────────────────────────────────────────────────────────────┐
│                     Thread Mapping Lifecycle                                │
│                                                                            │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐ │
│  │   Created   │───►│   Active     │───►│   Closed    │───►│  Archived  │ │
│  │             │    │              │    │             │    │            │ │
│  │ On first    │    │ Messages     │    │ Task done,  │    │ Purged     │ │
│  │ message in  │    │ routed via   │    │ mapping     │    │ after 90   │ │
│  │ new thread  │    │ this mapping │    │ locked      │    │ days       │ │
│  └─────────────┘    └──────────────┘    └─────────────┘    └────────────┘ │
│                                                                            │
│  State transitions:                                                        │
│  - Created→Active: Automatic on first message delivery                     │
│  - Active→Closed: When container ACKs task completion                      │
│  - Closed→Archived: Background job after 90-day retention                  │
└────────────────────────────────────────────────────────────────────────────┘
```

**Mapping Creation Rules:**

| Trigger | Mapping Created By | Validation |
|---------|-------------------|------------|
| New Slack thread mentioning @jib | Gateway (on message receipt) | Thread must not already be mapped |
| Orchestrator starts task for thread | Orchestrator (via internal API) | Orchestrator provides both task_id and thread_ts |
| Container requests messages for new task | Rejected | Container cannot create mappings |

**Immutability Constraints:**

Once created, a thread mapping has the following immutability guarantees:

```sql
-- thread_ts is immutable after creation
-- Enforced via trigger
CREATE TRIGGER prevent_thread_ts_update
    BEFORE UPDATE OF thread_ts ON thread_mappings
    BEGIN
        SELECT RAISE(ABORT, 'thread_ts is immutable');
    END;

-- task_id is immutable after creation
CREATE TRIGGER prevent_task_id_update
    BEFORE UPDATE OF task_id ON thread_mappings
    BEGIN
        SELECT RAISE(ABORT, 'task_id is immutable');
    END;
```

| Property | Immutable | Rationale |
|----------|-----------|-----------|
| task_id | Yes | Prevents task hijacking |
| thread_ts | Yes | Prevents thread redirects |
| created_at | Yes | Audit integrity |
| status | No | Lifecycle transitions allowed |
| updated_at | No | Tracks last activity |

**Collision Prevention:**

```python
def create_mapping(task_id: str, thread_ts: str, created_by: str) -> ThreadMapping:
    # Check for existing mappings
    existing_task = get_mapping_by_task(task_id)
    existing_thread = get_mapping_by_thread(thread_ts)

    if existing_task:
        raise MappingConflict(f"task_id {task_id} already mapped to thread {existing_task.thread_ts}")

    if existing_thread:
        raise MappingConflict(f"thread_ts {thread_ts} already mapped to task {existing_thread.task_id}")

    # Create mapping atomically
    return db.execute("""
        INSERT INTO thread_mappings (task_id, thread_ts, created_by)
        VALUES (?, ?, ?)
    """, (task_id, thread_ts, created_by))
```

**Security implications:**
- A thread can only map to one task (prevents message leakage)
- A task can only map to one thread (prevents impersonation)
- Only the orchestrator and gateway can create mappings (containers cannot)
- Closed mappings remain readable for audit but reject new messages

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

### Container Identity Verification

**Current approach: Shared Secret**

Per [ADR-Internet-Tool-Access-Lockdown](./ADR-Internet-Tool-Access-Lockdown.md), containers authenticate to the gateway using a shared secret injected at container startup:

```
Authorization: Bearer <shared-secret>
```

This is sufficient for Slack operations because:
- Both git and Slack operations flow through the same gateway
- The threat model assumes a trusted Docker network (containers cannot sniff traffic)
- The shared secret is generated per-session and never persisted

**Future consideration: mTLS**

The parent ADR mentions mTLS as a future enhancement for production deployments. For Slack operations specifically:

| Factor | Shared Secret | mTLS |
|--------|--------------|------|
| Implementation complexity | Low | High (PKI management) |
| Identity strength | Session-bound token | Cryptographic certificate |
| Replay protection | Relies on HTTPS | Built-in via TLS handshake |
| Suitable for | Local Docker deployment | GCP Cloud Run, multi-tenant |

**Recommendation:** Shared secret is acceptable for current single-tenant Docker deployment. If moving to:
- **GCP Cloud Run**: Implement mTLS using Cloud Run's native service identity
- **Multi-tenant deployment**: Implement mTLS with per-tenant certificates

This decision can be deferred to Phase 4 or a separate ADR focused on production hardening.

### Task Authorization Bootstrapping

**Registration Protocol:**

The orchestrator-to-gateway registration uses a secure channel to prevent task_id spoofing:

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│  Orchestrator  │     │    Gateway     │     │  jib Container │
└───────┬────────┘     └───────┬────────┘     └───────┬────────┘
        │                      │                      │
        │ 1. Register container │                      │
        │ POST /internal/register                      │
        │ {container_id, task_id, ttl}                │
        │─────────────────────►│                      │
        │                      │                      │
        │ 2. Return registration token                │
        │◄─────────────────────│                      │
        │                      │                      │
        │ 3. Start container   │                      │
        │ with shared secret + │                      │
        │ registration token   │                      │
        │──────────────────────────────────────────►│
        │                      │                      │
        │                      │ 4. First API call   │
        │                      │ includes registration│
        │                      │ token + shared secret│
        │                      │◄─────────────────────│
        │                      │                      │
        │                      │ 5. Validate token   │
        │                      │ Activate mapping    │
        │                      │─────────────────────►│
        │                      │                      │
```

**Security properties:**
- **Deny-by-default**: Containers cannot access any messages until registration is confirmed
- **Time-bound mappings**: Registrations include TTL (default: 4 hours); expired mappings are automatically revoked
- **Secure channel**: Orchestrator-to-gateway registration uses a separate admin secret not available to containers
- **One-time activation**: Registration token is single-use; gateway rejects replays
- **No task_id guessing**: Container only knows its own task_id; cannot enumerate other active tasks

**Race condition prevention:**
- Gateway queues messages for unregistered task_ids (30-minute retention)
- Container retries with exponential backoff if gateway returns "registration pending"
- Orchestrator waits for gateway ACK before starting container

**Handling container restarts:**
- If a container restarts with the same task_id, orchestrator issues new registration
- Gateway recognizes the task_id and extends the mapping to the new container_id
- Previous container_id authorization is immediately revoked

**Concurrent container access:**

Multiple containers can legitimately access the same task_id concurrently. This is a normal operational scenario that occurs when:
- Multiple messages arrive in a Slack thread in rapid succession
- Each message spawns a container, and multiple containers run in parallel on the same task

The gateway handles this as follows:
- Task_id → container_id mapping is one-to-many (multiple containers can be authorized for one task)
- Messages are delivered to ALL authorized containers for that task_id
- Each container processes independently; no coordination required
- Rate limits still apply per-container (not aggregated across containers on same task)
- When any container ACKs a message, it's marked as ACKed for that container only

```python
# Gateway maintains multiple container authorizations per task
def is_container_authorized(container_id: str, task_id: str) -> bool:
    # Returns True if this specific container is authorized for this task
    # Multiple containers can be authorized for the same task simultaneously
    return container_id in task_authorizations.get(task_id, set())

def deliver_message(task_id: str, message: Message):
    # Deliver to all authorized containers for this task
    for container_id in task_authorizations.get(task_id, set()):
        delivery_queue.add(container_id, message)
```

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

**Audit Log Retention:**

Consistent with [ADR-Internet-Tool-Access-Lockdown](./ADR-Internet-Tool-Access-Lockdown.md), Slack audit logs follow the same retention policy:

| Log Type | Retention | Storage |
|----------|-----------|---------|
| Gateway audit logs (Slack + git) | 90 days | Local JSON files, rotated daily |
| Message content | 30 days | SQLite (message queue) |
| Thread mappings | 90 days after closure | SQLite (thread_mappings) |
| Dead letter queue | 7 days | SQLite (dlq) |

No regulatory requirements specific to Slack differ from git operations. If compliance requirements change (e.g., SOC 2 audit trail), retention can be extended.

### Error Response Format

Gateway API errors follow the same format as git gateway operations for consistency:

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded for send_message operation",
    "details": {
      "limit": "30/minute",
      "retry_after_seconds": 45
    }
  },
  "request_id": "req-abc123",
  "timestamp": "2026-01-28T21:30:00.123Z"
}
```

**Error Codes:**

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Invalid or missing shared secret |
| `TASK_NOT_AUTHORIZED` | 403 | Container not registered for task_id |
| `RATE_LIMIT_EXCEEDED` | 429 | Rate limit exceeded (includes retry_after) |
| `THREAD_NOT_FOUND` | 404 | thread_ts does not exist or is not mapped |
| `VALIDATION_ERROR` | 400 | Request body failed schema validation |
| `SLACK_API_ERROR` | 502 | Upstream Slack API returned error |
| `INTERNAL_ERROR` | 500 | Unexpected gateway error |

### Message Schema Validation

Incoming and outgoing messages are validated against JSON schemas. Schema definitions will be stored in:

```
gateway/
  schemas/
    slack_message_incoming.json
    slack_message_outgoing.json
    slack_thread_reply.json
```

**Example schema (outgoing message):**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["task_id", "text"],
  "properties": {
    "task_id": {
      "type": "string",
      "pattern": "^task-[0-9]{8}-[0-9]{6}$"
    },
    "thread_ts": {
      "type": "string",
      "pattern": "^[0-9]+\\.[0-9]+$"
    },
    "text": {
      "type": "string",
      "minLength": 1,
      "maxLength": 4000
    },
    "markdown": {
      "type": "boolean",
      "default": true
    }
  },
  "additionalProperties": false
}
```

Schema validation errors return a `VALIDATION_ERROR` response with details about the failing field.

## Security Analysis

### Slack API Token Scope

The gateway requires the following Slack Bot Token scopes:

| Scope | Required | Purpose | Over-permissioning Risk |
|-------|----------|---------|------------------------|
| `chat:write` | Yes | Send messages to threads | Can message any accessible channel |
| `channels:history` | Yes | Read messages in public channels | Can read all public channel history |
| `groups:history` | Conditional | Read messages in private channels | Only if private channels needed |
| `im:history` | No | Read direct messages | Not required; reject DM interactions |
| `users:read` | Yes | Resolve user IDs to names | Read-only, low risk |
| `app_mentions:read` | Yes | Receive @mentions via Socket Mode | Event subscription only |
| `connections:write` | Yes | Establish Socket Mode connection | Required for real-time events |

**Minimizing Token Permissions:**

Unlike GitHub where the gateway explicitly blocks `gh pr merge`, Slack's API doesn't provide operation-level granularity within scopes. The gateway implements additional restrictions:

```python
# Gateway-enforced restrictions beyond token scopes
SLACK_RESTRICTIONS = {
    # Channel restrictions
    "allowed_channel_types": ["public_channel"],  # No DMs or private channels
    "blocked_channels": [],  # Admin-configurable blocklist

    # Message restrictions
    "max_message_length": 4000,  # Slack's limit
    "blocked_patterns": [],  # No content filtering by default

    # User restrictions
    "blocked_users": [],  # Admin-configurable blocklist
}

def validate_outgoing_message(message: SlackMessage) -> bool:
    # Enforce channel type restriction
    if message.channel_type not in SLACK_RESTRICTIONS["allowed_channel_types"]:
        raise PolicyViolation("DMs and private channels not allowed")

    # Enforce channel blocklist
    if message.channel_id in SLACK_RESTRICTIONS["blocked_channels"]:
        raise PolicyViolation(f"Channel {message.channel_id} is blocked")

    return True
```

**Token Scope Rationale:**

| Why Not Narrower | Explanation |
|------------------|-------------|
| `chat:write` instead of `chat:write.public` | Need to write to threads started by users in any channel type the bot is added to |
| `channels:history` required | Must fetch thread context for replies; cannot rely solely on Socket Mode events |

**Token Security:**
- Token stored only in gateway container
- Token never logged (sensitive field masking)
- Token rotation supported via config reload (no gateway restart required)
- Separate user token not used; only bot token

### Threat Model

| Threat | Current Risk | After Implementation | Mitigation |
|--------|-------------|---------------------|------------|
| Agent reads other tasks' messages | HIGH - full file access | VERY LOW - task-scoped API | Gateway validates task authorization |
| Agent impersonates other threads | MEDIUM - can write any thread_ts | VERY LOW - gateway validates | Gateway manages thread mapping |
| Message injection attacks | MEDIUM - raw file parsing | LOW - schema validation | Gateway validates message format |
| Credential theft | VERY LOW - already isolated | VERY LOW | Maintained: tokens only in gateway |
| Rate limiting bypass | HIGH - unlimited file writes | VERY LOW | Gateway enforces rate limits |
| Audit trail gaps | HIGH - no central logging | VERY LOW | All operations through gateway |

### Security Assumptions

This section documents assumptions made during security analysis that bound the threat model.

| Assumption | Rationale | Impact if Violated |
|------------|-----------|-------------------|
| **Gateway deployed securely** | The gateway sidecar will be deployed following the same security practices as other production services. On host machines, this is equivalent to existing credential storage (credentials would live somewhere on the machine regardless). | If gateway is compromised, attacker gains access to Slack and GitHub tokens. Mitigate via standard deployment hardening, not architectural changes. |
| **Isolated network traffic** | Traffic between jib container and gateway runs on an isolated network—either Docker bridge on host, or VPC in GCP. | If network is compromised, replay attacks become possible. Mitigate via mTLS in production (see Container Identity Verification section). |
| **Content filtering is out of scope** | Message content filtering to prevent secret leaks is explicitly out of scope. LLMs can work around any such filters through encoding, ciphers, or other subterfuge. The architectural controls (credential isolation, gateway policy) are the primary defense. | Agent could exfiltrate information via Slack messages. Mitigate via human review of Slack threads (Layer 6 in defense-in-depth). |
| **Concurrent container access is valid** | Multiple containers CAN legitimately access the same task_id concurrently. This occurs when multiple messages are sent to a single thread in rapid succession, spawning parallel container executions. | Gateway must handle concurrent access gracefully—no mutex on task_id access, only on registration/deregistration. |

**Implications for implementation:**

1. **Gateway compromise**: No separate credential sidecars needed. Standard deployment security is sufficient. This is consistent with the existing git gateway design.

2. **Replay attack prevention**: The current shared-secret approach plus HTTPS transport is sufficient for Docker deployment. mTLS should be implemented for GCP Cloud Run deployment (see Phase 4 or future hardening ADR).

3. **Message content**: The gateway enforces structural limits (message length, schema validation) but does not attempt semantic filtering. Audit logs provide visibility for human review.

4. **Concurrent access**: The "Handling container restarts" section is updated to reflect that this is a normal operation, not an error condition. Task mappings are many-to-one (multiple containers → one task_id).

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

Gateway enforces multi-level rate limits to prevent abuse:

**Per-Task Rate Limits:**

| Operation | Limit | Rationale |
|-----------|-------|-----------|
| Send message | 1/second, 30/minute | Prevent spam |
| Fetch messages | 10/second | Prevent polling abuse |
| Thread history | 1/minute per thread | Expensive operation |

**Aggregate Rate Limits (Bypass Prevention):**

To prevent rate limit bypass via task proliferation, the gateway also enforces aggregate limits:

| Scope | Operation | Limit | Rationale |
|-------|-----------|-------|-----------|
| Per-container | Send message | 60/minute | Limits total output regardless of task count |
| Per-container | New task registration | 10/hour | Prevents task_id enumeration attacks |
| Per-thread | Send message | 30/minute | Prevents thread bombing even across tasks |
| Global | Send message | 120/minute | Backstop for system-wide abuse |
| Global | Fetch messages | 1000/second | Protect gateway under load |

**Rate Limit Enforcement:**

```python
def check_rate_limit(container_id: str, task_id: str, thread_ts: str, operation: str) -> bool:
    # Check all applicable rate limits in order
    checks = [
        (f"task:{task_id}:{operation}", TASK_LIMITS[operation]),
        (f"container:{container_id}:{operation}", CONTAINER_LIMITS[operation]),
        (f"thread:{thread_ts}:{operation}", THREAD_LIMITS[operation]),
        (f"global:{operation}", GLOBAL_LIMITS[operation]),
    ]

    for key, limit in checks:
        if not rate_limiter.check(key, limit):
            audit_log.record(
                event="rate_limit_exceeded",
                container_id=container_id,
                task_id=task_id,
                limit_key=key
            )
            return False
    return True
```

Rate limit state is stored in Redis (or in-memory with persistence) to survive gateway restarts.

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

**`~/sharing/` Directory Migration Plan:**

| Subdirectory | Current Use | Post-Migration | Rationale |
|--------------|-------------|----------------|-----------|
| `~/sharing/incoming/` | Slack task files | **Removed** | Replaced by gateway API |
| `~/sharing/responses/` | Response capture | **Removed** | Replaced by gateway API |
| `~/sharing/notifications/` | Outbound notifications | **Removed** | Replaced by gateway API |
| `~/sharing/logs/` | Debug logs | **Preserved** | Non-Slack; useful for debugging |
| `~/sharing/tracking/` | Beads state | **Preserved** | Non-Slack; beads persistence |
| `~/sharing/context/` | Context sync data | **Preserved** | Non-Slack; load/save context |

**CLAUDE.md Update Required:**

The current CLAUDE.md references to be updated in Phase 3:

```diff
# Current references that will break:
- ~/sharing/incoming/     # Remove: tasks come via gateway API
- ~/sharing/responses/    # Remove: responses go via gateway API
- ~/sharing/notifications/  # Remove: use notification library (API-backed)

# References that remain valid:
  ~/sharing/logs/         # Preserved: debugging
  ~/sharing/tracking/     # Preserved: beads state (non-Slack)
```

A CLAUDE.md update will be included in the Phase 3 implementation PR.

**Deliverables:**
- Container has no Slack file access
- All Slack communication via gateway
- Full audit trail
- CLAUDE.md updated to reflect new paths

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
