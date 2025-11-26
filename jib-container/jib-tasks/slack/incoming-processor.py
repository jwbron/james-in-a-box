#!/usr/bin/env python3
"""
Incoming Message Processor

Processes a single incoming message or response from Slack.
Called by slack-receiver via `jib --exec` after writing a message file.

IMPORTANT: Preserves thread context from incoming messages.
The incoming message file contains YAML frontmatter with thread_ts,
which is propagated to the response notification for proper Slack threading.

Usage:
  python3 incoming-processor.py <message-file>
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Parse YAML frontmatter from file content.

    Returns:
        Tuple of (metadata dict, content without frontmatter)
    """
    metadata = {}

    # Check for YAML frontmatter (starts with ---)
    if not content.startswith('---'):
        return metadata, content

    # Find the closing ---
    lines = content.split('\n')
    end_idx = -1
    for i, line in enumerate(lines[1:], start=1):  # Skip first ---
        if line.strip() == '---':
            end_idx = i
            break

    if end_idx == -1:
        # No closing ---, treat as no frontmatter
        return metadata, content

    # Parse the frontmatter (simple key: value parsing)
    frontmatter_lines = lines[1:end_idx]
    for line in frontmatter_lines:
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip().strip('"\'')  # Remove quotes
            if value:  # Only add non-empty values
                metadata[key] = value

    # Return content without frontmatter
    remaining_content = '\n'.join(lines[end_idx + 1:]).strip()
    return metadata, remaining_content


def create_notification_with_thread(
    notifications_dir: Path,
    task_id: str,
    thread_ts: str,
    content: str
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

    frontmatter = '\n'.join(frontmatter_lines)
    full_content = frontmatter + content

    notification_file.write_text(full_content)
    return notification_file


def process_task(message_file: Path):
    """Process an incoming task from Slack using Claude Code."""
    print(f"📋 Processing task: {message_file.name}")

    # Read full message content
    raw_content = message_file.read_text()

    # Parse frontmatter to extract thread context
    frontmatter, content = parse_frontmatter(raw_content)
    thread_ts = frontmatter.get('thread_ts', '')
    original_task_id = frontmatter.get('task_id', message_file.stem)

    if thread_ts:
        print(f"📧 Thread context: {thread_ts}")

    # Extract task description (after "## Current Message" header)
    task_lines = []
    in_message_section = False
    for line in content.split('\n'):
        if line.startswith('## Current Message'):
            in_message_section = True
            continue
        if in_message_section:
            if line.startswith('---'):
                break
            if line.strip():
                task_lines.append(line)

    task_content = '\n'.join(task_lines).strip()

    if not task_content:
        print("⚠️ Empty task content")
        return False

    print(f"Task: {task_content[:100]}...")

    # Build thread context section if available
    thread_context_section = ""
    if frontmatter.get('thread_ts'):
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
**Received:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{thread_context_section}

## Task from User

{task_content}

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
   - Use the PR helper: `~/khan/james-in-a-box/jib-container/scripts/create-pr-helper.py`
   - Run: `create-pr-helper.py --auto --reviewer jwiesebron --no-notify`
   - Or with custom title: `create-pr-helper.py --title "Your PR title" --body "Description" --no-notify`
   - The script will push the branch and create a PR automatically
   - IMPORTANT: Always use `--no-notify` flag - your output will be captured and threaded correctly

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
- The PR helper automatically requests review from @jwiesebron
- **DO NOT create notification files directly** - your stdout will be captured and sent as a threaded Slack notification automatically

Process this task now."""

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    # Important: Start in ~/khan/ and use bypass permissions
    try:
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions"],
            input=prompt,
            text=True,
            capture_output=True,  # Capture output to create notification
            timeout=600,  # 10 minute timeout
            cwd=str(Path.home() / "khan")  # Start in khan directory
        )

        if result.returncode == 0:
            print(f"✅ Task processed successfully")

            # Create notification with Claude's response
            # IMPORTANT: Include thread_ts in frontmatter for proper Slack threading
            notifications_dir = Path.home() / "sharing" / "notifications"
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

            notification_content = f"""# Task Response - {timestamp}

**Task:** {task_content[:100]}{'...' if len(task_content) > 100 else ''}

## Claude's Response

{result.stdout}

---
*Generated by james-in-a-box incoming processor*
"""

            # Use helper function to create notification with thread context
            notification_file = create_notification_with_thread(
                notifications_dir=notifications_dir,
                task_id=original_task_id,
                thread_ts=thread_ts,
                content=notification_content
            )
            print(f"📬 Notification created: {notification_file.name}")
            if thread_ts:
                print(f"📧 Thread context preserved: {thread_ts}")

            return True
        else:
            print(f"⚠️ Claude exited with code {result.returncode}")
            print(f"Error output: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("⚠️ Task processing timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"❌ Error running Claude: {e}")
        return False


def process_response(message_file: Path):
    """Process a user's response to a previous notification using Claude Code."""
    print(f"💬 Processing response: {message_file.name}")

    # Read response content
    raw_content = message_file.read_text()

    # Parse frontmatter to extract thread context
    frontmatter, content = parse_frontmatter(raw_content)
    thread_ts = frontmatter.get('thread_ts', '')
    referenced_notif = frontmatter.get('referenced_notification', '')

    if thread_ts:
        print(f"📧 Thread context: {thread_ts}")

    # Fallback: Extract referenced notification from content if not in frontmatter
    original_notif_content = None
    if not referenced_notif:
        for line in content.split('\n'):
            if 'Re:**' in line and 'Notification' in line:
                # Extract timestamp from line like: **Re:** Notification `20251124-123456`
                parts = line.split('`')
                if len(parts) >= 2:
                    referenced_notif = parts[1]
                    break

    # Try to load original notification for context
    if referenced_notif:
        print(f"Response references: {referenced_notif}")
        notifications_dir = Path.home() / "sharing" / "notifications"
        original_file = notifications_dir / f"{referenced_notif}.md"
        if original_file.exists():
            original_notif_content = original_file.read_text()

    # Extract response content
    response_lines = []
    in_message_section = False
    for line in content.split('\n'):
        if line.startswith('## Current Message'):
            in_message_section = True
            continue
        if in_message_section:
            if line.startswith('---'):
                break
            if line.strip():
                response_lines.append(line)

    response_content = '\n'.join(response_lines).strip()

    if not response_content:
        print("⚠️ Empty response content")
        return False

    # Construct prompt for Claude with full context
    task_id_for_search = referenced_notif if referenced_notif else message_file.stem
    prompt = f"""# Slack Response Processing

You sent a notification that prompted a response from the user. Process their response and take appropriate action.

## Thread Context (CRITICAL)

**Task ID:** `{task_id_for_search}`
**Thread:** This is a threaded conversation - your response will be posted in the same thread.

**FIRST ACTION REQUIRED:** Search beads for existing context from this thread:
```bash
cd ~/beads
bd --allow-stale search "{task_id_for_search}"
# If found: bd --allow-stale show <found-id> to load full context
```

## Original Notification

{original_notif_content if original_notif_content else "*(Original notification not found)*"}

## User's Response

{response_content}

## Your Workflow

### 1. Load Beads Context (MANDATORY)
```bash
cd ~/beads
bd --allow-stale search "{task_id_for_search}"
bd --allow-stale show <found-id>  # Review what you did before
```

### 2. Understand the response
What is the user asking or telling you? Common patterns:
- Answered a question → Continue the work
- Gave feedback → Incorporate it
- Requested changes → Make the changes
- Asked a question → Research and respond

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

    # Run Claude Code via stdin (not --print which creates restricted session)
    # This allows full access to tools and filesystem
    # Important: Start in ~/khan/ and use bypass permissions
    try:
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions"],
            input=prompt,
            text=True,
            capture_output=True,  # Capture output to create notification
            timeout=600,  # 10 minute timeout
            cwd=str(Path.home() / "khan")  # Start in khan directory
        )

        if result.returncode == 0:
            print(f"✅ Response processed successfully")

            # Create notification with Claude's response
            # IMPORTANT: Include thread_ts in frontmatter for proper Slack threading
            notifications_dir = Path.home() / "sharing" / "notifications"
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

            # Determine task_id for notification filename
            # If we have a referenced notification, use that ID so slack-notifier threads correctly
            task_id = referenced_notif if referenced_notif else message_file.stem

            notification_content = f"""# Response Processed - {timestamp}

**Referenced Notification:** {referenced_notif if referenced_notif else 'None'}

## Claude's Response

{result.stdout}

---
*Generated by james-in-a-box incoming processor*
"""

            # Use helper function to create notification with thread context
            notification_file = create_notification_with_thread(
                notifications_dir=notifications_dir,
                task_id=task_id,
                thread_ts=thread_ts,
                content=notification_content
            )
            print(f"📬 Notification created: {notification_file.name}")
            if thread_ts:
                print(f"📧 Thread context preserved: {thread_ts}")

            return True
        else:
            print(f"⚠️ Claude exited with code {result.returncode}")
            print(f"Error output: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("⚠️ Response processing timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"❌ Error running Claude: {e}")
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: incoming-processor.py <message-file>", file=sys.stderr)
        return 1

    message_file = Path(sys.argv[1])

    if not message_file.exists():
        print(f"Error: File not found: {message_file}", file=sys.stderr)
        return 1

    # Determine message type based on parent directory
    if 'incoming' in str(message_file.parent):
        success = process_task(message_file)
    elif 'responses' in str(message_file.parent):
        success = process_response(message_file)
    else:
        print(f"Error: Unknown message type for {message_file}", file=sys.stderr)
        return 1

    # Stop background services before exiting (PostgreSQL, Redis keep container alive)
    # This ensures ephemeral jib --exec containers exit cleanly
    subprocess.run(["service", "postgresql", "stop"], capture_output=True)
    subprocess.run(["service", "redis-server", "stop"], capture_output=True)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
