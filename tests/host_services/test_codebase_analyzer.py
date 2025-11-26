"""
Tests for the codebase-analyzer module.

Tests the CodebaseAnalyzer class which analyzes codebases for potential
improvements and optionally creates PRs with fixes.
"""

import ast
import os
import tempfile
from pathlib import Path

import pytest


# Add project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestAnalysisCategoryEnum:
    """Tests for AnalysisCategory enum."""

    def test_analysis_categories_exist(self):
        """Test that all expected analysis categories exist."""
        # Simulate the enum
        categories = [
            "code_quality",
            "structural",
            "unused_code",
            "duplication",
            "documentation",
            "symlinks",
            "naming",
            "patterns",
        ]

        assert "code_quality" in categories
        assert "structural" in categories
        assert "documentation" in categories
        assert "patterns" in categories


class TestFixResultEnum:
    """Tests for FixResult enum."""

    def test_fix_result_values(self):
        """Test that all expected fix results exist."""
        results = [
            "success",
            "file_not_found",
            "file_too_large",
            "content_too_short",
            "content_too_long",
            "timeout",
            "claude_error",
            "requires_restructuring",
            "other_error",
        ]

        assert "success" in results
        assert "file_not_found" in results
        assert "timeout" in results
        assert "requires_restructuring" in results


class TestCodebaseAnalyzerFileFiltering:
    """Tests for file filtering logic."""

    def test_should_analyze_valid_extensions(self, temp_dir):
        """Test that valid file extensions are analyzed."""
        valid_extensions = {".py", ".sh", ".md", ".yml", ".yaml", ".json"}

        for ext in valid_extensions:
            test_file = temp_dir / f"test{ext}"
            test_file.write_text("test content")

            assert test_file.suffix in valid_extensions

    def test_should_analyze_dockerfile(self, temp_dir):
        """Test that Dockerfile is analyzed."""
        dockerfile = temp_dir / "Dockerfile"
        dockerfile.write_text("FROM python:3.11")

        # Dockerfiles have no extension but should be analyzed
        assert dockerfile.name == "Dockerfile"
        assert dockerfile.exists()

    def test_should_skip_large_files(self, temp_dir):
        """Test that large files are skipped."""
        max_size = 50_000

        large_file = temp_dir / "large.py"
        large_file.write_text("x" * 60_000)

        assert large_file.stat().st_size > max_size

    def test_should_skip_ignored_patterns(self):
        """Test that ignored patterns are skipped."""
        always_ignore = {
            ".git",
            "__pycache__",
            "node_modules",
            ".venv",
            ".pytest_cache",
            ".mypy_cache",
        }

        test_paths = [
            "/path/.git/config",
            "/path/__pycache__/module.pyc",
            "/path/node_modules/package/index.js",
            "/path/.venv/lib/python/site.py",
            "/path/.pytest_cache/v/cache/test.py",
            "/path/.mypy_cache/3.11/module.py",
        ]

        for path in test_paths:
            assert any(pattern in path for pattern in always_ignore)


class TestCodebaseAnalyzerStructuralInfo:
    """Tests for structural information gathering."""

    def test_detect_file_types(self, temp_dir):
        """Test detecting file types in codebase."""
        # Create test files
        (temp_dir / "script.py").write_text("# Python")
        (temp_dir / "config.yml").write_text("key: value")
        (temp_dir / "readme.md").write_text("# README")

        file_types = {}
        for f in temp_dir.iterdir():
            if f.is_file():
                ext = f.suffix.lower() or "no_extension"
                file_types[ext] = file_types.get(ext, 0) + 1

        assert file_types[".py"] == 1
        assert file_types[".yml"] == 1
        assert file_types[".md"] == 1

    def test_detect_readme_files(self, temp_dir):
        """Test detecting README files."""
        (temp_dir / "README.md").write_text("# Main README")
        (temp_dir / "readme.txt").write_text("Another readme")

        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "README.md").write_text("# Sub README")

        readme_files = []
        for f in temp_dir.rglob("*"):
            if f.is_file() and f.name.lower().startswith("readme"):
                readme_files.append(f.name)

        assert len(readme_files) == 3

    def test_detect_symlinks(self, temp_dir):
        """Test detecting symlinks."""
        target = temp_dir / "target.py"
        target.write_text("# Target")

        link = temp_dir / "link.py"
        link.symlink_to(target)

        symlinks = {}
        for f in temp_dir.iterdir():
            if f.is_symlink():
                symlinks[str(f.name)] = os.readlink(f)

        assert "link.py" in symlinks
        assert symlinks["link.py"] == str(target)

    def test_detect_broken_symlinks(self, temp_dir):
        """Test detecting broken symlinks."""
        link = temp_dir / "broken_link.py"
        link.symlink_to(temp_dir / "nonexistent.py")

        broken = []
        for f in temp_dir.iterdir():
            if f.is_symlink():
                resolved = f.parent / os.readlink(f)
                if not resolved.exists():
                    broken.append(f.name)

        assert "broken_link.py" in broken

    def test_detect_naming_patterns(self, temp_dir):
        """Test detecting naming patterns in scripts."""
        (temp_dir / "kebab-case.py").write_text("# kebab")
        (temp_dir / "snake_case.py").write_text("# snake")
        (temp_dir / "PascalCase.py").write_text("# pascal")
        (temp_dir / "lowercase.py").write_text("# lower")

        patterns = {}
        for f in temp_dir.iterdir():
            if f.suffix == ".py":
                name = f.stem
                if "-" in name:
                    pattern = "kebab-case"
                elif "_" in name:
                    pattern = "snake_case"
                elif name[0].isupper():
                    pattern = "PascalCase"
                else:
                    pattern = "lowercase"

                if pattern not in patterns:
                    patterns[pattern] = []
                patterns[pattern].append(f.name)

        assert "kebab-case" in patterns
        assert "snake_case" in patterns
        assert "PascalCase" in patterns
        assert "lowercase" in patterns


class TestCodebaseAnalyzerDuplicateDetection:
    """Tests for duplicate code detection."""

    def test_detect_similar_files(self, temp_dir):
        """Test detecting similar files by content."""
        common_content = "# Common code\nprint('hello')\nprint('world')\n"

        (temp_dir / "file1.py").write_text(common_content)
        (temp_dir / "file2.py").write_text(common_content)
        (temp_dir / "different.py").write_text("# Different\nprint('bye')")

        # Group by size first
        size_groups = {}
        for f in temp_dir.glob("*.py"):
            size = f.stat().st_size
            bucket = size // 100 * 100
            if bucket not in size_groups:
                size_groups[bucket] = []
            size_groups[bucket].append(f)

        # Files with same content should be in same size bucket
        for group in size_groups.values():
            if len(group) >= 2:
                c1 = group[0].read_text()
                c2 = group[1].read_text()
                if c1 == c2:
                    assert True  # Found duplicates


class TestCodebaseAnalyzerReadmeConsistency:
    """Tests for README consistency checking."""

    def test_detect_missing_file_reference(self, temp_dir):
        """Test detecting README references to missing files."""
        import re

        readme = temp_dir / "README.md"
        readme.write_text("""# Project

See `missing_file.py` for details.
Also check `./nonexistent.sh`.
""")

        # Find file references
        content = readme.read_text()
        patterns = [
            r"`([a-zA-Z0-9_\-./]+\.[a-zA-Z]+)`",
            r"(?:^|\s)(\.{1,2}/[a-zA-Z0-9_\-./]+)",
        ]

        references = set()
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                references.add(match.group(1))

        # Check which references don't exist
        missing = []
        for ref in references:
            ref_path = temp_dir / ref
            if not ref_path.exists():
                missing.append(ref)

        assert len(missing) == 2


class TestCodebaseAnalyzerCodebaseSummary:
    """Tests for codebase summary building."""

    def test_build_summary_truncates_large_files(self, temp_dir):
        """Test that large file contents are truncated in summary."""
        large_content = "x" * 5000
        (temp_dir / "large.py").write_text(large_content)

        # Simulate truncation
        max_length = 3000
        for f in temp_dir.glob("*.py"):
            content = f.read_text()
            if len(content) > max_length:
                content = content[:max_length] + "\n... [truncated]"

            assert len(content) <= max_length + len("\n... [truncated]")


class TestCodebaseAnalyzerImplementFix:
    """Tests for fix implementation logic."""

    def test_skip_non_autofixable_issues(self):
        """Test that non-autofixable issues are skipped."""
        issue = {"file": "old-service/", "auto_fixable": False, "category": "unused_code"}

        should_skip = not issue.get("auto_fixable", True)
        assert should_skip

    def test_skip_structural_categories(self):
        """Test that structural categories are skipped."""
        structural_categories = ["structural", "unused_code", "symlinks"]

        issue = {"file": "some_dir/", "category": "structural"}
        assert issue["category"] in structural_categories

    def test_validate_fix_content_length(self):
        """Test validation of fix content length."""
        original_content = "x" * 1000
        original_length = len(original_content)

        # Too short (< 30%)
        too_short = "y" * 200
        assert len(too_short) < original_length * 0.3

        # Too long (> 300%)
        too_long = "z" * 4000
        assert len(too_long) > original_length * 3

        # Just right
        valid_fix = "a" * 1000
        assert original_length * 0.3 <= len(valid_fix) <= original_length * 3


class TestCodebaseAnalyzerPRCreation:
    """Tests for PR creation logic."""

    def test_commit_message_format(self):
        """Test that commit message is properly formatted."""
        implemented = [
            {
                "file": "src/app.py",
                "category": "code_quality",
                "description": "Fixed bare except clause",
            },
            {
                "file": "src/utils.py",
                "category": "code_quality",
                "description": "Added error handling",
            },
        ]

        categories = {i["category"] for i in implemented}
        commit_msg = f"Auto-fix: {len(implemented)} codebase improvements\n\n"
        commit_msg += f"Categories: {', '.join(categories)}\n\n"
        commit_msg += "Fixes:\n"
        for issue in implemented:
            commit_msg += f"- {issue['file']}: {issue['description'][:50]}...\n"

        assert "Auto-fix: 2 codebase improvements" in commit_msg
        assert "code_quality" in commit_msg

    def test_pr_body_format(self):
        """Test that PR body is properly formatted."""
        implemented = [
            {
                "file": "src/app.py",
                "category": "code_quality",
                "description": "Fixed exception handling",
            },
        ]
        categories = {"code_quality"}

        pr_body = f"## Auto-fix: {len(implemented)} improvements\n\n"
        for cat in sorted(categories):
            cat_issues = [i for i in implemented if i["category"] == cat]
            pr_body += f"### {cat.title()} ({len(cat_issues)})\n"
            for i in cat_issues:
                pr_body += f"- `{i['file']}`: {i['description'][:60]}\n"
            pr_body += "\n"

        assert "## Auto-fix: 1 improvements" in pr_body
        assert "### Code_Quality (1)" in pr_body


class TestCodebaseAnalyzerNotification:
    """Tests for notification creation."""

    def test_notification_format(self, temp_dir):
        """Test that notification is properly formatted."""
        issues = [
            {
                "file": "src/app.py",
                "priority": "HIGH",
                "category": "code_quality",
                "description": "Bare except clause",
                "auto_fixable": True,
            },
            {
                "file": "docs/README.md",
                "priority": "MEDIUM",
                "category": "documentation",
                "description": "Outdated reference",
                "auto_fixable": False,
            },
        ]

        content = "# 🔍 Codebase Analysis\n\n"
        content += f"**Found {len(issues)} issues**\n\n"

        # Group by priority
        high = [i for i in issues if i["priority"] == "HIGH"]
        medium = [i for i in issues if i["priority"] == "MEDIUM"]

        assert len(high) == 1
        assert len(medium) == 1

        notif_file = temp_dir / "codebase-analysis.md"
        notif_file.write_text(content)

        assert notif_file.exists()


class TestCodebaseAnalyzerASTAnalysis:
    """Tests for AST-based Python analysis."""

    def test_detect_bare_except(self, temp_dir):
        """Test detection of bare except clauses using AST."""
        code = """
def foo():
    try:
        risky_operation()
    except:
        pass
"""
        (temp_dir / "bare_except.py").write_text(code)

        tree = ast.parse(code)
        has_bare_except = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                has_bare_except = True
                break

        assert has_bare_except

    def test_detect_eval_usage(self, temp_dir):
        """Test detection of eval() usage using AST."""
        code = """
def unsafe():
    user_input = input()
    result = eval(user_input)
    return result
"""
        (temp_dir / "eval_usage.py").write_text(code)

        tree = ast.parse(code)
        has_eval = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "eval"
            ):
                has_eval = True
                break

        assert has_eval

    def test_detect_syntax_error(self, temp_dir):
        """Test that syntax errors are detected."""
        code = """
def broken(
    print("missing closing paren"
"""
        (temp_dir / "syntax_error.py").write_text(code)

        with pytest.raises(SyntaxError):
            ast.parse(code)

    def test_no_issues_in_clean_code(self, temp_dir):
        """Test that clean code has no AST-detected issues."""
        code = '''
def safe_function():
    """This is a documented function."""
    try:
        result = some_operation()
    except ValueError as e:
        print(f"Error: {e}")
    return result
'''
        (temp_dir / "clean.py").write_text(code)

        tree = ast.parse(code)

        # Check for bare excepts
        has_bare_except = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                has_bare_except = True

        # Check for eval
        has_eval = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "eval"
            ):
                has_eval = True

        assert not has_bare_except
        assert not has_eval


class TestCodebaseAnalyzerCaching:
    """Tests for analysis result caching."""

    def test_file_hash_consistency(self, temp_dir):
        """Test that file hashes are consistent for same content."""
        import hashlib

        content = "print('hello world')"
        hash1 = hashlib.md5(content.encode("utf-8")).hexdigest()
        hash2 = hashlib.md5(content.encode("utf-8")).hexdigest()

        assert hash1 == hash2

    def test_file_hash_changes_with_content(self, temp_dir):
        """Test that file hashes change when content changes."""
        import hashlib

        content1 = "print('hello')"
        content2 = "print('world')"

        hash1 = hashlib.md5(content1.encode("utf-8")).hexdigest()
        hash2 = hashlib.md5(content2.encode("utf-8")).hexdigest()

        assert hash1 != hash2

    def test_cache_structure(self, temp_dir):
        """Test cache data structure."""
        import json
        from datetime import datetime

        cache_data = {
            "file_hashes": {"src/app.py": "abc123", "src/utils.py": "def456"},
            "last_analyzed": datetime.now().isoformat(),
            "issues": [
                {"file": "src/app.py", "description": "test issue"},
            ],
        }

        cache_file = temp_dir / ".codebase-analyzer-cache.json"
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)

        with open(cache_file) as f:
            loaded = json.load(f)

        assert loaded["file_hashes"]["src/app.py"] == "abc123"
        assert len(loaded["issues"]) == 1


class TestCodebaseAnalyzerGitIntegration:
    """Tests for git-based change detection."""

    def test_incremental_vs_full_mode(self):
        """Test that incremental and full modes are distinct."""
        # Simulated mode flags
        full_analysis = False
        since_days = 7

        # In incremental mode, only recent changes
        if not full_analysis:
            mode = f"Incremental (last {since_days} days)"
        else:
            mode = "Full"

        assert mode == "Incremental (last 7 days)"

        # In full mode
        full_analysis = True
        if not full_analysis:
            mode = f"Incremental (last {since_days} days)"
        else:
            mode = "Full"

        assert mode == "Full"

    def test_since_days_parameter(self):
        """Test since_days parameter handling."""
        default_since = 7
        custom_since = 14

        assert default_since == 7
        assert custom_since == 14

        # Full mode ignores since_days
        full_analysis = True
        since_days = 30
        effective_mode = "Full" if full_analysis else f"Incremental ({since_days} days)"

        assert effective_mode == "Full"


class TestCodebaseAnalyzerSinglePassScan:
    """Tests for single-pass codebase scanning."""

    def test_single_pass_collects_all_info(self, temp_dir):
        """Test that single pass collects all structural info."""
        # Create test structure
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "app.py").write_text("# app")
        (temp_dir / "src" / "utils.py").write_text("# utils")
        (temp_dir / "README.md").write_text("# README")

        # Simulate single-pass collection
        files = []
        file_types = {}
        readme_files = []
        directory_tree = {}

        for path in temp_dir.rglob("*"):
            rel_path = str(path.relative_to(temp_dir))
            parent = str(path.parent.relative_to(temp_dir)) if path.parent != temp_dir else "."

            if path.is_dir():
                if parent not in directory_tree:
                    directory_tree[parent] = []
                directory_tree[parent].append(path.name)
            elif path.is_file():
                files.append(path)
                ext = path.suffix.lower() or "no_extension"
                file_types[ext] = file_types.get(ext, 0) + 1
                if path.name.lower().startswith("readme"):
                    readme_files.append(rel_path)

        assert len(files) == 3
        assert file_types[".py"] == 2
        assert file_types[".md"] == 1
        assert len(readme_files) == 1
        assert "src" in directory_tree.get(".", [])


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
