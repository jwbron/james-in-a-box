# MCP Servers

This directory contains Model Context Protocol (MCP) servers for use with AI agents.

## Background

MCP servers provide tools for AI agents (like Claude Code, Cursor, etc.) to interact with external services. These servers implement the [Model Context Protocol](https://modelcontextprotocol.io/) specification.

### Relevant ADRs

- [ADR #867: Model Context Protocol services for internal AI agents](https://khanacademy.atlassian.net/wiki/spaces/ENG/pages/4216619431) - Policy for MCP server usage
- [ADR #873: MCP Gateway Service](https://khanacademy.atlassian.net/wiki/spaces/ENG/pages/4342415506) - Future centralized gateway
- [ADR #874: mcp-go for writing MCP servers](https://khanacademy.atlassian.net/wiki/spaces/ENG/pages/4343398422) - Standard Go library

## Available Servers

| Server | Description | Status |
|--------|-------------|--------|
| [github-mcp](./github-mcp/) | GitHub API integration | Active |

## Security Guidelines

Per ADR #867, MCP servers should follow these security practices:

### Acceptable Patterns

- **Stdio transport** with credentials from environment variables or disk (e.g., `~/.config/gcloud`)
- **HTTP transport with authentication** using OAuth tokens
- **Credentials loaded at runtime** from environment or secret managers

### Patterns to Avoid

- Credentials stored in repository config files
- HTTP servers without authentication
- Overly permissive tool access

## Adding a New MCP Server

1. Create a new directory under `mcp-servers/`
2. Use `mcp-go` library per ADR #874
3. Support both stdio (local) and HTTP (GCP) transports
4. Document the tools and configuration
5. Add to this README

## Deployment

### Local Development

Each server can run locally using stdio transport:

```bash
cd mcp-servers/<server-name>
go build
./<server-name>
```

### GCP Cloud Run

Servers are designed for deployment to Cloud Run:

```bash
cd mcp-servers/<server-name>
docker build -t <server-name> .
gcloud run deploy <server-name> --image gcr.io/PROJECT/<server-name>
```

## Future: MCP Gateway

Per ADR #873, a centralized `mcp-gateway` service will be deployed to Cloud Run. Individual MCP servers will be registered as upstream services, providing:

- Single authentication point
- Centralized logging and monitoring
- Tool subset configurations per agent
