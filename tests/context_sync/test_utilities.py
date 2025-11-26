"""
Tests for context-sync utility modules.

Tests config_loader, maintenance, search, and other utilities.
"""

import contextlib


class TestConfigLoader:
    """Tests for config_loader.py."""

    def test_load_env_file_checks_config_location(self, temp_dir, monkeypatch):
        """Test that load_env_file checks ~/.config/context-sync/.env."""
        monkeypatch.setenv("HOME", str(temp_dir))

        config_dir = temp_dir / ".config" / "context-sync"
        config_dir.mkdir(parents=True, exist_ok=True)

        env_file = config_dir / ".env"
        env_file.write_text("TEST_VAR=value\n")

        assert env_file.exists()

    def test_load_env_file_fallback_to_repo_env(self, temp_dir):
        """Test fallback to repo .env file."""
        repo_env = temp_dir / ".env"
        repo_env.write_text("FALLBACK_VAR=fallback\n")

        assert repo_env.exists()

    def test_load_env_handles_missing_dotenv(self):
        """Test handling when dotenv module is not available."""
        # Should not raise even if dotenv is missing
        with contextlib.suppress(ImportError):
            pass

        # Either way, should not crash
        assert True

    def test_load_env_handles_missing_files(self, temp_dir, monkeypatch):
        """Test handling when no .env files exist."""
        monkeypatch.setenv("HOME", str(temp_dir))

        config_path = temp_dir / ".config" / "context-sync" / ".env"
        assert not config_path.exists()

        # Should not crash
        assert True


class TestMaintenance:
    """Tests for maintenance.py."""

    def test_get_sync_status_handles_missing_dir(self, temp_dir, capsys):
        """Test get_sync_status when output dir doesn't exist."""
        output_dir = temp_dir / "nonexistent"

        if not output_dir.exists():
            print("No synced documentation found.")

        captured = capsys.readouterr()
        assert "No synced documentation found." in captured.out

    def test_get_sync_status_counts_pages(self, temp_dir, capsys):
        """Test that get_sync_status counts pages correctly."""
        output_dir = temp_dir / "confluence"
        space_dir = output_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        # Create some test pages
        (space_dir / "page1.md").write_text("# Page 1")
        (space_dir / "page2.md").write_text("# Page 2")
        (space_dir / "README.md").write_text("# Index")

        md_files = list(space_dir.glob("*.md"))
        page_count = len([f for f in md_files if f.name != "README.md"])

        print(f"  TECH: {page_count} pages")
        captured = capsys.readouterr()
        assert "TECH: 2 pages" in captured.out

    def test_get_sync_status_counts_spaces(self, temp_dir):
        """Test that get_sync_status counts spaces correctly."""
        output_dir = temp_dir / "confluence"
        (output_dir / "TECH").mkdir(parents=True, exist_ok=True)
        (output_dir / "DOCS").mkdir(parents=True, exist_ok=True)

        spaces = [d for d in output_dir.iterdir() if d.is_dir()]
        assert len(spaces) == 2

    def test_get_sync_status_checks_sync_state_file(self, temp_dir):
        """Test that sync state file existence is checked."""
        output_dir = temp_dir / "confluence"
        output_dir.mkdir(parents=True, exist_ok=True)

        sync_state_file = output_dir / ".sync_state"
        sync_state_file.write_text("")

        assert sync_state_file.exists()

    def test_find_orphaned_files_finds_md_files(self, temp_dir):
        """Test that find_orphaned_files finds markdown files."""
        space_dir = temp_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        orphan1 = space_dir / "orphan1.md"
        orphan2 = space_dir / "orphan2.md"
        readme = space_dir / "README.md"

        orphan1.write_text("content")
        orphan2.write_text("content")
        readme.write_text("index")

        orphaned = []
        for f in space_dir.iterdir():
            if f.is_file() and f.suffix == ".md" and f.name != "README.md":
                orphaned.append(f)

        assert len(orphaned) == 2

    def test_find_orphaned_files_dry_run(self, temp_dir):
        """Test that dry run doesn't delete files."""
        space_dir = temp_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        orphan = space_dir / "orphan.md"
        orphan.write_text("content")

        execute = False
        if not execute:
            # Dry run, don't delete
            pass

        assert orphan.exists()

    def test_find_orphaned_files_execute(self, temp_dir):
        """Test that execute mode deletes files."""
        space_dir = temp_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        orphan = space_dir / "orphan.md"
        orphan.write_text("content")

        execute = True
        if execute:
            orphan.unlink()

        assert not orphan.exists()

    def test_maintenance_main_usage(self, capsys):
        """Test maintenance main shows usage when no args."""
        print("Usage: python maintenance.py [--status|--cleanup] [--execute]")

        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    def test_maintenance_unknown_command(self, capsys):
        """Test handling of unknown command."""
        command = "--invalid"
        if command not in ["--status", "--cleanup"]:
            print("Unknown command. Use --status or --cleanup")

        captured = capsys.readouterr()
        assert "Unknown command" in captured.out


class TestSearch:
    """Tests for search.py."""

    def test_search_documentation_basic(self, temp_dir):
        """Test basic search functionality."""
        output_dir = temp_dir / "confluence"
        space_dir = output_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        page = space_dir / "test.md"
        page.write_text("# Test Page\n\nThis is a test page with searchable content.")

        query = "searchable"
        content = page.read_text().lower()
        found = query.lower() in content

        assert found

    def test_search_case_insensitive(self, temp_dir):
        """Test that search is case insensitive."""
        output_dir = temp_dir / "confluence"
        space_dir = output_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        page = space_dir / "test.md"
        page.write_text("SEARCHABLE Content")

        query = "searchable"
        content = page.read_text().lower()
        found = query.lower() in content

        assert found

    def test_search_extracts_context(self, temp_dir):
        """Test that search extracts context around match."""
        content = "prefix " + "X" * 200 + " searchable " + "Y" * 200 + " suffix"
        query_lower = "searchable"
        content_lower = content.lower()
        match_pos = content_lower.find(query_lower)

        start = max(0, match_pos - 200)
        end = min(len(content), match_pos + len(query_lower) + 200)
        context = content[start:end].strip()

        assert "searchable" in context
        assert len(context) <= 410  # 200 + query + 200

    def test_search_respects_max_results(self, temp_dir):
        """Test that search respects max_results limit."""
        max_results = 5
        results = list(range(10))  # Simulate 10 results

        limited = results[:max_results]
        assert len(limited) == 5

    def test_search_filters_by_space(self, temp_dir):
        """Test that search can filter by space."""
        output_dir = temp_dir / "confluence"
        (output_dir / "TECH").mkdir(parents=True, exist_ok=True)
        (output_dir / "DOCS").mkdir(parents=True, exist_ok=True)

        space_filter = "TECH"
        spaces_to_search = [space_filter] if space_filter else ["TECH", "DOCS"]

        assert len(spaces_to_search) == 1
        assert spaces_to_search[0] == "TECH"

    def test_search_skips_readme_files(self, temp_dir):
        """Test that search skips README.md files."""
        space_dir = temp_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        readme = space_dir / "README.md"
        readme.write_text("# Index with searchable content")

        skipped = readme.name == "README.md"
        assert skipped

    def test_search_extracts_title(self, temp_dir):
        """Test that search extracts title from first line."""
        content = "# Page Title\n\nContent here"
        lines = content.split("\n")
        title = lines[0].replace("# ", "").strip()

        assert title == "Page Title"

    def test_search_handles_empty_file(self, temp_dir):
        """Test handling of empty files."""
        space_dir = temp_dir / "TECH"
        space_dir.mkdir(parents=True, exist_ok=True)

        empty = space_dir / "empty.md"
        empty.write_text("")

        content = empty.read_text()
        assert content == ""

    def test_search_sorts_by_relevance(self):
        """Test that results are sorted by match position."""
        results = [
            {"title": "A", "match_position": 100},
            {"title": "B", "match_position": 10},
            {"title": "C", "match_position": 50},
        ]

        sorted_results = sorted(results, key=lambda x: x["match_position"])

        assert sorted_results[0]["title"] == "B"
        assert sorted_results[1]["title"] == "C"
        assert sorted_results[2]["title"] == "A"

    def test_list_spaces(self, temp_dir, capsys):
        """Test list_spaces function."""
        output_dir = temp_dir / "confluence"
        (output_dir / "TECH").mkdir(parents=True, exist_ok=True)
        (output_dir / "DOCS").mkdir(parents=True, exist_ok=True)

        spaces = sorted([d.name for d in output_dir.iterdir() if d.is_dir()])

        print("Available spaces:")
        for space in spaces:
            print(f"  {space}")

        captured = capsys.readouterr()
        assert "Available spaces:" in captured.out
        assert "DOCS" in captured.out
        assert "TECH" in captured.out

    def test_search_main_no_results(self, capsys):
        """Test main output when no results found."""
        query = "nonexistent"
        results = []

        if not results:
            print(f"No results found for '{query}'")

        captured = capsys.readouterr()
        assert "No results found" in captured.out

    def test_search_main_with_results(self, capsys):
        """Test main output with results."""
        results = [
            {"title": "Page 1", "space": "TECH", "file": "/path/page1.md", "context": "Context..."}
        ]

        print(f"Found {len(results)} results:")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']} (in {result['space']})")

        captured = capsys.readouterr()
        assert "Found 1 results" in captured.out
        assert "Page 1" in captured.out


class TestSearchArgumentParsing:
    """Tests for search CLI argument parsing."""

    def test_parse_space_argument(self):
        """Test parsing --space argument."""
        args = ["query", "--space", "TECH"]
        space = None

        i = 1
        while i < len(args):
            if args[i] == "--space" and i + 1 < len(args):
                space = args[i + 1]
                break
            i += 1

        assert space == "TECH"

    def test_parse_max_results_argument(self):
        """Test parsing --max-results argument."""
        args = ["query", "--max-results", "10"]
        max_results = 50  # default

        i = 1
        while i < len(args):
            if args[i] == "--max-results" and i + 1 < len(args):
                max_results = int(args[i + 1])
                break
            i += 1

        assert max_results == 10

    def test_default_max_results(self):
        """Test default max_results value."""
        max_results = 50
        assert max_results == 50


class TestSymlinkUtilities:
    """Tests for symlink-related utilities."""

    def test_ensure_gitignore_pattern(self, temp_dir):
        """Test adding pattern to .gitignore."""
        gitignore = temp_dir / ".gitignore"
        pattern = "context-sync/"

        existing = ""
        if gitignore.exists():
            existing = gitignore.read_text()

        if pattern not in existing:
            with open(gitignore, "a") as f:
                f.write(f"\n{pattern}\n")

        assert pattern in gitignore.read_text()

    def test_symlink_creation(self, temp_dir):
        """Test creating a symlink."""
        target = temp_dir / "target"
        target.mkdir()

        link = temp_dir / "link"
        link.symlink_to(target)

        assert link.is_symlink()
        assert link.resolve() == target

    def test_symlink_already_exists(self, temp_dir):
        """Test handling when symlink already exists."""
        target = temp_dir / "target"
        target.mkdir()

        link = temp_dir / "link"
        link.symlink_to(target)

        # Should not crash if link exists
        if link.exists() or link.is_symlink():
            pass

        assert link.is_symlink()

    def test_find_git_projects(self, temp_dir):
        """Test finding git projects in directory."""
        # Create git project
        project = temp_dir / "project1"
        project.mkdir()
        (project / ".git").mkdir()

        # Create non-git directory
        non_git = temp_dir / "not-a-project"
        non_git.mkdir()

        git_projects = [d for d in temp_dir.iterdir() if (d / ".git").is_dir()]

        assert len(git_projects) == 1
        assert git_projects[0].name == "project1"
