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

**DLQ Replay Security:**

When replaying DLQ messages, the gateway validates that the original task_id mapping is still valid:

```python
@app.route("/internal/dlq/<message_id>/replay", methods=["POST"])
@require_admin_auth
def replay_dlq_message(message_id: str):
    """Replay a dead-lettered message with validation."""
    with get_connection() as conn:
        dlq_row = conn.execute(
            "SELECT * FROM dead_letter_queue WHERE id = ?", (message_id,)
        ).fetchone()

        if not dlq_row:
            return jsonify({"error": "DLQ message not found"}), 404

        original_task_id = dlq_row["task_id"]

        # Validate task mapping still exists and is active
        mapping = conn.execute(
            "SELECT * FROM thread_mappings WHERE task_id = ? AND status = 'active'",
            (original_task_id,)
        ).fetchone()

        if not mapping:
            return jsonify({
                "error": "Task mapping no longer valid",
                "original_task_id": original_task_id,
                "action_required": "Create new task mapping or discard message"
            }), 400

        # Check if any container is currently authorized for this task
        authorized = conn.execute(
            """SELECT container_id FROM container_registrations
               WHERE task_id = ? AND status = 'active' AND expires_at > CURRENT_TIMESTAMP""",
            (original_task_id,)
        ).fetchone()

        # Replay the message
        new_container_id = authorized["container_id"] if authorized else None
        # ... replay logic ...

        audit_log(
            event_type="dlq_replay",
            original_message_id=message_id,
            task_id=original_task_id,
            new_container_id=new_container_id
        )

        return jsonify({"success": True, "replayed_to": new_container_id}), 200
```

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
- **Cryptographic binding**: Registration token is bound to container's shared secret via HMAC

**Registration Token Replay Prevention:**

The registration token alone is not sufficient to activate a container. To prevent replay attacks during the window between orchestrator registration and container startup, the activation requires a cryptographic proof:

```python
# Activation requires HMAC proof binding registration token to shared secret
def activate_registration(registration_token: str, shared_secret: str) -> bool:
    # Container must provide HMAC(shared_secret, registration_token)
    expected_proof = hmac.new(
        shared_secret.encode(),
        registration_token.encode(),
        hashlib.sha256
    ).hexdigest()

    provided_proof = request.headers.get("X-Activation-Proof")
    if not hmac.compare_digest(expected_proof, provided_proof):
        audit_log(event="activation_proof_mismatch", token=registration_token[:8])
        return False

    # Additional: Activation window is short (30 seconds from registration)
    # This limits the replay window even if proof is somehow compromised
    return True
```

**Security implications:**
- Even if an attacker intercepts the registration token, they cannot activate without the shared secret
- The shared secret is generated per-container and never transmitted over the network during activation
- Activation must occur within 30 seconds of registration (configurable) to limit the window

**Race condition prevention:**
- Gateway queues messages for unregistered task_ids (30-minute retention)
- Container retries with exponential backoff if gateway returns "registration pending"
- Orchestrator waits for gateway ACK before starting container
- Activation window (30 seconds) starts when orchestrator receives registration ACK

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
- Rate limits still apply per-container (not aggregated across containers on same task)
- Per-container ACK tracking prevents duplicate processing

**Response Deduplication (First-Responder Pattern):**

To prevent multiple containers from sending duplicate responses to the same incoming message, the gateway implements a first-responder pattern using correlation IDs:

```python
# Each incoming message gets a correlation_id
# Only one container can "claim" a message for response
def claim_message_for_response(container_id: str, message_id: str) -> bool:
    """Atomically claim a message for response. Returns True if claimed, False if already claimed."""
    with get_connection() as conn:
        result = conn.execute(
            """UPDATE messages SET response_claimed_by = ?, response_claimed_at = CURRENT_TIMESTAMP
               WHERE id = ? AND response_claimed_by IS NULL""",
            (container_id, message_id)
        )
        return result.rowcount > 0

def send_message_response(container_id: str, correlation_id: str, text: str) -> dict:
    """Send a response to an incoming message."""
    # Verify this container claimed the message
    with get_connection() as conn:
        row = conn.execute(
            "SELECT response_claimed_by FROM messages WHERE id = ?",
            (correlation_id,)
        ).fetchone()

        if not row:
            return {"error": "Message not found"}
        if row["response_claimed_by"] != container_id:
            return {"error": "Message claimed by another container", "claimed_by": row["response_claimed_by"]}

    # Proceed with sending response
    return slack_client.send_message(...)
```

**Schema update for response tracking:**

```sql
ALTER TABLE messages ADD COLUMN response_claimed_by TEXT;
ALTER TABLE messages ADD COLUMN response_claimed_at TIMESTAMP;
ALTER TABLE messages ADD COLUMN correlation_id TEXT UNIQUE;  -- Links response to incoming
```

**Usage pattern:**
1. Container receives message with `correlation_id`
2. Before responding, container calls `claim_message_for_response(container_id, correlation_id)`
3. If claim succeeds, container sends response with `correlation_id` in request
4. If claim fails (another container claimed it), container skips response

**Note:** The claim is optional—containers can still send unsolicited messages without a correlation_id. The first-responder pattern only applies when responding to a specific incoming message.

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
      "pattern": "^task-[a-zA-Z0-9-]{1,64}$",
      "description": "Task identifier - format is flexible to allow future changes"
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

**task_id Format:**

The schema pattern `^task-[a-zA-Z0-9-]{1,64}$` is intentionally flexible to allow future format changes. The authoritative validation is performed against the `thread_mappings` table—a task_id must exist in the registry to be valid:

```python
def validate_task_id(task_id: str) -> bool:
    """Validate task_id exists in registry (not just format)."""
    # Schema validation catches format errors first
    if not re.match(r"^task-[a-zA-Z0-9-]{1,64}$", task_id):
        raise ValidationError("Invalid task_id format")

    # Registry validation is the authoritative check
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM thread_mappings WHERE task_id = ?",
            (task_id,)
        ).fetchone()
        if not row:
            raise ValidationError(f"task_id {task_id} not found in registry")

    return True
```

**Current format:** `task-YYYYMMDD-HHMMSS` (timestamp-based, e.g., `task-20260128-132707`)

**Future considerations:** The orchestrator may switch to UUID-based IDs (e.g., `task-f47ac10b-58cc`) for better uniqueness guarantees. The flexible schema and registry-based validation ensure this change won't break the gateway.

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

**Channel Validation Strategy:**

Determining `channel_type` requires a Slack API call (`conversations.info`). To balance security with performance, the gateway uses a two-tier approach:

1. **Explicit allowlist (preferred, most secure):**
   ```python
   # config.yaml
   slack:
     allowed_channels:
       - C01234567  # #jib-tasks
       - C89ABCDEF  # #jib-testing

   def validate_channel(channel_id: str) -> bool:
       # Explicit allowlist - no API call needed
       if channel_id in ALLOWED_CHANNELS:
           return True
       raise PolicyViolation(f"Channel {channel_id} not in allowlist")
   ```

2. **Cached type validation (fallback, less restrictive):**
   ```python
   # Cache channel info with 5-minute TTL
   channel_cache = TTLCache(maxsize=100, ttl=300)

   def get_channel_type(channel_id: str) -> str:
       if channel_id in channel_cache:
           return channel_cache[channel_id]

       # Fetch from Slack API
       info = slack_client.conversations_info(channel=channel_id)
       channel_type = "public_channel" if info["channel"]["is_channel"] else "private"
       channel_cache[channel_id] = channel_type
       return channel_type
   ```

**Recommendation:** Use explicit allowlist in production. The gateway is configured with specific channels during deployment; there's no need for dynamic discovery. Cached validation is available for development/testing environments where channels may vary.

**Security implications:**
- Explicit allowlist prevents channel type changes from bypassing validation
- 5-minute TTL on cache is short enough that channel type changes (rare) are caught quickly
- Both approaches are logged for audit

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

This section provides detailed, actionable implementation plans for each phase. The plans are designed to be self-contained—an implementer should be able to follow them without referring to the rest of the ADR for basic implementation decisions.

---

### Phase 1: Gateway Slack API (Foundation)

**Goal:** Add Slack API endpoints to existing gateway sidecar, running in parallel with the existing file-based system.

**Duration estimate:** 1 sprint (implementation) + 1 sprint (testing and stabilization)

#### 1.1 Gateway Dependencies

**File:** `gateway-sidecar/requirements.txt`

Add Slack SDK and SQLite dependencies:

```
# Existing dependencies
flask>=3.0.0
waitress>=3.0.0
pyyaml>=6.0.1
requests>=2.31.0

# New dependencies for Slack integration
slack-sdk>=3.27.0      # Slack SDK with Socket Mode support
slack-bolt>=1.18.0     # Slack Bolt framework for event handling
jsonschema>=4.21.0     # Schema validation for messages
```

#### 1.2 SQLite Database Setup

**New file:** `gateway-sidecar/slack_db.py`

Implements the message queue schema from the High-Level Design section:

```python
"""SQLite database for Slack message queue and thread mappings."""

import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

DB_PATH = os.environ.get("SLACK_DB_PATH", "/var/lib/gateway/slack.db")

@dataclass
class Message:
    id: str
    task_id: str
    thread_ts: str
    user_id: str
    user_name: str
    text: str
    received_at: datetime
    delivered_at: Optional[datetime]
    acked_at: Optional[datetime]
    status: str  # pending, delivered, acked, failed
    retry_count: int

@dataclass
class ThreadMapping:
    task_id: str
    thread_ts: str
    status: str  # active, closed, archived
    created_at: datetime
    updated_at: datetime
    created_by: str

def init_db():
    """Initialize database with schema."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
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

            CREATE TABLE IF NOT EXISTS thread_mappings (
                task_id TEXT PRIMARY KEY,
                thread_ts TEXT NOT NULL UNIQUE,
                status TEXT CHECK(status IN ('active', 'closed', 'archived')) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id TEXT PRIMARY KEY,
                original_message_id TEXT REFERENCES messages(id),
                task_id TEXT,
                failure_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_messages_task_status ON messages(task_id, status);
            CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_ts);
            CREATE INDEX IF NOT EXISTS idx_thread_mappings_thread ON thread_mappings(thread_ts);

            -- Immutability triggers for thread_mappings
            CREATE TRIGGER IF NOT EXISTS prevent_thread_ts_update
                BEFORE UPDATE OF thread_ts ON thread_mappings
                BEGIN
                    SELECT RAISE(ABORT, 'thread_ts is immutable');
                END;

            CREATE TRIGGER IF NOT EXISTS prevent_task_id_update
                BEFORE UPDATE OF task_id ON thread_mappings
                BEGIN
                    SELECT RAISE(ABORT, 'task_id is immutable');
                END;
        """)
        conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode

@contextmanager
def get_connection():
    """Get a database connection with proper error handling."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

#### 1.3 Slack Client Module

**New file:** `gateway-sidecar/slack_client.py`

Wraps the Slack SDK with credential management and error handling:

```python
"""Slack API client for gateway operations."""

import os
import logging
from typing import Optional, Dict, Any
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.errors import SlackApiError

log = logging.getLogger(__name__)

class SlackClient:
    """Gateway Slack client with credential isolation."""

    def __init__(self):
        self.bot_token = self._load_token("SLACK_TOKEN", "/secrets/slack-bot-token")
        self.app_token = self._load_token("SLACK_APP_TOKEN", "/secrets/slack-app-token")
        self.web_client = WebClient(token=self.bot_token)
        self.socket_client: Optional[SocketModeClient] = None

    def _load_token(self, env_var: str, file_path: str) -> str:
        """Load token from environment or file."""
        token = os.environ.get(env_var)
        if token:
            return token
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return f.read().strip()
        raise ValueError(f"Slack token not found: {env_var} or {file_path}")

    def send_message(
        self,
        channel: str,
        text: str,
        thread_ts: Optional[str] = None,
        mrkdwn: bool = True
    ) -> Dict[str, Any]:
        """Send a message to Slack."""
        try:
            response = self.web_client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts,
                mrkdwn=mrkdwn
            )
            return {
                "success": True,
                "message_ts": response["ts"],
                "thread_ts": response.get("thread_ts", thread_ts),
                "channel": response["channel"]
            }
        except SlackApiError as e:
            log.error(f"Slack API error: {e.response['error']}")
            return {
                "success": False,
                "error": e.response["error"]
            }

    def fetch_thread_messages(self, channel: str, thread_ts: str) -> list:
        """Fetch all messages in a thread."""
        try:
            response = self.web_client.conversations_replies(
                channel=channel,
                ts=thread_ts
            )
            return response.get("messages", [])
        except SlackApiError as e:
            log.error(f"Failed to fetch thread: {e.response['error']}")
            return []

    def start_socket_mode(self, message_handler):
        """Start Socket Mode client for receiving messages."""
        if not self.app_token:
            raise ValueError("Socket Mode requires SLACK_APP_TOKEN")

        self.socket_client = SocketModeClient(
            app_token=self.app_token,
            web_client=self.web_client
        )
        self.socket_client.socket_mode_request_listeners.append(
            lambda client, req: self._handle_socket_request(req, message_handler)
        )
        self.socket_client.connect()
        log.info("Socket Mode client connected")

    def _handle_socket_request(self, req: SocketModeRequest, handler) -> SocketModeResponse:
        """Handle incoming Socket Mode requests.

        IMPORTANT: Only ACK after successful persistence to prevent message loss.
        If persistence fails, we don't ACK and Slack will retry delivery.
        """
        if req.type == "events_api":
            event = req.payload.get("event", {})
            if event.get("type") == "app_mention" or event.get("type") == "message":
                try:
                    # Handler must complete successfully (including SQLite write) before ACK
                    handler(event)
                except sqlite3.Error as e:
                    # SQLite persistence failed - don't ACK, let Slack retry
                    log.error(f"Failed to persist message, not ACKing: {e}")
                    return None  # No response = no ACK, Slack will retry
                except Exception as e:
                    # Log but still ACK for non-persistence errors to avoid infinite retries
                    log.error(f"Handler error (will ACK anyway): {e}")

        # Only ACK after successful processing
        return SocketModeResponse(envelope_id=req.envelope_id)
```

#### 1.4 Gateway API Endpoints

**File:** `gateway-sidecar/gateway.py`

Add new Slack API endpoints alongside existing git endpoints:

```python
# Add to existing gateway.py imports
from slack_client import SlackClient
from slack_db import init_db, get_connection, Message, ThreadMapping
from jsonschema import validate, ValidationError
import uuid

# Initialize Slack components at startup
slack_client = SlackClient()
init_db()

# ==================== SLACK ENDPOINTS ====================

@app.route("/api/v1/slack/send", methods=["POST"])
@require_auth
def slack_send():
    """Send a message to Slack."""
    data = request.get_json()

    # Validate request schema
    try:
        validate(data, SLACK_SEND_SCHEMA)
    except ValidationError as e:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": str(e)}}), 400

    task_id = data["task_id"]
    text = data["text"]
    thread_ts = data.get("thread_ts")

    # Look up thread mapping if not provided
    if not thread_ts:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT thread_ts FROM thread_mappings WHERE task_id = ?",
                (task_id,)
            ).fetchone()
            if row:
                thread_ts = row["thread_ts"]

    # Get channel from config
    channel = app.config.get("SLACK_CHANNEL")

    # Send message
    result = slack_client.send_message(
        channel=channel,
        text=text,
        thread_ts=thread_ts,
        mrkdwn=data.get("markdown", True)
    )

    # Audit log
    audit_log(
        event_type="slack_operation",
        operation="send_message",
        task_id=task_id,
        thread_ts=thread_ts,
        success=result["success"]
    )

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify({"error": {"code": "SLACK_API_ERROR", "message": result["error"]}}), 502


@app.route("/api/v1/slack/messages", methods=["GET"])
@require_auth
def slack_get_messages():
    """Get messages for a task."""
    task_id = request.args.get("task_id")
    if not task_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "task_id required"}}), 400

    include_thread = request.args.get("include_thread", "false").lower() == "true"

    with get_connection() as conn:
        # Get messages for this task
        rows = conn.execute(
            """SELECT * FROM messages
               WHERE task_id = ? AND status IN ('pending', 'delivered')
               ORDER BY received_at ASC""",
            (task_id,)
        ).fetchall()

        messages = [dict(row) for row in rows]

        # Get thread context
        mapping_row = conn.execute(
            "SELECT * FROM thread_mappings WHERE task_id = ?",
            (task_id,)
        ).fetchone()

    task_context = None
    if mapping_row:
        task_context = {
            "task_id": task_id,
            "thread_ts": mapping_row["thread_ts"],
            "status": mapping_row["status"]
        }

    # Optionally fetch full thread history from Slack
    if include_thread and task_context:
        channel = app.config.get("SLACK_CHANNEL")
        thread_messages = slack_client.fetch_thread_messages(
            channel, task_context["thread_ts"]
        )
        # Merge with local messages
        # (implementation details omitted for brevity)

    audit_log(
        event_type="slack_operation",
        operation="get_messages",
        task_id=task_id,
        message_count=len(messages)
    )

    return jsonify({
        "messages": messages,
        "task_context": task_context
    }), 200


@app.route("/api/v1/slack/ack", methods=["POST"])
@require_auth
def slack_ack_message():
    """Acknowledge message receipt."""
    data = request.get_json()
    message_id = data.get("message_id")
    task_id = data.get("task_id")

    if not message_id or not task_id:
        return jsonify({"error": {"code": "VALIDATION_ERROR", "message": "message_id and task_id required"}}), 400

    with get_connection() as conn:
        conn.execute(
            """UPDATE messages SET status = 'acked', acked_at = CURRENT_TIMESTAMP
               WHERE id = ? AND task_id = ?""",
            (message_id, task_id)
        )

    audit_log(
        event_type="slack_operation",
        operation="ack_message",
        task_id=task_id,
        message_id=message_id
    )

    return jsonify({"success": True}), 200


# Schema definitions
SLACK_SEND_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["task_id", "text"],
    "properties": {
        "task_id": {"type": "string", "pattern": "^task-[0-9]{8}-[0-9]{6}$"},
        "thread_ts": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+$"},
        "text": {"type": "string", "minLength": 1, "maxLength": 4000},
        "markdown": {"type": "boolean", "default": True}
    },
    "additionalProperties": False
}
```

#### 1.5 Socket Mode Integration

**New file:** `gateway-sidecar/slack_receiver.py`

Handles incoming Slack messages via Socket Mode:

```python
"""Socket Mode message receiver for gateway."""

import logging
import uuid
from datetime import datetime
from slack_client import SlackClient
from slack_db import get_connection

log = logging.getLogger(__name__)

class SlackReceiver:
    """Receives messages from Slack and queues them for processing."""

    def __init__(self, slack_client: SlackClient, config: dict):
        self.slack_client = slack_client
        self.config = config
        self.allowed_channel = config.get("SLACK_CHANNEL")

    def start(self):
        """Start receiving messages."""
        self.slack_client.start_socket_mode(self.handle_message)
        log.info("Slack receiver started")

    def handle_message(self, event: dict):
        """Handle incoming Slack message event."""
        # Extract message details
        channel = event.get("channel")
        text = event.get("text", "")
        user_id = event.get("user")
        thread_ts = event.get("thread_ts") or event.get("ts")
        message_ts = event.get("ts")

        # Validate channel
        if channel != self.allowed_channel:
            log.debug(f"Ignoring message from channel {channel}")
            return

        # Skip bot messages
        if event.get("bot_id"):
            return

        # Generate task_id for new threads
        task_id = self._get_or_create_task_id(thread_ts)

        # Store message in queue
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO messages (id, task_id, thread_ts, user_id, user_name, text, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                (message_id, task_id, thread_ts, user_id, "", text)
            )

        log.info(f"Queued message {message_id} for task {task_id}")

    def _get_or_create_task_id(self, thread_ts: str) -> str:
        """Get existing task_id for thread or create new one."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT task_id FROM thread_mappings WHERE thread_ts = ?",
                (thread_ts,)
            ).fetchone()

            if row:
                return row["task_id"]

            # Create new task_id
            task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            conn.execute(
                """INSERT INTO thread_mappings (task_id, thread_ts, created_by)
                   VALUES (?, ?, 'gateway')""",
                (task_id, thread_ts)
            )
            log.info(f"Created new task mapping: {task_id} -> {thread_ts}")
            return task_id
```

#### 1.6 Gateway Entrypoint Update

**File:** `gateway-sidecar/entrypoint.sh`

Update to start Slack receiver alongside the API server:

```bash
#!/bin/bash
set -e

# Initialize database
python -c "from slack_db import init_db; init_db()"

# Start Slack Socket Mode receiver in background (if tokens available)
if [ -n "$SLACK_APP_TOKEN" ]; then
    echo "Starting Slack Socket Mode receiver..."
    python -c "
from slack_client import SlackClient
from slack_receiver import SlackReceiver
import os
client = SlackClient()
receiver = SlackReceiver(client, {'SLACK_CHANNEL': os.environ.get('SLACK_CHANNEL')})
receiver.start()
" &
    SLACK_PID=$!
    echo "Slack receiver started (PID: $SLACK_PID)"
fi

# Start gateway API server
echo "Starting gateway API server..."
exec python -m waitress --port=9847 --host=0.0.0.0 gateway:app
```

#### 1.7 Configuration Update

**File:** `gateway-sidecar/Dockerfile`

Add Slack-related mounts and environment:

```dockerfile
# Add to existing Dockerfile
ENV SLACK_DB_PATH=/var/lib/gateway/slack.db

# Create directory for SQLite database
RUN mkdir -p /var/lib/gateway && chown 1000:1000 /var/lib/gateway

# Copy schema files
COPY schemas/ /app/schemas/
```

**File:** `gateway-sidecar/start-gateway.sh`

Add Slack token mounts:

```bash
# Add to mount generation
if [ -f "$HOME/.config/jib/slack-tokens/bot-token" ]; then
    MOUNT_ARGS+=("-v" "$HOME/.config/jib/slack-tokens:/secrets/slack:ro")
fi
```

#### 1.8 Testing Phase 1

**New file:** `gateway-sidecar/tests/test_slack_api.py`

```python
"""Tests for Slack gateway API endpoints."""

import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_slack_client():
    with patch("gateway.slack_client") as mock:
        mock.send_message.return_value = {
            "success": True,
            "message_ts": "1234567890.123456",
            "thread_ts": "1234567890.000000"
        }
        yield mock

def test_slack_send_success(client, mock_slack_client):
    """Test successful message send."""
    response = client.post(
        "/api/v1/slack/send",
        json={
            "task_id": "task-20260128-120000",
            "text": "Test message"
        },
        headers={"Authorization": f"Bearer {TEST_SECRET}"}
    )
    assert response.status_code == 200
    assert response.json["success"] is True

def test_slack_send_validation_error(client):
    """Test schema validation."""
    response = client.post(
        "/api/v1/slack/send",
        json={"text": "Missing task_id"},
        headers={"Authorization": f"Bearer {TEST_SECRET}"}
    )
    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"

def test_slack_get_messages(client, mock_db):
    """Test message retrieval."""
    # Insert test message
    mock_db.execute(
        "INSERT INTO messages (id, task_id, thread_ts, text, status) VALUES (?, ?, ?, ?, ?)",
        ("msg-1", "task-20260128-120000", "1234.5678", "Test", "pending")
    )

    response = client.get(
        "/api/v1/slack/messages?task_id=task-20260128-120000",
        headers={"Authorization": f"Bearer {TEST_SECRET}"}
    )
    assert response.status_code == 200
    assert len(response.json["messages"]) == 1
```

**Integration test script:** `gateway-sidecar/tests/test_slack_integration.sh`

```bash
#!/bin/bash
# Integration tests for Slack gateway API

GATEWAY_URL="${GATEWAY_URL:-http://localhost:9847}"
AUTH_HEADER="Authorization: Bearer $GATEWAY_SECRET"

echo "=== Phase 1 Integration Tests ==="

# Test 1: Health check
echo "Test 1: Health check..."
curl -sf "$GATEWAY_URL/api/v1/health" || { echo "FAIL: Health check"; exit 1; }
echo "PASS"

# Test 2: Send message (requires valid Slack token)
echo "Test 2: Send message..."
RESPONSE=$(curl -sf -X POST "$GATEWAY_URL/api/v1/slack/send" \
    -H "$AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d '{"task_id": "task-20260128-120000", "text": "Integration test message"}')
if echo "$RESPONSE" | jq -e '.success == true' > /dev/null; then
    echo "PASS"
else
    echo "FAIL: $RESPONSE"
    exit 1
fi

# Test 3: Get messages
echo "Test 3: Get messages..."
RESPONSE=$(curl -sf "$GATEWAY_URL/api/v1/slack/messages?task_id=task-20260128-120000" \
    -H "$AUTH_HEADER")
if echo "$RESPONSE" | jq -e '.messages' > /dev/null; then
    echo "PASS"
else
    echo "FAIL: $RESPONSE"
    exit 1
fi

echo "=== All Phase 1 tests passed ==="
```

#### 1.9 Phase 1 Deliverables Checklist

- [ ] `gateway-sidecar/slack_db.py` - SQLite database module
- [ ] `gateway-sidecar/slack_client.py` - Slack SDK wrapper
- [ ] `gateway-sidecar/slack_receiver.py` - Socket Mode handler
- [ ] `gateway-sidecar/gateway.py` - Add Slack endpoints
- [ ] `gateway-sidecar/schemas/` - JSON schemas for validation
- [ ] `gateway-sidecar/requirements.txt` - Add Slack SDK
- [ ] `gateway-sidecar/Dockerfile` - Add SQLite path, schemas
- [ ] `gateway-sidecar/entrypoint.sh` - Start Slack receiver
- [ ] `gateway-sidecar/start-gateway.sh` - Mount Slack tokens
- [ ] `gateway-sidecar/tests/test_slack_api.py` - Unit tests
- [ ] `gateway-sidecar/tests/test_slack_integration.sh` - Integration tests
- [ ] Verify existing file-based system continues working unchanged

#### 1.9 Phase 1 Success Criteria and Rollback

**Success criteria to proceed to Phase 2:**
- Gateway Slack API endpoints return 200 for valid requests (>99% success rate over 1 week)
- SQLite persistence verified (messages survive gateway restart)
- Socket Mode connection stable (no unexpected disconnects over 24 hours)
- File-based system continues operating unchanged (no regressions)
- Unit and integration tests passing

**Rollback procedure (Phase 1 → Pre-Phase 1):**
1. Stop Slack Socket Mode receiver: `kill $SLACK_PID` or remove startup from entrypoint
2. Remove Slack API endpoints from `gateway.py` (revert to previous version)
3. Remove new dependencies from `requirements.txt`
4. Delete SQLite database: `rm /var/lib/gateway/slack.db`
5. Redeploy gateway without Slack components
6. Verify file-based system operational (no changes needed—it was never modified)

**Rollback triggers:**
- Gateway stability issues (restarts, OOM) after Slack integration
- Socket Mode connection failures affecting message delivery
- SQLite corruption or performance degradation

---

### Phase 2: Notification Library Migration

**Goal:** Update container-side code to use gateway API for sending notifications, with file-based fallback.

**Duration estimate:** 1 sprint

**Prerequisite:** Phase 1 complete and stable

#### 2.1 Gateway Slack Client for Container

**New file:** `shared/notifications/gateway_client.py`

Client library for containers to communicate with gateway Slack API:

```python
"""Gateway Slack client for container use."""

import os
import logging
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

log = logging.getLogger(__name__)

GATEWAY_URL = os.environ.get("JIB_GATEWAY_URL", "http://jib-gateway:9847")

@dataclass
class GatewayResponse:
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class GatewaySlackClient:
    """Client for gateway Slack API."""

    def __init__(self):
        self.gateway_url = GATEWAY_URL
        self.secret = self._load_secret()
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.secret}"
        self.session.headers["Content-Type"] = "application/json"

    def _load_secret(self) -> str:
        """Load gateway shared secret."""
        secret_path = os.environ.get(
            "GATEWAY_SECRET_PATH",
            os.path.expanduser("~/.jib-sharing/.gateway-secret")
        )
        if os.path.exists(secret_path):
            with open(secret_path, "r") as f:
                return f.read().strip()
        raise ValueError(f"Gateway secret not found at {secret_path}")

    def send_message(
        self,
        task_id: str,
        text: str,
        thread_ts: Optional[str] = None,
        markdown: bool = True
    ) -> GatewayResponse:
        """Send a message via gateway."""
        try:
            response = self.session.post(
                f"{self.gateway_url}/api/v1/slack/send",
                json={
                    "task_id": task_id,
                    "text": text,
                    "thread_ts": thread_ts,
                    "markdown": markdown
                },
                timeout=30
            )
            if response.status_code == 200:
                return GatewayResponse(success=True, data=response.json())
            else:
                return GatewayResponse(
                    success=False,
                    error=response.json().get("error", {}).get("message", "Unknown error")
                )
        except requests.RequestException as e:
            log.error(f"Gateway request failed: {e}")
            return GatewayResponse(success=False, error=str(e))

    def get_messages(
        self,
        task_id: str,
        include_thread: bool = False
    ) -> GatewayResponse:
        """Get messages for a task from gateway."""
        try:
            response = self.session.get(
                f"{self.gateway_url}/api/v1/slack/messages",
                params={
                    "task_id": task_id,
                    "include_thread": str(include_thread).lower()
                },
                timeout=30
            )
            if response.status_code == 200:
                return GatewayResponse(success=True, data=response.json())
            else:
                return GatewayResponse(
                    success=False,
                    error=response.json().get("error", {}).get("message", "Unknown error")
                )
        except requests.RequestException as e:
            log.error(f"Gateway request failed: {e}")
            return GatewayResponse(success=False, error=str(e))

    def ack_message(self, task_id: str, message_id: str) -> GatewayResponse:
        """Acknowledge message receipt."""
        try:
            response = self.session.post(
                f"{self.gateway_url}/api/v1/slack/ack",
                json={"task_id": task_id, "message_id": message_id},
                timeout=10
            )
            return GatewayResponse(success=response.status_code == 200)
        except requests.RequestException as e:
            return GatewayResponse(success=False, error=str(e))

    def is_available(self) -> bool:
        """Check if gateway is available."""
        try:
            response = self.session.get(
                f"{self.gateway_url}/api/v1/health",
                timeout=5
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
```

#### 2.2 Update SlackNotificationService

**File:** `shared/notifications/slack.py`

Update to use gateway API with file-based fallback:

```python
"""Slack notification service with gateway API support."""

import os
import logging
from typing import Optional
from datetime import datetime

from .gateway_client import GatewaySlackClient, GatewayResponse
from .types import NotificationMessage, NotificationContext, NotificationResult

log = logging.getLogger(__name__)

class SlackNotificationService:
    """Slack notification service with gateway fallback."""

    def __init__(self, use_gateway: bool = True):
        self.use_gateway = use_gateway and self._gateway_available()
        self.gateway_client = GatewaySlackClient() if self.use_gateway else None
        self.notifications_dir = os.path.expanduser("~/sharing/notifications")

    def _gateway_available(self) -> bool:
        """Check if gateway is available."""
        try:
            client = GatewaySlackClient()
            return client.is_available()
        except Exception as e:
            log.warning(f"Gateway not available: {e}")
            return False

    def notify(
        self,
        subject: str,
        body: str,
        context: Optional[NotificationContext] = None
    ) -> NotificationResult:
        """Send a notification."""
        task_id = context.task_id if context else self._generate_task_id()
        thread_ts = context.thread_ts if context else None

        # Format message
        text = f"# {subject}\n\n{body}"

        # Try gateway first
        if self.use_gateway and self.gateway_client:
            result = self.gateway_client.send_message(
                task_id=task_id,
                text=text,
                thread_ts=thread_ts
            )
            if result.success:
                log.info(f"Notification sent via gateway: {task_id}")
                return NotificationResult(
                    success=True,
                    thread_id=result.data.get("thread_ts"),
                    message_ts=result.data.get("message_ts")
                )
            else:
                log.warning(f"Gateway send failed, falling back to file: {result.error}")

        # Fallback to file-based
        return self._write_notification_file(task_id, thread_ts, text)

    def _write_notification_file(
        self,
        task_id: str,
        thread_ts: Optional[str],
        text: str
    ) -> NotificationResult:
        """Write notification to file (fallback method)."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-notification.md"
        filepath = os.path.join(self.notifications_dir, filename)

        # Build frontmatter
        frontmatter = f"---\ntask_id: \"{task_id}\"\n"
        if thread_ts:
            frontmatter += f"thread_ts: \"{thread_ts}\"\n"
        frontmatter += "---\n\n"

        content = frontmatter + text

        os.makedirs(self.notifications_dir, exist_ok=True)
        with open(filepath, "w") as f:
            f.write(content)

        log.info(f"Notification written to file: {filepath}")
        return NotificationResult(success=True, file_path=filepath)

    def _generate_task_id(self) -> str:
        """Generate a new task_id."""
        return f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
```

#### 2.3 Update incoming-processor

**File:** `jib-container/jib-tasks/slack/incoming-processor.py`

Update to fetch messages from gateway:

```python
# Add to imports
from shared.notifications.gateway_client import GatewaySlackClient

# Update process_task function to check gateway first
def get_task_messages(task_id: str, thread_ts: str) -> list:
    """Get messages for task, preferring gateway API."""
    # Try gateway first
    try:
        client = GatewaySlackClient()
        if client.is_available():
            result = client.get_messages(task_id, include_thread=True)
            if result.success:
                return result.data.get("messages", [])
    except Exception as e:
        log.warning(f"Gateway unavailable, using file: {e}")

    # Fallback to file-based
    return get_messages_from_files(task_id, thread_ts)

# Update message acknowledgment
def ack_message(task_id: str, message_id: str):
    """Acknowledge message processing."""
    try:
        client = GatewaySlackClient()
        if client.is_available():
            client.ack_message(task_id, message_id)
    except Exception:
        pass  # Acknowledgment is best-effort
```

#### 2.4 Testing Phase 2

**New file:** `shared/notifications/tests/test_gateway_client.py`

```python
"""Tests for gateway Slack client."""

import pytest
from unittest.mock import Mock, patch

from notifications.gateway_client import GatewaySlackClient, GatewayResponse

@pytest.fixture
def mock_requests():
    with patch("notifications.gateway_client.requests") as mock:
        yield mock

def test_send_message_success(mock_requests):
    """Test successful message send via gateway."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "success": True,
        "message_ts": "1234567890.123456"
    }
    mock_requests.Session.return_value.post.return_value = mock_response

    client = GatewaySlackClient()
    result = client.send_message(
        task_id="task-20260128-120000",
        text="Test message"
    )

    assert result.success is True
    assert result.data["message_ts"] == "1234567890.123456"

def test_send_message_fallback_on_error(mock_requests):
    """Test that errors are properly reported."""
    mock_requests.Session.return_value.post.side_effect = Exception("Connection refused")

    client = GatewaySlackClient()
    result = client.send_message(
        task_id="task-20260128-120000",
        text="Test message"
    )

    assert result.success is False
    assert "Connection refused" in result.error
```

#### 2.5 Feature Flag

**File:** `shared/jib_config/configs/slack.py`

Add feature flag for gateway mode:

```python
# Add to slack configuration
SLACK_USE_GATEWAY = os.environ.get("SLACK_USE_GATEWAY", "true").lower() == "true"
```

#### 2.6 Phase 2 Deliverables Checklist

- [ ] `shared/notifications/gateway_client.py` - Gateway client library
- [ ] `shared/notifications/slack.py` - Update with gateway support
- [ ] `jib-container/jib-tasks/slack/incoming-processor.py` - Update message fetching
- [ ] `shared/jib_config/configs/slack.py` - Add feature flag
- [ ] `shared/notifications/tests/test_gateway_client.py` - Unit tests
- [ ] Integration test: Send notification via gateway
- [ ] Integration test: Fallback to file when gateway unavailable
- [ ] Documentation: Update README with new configuration options

#### 2.7 Phase 2 Success Criteria and Rollback

**Success criteria to proceed to Phase 3:**
- Gateway-based notifications working (>99.9% delivery success rate over 1 week)
- Fallback mechanism tested and operational
- No increase in notification latency (P99 < 500ms)
- Container logs show gateway being used as primary path

**Rollback procedure (Phase 2 → Phase 1):**
1. Set feature flag: `SLACK_USE_GATEWAY=false`
2. Restart affected containers
3. Verify file-based notifications resume
4. (Optional) Revert library changes if feature flag insufficient

**Rollback triggers:**
- Gateway notification delivery failures exceed 1%
- Notification latency increases significantly (P99 > 2s)
- Container-to-gateway connectivity issues

---

### Phase 3: File Access Removal

**Goal:** Remove direct file access from container for Slack operations.

**Duration estimate:** 1 sprint (changes) + 1 sprint (validation)

**Prerequisite:** Phase 2 complete and stable, gateway is reliable

#### 3.1 Remove Slack File Mounts

**File:** `jib-container/jib_lib/runtime.py`

Update container launch to remove Slack-related mounts:

```python
def _build_mount_args(config: Config) -> list[str]:
    """Build Docker mount arguments."""
    mounts = []

    # Keep these mounts
    mounts.extend(["-v", f"{config.repos_dir}:/home/jib/repos:rw"])
    mounts.extend(["-v", f"{config.beads_dir}:/home/jib/beads:rw"])
    mounts.extend(["-v", f"{config.sharing_dir}/logs:/home/jib/sharing/logs:rw"])
    mounts.extend(["-v", f"{config.sharing_dir}/tracking:/home/jib/sharing/tracking:rw"])
    mounts.extend(["-v", f"{config.sharing_dir}/context:/home/jib/sharing/context:rw"])
    mounts.extend(["-v", f"{config.sharing_dir}/.gateway-secret:/home/jib/.jib-sharing/.gateway-secret:ro"])

    # REMOVED: These mounts are no longer needed
    # mounts.extend(["-v", f"{config.sharing_dir}/incoming:/home/jib/sharing/incoming:ro"])
    # mounts.extend(["-v", f"{config.sharing_dir}/responses:/home/jib/sharing/responses:ro"])
    # mounts.extend(["-v", f"{config.sharing_dir}/notifications:/home/jib/sharing/notifications:rw"])

    return mounts
```

#### 3.2 Update Orchestrator

**File:** `host-services/orchestration/jib_exec.py`

Update task invocation to use gateway instead of file paths:

```python
def start_task(task_id: str, thread_ts: str, message: str) -> str:
    """Start a task via gateway API."""
    # Register container with gateway BEFORE starting container
    gateway_client = GatewayClient()
    registration = gateway_client.register_container(
        container_id=generate_container_id(),
        task_id=task_id,
        ttl_hours=4
    )

    if not registration.success:
        raise RuntimeError(f"Failed to register container: {registration.error}")

    # Start container with registration token
    container_id = start_container(
        task_id=task_id,
        registration_token=registration.data["token"],
        env={
            "JIB_TASK_ID": task_id,
            "JIB_THREAD_TS": thread_ts,
            "SLACK_USE_GATEWAY": "true"
        }
    )

    return container_id
```

#### 3.3 Remove File-Based Fallback Code

**File:** `shared/notifications/slack.py`

Remove file-based fallback after gateway is proven stable:

```python
class SlackNotificationService:
    """Slack notification service using gateway API only."""

    def __init__(self):
        self.gateway_client = GatewaySlackClient()
        if not self.gateway_client.is_available():
            raise RuntimeError("Gateway not available - cannot initialize notification service")

    def notify(
        self,
        subject: str,
        body: str,
        context: Optional[NotificationContext] = None
    ) -> NotificationResult:
        """Send a notification via gateway."""
        task_id = context.task_id if context else self._generate_task_id()
        thread_ts = context.thread_ts if context else None

        text = f"# {subject}\n\n{body}"

        result = self.gateway_client.send_message(
            task_id=task_id,
            text=text,
            thread_ts=thread_ts
        )

        if not result.success:
            raise NotificationError(f"Failed to send notification: {result.error}")

        return NotificationResult(
            success=True,
            thread_id=result.data.get("thread_ts"),
            message_ts=result.data.get("message_ts")
        )
```

#### 3.4 Remove Host Slack Services

**Phase 3b:** After confirming gateway stability, remove host services:

**Files to remove:**
- `host-services/slack/slack-receiver/` (entire directory)
- `host-services/slack/slack-notifier/` (entire directory)

**Systemd units to disable:**
- `slack-receiver.service`
- `slack-notifier.service`

**Note:** Keep a backup branch of these services for rollback purposes.

#### 3.5 Update CLAUDE.md

**File:** Root `CLAUDE.md` and container `CLAUDE.md`

Update file path references:

```markdown
## File System (Post-Phase 3)

| Path | Purpose |
|------|---------|
| `~/repos/` | Code workspace (RW) |
| `~/beads/` | Task memory |
| `~/sharing/logs/` | Debug logs (RW) |
| `~/sharing/tracking/` | Beads state (RW) |
| `~/sharing/context/` | Context sync data (RW) |

**Removed (now via gateway API):**
- `~/sharing/incoming/` - Tasks received via gateway API
- `~/sharing/responses/` - Responses sent via gateway API
- `~/sharing/notifications/` - Notifications sent via gateway API

## Notifications

Use the notifications library for Slack messages:
```python
from notifications import slack_notify
slack_notify("Subject", "Body")  # Sends via gateway API
```

File-based notifications are no longer supported.
```

#### 3.6 Rollback Plan

If issues are discovered after Phase 3 deployment:

```bash
# Quick rollback: Re-enable file mounts
# Edit jib_lib/runtime.py to restore mount lines

# Full rollback: Restore host services
git checkout pre-phase3-backup -- host-services/slack/
systemctl --user enable slack-receiver.service
systemctl --user enable slack-notifier.service
systemctl --user start slack-receiver.service
systemctl --user start slack-notifier.service

# Container: Re-enable fallback
export SLACK_USE_GATEWAY=false
```

#### 3.7 Phase 3 Deliverables Checklist

- [ ] `jib-container/jib_lib/runtime.py` - Remove Slack file mounts
- [ ] `host-services/orchestration/jib_exec.py` - Update task invocation
- [ ] `shared/notifications/slack.py` - Remove file fallback
- [ ] `CLAUDE.md` - Update file path documentation
- [ ] Remove `host-services/slack/` directory (Phase 3b)
- [ ] Disable `slack-receiver.service` (Phase 3b)
- [ ] Disable `slack-notifier.service` (Phase 3b)
- [ ] Create rollback branch with host services
- [ ] Integration test: Full workflow without file mounts
- [ ] Load test: High-volume message processing

---

### Phase 4: Task Authorization

**Goal:** Implement task-scoped message access control.

**Duration estimate:** 1.5 sprints

**Prerequisite:** Phase 3 complete

#### 4.1 Container Registration API

**File:** `gateway-sidecar/gateway.py`

Add internal registration endpoint:

```python
# Internal API for orchestrator (separate auth)
ADMIN_SECRET = os.environ.get("GATEWAY_ADMIN_SECRET")

def require_admin_auth(f):
    """Decorator for admin-only endpoints."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth[7:]
        if not secrets.compare_digest(token, ADMIN_SECRET):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@app.route("/internal/register", methods=["POST"])
@require_admin_auth
def register_container():
    """Register a container for task access."""
    data = request.get_json()
    container_id = data.get("container_id")
    task_id = data.get("task_id")
    ttl_hours = data.get("ttl_hours", 4)

    if not container_id or not task_id:
        return jsonify({"error": "container_id and task_id required"}), 400

    # Generate one-time registration token
    registration_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO container_registrations
               (container_id, task_id, registration_token, expires_at, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (container_id, task_id, registration_token, expires_at)
        )

    audit_log(
        event_type="container_registration",
        operation="register",
        container_id=container_id,
        task_id=task_id,
        ttl_hours=ttl_hours
    )

    return jsonify({
        "success": True,
        "token": registration_token,
        "expires_at": expires_at.isoformat()
    }), 200


@app.route("/internal/activate", methods=["POST"])
@require_auth
def activate_registration():
    """Activate container registration (called by container on first API call).

    Requires HMAC proof to prevent replay attacks during the registration window.
    The container must provide HMAC(shared_secret, registration_token) as proof.
    """
    data = request.get_json()
    registration_token = data.get("registration_token")
    activation_proof = request.headers.get("X-Activation-Proof")

    if not activation_proof:
        return jsonify({"error": "Missing activation proof header"}), 400

    # Get shared secret from request auth
    auth = request.headers.get("Authorization", "")
    shared_secret = auth[7:] if auth.startswith("Bearer ") else ""

    # Verify HMAC proof: HMAC(shared_secret, registration_token)
    expected_proof = hmac.new(
        shared_secret.encode(),
        registration_token.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_proof, activation_proof):
        audit_log(
            event_type="activation_proof_mismatch",
            token_prefix=registration_token[:8] if registration_token else None
        )
        return jsonify({"error": "Invalid activation proof"}), 401

    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM container_registrations
               WHERE registration_token = ? AND status = 'pending' AND expires_at > CURRENT_TIMESTAMP""",
            (registration_token,)
        ).fetchone()

        if not row:
            return jsonify({"error": "Invalid or expired registration token"}), 401

        # Check activation window (30 seconds from creation)
        created_at = datetime.fromisoformat(row["created_at"])
        activation_window = timedelta(seconds=30)
        if datetime.utcnow() > created_at + activation_window:
            audit_log(
                event_type="activation_window_expired",
                container_id=row["container_id"],
                task_id=row["task_id"]
            )
            return jsonify({"error": "Activation window expired"}), 401

        # Activate the registration
        conn.execute(
            """UPDATE container_registrations
               SET status = 'active', activated_at = CURRENT_TIMESTAMP
               WHERE registration_token = ?""",
            (registration_token,)
        )

    audit_log(
        event_type="container_registration",
        operation="activate",
        container_id=row["container_id"],
        task_id=row["task_id"]
    )

    return jsonify({
        "success": True,
        "container_id": row["container_id"],
        "task_id": row["task_id"]
    }), 200
```

#### 4.2 Task Authorization Enforcement

**File:** `gateway-sidecar/gateway.py`

Update Slack endpoints to check task authorization:

```python
def get_container_task_authorization(request) -> tuple[str, str]:
    """Extract and validate container authorization.

    Returns (container_id, task_id) if authorized.
    Raises Unauthorized if not.
    """
    # Get container identity from request
    container_id = request.headers.get("X-Container-ID")
    task_id = request.headers.get("X-Task-ID") or request.args.get("task_id")

    if not container_id or not task_id:
        raise Unauthorized("Missing container or task identification")

    # Check authorization
    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM container_registrations
               WHERE container_id = ? AND task_id = ? AND status = 'active' AND expires_at > CURRENT_TIMESTAMP""",
            (container_id, task_id)
        ).fetchone()

        if not row:
            audit_log(
                event_type="authorization_failure",
                container_id=container_id,
                task_id=task_id
            )
            raise Unauthorized(f"Container {container_id} not authorized for task {task_id}")

    return container_id, task_id


@app.route("/api/v1/slack/messages", methods=["GET"])
@require_auth
def slack_get_messages():
    """Get messages for a task (with authorization check)."""
    container_id, task_id = get_container_task_authorization(request)

    # ... rest of implementation ...
```

#### 4.3 Database Schema Update

**File:** `gateway-sidecar/slack_db.py`

Add container registrations table:

```python
def init_db():
    """Initialize database with schema."""
    with get_connection() as conn:
        conn.executescript("""
            -- Existing tables ...

            CREATE TABLE IF NOT EXISTS container_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                container_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                registration_token TEXT UNIQUE NOT NULL,
                status TEXT CHECK(status IN ('pending', 'active', 'expired', 'revoked')) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activated_at TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                UNIQUE(container_id, task_id)
            );

            CREATE INDEX IF NOT EXISTS idx_registrations_container ON container_registrations(container_id);
            CREATE INDEX IF NOT EXISTS idx_registrations_task ON container_registrations(task_id);
            CREATE INDEX IF NOT EXISTS idx_registrations_token ON container_registrations(registration_token);
        """)
```

#### 4.4 Container Startup Integration

**File:** `jib-container/entrypoint.py`

Add registration activation on startup:

```python
import hmac
import hashlib

def activate_task_registration():
    """Activate container registration with gateway.

    Includes HMAC proof to prevent replay attacks:
    X-Activation-Proof = HMAC(shared_secret, registration_token)
    """
    registration_token = os.environ.get("JIB_REGISTRATION_TOKEN")
    if not registration_token:
        log.warning("No registration token - running without task authorization")
        return

    gateway_url = os.environ.get("JIB_GATEWAY_URL", "http://jib-gateway:9847")
    secret = load_gateway_secret()

    # Generate HMAC proof binding registration token to our shared secret
    activation_proof = hmac.new(
        secret.encode(),
        registration_token.encode(),
        hashlib.sha256
    ).hexdigest()

    try:
        response = requests.post(
            f"{gateway_url}/internal/activate",
            json={"registration_token": registration_token},
            headers={
                "Authorization": f"Bearer {secret}",
                "X-Activation-Proof": activation_proof
            },
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            os.environ["JIB_CONTAINER_ID"] = data["container_id"]
            log.info(f"Registration activated for task {data['task_id']}")
        else:
            log.error(f"Registration activation failed: {response.text}")
            sys.exit(1)
    except requests.RequestException as e:
        log.error(f"Failed to activate registration: {e}")
        sys.exit(1)


# Call during startup
if __name__ == "__main__":
    wait_for_gateway()
    activate_task_registration()
    main()
```

#### 4.5 Update Gateway Client

**File:** `shared/notifications/gateway_client.py`

Add container identification headers:

```python
class GatewaySlackClient:
    """Client for gateway Slack API with task authorization."""

    def __init__(self):
        self.gateway_url = GATEWAY_URL
        self.secret = self._load_secret()
        self.container_id = os.environ.get("JIB_CONTAINER_ID")
        self.task_id = os.environ.get("JIB_TASK_ID")

        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.secret}"
        self.session.headers["Content-Type"] = "application/json"

        # Add container identification
        if self.container_id:
            self.session.headers["X-Container-ID"] = self.container_id
        if self.task_id:
            self.session.headers["X-Task-ID"] = self.task_id
```

#### 4.6 Testing Phase 4

**New file:** `gateway-sidecar/tests/test_task_authorization.py`

```python
"""Tests for task authorization."""

import pytest
from unittest.mock import Mock

def test_unauthorized_container_rejected(client):
    """Test that unauthorized containers cannot access messages."""
    response = client.get(
        "/api/v1/slack/messages?task_id=task-20260128-120000",
        headers={
            "Authorization": f"Bearer {TEST_SECRET}",
            "X-Container-ID": "unauthorized-container",
            "X-Task-ID": "task-20260128-120000"
        }
    )
    assert response.status_code == 401


def test_authorized_container_allowed(client, mock_db):
    """Test that authorized containers can access messages."""
    # Register container
    mock_db.execute(
        """INSERT INTO container_registrations
           (container_id, task_id, registration_token, status, expires_at)
           VALUES (?, ?, ?, 'active', datetime('now', '+1 hour'))""",
        ("test-container", "task-20260128-120000", "token123")
    )

    response = client.get(
        "/api/v1/slack/messages?task_id=task-20260128-120000",
        headers={
            "Authorization": f"Bearer {TEST_SECRET}",
            "X-Container-ID": "test-container",
            "X-Task-ID": "task-20260128-120000"
        }
    )
    assert response.status_code == 200


def test_expired_registration_rejected(client, mock_db):
    """Test that expired registrations are rejected."""
    # Register container with expired timestamp
    mock_db.execute(
        """INSERT INTO container_registrations
           (container_id, task_id, registration_token, status, expires_at)
           VALUES (?, ?, ?, 'active', datetime('now', '-1 hour'))""",
        ("test-container", "task-20260128-120000", "token123")
    )

    response = client.get(
        "/api/v1/slack/messages?task_id=task-20260128-120000",
        headers={
            "Authorization": f"Bearer {TEST_SECRET}",
            "X-Container-ID": "test-container",
            "X-Task-ID": "task-20260128-120000"
        }
    )
    assert response.status_code == 401
```

#### 4.7 Phase 4 Deliverables Checklist

- [ ] `gateway-sidecar/gateway.py` - Add registration and authorization endpoints
- [ ] `gateway-sidecar/slack_db.py` - Add container_registrations table
- [ ] `host-services/orchestration/jib_exec.py` - Register containers before start
- [ ] `jib-container/entrypoint.py` - Activate registration on startup
- [ ] `shared/notifications/gateway_client.py` - Add container headers
- [ ] `gateway-sidecar/tests/test_task_authorization.py` - Authorization tests
- [ ] Integration test: Full registration → activation → access flow
- [ ] Security test: Verify cross-task access is blocked
- [ ] Audit log review: Confirm all authorization decisions logged

#### 4.8 Phase 4 Success Criteria and Rollback

**Success criteria for completion:**
- All containers successfully register and activate (>99.9% success rate over 1 week)
- Cross-task access attempts logged and blocked (verified via audit logs)
- No false positives (legitimate access never blocked)
- Registration latency acceptable (P99 < 200ms)
- Activation proof validation working (HMAC verification succeeds)

**Rollback procedure (Phase 4 → Phase 3):**
1. Disable authorization checks in gateway (set `REQUIRE_TASK_AUTH=false`)
2. Remove container registration from orchestrator
3. Remove activation from container entrypoint
4. Redeploy containers without registration headers
5. Gateway continues to serve Slack API without authorization checks

**Rollback triggers:**
- Registration failures blocking container startup
- False positives preventing legitimate message access
- Gateway performance degradation under authorization load
- HMAC validation failures due to timing/synchronization issues

---

### Migration Path Summary

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        Migration Timeline                                        │
│                                                                                  │
│  Current State                                                                   │
│  ├─ slack-receiver (host) → ~/sharing/incoming/ → container reads files         │
│  └─ container → ~/sharing/notifications/ → slack-notifier (host) → Slack        │
│                                                                                  │
│  Phase 1: Gateway API (2 sprints)                                               │
│  ├─ Gateway receives Slack messages via Socket Mode                             │
│  ├─ Gateway stores messages in SQLite                                           │
│  ├─ Gateway API endpoints available but not used yet                            │
│  └─ Existing file-based system continues unchanged                              │
│                                                                                  │
│  Phase 2: Library Migration (1 sprint)                                          │
│  ├─ Container notification library uses gateway API                             │
│  ├─ incoming-processor fetches messages from gateway                            │
│  ├─ File-based system available as fallback                                     │
│  └─ Feature flag: SLACK_USE_GATEWAY=true (default)                              │
│                                                                                  │
│  Phase 3: File Removal (2 sprints)                                              │
│  ├─ Remove ~/sharing/incoming/, responses/, notifications/ mounts               │
│  ├─ Remove file-based fallback code                                             │
│  ├─ Disable host slack-receiver and slack-notifier services                     │
│  └─ Update CLAUDE.md documentation                                              │
│                                                                                  │
│  Phase 4: Task Authorization (1.5 sprints)                                      │
│  ├─ Orchestrator registers containers with gateway before start                 │
│  ├─ Containers activate registration on first API call                          │
│  ├─ Gateway enforces task-scoped access on all Slack endpoints                  │
│  └─ Unauthorized access attempts logged and blocked                             │
│                                                                                  │
│  Final State                                                                     │
│  ├─ gateway ← Slack (Socket Mode)                                               │
│  ├─ gateway ↔ container (REST API, task-authorized)                            │
│  ├─ gateway → Slack (API, rate-limited)                                         │
│  └─ Full audit trail of all Slack operations                                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Implementation Checklist (All Phases)

**Phase 1: Gateway Slack API**
- [ ] Add Slack SDK dependencies
- [ ] Implement SQLite database module
- [ ] Implement Slack client wrapper
- [ ] Implement Socket Mode receiver
- [ ] Add `/api/v1/slack/send` endpoint
- [ ] Add `/api/v1/slack/messages` endpoint
- [ ] Add `/api/v1/slack/ack` endpoint
- [ ] Update gateway entrypoint
- [ ] Add Slack token mounts
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Verify existing system unaffected

**Phase 2: Notification Library Migration**
- [ ] Implement GatewaySlackClient
- [ ] Update SlackNotificationService with gateway support
- [ ] Update incoming-processor to use gateway
- [ ] Add feature flag
- [ ] Write unit tests
- [ ] Test fallback behavior

**Phase 3: File Access Removal**
- [ ] Remove Slack file mounts from container
- [ ] Update orchestrator
- [ ] Remove file-based fallback
- [ ] Update CLAUDE.md
- [ ] Disable host Slack services
- [ ] Write rollback documentation
- [ ] Load testing

**Phase 4: Task Authorization**
- [ ] Add container_registrations table
- [ ] Implement registration API
- [ ] Implement activation flow
- [ ] Add authorization checks to all endpoints
- [ ] Update container startup
- [ ] Update gateway client
- [ ] Security testing
- [ ] Audit log verification

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
