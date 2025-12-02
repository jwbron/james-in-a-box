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
| [Context Sync Strategy](adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | How external data (Confluence, JIRA, GitHub) is synced |
| [Feature Analyzer - Doc Sync](adr/implemented/ADR-Feature-Analyzer-Documentation-Sync.md) | Automated documentation updates after ADR implementation |
| [LLM Inefficiency Reporting](adr/implemented/ADR-LLM-Inefficiency-Reporting.md) | Self-improvement through inefficiency detection and reporting |
| [Standardized Logging](adr/in-progress/ADR-Standardized-Logging-Interface.md) | Structured JSON logging with GCP compatibility |
| [Multi-Agent Pipeline](adr/not-implemented/ADR-Multi-Agent-Pipeline-Architecture.md) | Multi-agent pipeline design for complex tasks |
| [Review Artifacts](adr/not-implemented/ADR-Review-Artifacts-Async-Human-Review.md) | Standardized artifacts for async human review |

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
| [Features - Source Mapping](FEATURES.md) | Map of all features to their implementation locations |
| [Slack Quick Reference](reference/slack-quick-reference.md) | Common Slack operations and commands |
| [Khan Academy Culture](reference/khan-academy-culture.md) | L3-L4 engineering behavioral standards |
| [Conversation Analysis Criteria](reference/conversation-analysis-criteria.md) | Assessment criteria for agent performance |
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
| [GitHub Integration](features/github-integration.md) | PR monitoring, reviews, CI/CD automation |
| [Self-Improvement](features/self-improvement.md) | Trace collection, inefficiency detection |
| [Documentation System](features/documentation-system.md) | Feature analyzer, doc generator, drift detection |
| [Container Infrastructure](features/container-infrastructure.md) | jib container, custom commands, rules |
| [Utilities](features/utilities.md) | Helper tools, maintenance scripts, tokens |
| [Workflow Context](features/workflow-context.md) | Workflow traceability - tracking which job generated each output |

### Analysis Reports

| Document | Description |
|----------|-------------|
| [Beads Health Reports](analysis/beads/README.md) | Automated health analysis for Beads task tracking |

### System Improvement

| Document | Description |
|----------|-------------|
| [Reinforcements](reinforcements/README.md) | Records of system reinforcements from breakages |

## Task-Specific Guides

When working on specific tasks, consult these documents first:

| Task Type | Read First | Also Helpful |
|-----------|------------|--------------|
| **ANY new task** | [Beads Task Tracking](reference/beads.md) | Check for existing work before starting |
| **Slack integration changes** | [Slack Integration](architecture/slack-integration.md) | See open PR #246 for ADR |
| **Adding new host services** | [Architecture Overview](architecture/README.md) | [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) |
| **Security-related changes** | [ADR: Autonomous SE](adr/in-progress/ADR-Autonomous-Software-Engineer.md) | See open PR #243 for Internet Lockdown ADR |
| **Context sync modifications** | [ADR: Context Sync](adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | [Setup Overview](setup/README.md) |
| **GCP deployment changes** | See open PR #240 for ADR | See open PR #245 for Slack GCP ADR |
| **Documentation updates** | [ADR: Doc Index Strategy](adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) | This file |
| **ADR research/generation** | [ADR Researcher](../host-services/analysis/adr-researcher/README.md) | [ADR: Doc Index Strategy](adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) |
| **Feature discovery** | [Features Index](features/README.md) | [FEATURES.md](FEATURES.md), [Feature Analyzer](../host-services/analysis/feature-analyzer/README.md) |
| **Documentation sync** | [Feature Analyzer](../host-services/analysis/feature-analyzer/README.md) | [ADR: Feature Analyzer](adr/implemented/ADR-Feature-Analyzer-Documentation-Sync.md) |
| **Finding helper scripts** | [Features Index](features/README.md) | Category-specific docs in `docs/features/` |
| **Logging changes** | [ADR: Standardized Logging](adr/in-progress/ADR-Standardized-Logging-Interface.md) | [Log Persistence](reference/log-persistence.md) |
| **LLM efficiency analysis** | [ADR: Inefficiency Reporting](adr/implemented/ADR-LLM-Inefficiency-Reporting.md) | [Prompt Caching](reference/prompt-caching.md) |
| **Beads integration** | [Beads Integration](development/beads-integration.md) | [Beads Task Tracking](reference/beads.md) |

## Machine-Readable Indexes

These files are auto-generated and provide structured data for programmatic access.
See [Generated Indexes README](generated/README.md) for details on structure and access.

| File | Description | Update Frequency |
|------|-------------|------------------|
| [codebase.json](generated/codebase.json) | Structured codebase analysis | Weekly + significant changes |
| [patterns.json](generated/patterns.json) | Extracted code patterns | On pattern detection |
| [dependencies.json](generated/dependencies.json) | Dependency graph | Weekly |

> **Note:** Machine-readable indexes are generated by automated analysis. See [ADR: Doc Index Strategy](adr/implemented/ADR-LLM-Documentation-Index-Strategy.md) for details.
>
> **LLM Access:** These files are gitignored and regenerated on container startup. Use `Read` or `ls` to access them directly—`Glob` won't find gitignored files. Path: `~/khan/james-in-a-box/docs/generated/`

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
*Last updated: 2025-12-02*
