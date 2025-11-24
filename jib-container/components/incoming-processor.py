#!/usr/bin/env python3
"""
Incoming Message Processor

Processes a single incoming message or response from Slack.
Called by slack-receiver via `jib --exec` after writing a message file.

Usage:
  python3 incoming-processor.py <message-file>
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime


def process_task(message_file: Path):
    """Process an incoming task from Slack."""
    print(f"📋 Processing task: {message_file.name}")

    # Read message content
    content = message_file.read_text()

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

    # Create acknowledgment notification
    notifications_dir = Path.home() / "sharing" / "notifications"
    notifications_dir.mkdir(parents=True, exist_ok=True)

    ack_file = notifications_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-task-received.md"
    ack_file.write_text(f"""# 🎯 Task Received from Slack

**File:** `{message_file.name}`
**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Task Description

{task_content}

---

**Status:** Acknowledged and ready to begin
**Next:** Task will be processed

---
📨 *Delivered via Slack → incoming/ → Claude*
""")

    print(f"✅ Task acknowledged: {ack_file.name}")

    # TODO: Process task with Claude
    # For now, just acknowledge receipt
    # Future: Integrate with Claude CLI or agent

    return True


def process_response(message_file: Path):
    """Process a response to Claude's notification."""
    print(f"💬 Processing response: {message_file.name}")

    # Read response content
    content = message_file.read_text()

    # Extract referenced notification if present
    referenced_notif = None
    for line in content.split('\n'):
        if 'Re:**' in line and 'Notification' in line:
            # Extract timestamp from line like: **Re:** Notification `20251124-123456`
            parts = line.split('`')
            if len(parts) >= 2:
                referenced_notif = parts[1]
                break

    if referenced_notif:
        print(f"Response references: {referenced_notif}")

        # Create response link in notifications
        notifications_dir = Path.home() / "sharing" / "notifications"
        response_link = notifications_dir / f"RESPONSE-{referenced_notif}.md"
        response_link.write_text(content)
        print(f"✅ Response linked: {response_link.name}")
    else:
        print("⚠️ Response does not reference specific notification")

    # Create receipt notification
    notifications_dir = Path.home() / "sharing" / "notifications"
    receipt_file = notifications_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-response-received.md"

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

    receipt_file.write_text(f"""# 💬 Response Received from Slack

**File:** `{message_file.name}`
**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{f'**Re:** `{referenced_notif}`' if referenced_notif else ''}

## Response Content

{response_content}

---

**Status:** Response available for review
**Location:** `responses/{message_file.name}`
{f'**Linked:** `notifications/RESPONSE-{referenced_notif}.md`' if referenced_notif else ''}

---
📨 *Delivered via Slack → responses/ → Claude*
""")

    print(f"✅ Response processed: {receipt_file.name}")
    return True


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

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
