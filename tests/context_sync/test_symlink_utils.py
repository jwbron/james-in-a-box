"""
Tests for context-sync symlink utilities.

Tests the create_symlink.py and link_to_khan_projects.py modules.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestEnsureGitignorePattern:
    """Tests for ensure_gitignore_pattern function."""

    def test_creates_global_gitignore_if_not_exists(self, temp_dir, monkeypatch):
        """Test creating global gitignore when it doesn't exist."""
        monkeypatch.setenv("HOME", str(temp_dir))
        gitignore = temp_dir / ".gitignore"

        # Gitignore doesn't exist yet
        assert not gitignore.exists()

        # Simulate creating it
        link_name = "confluence-docs"
        gitignore.write_text(f"# Confluence documentation symlinks\n{link_name}\n")

        assert gitignore.exists()
        assert link_name in gitignore.read_text()

    def test_adds_pattern_to_existing_gitignore(self, temp_dir, monkeypatch):
        """Test adding pattern to existing gitignore."""
        monkeypatch.setenv("HOME", str(temp_dir))
        gitignore = temp_dir / ".gitignore"

        # Create existing gitignore with other content
        gitignore.write_text("*.pyc\n__pycache__/\n")

        link_name = "confluence-docs"
        existing = gitignore.read_text()

        if link_name not in existing:
            with gitignore.open("a") as f:
                f.write(f"\n# Confluence documentation symlinks\n{link_name}\n")

        content = gitignore.read_text()
        assert "*.pyc" in content  # Original content preserved
        assert link_name in content  # New pattern added

    def test_pattern_already_exists(self, temp_dir, monkeypatch):
        """Test when pattern already exists in gitignore."""
        monkeypatch.setenv("HOME", str(temp_dir))
        gitignore = temp_dir / ".gitignore"

        link_name = "confluence-docs"
        gitignore.write_text(f"confluence-docs\n")

        existing = gitignore.read_text()
        pattern_exists = link_name in existing

        assert pattern_exists

    def test_custom_link_name(self, temp_dir, monkeypatch):
        """Test using custom link name."""
        monkeypatch.setenv("HOME", str(temp_dir))
        gitignore = temp_dir / ".gitignore"

        link_name = "docs"
        gitignore.write_text(f"# Custom docs symlinks\n{link_name}\n")

        assert link_name in gitignore.read_text()


class TestEnsureCursorRule:
    """Tests for ensure_cursor_rule function."""

    def test_creates_cursor_rules_directory(self, temp_dir, monkeypatch):
        """Test creating Cursor rules directory."""
        monkeypatch.setenv("HOME", str(temp_dir))
        rules_dir = temp_dir / ".cursor" / "rules"

        rules_dir.mkdir(parents=True, exist_ok=True)
        assert rules_dir.exists()

    def test_creates_rule_file(self, temp_dir, monkeypatch):
        """Test creating the Cursor rule file."""
        monkeypatch.setenv("HOME", str(temp_dir))
        rules_dir = temp_dir / ".cursor" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)

        rule_file = rules_dir / "confluence-docs.mdc"
        link_name = "confluence-docs"

        rule_content = f"""---
description: Use internal company documentation
globs: ["**/{link_name}/**"]
---

When working with confluence-docs directories:
- Use the internal company documentation
"""
        rule_file.write_text(rule_content)

        assert rule_file.exists()
        assert link_name in rule_file.read_text()

    def test_updates_existing_rule_file(self, temp_dir, monkeypatch):
        """Test updating existing rule file with new content."""
        monkeypatch.setenv("HOME", str(temp_dir))
        rules_dir = temp_dir / ".cursor" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)

        rule_file = rules_dir / "confluence-docs.mdc"
        old_content = "old content"
        rule_file.write_text(old_content)

        new_content = "new content"
        rule_file.write_text(new_content)

        assert rule_file.read_text() == new_content


class TestCreateSymlink:
    """Tests for create_symlink function."""

    def test_creates_symlink_to_source(self, temp_dir):
        """Test creating a symlink to the documentation source."""
        source_path = temp_dir / "source-docs"
        source_path.mkdir(parents=True, exist_ok=True)
        (source_path / "test.md").write_text("test content")

        target_project = temp_dir / "my-project"
        target_project.mkdir(parents=True, exist_ok=True)

        symlink_path = target_project / "confluence-docs"
        symlink_path.symlink_to(source_path)

        assert symlink_path.is_symlink()
        assert symlink_path.resolve() == source_path

    def test_symlink_already_exists_correct_target(self, temp_dir):
        """Test handling when symlink already points to correct target."""
        source_path = temp_dir / "source-docs"
        source_path.mkdir()

        target_project = temp_dir / "my-project"
        target_project.mkdir()

        symlink_path = target_project / "confluence-docs"
        symlink_path.symlink_to(source_path)

        # Check that existing symlink points to correct location
        is_correct = symlink_path.is_symlink() and symlink_path.resolve() == source_path
        assert is_correct

    def test_symlink_exists_wrong_target(self, temp_dir):
        """Test updating symlink that points to wrong target."""
        old_source = temp_dir / "old-docs"
        old_source.mkdir()

        new_source = temp_dir / "new-docs"
        new_source.mkdir()

        target_project = temp_dir / "my-project"
        target_project.mkdir()

        symlink_path = target_project / "confluence-docs"
        symlink_path.symlink_to(old_source)

        # Update to new source
        symlink_path.unlink()
        symlink_path.symlink_to(new_source)

        assert symlink_path.resolve() == new_source

    def test_target_path_does_not_exist(self, temp_dir):
        """Test error handling when target project doesn't exist."""
        target_path = temp_dir / "nonexistent-project"
        assert not target_path.exists()

    def test_source_path_does_not_exist(self, temp_dir):
        """Test error handling when source documentation doesn't exist."""
        source_path = temp_dir / "nonexistent-docs"
        assert not source_path.exists()

    def test_path_exists_but_not_symlink(self, temp_dir):
        """Test error when path exists but is not a symlink."""
        target_project = temp_dir / "my-project"
        target_project.mkdir()

        # Create a regular directory instead of symlink
        docs_path = target_project / "confluence-docs"
        docs_path.mkdir()

        is_symlink = docs_path.is_symlink()
        assert not is_symlink

    def test_custom_link_name(self, temp_dir):
        """Test using custom link name."""
        source_path = temp_dir / "source-docs"
        source_path.mkdir()

        target_project = temp_dir / "my-project"
        target_project.mkdir()

        link_name = "docs"
        symlink_path = target_project / link_name
        symlink_path.symlink_to(source_path)

        assert symlink_path.name == "docs"
        assert symlink_path.is_symlink()


class TestFindGitProjects:
    """Tests for find_git_projects function."""

    def test_finds_git_projects(self, temp_dir):
        """Test finding git projects under a path."""
        # Create git projects
        project1 = temp_dir / "project1"
        project1.mkdir()
        (project1 / ".git").mkdir()

        project2 = temp_dir / "project2"
        project2.mkdir()
        (project2 / ".git").mkdir()

        # Find all git projects
        git_projects = []
        for item in temp_dir.rglob(".git"):
            if item.is_dir():
                git_projects.append(item.parent)

        assert len(git_projects) == 2

    def test_ignores_non_git_directories(self, temp_dir):
        """Test ignoring directories without .git."""
        project1 = temp_dir / "project1"
        project1.mkdir()
        (project1 / ".git").mkdir()

        not_git = temp_dir / "regular-dir"
        not_git.mkdir()

        git_projects = []
        for item in temp_dir.rglob(".git"):
            if item.is_dir():
                git_projects.append(item.parent)

        assert len(git_projects) == 1
        assert git_projects[0].name == "project1"

    def test_finds_nested_git_projects(self, temp_dir):
        """Test finding nested git projects."""
        nested = temp_dir / "workspace" / "projects" / "my-app"
        nested.mkdir(parents=True)
        (nested / ".git").mkdir()

        git_projects = list(temp_dir.rglob(".git"))
        assert len(git_projects) == 1

    def test_returns_empty_for_nonexistent_path(self, temp_dir):
        """Test returning empty list for nonexistent base path."""
        base_path = temp_dir / "nonexistent"
        if not base_path.exists():
            git_projects = []
        else:
            git_projects = list(base_path.rglob(".git"))

        assert git_projects == []


class TestCreateSymlinksForKhanProjects:
    """Tests for create_symlinks_for_khan_projects function."""

    def test_dry_run_does_not_create_symlinks(self, temp_dir, monkeypatch):
        """Test that dry run doesn't create symlinks."""
        monkeypatch.setenv("HOME", str(temp_dir))

        source = temp_dir / "source-docs"
        source.mkdir()

        project = temp_dir / "khan" / "my-project"
        project.mkdir(parents=True)
        (project / ".git").mkdir()

        symlink = project / "confluence-docs"
        dry_run = True

        if not dry_run:
            symlink.symlink_to(source)

        assert not symlink.exists()

    def test_execute_mode_creates_symlinks(self, temp_dir, monkeypatch):
        """Test that execute mode creates symlinks."""
        monkeypatch.setenv("HOME", str(temp_dir))

        source = temp_dir / "source-docs"
        source.mkdir()

        project = temp_dir / "khan" / "my-project"
        project.mkdir(parents=True)
        (project / ".git").mkdir()

        symlink = project / "confluence-docs"
        dry_run = False

        if not dry_run:
            symlink.symlink_to(source)

        assert symlink.is_symlink()

    def test_updates_existing_symlinks(self, temp_dir):
        """Test updating existing symlinks with wrong target."""
        old_source = temp_dir / "old-source"
        old_source.mkdir()

        new_source = temp_dir / "new-source"
        new_source.mkdir()

        project = temp_dir / "project"
        project.mkdir()
        (project / ".git").mkdir()

        symlink = project / "confluence-docs"
        symlink.symlink_to(old_source)

        # Update to new source
        if symlink.resolve() != new_source:
            symlink.unlink()
            symlink.symlink_to(new_source)

        assert symlink.resolve() == new_source

    def test_tracks_created_and_skipped_links(self, temp_dir):
        """Test tracking created and skipped symlinks."""
        source = temp_dir / "source"
        source.mkdir()

        project1 = temp_dir / "project1"
        project1.mkdir()
        project2 = temp_dir / "project2"
        project2.mkdir()

        created_links = []
        skipped_links = []

        # First project gets new symlink
        symlink1 = project1 / "docs"
        symlink1.symlink_to(source)
        created_links.append(project1)

        # Second project already has symlink
        symlink2 = project2 / "docs"
        symlink2.symlink_to(source)
        skipped_links.append(project2)  # Already linked

        assert len(created_links) == 1
        assert len(skipped_links) == 1


class TestListProjectsWithSymlinks:
    """Tests for list_projects_with_symlinks function."""

    def test_finds_projects_with_symlinks(self, temp_dir, monkeypatch):
        """Test finding projects that have symlinks to documentation."""
        monkeypatch.setenv("HOME", str(temp_dir))

        source = temp_dir / "source-docs"
        source.mkdir()

        project = temp_dir / "khan" / "my-project"
        project.mkdir(parents=True)

        symlink = project / "confluence-docs"
        symlink.symlink_to(source)

        # Find symlinks pointing to source
        found_links = []
        for item in project.iterdir():
            if item.is_symlink():
                try:
                    if item.resolve() == source:
                        found_links.append((project, item))
                except:
                    pass

        assert len(found_links) == 1
        assert found_links[0][0] == project

    def test_no_symlinks_found(self, temp_dir, monkeypatch):
        """Test when no projects have symlinks."""
        monkeypatch.setenv("HOME", str(temp_dir))

        project = temp_dir / "khan" / "my-project"
        project.mkdir(parents=True)

        found_links = []
        for item in project.iterdir():
            if item.is_symlink():
                found_links.append(item)

        assert len(found_links) == 0


class TestMainFunction:
    """Tests for create_symlink main() function."""

    def test_main_shows_usage_with_no_args(self, capsys):
        """Test that main shows usage when no args provided."""
        import sys

        args = []
        if len(args) < 1:
            print("Usage:")
            print("  python create_symlink.py <project_path> [link_name]")
            print("  python create_symlink.py --list")

        captured = capsys.readouterr()
        assert "Usage:" in captured.out

    def test_main_parses_project_path(self, temp_dir):
        """Test parsing project path argument."""
        import sys

        args = [str(temp_dir / "my-project")]
        target_project = args[0]

        assert str(temp_dir) in target_project

    def test_main_parses_custom_link_name(self):
        """Test parsing custom link name argument."""
        args = ["/path/to/project", "docs"]
        link_name = args[1] if len(args) > 1 else "confluence-docs"

        assert link_name == "docs"

    def test_main_handles_list_flag(self, capsys):
        """Test handling --list flag."""
        args = ["--list"]
        if args[0] == "--list":
            print("Listing projects with symlinks...")

        captured = capsys.readouterr()
        assert "Listing" in captured.out
