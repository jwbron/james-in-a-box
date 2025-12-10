# ADR: Jib Web Service Architecture - Unified REST API

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, jib (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** December 2025
**Status:** Proposed

## Table of Contents

- [Current Implementation Status](#current-implementation-status)
- [Relationship to Other ADRs](#relationship-to-other-adrs)
- [Context](#context)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
- [API Design](#api-design)
- [Task Classification System](#task-classification-system)
- [Cost Analysis](#cost-analysis)
- [Worked Example](#worked-example)
- [Security Considerations](#security-considerations)
- [State Management Strategy](#state-management-strategy)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)

## Current Implementation Status

**Not yet implemented.** This ADR proposes a fundamental architecture rework.

**Current State:**
- Docker-based sandbox running on local laptop
- Multiple entry points: `jib` CLI, Slack receiver, systemd services
- File-based communication (notifications, incoming tasks)
- Host services for sync and analysis

**Proposed State:**
- Single REST API endpoint that handles all task types
- Intelligent task routing based on input analysis
- Deployable as web service (Cloud Run, Kubernetes, etc.)
- Unified interface for all clients (Slack, CLI, web, mobile)

## Relationship to Other ADRs

This ADR focuses on the **API and deployment layer** and is designed to work with (not replace) other architectural decisions:

### ADR-Multi-Agent-Pipeline-Architecture

**Relationship:** Complementary, not competing.

| This ADR (Web Service) | Multi-Agent Pipeline ADR |
|------------------------|--------------------------|
| How tasks enter the system | How tasks are executed internally |
| API endpoint design | Agent orchestration patterns |
| Cloud deployment model | Execution patterns (sequential, parallel) |
| Request classification | Task decomposition and specialization |

**Integration Model:**

```
Client Request → API Gateway → Task Classifier → Multi-Agent Pipeline
                                     │
                                     ├─ Simple tasks: Single-agent execution
                                     └─ Complex tasks: Pipeline Orchestrator
                                            ├─ Planner Agent
                                            ├─ Implementer Agent
                                            ├─ Reviewer Agent
                                            └─ etc.
```

The **Task Classifier** in this ADR can be viewed as the entry point that decides:
1. Whether a task needs single-agent or multi-agent execution
2. Which pipeline pattern to invoke (if multi-agent)
3. Initial context requirements

If Multi-Agent Pipeline Architecture is adopted, the Classifier becomes the **first stage** that routes to the Pipeline Orchestrator for complex tasks, while simple queries (conversations, quick lookups) bypass the pipeline entirely.

**Explicit Design Decision:** This ADR does NOT supersede ADR-Multi-Agent-Pipeline-Architecture. They address different layers of the system.

### ADR-Autonomous-Software-Engineer

**Relationship:** This ADR extends the parent architecture by defining the API interface layer.

Key inherited constraints:
- Docker sandbox security model (preserved)
- Human-in-the-loop controls (maintained)
- Credential isolation (unchanged)

## Context

### Background

**Problem Statement:**

The current jib architecture evolved organically with multiple entry points:

1. **`jib` CLI** - Interactive sessions, `--exec` for one-shot tasks
2. **Slack receiver** - Processes incoming messages via file-based queue
3. **Host services** - Systemd timers for sync, analysis, notifications
4. **Watchers** - Context-specific processors (GitHub, JIRA, Confluence)

This creates several challenges:

| Challenge | Impact |
|-----------|--------|
| **Multiple entry points** | Different code paths, inconsistent behavior |
| **Host dependencies** | Tied to laptop with systemd, file watchers |
| **Complex deployment** | Many moving parts to orchestrate |
| **Limited scalability** | Single-user, single-machine |
| **Difficult integration** | Each client needs custom integration |

**Opportunity:**

A unified REST API would:
1. Simplify architecture to a single entry point
2. Enable deployment as a cloud service
3. Support multiple clients through one interface
4. Allow intelligent task routing at the API layer
5. Scale horizontally for multiple users/teams

### What We're Deciding

This ADR establishes the architecture for reworking jib as a web service with:

1. **Single REST API endpoint** accepting all task types
2. **Intelligent task classification** determining how to process input
3. **Unified execution model** regardless of task source
4. **Cloud-native deployment** supporting multiple platforms

### Goals

**Primary Goals:**
1. **Single Interface:** One API to rule them all
2. **Intelligent Routing:** Claude determines task type from input
3. **Cloud Deployable:** Run on Cloud Run, Kubernetes, or any container platform
4. **Stateless Design:** Enable horizontal scaling
5. **Multi-Client Support:** Slack, CLI, web, mobile through same API

**Non-Goals:**
- Changing how Claude Code processes tasks internally
- Removing Docker sandboxing (security model remains)
- Breaking existing Slack/CLI workflows (migration path provided)
- Supporting real-time bidirectional communication (polling/webhooks instead)

### Key Requirements

**Functional:**
1. Accept diverse task inputs (natural language, structured, code)
2. Classify and route tasks appropriately
3. Execute tasks in isolated environments
4. Return results in consistent format
5. Support async tasks with status polling

**Non-Functional:**
1. **Latency:** <3s for task acceptance including classification (execution async). See [Cost Analysis](#cost-analysis) for realistic timing breakdown.
2. **Availability:** 99.9% uptime target
3. **Security:** Maintain credential isolation, audit logging
4. **Scalability:** Support concurrent task execution
5. **Observability:** Structured logging, metrics, tracing

> **Note on Latency:** The original <500ms target was optimistic. Claude API calls for classification typically require 1-2 seconds. The revised target of <3s accounts for: load balancer (~50ms), API Gateway auth (~100ms), Claude classification (~1.5-2s), context determination (~200ms), and queueing (~100ms). For latency-sensitive integrations like Slack, we can use a hybrid approach: fast-path rule-based routing for known webhook formats, with Claude classification as fallback for ambiguous requests.

## Decision

**We will rearchitect jib as a web service with a single REST API endpoint that uses Claude to intelligently classify and route incoming tasks.**

### Core Principles

**1. Single Endpoint Philosophy**

Instead of multiple endpoints for different task types:
```
POST /api/v1/code-review
POST /api/v1/documentation
POST /api/v1/bug-fix
POST /api/v1/slack-message
```

We use ONE endpoint:
```
POST /api/v1/task
```

The API accepts any input and Claude determines how to handle it.

**2. Input Agnostic**

The endpoint accepts:
- Natural language requests
- Structured JSON payloads
- Code snippets
- File references
- Webhook payloads (Slack, GitHub, JIRA)

**3. Intelligent Classification**

Claude analyzes input to determine:
- Task type (code, docs, analysis, sync, etc.)
- Required context (repos, files, external data)
- Execution model (sync/async, resources needed)
- Response format (code, text, structured data)

**4. Stateless API Layer, Stateful Execution Layer**

The **API layer** is stateless for horizontal scaling, but the **execution layer** requires state:

| Layer | Stateless? | State Management |
|-------|------------|------------------|
| API Gateway | Yes | No state |
| Task Coordinator | Yes | Task metadata in Firestore |
| Docker Sandbox | **No** | Git worktrees, Beads, output files |

**How this works with Cloud Run:**
- The API layer runs on Cloud Run Services (stateless, auto-scaling)
- Task execution runs on Cloud Run Jobs (supports volume mounts, longer timeouts)
- State is externalized to Cloud Storage (code, context) and Firestore (Beads, task state)

See [State Management Strategy](#state-management-strategy) for detailed handling of code, Beads, and context in a cloud environment.

### Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **API Design** | Hybrid: typed webhook endpoints + catch-all | Best of both worlds (see below) | Pure single endpoint |
| **Task Classification** | Rule-based fast path + Claude fallback | Latency for known formats, flexibility for ambiguous | Pure Claude classification |
| **Execution Model** | Async with polling | Scalable, stateless, cloud-friendly | WebSockets, SSE |
| **State Management** | External (Beads/DB) | Stateless containers, persistence | In-memory state |
| **Container Orchestration** | Cloud Run (primary) | Serverless, auto-scaling, cost-effective | Kubernetes (complex), VMs (expensive) |

**Hybrid API Design (Revised):**

After considering the feedback on single-endpoint risks, we adopt a hybrid approach:

```
POST /api/v1/task              # Catch-all for CLI, natural language
POST /api/v1/webhooks/slack    # Typed endpoint for Slack (signature verified)
POST /api/v1/webhooks/github   # Typed endpoint for GitHub (secret verified)
POST /api/v1/webhooks/jira     # Typed endpoint for JIRA (secret verified)
GET  /api/v1/task/:id          # Task status polling
GET  /api/v1/health            # Health check
```

**Rationale:**
1. **Typed webhook endpoints** have known payload formats—use rule-based routing (fast, cheap)
2. **Catch-all endpoint** uses Claude classification for ambiguous/natural language input
3. **Versioning** is simpler: `/api/v1/` vs `/api/v2/` for breaking changes
4. **Documentation** is clearer: OpenAPI spec can define schemas per endpoint
5. **Error attribution** is explicit: webhook parse errors are distinct from classification errors

This addresses the reviewer concern about "accepts anything" being hard to document and version.

## High-Level Design

### System Architecture

```
                                    ┌─────────────────────────────────────┐
                                    │           Clients                     │
                                    │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐    │
                                    │  │Slack│ │ CLI │ │ Web │ │Mobile│    │
                                    │  └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘    │
                                    └─────┼───────┼───────┼───────┼───────┘
                                          │       │       │       │
                                          └───────┴───┬───┴───────┘
                                                      │
                                              ┌───────▼───────┐
                                              │  Load Balancer │
                                              │  (Cloud Run)   │
                                              └───────┬───────┘
                                                      │
                                              ┌───────▼───────┐
                                              │   API Gateway  │
                                              │  POST /task    │
                                              │  GET /task/:id │
                                              │  (Auth, Rate   │
                                              │   Limiting)    │
                                              └───────┬───────┘
                                                      │
┌─────────────────────────────────────────────────────┼─────────────────────────────────────────────────────┐
│                                       JIB SERVICE   │                                                      │
│                                                     │                                                      │
│  ┌──────────────────────────────────────────────────▼─────────────────────────────────────────────────┐  │
│  │                                    Task Coordinator                                                  │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                            │  │
│  │  │  Classifier  │  │   Context    │  │  Executor    │  │   Result     │                            │  │
│  │  │  (Claude)    │→ │  Gatherer    │→ │  Dispatcher  │→ │  Handler     │                            │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘                            │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                     │                                                      │
│                                                     │                                                      │
│  ┌──────────────────────────────────────────────────┼─────────────────────────────────────────────────┐  │
│  │                               Execution Layer    │                                                   │  │
│  │                                                  │                                                   │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                            Claude Code Sandbox (Docker)                                       │  │  │
│  │  │                                                                                               │  │  │
│  │  │   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐                                     │  │  │
│  │  │   │  Code   │   │ Context │   │  Beads  │   │ Output  │                                     │  │  │
│  │  │   │  (R/W)  │   │  (R/O)  │   │  (R/W)  │   │  (R/W)  │                                     │  │  │
│  │  │   └─────────┘   └─────────┘   └─────────┘   └─────────┘                                     │  │  │
│  │  │                                                                                               │  │  │
│  │  │   Security Boundary: No credentials, no direct push, no deploy                               │  │  │
│  │  └───────────────────────────────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                      │
                              ┌───────────────────────┼───────────────────────┐
                              │                       │                       │
                      ┌───────▼───────┐       ┌──────▼──────┐       ┌────────▼────────┐
                      │     Beads     │       │   GitHub    │       │  Context Sync   │
                      │  (Firestore)  │       │    (MCP)    │       │   (Cloud Stor.) │
                      └───────────────┘       └─────────────┘       └─────────────────┘
```

### Component Descriptions

**1. API Gateway**

Single entry point handling:
- Authentication (API keys, OAuth, Slack signatures)
- Rate limiting (per-user, per-client)
- Request validation (schema validation)
- Routing to Task Coordinator

**2. Task Coordinator**

Core orchestration layer:

| Component | Responsibility |
|-----------|----------------|
| **Classifier** | Uses Claude to analyze input, determine task type |
| **Context Gatherer** | Fetches required context (repos, docs, history) |
| **Executor Dispatcher** | Launches appropriate execution environment |
| **Result Handler** | Formats and stores results, triggers callbacks |

**3. Classifier (Claude-Powered)**

Analyzes incoming requests to determine:

```json
{
  "task_type": "code_modification | documentation | analysis | sync | conversation",
  "execution_mode": "sync | async",
  "required_context": ["repo:james-in-a-box", "jira:INFRA-123"],
  "estimated_duration": "short | medium | long",
  "response_format": "code | text | structured",
  "priority": "low | normal | high | urgent"
}
```

**4. Execution Layer (Docker Sandbox)**

Maintains existing security model:
- Isolated Docker container
- No credentials
- Read-only context mount
- Git worktree isolation
- Beads for persistence

**5. External Services**

| Service | Purpose |
|---------|---------|
| **Beads (Firestore)** | Task state, history, cross-session memory |
| **GitHub MCP** | Repository access, PR operations |
| **Context Storage** | Synced Confluence/JIRA docs |

## API Design

### Endpoint: POST /api/v1/task

**Request:**

```json
{
  "input": "<any - natural language, structured, code, webhook payload>",
  "context": {
    "source": "slack | cli | web | github | jira",
    "user": "user-identifier",
    "thread_id": "optional-conversation-thread",
    "metadata": {}
  },
  "options": {
    "async": true,
    "callback_url": "https://...",
    "timeout_seconds": 600,
    "priority": "normal"
  }
}
```

**Response (Sync):**

```json
{
  "task_id": "task-uuid",
  "status": "completed",
  "classification": {
    "task_type": "code_modification",
    "execution_mode": "sync"
  },
  "result": {
    "type": "code",
    "content": "...",
    "files_changed": [],
    "pr_url": "https://..."
  },
  "metadata": {
    "duration_ms": 12345,
    "tokens_used": 5000
  }
}
```

**Response (Async):**

```json
{
  "task_id": "task-uuid",
  "status": "accepted",
  "poll_url": "/api/v1/task/task-uuid",
  "estimated_duration": "medium"
}
```

### Endpoint: GET /api/v1/task/:id

**Response:**

```json
{
  "task_id": "task-uuid",
  "status": "pending | running | completed | failed",
  "progress": {
    "current_step": "Analyzing code...",
    "percent_complete": 45
  },
  "result": null,
  "created_at": "2025-12-04T00:00:00Z",
  "updated_at": "2025-12-04T00:01:00Z"
}
```

### Endpoint: DELETE /api/v1/task/:id

Cancels a running task.

### Endpoint: GET /api/v1/health

Health check for load balancer.

## Task Classification System

### How Claude Classifies Tasks

When a request arrives, a lightweight Claude call analyzes the input:

**Classification Prompt:**

```
Analyze this incoming request and classify it:

INPUT: {input}
CONTEXT: {context}

Determine:
1. Task type (code_modification, documentation, analysis, conversation, sync, unknown)
2. Execution mode (sync for <30s tasks, async for longer)
3. Required context (which repos, docs, external data needed)
4. Response format (code, text, structured_json, file)
5. Priority level based on urgency signals

Output JSON classification.
```

### Task Type Examples

| Input | Classification | Execution |
|-------|---------------|-----------|
| "Fix the bug in auth.py line 42" | code_modification | async |
| "What does the login function do?" | analysis | sync |
| "Write docs for the API endpoint" | documentation | async |
| "JIRA ticket INFRA-123 assigned" | code_modification | async |
| Slack webhook with PR review request | analysis | async |
| "Hi, how are you?" | conversation | sync |
| GitHub check failure webhook | code_modification | async |

### Intelligent Routing

Based on classification, the coordinator:

1. **Short sync tasks:** Execute immediately, return result
2. **Long async tasks:** Queue for execution, return task ID
3. **Conversation:** Quick Claude response, no sandbox
4. **Code modification:** Full sandbox execution with git
5. **Analysis:** Read-only execution, no commits

### Classification Error Handling

**What happens when classification fails or is ambiguous?**

| Scenario | Detection | Handling |
|----------|-----------|----------|
| **Low confidence** | Classifier returns confidence <0.7 | Ask user for clarification via response |
| **Unknown task type** | Classifier returns "unknown" | Default to "conversation" mode, ask for details |
| **Misclassification** | User feedback or failed execution | Log for review, allow task type override |
| **Classification timeout** | Claude API >5s | Fall back to rule-based classification |

**User Override Mechanism:**

For CLI and API clients, explicit task type can be specified:
```json
{
  "input": "Fix the bug",
  "options": {
    "task_type": "code_modification"  // Bypasses classification
  }
}
```

For Slack, users can prefix with hints: `/jib [code] Fix the bug in auth.py`

**Feedback Loop:**

1. All classifications logged with input/output pairs
2. Misclassifications flagged via user feedback or execution failures
3. Weekly review of misclassification patterns
4. Prompt tuning based on failure analysis

## Cost Analysis

### Token Usage Estimates

Based on Claude API pricing and typical jib workloads:

| Component | Input Tokens | Output Tokens | Cost per Call |
|-----------|--------------|---------------|---------------|
| **Classification (Haiku)** | ~500 | ~200 | ~$0.0004 |
| **Simple Query (Haiku)** | ~2,000 | ~500 | ~$0.0015 |
| **Code Task (Sonnet)** | ~50,000 | ~10,000 | ~$0.27 |
| **Complex Task (Opus)** | ~100,000 | ~20,000 | ~$1.20 |

*Prices based on December 2024 Claude API pricing.*

### Monthly Cost Projections

Assuming 500 tasks/month (current jib usage pattern):

| Cost Category | Current (Laptop) | Cloud Deployment | Delta |
|---------------|------------------|------------------|-------|
| **Claude API (execution)** | ~$150 | ~$150 | $0 |
| **Claude API (classification)** | $0 | ~$5 | +$5 |
| **Cloud Run Services** | $0 | ~$20 | +$20 |
| **Cloud Run Jobs** | $0 | ~$50 | +$50 |
| **Firestore** | $0 | ~$10 | +$10 |
| **Cloud Storage** | $0 | ~$5 | +$5 |
| **Total** | ~$150 | ~$240 | +$90/mo |

**Break-even Analysis:**

The ~$90/month premium pays for:
- Multi-user support (currently single-user)
- 24/7 availability (vs laptop uptime)
- Horizontal scaling for concurrent tasks
- No laptop dependency

At **2+ users** or **>1000 tasks/month**, cloud deployment becomes more cost-effective than running multiple laptops.

### Token Optimization Strategies

1. **Hybrid classification:** Rule-based for webhooks (0 tokens), Claude for ambiguous (~$5/mo savings)
2. **Model tiering:** Haiku for simple tasks, Sonnet for code, Opus only for complex (~30% savings)
3. **Context pruning:** Load only relevant files, not entire repos (~40% token reduction)
4. **Caching:** Cache classification results for identical inputs (~10% reduction)

## Worked Example

### End-to-End Flow: Slack Message "Fix the login bug in auth.py"

This example traces a complete request through the system with timing and token estimates.

**Step 1: Slack Webhook Received**
```
POST /api/v1/webhooks/slack
X-Slack-Signature: v0=abc123...
{
  "type": "event_callback",
  "event": {
    "type": "app_mention",
    "text": "<@U123> Fix the login bug in auth.py",
    "user": "U456",
    "channel": "C789"
  }
}
```
- **Time:** ~50ms (network + load balancer)
- **Tokens:** 0 (signature verification only)

**Step 2: API Gateway Authentication**
- Verify X-Slack-Signature against signing secret
- Extract user identity from Slack user ID
- Check rate limits
- **Time:** ~100ms
- **Tokens:** 0

**Step 3: Classification (Skipped for Typed Endpoint)**

Since this came via `/api/v1/webhooks/slack`, we use rule-based parsing:
- Slack app_mention with text → "code_modification" or "conversation"
- Text contains "fix", "bug", file reference → code_modification
- **Time:** ~10ms
- **Tokens:** 0 (rule-based fast path)

*If this were via `/api/v1/task` with ambiguous input, Claude classification would add ~1.5s and ~700 tokens.*

**Step 4: Context Gathering**
- Identify repository from channel mapping or context
- Fetch `auth.py` from GitHub via MCP
- Load recent commits for context
- Check Beads for related tasks
- **Time:** ~500ms
- **Tokens:** 0 (API calls, not Claude)

**Step 5: Task Queuing**
- Create task record in Firestore
- Return accepted response to Slack
- **Time:** ~100ms
- **Tokens:** 0

**Step 6: Immediate Slack Response**
```
{
  "response_type": "in_channel",
  "text": "🔧 On it! Investigating login bug in auth.py. Task ID: task-abc123"
}
```
- **Total acceptance time:** ~760ms ✅ (under 3s target)

**Step 7: Async Execution (Cloud Run Job)**
- Spin up Docker sandbox with mounted code
- Claude Code analyzes auth.py, identifies bug
- Implements fix, runs tests
- Creates PR via GitHub MCP
- **Time:** ~3-10 minutes
- **Tokens:** ~50,000 input, ~10,000 output
- **Cost:** ~$0.27

**Step 8: Completion Callback**
- Update Firestore task status
- Post to Slack channel: "✅ Fixed! PR #123 created: [link]"
- Update Beads with task completion
- **Time:** ~200ms
- **Tokens:** 0

### Summary

| Phase | Time | Tokens | Cost |
|-------|------|--------|------|
| Accept & Queue | 760ms | 0 | $0 |
| Execution | ~5 min | ~60,000 | ~$0.27 |
| Completion | 200ms | 0 | $0 |
| **Total** | **~5 min** | **~60,000** | **~$0.27** |

*Note: Current laptop-based jib has similar Claude costs but no cloud infrastructure costs.*

## Security Considerations

### Authentication

| Client | Method |
|--------|--------|
| **Slack** | Signature verification (X-Slack-Signature) |
| **CLI** | API key (stored in ~/.config/jib/) |
| **Web** | OAuth 2.0 (Google, GitHub) |
| **GitHub** | Webhook secret verification |
| **JIRA** | Webhook secret verification |

### Authorization

```yaml
# Per-user permissions
user:
  allowed_repos: ["james-in-a-box", "webapp"]
  allowed_actions: ["code", "docs", "analysis"]
  rate_limit: 100/hour
  priority_max: "high"
```

### Isolation

Existing Docker sandbox model preserved:
- No credentials in container
- Network isolation (outbound HTTP only)
- Read-only context mount
- Ephemeral containers (`--rm`)

### Audit Logging

All requests logged with:
- User identity
- Input (redacted if sensitive)
- Classification result
- Execution details
- Result summary

### Cloud-Specific Security

**Network Security:**

| Layer | Protection |
|-------|------------|
| **Edge** | Cloud Armor (DDoS, WAF rules) |
| **Load Balancer** | SSL termination, geographic restrictions |
| **VPC** | Private networking for internal services |
| **Egress** | Restricted to GitHub, Claude API, Slack |

**Rate Limiting (Detailed):**

| Scope | Limit | Burst | Action on Exceed |
|-------|-------|-------|------------------|
| Per-user | 100/hour | 10/minute | 429 + backoff |
| Per-organization | 1000/hour | 50/minute | 429 + notify admin |
| Global | 10000/hour | 500/minute | 503 + alert |

**Secret Management:**

| Secret | Storage | Rotation |
|--------|---------|----------|
| API keys | Secret Manager | 90-day auto-rotate |
| Claude API key | Secret Manager | Manual (Anthropic-issued) |
| Slack signing secret | Secret Manager | Manual (Slack-issued) |
| GitHub App key | Secret Manager | Annual |

**Data Residency:**

- All processing in `us-central1` (or configured region)
- No cross-region data transfer for task content
- Audit logs retained 90 days in Cloud Logging
- Task content not logged (only metadata)

**Reference:** See [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) for detailed data exfiltration concerns and sandbox security model.

## State Management Strategy

### Current State Model

The current jib implementation uses local file-based state:

| State Type | Current Location | Characteristics |
|------------|-----------------|-----------------|
| **Code** | Git worktree (`~/khan/`) | R/W, persisted |
| **Beads** | JSONL + SQLite (`~/beads/`) | R/W, git-backed |
| **Context** | Mounted files (`~/context-sync/`) | R/O, synced |
| **Output** | Shared volume (`~/sharing/`) | R/W, ephemeral |

### Cloud State Model

For cloud deployment, state must be externalized:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Cloud State Architecture                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────────┐│
│  │   Cloud     │   │  Firestore  │   │    Cloud Storage        ││
│  │   Storage   │   │             │   │    (Context Bucket)     ││
│  │  (Code)     │   │  (Beads)    │   │                         ││
│  └──────┬──────┘   └──────┬──────┘   └────────────┬────────────┘│
│         │                 │                       │              │
│         │    GCS FUSE     │   Firestore SDK       │   GCS FUSE   │
│         │    Mount        │   Direct Access       │   Mount      │
│         │                 │                       │              │
│  ┌──────┴─────────────────┴───────────────────────┴──────┐      │
│  │              Cloud Run Job (Docker Sandbox)            │      │
│  │                                                        │      │
│  │   /code (R/W)     /beads (R/W)     /context (R/O)    │      │
│  │                                                        │      │
│  └────────────────────────────────────────────────────────┘      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Beads Migration Strategy

**Current Beads Architecture:**
- JSONL files for issue data
- SQLite cache for queries
- Git-backed for audit trail
- Hash-based IDs (`bd-xxxx`)

**Cloud Beads Architecture (Firestore):**

```json
// Firestore document: /beads/{bead-id}
{
  "id": "bd-abc123",
  "title": "Fix login bug",
  "status": "in_progress",
  "labels": ["slack-thread", "task-123"],
  "created_at": "2025-12-04T00:00:00Z",
  "updated_at": "2025-12-04T01:00:00Z",
  "notes": ["Started investigation", "Found root cause"],
  "metadata": {
    "source": "slack",
    "thread_ts": "1234567890.123456"
  }
}
```

**Migration Approach:**

| Phase | Action | Rollback |
|-------|--------|----------|
| **1. Dual-write** | Write to both JSONL and Firestore | Disable Firestore writes |
| **2. Read from Firestore** | Switch reads to Firestore, continue dual-write | Switch reads back to JSONL |
| **3. Single-write** | Stop JSONL writes | Re-enable JSONL writes |
| **4. Archive JSONL** | Move JSONL to cold storage | Restore from archive |

**ID Generation:**
- Continue using `bd-xxxx` format for consistency
- Generate client-side using same algorithm
- Firestore document ID = Beads ID

**Audit Trail:**
- Firestore has built-in versioning (optional)
- Alternatively, write to separate `/beads-history/{bead-id}/changes/{timestamp}` collection
- Less granular than git history, but sufficient for task tracking

## Migration Strategy

### Phase 1: API Layer

Add REST API alongside existing infrastructure:

```
Existing:
├── jib CLI → Docker container
├── slack-receiver → File queue → Docker container
└── systemd services → Various processors

New:
└── REST API → Task Coordinator → Docker container
```

Both systems operate in parallel.

### Phase 2: Client Migration

Migrate clients to use API:

1. **CLI:** Add `jib api` subcommand using REST API
2. **Slack:** Update receiver to call API instead of file queue
3. **GitHub webhooks:** Route through API
4. **JIRA webhooks:** Route through API

### Phase 3: Deprecate Legacy

Remove deprecated components:
- File-based notification queue
- Direct Docker invocation from clients
- Host-based systemd services (move to Cloud Scheduler)

### Phase 4: Cloud Deployment

Deploy API to Cloud Run:
- Containerized API service
- Cloud Run Jobs for long tasks
- Cloud Scheduler for periodic tasks
- Firestore for state
- Cloud Storage for context

### Rollback Strategy

Each phase has explicit rollback criteria and procedures:

| Phase | Rollback Trigger | Rollback Procedure | Time to Rollback |
|-------|------------------|--------------------|--------------------|
| **Phase 1** | API errors >5%, latency >5s | Disable API endpoints, route to legacy | ~5 minutes |
| **Phase 2** | Client integration failures | Revert client configs, restore file queue | ~15 minutes |
| **Phase 3** | Missing functionality discovered | Re-enable legacy components from backup | ~30 minutes |
| **Phase 4** | Cloud deployment issues | Redirect traffic to laptop deployment | ~10 minutes |

**Phase 1 Rollback Details:**
- API Gateway can be disabled via feature flag
- Legacy file-based paths remain active during parallel operation
- No data migration needed (both systems write independently)

**Phase 2 Rollback Details:**
- Client configurations stored in version control
- `git revert` on client config changes
- Slack receiver can switch between API and file mode via env var

**Phase 3 Rollback Details:**
- Legacy components archived, not deleted
- Systemd unit files backed up to `/etc/systemd/system.backup/`
- One-command restore: `./scripts/restore-legacy.sh`

**Phase 4 Rollback Details:**
- DNS-based traffic routing (Cloud Load Balancer → laptop via Tailscale)
- Laptop deployment kept warm during initial cloud rollout
- Data sync between cloud and laptop via Beads dual-write

**Rollback Decision Criteria:**
- **Automatic:** Error rate >10% for 5 minutes
- **Manual:** User-reported critical issues
- **Scheduled:** Performance degradation trending upward

## Consequences

### Positive

| Benefit | Impact |
|---------|--------|
| **Simplified Architecture** | One entry point, easier to understand and maintain |
| **Cloud Deployable** | No host dependencies, runs anywhere |
| **Scalable** | Horizontal scaling for multiple users |
| **Flexible Integration** | Any client can use REST API |
| **Intelligent Routing** | Claude handles ambiguous inputs gracefully |
| **Better Observability** | Centralized logging, metrics, tracing |

### Negative / Trade-offs

| Trade-off | Mitigation |
|-----------|------------|
| **Additional API layer** | Rule-based fast path for webhooks (0ms), Claude only for ambiguous (~1.5s) |
| **Network dependency** | Deploy in same region as users |
| **Classification errors** | Allow explicit task type override, confidence thresholds |
| **Migration effort** | Phased approach with rollback at each phase |
| **Cold start latency** | Keep minimum instances warm, use Cloud Run min-instances |
| **Cloud costs (~$90/mo)** | Break-even at 2+ users or 1000+ tasks/month |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Classification accuracy | Medium | Medium | User can override, feedback loop |
| API availability | Low | High | Multi-region, health checks |
| Security gaps in new layer | Low | High | Security review, penetration testing |
| Performance degradation | Medium | Medium | Caching, optimize classification |

## Decision Permanence

**Reversible Decisions (Low Cost to Change):**
- API response formats
- Classification prompt tuning
- Rate limits and quotas
- Cloud provider (Cloud Run vs. alternatives)

**Semi-Permanent (Moderate Cost to Change):**
- Single vs. multiple endpoints
- Sync vs. async execution model
- Authentication mechanisms
- State storage choice

**Permanent (High Cost to Change):**
- REST vs. GraphQL vs. gRPC (REST chosen)
- Claude-powered classification (core design)
- Stateless container model
- Security isolation approach

## Alternatives Considered

### Alternative 1: Multiple Typed Endpoints

**Approach:** Separate endpoints per task type

```
POST /api/v1/code
POST /api/v1/docs
POST /api/v1/analyze
POST /api/v1/slack
```

**Pros:**
- Explicit routing
- Typed request/response schemas
- Easier to document

**Cons:**
- Clients must know task type
- Doesn't handle ambiguous inputs
- More endpoints to maintain
- Duplicated validation logic

**Rejected Because:** Defeats the goal of intelligent routing. Users shouldn't need to pre-classify their requests.

### Alternative 2: Rule-Based Classification

**Approach:** Use regex/keyword matching for task routing

**Pros:**
- Fast, no LLM call
- Predictable behavior
- Lower cost

**Cons:**
- Brittle, breaks on edge cases
- Can't handle natural language variation
- Requires constant rule updates
- Poor user experience

**Rejected Because:** Claude handles ambiguity far better than rules. The classification call is cheap and fast.

### Alternative 3: WebSocket for Real-Time

**Approach:** Persistent WebSocket connections for streaming results

**Pros:**
- True real-time updates
- Lower latency for progress
- Bidirectional communication

**Cons:**
- Stateful connections (scaling complexity)
- Connection management overhead
- Not Cloud Run native
- Mobile/firewall issues

**Rejected Because:** Polling/webhooks are simpler and sufficient. Real-time streaming is a nice-to-have, not essential.

### Alternative 4: GraphQL API

**Approach:** GraphQL instead of REST

**Pros:**
- Flexible queries
- Strong typing
- Single endpoint (already)
- Better for complex data

**Cons:**
- More complex to implement
- Overkill for our use case
- Learning curve
- Caching more complex

**Rejected Because:** REST is simpler and widely understood. Our API is not data-heavy enough to benefit from GraphQL.

### Alternative 5: gRPC

**Approach:** gRPC instead of REST

**Pros:**
- Strong typing
- Efficient binary protocol
- Streaming support
- Code generation

**Cons:**
- Harder to debug (binary)
- Browser support requires proxy
- Less universal client support
- More complex infrastructure

**Rejected Because:** REST is more accessible for all clients, especially Slack webhooks and web browsers.

---

## Implementation Checklist

### Phase 1: API Foundation
- [ ] Design OpenAPI specification
- [ ] Implement API gateway with authentication
- [ ] Build Task Coordinator framework
- [ ] Implement Claude classification prompt
- [ ] Add basic task execution (sync)
- [ ] Add async task queue
- [ ] Implement task polling endpoint
- [ ] Add health check endpoint
- [ ] Write API documentation

### Phase 2: Client Migration
- [ ] Update `jib` CLI to use API
- [ ] Update Slack receiver to use API
- [ ] Add GitHub webhook handler
- [ ] Add JIRA webhook handler
- [ ] Migrate file-based notifications to webhooks
- [ ] Add callback URL support

### Phase 2.5: Beads Migration (Critical Path)
- [ ] Design Firestore schema for Beads documents
- [ ] Implement dual-write adapter (JSONL + Firestore)
- [ ] Migrate historical Beads data to Firestore
- [ ] Switch reads to Firestore (dual-write continues)
- [ ] Validate data consistency between sources
- [ ] Stop JSONL writes, archive to cold storage
- [ ] Update `bd` CLI to use Firestore SDK

### Phase 3: Cloud Deployment
- [ ] Containerize API service
- [ ] Configure Cloud Run service
- [ ] Set up Cloud Run Jobs for long tasks
- [ ] Configure GCS FUSE mounts for code/context
- [ ] Set up Cloud Scheduler for periodic tasks
- [ ] Configure Cloud Storage for context
- [ ] Set up monitoring and alerting

### Phase 4: Deprecation
- [ ] Remove file-based task queue
- [ ] Remove direct Docker invocation from clients
- [ ] Archive legacy host services
- [ ] Update documentation

---

## References

- [ADR: Autonomous Software Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) - Core architecture
- [ADR: Multi-Agent Pipeline Architecture](ADR-Multi-Agent-Pipeline-Architecture.md) - Execution layer patterns
- [ADR: GCP Deployment Terraform](ADR-GCP-Deployment-Terraform.md) - Cloud infrastructure
- [ADR: Message Queue Slack Integration](ADR-Message-Queue-Slack-Integration.md) - Pub/Sub messaging
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Run Jobs Documentation](https://cloud.google.com/run/docs/create-jobs)
- [GCS FUSE Documentation](https://cloud.google.com/storage/docs/gcs-fuse)
- [OpenAPI Specification](https://swagger.io/specification/)

---

**Last Updated:** 2025-12-04
**Next Review:** After Phase 1 implementation
**Status:** Proposed

---
Authored-by: jib
