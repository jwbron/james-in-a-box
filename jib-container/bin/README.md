# PR Analyzer Tool

Analyzes GitHub Pull Requests and suggests or implements fixes using Claude.

## Overview

The PR analyzer fetches comprehensive context about a PR (metadata, diff, comments, reviews, CI status, failed check logs) and uses Claude to analyze issues and suggest solutions.

## Installation

The tool is automatically available when jib is set up. It requires:
- `gh` CLI installed and authenticated
- jib container built and ready

## Usage

### Basic Analysis

```bash
# Full URL
analyze-pr https://github.com/Khan/buildmaster2/pull/179

# Shorthand
analyze-pr Khan/buildmaster2#179

# Alternative format
analyze-pr Khan/buildmaster2/pull/179
```

### Options

| Flag | Description |
|------|-------------|
| `--fix` | Attempt to implement fixes (checkout PR branch, make changes, push) |
| `--interactive` | Drop into interactive Claude session after analysis |
| `--context-only` | Only fetch PR context, don't run analyzer |

### Examples

```bash
# Analyze and get suggestions
analyze-pr Khan/repo#123

# Analyze and implement fixes
analyze-pr --fix Khan/repo#123

# Interactive mode for complex issues
analyze-pr --interactive Khan/repo#123

# Just fetch context for manual review
analyze-pr --context-only Khan/repo#123
```

## How It Works

### 1. Host-side: Context Fetching (`bin/analyze-pr`)

The host-side script uses `gh` CLI to fetch:

| Data | Source |
|------|--------|
| PR metadata | `gh pr view --json` (title, state, author, review decision, etc.) |
| Full diff | `gh pr diff` |
| Files changed | `gh pr view --json files` |
| Comments | `gh pr view --json comments` |
| Review comments | `gh api repos/.../pulls/.../comments` |
| Reviews | `gh pr view --json reviews` |
| CI checks | `gh pr checks --json` |
| Failed check logs | `gh run view --log-failed` (for failed checks) |
| Commits | `gh pr view --json commits` |

Context is written to `~/.jib-sharing/pr-analysis/<repo>-<pr>-<timestamp>.json`

### 2. Container-side: Analysis (`watchers/pr-analyzer.py`)

The container script:
1. Loads the JSON context file
2. Formats it into a comprehensive prompt for Claude
3. Runs Claude with full tool access
4. In `--fix` mode: checks out the PR branch, makes changes, commits, and pushes

## Output

### Analysis Mode (default)

Claude provides:
- Summary of what the PR does
- Issues found (with priority)
- Failing CI analysis
- Review feedback summary
- Recommended next steps

### Fix Mode (`--fix`)

If the repo is available in `~/khan/`:
1. Checks out the PR branch
2. Makes necessary changes using Claude's tools
3. Commits with descriptive message
4. Pushes to update the PR

If repo not available:
- Provides detailed fix instructions
- Shows code snippets for manual changes

## Data Flow

```
analyze-pr <url>
     │
     ▼
┌─────────────────────────────┐
│ Host: bin/analyze-pr        │
│ - Parse PR reference        │
│ - Fetch via gh CLI          │
│ - Write JSON to sharing dir │
└─────────────────────────────┘
     │
     ▼
jib --exec python3 watchers/pr-analyzer.py <context.json>
     │
     ▼
┌─────────────────────────────┐
│ Container: pr-analyzer.py   │
│ - Load context JSON         │
│ - Format prompt             │
│ - Run Claude                │
│ - (--fix) Make changes      │
│ - Create notification       │
└─────────────────────────────┘
     │
     ▼
Results (stdout + notification)
```

## Configuration

The tool uses the configured GitHub username from `config/repositories.yaml` for:
- Determining write access to repos
- Setting default reviewer for any PRs created

## Troubleshooting

### "gh not found"
Install GitHub CLI: https://cli.github.com/

### "Could not resolve to a Repository"
- Check the repo name is correct
- Ensure you have access (private repos need authentication)
- Run `gh auth login` if needed

### Analysis times out
- Large PRs may take longer
- Use `--context-only` to just fetch data
- Check the context JSON manually

### Changes not pushed
- Verify the repo exists in `~/khan/`
- Check write access in `config/repositories.yaml`
- Ensure the PR is still open
