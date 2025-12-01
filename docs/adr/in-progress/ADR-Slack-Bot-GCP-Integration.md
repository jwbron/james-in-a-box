# ADR: Slack Bot for GCP-Hosted jib

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
- [Slash Command Specification](#slash-command-specification)
- [Architecture](#architecture)
- [Implementation Details](#implementation-details)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)

## Current Implementation Status

**Host-Based Commands (Phase 1 - Complete):**

| Category | Commands | Implementation |
|----------|----------|----------------|
| Container | `jib`, `jib --exec`, `jib --setup`, `jib --reset` | Python CLI script |
| Remote Control | `/jib status`, `/jib restart`, `/jib rebuild`, `/jib logs` | Message-triggered via `remote-control.sh` |
| Services | `/service list`, `/service status`, `/service start/stop/restart`, `/service logs` | Message-triggered via `remote-control.sh` |
| PR Creation | `/pr create [repo] [--ready]` | Message-triggered via `remote-control.sh` |
| Context Sync | `systemctl --user start context-sync.service` | Manual systemd command |
| Analyzers | `systemctl --user start codebase-analyzer.service` | Manual systemd command |

**Current Limitations:**
- Commands are message-based (not Slack slash commands)
- Require host machine access for some operations
- No job tracking for long-running operations
- Not designed for GCP/Cloud Run deployment

## Context

### Background

As jib moves from laptop deployment to **GCP Cloud Run** (Phase 3), host-based commands must be replaced with a cloud-native interface. The Slack bot becomes the **primary control plane** for managing jib instances.

**Current Architecture (Host-Based):**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Host Machine                                     │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────────┐ │
│  │ jib CLI      │   │ systemctl    │   │ host-receive-slack.py       │ │
│  │ (terminal)   │   │ (services)   │   │ (message commands)          │ │
│  └──────┬───────┘   └──────┬───────┘   └──────────────┬───────────────┘ │
│         │                  │                          │                  │
│         └──────────────────┼──────────────────────────┘                  │
│                            ▼                                             │
│                   Docker Container (jib)                                 │
└──────────────────────────────────────────────────────────────────────────┘
```

**Target Architecture (GCP + Slack Bot):**
```
┌─────────────────────────────────────────────────────────────────────────┐
│                            Slack                                         │
│                                                                          │
│  /jib status    /jib task    /sync    /analyze    /pr create            │
│       │              │          │          │            │                │
└───────┼──────────────┼──────────┼──────────┼────────────┼────────────────┘
        │              │          │          │            │
        └──────────────┴──────────┴──────────┴────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              GCP                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Cloud Run (jib-bot)                            │   │
│  │  • Receives slash commands                                        │   │
│  │  • Manages job queue                                              │   │
│  │  • Orchestrates jib instances                                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                  │                                       │
│              ┌───────────────────┼───────────────────┐                  │
│              ▼                   ▼                   ▼                  │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐        │
│  │ Cloud Run (jib)  │ │ Cloud Run (jib)  │ │ Cloud Run (jib)  │        │
│  │ Task Instance    │ │ Task Instance    │ │ Analyzer Job     │        │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
```

### What We're Deciding

This ADR specifies:
1. **Slack slash commands** to replace all host-based operations
2. **Bot architecture** for GCP deployment
3. **Job management** for long-running operations
4. **Security model** for cloud-based control plane

### Key Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Full parity with host commands | High | All current operations available via Slack |
| Proper Slack slash commands | High | Not message-based triggers |
| Job tracking | High | Status, cancellation for long-running ops |
| GCP-native | High | Cloud Run, Pub/Sub, Firestore |
| Mobile-friendly | High | Works well from phone |
| Multi-user support | Medium | Future: multiple engineers using jib |
| Audit trail | Medium | Log all commands and outcomes |
| Rate limiting | Medium | Prevent abuse |

## Decision

**We will build a comprehensive Slack bot with native slash commands that serves as the control plane for jib in GCP.**

### Core Principles

1. **Slash Commands:** Proper Slack slash commands (not message triggers)
2. **Async Execution:** Commands return immediately, results posted to channel/thread
3. **Job Tracking:** Long-running operations tracked with status updates
4. **Ephemeral Responses:** Sensitive info shown only to requester
5. **Cloud-Native:** Designed for Cloud Run from the start

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Command Interface** | Slack Slash Commands | Native UX, discoverability, validation | Message parsing (current) |
| **Bot Hosting** | Cloud Run | Serverless, scales to zero, GCP-native | GKE (overkill), VM (always-on cost) |
| **Job Queue** | Cloud Tasks + Firestore | Managed queue, job state persistence | Pub/Sub (no job tracking), Redis (always-on) |
| **jib Orchestration** | Cloud Run Jobs | Ephemeral, auto-cleanup, cost-efficient | Cloud Run Services (always-on), GKE (overkill) |
| **State Storage** | Firestore | Serverless, real-time updates | Cloud SQL (overkill), Memorystore (cost) |

## Slash Command Specification

### Container Management

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/jib status` | Show jib instance status, active jobs | Ephemeral |
| `/jib task <description>` | Start new Claude task | In-channel + thread |
| `/jib cancel <job-id>` | Cancel running job | Ephemeral |
| `/jib logs [job-id]` | Show recent logs | Ephemeral (chunked) |

**Example: `/jib task`**
```
/jib task Fix the authentication bug in user-service JIRA-1234

Response (ephemeral):
✅ Task queued
Job ID: job-abc123
Status: Starting...

Response (in-channel, after start):
🚀 **Task Started**
> Fix the authentication bug in user-service JIRA-1234

Job ID: `job-abc123`
Started: 2025-11-25 10:30:00 UTC

[View Logs] [Cancel]
```

### Service Management

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/service list` | List all jib services and status | Ephemeral |
| `/service status <name>` | Detailed service status | Ephemeral |
| `/service restart <name>` | Restart a service | Ephemeral + confirmation |
| `/service logs <name> [lines]` | Show service logs | Ephemeral (chunked) |

**Note:** In GCP, "services" are Cloud Run services/jobs, not systemd units.

### Context Sync

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/sync status` | Show sync status for all sources | Ephemeral |
| `/sync confluence` | Trigger Confluence sync | Ephemeral + completion notification |
| `/sync jira` | Trigger JIRA sync | Ephemeral + completion notification |
| `/sync github` | Trigger GitHub sync | Ephemeral + completion notification |
| `/sync all` | Trigger all syncs | Ephemeral + completion notifications |

**Example: `/sync confluence`**
```
/sync confluence

Response (ephemeral):
⏳ Confluence sync started
Job ID: sync-conf-xyz789
Last sync: 2 hours ago
Pages to check: ~150

Response (notification when complete):
✅ **Confluence Sync Complete**
Duration: 2m 34s
Pages synced: 147
New/updated: 3
```

### Analysis

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/analyze codebase [repo]` | Run codebase analyzer | In-channel + thread with results |
| `/analyze conversation` | Run conversation analyzer | Ephemeral + thread with results |
| `/analyze pr <pr-url>` | Analyze specific PR | Thread on PR notification |

**Example: `/analyze codebase`**
```
/analyze codebase webapp

Response (ephemeral):
⏳ Codebase analysis started
Job ID: analyze-abc123
Repository: khan/webapp
Estimated time: 10-15 minutes

Response (in-channel when complete):
📊 **Codebase Analysis Complete: webapp**

## Summary
- Files analyzed: 2,847
- Issues found: 12 (3 high, 5 medium, 4 low)

## Key Findings
[Threaded detailed report...]
```

### Pull Request

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/pr create [repo]` | Create PR from current work | In-channel with PR link |
| `/pr create [repo] --ready` | Create ready-for-review PR | In-channel with PR link |
| `/pr status` | Show PRs created by jib | Ephemeral |
| `/pr review <pr-url>` | Request jib to review a PR | Thread on request |

**Example: `/pr create`**
```
/pr create webapp

Response (ephemeral):
⏳ Creating PR...
Repository: khan/webapp
Branch: jib-temp-abc123

Response (in-channel when complete):
🎉 **Pull Request Created**

**Title:** Fix authentication bug in user-service

**URL:** https://github.com/khan/webapp/pull/456

**Summary:**
- Fixed token validation in auth middleware
- Added unit tests for edge cases
- Updated error messages

[View PR] [Request Review]
```

### Context Management

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/context save <name>` | Save current context | Ephemeral |
| `/context load <name>` | Load saved context | Ephemeral |
| `/context list` | List saved contexts | Ephemeral |
| `/context delete <name>` | Delete saved context | Ephemeral + confirmation |

### Task Memory (Beads)

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/beads list [--status <status>]` | List tasks | Ephemeral |
| `/beads add <description>` | Add new task | Ephemeral |
| `/beads update <id> --status <status>` | Update task status | Ephemeral |
| `/beads show <id>` | Show task details | Ephemeral |

### Help & Info

| Command | Description | Response Type |
|---------|-------------|---------------|
| `/jib help` | Show all available commands | Ephemeral |
| `/jib version` | Show jib version and config | Ephemeral |
| `/jib quota` | Show usage quota/limits | Ephemeral |

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                  Slack                                       │
│                                                                              │
│  Slash Commands ──────────────────────────────────────────────────────────┐ │
│  Events API (messages, reactions) ─────────────────────────────────────┐  │ │
│                                                                        │  │ │
└────────────────────────────────────────────────────────────────────────┼──┼─┘
                                                                         │  │
                        HTTPS (slash command payload)                    │  │
                        HTTPS (events webhook)                           │  │
                                                                         │  │
┌────────────────────────────────────────────────────────────────────────┼──┼─┐
│                                  GCP                                   │  │ │
│                                                                        │  │ │
│  ┌─────────────────────────────────────────────────────────────────┐  │  │ │
│  │                    Cloud Run: jib-bot                            │  │  │ │
│  │                                                                  │◀─┘  │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │◀────┘ │
│  │  │ Slash Cmd    │  │ Events       │  │ Job Manager          │  │       │
│  │  │ Handler      │  │ Handler      │  │                      │  │       │
│  │  │              │  │              │  │ • Create jobs        │  │       │
│  │  │ • Validate   │  │ • Messages   │  │ • Track status       │  │       │
│  │  │ • Dispatch   │  │ • Reactions  │  │ • Send updates       │  │       │
│  │  │ • Respond    │  │ • Threads    │  │ • Handle completion  │  │       │
│  │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │       │
│  │         │                 │                     │               │       │
│  └─────────┼─────────────────┼─────────────────────┼───────────────┘       │
│            │                 │                     │                        │
│            ▼                 ▼                     ▼                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         Cloud Tasks                                   │  │
│  │                                                                       │  │
│  │  Queue: jib-tasks        Queue: jib-sync        Queue: jib-analyze   │  │
│  │  • Task execution        • Context sync jobs    • Analysis jobs      │  │
│  │  • Retry logic           • Scheduled triggers   • Long-running       │  │
│  └───────────┬─────────────────────┬─────────────────────┬──────────────┘  │
│              │                     │                     │                  │
│              ▼                     ▼                     ▼                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐         │
│  │ Cloud Run Job    │  │ Cloud Run Job    │  │ Cloud Run Job    │         │
│  │ (jib-task)       │  │ (jib-sync)       │  │ (jib-analyze)    │         │
│  │                  │  │                  │  │                  │         │
│  │ • Claude Code    │  │ • Confluence     │  │ • Codebase       │         │
│  │ • Task execution │  │ • JIRA           │  │ • Conversation   │         │
│  │ • PR creation    │  │ • GitHub         │  │ • PR review      │         │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘         │
│              │                     │                     │                  │
│              └─────────────────────┴─────────────────────┘                  │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                          Firestore                                    │  │
│  │                                                                       │  │
│  │  jobs/              threads/            contexts/         beads/      │  │
│  │  • Job state        • Thread mapping    • Saved contexts  • Tasks    │  │
│  │  • Progress         • Conversation      • Project data    • Notes    │  │
│  │  • Results          • User mapping      • Learnings       • Status   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                        Cloud Pub/Sub                                  │  │
│  │                                                                       │  │
│  │  slack-outgoing     slack-incoming      job-updates                  │  │
│  │  • Notifications    • User messages     • Progress updates           │  │
│  │  • Results          • Commands          • Completion events          │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow: Slash Command Execution

```
1. User types: /jib task Fix the auth bug

2. Slack sends POST to jib-bot:
   {
     "command": "/jib",
     "text": "task Fix the auth bug",
     "user_id": "U123",
     "channel_id": "D456",
     "response_url": "https://hooks.slack.com/..."
   }

3. jib-bot validates and responds immediately (< 3 sec):
   {
     "response_type": "ephemeral",
     "text": "✅ Task queued\nJob ID: job-abc123"
   }

4. jib-bot creates Cloud Task:
   Queue: jib-tasks
   Payload: { job_id, task_description, user_id, channel_id }

5. Cloud Task triggers Cloud Run Job (jib-task):
   - Starts Claude Code container
   - Executes task
   - Streams progress to Pub/Sub (job-updates)

6. jib-bot receives progress updates:
   - Updates Firestore job state
   - Optionally posts progress to Slack thread

7. On completion:
   - jib-task publishes to slack-outgoing
   - slack-worker posts result to Slack
   - jib-bot updates job state to "completed"
```

### Job States

```
┌─────────┐     ┌─────────┐     ┌───────────┐     ┌───────────┐
│ QUEUED  │────▶│ RUNNING │────▶│ COMPLETED │     │ CANCELLED │
└─────────┘     └────┬────┘     └───────────┘     └───────────┘
                     │                                   ▲
                     │          ┌──────────┐             │
                     └─────────▶│  FAILED  │             │
                                └──────────┘             │
                                     │                   │
                                     └───────────────────┘
                                     (retry exhausted)
```

## Implementation Details

### 1. Slack App Configuration

**Slash Commands:**
```yaml
commands:
  - command: /jib
    url: https://jib-bot-xxx.run.app/slack/commands
    description: Manage jib autonomous agent
    usage_hint: "[status|task|cancel|logs|help] [args]"

  - command: /service
    url: https://jib-bot-xxx.run.app/slack/commands
    description: Manage jib services
    usage_hint: "[list|status|restart|logs] [service-name]"

  - command: /sync
    url: https://jib-bot-xxx.run.app/slack/commands
    description: Trigger context sync
    usage_hint: "[status|confluence|jira|github|all]"

  - command: /analyze
    url: https://jib-bot-xxx.run.app/slack/commands
    description: Run analysis jobs
    usage_hint: "[codebase|conversation|pr] [target]"

  - command: /pr
    url: https://jib-bot-xxx.run.app/slack/commands
    description: Manage pull requests
    usage_hint: "[create|status|review] [args]"

  - command: /context
    url: https://jib-bot-xxx.run.app/slack/commands
    description: Manage saved contexts
    usage_hint: "[save|load|list|delete] [name]"

  - command: /beads
    url: https://jib-bot-xxx.run.app/slack/commands
    description: Manage task memory
    usage_hint: "[list|add|update|show] [args]"
```

**OAuth Scopes:**
```yaml
bot_scopes:
  - commands              # Slash commands
  - chat:write           # Send messages
  - chat:write.public    # Send to public channels
  - users:read           # User info for attribution
  - reactions:write      # Add reactions for status
  - files:write          # Upload files (logs, reports)
```

### 2. jib-bot Service (Cloud Run)

```python
# jib_bot/main.py
from flask import Flask, request, jsonify
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from google.cloud import tasks_v2, firestore

app = Flask(__name__)
slack_app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)
handler = SlackRequestHandler(slack_app)
db = firestore.Client()
tasks_client = tasks_v2.CloudTasksClient()

# Slash command handlers
@slack_app.command("/jib")
def handle_jib(ack, command, respond):
    ack()  # Acknowledge immediately

    args = command["text"].split()
    subcommand = args[0] if args else "help"

    if subcommand == "status":
        jobs = get_active_jobs(command["user_id"])
        respond(format_status(jobs), response_type="ephemeral")

    elif subcommand == "task":
        description = " ".join(args[1:])
        job_id = create_task_job(description, command)
        respond(
            f"✅ Task queued\nJob ID: `{job_id}`\nStatus: Starting...",
            response_type="ephemeral"
        )

    elif subcommand == "cancel":
        job_id = args[1] if len(args) > 1 else None
        if cancel_job(job_id, command["user_id"]):
            respond(f"✅ Job `{job_id}` cancelled", response_type="ephemeral")
        else:
            respond(f"❌ Could not cancel job `{job_id}`", response_type="ephemeral")

    elif subcommand == "logs":
        job_id = args[1] if len(args) > 1 else "latest"
        logs = get_job_logs(job_id, command["user_id"])
        respond(format_logs(logs), response_type="ephemeral")

    else:
        respond(get_help_text(), response_type="ephemeral")

@slack_app.command("/sync")
def handle_sync(ack, command, respond):
    ack()

    args = command["text"].split()
    target = args[0] if args else "status"

    if target == "status":
        status = get_sync_status()
        respond(format_sync_status(status), response_type="ephemeral")

    elif target in ["confluence", "jira", "github", "all"]:
        job_id = create_sync_job(target, command)
        respond(
            f"⏳ {target.title()} sync started\nJob ID: `{job_id}`",
            response_type="ephemeral"
        )

    else:
        respond("Usage: /sync [status|confluence|jira|github|all]", response_type="ephemeral")

def create_task_job(description: str, command: dict) -> str:
    """Create a Cloud Task for jib task execution."""
    job_id = f"task-{uuid.uuid4().hex[:8]}"

    # Store job in Firestore
    db.collection("jobs").document(job_id).set({
        "id": job_id,
        "type": "task",
        "description": description,
        "user_id": command["user_id"],
        "channel_id": command["channel_id"],
        "status": "queued",
        "created_at": firestore.SERVER_TIMESTAMP,
    })

    # Create Cloud Task
    task = {
        "http_request": {
            "http_method": "POST",
            "url": f"{JIB_TASK_URL}/execute",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "job_id": job_id,
                "description": description,
                "user_id": command["user_id"],
                "channel_id": command["channel_id"],
            }).encode(),
        }
    }

    tasks_client.create_task(
        parent=f"projects/{PROJECT}/locations/{REGION}/queues/jib-tasks",
        task=task
    )

    return job_id

@app.route("/slack/commands", methods=["POST"])
def slack_commands():
    return handler.handle(request)

@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)
```

### 3. Cloud Tasks Configuration

```yaml
# terraform/cloud_tasks.tf

resource "google_cloud_tasks_queue" "jib_tasks" {
  name     = "jib-tasks"
  location = var.region

  rate_limits {
    max_concurrent_dispatches = 3  # Limit parallel jib instances
    max_dispatches_per_second = 1
  }

  retry_config {
    max_attempts       = 3
    min_backoff        = "10s"
    max_backoff        = "300s"
    max_retry_duration = "3600s"  # 1 hour max
  }
}

resource "google_cloud_tasks_queue" "jib_sync" {
  name     = "jib-sync"
  location = var.region

  rate_limits {
    max_concurrent_dispatches = 1  # Only one sync at a time
    max_dispatches_per_second = 0.1
  }
}

resource "google_cloud_tasks_queue" "jib_analyze" {
  name     = "jib-analyze"
  location = var.region

  rate_limits {
    max_concurrent_dispatches = 1  # Analysis is resource-intensive
    max_dispatches_per_second = 0.1
  }
}
```

### 4. Firestore Schema

```
firestore/
├── jobs/
│   └── {job_id}/
│       ├── id: string
│       ├── type: "task" | "sync" | "analyze" | "pr"
│       ├── description: string
│       ├── user_id: string
│       ├── channel_id: string
│       ├── thread_ts: string (optional)
│       ├── status: "queued" | "running" | "completed" | "failed" | "cancelled"
│       ├── progress: number (0-100)
│       ├── result: map (optional)
│       ├── error: string (optional)
│       ├── created_at: timestamp
│       ├── started_at: timestamp (optional)
│       └── completed_at: timestamp (optional)
│
├── threads/
│   └── {task_id}/
│       ├── thread_ts: string
│       ├── channel_id: string
│       └── updated_at: timestamp
│
├── contexts/
│   └── {context_name}/
│       ├── name: string
│       ├── content: string
│       ├── user_id: string
│       ├── created_at: timestamp
│       └── updated_at: timestamp
│
└── beads/
    └── {bead_id}/
        ├── id: string
        ├── description: string
        ├── status: "pending" | "in_progress" | "done"
        ├── tags: array<string>
        ├── notes: string
        ├── parent_id: string (optional)
        ├── created_at: timestamp
        └── updated_at: timestamp
```

### 5. Security Model

**Authentication:**
- Slack request signing (HMAC-SHA256) validates all requests
- Cloud Run IAM restricts who can invoke services
- Workload Identity for GCP service-to-service auth

**Authorization:**
- User allowlist in Firestore (initially just you)
- Rate limiting per user (10 commands/minute)
- Job ownership (users can only cancel their own jobs)

**Secrets Management:**
- Slack tokens in Secret Manager
- Accessed via Workload Identity
- No secrets in environment variables or code

```python
# Security middleware
def verify_slack_request(request):
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    # Verify timestamp (prevent replay attacks)
    if abs(time.time() - int(timestamp)) > 60 * 5:
        raise SecurityError("Request too old")

    # Verify signature
    sig_basestring = f"v0:{timestamp}:{request.get_data(as_text=True)}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise SecurityError("Invalid signature")

def check_user_allowed(user_id: str):
    allowed = db.collection("config").document("allowed_users").get()
    if user_id not in allowed.get("users", []):
        raise AuthorizationError("User not authorized")
```

## Migration Strategy

### Phase 1: Create Slack App (Week 1)

1. Create Slack app in workspace
2. Configure slash commands (pointing to placeholder URL)
3. Add OAuth scopes
4. Test slash command registration

**Deliverable:** Slack app configured, commands registered

### Phase 2: Deploy jib-bot Service (Week 2)

1. Deploy Cloud Run service (jib-bot)
2. Configure Slack app to point to Cloud Run URL
3. Implement basic command handlers (help, status)
4. Set up Firestore collections

**Deliverable:** `/jib help` and `/jib status` working

### Phase 3: Implement Task Execution (Weeks 3-4)

1. Create Cloud Tasks queues
2. Deploy jib-task Cloud Run Job
3. Implement `/jib task` command
4. Add job tracking and status updates
5. Implement `/jib cancel` and `/jib logs`

**Deliverable:** Full task execution via `/jib task`

### Phase 4: Implement Sync Commands (Week 5)

1. Deploy jib-sync Cloud Run Job
2. Implement `/sync` commands
3. Add scheduled sync triggers (Cloud Scheduler)
4. Migrate from systemd timers

**Deliverable:** Context sync via Slack commands

### Phase 5: Implement Analysis Commands (Week 6)

1. Deploy jib-analyze Cloud Run Job
2. Implement `/analyze` commands
3. Add progress reporting for long-running analysis

**Deliverable:** Analysis via Slack commands

### Phase 6: Implement Remaining Commands (Week 7)

1. `/pr` commands
2. `/context` commands
3. `/beads` commands
4. `/service` commands (Cloud Run management)

**Deliverable:** Full command parity

### Phase 7: Deprecate Host-Based Commands (Week 8)

1. Update documentation
2. Add deprecation notices to host commands
3. Remove host-based command infrastructure
4. Archive deprecated code

**Deliverable:** Clean cutover to Slack-based control

## Consequences

### Benefits

1. **Mobile-First Control:** Full jib control from phone
2. **No Host Required:** Control jib from anywhere
3. **Discoverability:** Slack shows available commands
4. **Job Tracking:** See status of long-running operations
5. **Multi-User Ready:** Foundation for multiple engineers
6. **Audit Trail:** All commands logged in Firestore
7. **GCP-Native:** Fully serverless, scales to zero

### Drawbacks

1. **Slack Dependency:** Requires Slack availability
2. **Latency:** Slash commands have 3-second response limit
3. **Complexity:** More components than host-based approach
4. **Cost:** Cloud Tasks, Firestore, Cloud Run (minimal at low volume)

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Slack outage | Jobs continue running; results cached for later delivery |
| Command spam | Rate limiting, user allowlist |
| Long response time | Immediate ack, async execution, progress updates |
| Job stuck | Timeout + automatic cleanup, manual cancel via command |
| Cost overrun | Budget alerts, concurrency limits, auto-scaling limits |

### Cost Estimate

| Component | Usage | Monthly Cost |
|-----------|-------|--------------|
| Cloud Run (jib-bot) | ~10K requests | ~$1 |
| Cloud Run Jobs (jib-task) | ~500 job-hours | ~$20 |
| Cloud Tasks | ~5K tasks | Free tier |
| Firestore | ~100K ops | Free tier |
| Secret Manager | ~1K accesses | Free tier |
| **Total** | | **~$21/month** |

## Decision Permanence

**High permanence.**

This establishes the control plane architecture for jib in GCP. The slash command interface becomes the primary way to interact with jib. Changing this would require:
- Rebuilding control plane
- Retraining users
- Updating all documentation

The specific commands can evolve, but the Slack bot as control plane is a foundational decision.

## Alternatives Considered

### Alternative 1: Keep Host-Based Commands

**Description:** Continue using host machine for jib control.

**Pros:**
- No migration effort
- Works today

**Cons:**
- Requires host machine access
- Doesn't work for GCP deployment
- Not mobile-friendly

**Rejected because:** Blocks GCP deployment and mobile-first goal.

### Alternative 2: Web Dashboard

**Description:** Build web UI for jib control instead of Slack.

**Pros:**
- Richer UI possibilities
- No Slack dependency
- Custom UX

**Cons:**
- Significant development effort
- Another app to maintain
- Context switching from Slack

**Rejected because:** Slack is where engineers already work. Building a separate UI adds friction.

### Alternative 3: CLI Only (gcloud-style)

**Description:** Build a `jib` CLI that talks to GCP APIs.

**Pros:**
- Familiar pattern (like gcloud)
- Scriptable
- No Slack dependency

**Cons:**
- Requires terminal access
- Not mobile-friendly
- Doesn't integrate with Slack notifications

**Rejected because:** Doesn't solve mobile-first requirement. Still need Slack for notifications anyway.

### Alternative 4: GitHub Actions / Issues

**Description:** Use GitHub Issues or Actions to trigger jib.

**Pros:**
- Integrated with code workflow
- Familiar to developers
- Good for automation

**Cons:**
- Not mobile-optimized
- Slower feedback loop
- Mixing concerns (code repo vs agent control)

**Rejected because:** Optimized for CI/CD, not interactive agent control.

## References

- [Slack Slash Commands Documentation](https://api.slack.com/interactivity/slash-commands)
- [Cloud Tasks Documentation](https://cloud.google.com/tasks/docs)
- [Cloud Run Jobs Documentation](https://cloud.google.com/run/docs/create-jobs)
- [ADR: Message Queue for Slack Integration](./ADR-Message-Queue-Slack-Integration.md)
- [ADR: Slack Integration Strategy - MCP vs Custom](./ADR-Slack-Integration-Strategy-MCP-vs-Custom.md)
- [ADR: Context Sync Strategy - Custom vs MCP](../implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)

---

**Last Updated:** 2025-11-28
**Next Review:** 2025-12-28 (Monthly)
**Status:** Proposed
