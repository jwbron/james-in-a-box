# GitHub MCP Server

A Model Context Protocol (MCP) server that provides GitHub tools for AI agents.

Built per [ADR #867](https://khanacademy.atlassian.net/wiki/spaces/ENG/pages/4216619431) (MCP servers for internal AI agents), [ADR #873](https://khanacademy.atlassian.net/wiki/spaces/ENG/pages/4342415506) (MCP Gateway Service), and [ADR #874](https://khanacademy.atlassian.net/wiki/spaces/ENG/pages/4343398422) (mcp-go for writing MCP servers).

## Features

### Tools Available

| Tool | Description |
|------|-------------|
| `github_list_repos` | List repositories for a user or organization |
| `github_get_repo` | Get detailed information about a repository |
| `github_list_issues` | List issues in a repository |
| `github_get_issue` | Get detailed information about an issue |
| `github_create_issue` | Create a new issue in a repository |
| `github_list_prs` | List pull requests in a repository |
| `github_get_pr` | Get detailed information about a pull request |
| `github_get_file` | Get the contents of a file from a repository |
| `github_search_code` | Search for code across GitHub repositories |
| `github_list_commits` | List commits in a repository |
| `github_create_pr_comment` | Create a comment on a pull request |

## Installation

### Prerequisites

- Go 1.22 or later
- A GitHub Personal Access Token (PAT) with appropriate permissions

### Build

```bash
cd mcp-servers/github-mcp
go mod tidy
go build -o github-mcp .
```

## Usage

### Local Mode (stdio)

For local use with agents like Claude Code or Cursor:

```bash
GITHUB_TOKEN=<your-token> ./github-mcp
```

### HTTP Server Mode

For deployment to GCP Cloud Run or other hosting:

```bash
GITHUB_TOKEN=<your-token> ./github-mcp --http :8080
```

## Configuration

### Claude Code / Claude Desktop

Add to your `claude_desktop_config.json` or use the MCP configuration:

```json
{
  "mcpServers": {
    "github": {
      "command": "/path/to/github-mcp",
      "env": {
        "GITHUB_TOKEN": "<your-token>"
      }
    }
  }
}
```

### Cursor

Add to your Cursor MCP settings:

```json
{
  "mcpServers": {
    "github": {
      "command": "/path/to/github-mcp",
      "env": {
        "GITHUB_TOKEN": "<your-token>"
      }
    }
  }
}
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub Personal Access Token |

### Creating a GitHub Token

1. Go to [GitHub Settings > Developer Settings > Personal Access Tokens](https://github.com/settings/tokens)
2. Generate a new token (classic) with these scopes:
   - `repo` - Full control of private repositories (or `public_repo` for public only)
   - `read:org` - Read organization data
   - `read:user` - Read user profile data

## Security Considerations

Per [ADR #867](https://khanacademy.atlassian.net/wiki/spaces/ENG/pages/4216619431), this MCP server follows the "Option A: Local MCP server" pattern:

- Uses stdio transport (or authenticated HTTP)
- Credentials are loaded from environment variables (not stored in config files)
- Follows the "Good" security practices outlined in the ADR

**Important:** Never commit your GitHub token to version control. Use environment variables or secret management.

## GCP Deployment

This server is designed with GCP Cloud Run deployment in mind:

1. Build the container:
   ```bash
   docker build -t github-mcp .
   ```

2. Deploy to Cloud Run:
   ```bash
   gcloud run deploy github-mcp \
     --image gcr.io/PROJECT/github-mcp \
     --set-secrets GITHUB_TOKEN=github-token:latest \
     --allow-unauthenticated  # Or use IAP for authentication
   ```

3. For integration with the planned `mcp-gateway` service (per ADR #873), this server can be registered as an upstream MCP server.

## Development

### Running Tests

```bash
go test ./...
```

### Adding New Tools

1. Define the tool schema using `mcp.NewTool()`
2. Implement the handler function returning `server.ToolHandlerFunc`
3. Register with `s.AddTool()`

Example:
```go
myTool := mcp.NewTool("github_my_tool",
    mcp.WithDescription("Description of what the tool does"),
    mcp.WithString("param1",
        mcp.Required(),
        mcp.Description("Parameter description"),
    ),
)
s.AddTool(myTool, myToolHandler(gh))
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   AI Agent      │────▶│  GitHub MCP      │────▶│   GitHub API    │
│ (Claude/Cursor) │     │  Server          │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                       │
        │                       │
        ▼                       ▼
   MCP Protocol            go-github
   (stdio/SSE)              client
```

## License

Internal Khan Academy use.
