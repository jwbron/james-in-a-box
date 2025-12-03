#!/usr/bin/env python3
"""
Codebase Index Generator for LLM Documentation Strategy

Generates machine-readable indexes of the codebase for efficient LLM navigation:
- codebase.json: Structured project layout with components
- patterns.json: Extracted code patterns and conventions
- dependencies.json: Internal and external dependency graph

Per ADR: LLM Documentation Index Strategy (Phase 2)
"""

import ast
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CodebaseIndexer:
    """Analyzes a codebase and generates structured indexes."""

    # File extensions to analyze
    PYTHON_EXTENSIONS = {".py"}
    SHELL_EXTENSIONS = {".sh"}
    CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml"}
    DOC_EXTENSIONS = {".md"}

    # Directories to skip
    SKIP_DIRS = {
        "__pycache__",
        ".git",
        ".pytest_cache",
        "node_modules",
        ".mypy_cache",
        ".tox",
        "venv",
        ".venv",
        "env",
        ".env",
        "build",
        "dist",
        "*.egg-info",
    }

    # Package name to import name mappings (package -> import)
    # Used when PyPI package name differs from import name
    PACKAGE_IMPORT_MAP = {
        "pyyaml": "yaml",
        "python-dotenv": "dotenv",
        "pyjwt": "jwt",
        "pillow": "PIL",
        "scikit-learn": "sklearn",
        "beautifulsoup4": "bs4",
        "opencv-python": "cv2",
    }

    # Python standard library modules (Python 3.10+)
    STDLIB_MODULES = {
        "abc",
        "aifc",
        "argparse",
        "array",
        "ast",
        "asynchat",
        "asyncio",
        "asyncore",
        "atexit",
        "audioop",
        "base64",
        "bdb",
        "binascii",
        "binhex",
        "bisect",
        "builtins",
        "bz2",
        "calendar",
        "cgi",
        "cgitb",
        "chunk",
        "cmath",
        "cmd",
        "code",
        "codecs",
        "codeop",
        "collections",
        "colorsys",
        "compileall",
        "concurrent",
        "configparser",
        "contextlib",
        "contextvars",
        "copy",
        "copyreg",
        "cProfile",
        "crypt",
        "csv",
        "ctypes",
        "curses",
        "dataclasses",
        "datetime",
        "dbm",
        "decimal",
        "difflib",
        "dis",
        "distutils",
        "doctest",
        "email",
        "encodings",
        "enum",
        "errno",
        "faulthandler",
        "fcntl",
        "filecmp",
        "fileinput",
        "fnmatch",
        "fractions",
        "ftplib",
        "functools",
        "gc",
        "getopt",
        "getpass",
        "gettext",
        "glob",
        "graphlib",
        "grp",
        "gzip",
        "hashlib",
        "heapq",
        "hmac",
        "html",
        "http",
        "idlelib",
        "imaplib",
        "imghdr",
        "imp",
        "importlib",
        "inspect",
        "io",
        "ipaddress",
        "itertools",
        "json",
        "keyword",
        "lib2to3",
        "linecache",
        "locale",
        "logging",
        "lzma",
        "mailbox",
        "mailcap",
        "marshal",
        "math",
        "mimetypes",
        "mmap",
        "modulefinder",
        "multiprocessing",
        "netrc",
        "nis",
        "nntplib",
        "numbers",
        "operator",
        "optparse",
        "os",
        "ossaudiodev",
        "pathlib",
        "pdb",
        "pickle",
        "pickletools",
        "pipes",
        "pkgutil",
        "platform",
        "plistlib",
        "poplib",
        "posix",
        "posixpath",
        "pprint",
        "profile",
        "pstats",
        "pty",
        "pwd",
        "py_compile",
        "pyclbr",
        "pydoc",
        "queue",
        "quopri",
        "random",
        "re",
        "readline",
        "reprlib",
        "resource",
        "rlcompleter",
        "runpy",
        "sched",
        "secrets",
        "select",
        "selectors",
        "shelve",
        "shlex",
        "shutil",
        "signal",
        "site",
        "smtpd",
        "smtplib",
        "sndhdr",
        "socket",
        "socketserver",
        "spwd",
        "sqlite3",
        "ssl",
        "stat",
        "statistics",
        "string",
        "stringprep",
        "struct",
        "subprocess",
        "sunau",
        "symtable",
        "sys",
        "sysconfig",
        "syslog",
        "tabnanny",
        "tarfile",
        "telnetlib",
        "tempfile",
        "termios",
        "test",
        "textwrap",
        "threading",
        "time",
        "timeit",
        "tkinter",
        "token",
        "tokenize",
        "trace",
        "traceback",
        "tracemalloc",
        "tty",
        "turtle",
        "turtledemo",
        "types",
        "typing",
        "unicodedata",
        "unittest",
        "urllib",
        "uu",
        "uuid",
        "venv",
        "warnings",
        "wave",
        "weakref",
        "webbrowser",
        "winreg",
        "winsound",
        "wsgiref",
        "xdrlib",
        "xml",
        "xmlrpc",
        "zipapp",
        "zipfile",
        "zipimport",
        "zlib",
        "zoneinfo",
        # Also include common submodules
        "collections.abc",
        "concurrent.futures",
        "os.path",
        "urllib.parse",
        "urllib.request",
        "xml.etree",
        "xml.etree.ElementTree",
    }

    # Known patterns to detect
    PATTERNS = {
        "event_driven": {
            "indicators": ["watcher", "observer", "listener", "handler", "on_"],
            "description": "Event-driven architecture with watchers and handlers",
        },
        "connector": {
            "indicators": ["connector", "client", "adapter", "Connector"],
            "description": "External service integration via connectors",
        },
        "processor": {
            "indicators": ["processor", "Processor", "process_"],
            "description": "Data processing pipelines",
        },
        "notification": {
            "indicators": ["notify", "notification", "alert", "slack"],
            "description": "Notification and alerting system",
        },
        "sync": {
            "indicators": ["sync", "Sync", "synchronize"],
            "description": "Data synchronization patterns",
        },
        "config": {
            "indicators": ["config", "Config", "settings", "Settings"],
            "description": "Configuration management",
        },
    }

    def __init__(self, project_root: Path, output_dir: Path):
        self.project_root = project_root.resolve()
        self.output_dir = output_dir.resolve()
        self.project_name = self.project_root.name

        # Collected data
        self.structure: dict[str, Any] = {}
        self.components: list[dict] = []
        self.patterns_found: dict[str, dict] = defaultdict(
            lambda: {"description": "", "examples": [], "conventions": []}
        )
        self.internal_deps: dict[str, list] = defaultdict(list)
        self.external_deps: dict[str, str] = {}

    def should_skip_dir(self, dir_name: str) -> bool:
        """Check if directory should be skipped."""
        return dir_name in self.SKIP_DIRS or dir_name.startswith(".")

    def get_directory_description(self, dir_path: Path) -> str:
        """Infer directory purpose from name and contents."""
        name = dir_path.name

        # Known directory patterns
        descriptions = {
            "host-services": "Services running on the host machine",
            "analysis": "Code and conversation analysis tools",
            "slack": "Slack integration services",
            "sync": "Data synchronization services",
            "utilities": "Utility scripts and tools",
            "jib-container": "Docker container configuration and scripts",
            "jib-tasks": "Tasks executed inside the container",
            "jib-tools": "Tools available inside the container",
            "config": "Configuration files and loaders",
            "shared": "Shared libraries and utilities",
            "tests": "Test suite",
            "docs": "Documentation",
            "connectors": "External service connectors",
            "utils": "Utility functions",
        }

        return descriptions.get(name, f"{name} directory")

    def analyze_python_file(self, file_path: Path) -> dict | None:
        """Parse a Python file and extract components."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"  Warning: Could not parse {file_path}: {e}")
            return None

        rel_path = file_path.relative_to(self.project_root)
        file_info = {
            "path": str(rel_path),
            "classes": [],
            "functions": [],
            "imports": {"internal": [], "external": []},
        }

        # Get module docstring
        module_doc = ast.get_docstring(tree)
        if module_doc:
            file_info["description"] = module_doc.split("\n")[0][:200]

        for node in ast.walk(tree):
            # Extract classes
            if isinstance(node, ast.ClassDef):
                class_info = {
                    "name": node.name,
                    "file": str(rel_path),
                    "line": node.lineno,
                    "type": "class",
                }

                # Get class docstring
                docstring = ast.get_docstring(node)
                if docstring:
                    class_info["description"] = docstring.split("\n")[0][:200]

                # Get base classes
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(
                            f"{base.value.id if hasattr(base.value, 'id') else '...'}.{base.attr}"
                        )
                if bases:
                    class_info["bases"] = bases

                # Get methods
                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                if methods:
                    class_info["methods"] = methods[:10]  # Limit to first 10

                file_info["classes"].append(class_info)

                # Detect patterns
                self._detect_patterns(node.name, str(rel_path), node.lineno, "class")

            # Extract top-level functions
            elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                func_info = {
                    "name": node.name,
                    "file": str(rel_path),
                    "line": node.lineno,
                    "type": "function",
                }

                # Get function docstring
                docstring = ast.get_docstring(node)
                if docstring:
                    func_info["description"] = docstring.split("\n")[0][:200]

                file_info["functions"].append(func_info)

                # Detect patterns
                self._detect_patterns(node.name, str(rel_path), node.lineno, "function")

            # Extract imports
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self._categorize_import(alias.name, file_info)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._categorize_import(node.module, file_info)

        return file_info

    def _categorize_import(self, module_name: str, file_info: dict):
        """Categorize import as internal, external, or stdlib."""
        # Extract package name (first part of module path)
        package = module_name.split(".")[0]

        # Check if it's a stdlib module
        if package in self.STDLIB_MODULES or module_name in self.STDLIB_MODULES:
            return  # Skip stdlib modules entirely

        # Check if it's an internal import (relative or from this project)
        if module_name.startswith((".", self.project_name)):
            if module_name not in file_info["imports"]["internal"]:
                file_info["imports"]["internal"].append(module_name)
        elif self._is_internal_module(package):
            # It's a local module within the project
            if module_name not in file_info["imports"]["internal"]:
                file_info["imports"]["internal"].append(module_name)
        else:
            # External (third-party) import
            if package not in file_info["imports"]["external"]:
                file_info["imports"]["external"].append(package)

            # Track for external deps (we'll try to get versions later)
            if package not in self.external_deps:
                self.external_deps[package] = "unknown"

    def _is_internal_module(self, module_name: str) -> bool:
        """Check if a module exists within the project directory."""
        # Check for module_name.py or module_name/__init__.py anywhere in project
        for py_file in self.project_root.rglob(f"{module_name}.py"):
            if not any(part in self.SKIP_DIRS for part in py_file.parts):
                return True
        for init_file in self.project_root.rglob(f"{module_name}/__init__.py"):
            if not any(part in self.SKIP_DIRS for part in init_file.parts):
                return True
        return False

    def _detect_patterns(self, name: str, file_path: str, line: int, kind: str):
        """Detect code patterns based on naming conventions."""
        name_lower = name.lower()

        for pattern_name, pattern_info in self.PATTERNS.items():
            for indicator in pattern_info["indicators"]:
                if indicator.lower() in name_lower:
                    example = f"{file_path}:{line}"
                    if example not in self.patterns_found[pattern_name]["examples"]:
                        self.patterns_found[pattern_name]["examples"].append(example)
                        self.patterns_found[pattern_name]["description"] = pattern_info[
                            "description"
                        ]
                    break

    def build_structure(self, path: Path, depth: int = 0) -> dict:
        """Recursively build directory structure."""
        if depth > 5:  # Limit depth
            return {}

        structure = {"description": self.get_directory_description(path), "children": {}}

        files = []

        try:
            for item in sorted(path.iterdir()):
                if item.is_dir():
                    if not self.should_skip_dir(item.name):
                        structure["children"][item.name + "/"] = self.build_structure(
                            item, depth + 1
                        )
                elif (
                    item.is_file() and item.suffix in self.PYTHON_EXTENSIONS | self.SHELL_EXTENSIONS
                ):
                    # Track relevant files
                    files.append(item.name)
        except PermissionError:
            pass

        if files:
            structure["files"] = files[:20]  # Limit files shown

        # Remove empty children
        if not structure["children"]:
            del structure["children"]

        return structure

    def extract_versions_from_requirements(self):
        """Try to extract versions from requirements files throughout the project."""
        # Find all requirements files recursively
        req_files = list(self.project_root.rglob("requirements*.txt"))

        # Also check for pyproject.toml files
        pyproject_files = list(self.project_root.rglob("pyproject.toml"))

        # Parse requirements.txt files
        for req_file in req_files:
            # Skip files in ignored directories
            if any(part in self.SKIP_DIRS for part in req_file.parts):
                continue
            try:
                content = req_file.read_text()
                # Match various requirement formats: pkg==1.0, pkg>=1.0, pkg~=1.0
                for match in re.finditer(
                    r"^([a-zA-Z0-9_-]+)[=~><]=?=?([0-9][^\s,;#]*)", content, re.MULTILINE
                ):
                    pkg, version = match.groups()
                    self._update_dep_version(pkg, version)
            except Exception:
                pass

        # Parse pyproject.toml files for dependencies
        for pyproject in pyproject_files:
            if any(part in self.SKIP_DIRS for part in pyproject.parts):
                continue
            try:
                content = pyproject.read_text()
                # Simple regex to find dependencies in pyproject.toml
                # Matches: "package>=1.0" or 'package==1.0' etc.
                for match in re.finditer(
                    r'["\']([a-zA-Z0-9_-]+)[=~><]=?=?([0-9][^"\']*)["\']', content
                ):
                    pkg, version = match.groups()
                    self._update_dep_version(pkg, version)
            except Exception:
                pass

    def _update_dep_version(self, pkg: str, version: str):
        """Update dependency version, handling package name mappings."""
        pkg_lower = pkg.lower().replace("-", "_")

        # Check if this package maps to a different import name
        import_name = self.PACKAGE_IMPORT_MAP.get(pkg.lower())

        for dep in list(self.external_deps.keys()):
            dep_normalized = dep.lower().replace("-", "_")
            # Match either by normalized name or by mapped import name
            if dep_normalized == pkg_lower or (import_name and dep == import_name):
                if self.external_deps[dep] == "unknown":
                    self.external_deps[dep] = version
                break

    def generate_indexes(self):
        """Main method to generate all indexes."""
        print(f"Analyzing codebase: {self.project_root}")

        # Build directory structure
        print("  Building directory structure...")
        self.structure = self.build_structure(self.project_root)

        # Analyze Python files (sorted for deterministic output)
        print("  Analyzing Python files...")
        python_files = sorted(self.project_root.rglob("*.py"))
        for py_file in python_files:
            # Skip files in ignored directories
            if any(part in self.SKIP_DIRS for part in py_file.parts):
                continue

            file_info = self.analyze_python_file(py_file)
            if file_info:
                # Add classes and functions to components
                for cls in file_info["classes"]:
                    self.components.append(cls)
                for func in file_info["functions"]:
                    # Only add significant functions (not test helpers, etc.)
                    if not func["name"].startswith("_") and not func["name"].startswith("test_"):
                        self.components.append(func)

                # Build internal dependency graph
                for internal_import in file_info["imports"]["internal"]:
                    rel_path = str(py_file.relative_to(self.project_root))
                    self.internal_deps[rel_path].append(internal_import)

        # Try to get package versions
        print("  Extracting dependency versions...")
        self.extract_versions_from_requirements()

        # Add conventions to detected patterns
        self._add_pattern_conventions()

        # Generate timestamp (using timezone.utc for Python 3.10 compatibility)
        generated_at = datetime.now(timezone.utc).isoformat()  # noqa: UP017

        # Sort components by file path and line number for deterministic output
        sorted_components = sorted(
            self.components, key=lambda c: (c.get("file", ""), c.get("line", 0))
        )

        # Build codebase.json
        codebase_json = {
            "generated": generated_at,
            "project": self.project_name,
            "structure": self.structure,
            "components": sorted_components[:100],  # Limit to top 100
            "summary": {
                "total_python_files": len(python_files),
                "total_classes": len([c for c in self.components if c.get("type") == "class"]),
                "total_functions": len([c for c in self.components if c.get("type") == "function"]),
                "patterns_detected": sorted(self.patterns_found.keys()),
            },
        }

        # Build patterns.json (sorted for deterministic output)
        sorted_patterns = {}
        for pattern_name in sorted(self.patterns_found.keys()):
            pattern_data = self.patterns_found[pattern_name]
            sorted_patterns[pattern_name] = {
                "description": pattern_data.get("description", ""),
                "examples": sorted(pattern_data.get("examples", [])),
                "conventions": pattern_data.get("conventions", []),
            }
        patterns_json = {
            "generated": generated_at,
            "project": self.project_name,
            "patterns": sorted_patterns,
        }

        # Build dependencies.json (sorted for deterministic output)
        sorted_internal = {k: sorted(v) for k, v in sorted(self.internal_deps.items())}
        sorted_external = dict(sorted(self.external_deps.items()))
        dependencies_json = {
            "generated": generated_at,
            "project": self.project_name,
            "internal": sorted_internal,
            "external": sorted_external,
        }

        # Write files
        self.output_dir.mkdir(parents=True, exist_ok=True)

        codebase_path = self.output_dir / "codebase.json"
        patterns_path = self.output_dir / "patterns.json"
        deps_path = self.output_dir / "dependencies.json"

        print(f"  Writing {codebase_path}...")
        with open(codebase_path, "w") as f:
            json.dump(codebase_json, f, indent=2)

        print(f"  Writing {patterns_path}...")
        with open(patterns_path, "w") as f:
            json.dump(patterns_json, f, indent=2)

        print(f"  Writing {deps_path}...")
        with open(deps_path, "w") as f:
            json.dump(dependencies_json, f, indent=2)

        print("\nGenerated indexes:")
        print(f"  - {codebase_path} ({len(self.components)} components)")
        print(f"  - {patterns_path} ({len(self.patterns_found)} patterns)")
        print(f"  - {deps_path} ({len(self.external_deps)} external deps)")

        return codebase_json, patterns_json, dependencies_json

    def _add_pattern_conventions(self):
        """Add conventions to detected patterns based on examples."""
        conventions = {
            "event_driven": [
                "Watchers monitor external sources (GitHub, Slack, file system)",
                "Handlers process events and trigger actions",
                "Use asyncio for concurrent event processing when appropriate",
            ],
            "connector": [
                "Connectors inherit from BaseConnector",
                "Each connector handles authentication for its service",
                "Connectors are responsible for rate limiting",
            ],
            "processor": [
                "Processors transform data from one format to another",
                "Each processor handles a specific data source",
                "Processors write output to standardized locations",
            ],
            "notification": [
                "Use the notifications library for all Slack messaging",
                "Notifications support threading via task_id",
                "Different notification types: info, warning, action_required",
            ],
            "sync": [
                "Sync services run on a schedule (systemd timers)",
                "Sync operations are idempotent",
                "Sync state is tracked to avoid duplicate processing",
            ],
            "config": [
                "Configuration loaded from environment variables",
                "Config classes validate required settings on init",
                "Sensitive values never logged or exposed",
            ],
        }

        for pattern_name, pattern_conventions in conventions.items():
            if pattern_name in self.patterns_found:
                self.patterns_found[pattern_name]["conventions"] = pattern_conventions


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate codebase indexes for LLM navigation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Index current project
  %(prog)s --project ~/khan/webapp      # Index specific project
  %(prog)s --output ./custom-output     # Custom output directory
        """,
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=Path.cwd(),
        help="Project root to analyze (default: current working directory)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory (default: <project>/docs/generated)",
    )

    args = parser.parse_args()

    project_root = args.project.resolve()
    output_dir = args.output or (project_root / "docs" / "generated")

    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}")
        sys.exit(1)

    indexer = CodebaseIndexer(project_root, output_dir)
    indexer.generate_indexes()


if __name__ == "__main__":
    main()
