# jib Container Scripts

Utility scripts that run inside the jib container for analysis and automation.

## Available Scripts

### analyze-sprint.py

Analyzes your currently assigned JIRA tickets and suggests next steps.

**Features:**
- Groups tickets by status (In Progress, In Review, Blocked, To Do)
- Suggests next steps for each ticket based on status and context
- Identifies potential blockers from ticket descriptions
- Recommends which backlog tickets to pull in next
- Scores backlog tickets by priority, clarity, and recent activity
- Sends analysis as Slack notification

**Usage:**

```bash
# From host
cd ~/khan/james-in-a-box
bin/jib --exec /home/jwies/khan/james-in-a-box/jib-container/scripts/analyze-sprint.py

# From inside container
~/khan/james-in-a-box/jib-container/scripts/analyze-sprint.py
```

**Prerequisites:**
- JIRA sync must be configured and run at least once
- Tickets must be synced to `~/context-sync/jira/`
- Git config must have your name/email (used to identify assigned tickets)

**Output:**
- Slack notification with summary (top-level)
- Detailed analysis in thread:
  - Tickets grouped by status
  - Next steps for each ticket
  - Suggested backlog tickets to pull in
  - Strategic recommendations

**Example notification:**

```
📊 Sprint Ticket Analysis

Assigned Tickets: 8 total, 5 in active work
Backlog Suggestions: 5 tickets ready to pull in

📄 Full analysis in thread below
```

**Detailed thread includes:**
- 🚀 In Progress (with next steps)
- 👀 In Review (with action items)
- ⚠️ Blocked or Needs Attention
- 📝 To Do
- 💼 Suggested Tickets to Pull In (scored by priority and readiness)

### comment-pr-helper.py

Posts comments on GitHub PRs and sends Slack notifications. Use this instead of raw `gh pr comment` to ensure consistent formatting and Slack notifications.

**Features:**
- Wraps `gh pr comment` with consistent error handling
- Automatically adds jib signature to comments
- Sends Slack notification with comment details
- Supports task ID for Slack thread correlation

**Usage:**

```bash
# Basic usage - comment on a PR
comment-pr-helper.py --pr 123 --body "This looks good!"

# Comment from a file
comment-pr-helper.py --pr 123 --body-file review-comments.md

# Skip Slack notification (use when output will be captured)
comment-pr-helper.py --pr 123 --body "Comment" --no-notify

# Don't add jib signature
comment-pr-helper.py --pr 123 --body "Comment" --no-sign

# With task ID for thread correlation
comment-pr-helper.py --pr 123 --body "Done!" --task-id my-task-123
```

**Options:**
- `--pr, -p`: PR number to comment on (required)
- `--body, -b`: Comment body (markdown supported)
- `--body-file, -f`: Read comment body from file
- `--no-notify`: Skip Slack notification
- `--no-sign`: Don't add jib signature
- `--task-id, -t`: Task ID for Slack thread correlation

**Important:** Always use `--no-notify` when your stdout will be captured and sent as a threaded Slack notification automatically (e.g., from task runners).

### create-pr-helper.py

Creates GitHub PRs with proper formatting and Slack notifications. See main CLAUDE.md for detailed usage.

### discover-tests.py

Discovers test frameworks and test commands for a repository.

## Creating New Scripts

When adding new scripts to this directory:

1. **Make executable**: `chmod +x script-name.py`
2. **Add shebang**: `#!/usr/bin/env python3`
3. **Document**: Update this README
4. **Usage pattern**: Support both host (`bin/jib --exec`) and container execution
5. **Notifications**: Send results via Slack (write to `~/sharing/notifications/`)

**Script template:**

```python
#!/usr/bin/env python3
"""
Script description

Usage:
  # From host
  bin/jib --exec /home/jwies/khan/james-in-a-box/jib-container/scripts/your-script.py

  # From inside container
  ~/khan/james-in-a-box/jib-container/scripts/your-script.py
"""

from pathlib import Path
from datetime import datetime


class YourAnalyzer:
    def __init__(self):
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)

    def generate_notification(self, content: str):
        """Send notification via Slack."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Summary (top-level Slack message)
        summary_file = self.notifications_dir / f"{timestamp}-your-analysis.md"
        summary_file.write_text(f"# Summary\n\n{content[:200]}")

        # Detail (threaded reply)
        detail_file = self.notifications_dir / f"RESPONSE-{timestamp}-your-analysis.md"
        detail_file.write_text(content)

    def run(self):
        # Your logic here
        pass


def main():
    analyzer = YourAnalyzer()
    return analyzer.run()


if __name__ == "__main__":
    exit(main())
```

## Troubleshooting

**"No tickets found"**:
- Run JIRA sync first: `cd ~/khan/james-in-a-box/host-services/context-sync && make sync-jira`
- Check `~/context-sync/jira/` for ticket files

**"No tickets assigned to you"**:
- Verify git config has your name: `git config user.name`
- Verify git config has your email: `git config user.email`
- Check that tickets in JIRA are actually assigned to you

**Script errors inside container**:
- Check script permissions: `ls -la ~/khan/james-in-a-box/jib-container/scripts/`
- Make executable if needed: `chmod +x script.py`
- Check Python syntax: `python3 -m py_compile script.py`
