#!/usr/bin/env python3
"""
JIRA Watcher - Monitors JIRA tickets and sends proactive notifications

Detects new or updated JIRA tickets assigned to you, analyzes requirements,
extracts action items, and sends summaries via Slack notifications.

Scope: Only processes tickets assigned to you
"""

import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class JIRAWatcher:
    def __init__(self):
        self.jira_dir = Path.home() / "context-sync" / "jira"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.beads_dir = Path.home() / "beads"

        # Track which tickets we've already notified about
        self.state_file = Path.home() / "sharing" / "tracking" / "jira-watcher-state.json"
        self.processed_tickets = self.load_state()

    def load_state(self) -> Dict:
        """Load previously processed tickets with their last update times"""
        import json
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except:
                pass
        return {'processed': {}}

    def save_state(self):
        """Save processed ticket state"""
        import json
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open('w') as f:
            json.dump({'processed': self.processed_tickets}, f, indent=2)

    def watch(self):
        """Main watch loop - check for new or updated tickets"""
        if not self.jira_dir.exists():
            print("JIRA directory not found - skipping watch")
            return

        # Scan all JIRA ticket files
        for ticket_file in self.jira_dir.glob("*.md"):
            try:
                self.process_ticket_file(ticket_file)
            except Exception as e:
                print(f"Error processing {ticket_file}: {e}")

    def process_ticket_file(self, ticket_file: Path):
        """Process a single JIRA ticket file"""
        # Parse ticket data
        ticket = self.parse_ticket(ticket_file)
        if not ticket:
            return

        ticket_key = ticket['key']
        updated_time = ticket.get('updated', '')

        # Check if this is new or updated
        if ticket_key in self.processed_tickets:
            last_seen = self.processed_tickets[ticket_key]
            if last_seen == updated_time:
                return  # No changes since last check

        print(f"New or updated ticket: {ticket_key}")

        # Determine if this is a new ticket or an update
        is_new = ticket_key not in self.processed_tickets

        # Analyze the ticket
        analysis = self.analyze_ticket(ticket)

        # Create Beads task if new
        beads_id = None
        if is_new:
            beads_id = self.create_beads_task(ticket, analysis)

        # Send notification
        self.create_notification(ticket, analysis, is_new, beads_id)

        # Mark as processed
        self.processed_tickets[ticket_key] = updated_time
        self.save_state()

    def parse_ticket(self, ticket_file: Path) -> Optional[Dict]:
        """Parse JIRA ticket markdown file"""
        try:
            with ticket_file.open() as f:
                content = f.read()

            # Extract key from filename
            filename = ticket_file.name
            ticket_key = filename.split('_')[0] if '_' in filename else filename.replace('.md', '')

            ticket = {
                'key': ticket_key,
                'file': ticket_file,
                'title': '',
                'url': '',
                'type': '',
                'status': '',
                'priority': '',
                'assignee': '',
                'reporter': '',
                'created': '',
                'updated': '',
                'description': '',
                'acceptance_criteria': [],
                'comments': []
            }

            lines = content.split('\n')
            current_section = None
            section_content = []

            for line in lines:
                # Parse title
                if line.startswith('# '):
                    ticket['title'] = line.replace('#', '').strip()
                    # Extract key from title if not already set
                    if ':' in ticket['title']:
                        ticket['key'] = ticket['title'].split(':')[0].strip()

                # Parse metadata
                elif line.startswith('**URL:**'):
                    match = re.search(r'\[([^\]]+)\]\(([^\)]+)\)', line)
                    if match:
                        ticket['url'] = match.group(2)
                elif line.startswith('**Type:**'):
                    ticket['type'] = line.split(':', 1)[1].strip()
                elif line.startswith('**Status:**'):
                    ticket['status'] = line.split(':', 1)[1].strip()
                elif line.startswith('**Priority:**'):
                    ticket['priority'] = line.split(':', 1)[1].strip()
                elif line.startswith('**Assignee:**'):
                    ticket['assignee'] = line.split(':', 1)[1].strip()
                elif line.startswith('**Reporter:**'):
                    ticket['reporter'] = line.split(':', 1)[1].strip()
                elif line.startswith('**Created:**'):
                    ticket['created'] = line.split(':', 1)[1].strip()
                elif line.startswith('**Updated:**'):
                    ticket['updated'] = line.split(':', 1)[1].strip()

                # Track sections
                elif line.startswith('## Description'):
                    current_section = 'description'
                    section_content = []
                elif line.startswith('## Acceptance Criteria'):
                    if current_section == 'description':
                        ticket['description'] = '\n'.join(section_content).strip()
                    current_section = 'acceptance_criteria'
                    section_content = []
                elif line.startswith('## Comments'):
                    if current_section == 'acceptance_criteria':
                        # Parse acceptance criteria checkboxes
                        for sc_line in section_content:
                            if sc_line.strip().startswith('- [ ]') or sc_line.strip().startswith('- [x]'):
                                ticket['acceptance_criteria'].append(sc_line.strip())
                    current_section = 'comments'
                    section_content = []
                elif line.startswith('##'):
                    # New section
                    if current_section == 'description':
                        ticket['description'] = '\n'.join(section_content).strip()
                    current_section = None
                elif current_section:
                    section_content.append(line)

            # Handle last section
            if current_section == 'description':
                ticket['description'] = '\n'.join(section_content).strip()

            return ticket

        except Exception as e:
            print(f"Error parsing ticket file {ticket_file}: {e}")
            return None

    def analyze_ticket(self, ticket: Dict) -> Dict:
        """Analyze ticket and extract actionable insights"""
        analysis = {
            'summary': '',
            'action_items': [],
            'estimated_scope': '',
            'dependencies': [],
            'next_steps': [],
            'risks': []
        }

        description = ticket.get('description', '').lower()
        title = ticket.get('title', '').lower()
        ticket_type = ticket.get('type', '').lower()

        # Determine scope
        criteria_count = len(ticket.get('acceptance_criteria', []))
        if criteria_count > 5 or len(description) > 500:
            analysis['estimated_scope'] = 'Large (multiple days)'
        elif criteria_count > 2 or len(description) > 200:
            analysis['estimated_scope'] = 'Medium (1-2 days)'
        else:
            analysis['estimated_scope'] = 'Small (few hours)'

        # Extract action items from description
        action_patterns = [
            r'need to\s+([^.!?\n]+)',
            r'should\s+([^.!?\n]+)',
            r'must\s+([^.!?\n]+)',
            r'\d+\.\s+([^.!?\n]+)',  # Numbered lists
        ]

        for pattern in action_patterns:
            matches = re.finditer(pattern, description, re.IGNORECASE)
            for match in matches:
                action = match.group(1).strip()
                if len(action) > 10 and len(action) < 100:  # Reasonable length
                    analysis['action_items'].append(action)

        # Identify dependencies
        dep_keywords = ['depend', 'requires', 'needs', 'blocked by', 'after']
        for keyword in dep_keywords:
            if keyword in description:
                analysis['dependencies'].append(f"Mentioned: {keyword}")

        # Identify risks
        risk_keywords = ['concern', 'risk', 'careful', 'breaking change', 'migration']
        for keyword in risk_keywords:
            if keyword in description:
                analysis['risks'].append(f"Mentioned: {keyword}")

        # Generate summary based on type
        if 'bug' in ticket_type:
            analysis['summary'] = f"Bug fix required: {ticket['title']}"
            analysis['next_steps'] = [
                "Reproduce the issue",
                "Identify root cause",
                "Implement fix with tests",
                "Verify resolution"
            ]
        elif 'task' in ticket_type:
            analysis['summary'] = f"Task: {ticket['title']}"
            analysis['next_steps'] = [
                "Review requirements and acceptance criteria",
                "Plan implementation approach",
                "Break down into subtasks if needed",
                "Implement and test"
            ]
        else:
            analysis['summary'] = f"Work item: {ticket['title']}"
            analysis['next_steps'] = [
                "Review ticket details",
                "Clarify any ambiguities",
                "Plan and implement"
            ]

        return analysis

    def create_beads_task(self, ticket: Dict, analysis: Dict) -> Optional[str]:
        """Create Beads task for the ticket"""
        try:
            result = subprocess.run(['which', 'bd'], capture_output=True)
            if result.returncode != 0:
                return None

            ticket_key = ticket['key']
            title = f"{ticket_key}: {ticket['title']}"

            # Truncate title if too long
            if len(title) > 80:
                title = title[:77] + "..."

            result = subprocess.run(
                ['bd', 'add', title, '--tags', ticket_key.lower(), 'jira', ticket.get('type', 'task').lower()],
                cwd=self.beads_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if 'Created' in output and 'bd-' in output:
                    bead_id = output.split('bd-')[1].split(':')[0]
                    bead_id = f"bd-{bead_id.split()[0]}"

                    # Add notes with details
                    notes = f"JIRA: {ticket_key}\n"
                    notes += f"Status: {ticket.get('status', 'Unknown')}\n"
                    notes += f"Priority: {ticket.get('priority', 'Not Set')}\n"
                    notes += f"Scope: {analysis['estimated_scope']}\n"
                    notes += f"URL: {ticket.get('url', 'N/A')}"

                    subprocess.run(
                        ['bd', 'update', bead_id, '--notes', notes],
                        cwd=self.beads_dir,
                        capture_output=True
                    )

                    print(f"  ✓ Created Beads task: {bead_id}")
                    return bead_id
        except Exception as e:
            print(f"  Could not create Beads task: {e}")

        return None

    def create_notification(self, ticket: Dict, analysis: Dict, is_new: bool, beads_id: Optional[str]):
        """Create Slack notification for ticket"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        ticket_key = ticket['key']
        notif_type = "new-ticket" if is_new else "ticket-updated"
        notif_file = self.notifications_dir / f"{timestamp}-jira-{notif_type}-{ticket_key}.md"

        with notif_file.open('w') as f:
            emoji = "🆕" if is_new else "📝"
            f.write(f"# {emoji} JIRA Ticket {'Assigned' if is_new else 'Updated'}: {ticket_key}\n\n")

            f.write(f"**Ticket**: {ticket['title']}\n")
            f.write(f"**Type**: {ticket.get('type', 'Unknown')}\n")
            f.write(f"**Status**: {ticket.get('status', 'Unknown')}\n")
            f.write(f"**Priority**: {ticket.get('priority', 'Not Set')}\n")
            f.write(f"**URL**: {ticket.get('url', 'N/A')}\n")
            if beads_id:
                f.write(f"**Beads Task**: {beads_id}\n")
            f.write("\n")

            # Summary
            f.write("## 📊 Quick Summary\n\n")
            f.write(f"{analysis['summary']}\n\n")
            f.write(f"**Estimated Scope**: {analysis['estimated_scope']}\n\n")

            # Description
            if ticket.get('description'):
                f.write("## 📄 Description\n\n")
                desc = ticket['description']
                if len(desc) > 500:
                    desc = desc[:500] + "...\n\n*(Truncated, see ticket for full description)*"
                f.write(f"{desc}\n\n")

            # Acceptance Criteria
            if ticket.get('acceptance_criteria'):
                f.write("## ✅ Acceptance Criteria\n\n")
                for criterion in ticket['acceptance_criteria']:
                    f.write(f"{criterion}\n")
                f.write("\n")

            # Action Items
            if analysis['action_items']:
                f.write("## 🎯 Extracted Action Items\n\n")
                for i, action in enumerate(analysis['action_items'][:5], 1):
                    f.write(f"{i}. {action}\n")
                if len(analysis['action_items']) > 5:
                    f.write(f"\n*(+{len(analysis['action_items']) - 5} more in ticket)*\n")
                f.write("\n")

            # Dependencies
            if analysis['dependencies']:
                f.write("## 🔗 Dependencies/Blockers\n\n")
                for dep in analysis['dependencies']:
                    f.write(f"- {dep}\n")
                f.write("\n")

            # Risks
            if analysis['risks']:
                f.write("## ⚠️ Potential Risks\n\n")
                for risk in analysis['risks']:
                    f.write(f"- {risk}\n")
                f.write("\n")

            # Next Steps
            f.write("## 📋 Suggested Next Steps\n\n")
            for i, step in enumerate(analysis['next_steps'], 1):
                f.write(f"{i}. {step}\n")
            f.write("\n")

            if is_new and beads_id:
                f.write("**Beads Task Created**: Use `bd update` to track progress\n\n")

            f.write("---\n")
            f.write(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"📂 {ticket_key} in JIRA\n")

        print(f"  ✓ Created notification: {notif_file.name}")


def main():
    """Main entry point"""
    watcher = JIRAWatcher()
    watcher.watch()


if __name__ == '__main__':
    main()
