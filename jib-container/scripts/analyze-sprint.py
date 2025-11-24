#!/usr/bin/env python3
"""
Sprint Ticket Analyzer

Analyzes tickets in the active sprint and suggests:
- Next steps for currently assigned tickets
- Which tickets to pull in from backlog

Usage:
  # From host
  bin/jib --exec /home/jwies/khan/james-in-a-box/jib-container/scripts/analyze-sprint.py

  # From inside container
  ~/khan/james-in-a-box/jib-container/scripts/analyze-sprint.py
"""

import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class SprintAnalyzer:
    """Analyzes sprint tickets and provides recommendations."""

    def __init__(self):
        self.jira_dir = Path.home() / "context-sync" / "jira"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.notifications_dir.mkdir(parents=True, exist_ok=True)

    def parse_ticket_file(self, ticket_file: Path) -> Optional[Dict]:
        """Parse a JIRA ticket markdown file."""
        try:
            content = ticket_file.read_text()

            ticket = {
                'file': ticket_file,
                'key': '',
                'title': '',
                'status': '',
                'assignee': '',
                'priority': '',
                'type': '',
                'labels': [],
                'description': '',
                'has_acceptance_criteria': False,
                'comments_count': 0,
                'updated': ''
            }

            lines = content.split('\n')

            # Extract key and title from first line (# INFRA-1234: Title)
            first_line = lines[0] if lines else ''
            title_match = re.match(r'^#\s+([A-Z]+-\d+):\s+(.+)$', first_line)
            if title_match:
                ticket['key'] = title_match.group(1)
                ticket['title'] = title_match.group(2)

            # Extract metadata
            for line in lines:
                if line.startswith('**Status:**'):
                    ticket['status'] = line.replace('**Status:**', '').strip()
                elif line.startswith('**Assignee:**'):
                    ticket['assignee'] = line.replace('**Assignee:**', '').strip()
                elif line.startswith('**Priority:**'):
                    ticket['priority'] = line.replace('**Priority:**', '').strip()
                elif line.startswith('**Type:**'):
                    ticket['type'] = line.replace('**Type:**', '').strip()
                elif line.startswith('**Labels:**'):
                    labels_str = line.replace('**Labels:**', '').strip()
                    ticket['labels'] = [l.strip() for l in labels_str.split(',') if l.strip()]
                elif line.startswith('**Updated:**'):
                    ticket['updated'] = line.replace('**Updated:**', '').strip()

            # Check for acceptance criteria
            if 'acceptance criteria' in content.lower() or '- [ ]' in content:
                ticket['has_acceptance_criteria'] = True

            # Count comments
            ticket['comments_count'] = content.count('### Comment ')

            # Extract description section
            desc_start = content.find('## Description')
            if desc_start != -1:
                desc_end = content.find('\n## ', desc_start + 1)
                if desc_end == -1:
                    desc_end = len(content)
                ticket['description'] = content[desc_start:desc_end].strip()

            return ticket

        except Exception as e:
            print(f"Error parsing {ticket_file}: {e}")
            return None

    def is_assigned_to_me(self, ticket: Dict) -> bool:
        """Check if ticket is assigned to current user."""
        assignee = ticket.get('assignee', '').lower()

        # Get user info from environment or git config
        try:
            result = subprocess.run(
                ['git', 'config', 'user.name'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                git_name = result.stdout.strip().lower()
                if git_name in assignee:
                    return True

            result = subprocess.run(
                ['git', 'config', 'user.email'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                git_email = result.stdout.strip().lower()
                # Extract name from email
                email_name = git_email.split('@')[0].replace('.', ' ')
                if email_name in assignee:
                    return True
        except:
            pass

        return False

    def is_in_active_sprint(self, ticket: Dict) -> bool:
        """Check if ticket is in active sprint (heuristic based on labels/status)."""
        # Check labels for sprint indicators
        labels = [l.lower() for l in ticket.get('labels', [])]
        if any('sprint' in label for label in labels):
            return True

        # Active statuses typically indicate sprint work
        status = ticket.get('status', '').lower()
        active_statuses = ['in progress', 'in review', 'ready for review', 'testing']
        if any(s in status for s in active_statuses):
            return True

        return False

    def analyze_ticket(self, ticket: Dict) -> Dict:
        """Analyze a ticket and suggest next steps."""
        analysis = {
            'priority_score': 0,
            'next_steps': [],
            'blockers': [],
            'suggestions': []
        }

        status = ticket.get('status', '').lower()
        priority = ticket.get('priority', '').lower()

        # Priority scoring
        if 'critical' in priority or 'highest' in priority:
            analysis['priority_score'] = 5
        elif 'high' in priority:
            analysis['priority_score'] = 4
        elif 'medium' in priority:
            analysis['priority_score'] = 3
        else:
            analysis['priority_score'] = 2

        # Status-based next steps
        if 'to do' in status or 'open' in status or 'backlog' in status:
            analysis['next_steps'].append("Start work on this ticket")
            if not ticket.get('has_acceptance_criteria'):
                analysis['suggestions'].append("Add acceptance criteria before starting")

        elif 'in progress' in status:
            if ticket.get('comments_count', 0) == 0:
                analysis['suggestions'].append("Add progress update in comments")
            analysis['next_steps'].append("Continue implementation")
            analysis['next_steps'].append("Add tests for new functionality")

        elif 'review' in status:
            analysis['next_steps'].append("Address review comments")
            analysis['next_steps'].append("Request re-review when ready")

        elif 'testing' in status:
            analysis['next_steps'].append("Verify tests pass")
            analysis['next_steps'].append("Test in staging environment")

        # Type-based suggestions
        ticket_type = ticket.get('type', '').lower()
        if 'epic' in ticket_type:
            analysis['suggestions'].append("Break down into smaller sub-tasks")

        # Check for potential blockers
        description = ticket.get('description', '').lower()
        blocker_keywords = ['blocked', 'waiting', 'depends on', 'requires', 'need']
        for keyword in blocker_keywords:
            if keyword in description:
                analysis['blockers'].append(f"Potential blocker: '{keyword}' mentioned in description")

        return analysis

    def get_backlog_suggestions(self, all_tickets: List[Dict]) -> List[Dict]:
        """Suggest which backlog tickets to pull into sprint."""
        backlog = []

        for ticket in all_tickets:
            status = ticket.get('status', '').lower()

            # Skip tickets already in progress
            if status in ['in progress', 'in review', 'testing', 'done']:
                continue

            # Skip unassigned tickets (not ready for current user)
            if not self.is_assigned_to_me(ticket):
                continue

            # Score the ticket
            score = 0

            # Priority weight
            priority = ticket.get('priority', '').lower()
            if 'critical' in priority or 'highest' in priority:
                score += 10
            elif 'high' in priority:
                score += 7
            elif 'medium' in priority:
                score += 4

            # Completeness weight (tickets with acceptance criteria are better defined)
            if ticket.get('has_acceptance_criteria'):
                score += 3

            # Recent activity weight
            if ticket.get('comments_count', 0) > 0:
                score += 2

            # Type weight (prefer tasks over epics)
            ticket_type = ticket.get('type', '').lower()
            if 'story' in ticket_type or 'task' in ticket_type:
                score += 3
            elif 'bug' in ticket_type:
                score += 5  # Bugs often need quick attention

            backlog.append({
                'ticket': ticket,
                'score': score
            })

        # Sort by score descending
        backlog.sort(key=lambda x: -x['score'])

        return backlog[:5]  # Top 5 suggestions

    def generate_notification(self, assigned_tickets: List[Dict], backlog_suggestions: List[Dict]):
        """Generate Slack notification with sprint analysis."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        task_id = f"{timestamp}-sprint-analysis"

        # Create summary notification
        summary_file = self.notifications_dir / f"{task_id}.md"
        active_count = len([t for t in assigned_tickets if self.is_in_active_sprint(t)])

        summary = f"""# 📊 Sprint Ticket Analysis

**Assigned Tickets**: {len(assigned_tickets)} total, {active_count} in active work
**Backlog Suggestions**: {len(backlog_suggestions)} tickets ready to pull in

📄 Full analysis in thread below
"""

        summary_file.write_text(summary)

        # Create detailed analysis
        detail_file = self.notifications_dir / f"RESPONSE-{task_id}.md"
        detail_content = f"""# 📊 Sprint Ticket Analysis

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Source**: ~/context-sync/jira/

---

## 🎯 Currently Assigned Tickets

"""

        # Group tickets by status
        in_progress = []
        in_review = []
        blocked = []
        todo = []

        for ticket in assigned_tickets:
            analysis = self.analyze_ticket(ticket)

            ticket_data = {
                'ticket': ticket,
                'analysis': analysis
            }

            status = ticket.get('status', '').lower()
            if 'progress' in status:
                in_progress.append(ticket_data)
            elif 'review' in status:
                in_review.append(ticket_data)
            elif 'blocked' in status or analysis['blockers']:
                blocked.append(ticket_data)
            else:
                todo.append(ticket_data)

        # In Progress section
        if in_progress:
            detail_content += "### 🚀 In Progress\n\n"
            for item in in_progress:
                ticket = item['ticket']
                analysis = item['analysis']

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"
                detail_content += f"- Status: {ticket.get('status', 'Unknown')}\n"

                if analysis['next_steps']:
                    detail_content += "- **Next Steps**:\n"
                    for step in analysis['next_steps']:
                        detail_content += f"  - {step}\n"

                if analysis['suggestions']:
                    detail_content += "- **Suggestions**:\n"
                    for suggestion in analysis['suggestions']:
                        detail_content += f"  - {suggestion}\n"

                detail_content += "\n"

        # In Review section
        if in_review:
            detail_content += "### 👀 In Review\n\n"
            for item in in_review:
                ticket = item['ticket']
                analysis = item['analysis']

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"

                if analysis['next_steps']:
                    for step in analysis['next_steps']:
                        detail_content += f"- {step}\n"

                detail_content += "\n"

        # Blocked section
        if blocked:
            detail_content += "### ⚠️ Blocked or Needs Attention\n\n"
            for item in blocked:
                ticket = item['ticket']
                analysis = item['analysis']

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"
                detail_content += f"- Status: {ticket.get('status', 'Unknown')}\n"

                if analysis['blockers']:
                    detail_content += "- **Blockers**:\n"
                    for blocker in analysis['blockers']:
                        detail_content += f"  - {blocker}\n"

                detail_content += "\n"

        # To Do section
        if todo:
            detail_content += "### 📝 To Do\n\n"
            for item in todo:
                ticket = item['ticket']
                analysis = item['analysis']

                detail_content += f"**{ticket['key']}: {ticket['title']}**\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"

                if analysis['suggestions']:
                    for suggestion in analysis['suggestions']:
                        detail_content += f"- 💡 {suggestion}\n"

                detail_content += "\n"

        # Backlog suggestions section
        if backlog_suggestions:
            detail_content += "\n## 💼 Suggested Tickets to Pull In\n\n"
            detail_content += "*Based on priority, clarity, and recent activity*\n\n"

            for item in backlog_suggestions:
                ticket = item['ticket']
                score = item['score']

                detail_content += f"**{ticket['key']}: {ticket['title']}** (Score: {score})\n"
                detail_content += f"- Priority: {ticket.get('priority', 'Unknown')}\n"
                detail_content += f"- Type: {ticket.get('type', 'Unknown')}\n"
                detail_content += f"- Status: {ticket.get('status', 'Unknown')}\n"

                if ticket.get('has_acceptance_criteria'):
                    detail_content += "- ✓ Has acceptance criteria\n"

                if ticket.get('comments_count', 0) > 0:
                    detail_content += f"- {ticket['comments_count']} comment(s) - recent activity\n"

                detail_content += "\n"

        # Add recommendations
        detail_content += """
---

## 📋 Recommendations

1. **Focus on In Progress**: Complete current work before starting new tickets
2. **Unblock**: Address blocked tickets to maintain velocity
3. **Review Ready**: Prioritize tickets in review to unblock teammates
4. **Pull Strategically**: Use suggested tickets based on priority and clarity

---

📅 {date}
🔄 Run again with: bin/jib --exec ~/khan/james-in-a-box/jib-container/scripts/analyze-sprint.py
""".format(date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        detail_file.write_text(detail_content)

        print(f"✓ Sprint analysis complete!")
        print(f"  Summary: {summary_file}")
        print(f"  Detail: {detail_file}")

    def run(self):
        """Main analysis workflow."""
        print("Analyzing sprint tickets...")

        if not self.jira_dir.exists():
            print(f"Error: JIRA directory not found: {self.jira_dir}")
            print("Run context-sync first to fetch JIRA tickets")
            return 1

        # Get all ticket files
        ticket_files = list(self.jira_dir.glob("*.md"))

        if not ticket_files:
            print(f"No tickets found in {self.jira_dir}")
            return 1

        print(f"Found {len(ticket_files)} ticket files")

        # Parse all tickets
        all_tickets = []
        for ticket_file in ticket_files:
            ticket = self.parse_ticket_file(ticket_file)
            if ticket:
                all_tickets.append(ticket)

        print(f"Parsed {len(all_tickets)} tickets")

        # Filter assigned tickets
        assigned_tickets = [t for t in all_tickets if self.is_assigned_to_me(t)]

        if not assigned_tickets:
            print("No tickets assigned to you found")
            print("Check ~/context-sync/jira/ for ticket files")
            return 1

        print(f"Found {len(assigned_tickets)} assigned tickets")

        # Get backlog suggestions
        backlog_suggestions = self.get_backlog_suggestions(all_tickets)

        # Generate notification
        self.generate_notification(assigned_tickets, backlog_suggestions)

        return 0


def main():
    """Main entry point."""
    analyzer = SprintAnalyzer()
    return analyzer.run()


if __name__ == "__main__":
    exit(main())
