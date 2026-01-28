# Documentation Index

> james-in-a-box: LLM-powered guided autonomous software engineering agent in a Docker sandbox

This index helps both humans and LLMs navigate the documentation efficiently.
For task-specific guidance, see [Task-Specific Guides](#task-specific-guides) below.

## Core Documentation

### Architecture Decision Records (ADRs)

| Document | Description |
|----------|-------------|
| [ADR Overview](adr/README.md) | Index of all ADRs and their status |
| [Autonomous Software Engineer](adr/in-progress/ADR-Autonomous-Software-Engineer.md) | Core system architecture, security model, and design decisions |
| [Context Sync Strategy](adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | How external data (Confluence, JIRA, GitHub) is synced |
| [Git Isolation Architecture](adr/implemented/ADR-Git-Isolation-Architecture.md) | Gateway sidecar design for credential isolation |
| [Standardized Logging](adr/in-progress/ADR-Standardized-Logging-Interface.md) | Structured JSON logging with GCP compatibility |

### Architecture

| Document | Description |
|----------|-------------|
| [Architecture Overview](architecture/README.md) | High-level system design, components, data flows |
| [Slack Integration](architecture/slack-integration.md) | Bidirectional Slack messaging design |
| [Host Slack Notifier](architecture/host-slack-notifier.md) | Notification system implementation details |

### Setup Guides

| Document | Description |
|----------|-------------|
| [Setup Overview](setup/README.md) | Installation and configuration summary |
| [Slack Quickstart](setup/slack-quickstart.md) | Get Slack notifications working in 10 minutes |
| [Slack App Setup](setup/slack-app-setup.md) | Detailed Slack app configuration |
| [Slack Bidirectional](setup/slack-bidirectional.md) | Two-way Slack communication setup |
| [GitHub App Setup](setup/github-app-setup.md) | GitHub App permissions and installation |

### Reference

| Document | Description |
|----------|-------------|
| [Reference Overview](reference/README.md) | Quick reference guides and troubleshooting |
| [Beads Task Tracking](reference/beads.md) | Persistent task memory system - commands, workflows, best practices |
| [jib_config Framework](../shared/jib_config/README.md) | Unified configuration loading, validation, and health checks |
| [Features - Source Mapping](FEATURES.md) | Map of all features to their implementation locations |
| [Slack Quick Reference](reference/slack-quick-reference.md) | Common Slack operations and commands |
| [Engineering Culture](reference/engineering-culture.md) | L3-L4 engineering behavioral standards |
| [Log Persistence](reference/log-persistence.md) | Container log persistence and correlation |
| [Prompt Caching](reference/prompt-caching.md) | Claude prompt caching optimization and monitoring |

### Development

| Document | Description |
|----------|-------------|
| [Development Overview](development/README.md) | Contributing and development guidelines |
| [Project Structure](development/STRUCTURE.md) | Directory conventions and organization |
| [Beads Integration](development/beads-integration.md) | How to integrate Beads into container tools |

### User Guide

| Document | Description |
|----------|-------------|
| [User Guide](user-guide/README.md) | Day-to-day usage and common tasks |

### Features

| Document | Description |
|----------|-------------|
| [Features Index](features/README.md) | Overview of all feature categories |
| [Communication](features/communication.md) | Slack integration - notifier, receiver, notifications |
| [Context Management](features/context-management.md) | Confluence, JIRA sync, Beads task tracking |
| [GitHub Integration](features/github-integration.md) | GitHub command handling, PR workflows |
| [Container Infrastructure](features/container-infrastructure.md) | jib container, custom commands, rules |
| [Utilities](features/utilities.md) | Helper tools, maintenance scripts, tokens |
| [Workflow Context](features/workflow-context.md) | Workflow traceability - tracking which job generated each output |

### System Improvement

| Document | Description |
|----------|-------------|
| [Reinforcements](reinforcements/README.md) | Records of system reinforcements from breakages |

## Task-Specific Guides

When working on specific tasks, consult these documents first:

| Task Type | Read First | Also Helpful |
|-----------|------------|--------------|
| **ANY new task** | [Beads Task Tracking](reference/beads.md) | Check for existing work before starting |
| **Slack integration changes** | [Slack Integration](architecture/slack-integration.md) | [Slack Quick Reference](reference/slack-quick-reference.md) |
| **Adding new host services** | [Architecture Overview](architecture/README.md) | [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) |
| **Security-related changes** | [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) | [Git Isolation](adr/implemented/ADR-Git-Isolation-Architecture.md) |
| **Context sync modifications** | [ADR: Context Sync](adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | [Setup Overview](setup/README.md) |
| **Logging changes** | [ADR: Standardized Logging](adr/in-progress/ADR-Standardized-Logging-Interface.md) | [Log Persistence](reference/log-persistence.md) |
| **Beads integration** | [Beads Integration](development/beads-integration.md) | [Beads Task Tracking](reference/beads.md) |

## Quick Navigation

**Getting Started:**
1. [Main README](../README.md) - Project overview
2. [Setup Overview](setup/README.md) - Installation guide
3. [User Guide](user-guide/README.md) - Daily usage

**Understanding the System:**
1. [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) - Full architecture
2. [Architecture Overview](architecture/README.md) - Component design
3. [Project Structure](development/STRUCTURE.md) - Code organization

**Troubleshooting:**
1. [Reference Overview](reference/README.md) - Common issues
2. [Slack Quick Reference](reference/slack-quick-reference.md) - Slack problems

---

*This index follows the [llms.txt](https://llmstxt.org/) convention for LLM-friendly documentation.*
*Last updated: 2026-01-28*
