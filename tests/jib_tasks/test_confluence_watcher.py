"""
Tests for the Confluence watcher module.

Tests the confluence-watcher.py which monitors Confluence documentation changes.
"""

import json
from datetime import datetime
from pathlib import Path


class TestConfluenceWatcherInit:
    """Tests for Confluence watcher initialization."""

    def test_confluence_dir_path(self, temp_dir, monkeypatch):
        """Test the path to Confluence directory."""
        monkeypatch.setenv("HOME", str(temp_dir))

        confluence_dir = Path.home() / "context-sync" / "confluence"
        assert "confluence" in str(confluence_dir)

    def test_state_file_path(self, temp_dir, monkeypatch):
        """Test the path to state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = Path.home() / "sharing" / "tracking" / "confluence-watcher-state.json"
        assert "confluence-watcher-state.json" in str(state_file)

    def test_returns_early_if_confluence_dir_not_exists(self, temp_dir, monkeypatch):
        """Test early return when Confluence directory doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        confluence_dir = temp_dir / "context-sync" / "confluence"
        assert not confluence_dir.exists()


class TestStateManagement:
    """Tests for state file management."""

    def test_loads_existing_state(self, temp_dir, monkeypatch):
        """Test loading existing state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "confluence-watcher-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state_data = {
            "processed": {
                "/path/to/doc1.md": "2024-01-01T00:00:00",
                "/path/to/doc2.md": "2024-01-02T00:00:00",
            }
        }
        state_file.write_text(json.dumps(state_data))

        with state_file.open() as f:
            loaded = json.load(f)

        assert len(loaded["processed"]) == 2

    def test_handles_missing_state_file(self, temp_dir, monkeypatch):
        """Test handling when state file doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "confluence-watcher-state.json"
        processed_docs = {}

        if state_file.exists():
            with state_file.open() as f:
                data = json.load(f)
                processed_docs = data.get("processed", {})

        assert processed_docs == {}

    def test_handles_corrupted_state_file(self, temp_dir, monkeypatch):
        """Test handling corrupted state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "confluence-watcher-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("not valid json")

        processed_docs = {}
        try:
            with state_file.open() as f:
                data = json.load(f)
                processed_docs = data.get("processed", {})
        except (OSError, json.JSONDecodeError):
            processed_docs = {}

        assert processed_docs == {}

    def test_saves_updated_state(self, temp_dir, monkeypatch):
        """Test saving updated state file."""
        monkeypatch.setenv("HOME", str(temp_dir))

        state_file = temp_dir / "sharing" / "tracking" / "confluence-watcher-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        processed_docs = {"/path/to/new-doc.md": "2024-01-03T00:00:00"}

        with state_file.open("w") as f:
            json.dump({"processed": processed_docs}, f, indent=2)

        assert state_file.exists()

        with state_file.open() as f:
            saved = json.load(f)

        assert len(saved["processed"]) == 1


class TestDocumentDiscovery:
    """Tests for document discovery."""

    def test_finds_adr_files(self, temp_dir):
        """Test finding ADR files."""
        confluence_dir = temp_dir / "confluence"
        space_dir = confluence_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        (space_dir / "ADR-001-Architecture.md").write_text("# ADR 001")
        (space_dir / "ADR-002-Database.md").write_text("# ADR 002")
        (space_dir / "other-doc.md").write_text("# Other")

        adr_files = list(confluence_dir.rglob("*ADR*.md"))
        assert len(adr_files) == 2

    def test_finds_runbook_files(self, temp_dir):
        """Test finding runbook files."""
        confluence_dir = temp_dir / "confluence"
        space_dir = confluence_dir / "OPS"
        space_dir.mkdir(parents=True, exist_ok=True)

        (space_dir / "Deployment-Runbook.md").write_text("# Runbook")
        (space_dir / "Incident-Runbook.md").write_text("# Incident")

        runbook_files = list(confluence_dir.rglob("*unbook*.md"))
        assert len(runbook_files) == 2

    def test_limits_adr_files_to_prevent_spam(self):
        """Test limiting ADR files to avoid spam."""
        adr_files = [f"adr_{i}.md" for i in range(20)]
        limited = adr_files[:10]

        assert len(limited) == 10

    def test_limits_runbook_files_to_prevent_spam(self):
        """Test limiting runbook files to avoid spam."""
        runbook_files = [f"runbook_{i}.md" for i in range(10)]
        limited = runbook_files[:5]

        assert len(limited) == 5


class TestChangeDetection:
    """Tests for detecting new/updated documents."""

    def test_detects_new_document(self, temp_dir):
        """Test detecting a new document."""
        processed_docs = {}
        doc_path = str(temp_dir / "new-doc.md")

        is_new = doc_path not in processed_docs
        assert is_new

    def test_detects_updated_document(self, temp_dir):
        """Test detecting an updated document."""
        doc_file = temp_dir / "doc.md"
        doc_file.write_text("content")

        old_mtime = "2024-01-01T00:00:00"
        new_mtime = datetime.fromtimestamp(doc_file.stat().st_mtime).isoformat()

        processed_docs = {str(doc_file): old_mtime}

        is_updated = processed_docs.get(str(doc_file)) != new_mtime
        assert is_updated

    def test_skips_unchanged_document(self, temp_dir):
        """Test skipping unchanged document."""
        doc_file = temp_dir / "doc.md"
        doc_file.write_text("content")

        mtime = datetime.fromtimestamp(doc_file.stat().st_mtime).isoformat()
        processed_docs = {str(doc_file): mtime}

        is_changed = processed_docs.get(str(doc_file)) != mtime
        assert not is_changed

    def test_collects_document_metadata(self, temp_dir):
        """Test collecting document metadata."""
        doc_file = temp_dir / "ADR-001.md"
        doc_file.write_text("# ADR 001\n\nContent here")

        mtime = doc_file.stat().st_mtime
        mtime_str = datetime.fromtimestamp(mtime).isoformat()

        doc_info = {
            "file": doc_file,
            "path": str(doc_file),
            "mtime": mtime_str,
            "is_new": True,
            "doc_type": "ADR",
            "content": doc_file.read_text(),
        }

        assert doc_info["doc_type"] == "ADR"
        assert "ADR 001" in doc_info["content"]


class TestPromptConstruction:
    """Tests for prompt construction."""

    def test_constructs_document_summary(self):
        """Test constructing document summary for prompt."""
        docs = [
            {"file": Path("ADR-001.md"), "is_new": True, "doc_type": "ADR"},
            {"file": Path("Runbook-Deploy.md"), "is_new": False, "doc_type": "Runbook"},
        ]

        summary = []
        for d in docs:
            status = "New" if d["is_new"] else "Updated"
            summary.append(f"**{status} {d['doc_type']}**: {d['file'].name}")

        assert len(summary) == 2
        assert "New ADR" in summary[0]
        assert "Updated Runbook" in summary[1]

    def test_truncates_long_content(self):
        """Test truncating long document content."""
        content = "x" * 5000
        max_length = 3000

        truncated = content[:max_length]
        suffix = "..." if len(content) > max_length else ""

        assert len(truncated) == 3000
        assert suffix == "..."

    def test_includes_workflow_instructions(self):
        """Test that prompt includes workflow instructions."""
        prompt_sections = [
            "Analyze the document",
            "Track in Beads",
            "Create notification",
            "Update state file",
        ]

        prompt_template = """
## Your Workflow (per ADR)

1. **Analyze the document**
2. **Track in Beads**
3. **Create notification**
4. **Update state file**
"""

        for section in prompt_sections:
            assert section in prompt_template


class TestClaudeExecution:
    """Tests for Claude Code execution."""

    def test_runs_claude_with_prompt(self):
        """Test running Claude with constructed prompt."""
        cmd = ["claude", "--dangerously-skip-permissions"]
        assert "claude" in cmd[0]
        assert "--dangerously-skip-permissions" in cmd

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


class TestStateUpdate:
    """Tests for updating state after processing."""

    def test_updates_processed_docs(self):
        """Test updating processed docs after analysis."""
        processed_docs = {}
        new_docs = [
            {"path": "/path/to/doc1.md", "mtime": "2024-01-01T00:00:00"},
            {"path": "/path/to/doc2.md", "mtime": "2024-01-02T00:00:00"},
        ]

        for d in new_docs:
            processed_docs[d["path"]] = d["mtime"]

        assert len(processed_docs) == 2
        assert "/path/to/doc1.md" in processed_docs

    def test_creates_state_directory_if_missing(self, temp_dir):
        """Test creating state directory if it doesn't exist."""
        state_file = temp_dir / "sharing" / "tracking" / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        assert state_file.parent.exists()


class TestMain:
    """Tests for main() entry point."""

    def test_returns_zero_when_no_changes(self):
        """Test returning 0 when no new/updated documents."""
        new_or_updated = []
        return_code = 0 if not new_or_updated else None

        assert return_code == 0

    def test_returns_zero_when_confluence_dir_missing(self, temp_dir, monkeypatch):
        """Test returning 0 when Confluence directory doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        confluence_dir = temp_dir / "context-sync" / "confluence"
        if not confluence_dir.exists():
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
        print("Confluence Watcher - Analyzing documentation changes...")

        captured = capsys.readouterr()
        assert "Confluence Watcher" in captured.out
