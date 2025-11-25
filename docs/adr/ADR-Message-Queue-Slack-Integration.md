# ADR: Message Queue for Slack Integration

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Proposed

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
- [Implementation Details](#implementation-details)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Alternatives Considered](#alternatives-considered)

## Context

### Background

The current Slack notification system uses **file-based communication**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              HOST                                        │
│  ┌─────────────────────┐         ┌─────────────────────┐                │
│  │ host-notify-slack.py│         │host-receive-slack.py│                │
│  │  (inotify watcher)  │         │  (Socket Mode)      │                │
│  │  15s batch window   │         │                     │                │
│  └──────────┬──────────┘         └──────────┬──────────┘                │
│             │ watches                        │ writes                    │
│  ┌──────────▼────────────────────────────────▼──────────┐               │
│  │              ~/.jib-sharing/                          │               │
│  │  notifications/  incoming/  responses/  tracking/     │               │
│  └──────────────────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────────────┘
```

**Current Implementation:**
- Container writes markdown files to `~/sharing/notifications/`
- Host-side `host-notify-slack.py` uses inotify to detect new files
- 15-second batch window before sending to Slack API
- Thread tracking via `slack-threads.json` file
- Bidirectional via `host-receive-slack.py` (Slack Socket Mode)

### Problem Statement

The file-based approach **works well for local laptop deployment** but has limitations:

1. **GCP Deployment Blocker:** File-based communication won't work when jib runs in Cloud Run
   - Cloud Run containers are ephemeral
   - No shared filesystem between services
   - Need network-based communication

2. **Reliability Gaps:**
   - No delivery guarantees (message lost if service crashes during send)
   - No retry logic for transient Slack API failures
   - No deduplication (same file written twice = duplicate messages)

3. **Observability Limitations:**
   - No visibility into pending/failed messages
   - No metrics on notification success rate
   - Thread mapping in fragile JSON file

4. **Latency:**
   - 15-second batch window adds delay
   - Acceptable for current use case but not ideal

### What We're Deciding

This ADR establishes the architecture for **replacing file-based Slack communication with a message queue** that:

1. Works both locally and in GCP
2. Provides delivery guarantees and retry logic
3. Enables the Cloud Run deployment path (Phase 3)
4. Maintains debugging transparency

## Decision

**We will use Google Cloud Pub/Sub as the message queue for Slack integration.**

### Why Pub/Sub

| Criteria | Pub/Sub | Redis Streams | Cloud Tasks | RabbitMQ |
|----------|---------|---------------|-------------|----------|
| Local emulator | Yes | N/A (native) | No | Yes |
| GCP managed | Yes | Memorystore ($) | Yes | No |
| Cloud Run integration | Native push | Requires VPC | Native | Manual |
| At-least-once delivery | Built-in | Manual | Built-in | Built-in |
| Dead letter queues | Built-in | Manual | Built-in | Built-in |
| Cost at low volume | Free tier | Always-on VM | Free tier | Self-hosted |
| Learning curve | Medium | Low | Medium | High |

**Pub/Sub wins because:**
1. **Local emulator** enables identical dev/prod code paths
2. **Native Cloud Run integration** via push subscriptions
3. **Free tier** covers jib's volume (~100 notifications/day)
4. **Dead letter topics** handle persistent failures automatically
5. **Fan-out capability** enables future monitoring/logging subscribers

## High-Level Design

### Local Development

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         docker-compose                                   │
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐ │
│  │     jib      │     │   Pub/Sub    │     │     slack-worker         │ │
│  │  container   │────▶│   Emulator   │────▶│     (container)          │ │
│  │              │     │  :8085       │     │                          │ │
│  └──────────────┘     └──────────────┘     └──────────────────────────┘ │
│                                                      │                   │
└──────────────────────────────────────────────────────┼───────────────────┘
                                                       │
                                                       ▼
                                                   Slack API
```

### GCP (Cloud Run)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              GCP                                         │
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐ │
│  │  Cloud Run   │     │  Cloud       │     │      Cloud Run           │ │
│  │  (jib)       │────▶│  Pub/Sub     │────▶│   (slack-worker)         │ │
│  │              │     │              │push │                          │ │
│  └──────────────┘     └──────────────┘     └──────────────────────────┘ │
│                              │                       │                   │
│                              ▼                       │                   │
│                       Dead Letter Topic              │                   │
│                       (failed messages)              │                   │
└──────────────────────────────────────────────────────┼───────────────────┘
                                                       │
                                                       ▼
                                                   Slack API
```

### Topics & Subscriptions

```
Topics:
├── slack-outgoing                    # jib → Slack messages
│   ├── slack-worker-sub              # Push to slack-worker service
│   └── audit-log-sub                 # (future) Log all notifications
│
├── slack-incoming                    # Slack → jib messages
│   └── jib-incoming-sub              # Push to jib container
│
└── slack-outgoing-dlq                # Dead letter for failed sends
    └── alert-sub                     # Notify on persistent failures
```

### Thread State Management

The current `slack-threads.json` won't work in GCP. We'll use **Firestore** for thread mapping:

| Option | Pros | Cons |
|--------|------|------|
| **Firestore** | Serverless, scales to zero, cheap | Another GCP service |
| Memorystore (Redis) | Familiar, fast | Always-on cost (~$35/month min) |
| Pub/Sub attributes | No extra service | Worker must track state |

**Decision:** Firestore for thread mapping
- Free tier: 50K reads, 20K writes/day (far exceeds jib's needs)
- Scales to zero cost when idle
- Simple key-value access pattern

## Implementation Details

### 1. Notification Library (Container Side)

```python
# notifications/pubsub.py
import json
import os
from google.cloud import pubsub_v1
from datetime import datetime
from .types import NotificationContext

class PubSubNotificationService:
    """Send notifications via Pub/Sub (works local + GCP)."""

    def __init__(self):
        self.project_id = os.environ.get("GCP_PROJECT_ID", "jib-local")
        self.topic_id = "slack-outgoing"
        self.publisher = pubsub_v1.PublisherClient()
        self.topic_path = self.publisher.topic_path(self.project_id, self.topic_id)

    def send(self, title: str, body: str, context: NotificationContext = None,
             priority: str = "normal") -> str:
        """Publish notification to Pub/Sub."""

        message = {
            "title": title,
            "body": body,
            "priority": priority,
            "timestamp": datetime.utcnow().isoformat(),
            "context": context.to_dict() if context else {}
        }

        # Pub/Sub message attributes (for filtering/routing)
        attributes = {
            "priority": priority,
            "type": "notification",
        }
        if context and context.task_id:
            attributes["task_id"] = context.task_id

        future = self.publisher.publish(
            self.topic_path,
            json.dumps(message).encode("utf-8"),
            **attributes
        )

        return future.result()  # Returns message ID
```

### 2. Slack Worker Service

```python
# slack-worker/main.py
import os
import json
import base64
import logging
from flask import Flask, request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from google.cloud import firestore

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

slack = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
db = firestore.Client()
SLACK_CHANNEL = os.environ["SLACK_CHANNEL"]

@app.route("/", methods=["POST"])
def handle_pubsub():
    """Receive Pub/Sub push messages."""
    envelope = request.get_json()

    if not envelope or "message" not in envelope:
        return "Bad Request", 400

    pubsub_message = envelope["message"]
    data = json.loads(
        base64.b64decode(pubsub_message["data"]).decode("utf-8")
    )
    attributes = pubsub_message.get("attributes", {})

    try:
        send_to_slack(data, attributes)
        return "OK", 200
    except SlackApiError as e:
        logging.error(f"Slack API error: {e}")
        # Return 500 to trigger Pub/Sub retry
        return "Slack Error", 500

def send_to_slack(data: dict, attributes: dict):
    """Send message to Slack, handling threading."""

    task_id = attributes.get("task_id") or data.get("context", {}).get("task_id")
    thread_ts = get_thread_ts(task_id) if task_id else None

    # Format message
    text = f"*{data['title']}*\n\n{data['body']}"

    # Send to Slack
    response = slack.chat_postMessage(
        channel=SLACK_CHANNEL,
        text=text,
        thread_ts=thread_ts,
        unfurl_links=False
    )

    # Cache thread for future messages
    if task_id and not thread_ts:
        set_thread_ts(task_id, response["ts"])

    logging.info(f"Sent to Slack: {response['ts']}")

def get_thread_ts(task_id: str) -> str | None:
    """Get thread timestamp from Firestore."""
    doc = db.collection("slack_threads").document(task_id).get()
    return doc.get("thread_ts") if doc.exists else None

def set_thread_ts(task_id: str, thread_ts: str):
    """Store thread timestamp in Firestore."""
    db.collection("slack_threads").document(task_id).set({
        "thread_ts": thread_ts,
        "updated_at": firestore.SERVER_TIMESTAMP
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
```

### 3. Local Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  pubsub-emulator:
    image: gcr.io/google.com/cloudsdktool/cloud-sdk:emulators
    command: >
      gcloud beta emulators pubsub start
      --host-port=0.0.0.0:8085
      --project=jib-local
    ports:
      - "8085:8085"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8085"]
      interval: 5s
      timeout: 5s
      retries: 5

  pubsub-init:
    image: gcr.io/google.com/cloudsdktool/cloud-sdk:latest
    depends_on:
      pubsub-emulator:
        condition: service_healthy
    environment:
      - PUBSUB_EMULATOR_HOST=pubsub-emulator:8085
    entrypoint: ["/bin/bash", "-c"]
    command:
      - |
        # Create topics
        curl -X PUT "http://pubsub-emulator:8085/v1/projects/jib-local/topics/slack-outgoing"
        curl -X PUT "http://pubsub-emulator:8085/v1/projects/jib-local/topics/slack-incoming"
        curl -X PUT "http://pubsub-emulator:8085/v1/projects/jib-local/topics/slack-outgoing-dlq"

        # Create push subscription to slack-worker
        curl -X PUT "http://pubsub-emulator:8085/v1/projects/jib-local/subscriptions/slack-worker-sub" \
          -H "Content-Type: application/json" \
          -d '{
            "topic": "projects/jib-local/topics/slack-outgoing",
            "pushConfig": {"pushEndpoint": "http://slack-worker:8080"}
          }'

        echo "Pub/Sub initialized"

  firestore-emulator:
    image: gcr.io/google.com/cloudsdktool/cloud-sdk:emulators
    command: >
      gcloud beta emulators firestore start
      --host-port=0.0.0.0:8086
      --project=jib-local
    ports:
      - "8086:8086"

  slack-worker:
    build: ./components/slack-worker
    ports:
      - "8080:8080"
    environment:
      - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
      - SLACK_CHANNEL=${SLACK_CHANNEL}
      - PUBSUB_EMULATOR_HOST=pubsub-emulator:8085
      - FIRESTORE_EMULATOR_HOST=firestore-emulator:8086
      - GCP_PROJECT_ID=jib-local
    depends_on:
      - pubsub-init
      - firestore-emulator

  jib:
    build: ./jib-container
    environment:
      - PUBSUB_EMULATOR_HOST=pubsub-emulator:8085
      - FIRESTORE_EMULATOR_HOST=firestore-emulator:8086
      - GCP_PROJECT_ID=jib-local
    depends_on:
      - pubsub-init
    volumes:
      - ~/khan:/home/user/khan:rw
      - ~/.claude:/home/user/.claude:rw
```

### 4. GCP Infrastructure (Terraform)

```hcl
# terraform/pubsub.tf

resource "google_pubsub_topic" "slack_outgoing" {
  name = "slack-outgoing"

  message_retention_duration = "86400s"  # 24 hours
}

resource "google_pubsub_topic" "slack_outgoing_dlq" {
  name = "slack-outgoing-dlq"
}

resource "google_pubsub_subscription" "slack_worker" {
  name  = "slack-worker-sub"
  topic = google_pubsub_topic.slack_outgoing.name

  push_config {
    push_endpoint = google_cloud_run_service.slack_worker.status[0].url

    oidc_token {
      service_account_email = google_service_account.pubsub_invoker.email
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.slack_outgoing_dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  ack_deadline_seconds = 30
}

resource "google_pubsub_topic" "slack_incoming" {
  name = "slack-incoming"
}

# Firestore for thread state
resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}
```

## Migration Strategy

### Phase 1: Add Pub/Sub Alongside File-Based (Low Risk)

**Goal:** Validate Pub/Sub locally without breaking existing system

1. Add `notifications/pubsub.py` to container
2. Add feature flag: `NOTIFICATION_BACKEND=file|pubsub`
3. Run Pub/Sub emulator in docker-compose (optional service)
4. Test locally with both backends

**Rollback:** Set `NOTIFICATION_BACKEND=file`

### Phase 2: Deploy Slack Worker Service

**Goal:** Run slack-worker as standalone service

1. Create `components/slack-worker/` with Flask app
2. Deploy locally via docker-compose
3. Test end-to-end: jib → Pub/Sub → slack-worker → Slack
4. Validate threading, retries, error handling

**Success Criteria:**
- Messages delivered within 5 seconds
- Retries work for transient failures
- Thread continuity maintained

### Phase 3: Switch to Pub/Sub Primary

**Goal:** Make Pub/Sub the default backend

1. Set `NOTIFICATION_BACKEND=pubsub` as default
2. Keep file-based as fallback (graceful degradation)
3. Monitor for issues over 1 week
4. Remove file-based code after validation

### Phase 4: Deploy to GCP

**Goal:** Run full system in Cloud Run

1. Deploy Pub/Sub topics via Terraform
2. Deploy slack-worker to Cloud Run
3. Deploy jib to Cloud Run
4. Migrate thread state from JSON to Firestore
5. Decommission host-side services

## Consequences

### Positive

1. **Enables GCP Deployment:** Unblocks Cloud Run migration (Phase 3 goal)
2. **Improved Reliability:** At-least-once delivery, automatic retries, dead letter handling
3. **Better Observability:** Pub/Sub metrics, Cloud Monitoring integration
4. **Reduced Latency:** Sub-second delivery vs 15-second batch window
5. **Scalability:** Can handle multiple jib instances, fan-out to monitoring
6. **Consistent Dev/Prod:** Same code path locally and in GCP

### Negative

1. **Increased Complexity:** More services to manage (Pub/Sub, Firestore, slack-worker)
2. **Local Dev Changes:** Need to run emulators (docker-compose handles this)
3. **New Dependencies:** google-cloud-pubsub, google-cloud-firestore packages
4. **Learning Curve:** Team needs to understand Pub/Sub patterns
5. **Debugging:** Harder than inspecting files (mitigated by logging)

### Neutral

1. **Cost:** Essentially free at current volume, scales with usage
2. **Testing:** Different approach (emulator vs real files)
3. **Thread State:** Moves from JSON file to Firestore (same data, different store)

## Alternatives Considered

### 1. Redis Streams (Local) → Memorystore (GCP)

**Pros:**
- Redis already running in container
- Familiar patterns
- Low latency

**Cons:**
- Memorystore requires VPC connector ($35+/month minimum)
- No native Cloud Run push integration
- Would need custom worker polling Redis

**Decision:** Rejected due to cost and complexity for Cloud Run integration

### 2. Cloud Tasks

**Pros:**
- Built for HTTP task dispatch
- Native retry/scheduling
- Good Cloud Run integration

**Cons:**
- No local emulator (must use real service or mock)
- Less flexible than Pub/Sub (no fan-out)
- Harder to debug locally

**Decision:** Rejected due to lack of local emulator

### 3. Keep File-Based, Use Cloud Storage

**Pros:**
- Minimal code changes
- Cloud Storage has change notifications

**Cons:**
- Cloud Storage notifications are eventually consistent (minutes delay)
- Still need worker to process files
- Doesn't solve reliability issues

**Decision:** Rejected due to latency and reliability gaps

### 4. Direct Slack API from Container

**Pros:**
- Simplest architecture
- No intermediate services

**Cons:**
- No retry logic
- No delivery guarantees
- Token management in container (security concern)
- Can't fan-out to monitoring

**Decision:** Rejected due to reliability and security concerns

### 5. Hybrid: Redis Buffer + File Output

**Pros:**
- Keeps file debugging
- Adds reliability via Redis
- No host-side changes

**Cons:**
- Doesn't solve GCP deployment problem
- Two systems to maintain
- Redis still unused outside container

**Decision:** Rejected as it doesn't address core GCP deployment blocker

## Cost Estimate

At jib's expected volume (~100-500 notifications/day):

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Cloud Pub/Sub | ~15,000 msgs/month | Free tier |
| Cloud Run (slack-worker) | ~15,000 invocations/month | Free tier |
| Firestore | ~30,000 reads, 15,000 writes/month | Free tier |
| **Total** | | **$0** |

Cost becomes non-trivial only at >10,000 notifications/day (~$5-10/month).

## Related ADRs

This ADR is the foundation for a series defining the jib GCP deployment architecture:

| ADR | Relationship to This ADR |
|-----|-------------------------|
| [ADR-Context-Sync-Strategy-Custom-vs-MCP](./ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | Sync jobs use Pub/Sub to send completion notifications |
| [ADR-Slack-Integration-Strategy-MCP-vs-Custom](./ADR-Slack-Integration-Strategy-MCP-vs-Custom.md) | Defines MCP for reading Slack (complementary to Pub/Sub for sending) |
| [ADR-Slack-Bot-GCP-Integration](./ADR-Slack-Bot-GCP-Integration.md) | Slash commands trigger jobs that publish results via Pub/Sub |
| [ADR-GCP-Deployment-Terraform](./ADR-GCP-Deployment-Terraform.md) | Terraform definitions for Pub/Sub topics, slack-worker service |

## References

- [Cloud Pub/Sub Documentation](https://cloud.google.com/pubsub/docs)
- [Pub/Sub Emulator](https://cloud.google.com/pubsub/docs/emulator)
- [Cloud Run Push Subscriptions](https://cloud.google.com/run/docs/triggering/pubsub-push)
- [Firestore Documentation](https://cloud.google.com/firestore/docs)
- [Current Slack Integration Architecture](../architecture/slack-integration.md)
