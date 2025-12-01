# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) documenting significant technical decisions for james-in-a-box.

## What is an ADR?

An ADR captures the context, decision, and consequences of an architectural choice. They help future contributors understand why the system is designed the way it is.

## Directory Structure

ADRs are organized by implementation status:

- **`in-progress/`** - ADRs actively being implemented
- **`implemented/`** - ADRs fully implemented and in production
- **`not-implemented/`** - ADRs proposed but not yet started

## ADR Index

### Implemented

| ADR | Summary |
|-----|---------|
| [Context Sync Strategy](implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | Hybrid approach: GitHub MCP implemented ✅, JIRA MCP pending ❌, Confluence sync retained |
| [LLM Documentation Index Strategy](implemented/ADR-LLM-Documentation-Index-Strategy.md) | LLM-navigable documentation with 6-agent pipeline |

### In Progress

| ADR | Summary |
|-----|---------|
| [Autonomous Software Engineer](in-progress/ADR-Autonomous-Software-Engineer.md) | Core system architecture, security model, operating principles |
| [LLM Inefficiency Reporting](in-progress/ADR-LLM-Inefficiency-Reporting.md) | Self-improvement through inefficiency detection and reporting (Phase 1a: Beads Analyzer implemented) |

### Not Implemented

| ADR | Summary |
|-----|---------|
| [Codebase Analyzer Strategy](not-implemented/ADR-Codebase-Analyzer-Strategy.md) | Multi-layered codebase analysis with external best practices integration |
| [Continuous System Reinforcement](not-implemented/ADR-Continuous-System-Reinforcement.md) | Systematic learning from breakages to strengthen the system |
| [Feature Analyzer - Documentation Sync](in-progress/ADR-Feature-Analyzer-Documentation-Sync.md) | Automated documentation updates after ADR implementation and merge |
| [GCP Deployment](not-implemented/ADR-GCP-Deployment-Terraform.md) | Terraform-based GCP deployment |
| [Internet Tool Access Lockdown](not-implemented/ADR-Internet-Tool-Access-Lockdown.md) | Security restrictions on agent network access |
| [Message Queue Integration](not-implemented/ADR-Message-Queue-Slack-Integration.md) | GCP Pub/Sub for Slack message queuing |
| [Slack Bot GCP Integration](not-implemented/ADR-Slack-Bot-GCP-Integration.md) | GCP-hosted Slack bot architecture |
| [Slack Integration Strategy](not-implemented/ADR-Slack-Integration-Strategy-MCP-vs-Custom.md) | Custom Slack integration vs MCP server |
| [Standardized Logging Interface](in-progress/ADR-Standardized-Logging-Interface.md) | Structured JSON logging with GCP compatibility |

## ADR Template

When creating a new ADR, include:

1. **Title** - Clear, descriptive name
2. **Status** - Proposed, Accepted, Deprecated, Superseded
3. **Context** - What problem are we solving?
4. **Decision** - What did we decide?
5. **Consequences** - What are the trade-offs?

### Important Guidelines

**DO NOT include time-based estimates** in ADRs (e.g., "Week 1-2", "Phase 1 takes 3 weeks"). Time estimates are not reliable or relevant for LLM-assisted development where task completion depends on many unpredictable factors. Instead:

- Use **phase numbering** without time estimates (Phase 1, Phase 2, etc.)
- Define **success criteria** for each phase
- List **dependencies** between phases
- Focus on **what** needs to be done, not **when**

Place new ADRs in `not-implemented/` until work begins.

## See Also

- [Architecture Overview](../architecture/README.md)
- [Documentation Index](../index.md)
