# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) documenting significant technical decisions for james-in-a-box.

## What is an ADR?

An ADR captures the context, decision, and consequences of an architectural choice. They help future contributors understand why the system is designed the way it is.

## ADR Index

| ADR | Status | Summary |
|-----|--------|--------|
| [Autonomous Software Engineer](ADR-Autonomous-Software-Engineer.md) | Accepted | Core system architecture, security model, operating principles |
| [LLM Documentation Index Strategy](ADR-LLM-Documentation-Index-Strategy.md) | Proposed | Strategy for LLM-navigable documentation |
| [Context Sync Strategy](ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | Accepted | Custom sync vs MCP for Confluence/JIRA/GitHub |
| [Slack Integration Strategy](ADR-Slack-Integration-Strategy-MCP-vs-Custom.md) | Accepted | Custom Slack integration vs MCP server |
| [Message Queue Integration](ADR-Message-Queue-Slack-Integration.md) | Proposed | GCP Pub/Sub for Slack message queuing |
| [Slack Bot GCP Integration](ADR-Slack-Bot-GCP-Integration.md) | Proposed | GCP-hosted Slack bot architecture |
| [GCP Deployment](ADR-GCP-Deployment-Terraform.md) | Proposed | Terraform-based GCP deployment |
| [Internet Tool Access Lockdown](ADR-Internet-Tool-Access-Lockdown.md) | Accepted | Security restrictions on agent network access |

## ADR Template

When creating a new ADR, include:

1. **Title** - Clear, descriptive name
2. **Status** - Proposed, Accepted, Deprecated, Superseded
3. **Context** - What problem are we solving?
4. **Decision** - What did we decide?
5. **Consequences** - What are the trade-offs?

## See Also

- [Architecture Overview](../architecture/README.md)
- [Documentation Index](../index.md)
