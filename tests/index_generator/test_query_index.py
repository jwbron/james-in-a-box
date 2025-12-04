"""
Tests for the codebase index query tool.
"""

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest


# Add the module path for import
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "host-services" / "analysis" / "index-generator"))

# Import the module using its new Python-safe name
from importlib import import_module

query_index = import_module("query-index")


class TestLoadIndex:
    """Tests for load_index function."""

    def test_loads_valid_json(self, temp_dir):
        """Test loading a valid JSON index file."""
        index_file = temp_dir / "test.json"
        data = {"key": "value", "number": 42}
        index_file.write_text(json.dumps(data))

        result = query_index.load_index(index_file)

        assert result == data

    def test_exits_on_missing_file(self, temp_dir):
        """Test that missing file causes exit."""
        missing_file = temp_dir / "nonexistent.json"

        with pytest.raises(SystemExit) as exc_info:
            query_index.load_index(missing_file)

        assert exc_info.value.code == 1


class TestCmdComponent:
    """Tests for cmd_component function."""

    def test_finds_matching_component(self, temp_dir, capsys):
        """Test finding a component by name."""
        codebase = {
            "components": [
                {
                    "name": "GitHubWatcher",
                    "type": "class",
                    "file": "watchers/github.py",
                    "line": 10,
                },
                {
                    "name": "SlackConnector",
                    "type": "class",
                    "file": "connectors/slack.py",
                    "line": 5,
                },
            ]
        }
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))

        args = Namespace(name="GitHub")
        query_index.cmd_component(args, temp_dir)

        captured = capsys.readouterr()
        assert "GitHubWatcher" in captured.out
        assert "watchers/github.py" in captured.out
        assert "SlackConnector" not in captured.out

    def test_no_matches_message(self, temp_dir, capsys):
        """Test message when no components match."""
        codebase = {
            "components": [{"name": "Other", "type": "class", "file": "other.py", "line": 1}]
        }
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))

        args = Namespace(name="NonExistent")
        query_index.cmd_component(args, temp_dir)

        captured = capsys.readouterr()
        assert "No components found" in captured.out

    def test_shows_description_and_methods(self, temp_dir, capsys):
        """Test that description and methods are displayed."""
        codebase = {
            "components": [
                {
                    "name": "MyClass",
                    "type": "class",
                    "file": "test.py",
                    "line": 1,
                    "description": "A test class for something",
                    "methods": ["method_a", "method_b", "method_c"],
                }
            ]
        }
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))

        args = Namespace(name="MyClass")
        query_index.cmd_component(args, temp_dir)

        captured = capsys.readouterr()
        assert "A test class" in captured.out
        assert "method_a" in captured.out


class TestCmdPattern:
    """Tests for cmd_pattern function."""

    def test_lists_all_patterns(self, temp_dir, capsys):
        """Test listing all patterns when no name specified."""
        patterns = {
            "patterns": {
                "connector": {
                    "description": "Service connectors",
                    "examples": ["a.py:1", "b.py:2"],
                },
                "notification": {"description": "Notifications", "examples": ["c.py:3"]},
            }
        }
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))

        args = Namespace(name=None)
        query_index.cmd_pattern(args, temp_dir)

        captured = capsys.readouterr()
        assert "connector" in captured.out
        assert "notification" in captured.out
        assert "2 examples" in captured.out
        assert "1 examples" in captured.out

    def test_shows_specific_pattern(self, temp_dir, capsys):
        """Test showing details for a specific pattern."""
        patterns = {
            "patterns": {
                "connector": {
                    "description": "Service integration connectors",
                    "examples": ["connectors/slack.py:10", "connectors/jira.py:15"],
                    "conventions": ["Use base class", "Handle auth"],
                }
            }
        }
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))

        args = Namespace(name="connector")
        query_index.cmd_pattern(args, temp_dir)

        captured = capsys.readouterr()
        assert "Pattern: connector" in captured.out
        assert "Service integration connectors" in captured.out
        assert "connectors/slack.py:10" in captured.out
        assert "Use base class" in captured.out

    def test_pattern_not_found(self, temp_dir, capsys):
        """Test message when pattern not found."""
        patterns = {"patterns": {"connector": {"description": "test", "examples": []}}}
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))

        args = Namespace(name="nonexistent")
        query_index.cmd_pattern(args, temp_dir)

        captured = capsys.readouterr()
        assert "not found" in captured.out
        assert "connector" in captured.out  # Shows available patterns


class TestCmdDeps:
    """Tests for cmd_deps function."""

    def test_shows_external_deps(self, temp_dir, capsys):
        """Test showing external dependencies."""
        deps = {
            "external": {
                "requests": "2.31.0",
                "flask": "2.0.0",
                "yaml": "6.0",
            },
            "internal": {},
        }
        (temp_dir / "dependencies.json").write_text(json.dumps(deps))

        args = Namespace(component=None)
        query_index.cmd_deps(args, temp_dir)

        captured = capsys.readouterr()
        assert "requests" in captured.out
        assert "2.31.0" in captured.out
        assert "flask" in captured.out

    def test_shows_internal_deps_for_component(self, temp_dir, capsys):
        """Test showing internal deps for a specific component."""
        deps = {
            "external": {},
            "internal": {
                "config/loader.py": ["utils.helpers", "core.base"],
            },
        }
        (temp_dir / "dependencies.json").write_text(json.dumps(deps))

        args = Namespace(component="config/loader.py")
        query_index.cmd_deps(args, temp_dir)

        captured = capsys.readouterr()
        assert "utils.helpers" in captured.out
        assert "core.base" in captured.out

    def test_component_not_found(self, temp_dir, capsys):
        """Test message when component not found in internal deps."""
        deps = {"external": {}, "internal": {}}
        (temp_dir / "dependencies.json").write_text(json.dumps(deps))

        args = Namespace(component="nonexistent.py")
        query_index.cmd_deps(args, temp_dir)

        captured = capsys.readouterr()
        assert "No internal dependencies found" in captured.out


class TestCmdStructure:
    """Tests for cmd_structure function."""

    def test_shows_project_structure(self, temp_dir, capsys):
        """Test displaying project structure."""
        codebase = {
            "project": "test-project",
            "structure": {
                "description": "Root",
                "children": {
                    "src/": {
                        "description": "Source code",
                        "children": {
                            "utils/": {"description": "Utilities"},
                        },
                    },
                    "tests/": {"description": "Test suite"},
                },
            },
        }
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))

        args = Namespace()
        query_index.cmd_structure(args, temp_dir)

        captured = capsys.readouterr()
        assert "test-project" in captured.out
        assert "src/" in captured.out
        assert "utils/" in captured.out
        assert "tests/" in captured.out


class TestCmdSummary:
    """Tests for cmd_summary function."""

    def test_shows_codebase_summary(self, temp_dir, capsys):
        """Test displaying codebase summary."""
        codebase = {
            "project": "my-project",
            "generated": "2025-01-01T00:00:00",
            "summary": {
                "total_python_files": 50,
                "total_classes": 25,
                "total_functions": 100,
            },
        }
        patterns = {"patterns": {"connector": {}, "notification": {}}}
        deps = {"external": {"requests": "2.31.0", "flask": "2.0.0"}, "internal": {}}

        (temp_dir / "codebase.json").write_text(json.dumps(codebase))
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))
        (temp_dir / "dependencies.json").write_text(json.dumps(deps))

        args = Namespace()
        query_index.cmd_summary(args, temp_dir)

        captured = capsys.readouterr()
        assert "my-project" in captured.out
        assert "50" in captured.out  # Python files
        assert "25" in captured.out  # Classes
        assert "100" in captured.out  # Functions
        assert "connector" in captured.out
        assert "notification" in captured.out


class TestCmdSearch:
    """Tests for cmd_search function."""

    def test_finds_components_by_name(self, temp_dir, capsys):
        """Test searching for components by name."""
        codebase = {
            "components": [
                {"name": "SlackNotifier", "file": "notify.py"},
                {"name": "EmailSender", "file": "email.py"},
            ]
        }
        patterns = {"patterns": {}}
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))

        args = Namespace(query="slack")
        query_index.cmd_search(args, temp_dir)

        captured = capsys.readouterr()
        assert "SlackNotifier" in captured.out
        assert "EmailSender" not in captured.out

    def test_finds_patterns_by_name(self, temp_dir, capsys):
        """Test searching for patterns."""
        codebase = {"components": []}
        patterns = {
            "patterns": {
                "notification": {"description": "Notification system"},
                "connector": {"description": "Service connectors"},
            }
        }
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))

        args = Namespace(query="notification")
        query_index.cmd_search(args, temp_dir)

        captured = capsys.readouterr()
        assert "[pattern" in captured.out
        assert "notification" in captured.out

    def test_no_results_message(self, temp_dir, capsys):
        """Test message when no results found."""
        codebase = {"components": []}
        patterns = {"patterns": {}}
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))

        args = Namespace(query="nonexistent")
        query_index.cmd_search(args, temp_dir)

        captured = capsys.readouterr()
        assert "No results found" in captured.out

    def test_searches_descriptions(self, temp_dir, capsys):
        """Test that search also matches descriptions."""
        codebase = {
            "components": [
                {"name": "MyClass", "description": "Handles slack notifications"},
            ]
        }
        patterns = {"patterns": {}}
        (temp_dir / "codebase.json").write_text(json.dumps(codebase))
        (temp_dir / "patterns.json").write_text(json.dumps(patterns))

        args = Namespace(query="slack")
        query_index.cmd_search(args, temp_dir)

        captured = capsys.readouterr()
        assert "MyClass" in captured.out
