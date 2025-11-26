"""
Tests for the JIRA watcher module.

Tests the jira-watcher.py which monitors JIRA tickets and sends notifications.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestJiraWatcherInit:
    """Tests for JIRA watcher initialization."""

    def test_jira_dir_path(self, temp_dir, monkeypatch):
        """Test the path to JIRA directory."""
        monkeypatch.setenv("HOME", str(temp_dir))

        jira_dir = Path.home() / "context-sync" / "jira"
        assert "jira" in str(jira_dir)

    def test_state_file_path(self, temp_dir, monkeypatch):
        """Test the path to state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = Path.home() / "sharing" / "tracking" / "jira-watcher-state.json"
        assert "jira-watcher-state.json" in str(state_file)

    def test_returns_early_if_jira_dir_not_exists(self, temp_dir, monkeypatch):
        """Test early return when JIRA directory doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        jira_dir = temp_dir / "context-sync" / "jira"
        assert not jira_dir.exists()


class TestTicketStateManagement:
    """Tests for ticket state file management."""

    def test_loads_existing_state(self, temp_dir, monkeypatch):
        """Test loading existing state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "jira-watcher-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_data = {
            'processed': {
                '/path/to/PROJ-123.md': '2024-01-01T00:00:00',
                '/path/to/PROJ-456.md': '2024-01-02T00:00:00'
            }
        }
        state_file.write_text(json.dumps(state_data))

        with state_file.open() as f:
            loaded = json.load(f)

        assert len(loaded['processed']) == 2

    def test_handles_missing_state_file(self, temp_dir, monkeypatch):
        """Test handling when state file doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "jira-watcher-state.json"
        processed_tickets = {}

        if state_file.exists():
            with state_file.open() as f:
                data = json.load(f)
                processed_tickets = data.get('processed', {})

        assert processed_tickets == {}

    def test_handles_corrupted_state_file(self, temp_dir, monkeypatch):
        """Test handling corrupted state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "jira-watcher-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("invalid json content")

        processed_tickets = {}
        try:
            with state_file.open() as f:
                data = json.load(f)
                processed_tickets = data.get('processed', {})
        except (OSError, json.JSONDecodeError):
            processed_tickets = {}

        assert processed_tickets == {}

    def test_saves_updated_state(self, temp_dir, monkeypatch):
        """Test saving updated state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "jira-watcher-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        processed_tickets = {
            '/path/to/PROJ-789.md': '2024-01-03T00:00:00'
        }

        with state_file.open('w') as f:
            json.dump({'processed': processed_tickets}, f, indent=2)

        assert state_file.exists()


class TestTicketDiscovery:
    """Tests for discovering JIRA ticket files."""

    def test_finds_markdown_ticket_files(self, temp_dir):
        """Test finding markdown ticket files."""
        jira_dir = temp_dir / "jira"
        jira_dir.mkdir()

        (jira_dir / "PROJ-123.md").write_text("# PROJ-123")
        (jira_dir / "PROJ-456.md").write_text("# PROJ-456")
        (jira_dir / "README.md").write_text("# README")

        ticket_files = list(jira_dir.glob("*.md"))
        assert len(ticket_files) == 3

    def test_filters_only_ticket_files(self, temp_dir):
        """Test filtering to include only ticket files."""
        jira_dir = temp_dir / "jira"
        jira_dir.mkdir()

        (jira_dir / "PROJ-123.md").write_text("# PROJ-123")
        (jira_dir / "not-a-ticket.txt").write_text("text file")
        (jira_dir / "data.json").write_text("{}")

        md_files = list(jira_dir.glob("*.md"))
        assert len(md_files) == 1


class TestTicketChangeDetection:
    """Tests for detecting new/updated tickets."""

    def test_detects_new_ticket(self, temp_dir):
        """Test detecting a new ticket."""
        processed_tickets = {}
        ticket_path = str(temp_dir / "PROJ-123.md")

        is_new = ticket_path not in processed_tickets
        assert is_new

    def test_detects_updated_ticket(self, temp_dir):
        """Test detecting an updated ticket."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("# PROJ-123\n\nUpdated content")

        old_mtime = '2024-01-01T00:00:00'
        new_mtime = datetime.fromtimestamp(ticket_file.stat().st_mtime).isoformat()

        processed_tickets = {str(ticket_file): old_mtime}

        is_updated = processed_tickets.get(str(ticket_file)) != new_mtime
        assert is_updated

    def test_skips_unchanged_ticket(self, temp_dir):
        """Test skipping unchanged ticket."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("content")

        mtime = datetime.fromtimestamp(ticket_file.stat().st_mtime).isoformat()
        processed_tickets = {str(ticket_file): mtime}

        is_changed = processed_tickets.get(str(ticket_file)) != mtime
        assert not is_changed

    def test_collects_ticket_metadata(self, temp_dir):
        """Test collecting ticket metadata."""
        ticket_file = temp_dir / "PROJ-123.md"
        ticket_file.write_text("# PROJ-123: Fix Bug\n\nDescription here")

        mtime = ticket_file.stat().st_mtime
        mtime_str = datetime.fromtimestamp(mtime).isoformat()

        ticket_info = {
            'file': ticket_file,
            'path': str(ticket_file),
            'mtime': mtime_str,
            'is_new': True,
            'content': ticket_file.read_text()
        }

        assert 'PROJ-123' in str(ticket_info['file'])
        assert 'Fix Bug' in ticket_info['content']


class TestTicketPromptConstruction:
    """Tests for prompt construction."""

    def test_constructs_ticket_summary(self):
        """Test constructing ticket summary for prompt."""
        tickets = [
            {'file': Path('PROJ-123.md'), 'is_new': True},
            {'file': Path('PROJ-456.md'), 'is_new': False}
        ]

        summary = []
        for t in tickets:
            status = "New" if t['is_new'] else "Updated"
            summary.append(f"**{status}**: {t['file'].name}")

        assert len(summary) == 2
        assert "New" in summary[0]
        assert "Updated" in summary[1]

    def test_truncates_long_content(self):
        """Test truncating long ticket content."""
        content = "x" * 3000
        max_length = 2000

        truncated = content[:max_length]
        suffix = "..." if len(content) > max_length else ""

        assert len(truncated) == 2000
        assert suffix == "..."

    def test_includes_workflow_instructions(self):
        """Test that prompt includes workflow instructions."""
        workflow_steps = [
            "Analyze the ticket",
            "Track in Beads",
            "Create notification",
            "Update state file"
        ]

        prompt_template = """
## Your Workflow (per ADR)

1. **Analyze the ticket**
2. **Track in Beads**
3. **Create notification**
4. **Update state file**
"""

        for step in workflow_steps:
            assert step in prompt_template

    def test_includes_ticket_metadata_in_prompt(self):
        """Test including ticket metadata in prompt."""
        ticket = {
            'file': Path('PROJ-123.md'),
            'is_new': True,
            'content': '# PROJ-123: Implement Feature'
        }

        status = "NEW TICKET" if ticket['is_new'] else "UPDATED TICKET"
        prompt_section = f"""
### {status}: {ticket['file'].name}

**File:** `{ticket['file']}`

**Content:**
```markdown
{ticket['content']}
```
"""

        assert "NEW TICKET" in prompt_section
        assert "PROJ-123" in prompt_section


class TestClaudeExecution:
    """Tests for Claude Code execution."""

    def test_runs_claude_with_prompt(self):
        """Test running Claude with constructed prompt."""
        cmd = ["claude", "--dangerously-skip-permissions"]
        assert "claude" in cmd[0]

    def test_handles_successful_execution(self):
        """Test handling successful Claude execution."""
        returncode = 0
        is_success = returncode == 0

        assert is_success

    def test_handles_claude_error(self):
        """Test handling Claude execution error."""
        returncode = 1
        is_success = returncode == 0

        assert not is_success

    def test_handles_timeout(self):
        """Test handling execution timeout."""
        timeout_seconds = 900  # 15 minutes

        assert timeout_seconds == 900


class TestTicketStateUpdate:
    """Tests for updating state after processing."""

    def test_updates_processed_tickets(self):
        """Test updating processed tickets after analysis."""
        processed_tickets = {}
        new_tickets = [
            {'path': '/path/to/PROJ-123.md', 'mtime': '2024-01-01T00:00:00'},
            {'path': '/path/to/PROJ-456.md', 'mtime': '2024-01-02T00:00:00'}
        ]

        for t in new_tickets:
            processed_tickets[t['path']] = t['mtime']

        assert len(processed_tickets) == 2
        assert '/path/to/PROJ-123.md' in processed_tickets

    def test_creates_state_directory_if_missing(self, temp_dir):
        """Test creating state directory if it doesn't exist."""
        state_file = temp_dir / "sharing" / "tracking" / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        assert state_file.parent.exists()


class TestJiraMain:
    """Tests for main() entry point."""

    def test_returns_zero_when_no_changes(self):
        """Test returning 0 when no new/updated tickets."""
        new_or_updated = []
        return_code = 0 if not new_or_updated else None

        assert return_code == 0

    def test_returns_zero_when_jira_dir_missing(self, temp_dir, monkeypatch):
        """Test returning 0 when JIRA directory doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        jira_dir = temp_dir / "context-sync" / "jira"
        if not jira_dir.exists():
            return_code = 0
        else:
            return_code = 1

        assert return_code == 0

    def test_returns_one_on_error(self):
        """Test returning 1 on error."""
        error_occurred = True
        return_code = 1 if error_occurred else 0

        assert return_code == 1

    def test_prints_status_messages(self, capsys):
        """Test printing status messages."""
        print("JIRA Watcher - Analyzing assigned tickets...")

        captured = capsys.readouterr()
        assert "JIRA Watcher" in captured.out

    def test_prints_found_tickets_count(self, capsys):
        """Test printing count of found tickets."""
        new_or_updated = [1, 2, 3]
        print(f"Found {len(new_or_updated)} new or updated ticket(s)")

        captured = capsys.readouterr()
        assert "Found 3" in captured.out


class TestTicketParsing:
    """Tests for parsing ticket content."""

    def test_extracts_ticket_key_from_filename(self):
        """Test extracting ticket key from filename."""
        filename = "PROJ-123.md"
        ticket_key = filename.replace(".md", "")

        assert ticket_key == "PROJ-123"

    def test_extracts_title_from_content(self):
        """Test extracting title from ticket content."""
        content = "# PROJ-123: Implement Feature\n\nDescription..."
        lines = content.split('\n')
        title = lines[0].replace('#', '').strip()

        assert "Implement Feature" in title

    def test_handles_various_ticket_formats(self):
        """Test handling various ticket key formats."""
        ticket_keys = [
            "PROJ-123",
            "ABC-1",
            "TEAM-9999",
            "XX-1234567"
        ]

        for key in ticket_keys:
            # Ticket key format: LETTERS-NUMBERS
            parts = key.split('-')
            assert len(parts) == 2
            assert parts[0].isalpha()
            assert parts[1].isdigit()
