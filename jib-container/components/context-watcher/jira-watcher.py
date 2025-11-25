#!/usr/bin/env python3
"""
JIRA Watcher - Monitors JIRA tickets and sends proactive notifications

Detects new or updated JIRA tickets assigned to you, analyzes requirements,
extracts action items, and sends summaries via Slack notifications.

Uses Claude Code to intelligently analyze tickets and create action plans.

Scope: Only processes tickets assigned to you
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime


def main():
    """Run one-shot JIRA ticket analysis using Claude Code."""
    print("🔍 JIRA Watcher - Analyzing assigned tickets...")

    jira_dir = Path.home() / "context-sync" / "jira"
    state_file = Path.home() / "sharing" / "tracking" / "jira-watcher-state.json"

    if not jira_dir.exists():
        print("JIRA directory not found - skipping watch")
        return 0

    # Load state to track processed tickets
    processed_tickets = {}
    if state_file.exists():
        try:
            with state_file.open() as f:
                data = json.load(f)
                processed_tickets = data.get('processed', {})
        except (json.JSONDecodeError, IOError) as e:
            print(f'Warning: Failed to load state: {e}')

    # Collect new or updated tickets
    new_or_updated = []
    for ticket_file in jira_dir.glob("*.md"):
        try:
            # Get file modification time
            mtime = ticket_file.stat().st_mtime
            mtime_str = datetime.fromtimestamp(mtime).isoformat()
            ticket_path = str(ticket_file)

            # Check if new or updated
            if ticket_path not in processed_tickets or processed_tickets[ticket_path] != mtime_str:
                content = ticket_file.read_text()
                is_new = ticket_path not in processed_tickets

                new_or_updated.append({
                    'file': ticket_file,
                    'path': ticket_path,
                    'mtime': mtime_str,
                    'is_new': is_new,
                    'content': content
                })
        except Exception as e:
            print(f"Error processing {ticket_file}: {e}")

    if not new_or_updated:
        print("No new or updated tickets found")
        return 0

    print(f"Found {len(new_or_updated)} new or updated ticket(s)")

    # Construct prompt for Claude
    tickets_summary = []
    for t in new_or_updated:
        status = "New" if t['is_new'] else "Updated"
        tickets_summary.append(f"**{status}**: {t['file'].name}")

    prompt = f"""# JIRA Ticket Analysis

You are analyzing JIRA tickets that have been assigned to you. Your goal is to understand requirements, extract action items, assess scope, and create actionable plans.

## Summary

{len(new_or_updated)} ticket(s) require attention:
{chr(10).join('- ' + s for s in tickets_summary)}

## Full Ticket Details

"""

    for t in new_or_updated:
        status = "NEW TICKET" if t['is_new'] else "UPDATED TICKET"
        prompt += f"""
### {status}: {t['file'].name}

**File:** `{t['file']}`

**Content:**
```markdown
{t['content'][:2000]}{"..." if len(t['content']) > 2000 else ""}
```

---

"""

    prompt += """
## Your Workflow (per ADR)

For each ticket:

1. **Analyze the ticket**:
   - Parse title, type, status, priority, description
   - Extract acceptance criteria and key requirements
   - Assess scope and complexity
   - Identify dependencies, risks, and blockers
   - Extract actionable items

2. **Track in Beads**:
   - Create Beads task: `bd add "<ticket-key>: <title>" --tags <ticket-key> jira <type>`
   - Add notes with: status, priority, scope estimate, URL
   - For NEW tickets only (not updates)

3. **Create notification** to `~/sharing/notifications/`:
   - Use format: `YYYYMMDD-HHMMSS-jira-{new-ticket|ticket-updated}-<ticket-key>.md`
   - Include:
     - Title and metadata (type, status, priority, URL, Beads task ID if created)
     - Quick summary of what the ticket is about
     - Estimated scope (small/medium/large)
     - Key requirements and acceptance criteria
     - Extracted action items
     - Dependencies/blockers if mentioned
     - Potential risks if mentioned
     - Suggested next steps for implementation
   - Keep it concise but actionable

4. **Update state file**:
   - Save ticket path and mtime to `~/sharing/tracking/jira-watcher-state.json`
   - This prevents re-processing unchanged tickets

## Important Notes

- You're in an ephemeral container
- Tickets are synced to ~/context-sync/jira/
- Focus on tickets assigned to YOU only
- Use Beads to track work across sessions
- Notifications will be sent to Slack automatically

Analyze these tickets now and take appropriate action."""

    # Run Claude Code
    try:
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=False,
            text=True,
            timeout=900  # 15 minute timeout
        )

        if result.returncode == 0:
            print("✅ Ticket analysis complete")

            # Update state file with processed tickets
            for t in new_or_updated:
                processed_tickets[t['path']] = t['mtime']

            state_file.parent.mkdir(parents=True, exist_ok=True)
            with state_file.open('w') as f:
                json.dump({'processed': processed_tickets}, f, indent=2)

            return 0
        else:
            print(f"⚠️  Claude exited with code {result.returncode}")
            return 1

    except subprocess.TimeoutExpired:
        print("⚠️ Analysis timed out after 15 minutes")
        return 1
    except Exception as e:
        print(f"❌ Error running Claude: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())