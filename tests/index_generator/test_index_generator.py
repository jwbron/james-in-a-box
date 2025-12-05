"""
Tests for the codebase index generator.
"""

import json

# Import will work due to conftest.py sys.path setup
from importlib import import_module
from textwrap import dedent


# Import the module from its new location in jib-container/jib-tasks/analysis/utilities/
index_generator = import_module("index_generator")
CodebaseIndexer = index_generator.CodebaseIndexer


class TestCodebaseIndexerInit:
    """Tests for CodebaseIndexer initialization."""

    def test_init_sets_paths(self, temp_dir):
        """Test that init sets project_root and output_dir correctly."""
        output_dir = temp_dir / "output"
        indexer = CodebaseIndexer(temp_dir, output_dir)

        assert indexer.project_root == temp_dir.resolve()
        assert indexer.output_dir == output_dir.resolve()
        assert indexer.project_name == temp_dir.name

    def test_init_creates_empty_collections(self, temp_dir):
        """Test that init creates empty data collections."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        assert indexer.structure == {}
        assert indexer.components == []
        assert indexer.external_deps == {}


class TestStdlibDetection:
    """Tests for stdlib module detection."""

    def test_stdlib_modules_contains_common_modules(self):
        """Test that STDLIB_MODULES includes common stdlib modules."""
        stdlib = CodebaseIndexer.STDLIB_MODULES

        # Common stdlib modules should be present
        assert "os" in stdlib
        assert "sys" in stdlib
        assert "json" in stdlib
        assert "pathlib" in stdlib
        assert "typing" in stdlib
        assert "logging" in stdlib
        assert "collections" in stdlib
        assert "datetime" in stdlib
        assert "unittest" in stdlib

    def test_stdlib_modules_excludes_third_party(self):
        """Test that STDLIB_MODULES doesn't include third-party packages."""
        stdlib = CodebaseIndexer.STDLIB_MODULES

        # Third-party packages should NOT be in stdlib
        assert "requests" not in stdlib
        assert "pytest" not in stdlib
        assert "flask" not in stdlib
        assert "django" not in stdlib
        assert "numpy" not in stdlib


class TestPackageImportMap:
    """Tests for package name to import name mapping."""

    def test_common_mappings_present(self):
        """Test that common package->import mappings are defined."""
        mapping = CodebaseIndexer.PACKAGE_IMPORT_MAP

        assert mapping.get("pyyaml") == "yaml"
        assert mapping.get("python-dotenv") == "dotenv"
        assert mapping.get("pyjwt") == "jwt"
        assert mapping.get("pillow") == "PIL"


class TestCategorizeImport:
    """Tests for _categorize_import method."""

    def test_stdlib_imports_skipped(self, temp_dir):
        """Test that stdlib imports are not added to either list."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        file_info = {"imports": {"internal": [], "external": []}}

        indexer._categorize_import("os", file_info)
        indexer._categorize_import("sys", file_info)
        indexer._categorize_import("json", file_info)

        assert file_info["imports"]["internal"] == []
        assert file_info["imports"]["external"] == []
        assert indexer.external_deps == {}

    def test_relative_imports_are_internal(self, temp_dir):
        """Test that relative imports (.module) are categorized as internal."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        file_info = {"imports": {"internal": [], "external": []}}

        indexer._categorize_import(".utils", file_info)
        indexer._categorize_import("..config", file_info)

        assert ".utils" in file_info["imports"]["internal"]
        assert "..config" in file_info["imports"]["internal"]
        assert file_info["imports"]["external"] == []

    def test_third_party_imports_are_external(self, temp_dir):
        """Test that third-party packages are categorized as external."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        file_info = {"imports": {"internal": [], "external": []}}

        indexer._categorize_import("requests", file_info)
        indexer._categorize_import("flask", file_info)

        assert "requests" in file_info["imports"]["external"]
        assert "flask" in file_info["imports"]["external"]
        assert "requests" in indexer.external_deps
        assert "flask" in indexer.external_deps

    def test_submodule_imports_use_package_name(self, temp_dir):
        """Test that submodule imports use the top-level package name."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        file_info = {"imports": {"internal": [], "external": []}}

        indexer._categorize_import("requests.auth", file_info)
        indexer._categorize_import("flask.views", file_info)

        assert "requests" in file_info["imports"]["external"]
        assert "flask" in file_info["imports"]["external"]
        # Should not have the submodule names
        assert "requests.auth" not in file_info["imports"]["external"]


class TestIsInternalModule:
    """Tests for _is_internal_module method."""

    def test_detects_existing_py_file(self, temp_dir):
        """Test that existing .py files are detected as internal."""
        # Create a Python file
        (temp_dir / "utils.py").write_text("# utils module")

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        assert indexer._is_internal_module("utils") is True
        assert indexer._is_internal_module("nonexistent") is False

    def test_detects_package_with_init(self, temp_dir):
        """Test that packages with __init__.py are detected as internal."""
        # Create a package
        pkg_dir = temp_dir / "mypackage"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("# package init")

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        assert indexer._is_internal_module("mypackage") is True

    def test_ignores_skip_dirs(self, temp_dir):
        """Test that modules in skip directories are not detected."""
        # Create file in __pycache__ (should be ignored)
        cache_dir = temp_dir / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "utils.py").write_text("# cached")

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        # utils.py is only in __pycache__, should not be found
        assert indexer._is_internal_module("utils") is False


class TestDetectPatterns:
    """Tests for _detect_patterns method."""

    def test_detects_connector_pattern(self, temp_dir):
        """Test that connector pattern is detected from naming."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        indexer._detect_patterns("SlackConnector", "connectors/slack.py", 10, "class")

        assert "connector" in indexer.patterns_found
        assert "connectors/slack.py:10" in indexer.patterns_found["connector"]["examples"]

    def test_detects_notification_pattern(self, temp_dir):
        """Test that notification pattern is detected."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        indexer._detect_patterns("send_notification", "utils/notify.py", 25, "function")

        assert "notification" in indexer.patterns_found

    def test_detects_watcher_pattern(self, temp_dir):
        """Test that event_driven pattern is detected from watcher naming."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        indexer._detect_patterns("GitHubWatcher", "watchers/github.py", 1, "class")

        assert "event_driven" in indexer.patterns_found

    def test_no_duplicate_examples(self, temp_dir):
        """Test that the same example is not added twice."""
        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")

        indexer._detect_patterns("MyConnector", "test.py", 1, "class")
        indexer._detect_patterns("MyConnector", "test.py", 1, "class")

        assert len(indexer.patterns_found["connector"]["examples"]) == 1


class TestExtractVersions:
    """Tests for extract_versions_from_requirements method."""

    def test_extracts_from_requirements_txt(self, temp_dir):
        """Test extracting versions from requirements.txt."""
        req_file = temp_dir / "requirements.txt"
        req_file.write_text(
            dedent("""
            requests==2.31.0
            flask>=2.0.0
            pytest~=7.0
        """).strip()
        )

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        indexer.external_deps = {"requests": "unknown", "flask": "unknown", "pytest": "unknown"}

        indexer.extract_versions_from_requirements()

        assert indexer.external_deps["requests"] == "2.31.0"
        assert indexer.external_deps["flask"] == "2.0.0"
        assert indexer.external_deps["pytest"] == "7.0"

    def test_extracts_from_nested_requirements(self, temp_dir):
        """Test extracting versions from nested requirements files."""
        subdir = temp_dir / "services" / "api"
        subdir.mkdir(parents=True)
        (subdir / "requirements.txt").write_text("requests==2.28.0")

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        indexer.external_deps = {"requests": "unknown"}

        indexer.extract_versions_from_requirements()

        assert indexer.external_deps["requests"] == "2.28.0"

    def test_handles_package_name_mapping(self, temp_dir):
        """Test that package name mapping works (pyyaml -> yaml)."""
        req_file = temp_dir / "requirements.txt"
        req_file.write_text("pyyaml>=6.0\npython-dotenv>=0.19.0")

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        indexer.external_deps = {"yaml": "unknown", "dotenv": "unknown"}

        indexer.extract_versions_from_requirements()

        assert indexer.external_deps["yaml"] == "6.0"
        assert indexer.external_deps["dotenv"] == "0.19.0"


class TestAnalyzePythonFile:
    """Tests for analyze_python_file method."""

    def test_extracts_classes(self, temp_dir):
        """Test that classes are extracted from Python files."""
        py_file = temp_dir / "example.py"
        py_file.write_text(
            dedent('''
            """Example module."""

            class MyClass:
                """A sample class."""

                def method_one(self):
                    pass

                def method_two(self):
                    pass
        ''').strip()
        )

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        file_info = indexer.analyze_python_file(py_file)

        assert len(file_info["classes"]) == 1
        cls = file_info["classes"][0]
        assert cls["name"] == "MyClass"
        assert cls["type"] == "class"
        assert "A sample class" in cls.get("description", "")
        assert "method_one" in cls.get("methods", [])

    def test_extracts_functions(self, temp_dir):
        """Test that top-level functions are extracted."""
        py_file = temp_dir / "funcs.py"
        py_file.write_text(
            dedent('''
            def my_function():
                """Does something useful."""
                pass

            def another_function():
                pass
        ''').strip()
        )

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        file_info = indexer.analyze_python_file(py_file)

        assert len(file_info["functions"]) == 2
        func_names = [f["name"] for f in file_info["functions"]]
        assert "my_function" in func_names
        assert "another_function" in func_names

    def test_extracts_imports(self, temp_dir):
        """Test that imports are categorized correctly."""
        py_file = temp_dir / "imports.py"
        py_file.write_text(
            dedent("""
            import os
            import requests
            from pathlib import Path
            from flask import Flask
        """).strip()
        )

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        file_info = indexer.analyze_python_file(py_file)

        # os and pathlib are stdlib, should not appear
        assert "os" not in file_info["imports"]["external"]
        assert "pathlib" not in file_info["imports"]["external"]

        # requests and flask are external
        assert "requests" in file_info["imports"]["external"]
        assert "flask" in file_info["imports"]["external"]

    def test_handles_syntax_errors(self, temp_dir):
        """Test that syntax errors are handled gracefully."""
        py_file = temp_dir / "bad.py"
        py_file.write_text("def broken(:\n    pass")

        indexer = CodebaseIndexer(temp_dir, temp_dir / "output")
        result = indexer.analyze_python_file(py_file)

        assert result is None


class TestGenerateIndexes:
    """Integration tests for generate_indexes method."""

    def test_generates_all_index_files(self, temp_dir):
        """Test that all three index files are generated."""
        # Create a minimal project structure
        (temp_dir / "main.py").write_text(
            dedent('''
            """Main module."""
            import requests

            class App:
                """Main application."""
                pass

            def run():
                """Run the app."""
                pass
        ''').strip()
        )

        output_dir = temp_dir / "docs" / "generated"
        indexer = CodebaseIndexer(temp_dir, output_dir)
        indexer.generate_indexes()

        assert (output_dir / "codebase.json").exists()
        assert (output_dir / "patterns.json").exists()
        assert (output_dir / "dependencies.json").exists()

    def test_codebase_json_structure(self, temp_dir):
        """Test that codebase.json has expected structure."""
        (temp_dir / "example.py").write_text("class Example: pass")

        output_dir = temp_dir / "output"
        indexer = CodebaseIndexer(temp_dir, output_dir)
        indexer.generate_indexes()

        with open(output_dir / "codebase.json") as f:
            codebase = json.load(f)

        assert "generated" in codebase
        assert "project" in codebase
        assert "structure" in codebase
        assert "components" in codebase
        assert "summary" in codebase

    def test_patterns_json_structure(self, temp_dir):
        """Test that patterns.json has expected structure."""
        (temp_dir / "connector.py").write_text("class MyConnector: pass")

        output_dir = temp_dir / "output"
        indexer = CodebaseIndexer(temp_dir, output_dir)
        indexer.generate_indexes()

        with open(output_dir / "patterns.json") as f:
            patterns = json.load(f)

        assert "generated" in patterns
        assert "project" in patterns
        assert "patterns" in patterns

    def test_dependencies_json_structure(self, temp_dir):
        """Test that dependencies.json has expected structure."""
        (temp_dir / "deps.py").write_text("import requests")

        output_dir = temp_dir / "output"
        indexer = CodebaseIndexer(temp_dir, output_dir)
        indexer.generate_indexes()

        with open(output_dir / "dependencies.json") as f:
            deps = json.load(f)

        assert "generated" in deps
        assert "project" in deps
        assert "internal" in deps
        assert "external" in deps
