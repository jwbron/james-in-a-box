# ADR: GCP Deployment Architecture and Terraform Infrastructure

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams, SRE
**Proposed:** November 2025
**Status:** Proposed

## Table of Contents

- [Current Implementation Status](#current-implementation-status)
- [Context](#context)
- [Decision](#decision)
- [Decision Matrix](#decision-matrix)
- [Infrastructure Architecture](#infrastructure-architecture)
- [Terraform Structure](#terraform-structure)
- [Scheduled Jobs](#scheduled-jobs)
- [Security and Access Control](#security-and-access-control)
- [Cost Analysis](#cost-analysis)
- [Usage Limits and Quotas](#usage-limits-and-quotas)
- [Gaps and Additional Considerations](#gaps-and-additional-considerations)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)

## Current Implementation Status

**Phase 1 (Complete):** Laptop-based deployment
- Docker container running on engineer's laptop
- File-based communication via mounted directories
- Systemd services for host-side components
- Manual container management via `jib` CLI

**Phase 3 (This ADR):** GCP Cloud Run deployment
- Cloud Run services and jobs for all components
- Terraform-managed infrastructure per ADR #889
- Pub/Sub for messaging per ADR-Message-Queue
- Firestore for state management
- Slack bot as control plane per ADR-Slack-Bot-GCP-Integration

## Context

### Background

This ADR defines the complete GCP deployment architecture for jib, building on four previous ADRs:

| ADR | Purpose | Key Decisions |
|-----|---------|---------------|
| ADR-Message-Queue | Slack transport | Cloud Pub/Sub, Firestore for threads |
| ADR-Context-Sync | External data access | MCP for Jira/GitHub, custom sync for Confluence |
| ADR-Slack-Integration | Slack read/write | MCP for reading, Pub/Sub for sending |
| ADR-Slack-Bot-GCP | Control plane | Slash commands, Cloud Tasks, job management |

This ADR addresses:
1. **How** to deploy these components to GCP
2. **Terraform structure** following Khan Academy standards (ADR #889)
3. **Scheduled jobs** using established patterns
4. **Security**, access control, and authentication
5. **Cost** analysis and usage limits
6. **Gaps** in the overall architecture

### What We're Deciding

1. **GCP Project Structure:** Where jib resources live
2. **Cloud Run Configuration:** Services, jobs, scaling
3. **Terraform Organization:** Repository structure, CI/CD
4. **Scheduled Jobs:** Context sync, analyzers, maintenance
5. **Security Model:** Authentication, authorization, secrets
6. **Access Control:** User allowlist, rate limiting, audit
7. **Cost Management:** Budgets, quotas, optimization

### Key Requirements

| Requirement | Priority | Notes |
|-------------|----------|-------|
| Follow ADR #889 Terraform patterns | High | Workload Identity, dual service accounts |
| Use scheduled-job module | High | Established pattern for cron jobs |
| Security-first | High | Least privilege, audit trail |
| Cost-efficient | High | Scale to zero, budget alerts |
| Multi-user capable | Medium | Foundation for team expansion |
| Observable | Medium | Logging, monitoring, alerting |

## Decision

**We will deploy jib to GCP using Cloud Run, following Khan Academy's Terraform CI/CD standards (ADR #889), with security controls appropriate for an autonomous agent.**

### Core Principles

1. **ADR #889 Compliance:** Terraform CI/CD, Workload Identity, dual service accounts
2. **Serverless-First:** Cloud Run scales to zero, pay-per-use
3. **Least Privilege:** Each component gets minimal required permissions
4. **Defense in Depth:** Multiple security layers (auth, authz, audit)
5. **Cost Awareness:** Budgets, quotas, and alerts from day one

## Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **GCP Project** | Dedicated `khan-jib` project | Isolation, clear cost attribution | Shared project (blast radius) |
| **Compute** | Cloud Run (services + jobs) | Serverless, scales to zero | GKE (overkill), GCE (always-on cost) |
| **Terraform CI/CD** | ADR #889 patterns | Established, secure, auditable | Manual applies (no audit) |
| **Scheduled Jobs** | scheduled-job module | Established pattern, alerting built-in | Cloud Scheduler only (no monitoring) |
| **Secrets** | Secret Manager | Rotation, audit, no keys in env | Env vars (insecure) |
| **Auth** | Workload Identity + Slack OAuth | Keyless, user-scoped | Service account keys (insecure) |
| **Access Control** | Firestore allowlist + rate limits | Flexible, auditable | IAM only (too rigid) |

## Infrastructure Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              GCP Project: khan-jib                               │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                         Cloud Run Services                                  │ │
│  │                                                                             │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │ │
│  │  │   jib-bot       │  │  slack-worker   │  │   slack-receiver            │ │ │
│  │  │                 │  │                 │  │                             │ │ │
│  │  │ • Slash cmds    │  │ • Send messages │  │ • Events API webhook        │ │ │
│  │  │ • Job manager   │  │ • Rate limiting │  │ • Socket Mode (optional)    │ │ │
│  │  │ • Status API    │  │ • Thread mgmt   │  │ • Message routing           │ │ │
│  │  │                 │  │                 │  │                             │ │ │
│  │  │ Min: 0, Max: 3  │  │ Min: 0, Max: 5  │  │ Min: 1, Max: 3              │ │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                          Cloud Run Jobs                                     │ │
│  │                                                                             │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │ │
│  │  │   jib-task      │  │   jib-sync      │  │   jib-analyze               │ │ │
│  │  │                 │  │                 │  │                             │ │ │
│  │  │ • Claude Code   │  │ • Confluence    │  │ • Codebase analyzer         │ │ │
│  │  │ • Task exec     │  │ • JIRA          │  │ • Conversation analyzer     │ │ │
│  │  │ • PR creation   │  │ • GitHub        │  │ • PR reviewer               │ │ │
│  │  │                 │  │                 │  │                             │ │ │
│  │  │ CPU: 4, Mem: 8G │  │ CPU: 1, Mem: 2G │  │ CPU: 2, Mem: 4G             │ │ │
│  │  │ Timeout: 4h     │  │ Timeout: 30m    │  │ Timeout: 1h                 │ │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                          Supporting Services                                │ │
│  │                                                                             │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │ │
│  │  │   Cloud Pub/Sub │  │    Firestore    │  │   Cloud Storage             │ │ │
│  │  │                 │  │                 │  │                             │ │ │
│  │  │ • slack-outgoing│  │ • jobs/         │  │ • jib-context-sync          │ │ │
│  │  │ • slack-incoming│  │ • threads/      │  │ • jib-artifacts             │ │ │
│  │  │ • job-updates   │  │ • users/        │  │ • terraform-state           │ │ │
│  │  │ • dead-letter   │  │ • contexts/     │  │                             │ │ │
│  │  │                 │  │ • beads/        │  │                             │ │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │ │
│  │                                                                             │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │ │
│  │  │  Cloud Tasks    │  │ Cloud Scheduler │  │   Secret Manager            │ │ │
│  │  │                 │  │                 │  │                             │ │ │
│  │  │ • jib-tasks     │  │ • sync-confl    │  │ • slack-bot-token           │ │ │
│  │  │ • jib-sync      │  │ • sync-jira     │  │ • slack-app-token           │ │ │
│  │  │ • jib-analyze   │  │ • sync-github   │  │ • anthropic-api-key         │ │ │
│  │  │                 │  │ • analyze-*     │  │ • github-token              │ │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                          Monitoring & Alerting                              │ │
│  │                                                                             │ │
│  │  • Cloud Monitoring dashboards                                              │ │
│  │  • Alert policies for job failures → Slack                                  │ │
│  │  • Budget alerts → Email + Slack                                            │ │
│  │  • Error reporting                                                          │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Network Architecture

```
                                    Internet
                                        │
                                        │ HTTPS
                                        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                              Cloud Load Balancer                               │
│                           (managed by Cloud Run)                               │
└─────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
            ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
            │   jib-bot     │   │ slack-worker  │   │slack-receiver │
            │ (slash cmds)  │   │ (Pub/Sub push)│   │ (events API)  │
            └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
                    │                   │                   │
                    │                   │                   │
                    ▼                   ▼                   ▼
            ┌─────────────────────────────────────────────────────┐
            │                    VPC Connector                     │
            │              (for internal services)                 │
            └─────────────────────────────────────────────────────┘
                                        │
                                        ▼
                              ┌───────────────────┐
                              │  External APIs    │
                              │  • Anthropic      │
                              │  • GitHub         │
                              │  • Atlassian      │
                              │  • Slack          │
                              └───────────────────┘
```

## Terraform Structure

### Repository Structure (Pattern A from ADR #889)

jib is a single deployable unit with shared infrastructure:

```
james-in-a-box/
├── .github/
│   └── workflows/
│       ├── terraform-lint.yml              # Terraform linting (fmt, tflint, checkov)
│       ├── build-terraform-plan.yml        # Plan generation
│       └── apply-terraform-plan.yml        # Plan application
│
├── terraform/
│   ├── bootstrap/                          # CI service account setup (run locally once)
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── README.md
│   │
│   ├── infrastructure/                     # Main infrastructure (managed in CI)
│   │   ├── main.tf                         # Root module
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   ├── versions.tf                     # Provider versions
│   │   ├── backend.tf                      # GCS backend config
│   │   │
│   │   ├── services/                       # Cloud Run services
│   │   │   ├── jib-bot.tf
│   │   │   ├── slack-worker.tf
│   │   │   └── slack-receiver.tf
│   │   │
│   │   ├── jobs/                           # Cloud Run jobs
│   │   │   ├── jib-task.tf
│   │   │   ├── jib-sync.tf
│   │   │   └── jib-analyze.tf
│   │   │
│   │   ├── messaging/                      # Pub/Sub, Cloud Tasks
│   │   │   ├── pubsub.tf
│   │   │   └── cloud-tasks.tf
│   │   │
│   │   ├── storage/                        # Firestore, GCS, Secrets
│   │   │   ├── firestore.tf
│   │   │   ├── gcs.tf
│   │   │   └── secrets.tf
│   │   │
│   │   ├── scheduled/                      # Scheduled jobs (using scheduled-job module)
│   │   │   ├── sync-confluence.tf
│   │   │   ├── sync-jira.tf
│   │   │   ├── sync-github.tf
│   │   │   ├── analyze-codebase.tf
│   │   │   └── analyze-conversation.tf
│   │   │
│   │   ├── security/                       # IAM, service accounts
│   │   │   ├── service-accounts.tf
│   │   │   └── iam.tf
│   │   │
│   │   ├── monitoring/                     # Dashboards, alerts
│   │   │   ├── dashboards.tf
│   │   │   ├── alerts.tf
│   │   │   └── budget.tf
│   │   │
│   │   ├── tfplan.binary                   # Generated by CI (git-tracked)
│   │   └── tfplan.txt                      # Generated by CI (git-tracked)
│   │
│   ├── Makefile                            # Local development helpers
│   └── README.md                           # Setup and usage docs
│
├── services/                               # Service source code
│   ├── jib-bot/
│   ├── slack-worker/
│   └── slack-receiver/
│
├── jobs/                                   # Job source code
│   ├── jib-task/
│   ├── jib-sync/
│   └── jib-analyze/
│
└── docs/
    └── adr/                                # This and related ADRs
```

### Bootstrap Configuration

Following ADR #889, bootstrap creates CI service accounts with Workload Identity:

```hcl
# terraform/bootstrap/main.tf

module "github_ci_bootstrap" {
  source = "git::https://github.com/Khan/terraform-modules.git//terraform/modules/github-ci-bootstrap?ref=github-ci-bootstrap-v1.0.2"

  service_name      = "jib-prod"
  github_repository = "Khan/james-in-a-box"  # or jwbron/james-in-a-box

  target_projects = {
    "khan-jib" = {
      required_services = [
        "run",              # Cloud Run
        "cloudbuild",       # Container builds
        "cloudscheduler",   # Scheduled jobs
        "cloudtasks",       # Task queues
        "pubsub",           # Messaging
        "firestore",        # State storage
        "storage",          # GCS buckets
        "secretmanager",    # Secrets
        "monitoring",       # Observability
        "logging",          # Logs
      ]
    }
  }

  terraform_state_bucket = "terraform-khan-academy"

  secrets_project_id = "khan-academy"
  secret_ids = [
    "jib-slack-bot-token",
    "jib-slack-app-token",
    "jib-anthropic-api-key",
    "jib-github-token",
    "Slack__API_token_for_alertlib",  # For alerting
  ]
}
```

### Main Infrastructure Configuration

```hcl
# terraform/infrastructure/main.tf

terraform {
  required_version = ">= 1.9.0"

  backend "gcs" {
    bucket = "terraform-khan-academy"
    prefix = "jib/infrastructure"
  }
}

locals {
  project_id         = "khan-jib"
  region             = "us-central1"
  secrets_project_id = "khan-academy"
}

# Cloud Run Services
module "jib_bot" {
  source = "./services/jib-bot"

  project_id = local.project_id
  region     = local.region

  slack_bot_token_secret    = "jib-slack-bot-token"
  slack_signing_secret      = "jib-slack-signing-secret"
  secrets_project_id        = local.secrets_project_id

  service_account_email = google_service_account.jib_bot.email

  min_instances = 0
  max_instances = 3
}

module "slack_worker" {
  source = "./services/slack-worker"

  project_id = local.project_id
  region     = local.region

  pubsub_subscription = google_pubsub_subscription.slack_worker.name
  firestore_database  = google_firestore_database.default.name

  service_account_email = google_service_account.slack_worker.email

  min_instances = 0
  max_instances = 5
}

# Cloud Run Jobs
module "jib_task" {
  source = "./jobs/jib-task"

  project_id = local.project_id
  region     = local.region

  cpu       = "4"
  memory    = "8Gi"
  timeout   = "14400s"  # 4 hours

  anthropic_api_key_secret = "jib-anthropic-api-key"
  github_token_secret      = "jib-github-token"
  secrets_project_id       = local.secrets_project_id

  service_account_email = google_service_account.jib_task.email
}
```

## Scheduled Jobs

Using the `scheduled-job` module from `terraform-modules`:

### Context Sync Jobs

```hcl
# terraform/infrastructure/scheduled/sync-confluence.tf

module "sync_confluence" {
  source = "git::https://github.com/Khan/terraform-modules.git//terraform/modules/scheduled-job?ref=v1.0.0"

  job_name           = "jib-sync-confluence"
  execution_type     = "job"
  project_id         = local.project_id
  secrets_project_id = local.secrets_project_id

  source_dir  = "${path.root}/../../jobs/jib-sync"
  main_file   = "sync_confluence.py"
  schedule    = "0 * * * *"  # Hourly
  description = "Sync Confluence documentation to jib context"

  job_cpu     = "1000m"
  job_memory  = "2Gi"
  job_timeout = "1800s"  # 30 minutes
  job_image   = module.jib_sync_image.image_digest

  environment_variables = {
    SYNC_TYPE         = "confluence"
    OUTPUT_BUCKET     = google_storage_bucket.context_sync.name
    FIRESTORE_PROJECT = local.project_id
  }

  secrets = [
    {
      env_var_name = "CONFLUENCE_API_TOKEN"
      secret_id    = "jib-confluence-api-token"
      version      = "latest"
    }
  ]

  # Alerting
  enable_alerting     = true
  slack_channel       = "#jib-alerts"
  slack_mention_users = ["@jwiesebron"]
}
```

### Analyzer Jobs

```hcl
# terraform/infrastructure/scheduled/analyze-codebase.tf

module "analyze_codebase" {
  source = "git::https://github.com/Khan/terraform-modules.git//terraform/modules/scheduled-job?ref=v1.0.0"

  job_name           = "jib-analyze-codebase"
  execution_type     = "job"
  project_id         = local.project_id
  secrets_project_id = local.secrets_project_id

  source_dir  = "${path.root}/../../jobs/jib-analyze"
  main_file   = "codebase_analyzer.py"
  schedule    = "0 11 * * 1"  # Monday 11 AM
  description = "Weekly codebase analysis with improvement suggestions"

  job_cpu     = "2000m"
  job_memory  = "4Gi"
  job_timeout = "3600s"  # 1 hour
  job_image   = module.jib_analyze_image.image_digest

  environment_variables = {
    ANALYSIS_TYPE     = "codebase"
    PUBSUB_TOPIC      = google_pubsub_topic.slack_outgoing.name
  }

  secrets = [
    {
      env_var_name = "ANTHROPIC_API_KEY"
      secret_id    = "jib-anthropic-api-key"
      version      = "latest"
    }
  ]

  enable_alerting     = true
  slack_channel       = "#jib-alerts"
  slack_mention_users = ["@jwiesebron"]
}
```

### Scheduled Jobs Summary

| Job | Schedule | Purpose | Timeout | Resources |
|-----|----------|---------|---------|------------|
| `sync-confluence` | Hourly | Sync documentation | 30m | 1 CPU, 2GB |
| `sync-jira` | Hourly | Sync tickets | 30m | 1 CPU, 2GB |
| `sync-github` | Every 15m | Sync PRs, checks | 15m | 1 CPU, 2GB |
| `analyze-codebase` | Weekly (Mon 11AM) | Code quality analysis | 1h | 2 CPU, 4GB |
| `analyze-conversation` | Daily (2AM) | Conversation quality | 30m | 1 CPU, 2GB |
| `cleanup-jobs` | Daily (3AM) | Clean old job records | 15m | 0.5 CPU, 512MB |

## Security and Access Control

### Authentication Layers

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Authentication Flow                                 │
│                                                                                  │
│  1. Slack Request Signing                                                        │
│     ┌──────────────┐                                                            │
│     │ Slack API    │──── X-Slack-Signature ────▶ jib-bot validates HMAC        │
│     └──────────────┘                                                            │
│                                                                                  │
│  2. User Identity                                                                │
│     ┌──────────────┐                                                            │
│     │ Slack User   │──── user_id in payload ───▶ Lookup in Firestore users/    │
│     └──────────────┘                                                            │
│                                                                                  │
│  3. Service-to-Service (Workload Identity)                                       │
│     ┌──────────────┐                                                            │
│     │ Cloud Run    │──── IAM token ────────────▶ Other GCP services             │
│     └──────────────┘                                                            │
│                                                                                  │
│  4. External APIs                                                                │
│     ┌──────────────┐                                                            │
│     │ jib-task     │──── API keys from Secrets ─▶ Anthropic, GitHub, Atlassian │
│     └──────────────┘                                                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Authorization Model

```hcl
# terraform/infrastructure/storage/firestore.tf

# User authorization data stored in Firestore
# Collection: users/{user_id}

# Example document structure:
# {
#   "slack_user_id": "U0123456789",
#   "email": "jwiesebron@khanacademy.org",
#   "name": "James Wiesebron",
#   "role": "admin",                    # admin | user | readonly
#   "allowed_commands": ["*"],          # or specific: ["jib", "sync", "pr"]
#   "rate_limit": {
#     "commands_per_minute": 20,
#     "tasks_per_hour": 10,
#     "tokens_per_day": 1000000
#   },
#   "created_at": "2025-11-25T00:00:00Z",
#   "updated_at": "2025-11-25T00:00:00Z"
# }
```

### Authorization Logic

```python
# services/jib-bot/auth.py

from google.cloud import firestore
from functools import wraps
import time

db = firestore.Client()

class AuthorizationError(Exception):
    pass

class RateLimitError(Exception):
    pass

def authorize_user(user_id: str, command: str) -> dict:
    """Check if user is authorized to run command."""

    # Get user from Firestore
    user_ref = db.collection("users").document(user_id)
    user = user_ref.get()

    if not user.exists:
        raise AuthorizationError(f"User {user_id} not authorized to use jib")

    user_data = user.to_dict()

    # Check role
    if user_data.get("role") == "readonly":
        raise AuthorizationError("Read-only users cannot execute commands")

    # Check command allowlist
    allowed = user_data.get("allowed_commands", [])
    if "*" not in allowed and command not in allowed:
        raise AuthorizationError(f"User not authorized for /{command}")

    # Check rate limit
    check_rate_limit(user_id, user_data.get("rate_limit", {}))

    return user_data

def check_rate_limit(user_id: str, limits: dict):
    """Check and enforce rate limits."""

    commands_per_minute = limits.get("commands_per_minute", 10)

    # Get recent command count from Firestore
    now = time.time()
    minute_ago = now - 60

    commands_ref = db.collection("rate_limits").document(user_id)
    commands = commands_ref.get()

    if commands.exists:
        recent = [t for t in commands.to_dict().get("timestamps", []) if t > minute_ago]
        if len(recent) >= commands_per_minute:
            raise RateLimitError(f"Rate limit exceeded: {commands_per_minute}/minute")
        recent.append(now)
        commands_ref.update({"timestamps": recent})
    else:
        commands_ref.set({"timestamps": [now]})

def requires_auth(command: str):
    """Decorator for command handlers."""
    def decorator(func):
        @wraps(func)
        def wrapper(ack, command_payload, respond, *args, **kwargs):
            try:
                user = authorize_user(command_payload["user_id"], command)
                return func(ack, command_payload, respond, user=user, *args, **kwargs)
            except AuthorizationError as e:
                ack()
                respond(f"❌ {str(e)}", response_type="ephemeral")
            except RateLimitError as e:
                ack()
                respond(f"⏱️ {str(e)}", response_type="ephemeral")
        return wrapper
    return decorator
```

### Service Account Permissions

Each component gets minimal required permissions:

```hcl
# terraform/infrastructure/security/service-accounts.tf

# jib-bot: Slash command handler
resource "google_service_account" "jib_bot" {
  account_id   = "jib-bot"
  display_name = "jib Slack Bot"
  description  = "Service account for jib-bot slash command handler"
}

resource "google_project_iam_member" "jib_bot_firestore" {
  project = local.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.jib_bot.email}"
}

resource "google_project_iam_member" "jib_bot_tasks" {
  project = local.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.jib_bot.email}"
}

# jib-task: Claude Code execution
resource "google_service_account" "jib_task" {
  account_id   = "jib-task"
  display_name = "jib Task Executor"
  description  = "Service account for Claude Code task execution"
}

resource "google_project_iam_member" "jib_task_storage" {
  project = local.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.jib_task.email}"
}

resource "google_project_iam_member" "jib_task_pubsub" {
  project = local.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.jib_task.email}"
}

# Secret Manager access (per-secret, not project-wide)
resource "google_secret_manager_secret_iam_member" "jib_task_anthropic" {
  project   = local.secrets_project_id
  secret_id = "jib-anthropic-api-key"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.jib_task.email}"
}
```

### Audit Logging

```hcl
# terraform/infrastructure/monitoring/audit.tf

# Enable Data Access audit logs
resource "google_project_iam_audit_config" "jib" {
  project = local.project_id
  service = "allServices"

  audit_log_config {
    log_type = "ADMIN_READ"
  }

  audit_log_config {
    log_type = "DATA_READ"
  }

  audit_log_config {
    log_type = "DATA_WRITE"
  }
}

# Log sink for long-term retention
resource "google_logging_project_sink" "jib_audit" {
  name        = "jib-audit-sink"
  project     = local.project_id
  destination = "storage.googleapis.com/${google_storage_bucket.audit_logs.name}"

  filter = <<-EOT
    resource.type="cloud_run_revision" OR
    resource.type="cloud_run_job" OR
    resource.type="cloud_tasks_queue" OR
    resource.type="pubsub_topic"
  EOT

  unique_writer_identity = true
}
```

### Secrets Configuration

```hcl
# terraform/infrastructure/storage/secrets.tf

# All secrets stored in khan-academy project (shared secrets)
# jib service accounts get secretAccessor on specific secrets only

locals {
  jib_secrets = {
    "jib-slack-bot-token" = {
      description = "Slack bot OAuth token for jib"
      accessors   = [
        google_service_account.jib_bot.email,
        google_service_account.slack_worker.email,
      ]
    }
    "jib-slack-signing-secret" = {
      description = "Slack request signing secret"
      accessors   = [google_service_account.jib_bot.email]
    }
    "jib-anthropic-api-key" = {
      description = "Anthropic API key for Claude"
      accessors   = [
        google_service_account.jib_task.email,
        google_service_account.jib_analyze.email,
      ]
    }
    "jib-github-token" = {
      description = "GitHub token for PR operations"
      accessors   = [
        google_service_account.jib_task.email,
        google_service_account.jib_sync.email,
      ]
    }
  }
}

resource "google_secret_manager_secret_iam_member" "secret_accessors" {
  for_each = {
    for pair in flatten([
      for secret_id, config in local.jib_secrets : [
        for accessor in config.accessors : {
          key       = "${secret_id}-${accessor}"
          secret_id = secret_id
          accessor  = accessor
        }
      ]
    ]) : pair.key => pair
  }

  project   = local.secrets_project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.accessor}"
}
```

## Cost Analysis

### Monthly Cost Estimate (Typical Usage)

| Component | Usage Estimate | Unit Cost | Monthly Cost |
|-----------|---------------|-----------|---------------|
| **Cloud Run Services** | | | |
| jib-bot | 10K requests, 100 CPU-hours | $0.00002/req + $0.08/CPU-hr | ~$10 |
| slack-worker | 5K requests, 50 CPU-hours | $0.00002/req + $0.08/CPU-hr | ~$5 |
| slack-receiver | Always-on (min 1), 720 CPU-hours | $0.08/CPU-hr | ~$60 |
| **Cloud Run Jobs** | | | |
| jib-task | 100 jobs, 200 CPU-hours | $0.08/CPU-hr | ~$16 |
| jib-sync | 2,200 jobs/mo, 100 CPU-hours | $0.08/CPU-hr | ~$8 |
| jib-analyze | 35 jobs/mo, 50 CPU-hours | $0.08/CPU-hr | ~$4 |
| **Storage** | | | |
| Firestore | 500K reads, 100K writes | $0.06/100K + $0.18/100K | ~$1 |
| Cloud Storage | 10GB, 10K operations | $0.02/GB + $0.004/1K ops | ~$1 |
| **Messaging** | | | |
| Pub/Sub | 100K messages | $0.04/million | ~$0 |
| Cloud Tasks | 10K tasks | Free first 1M | ~$0 |
| **Other** | | | |
| Secret Manager | 10K accesses | $0.03/10K | ~$0 |
| Cloud Scheduler | 35 jobs | $0.10/job/mo | ~$4 |
| Logging/Monitoring | 10GB logs | $0.50/GB | ~$5 |
| **Total** | | | **~$114/month** |

### Cost Optimization Strategies

1. **Scale to Zero:** All services except slack-receiver scale to 0 when idle
2. **Right-size Resources:** Start conservative, monitor and adjust
3. **Job Timeout:** Prevent runaway costs with strict timeouts
4. **Budget Alerts:** Set at $150/month with Slack notifications
5. **Log Retention:** 30 days for operational logs, 90 days for audit

### Budget Alerts

```hcl
# terraform/infrastructure/monitoring/budget.tf

resource "google_billing_budget" "jib" {
  billing_account = var.billing_account
  display_name    = "jib Monthly Budget"

  budget_filter {
    projects = ["projects/${local.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "150"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 0.8
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = [
      google_monitoring_notification_channel.jib_slack.name,
    ]
    disable_default_iam_recipients = false
  }
}
```

## Usage Limits and Quotas

### Application-Level Limits

```yaml
# Enforced by jib-bot

Rate Limits (per user):
  commands_per_minute: 10        # Slash commands
  tasks_per_hour: 5              # /jib task commands
  syncs_per_hour: 2              # /sync commands
  tokens_per_day: 1_000_000      # Anthropic API tokens

Global Limits:
  concurrent_tasks: 3            # Max parallel jib-task jobs
  max_task_duration: 4h          # Task timeout
  max_sync_duration: 30m         # Sync timeout
  max_analyze_duration: 1h       # Analysis timeout

Storage Limits:
  context_size_mb: 100           # Max synced context per source
  job_log_retention_days: 7      # Job logs in Firestore
  artifact_retention_days: 30    # GCS artifacts
```

### GCP Quotas

```hcl
# terraform/infrastructure/quotas.tf

# Request quota increases if needed

resource "google_project_service" "cloudquotas" {
  project = local.project_id
  service = "cloudquotas.googleapis.com"
}

# Monitor quota usage
resource "google_monitoring_alert_policy" "quota_warning" {
  display_name = "jib Quota Warning"
  project      = local.project_id

  conditions {
    display_name = "Quota usage > 80%"

    condition_threshold {
      filter = <<-EOT
        resource.type="consumer_quota" AND
        metric.type="serviceruntime.googleapis.com/quota/allocation/usage"
      EOT

      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      duration        = "0s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.jib_slack.name,
  ]
}
```

## Gaps and Additional Considerations

### Identified Gaps in Previous ADRs

| Gap | Description | Resolution |
|-----|-------------|------------|
| **Container Images** | How are images built and versioned? | Use `cloud-build-docker` module with commit SHA tags |
| **Code Deployment** | How does code get into Cloud Run? | GitHub Actions → Cloud Build → Artifact Registry → Cloud Run |
| **Rollback** | How to rollback bad deployments? | Cloud Run traffic splitting + revision management |
| **VPC Connector** | Needed for internal services? | Yes, for Firestore and internal APIs |
| **Cold Start** | Latency for scale-to-zero services? | Accept for jib-bot (~1s), always-on for slack-receiver |
| **Multi-Region** | DR and latency? | Single region initially; multi-region as Phase 4 |
| **Backup** | Firestore backup? | Daily exports to GCS |

### Container Build Pipeline

```yaml
# .github/workflows/build-images.yml

name: Build Container Images

on:
  push:
    branches: [main]
    paths:
      - 'services/**'
      - 'jobs/**'

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service:
          - jib-bot
          - slack-worker
          - slack-receiver
          - jib-task
          - jib-sync
          - jib-analyze

    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIP_RW }}
          service_account: ${{ secrets.SA_RW }}

      - name: Build and Push
        uses: Khan/actions@cloud-build-docker-v1
        with:
          project_id: khan-jib
          image_name: ${{ matrix.service }}
          context_path: ./${{ contains(matrix.service, 'jib-') && 'jobs' || 'services' }}/${{ matrix.service }}
          image_tag: ${{ github.sha }}
```

### Firestore Backup

```hcl
# terraform/infrastructure/storage/backup.tf

resource "google_firestore_backup_schedule" "daily" {
  project  = local.project_id
  database = google_firestore_database.default.name

  retention = "604800s"  # 7 days

  daily_recurrence {}
}

# Export to GCS for long-term retention
module "firestore_export" {
  source = "git::https://github.com/Khan/terraform-modules.git//terraform/modules/scheduled-job?ref=v1.0.0"

  job_name           = "jib-firestore-export"
  execution_type     = "function"
  project_id         = local.project_id
  secrets_project_id = local.secrets_project_id

  source_dir  = "${path.root}/../../functions/firestore-export"
  main_file   = "main.py"
  schedule    = "0 4 * * *"  # 4 AM daily
  description = "Export Firestore to GCS for backup"

  environment_variables = {
    OUTPUT_BUCKET = google_storage_bucket.backups.name
    DATABASE      = google_firestore_database.default.name
  }
}
```

### VPC Connector

```hcl
# terraform/infrastructure/networking/vpc.tf

resource "google_vpc_access_connector" "jib" {
  name          = "jib-vpc-connector"
  project       = local.project_id
  region        = local.region
  network       = "default"
  ip_cidr_range = "10.8.0.0/28"

  min_instances = 2
  max_instances = 3
}

# Apply to Cloud Run services that need internal access
resource "google_cloud_run_v2_service" "jib_task" {
  # ...

  template {
    vpc_access {
      connector = google_vpc_access_connector.jib.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
  }
}
```

## Migration Strategy

### Phase 1: Infrastructure Setup (Week 1-2)

1. Create `khan-jib` GCP project
2. Run Terraform bootstrap locally
3. Deploy initial infrastructure (Pub/Sub, Firestore, GCS)
4. Set up secrets in Secret Manager
5. Configure budget alerts

**Validation:** Infrastructure created, no services yet

### Phase 2: Deploy Services (Week 3-4)

1. Build and push container images
2. Deploy Cloud Run services (jib-bot, slack-worker)
3. Configure Slack app to point to Cloud Run
4. Test slash commands end-to-end

**Validation:** `/jib help` works from Slack

### Phase 3: Deploy Jobs (Week 5-6)

1. Deploy jib-task Cloud Run Job
2. Test `/jib task` execution
3. Deploy sync jobs
4. Configure Cloud Scheduler

**Validation:** Full task execution, sync running on schedule

### Phase 4: Migration Complete (Week 7-8)

1. Migrate all users to cloud-based jib
2. Update documentation
3. Deprecate laptop-based deployment
4. Monitor and tune

**Validation:** No laptop-based jib instances running

## Consequences

### Benefits

1. **Scalable:** Handles multiple users, concurrent tasks
2. **Cost-Efficient:** Scales to zero when idle
3. **Reliable:** Managed services, automatic restarts
4. **Auditable:** Full audit trail in Cloud Logging
5. **Secure:** Workload Identity, least privilege, encrypted secrets
6. **Observable:** Dashboards, alerts, budget tracking
7. **Maintainable:** Terraform-managed, CI/CD automated

### Drawbacks

1. **Complexity:** More components than laptop deployment
2. **Cold Start:** ~1 second latency for idle services
3. **Cost:** ~$114/month vs $0 for laptop
4. **External Dependencies:** Requires GCP availability

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Cost overrun | Budget alerts, usage limits, monitoring |
| Security breach | Least privilege, audit logs, secrets rotation |
| Service outage | Health checks, alerts, runbooks |
| Data loss | Backups, multi-region (future) |
| Unauthorized access | User allowlist, rate limiting, audit |

## Decision Permanence

**High permanence.**

This establishes the foundational infrastructure for jib in GCP. Changes would require:
- Terraform state migration
- Service redeployment
- User migration
- Documentation updates

The specific configurations can evolve, but the core architecture (Cloud Run + Terraform + GCP services) is a long-term commitment.

## Alternatives Considered

### Alternative 1: GKE Instead of Cloud Run

**Pros:** More control, persistent workloads, familiar k8s patterns
**Cons:** Always-on cost (~$300+/month minimum), operational overhead, overkill for jib's scale
**Rejected:** Cloud Run's serverless model better fits jib's bursty workload

### Alternative 2: Single VM with Docker Compose

**Pros:** Simpler, closer to current laptop setup, predictable cost
**Cons:** Always-on, single point of failure, manual scaling, no Terraform patterns
**Rejected:** Doesn't leverage GCP services, harder to maintain

### Alternative 3: AWS/Azure Instead of GCP

**Pros:** Alternative cloud options
**Cons:** Khan Academy is GCP-native, no established Terraform patterns
**Rejected:** Inconsistent with Khan Academy infrastructure

### Alternative 4: Separate Project per Component

**Pros:** Maximum isolation
**Cons:** Complex IAM, harder cost tracking, more Terraform
**Rejected:** Overkill for single-team project

## Related ADRs

This ADR is the culmination of a series defining the jib GCP deployment architecture:

| ADR | Relationship to This ADR |
|-----|-------------------------|
| [ADR-Message-Queue-Slack-Integration](./ADR-Message-Queue-Slack-Integration.md) | Defines Pub/Sub topics, slack-worker service, and Firestore collections deployed here |
| [ADR-Context-Sync-Strategy-Custom-vs-MCP](./ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | Defines what jib-sync jobs execute and MCP configuration for Jira/GitHub |
| [ADR-Slack-Integration-Strategy-MCP-vs-Custom](./ADR-Slack-Integration-Strategy-MCP-vs-Custom.md) | Defines slack-worker and slack-receiver service requirements |
| [ADR-Slack-Bot-GCP-Integration](./ADR-Slack-Bot-GCP-Integration.md) | Defines jib-bot service, Cloud Tasks queues, and slash command interface |

## References

- [ADR #889: Terraform CI/CD Standards](https://khanacademy.atlassian.net/wiki/pages/viewpage.action?pageId=4385800306)
- [terraform-modules/scheduled-job](https://github.com/Khan/terraform-modules/tree/main/terraform/modules/scheduled-job)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Run Jobs Documentation](https://cloud.google.com/run/docs/create-jobs)

---

**Last Updated:** 2025-11-28
