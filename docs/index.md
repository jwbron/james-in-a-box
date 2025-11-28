# Documentation Index

> james-in-a-box: LLM-powered autonomous software engineering agent in a Docker sandbox

This index helps both humans and LLMs navigate the documentation efficiently.
For task-specific guidance, see [Task-Specific Guides](#task-specific-guides) below.

## Core Documentation

### Architecture Decision Records (ADRs)

| Document | Description |
|----------|-------------|
| [ADR Overview](adr/README.md) | Index of all ADRs and their status |
| [Autonomous Software Engineer](adr/in-progress/ADR-Autonomous-Software-Engineer.md) | Core system architecture, security model, and design decisions |
| [LLM Documentation Index Strategy](adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) | Strategy for LLM-navigable documentation (this index) |
| [Context Sync Strategy](adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | How external data (Confluence, JIRA, GitHub) is synced |
| [Slack Integration Strategy](adr/not-implemented/ADR-Slack-Integration-Strategy-MCP-vs-Custom.md) | Bidirectional Slack communication approach |
| [Message Queue Integration](adr/not-implemented/ADR-Message-Queue-Slack-Integration.md) | GCP Pub/Sub migration plan for Slack |
| [Slack Bot GCP Integration](adr/not-implemented/ADR-Slack-Bot-GCP-Integration.md) | GCP-hosted Slack bot architecture |
| [GCP Deployment](adr/not-implemented/ADR-GCP-Deployment-Terraform.md) | Terraform-based GCP deployment strategy |
| [Internet Tool Access Lockdown](adr/not-implemented/ADR-Internet-Tool-Access-Lockdown.md) | Security restrictions on network access |
| [Automated PR Review Agent](adr/not-implemented/ADR-Automated-PR-Review-Agent.md) | Bounded-context automated PR review agent |

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
| [Slack Quick Reference](reference/slack-quick-reference.md) | Common Slack operations and commands |
| [Claude Authentication](reference/claude-authentication.md) | Claude CLI authentication guide |
| [Khan Academy Culture](reference/khan-academy-culture.md) | L3-L4 engineering behavioral standards |
| [Conversation Analysis Criteria](reference/conversation-analysis-criteria.md) | Assessment criteria for agent performance |

### Development

| Document | Description |
|----------|-------------|
| [Development Overview](development/README.md) | Contributing and development guidelines |
| [Project Structure](development/STRUCTURE.md) | Directory conventions and organization |

### User Guide

| Document | Description |
|----------|-------------|
| [User Guide](user-guide/README.md) | Day-to-day usage and common tasks |

## Task-Specific Guides

When working on specific tasks, consult these documents first:

| Task Type | Read First | Also Helpful |
|-----------|------------|--------------|
| **ANY new task** | [Beads Task Tracking](reference/beads.md) | Check for existing work before starting |
| **Slack integration changes** | [Slack Integration](architecture/slack-integration.md) | [ADR: Slack Strategy](adr/not-implemented/ADR-Slack-Integration-Strategy-MCP-vs-Custom.md) |
| **Adding new host services** | [Architecture Overview](architecture/README.md) | [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) |
| **Security-related changes** | [ADR: Internet Lockdown](adr/not-implemented/ADR-Internet-Tool-Access-Lockdown.md) | [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) |
| **Context sync modifications** | [ADR: Context Sync](adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | [Setup Overview](setup/README.md) |
| **GCP deployment changes** | [ADR: GCP Deployment](adr/not-implemented/ADR-GCP-Deployment-Terraform.md) | [ADR: Slack GCP](adr/not-implemented/ADR-Slack-Bot-GCP-Integration.md) |
| **PR review automation** | [ADR: PR Review Agent](adr/not-implemented/ADR-Automated-PR-Review-Agent.md) | [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) |
| **Documentation updates** | [ADR: Doc Index Strategy](adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) | This file |

## Machine-Readable Indexes

These files are auto-generated and provide structured data for programmatic access:

| File | Description | Update Frequency |
|------|-------------|------------------|
| [codebase.json](generated/codebase.json) | Structured codebase analysis | Weekly + significant changes |
| [patterns.json](generated/patterns.json) | Extracted code patterns | On pattern detection |
| [dependencies.json](generated/dependencies.json) | Dependency graph | Weekly |

> **Note:** Machine-readable indexes are generated by automated analysis. See [ADR: Doc Index Strategy](adr/in-progress/ADR-LLM-Documentation-Index-Strategy.md) for details.

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
*Last updated: 2024-11-28*
