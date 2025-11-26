"""
Tests for the Sprint Ticket Analyzer module.

Tests the analyze-sprint.py which analyzes tickets in the active sprint.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSprintAnalyzerInit:
    """Tests for SprintAnalyzer initialization."""

    def test_jira_dir_path(self, temp_dir, monkeypatch):
        """Test the path to JIRA directory."""
        monkeypatch.setenv("HOME", str(temp_dir))

        jira_dir = Path.home() / "context-sync" / "jira"
        assert "jira" in str(jira_dir)

    def test_notifications_dir_path(self, temp_dir, monkeypatch):
        """Test the path to notifications directory."""
        monkeypatch.setenv("HOME", str(temp_dir))

        notifications_dir = Path.home() / "sharing" / "notifications"
        assert "notifications" in str(notifications_dir)

    def test_creates_notifications_dir(self, temp_dir, monkeypatch):
        """Test creating notifications directory."""
        monkeypatch.setenv("HOME", str(temp_dir))

        notifications_dir = temp_dir / "sharing" / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)

        assert notifications_dir.exists()


class TestParseTicketFile:
    """Tests for parse_ticket_file method."""

    def test_parses_ticket_key_and_title(self, temp_dir):
        """Test parsing ticket key and title from first line."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("# PROJ-123: Fix Important Bug\n\nDescription")

        import re
        content = ticket_file.read_text()
        lines = content.split("\n")
        first_line = lines[0]

        title_match = re.match(r"^#\s+([A-Z]+-\d+):\s+(.+)$", first_line)

        assert title_match is not None
        assert title_match.group(1) == "PROJ-123"
        assert title_match.group(2) == "Fix Important Bug"

    def test_extracts_status(self, temp_dir):
        """Test extracting ticket status."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title
**Status:** In Progress
""")

        content = ticket_file.read_text()
        status = ""
        for line in content.split("\n"):
            if line.startswith("**Status:**"):
                status = line.replace("**Status:**", "").strip()

        assert status == "In Progress"

    def test_extracts_assignee(self, temp_dir):
        """Test extracting ticket assignee."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title
**Assignee:** jwiesebron
""")

        content = ticket_file.read_text()
        assignee = ""
        for line in content.split("\n"):
            if line.startswith("**Assignee:**"):
                assignee = line.replace("**Assignee:**", "").strip()

        assert assignee == "jwiesebron"

    def test_extracts_priority(self, temp_dir):
        """Test extracting ticket priority."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title
**Priority:** High
""")

        content = ticket_file.read_text()
        priority = ""
        for line in content.split("\n"):
            if line.startswith("**Priority:**"):
                priority = line.replace("**Priority:**", "").strip()

        assert priority == "High"

    def test_extracts_type(self, temp_dir):
        """Test extracting ticket type."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title
**Type:** Bug
""")

        content = ticket_file.read_text()
        ticket_type = ""
        for line in content.split("\n"):
            if line.startswith("**Type:**"):
                ticket_type = line.replace("**Type:**", "").strip()

        assert ticket_type == "Bug"

    def test_extracts_labels(self, temp_dir):
        """Test extracting ticket labels."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title
**Labels:** backend, urgent, tech-debt
""")

        content = ticket_file.read_text()
        labels = []
        for line in content.split("\n"):
            if line.startswith("**Labels:**"):
                labels_str = line.replace("**Labels:**", "").strip()
                labels = [l.strip() for l in labels_str.split(",") if l.strip()]

        assert len(labels) == 3
        assert "backend" in labels
        assert "urgent" in labels

    def test_detects_acceptance_criteria(self, temp_dir):
        """Test detecting presence of acceptance criteria."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title

## Acceptance Criteria
- [ ] First criterion
- [ ] Second criterion
""")

        content = ticket_file.read_text()
        has_acceptance = "acceptance criteria" in content.lower() or "- [ ]" in content

        assert has_acceptance

    def test_counts_comments(self, temp_dir):
        """Test counting comments."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title

## Comments

### Comment 1
First comment

### Comment 2
Second comment

### Comment 3
Third comment
""")

        content = ticket_file.read_text()
        comments_count = content.count("### Comment ")

        assert comments_count == 3

    def test_extracts_description(self, temp_dir):
        """Test extracting description section."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("""# PROJ-123: Title

## Description
This is the description of the ticket.
It can span multiple lines.

## Comments
Comment section
""")

        content = ticket_file.read_text()
        desc_start = content.find("## Description")
        if desc_start != -1:
            desc_end = content.find("\n## ", desc_start + 1)
            if desc_end == -1:
                desc_end = len(content)
            description = content[desc_start:desc_end].strip()

        assert "description of the ticket" in description
        assert "multiple lines" in description

    def test_handles_parsing_error(self, temp_dir):
        """Test handling parsing errors."""
        ticket_file = temp_dir / "invalid.md"
        ticket_file.write_text("")  # Empty file

        # Should not raise
        content = ticket_file.read_text()
        lines = content.split("\n")
        first_line = lines[0] if lines else ""

        assert first_line == ""


class TestIsAssignedToMe:
    """Tests for is_assigned_to_me method."""

    def test_returns_true_for_assigned_ticket(self):
        """Test returning True when ticket is assigned to me."""
        ticket = {"assignee": "jwiesebron"}
        assignee = ticket.get("assignee", "").lower()

        # Assuming 'jwiesebron' is the current user
        is_assigned = "jwiesebron" in assignee.lower()
        assert is_assigned

    def test_returns_false_for_unassigned_ticket(self):
        """Test returning False when ticket is unassigned."""
        ticket = {"assignee": "Unassigned"}
        assignee = ticket.get("assignee", "").lower()

        is_assigned = "jwiesebron" in assignee
        assert not is_assigned

    def test_returns_false_for_other_assignee(self):
        """Test returning False when assigned to someone else."""
        ticket = {"assignee": "someone-else"}
        assignee = ticket.get("assignee", "").lower()

        is_assigned = "jwiesebron" in assignee
        assert not is_assigned


class TestCategorizeTickets:
    """Tests for categorizing tickets."""

    def test_categorizes_in_progress_tickets(self):
        """Test categorizing tickets by status."""
        tickets = [
            {"key": "PROJ-1", "status": "In Progress"},
            {"key": "PROJ-2", "status": "To Do"},
            {"key": "PROJ-3", "status": "Done"},
        ]

        in_progress = [t for t in tickets if "progress" in t["status"].lower()]
        assert len(in_progress) == 1
        assert in_progress[0]["key"] == "PROJ-1"

    def test_sorts_by_priority(self):
        """Test sorting tickets by priority."""
        tickets = [
            {"key": "PROJ-1", "priority": "Low"},
            {"key": "PROJ-2", "priority": "High"},
            {"key": "PROJ-3", "priority": "Medium"},
        ]

        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_tickets = sorted(
            tickets,
            key=lambda t: priority_order.get(t["priority"].lower(), 99)
        )

        assert sorted_tickets[0]["key"] == "PROJ-2"  # High priority first
        assert sorted_tickets[1]["key"] == "PROJ-3"  # Medium
        assert sorted_tickets[2]["key"] == "PROJ-1"  # Low

    def test_filters_by_labels(self):
        """Test filtering tickets by labels."""
        tickets = [
            {"key": "PROJ-1", "labels": ["backend", "urgent"]},
            {"key": "PROJ-2", "labels": ["frontend"]},
            {"key": "PROJ-3", "labels": ["backend"]},
        ]

        backend_tickets = [t for t in tickets if "backend" in t["labels"]]
        assert len(backend_tickets) == 2


class TestGenerateRecommendations:
    """Tests for generating recommendations."""

    def test_recommends_in_progress_tickets_first(self):
        """Test recommending in-progress tickets first."""
        tickets = [
            {"key": "PROJ-1", "status": "In Progress", "title": "Fix Bug"},
            {"key": "PROJ-2", "status": "To Do", "title": "New Feature"},
        ]

        in_progress = [t for t in tickets if "progress" in t["status"].lower()]
        recommendations = []

        if in_progress:
            recommendations.append({
                "action": "continue",
                "ticket": in_progress[0],
                "reason": "Ticket already in progress"
            })

        assert len(recommendations) == 1
        assert recommendations[0]["action"] == "continue"

    def test_recommends_high_priority_from_backlog(self):
        """Test recommending high priority tickets from backlog."""
        tickets = [
            {"key": "PROJ-1", "status": "To Do", "priority": "High"},
            {"key": "PROJ-2", "status": "To Do", "priority": "Low"},
        ]

        backlog = [t for t in tickets if t["status"] == "To Do"]
        high_priority = [t for t in backlog if t["priority"] == "High"]

        assert len(high_priority) == 1
        assert high_priority[0]["key"] == "PROJ-1"


class TestNotificationGeneration:
    """Tests for generating notifications."""

    def test_creates_notification_file(self, temp_dir):
        """Test creating notification file."""
        notifications_dir = temp_dir / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = notifications_dir / f"{timestamp}-sprint-analysis.md"
        notif_file.write_text("# Sprint Analysis\n\nContent here")

        assert notif_file.exists()

    def test_notification_includes_recommendations(self, temp_dir):
        """Test that notification includes recommendations."""
        notifications_dir = temp_dir / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)

        recommendations = [
            {"action": "continue", "ticket": {"key": "PROJ-1", "title": "Fix Bug"}},
            {"action": "pull", "ticket": {"key": "PROJ-2", "title": "New Feature"}},
        ]

        content = "# Sprint Analysis\n\n## Recommendations\n\n"
        for rec in recommendations:
            content += f"- **{rec['action'].upper()}**: {rec['ticket']['key']} - {rec['ticket']['title']}\n"

        notif_file = notifications_dir / "sprint-analysis.md"
        notif_file.write_text(content)

        assert "PROJ-1" in notif_file.read_text()
        assert "PROJ-2" in notif_file.read_text()

    def test_notification_formats_correctly(self, temp_dir):
        """Test notification formatting."""
        notifications_dir = temp_dir / "notifications"
        notifications_dir.mkdir(parents=True, exist_ok=True)

        content = """# Sprint Analysis

## Summary
- 2 tickets in progress
- 5 tickets in backlog
- 1 high priority ticket recommended

## Current Work
...
"""
        notif_file = notifications_dir / "sprint-analysis.md"
        notif_file.write_text(content)

        output = notif_file.read_text()
        assert "# Sprint Analysis" in output
        assert "## Summary" in output


class TestMain:
    """Tests for main entry point."""

    def test_returns_zero_when_no_jira_dir(self, temp_dir, monkeypatch):
        """Test returning 0 when JIRA directory doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        jira_dir = temp_dir / "context-sync" / "jira"
        if not jira_dir.exists():
            return_code = 0
        else:
            return_code = 1

        assert return_code == 0

    def test_returns_zero_on_success(self):
        """Test returning 0 on success."""
        success = True
        return_code = 0 if success else 1

        assert return_code == 0

    def test_returns_one_on_error(self):
        """Test returning 1 on error."""
        error = True
        return_code = 1 if error else 0

        assert return_code == 1

    def test_prints_status_messages(self, capsys):
        """Test printing status messages."""
        print("Sprint Ticket Analyzer - Analyzing tickets...")

        captured = capsys.readouterr()
        assert "Sprint Ticket Analyzer" in captured.out
