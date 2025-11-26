# GitHub PR Context - Persistent Memory via Beads

## Overview

When processing GitHub PRs (comments, reviews, check failures), you MUST use the PR number and repository as a unique key to maintain persistent context across container restarts and multiple interactions. This ensures continuity even when containers are ephemeral.

**CRITICAL**: Every PR is a conversation. Use `pr-<repo>-<number>` as a unique key to save/load context from Beads.

## How PR Context IDs Work

For GitHub PR workflows, context is identified by:
- **Repository**: The repo name (e.g., `james-in-a-box`)
- **PR Number**: The pull request number (e.g., `75`)
- **Context ID**: `pr-<repo>-<number>` (e.g., `pr-james-in-a-box-75`)

This ID is used as a beads label for searching and tracking.

## MANDATORY Workflow

### When Processing Any PR Event

**ALWAYS do this FIRST before any other work:**

```bash
# 1. Extract PR context from the event
REPO_NAME="james-in-a-box"  # From the PR data
PR_NUM="75"                  # From the PR data
PR_CONTEXT_ID="pr-${REPO_NAME}-${PR_NUM}"

# 2. Search for existing context in Beads
cd ~/beads
bd list --search "$PR_CONTEXT_ID"

# 3A. If found - LOAD the context
bd show <found-id>  # Review previous work, decisions, progress

# 3B. If not found - CREATE new task with PR context as label
bd create "PR #$PR_NUM: [PR Title]" \
  --label github-pr \
  --label "$PR_CONTEXT_ID" \
  --label "$REPO_NAME"
```

### Context to Track for Each PR

Every PR task should maintain notes with:
- **PR Details**: Title, author, branch, base
- **Actions Taken**: Comments posted, code changes made, reviews given
- **Pending Items**: Unaddressed feedback, open questions
- **History**: Chronological log of interactions

Example notes format:
```
PR #75: Improve beads task management
Author: @jwiesebron
Branch: feature/beads-improvements -> main

=== 2025-01-20 14:30 ===
Processed 2 review comments:
- Addressed naming concern → committed fix
- Answered question about error handling

=== 2025-01-20 15:00 ===
CI check failure: eslint
- Auto-fixed with eslint --fix
- Pushed to branch

Pending:
- Awaiting re-review from @reviewer
```

### During PR Work

**Update Beads with context as you work:**

```bash
# Add notes about actions taken
bd update <task-id> --notes "=== $(date '+%Y-%m-%d %H:%M') ===
Processed comment from @reviewer:
- Made requested changes
- Pushed commit abc1234"

# Update status as appropriate
bd update <task-id> --status in_progress
```

### When PR is Completed (Merged/Closed)

**Mark the task done with final summary:**

```bash
bd update <task-id> --status closed
bd update <task-id> --notes "=== $(date '+%Y-%m-%d %H:%M') ===
PR MERGED
- All feedback addressed
- 3 comments responded to
- 2 code changes made
- Final approval from @reviewer"
```

## Complete Example

```bash
# PR comment event arrives for PR #42 in webapp

# Step 1: Check for existing context
cd ~/beads
bd list --search "pr-webapp-42"

# Result: Found existing task beads-xyz123
bd show beads-xyz123
# Shows: "PR #42: Add user authentication
#         Author: @developer
#         === 2025-01-19 10:00 ===
#         Initial review posted
#         === 2025-01-19 14:00 ===
#         Addressed feedback on error handling"

# Step 2: New comment is: "Please add more tests"

# Step 3: Update context with new information
bd update beads-xyz123 --status in_progress
bd update beads-xyz123 --notes "=== $(date '+%Y-%m-%d %H:%M') ===
Processing comment: 'Please add more tests'
Adding test coverage..."

# Step 4: Do the work (add tests, commit, push)...

# Step 5: Update context with results
bd update beads-xyz123 --notes "=== $(date '+%Y-%m-%d %H:%M') ===
Added 3 test cases for authentication
Pushed commit def5678
Posted response to reviewer"
```

## Why This Matters

1. **Containers are ephemeral**: Each GitHub event may spawn a new container
2. **Context must persist**: Without Beads, you lose all memory between events
3. **PRs are conversations**: Multiple comments, reviews, and CI runs relate to the same work
4. **Avoid redundancy**: Loading context prevents re-doing analysis or asking duplicate questions
5. **Track history**: See what's been done on a PR across multiple sessions

## PR Lifecycle in Beads

| PR Event | Beads Action |
|----------|--------------|
| First comment/review | Create task with `pr-<repo>-<num>` label |
| Subsequent events | Load existing task, append notes |
| Comment response | Update notes with response summary |
| CI failure | Update notes with failure analysis |
| Code changes made | Update notes with commit reference |
| PR merged | Mark task `closed` with final summary |
| PR closed (no merge) | Mark task `cancelled` with reason |

## Label Conventions

Always use these labels for PR tasks:
- `github-pr` - Type identifier
- `pr-<repo>-<num>` - Unique context ID (e.g., `pr-webapp-42`)
- `<repo>` - Repository name for filtering (e.g., `webapp`)

Optional labels:
- `ci-failure` - If tracking check failures
- `review` - If tracking reviews
- `urgent` - If marked urgent

## Integration with GitHub Scripts

### comment-responder.py
- Search for existing PR context before generating response
- Update notes with comment processed and response posted
- Reference previous context in Claude prompts

### pr-reviewer.py
- Create/update PR task when reviewing
- Track review status and findings
- Note when follow-up reviews are needed

### check-monitor.py
- Search for existing PR context for failed checks
- Update notes with failure analysis
- Track fix attempts and status

## Quick Reference

| When | Action |
|------|--------|
| Any PR event | `bd list --search "pr-<repo>-<num>"` |
| New PR context | `bd create "PR #<num>: <title>" --label github-pr --label "pr-<repo>-<num>"` |
| Existing context | `bd show <id>` then `bd update <id> --status in_progress` |
| During work | `bd update <id> --notes "=== <timestamp> ===\n<what was done>"` |
| PR merged | `bd update <id> --status closed --notes "PR MERGED..."` |

**Remember**: The PR context ID (`pr-<repo>-<num>`) is your key to persistent memory. NEVER process a PR event without first checking Beads for existing context.
