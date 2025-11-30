#!/usr/bin/env python3
"""
Incoming Message Processor

Processes a single incoming message or response from Slack.
Called by slack-receiver via `jib --exec` after writing a message file.

IMPORTANT: Preserves thread context from incoming messages.
The incoming message file contains YAML frontmatter with thread_ts,
which is propagated to the response notification for proper Slack threading.

Notification behavior:
- ALWAYS sends a notification back to Slack, even on failure
- Success: includes Claude's response
- Failure: includes error details and troubleshooting info
- Timeout: notifies user and suggests retry

Usage:
  python3 incoming-processor.py <message-file>
"""

import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


# Add shared directory to path for enrichment, Claude runner, and jib_logging modules
sys.path.insert(0, str(Path.home() / "khan" / "james-in-a-box" / "shared"))

from claude.runner import run_claude
from enrichment import enrich_task
from jib_logging import get_logger


# Initialize jib_logging logger
logger = get_logger("incoming-processor")


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from file content.

    Returns:
        Tuple of (metadata dict, content without frontmatter)
    """
    metadata = {}

    # Check for YAML frontmatter (starts with ---)
    if not content.startswith("---"):
        return metadata, content

    # Find the closing ---
    lines = content.split("\n")
    end_idx = -1
    for i, line in enumerate(lines[1:], start=1):  # Skip first ---
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        # No closing ---, treat as no frontmatter
        return metadata, content

    # Parse the frontmatter (simple key: value parsing)
    frontmatter_lines = lines[1:end_idx]
    for line in frontmatter_lines:
        line = line.strip()
        if ":" in line and not line.startswith("#"):
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")  # Remove quotes
            if value:  # Only add non-empty values
                metadata[key] = value

    # Return content without frontmatter
    remaining_content = "\n".join(lines[end_idx + 1 :]).strip()
    return metadata, remaining_content


def create_notification_with_thread(
    notifications_dir: Path, task_id: str, thread_ts: str, content: str
) -> Path:
    """Create a notification file with YAML frontmatter for threading.

    Args:
        notifications_dir: Directory to write notification to
        task_id: Task ID for filename and thread lookup
        thread_ts: Slack thread timestamp for threading
        content: Notification content (markdown)

    Returns:
        Path to created notification file
    """
    notifications_dir.mkdir(parents=True, exist_ok=True)

    notification_file = notifications_dir / f"{task_id}.md"

    # Build frontmatter
    frontmatter_lines = [
        "---",
        f'task_id: "{task_id}"',
    ]
    if thread_ts:
        frontmatter_lines.append(f'thread_ts: "{thread_ts}"')
    frontmatter_lines.append("---")
    frontmatter_lines.append("")

    frontmatter = "\n".join(frontmatter_lines)
    full_content = frontmatter + content

    notification_file.write_text(full_content)
    return notification_file


def process_task(message_file: Path):
    """Process an incoming task from Slack using Claude Code.

    ALWAYS creates a notification back to Slack, whether successful or not.
    """
    start_time = time.time()
    logger.info("Processing task", file=message_file.name)

    # Read full message content
    raw_content = message_file.read_text()

    # Parse frontmatter to extract thread context
    frontmatter, content = parse_frontmatter(raw_content)
    thread_ts = frontmatter.get("thread_ts", "")
    original_task_id = frontmatter.get("task_id", message_file.stem)
    notifications_dir = Path.home() / "sharing" / "notifications"

    logger.info("Task metadata", task_id=original_task_id, thread_ts=thread_ts or None)

    # Extract task description (after "## Current Message" header)
    task_lines = []
    in_message_section = False
    for line in content.split("\n"):
        if line.startswith("## Current Message"):
            in_message_section = True
            continue
        if in_message_section:
            if line.startswith("---"):
                break
            if line.strip():
                task_lines.append(line)

    task_content = "\n".join(task_lines).strip()

    if not task_content:
        logger.warning("Empty task content - nothing to process", task_id=original_task_id)
        # Still send a notification about the empty task
        create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id=original_task_id,
            thread_ts=thread_ts,
            content="# Task Processing Issue\n\nReceived an empty task with no content to process.\n",
        )
        return False

    logger.info("Task content extracted", preview=task_content[:100])

    # Enrich task with relevant documentation context (Phase 3 of LLM Doc Strategy ADR)
    enriched_context = enrich_task(task_content)
    if enriched_context:
        logger.info("Added documentation context enrichment", task_id=original_task_id)

    # Build thread context section if available
    thread_context_section = ""
    if frontmatter.get("thread_ts"):
        thread_context_section = f"""
## Thread Context (CRITICAL)

**Thread ID:** `{thread_ts}`
**This is part of an ongoing Slack conversation.** You MUST:
1. Search beads for existing context: `bd --allow-stale search "{original_task_id}"`
2. If found, load the previous work context before proceeding
3. If not found, create a new beads task with this thread ID as a label
"""

    # Construct prompt for Claude with full context
    prompt = f"""# Slack Task Processing

You received a task via Slack. Process it according to the workflow below.

## Message Details

**File:** `{message_file.name}`
**Task ID:** `{original_task_id}`
**Received:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
{thread_context_section}

## Task from User

{task_content}

{enriched_context}
## Your Workflow

### 1. FIRST: Check Beads for Existing Context (MANDATORY)

```bash
cd ~/beads
bd --allow-stale search "{original_task_id}"
# If found: bd --allow-stale show <found-id> to load context
# If not found: Create new task below
```

### 2. Track in Beads

If no existing task was found:
```bash
bd --allow-stale create "Slack: {original_task_id}" --labels slack-thread,"{original_task_id}" --description "Task from Slack thread"
bd --allow-stale update <id> --status in_progress
```

### 3. Execute the task
   - Read relevant code/documentation
   - Make necessary changes
   - Run tests if applicable
   - Commit changes with clear messages

### 4. Create PR (if code changes were made)
   - Use GitHub MCP to create the PR: `create_pull_request(owner, repo, title, head, base, body)`
   - Push the branch first using MCP `push_files` if needed
   - Request review from @jwiesebron
   - Your output will be captured and threaded correctly

### 5. Update Beads with Results (MANDATORY)
```bash
bd --allow-stale update <task-id> --notes "Summary of work done. PR #XX if created. Next steps if any."
bd --allow-stale update <task-id> --status closed  # Or keep open if awaiting response
```

### 6. Output your response
Print a clear summary to stdout with:
   - Summary of what was done
   - PR URL (if created)
   - Branch name (if commits were made)
   - Next steps for user
   - Any blockers or questions

## Important Notes

- You're in an ephemeral container (will exit when done)
- All work should be committed to git
- **Create a PR after completing code changes** - this lets the user review on GitHub
- **Beads is your persistent memory** - ALWAYS check and update beads
- Working directory: You can access all repos in `~/khan/`
- Use GitHub MCP to create PRs and request review from @jwiesebron
- **DO NOT create notification files directly** - your stdout will be captured and sent as a threaded Slack notification automatically

Process this task now."""

    # Run Claude Code via shared runner module
    # This delegates timeout handling to the shared module (default: 30 minutes)
    # and provides consistent behavior across all Claude invocations
    logger.info("Starting Claude Code", task_id=original_task_id)

    claude_result = run_claude(
        prompt=prompt,
        cwd=Path.home() / "khan",  # Start in khan directory
        capture_output=True,
    )
    logger.info("Claude completed", return_code=claude_result.returncode, task_id=original_task_id)
    if claude_result.stderr:
        logger.warning("Claude stderr output", stderr=claude_result.stderr[:500])

    # Determine success/failure/timeout status
    timed_out = False
    error_message = None
    if not claude_result.success:
        if claude_result.error and "timed out" in claude_result.error.lower():
            timed_out = True
        error_message = claude_result.error

    # Calculate processing time
    elapsed_time = time.time() - start_time
    elapsed_str = f"{elapsed_time:.1f}s" if elapsed_time < 60 else f"{elapsed_time / 60:.1f}m"
    logger.info("Processing completed", duration=elapsed_str, task_id=original_task_id)

    # ALWAYS create a notification - success, failure, or timeout
    task_summary = task_content[:100] + ("..." if len(task_content) > 100 else "")

    if claude_result.returncode == 0:
        # SUCCESS: Include Claude's response
        logger.info("Task processed successfully", task_id=original_task_id)

        claude_output = claude_result.stdout.strip() if claude_result.stdout else ""
        if not claude_output:
            logger.warning(
                "Claude returned empty output despite success return code", task_id=original_task_id
            )
            claude_output = "*Claude completed but produced no output. The task may have been processed - check GitHub for any PRs created.*"

        notification_content = f"""# Task Completed

**Task:** {task_summary}
**Processing time:** {elapsed_str}
**Status:** Success

## Response

{claude_output}

---
*Generated by jib incoming-processor*
"""
    elif timed_out:
        # TIMEOUT: Notify user with helpful context
        logger.error("Task timed out", task_id=original_task_id, duration=elapsed_str)
        partial_output = ""
        if claude_result.stdout:
            partial_output = (
                f"\n\n**Partial output before timeout:**\n{claude_result.stdout[:1000]}"
            )

        notification_content = f"""# Task Processing Timed Out

**Task:** {task_summary}
**Processing time:** {elapsed_str} (timeout)
**Status:** {error_message or "Timed out"}

The task took too long to complete. This can happen with complex tasks.
{partial_output}

**What you can do:**
- Check GitHub for any PRs that may have been created before timeout
- Try breaking the task into smaller pieces
- Retry the task if it was interrupted mid-way

---
*Generated by jib incoming-processor*
"""
    else:
        # FAILURE: Include error details
        stderr_output = claude_result.stderr[:500] if claude_result.stderr else "None"
        stdout_output = claude_result.stdout[:500] if claude_result.stdout else "None"

        logger.error(
            "Task failed",
            task_id=original_task_id,
            return_code=claude_result.returncode,
            error=error_message,
        )

        notification_content = f"""# Task Processing Failed

**Task:** {task_summary}
**Processing time:** {elapsed_str}
**Status:** Failed (exit code: {claude_result.returncode})

## Error Details

{error_message or "Claude exited with non-zero status"}

**Stderr:** {stderr_output}

**Stdout (partial):** {stdout_output}

**What you can do:**
- Check the logs at `~/sharing/logs/incoming-processor.log`
- Check GitHub for any PRs that may have been created
- Retry the task

---
*Generated by jib incoming-processor*
"""

    # Write the notification
    notification_file = create_notification_with_thread(
        notifications_dir=notifications_dir,
        task_id=original_task_id,
        thread_ts=thread_ts,
        content=notification_content,
    )
    logger.info("Notification created", file=notification_file.name, thread_ts=thread_ts or None)

    return claude_result.returncode == 0


def extract_original_task_id(content: str) -> str | None:
    """Extract the original task ID from thread context.

    Looks for patterns like:
    - "Saved to: `task-20251126-150200.md`"
    - "task-YYYYMMDD-HHMMSS" anywhere in thread context

    Returns the task ID (e.g., "task-20251126-150200") or None.
    """
    # Pattern to match task IDs: task-YYYYMMDD-HHMMSS
    task_pattern = r"task-\d{8}-\d{6}"

    # Look for "Saved to:" pattern first (most reliable)
    saved_to_match = re.search(r"Saved to: `(" + task_pattern + r")\.md`", content)
    if saved_to_match:
        return saved_to_match.group(1)

    # Fall back to any task ID in the content
    task_match = re.search(task_pattern, content)
    if task_match:
        return task_match.group(0)

    return None


def extract_thread_context(content: str) -> tuple[str, list[str]]:
    """Extract thread context and PR/repo references from message content.

    Returns:
        Tuple of (thread_context_text, list of PR/repo references found)
    """
    thread_context = ""
    pr_refs = []

    # Extract the Thread Context section
    in_thread_context = False
    thread_lines = []
    for line in content.split("\n"):
        if line.startswith("## Thread Context"):
            in_thread_context = True
            continue
        if in_thread_context:
            if line.startswith("## ") and not line.startswith("## Thread"):
                break
            thread_lines.append(line)

    thread_context = "\n".join(thread_lines).strip()

    # Extract PR references from the full content
    # Patterns to match:
    # - "PR Analysis: Khan/terraform-modules#29"
    # - "https://github.com/owner/repo/pull/123"
    # - "owner/repo#123"
    pr_analysis_pattern = r"PR Analysis:\s*([^#\s]+)#(\d+)"
    github_url_pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    shorthand_pattern = r"([A-Za-z0-9_-]+/[A-Za-z0-9_-]+)#(\d+)"

    # Search in thread context and full content
    for text in [thread_context, content]:
        # PR Analysis format
        for match in re.finditer(pr_analysis_pattern, text):
            ref = f"{match.group(1)}#{match.group(2)}"
            if ref not in pr_refs:
                pr_refs.append(ref)

        # GitHub URLs
        for match in re.finditer(github_url_pattern, text):
            ref = f"{match.group(1)}/{match.group(2)}#{match.group(3)}"
            if ref not in pr_refs:
                pr_refs.append(ref)

        # Shorthand owner/repo#number (but exclude file paths)
        for match in re.finditer(shorthand_pattern, text):
            # Exclude common false positives like issue/comment patterns
            ref = f"{match.group(1)}#{match.group(2)}"
            if ref not in pr_refs and "/" in match.group(1):
                pr_refs.append(ref)

    return thread_context, pr_refs


def process_response(message_file: Path):
    """Process a user's response to a previous notification using Claude Code.

    ALWAYS creates a notification back to Slack, whether successful or not.
    """
    start_time = time.time()
    logger.info("Processing response", file=message_file.name)

    # Read response content
    raw_content = message_file.read_text()

    # Parse frontmatter to extract thread context
    frontmatter, content = parse_frontmatter(raw_content)
    thread_ts = frontmatter.get("thread_ts", "")
    referenced_notif = frontmatter.get("referenced_notification", "")
    notifications_dir = Path.home() / "sharing" / "notifications"

    logger.info(
        "Response metadata",
        thread_ts=thread_ts or None,
        referenced_notification=referenced_notif or None,
    )

    # CRITICAL: Extract the original task ID from thread context
    # This is the key to preserving memory across Slack thread conversations
    # The original task ID (e.g., "task-20251126-150200") is what beads tasks are labeled with
    original_task_id = extract_original_task_id(content)
    if original_task_id:
        logger.info("Found original task ID from thread", task_id=original_task_id)

    # Extract thread context and PR references from the message
    thread_context_text, pr_refs = extract_thread_context(content)
    if pr_refs:
        logger.info("PR references found", pr_refs=pr_refs)

    # Fallback: Extract referenced notification from content if not in frontmatter
    original_notif_content = None
    if not referenced_notif:
        for line in content.split("\n"):
            if "Re:**" in line and "Notification" in line:
                # Extract timestamp from line like: **Re:** Notification `20251124-123456`
                parts = line.split("`")
                if len(parts) >= 2:
                    referenced_notif = parts[1]
                    break

    # Try to load original notification for context
    if referenced_notif:
        logger.info("Response references notification", referenced_notif=referenced_notif)
        original_file = notifications_dir / f"{referenced_notif}.md"
        if original_file.exists():
            original_notif_content = original_file.read_text()
            logger.info("Loaded original notification", file=original_file.name)

    # Extract response content
    response_lines = []
    in_message_section = False
    for line in content.split("\n"):
        if line.startswith("## Current Message"):
            in_message_section = True
            continue
        if in_message_section:
            if line.startswith("---"):
                break
            if line.strip():
                response_lines.append(line)

    response_content = "\n".join(response_lines).strip()

    if not response_content:
        logger.warning("Empty response content - nothing to process", file=message_file.name)
        # Still send a notification about the empty response
        task_id = referenced_notif if referenced_notif else message_file.stem
        create_notification_with_thread(
            notifications_dir=notifications_dir,
            task_id=task_id,
            thread_ts=thread_ts,
            content="# Response Processing Issue\n\nReceived an empty response with no content to process.\n",
        )
        return False

    logger.info("Response content extracted", preview=response_content[:100])

    # Construct task_id for search BEFORE using it
    # PRIORITY: original_task_id > referenced_notif > message_file.stem
    # original_task_id is the actual beads label, which is what we need to search for
    task_id_for_search = original_task_id or referenced_notif or message_file.stem

    # Enrich response with relevant documentation context (Phase 3 of LLM Doc Strategy ADR)
    enriched_context = enrich_task(response_content)
    if enriched_context:
        logger.info("Added documentation context enrichment", task_id=task_id_for_search)

    # Build PR context warning if we found PR references
    pr_context_warning = ""
    if pr_refs:
        pr_list = ", ".join(pr_refs)
        pr_context_warning = f"""
## \u26a0\ufe0f CRITICAL: PR/Repo Context

**This conversation is about: {pr_list}**

The user is responding in a thread that discusses the PR(s) listed above.
**You MUST work on the PR(s) mentioned above**, NOT on any other recent work.
If you cannot find or access this specific PR, say so explicitly.
"""

    # Build thread context section
    thread_section = ""
    if thread_context_text:
        thread_section = f"""
## Full Thread History

The following is the complete conversation history from this Slack thread:

{thread_context_text}
"""

    prompt = f"""# Slack Response Processing

You sent a notification that prompted a response from the user. Process their response and take appropriate action.

## Thread Context (CRITICAL)

**Task ID:** `{task_id_for_search}`
**Thread:** This is a threaded conversation - your response will be posted in the same thread.
{pr_context_warning}
**FIRST ACTION REQUIRED:** Search beads for existing context from this thread:
```bash
cd ~/beads
bd --allow-stale search "{task_id_for_search}"
# If found: bd --allow-stale show <found-id> to load full context
```

## Original Notification

{original_notif_content if original_notif_content else "*(Original notification not found - see Full Thread History below)*"}
{thread_section}
## User's Response

{response_content}

{enriched_context}
## Your Workflow

### 1. Load Beads Context (MANDATORY)
```bash
cd ~/beads
bd --allow-stale search "{task_id_for_search}"
bd --allow-stale show <found-id>  # Review what you did before
```

### 2. Understand the response
What is the user asking or telling you? Common patterns:
- Answered a question \u2192 Continue the work
- Gave feedback \u2192 Incorporate it
- Requested changes \u2192 Make the changes
- Asked a question \u2192 Research and respond

**IMPORTANT:** Work on the specific PR/task mentioned in the thread, not on any other recent work.

### 3. Take appropriate action
Execute what's needed based on the response.

### 4. Update Beads (MANDATORY)
```bash
bd --allow-stale update <task-id> --notes "User responded: [summary]. Action taken: [what you did]. Next: [pending items]."
bd --allow-stale update <task-id> --status closed  # Or keep open if more expected
```

### 5. Output your response
Print a clear summary to stdout.

## Important Notes

- You're in an ephemeral container (will exit when done)
- All work should be committed to git
- **Beads is your persistent memory** - ALWAYS check and update beads
- **DO NOT create notification files directly** - your stdout will be captured and sent as a threaded Slack reply automatically

Process this response now."""

    # Run Claude Code via shared runner module
    # This delegates timeout handling to the shared module (default: 30 minutes)
    # and provides consistent behavior across all Claude invocations
    logger.info("Starting Claude Code for response", task_id=task_id_for_search)

    # Determine task_id for notification filename
    # If we have a referenced notification, use that ID so slack-notifier threads correctly
    task_id = referenced_notif if referenced_notif else message_file.stem

    claude_result = run_claude(
        prompt=prompt,
        cwd=Path.home() / "khan",  # Start in khan directory
        capture_output=True,
    )
    logger.info(
        "Claude completed", return_code=claude_result.returncode, task_id=task_id_for_search
    )
    if claude_result.stderr:
        logger.warning("Claude stderr output", stderr=claude_result.stderr[:500])

    # Determine success/failure/timeout status
    timed_out = False
    error_message = None
    if not claude_result.success:
        if claude_result.error and "timed out" in claude_result.error.lower():
            timed_out = True
        error_message = claude_result.error

    # Calculate processing time
    elapsed_time = time.time() - start_time
    elapsed_str = f"{elapsed_time:.1f}s" if elapsed_time < 60 else f"{elapsed_time / 60:.1f}m"
    logger.info("Response processing completed", duration=elapsed_str, task_id=task_id_for_search)

    # ALWAYS create a notification - success, failure, or timeout
    response_summary = response_content[:100] + ("..." if len(response_content) > 100 else "")

    if claude_result.returncode == 0:
        # SUCCESS: Include Claude's response
        logger.info("Response processed successfully", task_id=task_id_for_search)

        claude_output = claude_result.stdout.strip() if claude_result.stdout else ""
        if not claude_output:
            logger.warning(
                "Claude returned empty output despite success return code",
                task_id=task_id_for_search,
            )
            claude_output = "*Claude completed but produced no output. The response may have been processed - check GitHub for any updates.*"

        notification_content = f"""# Response Processed

**Your message:** {response_summary}
**Processing time:** {elapsed_str}
**Status:** Success

## Response

{claude_output}

---
*Generated by jib incoming-processor*
"""
    elif timed_out:
        # TIMEOUT: Notify user with helpful context
        logger.error(
            "Response processing timed out", task_id=task_id_for_search, duration=elapsed_str
        )
        partial_output = ""
        if claude_result.stdout:
            partial_output = (
                f"\n\n**Partial output before timeout:**\n{claude_result.stdout[:1000]}"
            )

        notification_content = f"""# Response Processing Timed Out

**Your message:** {response_summary}
**Processing time:** {elapsed_str} (timeout)
**Status:** {error_message or "Timed out"}

The response took too long to process.
{partial_output}

**What you can do:**
- Check GitHub for any updates that may have been made
- Try rephrasing your request more concisely
- Retry if the task was interrupted

---
*Generated by jib incoming-processor*
"""
    else:
        # FAILURE: Include error details
        stderr_output = claude_result.stderr[:500] if claude_result.stderr else "None"
        stdout_output = claude_result.stdout[:500] if claude_result.stdout else "None"

        logger.error(
            "Response processing failed",
            task_id=task_id_for_search,
            return_code=claude_result.returncode,
            error=error_message,
        )

        notification_content = f"""# Response Processing Failed

**Your message:** {response_summary}
**Processing time:** {elapsed_str}
**Status:** Failed (exit code: {claude_result.returncode})

## Error Details

{error_message or "Claude exited with non-zero status"}

**Stderr:** {stderr_output}

**Stdout (partial):** {stdout_output}

**What you can do:**
- Check the logs at `~/sharing/logs/incoming-processor.log`
- Check GitHub for any updates
- Retry the message

---
*Generated by jib incoming-processor*
"""

    # Write the notification
    notification_file = create_notification_with_thread(
        notifications_dir=notifications_dir,
        task_id=task_id,
        thread_ts=thread_ts,
        content=notification_content,
    )
    logger.info("Notification created", file=notification_file.name, thread_ts=thread_ts or None)

    return claude_result.returncode == 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: incoming-processor.py <message-file>")
        return 1

    message_file = Path(sys.argv[1])
    logger.info("Starting incoming-processor", file=str(message_file))

    # Refresh GitHub authentication to handle token expiration in long-running containers
    # This ensures both gh CLI (via GITHUB_TOKEN env var) and GitHub MCP stay authenticated
    try:
        from github_auth import refresh_all_auth, start_token_watcher_daemon
        env_ok, mcp_ok = refresh_all_auth()
        if env_ok or mcp_ok:
            logger.info("GitHub authentication refreshed", env=env_ok, mcp=mcp_ok)
        # Start background watcher for containers that may run >1hr
        start_token_watcher_daemon(interval=300)  # Check every 5 minutes
    except Exception as e:
        logger.warning("Failed to refresh GitHub auth - continuing anyway", error=str(e))

    if not message_file.exists():
        logger.error("File not found", file=str(message_file))
        return 1

    # Determine message type based on parent directory
    if "incoming" in str(message_file.parent):
        logger.info("Processing incoming task", file=message_file.name)
        success = process_task(message_file)
    elif "responses" in str(message_file.parent):
        logger.info("Processing response to previous notification", file=message_file.name)
        success = process_response(message_file)
    else:
        logger.error("Unknown message type", file=str(message_file))
        return 1

    logger.info("Processing complete", success=success)

    # Stop background services before exiting (PostgreSQL, Redis keep container alive)
    # This ensures ephemeral jib --exec containers exit cleanly
    logger.info("Stopping background services")
    subprocess.run(["service", "postgresql", "stop"], check=False, capture_output=True)
    subprocess.run(["service", "redis-server", "stop"], check=False, capture_output=True)

    logger.info("Incoming processor complete", success=success)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
