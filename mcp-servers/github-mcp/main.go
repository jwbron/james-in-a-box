// Package main implements a GitHub MCP (Model Context Protocol) server.
//
// This MCP server provides tools for AI agents to interact with GitHub,
// including listing repositories, issues, pull requests, and more.
//
// Usage:
//
//	Local (stdio):
//	  GITHUB_TOKEN=<token> github-mcp
//
//	HTTP Server (for GCP deployment):
//	  GITHUB_TOKEN=<token> github-mcp --http :8080
//
// Per ADR #867, this server uses credentials from environment variables
// (GITHUB_TOKEN) which is acceptable for local MCP servers.
// Per ADR #874, this uses the mcp-go library.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"

	"github.com/google/go-github/v66/github"
	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"
	"golang.org/x/oauth2"
)

var (
	httpAddr = flag.String("http", "", "HTTP address to listen on (e.g., :8080). If empty, uses stdio transport.")
	version  = "0.1.0"
)

func main() {
	flag.Parse()

	token := os.Getenv("GITHUB_TOKEN")
	if token == "" {
		log.Fatal("GITHUB_TOKEN environment variable is required")
	}

	// Create GitHub client
	ctx := context.Background()
	ts := oauth2.StaticTokenSource(&oauth2.Token{AccessToken: token})
	tc := oauth2.NewClient(ctx, ts)
	ghClient := github.NewClient(tc)

	// Create MCP server
	s := server.NewMCPServer(
		"github-mcp",
		version,
		server.WithToolCapabilities(true),
		server.WithResourceCapabilities(true, false),
	)

	// Register tools
	registerTools(s, ghClient)

	// Start server
	if *httpAddr != "" {
		// HTTP transport for GCP Cloud Run deployment
		log.Printf("Starting GitHub MCP server on %s", *httpAddr)
		if err := server.NewSSEServer(s).Start(*httpAddr); err != nil {
			log.Fatalf("Failed to start HTTP server: %v", err)
		}
	} else {
		// Stdio transport for local use
		log.Println("Starting GitHub MCP server (stdio)")
		if err := server.NewStdioServer(s).Listen(ctx, os.Stdin, os.Stdout); err != nil {
			log.Fatalf("Server error: %v", err)
		}
	}
}

func registerTools(s *server.MCPServer, gh *github.Client) {
	// List repositories tool
	listReposTool := mcp.NewTool("github_list_repos",
		mcp.WithDescription("List repositories for a user or organization"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("GitHub username or organization name"),
		),
		mcp.WithString("type",
			mcp.Description("Type of repositories: all, owner, member (default: all)"),
		),
		mcp.WithNumber("per_page",
			mcp.Description("Number of results per page (max 100, default 30)"),
		),
	)
	s.AddTool(listReposTool, listReposHandler(gh))

	// Get repository tool
	getRepoTool := mcp.NewTool("github_get_repo",
		mcp.WithDescription("Get detailed information about a repository"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner (username or organization)"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
	)
	s.AddTool(getRepoTool, getRepoHandler(gh))

	// List issues tool
	listIssuesTool := mcp.NewTool("github_list_issues",
		mcp.WithDescription("List issues in a repository"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithString("state",
			mcp.Description("Issue state: open, closed, all (default: open)"),
		),
		mcp.WithString("labels",
			mcp.Description("Comma-separated list of label names"),
		),
		mcp.WithNumber("per_page",
			mcp.Description("Number of results per page (max 100, default 30)"),
		),
	)
	s.AddTool(listIssuesTool, listIssuesHandler(gh))

	// Get issue tool
	getIssueTool := mcp.NewTool("github_get_issue",
		mcp.WithDescription("Get detailed information about an issue"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithNumber("issue_number",
			mcp.Required(),
			mcp.Description("Issue number"),
		),
	)
	s.AddTool(getIssueTool, getIssueHandler(gh))

	// Create issue tool
	createIssueTool := mcp.NewTool("github_create_issue",
		mcp.WithDescription("Create a new issue in a repository"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithString("title",
			mcp.Required(),
			mcp.Description("Issue title"),
		),
		mcp.WithString("body",
			mcp.Description("Issue body/description"),
		),
		mcp.WithString("labels",
			mcp.Description("Comma-separated list of label names"),
		),
	)
	s.AddTool(createIssueTool, createIssueHandler(gh))

	// List pull requests tool
	listPRsTool := mcp.NewTool("github_list_prs",
		mcp.WithDescription("List pull requests in a repository"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithString("state",
			mcp.Description("PR state: open, closed, all (default: open)"),
		),
		mcp.WithString("base",
			mcp.Description("Filter by base branch name"),
		),
		mcp.WithNumber("per_page",
			mcp.Description("Number of results per page (max 100, default 30)"),
		),
	)
	s.AddTool(listPRsTool, listPRsHandler(gh))

	// Get pull request tool
	getPRTool := mcp.NewTool("github_get_pr",
		mcp.WithDescription("Get detailed information about a pull request"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithNumber("pr_number",
			mcp.Required(),
			mcp.Description("Pull request number"),
		),
	)
	s.AddTool(getPRTool, getPRHandler(gh))

	// Get file contents tool
	getFileTool := mcp.NewTool("github_get_file",
		mcp.WithDescription("Get the contents of a file from a repository"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithString("path",
			mcp.Required(),
			mcp.Description("Path to the file in the repository"),
		),
		mcp.WithString("ref",
			mcp.Description("Git reference (branch, tag, or commit SHA). Defaults to default branch."),
		),
	)
	s.AddTool(getFileTool, getFileHandler(gh))

	// Search code tool
	searchCodeTool := mcp.NewTool("github_search_code",
		mcp.WithDescription("Search for code across GitHub repositories"),
		mcp.WithString("query",
			mcp.Required(),
			mcp.Description("Search query (can include qualifiers like repo:, language:, path:)"),
		),
		mcp.WithNumber("per_page",
			mcp.Description("Number of results per page (max 100, default 30)"),
		),
	)
	s.AddTool(searchCodeTool, searchCodeHandler(gh))

	// List commits tool
	listCommitsTool := mcp.NewTool("github_list_commits",
		mcp.WithDescription("List commits in a repository"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithString("sha",
			mcp.Description("SHA or branch to list commits from. Defaults to default branch."),
		),
		mcp.WithString("path",
			mcp.Description("Only commits containing this file path"),
		),
		mcp.WithNumber("per_page",
			mcp.Description("Number of results per page (max 100, default 30)"),
		),
	)
	s.AddTool(listCommitsTool, listCommitsHandler(gh))

	// Create PR comment tool
	createPRCommentTool := mcp.NewTool("github_create_pr_comment",
		mcp.WithDescription("Create a comment on a pull request"),
		mcp.WithString("owner",
			mcp.Required(),
			mcp.Description("Repository owner"),
		),
		mcp.WithString("repo",
			mcp.Required(),
			mcp.Description("Repository name"),
		),
		mcp.WithNumber("pr_number",
			mcp.Required(),
			mcp.Description("Pull request number"),
		),
		mcp.WithString("body",
			mcp.Required(),
			mcp.Description("Comment body"),
		),
	)
	s.AddTool(createPRCommentTool, createPRCommentHandler(gh))
}

// Tool handlers

func listReposHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)

		opts := &github.RepositoryListByUserOptions{}
		if t, ok := request.Params.Arguments["type"].(string); ok && t != "" {
			opts.Type = t
		}
		if pp, ok := request.Params.Arguments["per_page"].(float64); ok {
			opts.PerPage = int(pp)
		}

		repos, _, err := gh.Repositories.ListByUser(ctx, owner, opts)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to list repositories: %v", err)), nil
		}

		var result strings.Builder
		result.WriteString(fmt.Sprintf("Repositories for %s:\n\n", owner))
		for _, repo := range repos {
			result.WriteString(fmt.Sprintf("- **%s** (%s)\n", repo.GetName(), repo.GetHTMLURL()))
			if repo.Description != nil && *repo.Description != "" {
				result.WriteString(fmt.Sprintf("  %s\n", *repo.Description))
			}
			result.WriteString(fmt.Sprintf("  Stars: %d | Forks: %d | Language: %s\n\n",
				repo.GetStargazersCount(), repo.GetForksCount(), repo.GetLanguage()))
		}

		return mcp.NewToolResultText(result.String()), nil
	}
}

func getRepoHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)

		repository, _, err := gh.Repositories.Get(ctx, owner, repo)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to get repository: %v", err)), nil
		}

		result := fmt.Sprintf(`# %s/%s

**URL:** %s
**Description:** %s
**Language:** %s
**Default Branch:** %s

## Stats
- Stars: %d
- Forks: %d
- Open Issues: %d
- Watchers: %d

## Settings
- Private: %t
- Fork: %t
- Archived: %t
- Has Issues: %t
- Has Wiki: %t

**Created:** %s
**Updated:** %s
`,
			repository.GetOwner().GetLogin(), repository.GetName(),
			repository.GetHTMLURL(),
			repository.GetDescription(),
			repository.GetLanguage(),
			repository.GetDefaultBranch(),
			repository.GetStargazersCount(),
			repository.GetForksCount(),
			repository.GetOpenIssuesCount(),
			repository.GetWatchersCount(),
			repository.GetPrivate(),
			repository.GetFork(),
			repository.GetArchived(),
			repository.GetHasIssues(),
			repository.GetHasWiki(),
			repository.GetCreatedAt().Format("2006-01-02"),
			repository.GetUpdatedAt().Format("2006-01-02"),
		)

		return mcp.NewToolResultText(result), nil
	}
}

func listIssuesHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)

		opts := &github.IssueListByRepoOptions{}
		if state, ok := request.Params.Arguments["state"].(string); ok && state != "" {
			opts.State = state
		}
		if labels, ok := request.Params.Arguments["labels"].(string); ok && labels != "" {
			opts.Labels = strings.Split(labels, ",")
		}
		if pp, ok := request.Params.Arguments["per_page"].(float64); ok {
			opts.PerPage = int(pp)
		}

		issues, _, err := gh.Issues.ListByRepo(ctx, owner, repo, opts)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to list issues: %v", err)), nil
		}

		var result strings.Builder
		result.WriteString(fmt.Sprintf("Issues in %s/%s:\n\n", owner, repo))
		for _, issue := range issues {
			// Skip pull requests (they appear in issues API)
			if issue.PullRequestLinks != nil {
				continue
			}
			labels := make([]string, len(issue.Labels))
			for i, l := range issue.Labels {
				labels[i] = l.GetName()
			}
			result.WriteString(fmt.Sprintf("- #%d: **%s** [%s]\n",
				issue.GetNumber(), issue.GetTitle(), issue.GetState()))
			if len(labels) > 0 {
				result.WriteString(fmt.Sprintf("  Labels: %s\n", strings.Join(labels, ", ")))
			}
			result.WriteString(fmt.Sprintf("  Created: %s by @%s\n\n",
				issue.GetCreatedAt().Format("2006-01-02"), issue.GetUser().GetLogin()))
		}

		return mcp.NewToolResultText(result.String()), nil
	}
}

func getIssueHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)
		issueNum := int(request.Params.Arguments["issue_number"].(float64))

		issue, _, err := gh.Issues.Get(ctx, owner, repo, issueNum)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to get issue: %v", err)), nil
		}

		labels := make([]string, len(issue.Labels))
		for i, l := range issue.Labels {
			labels[i] = l.GetName()
		}

		result := fmt.Sprintf(`# Issue #%d: %s

**URL:** %s
**State:** %s
**Author:** @%s
**Created:** %s
**Updated:** %s

**Labels:** %s
**Assignees:** %s

## Body

%s
`,
			issue.GetNumber(), issue.GetTitle(),
			issue.GetHTMLURL(),
			issue.GetState(),
			issue.GetUser().GetLogin(),
			issue.GetCreatedAt().Format("2006-01-02 15:04"),
			issue.GetUpdatedAt().Format("2006-01-02 15:04"),
			strings.Join(labels, ", "),
			formatAssignees(issue.Assignees),
			issue.GetBody(),
		)

		return mcp.NewToolResultText(result), nil
	}
}

func createIssueHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)
		title := request.Params.Arguments["title"].(string)

		issueRequest := &github.IssueRequest{
			Title: &title,
		}

		if body, ok := request.Params.Arguments["body"].(string); ok && body != "" {
			issueRequest.Body = &body
		}
		if labels, ok := request.Params.Arguments["labels"].(string); ok && labels != "" {
			labelSlice := strings.Split(labels, ",")
			issueRequest.Labels = &labelSlice
		}

		issue, _, err := gh.Issues.Create(ctx, owner, repo, issueRequest)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to create issue: %v", err)), nil
		}

		result := fmt.Sprintf("Created issue #%d: %s\nURL: %s",
			issue.GetNumber(), issue.GetTitle(), issue.GetHTMLURL())

		return mcp.NewToolResultText(result), nil
	}
}

func listPRsHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)

		opts := &github.PullRequestListOptions{}
		if state, ok := request.Params.Arguments["state"].(string); ok && state != "" {
			opts.State = state
		}
		if base, ok := request.Params.Arguments["base"].(string); ok && base != "" {
			opts.Base = base
		}
		if pp, ok := request.Params.Arguments["per_page"].(float64); ok {
			opts.PerPage = int(pp)
		}

		prs, _, err := gh.PullRequests.List(ctx, owner, repo, opts)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to list pull requests: %v", err)), nil
		}

		var result strings.Builder
		result.WriteString(fmt.Sprintf("Pull Requests in %s/%s:\n\n", owner, repo))
		for _, pr := range prs {
			result.WriteString(fmt.Sprintf("- #%d: **%s** [%s]\n",
				pr.GetNumber(), pr.GetTitle(), pr.GetState()))
			result.WriteString(fmt.Sprintf("  %s -> %s\n",
				pr.GetHead().GetRef(), pr.GetBase().GetRef()))
			result.WriteString(fmt.Sprintf("  Author: @%s | Created: %s\n\n",
				pr.GetUser().GetLogin(), pr.GetCreatedAt().Format("2006-01-02")))
		}

		return mcp.NewToolResultText(result.String()), nil
	}
}

func getPRHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)
		prNum := int(request.Params.Arguments["pr_number"].(float64))

		pr, _, err := gh.PullRequests.Get(ctx, owner, repo, prNum)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to get pull request: %v", err)), nil
		}

		labels := make([]string, len(pr.Labels))
		for i, l := range pr.Labels {
			labels[i] = l.GetName()
		}

		result := fmt.Sprintf(`# PR #%d: %s

**URL:** %s
**State:** %s
**Draft:** %t
**Mergeable:** %v
**Author:** @%s

**Branch:** %s -> %s
**Created:** %s
**Updated:** %s

**Labels:** %s
**Reviewers:** %s

## Stats
- Commits: %d
- Changed Files: %d
- Additions: %d
- Deletions: %d

## Body

%s
`,
			pr.GetNumber(), pr.GetTitle(),
			pr.GetHTMLURL(),
			pr.GetState(),
			pr.GetDraft(),
			pr.GetMergeable(),
			pr.GetUser().GetLogin(),
			pr.GetHead().GetRef(), pr.GetBase().GetRef(),
			pr.GetCreatedAt().Format("2006-01-02 15:04"),
			pr.GetUpdatedAt().Format("2006-01-02 15:04"),
			strings.Join(labels, ", "),
			formatReviewers(pr.RequestedReviewers),
			pr.GetCommits(),
			pr.GetChangedFiles(),
			pr.GetAdditions(),
			pr.GetDeletions(),
			pr.GetBody(),
		)

		return mcp.NewToolResultText(result), nil
	}
}

func getFileHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)
		path := request.Params.Arguments["path"].(string)

		opts := &github.RepositoryContentGetOptions{}
		if ref, ok := request.Params.Arguments["ref"].(string); ok && ref != "" {
			opts.Ref = ref
		}

		fileContent, _, _, err := gh.Repositories.GetContents(ctx, owner, repo, path, opts)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to get file: %v", err)), nil
		}

		if fileContent == nil {
			return mcp.NewToolResultError("Path is a directory, not a file"), nil
		}

		content, err := fileContent.GetContent()
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to decode file content: %v", err)), nil
		}

		result := fmt.Sprintf("# %s\n\n**Path:** %s\n**Size:** %d bytes\n**SHA:** %s\n\n```\n%s\n```",
			fileContent.GetName(),
			fileContent.GetPath(),
			fileContent.GetSize(),
			fileContent.GetSHA(),
			content,
		)

		return mcp.NewToolResultText(result), nil
	}
}

func searchCodeHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		query := request.Params.Arguments["query"].(string)

		opts := &github.SearchOptions{}
		if pp, ok := request.Params.Arguments["per_page"].(float64); ok {
			opts.PerPage = int(pp)
		}

		results, _, err := gh.Search.Code(ctx, query, opts)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to search code: %v", err)), nil
		}

		var result strings.Builder
		result.WriteString(fmt.Sprintf("Search results for '%s' (%d total):\n\n", query, results.GetTotal()))
		for _, item := range results.CodeResults {
			result.WriteString(fmt.Sprintf("- **%s** in %s/%s\n",
				item.GetPath(),
				item.GetRepository().GetOwner().GetLogin(),
				item.GetRepository().GetName()))
			result.WriteString(fmt.Sprintf("  URL: %s\n\n", item.GetHTMLURL()))
		}

		return mcp.NewToolResultText(result.String()), nil
	}
}

func listCommitsHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)

		opts := &github.CommitsListOptions{}
		if sha, ok := request.Params.Arguments["sha"].(string); ok && sha != "" {
			opts.SHA = sha
		}
		if path, ok := request.Params.Arguments["path"].(string); ok && path != "" {
			opts.Path = path
		}
		if pp, ok := request.Params.Arguments["per_page"].(float64); ok {
			opts.PerPage = int(pp)
		}

		commits, _, err := gh.Repositories.ListCommits(ctx, owner, repo, opts)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to list commits: %v", err)), nil
		}

		var result strings.Builder
		result.WriteString(fmt.Sprintf("Commits in %s/%s:\n\n", owner, repo))
		for _, commit := range commits {
			message := commit.GetCommit().GetMessage()
			// Truncate long messages
			if len(message) > 100 {
				message = message[:100] + "..."
			}
			// Replace newlines for single-line display
			message = strings.ReplaceAll(message, "\n", " ")

			result.WriteString(fmt.Sprintf("- **%s**: %s\n",
				commit.GetSHA()[:7], message))
			result.WriteString(fmt.Sprintf("  Author: @%s | Date: %s\n\n",
				commit.GetAuthor().GetLogin(),
				commit.GetCommit().GetAuthor().GetDate().Format("2006-01-02 15:04")))
		}

		return mcp.NewToolResultText(result.String()), nil
	}
}

func createPRCommentHandler(gh *github.Client) server.ToolHandlerFunc {
	return func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		owner := request.Params.Arguments["owner"].(string)
		repo := request.Params.Arguments["repo"].(string)
		prNum := int(request.Params.Arguments["pr_number"].(float64))
		body := request.Params.Arguments["body"].(string)

		comment := &github.IssueComment{
			Body: &body,
		}

		created, _, err := gh.Issues.CreateComment(ctx, owner, repo, prNum, comment)
		if err != nil {
			return mcp.NewToolResultError(fmt.Sprintf("Failed to create comment: %v", err)), nil
		}

		result := fmt.Sprintf("Created comment on PR #%d\nURL: %s",
			prNum, created.GetHTMLURL())

		return mcp.NewToolResultText(result), nil
	}
}

// Helper functions

func formatAssignees(assignees []*github.User) string {
	if len(assignees) == 0 {
		return "None"
	}
	names := make([]string, len(assignees))
	for i, a := range assignees {
		names[i] = "@" + a.GetLogin()
	}
	return strings.Join(names, ", ")
}

func formatReviewers(reviewers []*github.User) string {
	if len(reviewers) == 0 {
		return "None"
	}
	names := make([]string, len(reviewers))
	for i, r := range reviewers {
		names[i] = "@" + r.GetLogin()
	}
	return strings.Join(names, ", ")
}

// Utility function for converting interface to int (not currently used but useful)
func toInt(v interface{}) int {
	switch val := v.(type) {
	case float64:
		return int(val)
	case int:
		return val
	case string:
		i, _ := strconv.Atoi(val)
		return i
	default:
		return 0
	}
}
