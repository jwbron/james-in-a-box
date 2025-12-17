# Beads Integration Guide

How to integrate Beads task tracking into container-side tools and scripts.

## Overview

Beads provides persistent task memory across ephemeral container sessions. When building container-side tools that process tasks, you should integrate with Beads to:

- Track work across container restarts
- Maintain context between related tasks
- Enable discovery of prior work on the same PR/issue/thread

## Core Requirements

**MANDATORY: Every PR and every Slack thread MUST have a beads task.**

1. **PR Tasks**: Each GitHub PR gets a unique beads task (via `PRContextManager`)
   - Task is created on first interaction (review, comment, check failure, etc.)
   - Task persists across all interactions with that PR
   - Task is loaded on EVERY PR interaction, even if marked as closed
   - Multiple Slack threads about the same PR should link to the PR's beads task

2. **Slack Thread Tasks**: Each Slack thread gets a unique beads task
   - Task is created when thread starts (first message)
   - Task persists across all replies in the thread
   - Task is loaded on EVERY thread reply, even if marked as closed
   - If thread is about a specific PR, link the thread task to the PR task

3. **Loading Closed Tasks**: Tasks marked as "closed" are still loaded when:
   - Receiving a new message in that Slack thread
   - Receiving a new GitHub event for that PR
   - User explicitly references that PR or thread
   - This ensures context is preserved even after work is "done"

4. **Full Thread Context Discovery**: The LLM must be able to discover full context:
   - Slack thread history should be included in the prompt
   - Beads tasks should be searchable by both task ID and thread ID
   - PR-related Slack threads should reference the PR in labels
   - Instructions should explicitly tell Claude how to find and load all related context

## When to Integrate

**Beads integration is required for container tasks that:**
- Process work items that may span multiple sessions (PRs, Slack threads, JIRA tickets)
- Need to remember context from previous interactions
- Should avoid duplicate work on the same item
- Track progress on multi-step tasks

**Beads integration is NOT needed for:**
- One-shot utilities with no persistent state
- Host-side services (beads runs in the container)
- GitHub Actions workflows (run in GitHub's environment)

## Integration Approaches

### 1. Direct Integration (Recommended)

Use a context manager class to directly call the `bd` CLI:

```python
import subprocess
from pathlib import Path

class TaskContextManager:
    """Manages persistent task context in Beads."""

    def __init__(self):
        self.beads_dir = Path.home() / "beads"

    def get_context_id(self, identifier: str) -> str:
        """Generate unique context ID for a task."""
        return f"task-{identifier}"

    def search_context(self, identifier: str) -> str | None:
        """Search for existing beads task.

        Returns:
            Beads task ID if found, None otherwise.
        """
        context_id = self.get_context_id(identifier)
        try:
            result = subprocess.run(
                ["bd", "--allow-stale", "search", context_id],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if line.strip() and line.startswith("beads-"):
                        return line.split()[0]
            return None
        except Exception:
            return None

    def create_context(self, identifier: str, title: str, labels: list[str]) -> str | None:
        """Create new beads task for tracking.

        Returns:
            Beads task ID if created, None on failure.
        """
        context_id = self.get_context_id(identifier)
        label_str = ",".join(labels + [context_id])

        try:
            result = subprocess.run(
                ["bd", "--allow-stale", "create", title, "--labels", label_str],
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            if result.returncode == 0:
                # Parse task ID from output
                for line in result.stdout.split("\n"):
                    if "beads-" in line:
                        for word in line.split():
                            if word.startswith("beads-"):
                                return word
            return None
        except Exception:
            return None

    def update_context(self, task_id: str, notes: str, status: str | None = None) -> bool:
        """Update beads task with progress."""
        cmd = ["bd", "--allow-stale", "update", task_id, "--notes", notes]
        if status:
            cmd.extend(["--status", status])

        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                cwd=self.beads_dir,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False
```

**Example usage in a processor:**

```python
def process_pr(repo: str, pr_num: int, context: dict):
    """Process a PR with beads context tracking."""
    ctx_manager = TaskContextManager()

    # 1. Check for existing context
    task_id = ctx_manager.search_context(f"pr-{repo.split('/')[-1]}-{pr_num}")

    if task_id:
        # Resume existing task
        ctx_manager.update_context(task_id, "Resuming PR processing...")
    else:
        # Create new task
        task_id = ctx_manager.create_context(
            identifier=f"pr-{repo.split('/')[-1]}-{pr_num}",
            title=f"PR #{pr_num}: {context.get('title', 'Unknown')}",
            labels=["github", "pr", repo.split('/')[-1]]
        )

    try:
        # Do the actual work...
        result = do_pr_processing(context)

        # Update with results
        ctx_manager.update_context(
            task_id,
            f"Processing complete. Result: {result}",
            status="closed"
        )
    except Exception as e:
        ctx_manager.update_context(
            task_id,
            f"Processing failed: {e}",
            status="blocked"
        )
        raise
```

### 2. Prompt-Based Integration

For scripts that invoke Claude, include beads instructions in the prompt:

```python
prompt = f"""# Task Processing

## Beads Context (MANDATORY)

**Task ID:** `{task_id}`

### Step 1: Check for existing context
```bash
cd ~/beads
bd --allow-stale search "{task_id}"
# If found: bd --allow-stale show <found-id>
```

### Step 2: Create or update task
If no existing task:
```bash
bd --allow-stale create "Task: {title}" --labels {labels}
bd --allow-stale update <id> --status in_progress
```

### Step 3: Update when done (MANDATORY)
```bash
bd --allow-stale update <task-id> --notes "Summary of work done"
bd --allow-stale update <task-id> --status closed
```

## Your Task

{actual_task_description}
"""
```

**When to use each approach:**

| Approach | Best For | Reliability |
|----------|----------|-------------|
| Direct integration | Critical task tracking, idempotency checks | High - doesn't depend on Claude |
| Prompt-based | Flexible exploration, Claude-driven tasks | Medium - depends on Claude following instructions |

## Reference Implementation

See these files for working examples:

- **Direct integration**: `jib-container/jib-tasks/github/pr-reviewer.py` - Uses `PRContextManager` class
- **Direct integration**: `jib-container/jib-tasks/github/comment-responder.py` - Uses `PRContextManager` class
- **Prompt-based**: `jib-container/jib-tasks/slack/incoming-processor.py` - Includes beads in Claude prompts

## Context ID Conventions

Use consistent, searchable context IDs:

| Source | Format | Example |
|--------|--------|---------|
| GitHub PR | `pr-{repo}-{number}` | `pr-james-in-a-box-75` |
| Slack thread | `task-{task_id}` | `task-20251128-134500` |
| Slack thread ID | `thread:{thread_ts}` | `thread:1765932352.046209` |
| JIRA ticket | `jira-{ticket}` | `jira-PROJECT-1234` |
| Confluence page | `confluence-{page_id}` | `confluence-12345678` |

## Linking Tasks

When a Slack thread is focused on a specific PR, create a bidirectional link:

```python
# Create Slack thread task with PR reference in labels
slack_task_id = manager.create_context(
    identifier=f"task-{timestamp}",
    title=f"Slack: Discussion about PR #{pr_num}",
    labels=["slack-thread", f"thread:{thread_ts}", f"pr-{repo_name}-{pr_num}"]
)

# Update PR task to reference the Slack thread
pr_task_id = pr_manager.get_or_create_context(repo, pr_num, pr_title)
pr_manager.update_context(
    pr_task_id,
    f"Slack thread {thread_ts} discussing this PR"
)
```

This allows:
- Finding all Slack discussions about a PR: `bd list --label pr-{repo}-{pr_num}`
- Finding the PR being discussed in a thread: Search labels for `pr-*` pattern
- Maintaining context across both GitHub and Slack interactions

## Labeling Strategy

Include these labels for discoverability:

```python
labels = [
    source,           # github, slack, jira, confluence
    type,             # pr, issue, thread, ticket
    repo_or_project,  # james-in-a-box, webapp
    context_id,       # pr-james-in-a-box-75
]
```

## Current Integration Status

| Script | Integration | Notes |
|--------|-------------|-------|
| `github/pr-reviewer.py` | Direct | PRContextManager class |
| `github/comment-responder.py` | Direct | PRContextManager class |
| `slack/incoming-processor.py` | Prompt-based | Instructions in Claude prompt |
| `github/github-processor.py` | Prompt-based | Instructions in Claude prompt |
| `github/pr-analyzer.py` | None | Should add direct integration |
| `jira/jira-processor.py` | None | Should add direct integration |
| `confluence/confluence-processor.py` | None | Should add direct integration |

## Best Practices

1. **Always check for existing context first** - Avoids duplicate tasks
2. **Use `--allow-stale` flag** - Required in ephemeral containers
3. **Update status immediately** - Mark `in_progress` when starting, `closed` when done
4. **Include meaningful notes** - Future sessions need context
5. **Use searchable context IDs** - Include PR numbers, ticket IDs in labels
6. **Handle failures gracefully** - Beads failures shouldn't break the main task

## See Also

- [Beads Reference](../reference/beads.md) - Full command reference
- [Beads Usage Rules](../../jib-container/.claude/rules/beads-usage.md) - Quick reference
- [Context Tracking](../../jib-container/.claude/rules/context-tracking.md) - Agent context patterns
