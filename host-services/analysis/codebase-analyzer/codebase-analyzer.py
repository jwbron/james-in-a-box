#!/usr/bin/env python3
"""
Codebase Improvement Analyzer

Analyzes the james-in-a-box codebase for potential improvements using a SINGLE
Claude call, then optionally implements the top fixes and opens a PR.

The analyzer performs comprehensive analysis across multiple dimensions:
- Code Quality: Bare except clauses, missing error handling, style issues
- Structural Issues: Directory organization, file placement, naming consistency
- Unused Code: Dead code, obsolete files, unreferenced modules
- Duplication: Similar code patterns, repeated implementations
- Documentation Drift: READMEs out of sync, outdated references
- Symlink Health: Broken or incorrect symlinks
- Pattern Consistency: Similar modules should follow similar patterns

Efficiency Optimizations:
- Uses git-based change detection by default (only analyzes recently changed files)
- Single-pass file iteration (consolidates 4 rglob calls into one)
- Caches analysis results with file hash tracking
- Uses git ls-files for faster file listing (respects .gitignore automatically)

Usage:
  codebase-analyzer.py                    # Analyze recently changed files (default)
  codebase-analyzer.py --full             # Analyze entire codebase
  codebase-analyzer.py --since 14         # Analyze files changed in last 14 days
  codebase-analyzer.py --implement        # Analyze, fix top 10 issues, open PR
  codebase-analyzer.py --implement --max-fixes 5  # Fix top 5 issues
  codebase-analyzer.py --focus structural  # Focus on structural analysis
"""

import argparse
import ast
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

# Import shared Claude runner
# Path: host-services/analysis/codebase-analyzer/codebase-analyzer.py -> repo-root/shared
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from claude import is_claude_available, run_claude


class AnalysisCategory(Enum):
    """Categories of analysis the tool performs."""

    CODE_QUALITY = "code_quality"  # Error handling, exceptions, style
    STRUCTURAL = "structural"  # Directory organization, file placement
    UNUSED_CODE = "unused_code"  # Dead code, obsolete files
    DUPLICATION = "duplication"  # Similar patterns, repeated code
    DOCUMENTATION = "documentation"  # README drift, outdated docs
    SYMLINKS = "symlinks"  # Broken or incorrect symlinks
    NAMING = "naming"  # Naming consistency
    PATTERNS = "patterns"  # Design pattern consistency


class FixResult(Enum):
    """Result of attempting to fix an issue."""

    SUCCESS = "success"
    FILE_NOT_FOUND = "file_not_found"
    FILE_TOO_LARGE = "file_too_large"
    CONTENT_TOO_SHORT = "content_too_short"
    CONTENT_TOO_LONG = "content_too_long"
    META_COMMENTARY = "meta_commentary"  # AI included explanations in output
    TIMEOUT = "timeout"
    CLAUDE_ERROR = "claude_error"
    REQUIRES_RESTRUCTURING = "requires_restructuring"
    OTHER_ERROR = "other_error"


@dataclass
class FileInfo:
    """Information about a single file gathered during single-pass scan."""

    path: Path
    rel_path: str
    size: int
    extension: str
    is_symlink: bool = False
    symlink_target: str | None = None
    symlink_broken: bool = False
    content_hash: str | None = None
    content: str | None = None  # Cached content for analysis


@dataclass
class StructuralInfo:
    """Information about codebase structure."""

    directory_tree: dict[str, list[str]] = field(default_factory=dict)
    file_types: dict[str, int] = field(default_factory=dict)
    symlinks: dict[str, str] = field(default_factory=dict)  # symlink -> target
    broken_symlinks: list[str] = field(default_factory=list)
    readme_files: list[str] = field(default_factory=list)
    naming_patterns: dict[str, list[str]] = field(default_factory=dict)  # pattern -> files


@dataclass
class AnalysisCache:
    """Cache for analysis results to avoid re-analyzing unchanged files."""

    file_hashes: dict[str, str] = field(default_factory=dict)  # path -> content hash
    last_analyzed: str | None = None
    issues: list[dict] = field(default_factory=list)


@dataclass
class PRResult:
    """Result of PR creation attempt."""

    success: bool
    pr_url: str | None = None
    branch_name: str | None = None
    error: str | None = None


class ASTIssueDetector(ast.NodeVisitor):
    """AST-based detector for Python code issues."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.issues: list[dict] = []
        self._in_function = False
        self._current_function: str | None = None

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Detect bare except clauses."""
        if node.type is None:
            self.issues.append(
                {
                    "file": self.file_path,
                    "line_hint": f"line {node.lineno}",
                    "priority": "HIGH",
                    "category": "code_quality",
                    "description": "Bare except clause catches all exceptions including KeyboardInterrupt",
                    "suggestion": "Replace 'except:' with 'except Exception as e:' and log the error",
                    "auto_fixable": True,
                }
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function context and detect issues."""
        old_function = self._current_function
        self._current_function = node.name
        self._in_function = True

        # Check for functions without docstrings (only for public functions)
        # Skip small functions (less than 5 lines), private functions, and functions with docstrings
        has_docstring = (
            len(node.body) > 0
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
        is_large_public_function = (
            not node.name.startswith("_")
            and len(node.body) > 0
            and hasattr(node, "end_lineno")
            and node.end_lineno - node.lineno > 5
        )
        if is_large_public_function and not has_docstring:
            self.issues.append(
                {
                    "file": self.file_path,
                    "line_hint": f"function {node.name}() at line {node.lineno}",
                    "priority": "MEDIUM",
                    "category": "documentation",
                    "description": f"Public function '{node.name}' lacks a docstring",
                    "suggestion": "Add a docstring describing what the function does",
                    "auto_fixable": False,
                }
            )

        self.generic_visit(node)
        self._current_function = old_function
        self._in_function = old_function is not None

    def visit_Import(self, node: ast.Import) -> None:
        """Detect potentially unused imports (heuristic)."""
        # This is a basic check - could be extended with more sophisticated analysis
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Detect potentially problematic function calls."""
        # Check for eval() usage
        if isinstance(node.func, ast.Name) and node.func.id == "eval":
            self.issues.append(
                {
                    "file": self.file_path,
                    "line_hint": f"line {node.lineno}",
                    "priority": "HIGH",
                    "category": "code_quality",
                    "description": "Use of eval() is a security risk",
                    "suggestion": "Replace eval() with safer alternatives like ast.literal_eval() or json.loads()",
                    "auto_fixable": False,
                }
            )
        self.generic_visit(node)


class CodebaseAnalyzer:
    """Analyzes codebase for improvements using a single Claude Code call."""

    # Valid extensions to analyze
    VALID_EXTENSIONS = {".py", ".sh", ".md", ".yml", ".yaml", ".json"}
    # Directories to always ignore
    ALWAYS_IGNORE = {".git", "__pycache__", "node_modules", ".venv", ".pytest_cache", ".mypy_cache"}
    # Maximum file size for analysis (50KB)
    MAX_FILE_SIZE = 50_000
    # Cache file location
    CACHE_FILE = ".codebase-analyzer-cache.json"

    def __init__(
        self,
        codebase_path: Path,
        notification_dir: Path,
        focus: str | None = None,
        full_analysis: bool = False,
        since_days: int = 7,
    ):
        self.codebase_path = codebase_path
        self.notification_dir = notification_dir
        self.focus = focus  # Optional focus category
        self.full_analysis = full_analysis
        self.since_days = since_days
        self.logger = self._setup_logging()

        # Check for claude CLI
        if not self._check_claude_cli():
            self.logger.error("claude CLI not found in PATH")
            raise ValueError("claude command not available")

        # Single-pass scan results
        self._scanned_files: dict[str, FileInfo] = {}
        self._structural_info: StructuralInfo | None = None

        # Analysis cache
        self._cache = self._load_cache()

    def _check_claude_cli(self) -> bool:
        """Check if claude CLI is available."""
        return is_claude_available()

    def _setup_logging(self) -> logging.Logger:
        """Configure logging."""
        logger = logging.getLogger("codebase-analyzer")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            console = logging.StreamHandler()
            console.setLevel(logging.INFO)
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            console.setFormatter(formatter)
            logger.addHandler(console)
        return logger

    def _load_cache(self) -> AnalysisCache:
        """Load analysis cache from disk."""
        cache_path = self.codebase_path / self.CACHE_FILE
        if cache_path.exists():
            try:
                with open(cache_path, encoding="utf-8") as f:
                    data = json.load(f)
                    return AnalysisCache(
                        file_hashes=data.get("file_hashes", {}),
                        last_analyzed=data.get("last_analyzed"),
                        issues=data.get("issues", []),
                    )
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.warning(f"Error loading cache: {e}")
        return AnalysisCache()

    def _save_cache(self, issues: list[dict]) -> None:
        """Save analysis cache to disk."""
        cache_path = self.codebase_path / self.CACHE_FILE
        cache_data = {
            "file_hashes": {
                rel_path: info.content_hash
                for rel_path, info in self._scanned_files.items()
                if info.content_hash
            },
            "last_analyzed": datetime.now().isoformat(),
            "issues": issues,
        }
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Error saving cache: {e}")

    def _get_file_hash(self, content: str) -> str:
        """Get hash of file content for caching."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _get_git_tracked_files(self) -> set[str]:
        """Get list of files tracked by git (respects .gitignore automatically)."""
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True,
                text=True,
                cwd=self.codebase_path,
                check=False,
            )
            if result.returncode == 0:
                return set(result.stdout.strip().split("\n"))
        except Exception as e:
            self.logger.warning(f"Error getting git-tracked files: {e}")
        return set()

    def _get_recently_changed_files(self) -> set[str]:
        """Get files changed in the last N days using git."""
        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--name-only",
                    f"--since={self.since_days} days ago",
                    "--pretty=format:",
                ],
                capture_output=True,
                text=True,
                cwd=self.codebase_path,
                check=False,
            )
            if result.returncode == 0:
                files = {f.strip() for f in result.stdout.strip().split("\n") if f.strip()}
                self.logger.info(f"Found {len(files)} files changed in last {self.since_days} days")
                return files
        except Exception as e:
            self.logger.warning(f"Error getting changed files: {e}")
        return set()

    def _should_analyze_file(self, path: Path, rel_path: str) -> bool:
        """Determine if file should be analyzed."""
        # Check always-ignore patterns
        for pattern in self.ALWAYS_IGNORE:
            if pattern in str(path):
                return False

        # Only analyze specific file types
        if path.suffix.lower() not in self.VALID_EXTENSIONS and path.name != "Dockerfile":
            return False

        # Skip very large files
        try:
            if path.stat().st_size > self.MAX_FILE_SIZE:
                return False
        except OSError:
            return False

        return True

    def scan_codebase_single_pass(self) -> tuple[list[Path], StructuralInfo]:
        """
        Single-pass scan of the codebase that gathers:
        - Files to analyze
        - Directory structure
        - Symlink information
        - Naming patterns
        - File type counts

        This consolidates what was previously 4 separate rglob() calls.
        """
        self.logger.info("Scanning codebase (single pass)...")

        info = StructuralInfo()
        files_to_analyze: list[Path] = []
        git_tracked = self._get_git_tracked_files()

        # Determine which files to consider based on mode
        if self.full_analysis:
            self.logger.info("Full analysis mode - scanning all files")
            target_files = git_tracked
        else:
            changed_files = self._get_recently_changed_files()
            if changed_files:
                target_files = changed_files
                self.logger.info(f"Incremental mode - analyzing {len(target_files)} changed files")
            else:
                self.logger.info("No recent changes found, falling back to full analysis")
                target_files = git_tracked

        # Single pass through the codebase
        for path in self.codebase_path.rglob("*"):
            # Skip ignored directories early
            if any(ig in str(path) for ig in self.ALWAYS_IGNORE):
                continue

            try:
                rel_path = str(path.relative_to(self.codebase_path))
            except ValueError:
                continue

            parent = (
                str(path.parent.relative_to(self.codebase_path))
                if path.parent != self.codebase_path
                else "."
            )

            # Handle directories
            if path.is_dir():
                if parent not in info.directory_tree:
                    info.directory_tree[parent] = []
                info.directory_tree[parent].append(path.name)
                continue

            # Handle symlinks
            if path.is_symlink():
                target = os.readlink(path)
                info.symlinks[rel_path] = target
                resolved = path.parent / target
                if not resolved.exists():
                    info.broken_symlinks.append(rel_path)

                self._scanned_files[rel_path] = FileInfo(
                    path=path,
                    rel_path=rel_path,
                    size=0,
                    extension=path.suffix.lower(),
                    is_symlink=True,
                    symlink_target=target,
                    symlink_broken=not resolved.exists(),
                )
                continue

            # Handle regular files
            if not path.is_file():
                continue

            try:
                stat = path.stat()
                size = stat.st_size
            except OSError:
                continue

            ext = path.suffix.lower() or "no_extension"
            info.file_types[ext] = info.file_types.get(ext, 0) + 1

            # Track README files
            if path.name.lower().startswith("readme"):
                info.readme_files.append(rel_path)

            # Track naming patterns for scripts
            if ext in {".py", ".sh"}:
                name = path.stem
                if "-" in name:
                    pattern = "kebab-case"
                elif "_" in name:
                    pattern = "snake_case"
                elif name and name[0].isupper():
                    pattern = "PascalCase"
                else:
                    pattern = "lowercase"

                if pattern not in info.naming_patterns:
                    info.naming_patterns[pattern] = []
                info.naming_patterns[pattern].append(rel_path)

            # Create file info
            file_info = FileInfo(
                path=path,
                rel_path=rel_path,
                size=size,
                extension=ext,
            )

            # Check if this file should be analyzed
            if self._should_analyze_file(path, rel_path):
                # In incremental mode, only add files that changed
                if not self.full_analysis and rel_path not in target_files:
                    # Still store info but don't add to analysis list
                    self._scanned_files[rel_path] = file_info
                    continue

                # Read content and compute hash for caching
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                    file_info.content = content
                    file_info.content_hash = self._get_file_hash(content)

                    # Check if file has changed since last analysis
                    if (
                        not self.full_analysis
                        and self._cache.file_hashes.get(rel_path) == file_info.content_hash
                    ):
                        self.logger.debug(f"Skipping unchanged file: {rel_path}")
                    else:
                        files_to_analyze.append(path)
                except Exception as e:
                    self.logger.warning(f"Error reading {path}: {e}")

            self._scanned_files[rel_path] = file_info

        self._structural_info = info
        self.logger.info(
            f"Scan complete: {len(files_to_analyze)} files to analyze, "
            f"{len(info.symlinks)} symlinks, {len(info.broken_symlinks)} broken"
        )
        return files_to_analyze, info

    def analyze_python_with_ast(self, files: list[Path]) -> list[dict]:
        """Use AST-based analysis for Python files to detect issues programmatically."""
        issues: list[dict] = []

        for file_path in files:
            if file_path.suffix != ".py":
                continue

            rel_path = str(file_path.relative_to(self.codebase_path))
            file_info = self._scanned_files.get(rel_path)
            if not file_info or not file_info.content:
                continue

            try:
                tree = ast.parse(file_info.content)
                detector = ASTIssueDetector(rel_path)
                detector.visit(tree)
                issues.extend(detector.issues)
            except SyntaxError as e:
                issues.append(
                    {
                        "file": rel_path,
                        "line_hint": f"line {e.lineno}" if e.lineno else "unknown",
                        "priority": "HIGH",
                        "category": "code_quality",
                        "description": f"Python syntax error: {e.msg}",
                        "suggestion": "Fix the syntax error to allow proper parsing",
                        "auto_fixable": False,
                    }
                )
            except Exception as e:
                self.logger.warning(f"AST analysis failed for {rel_path}: {e}")

        return issues

    def detect_potential_duplicates(self, files: list[Path]) -> list[tuple[str, str, float]]:
        """Detect potentially duplicated code by comparing file content hashes and structure.

        Returns list of (file1, file2, similarity_score) tuples.
        """
        duplicates = []

        # Group files by size bucket (similar size = potential duplicate)
        size_buckets: dict[int, list[str]] = {}
        for file_path in files:
            rel_path = str(file_path.relative_to(self.codebase_path))
            file_info = self._scanned_files.get(rel_path)
            if not file_info or not file_info.content:
                continue

            bucket = file_info.size // 100 * 100
            if bucket not in size_buckets:
                size_buckets[bucket] = []
            size_buckets[bucket].append(rel_path)

        # Compare files in same bucket
        for _bucket, group in size_buckets.items():
            if len(group) < 2:
                continue

            for i, rel1 in enumerate(group):
                for rel2 in group[i + 1 :]:
                    info1 = self._scanned_files.get(rel1)
                    info2 = self._scanned_files.get(rel2)
                    if not info1 or not info2 or not info1.content or not info2.content:
                        continue

                    # Quick hash comparison first
                    if info1.content_hash == info2.content_hash:
                        duplicates.append((rel1, rel2, 1.0))
                        continue

                    # Line-based similarity for non-identical files
                    lines1 = set(info1.content.strip().split("\n"))
                    lines2 = set(info2.content.strip().split("\n"))

                    if not lines1 or not lines2:
                        continue

                    intersection = len(lines1 & lines2)
                    union = len(lines1 | lines2)
                    similarity = intersection / union if union > 0 else 0

                    if similarity > 0.5:  # More than 50% similar
                        duplicates.append((rel1, rel2, similarity))

        return duplicates

    def check_readme_consistency(self, files: list[Path]) -> list[dict]:
        """Check if README files reference files that exist or are missing."""
        issues = []

        for readme_path in files:
            if not readme_path.name.lower().startswith("readme"):
                continue

            rel_readme = str(readme_path.relative_to(self.codebase_path))
            file_info = self._scanned_files.get(rel_readme)
            if not file_info or not file_info.content:
                continue

            content = file_info.content
            readme_dir = readme_path.parent

            # Find file/path references in README
            patterns = [
                r"`([a-zA-Z0-9_\-./]+\.[a-zA-Z]+)`",  # `filename.ext`
                r"`([a-zA-Z0-9_\-]+\.(py|sh|md|yml|yaml|json))`",  # `script.py`
                r"(?:^|\s)(\.{1,2}/[a-zA-Z0-9_\-./]+)",  # ./path or ../path
            ]

            referenced_files = set()
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    referenced_files.add(match.group(1))

            # Check each reference
            for ref in referenced_files:
                if ref.startswith(("http", "#")):
                    continue

                ref_path = readme_dir / ref
                if not ref_path.exists() and not (self.codebase_path / ref).exists():
                    issues.append(
                        {
                            "file": rel_readme,
                            "line_hint": f"references '{ref}'",
                            "priority": "MEDIUM",
                            "category": "documentation",
                            "description": f"README references non-existent file: {ref}",
                            "suggestion": f"Update or remove reference to '{ref}' in README",
                            "auto_fixable": False,
                        }
                    )

        return issues

    def build_codebase_summary(self, files: list[Path]) -> str:
        """Build a summary of the codebase for Claude to analyze."""
        summary_parts = []

        for file_path in files:
            rel_path = str(file_path.relative_to(self.codebase_path))
            file_info = self._scanned_files.get(rel_path)
            if not file_info or not file_info.content:
                continue

            content = file_info.content
            # Truncate large files
            if len(content) > 3000:
                content = content[:3000] + "\n... [truncated]"

            summary_parts.append(f"=== FILE: {rel_path} ===\n{content}\n")

        return "\n".join(summary_parts)

    def build_structural_context(
        self, structural_info: StructuralInfo, duplicates: list[tuple[str, str, float]]
    ) -> str:
        """Build a structural context section for the Claude prompt."""
        context_parts = []

        # Directory structure overview
        context_parts.append("=== DIRECTORY STRUCTURE ===")
        for parent, children in sorted(structural_info.directory_tree.items())[:20]:
            context_parts.append(f"{parent}/: {', '.join(children[:10])}")

        # Symlinks status
        if structural_info.symlinks:
            context_parts.append("\n=== SYMLINKS ===")
            for link, target in structural_info.symlinks.items():
                status = "BROKEN" if link in structural_info.broken_symlinks else "OK"
                context_parts.append(f"{link} -> {target} [{status}]")

        # Naming patterns
        if structural_info.naming_patterns:
            context_parts.append("\n=== NAMING PATTERNS ===")
            for pattern, files in structural_info.naming_patterns.items():
                context_parts.append(f"{pattern}: {len(files)} files")
                for f in files[:5]:
                    context_parts.append(f"  - {f}")

        # Potential duplicates
        if duplicates:
            context_parts.append("\n=== POTENTIAL DUPLICATES ===")
            for f1, f2, sim in duplicates[:10]:
                context_parts.append(f"{f1} <-> {f2} ({sim:.0%} similar)")

        return "\n".join(context_parts)

    def analyze_codebase(self, files: list[Path]) -> list[dict]:
        """Analyze entire codebase in a single Claude call."""
        if not self._structural_info:
            _, self._structural_info = self.scan_codebase_single_pass()

        structural_info = self._structural_info

        # Run AST-based analysis for Python files first
        self.logger.info("Running AST-based Python analysis...")
        ast_issues = self.analyze_python_with_ast(files)
        if ast_issues:
            self.logger.info(f"AST analysis found {len(ast_issues)} issues")

        self.logger.info("Checking for potential duplicates...")
        duplicates = self.detect_potential_duplicates(files)
        if duplicates:
            self.logger.info(f"Found {len(duplicates)} potential duplicate pairs")

        self.logger.info("Checking README consistency...")
        readme_issues = self.check_readme_consistency(files)
        if readme_issues:
            self.logger.info(f"Found {len(readme_issues)} README issues")

        self.logger.info("Building codebase summary...")
        codebase_summary = self.build_codebase_summary(files)
        structural_context = self.build_structural_context(structural_info, duplicates)

        self.logger.info(f"Codebase summary: {len(codebase_summary)} characters")

        # Build focus-specific instructions
        focus_instructions = ""
        if self.focus:
            focus_map = {
                "structural": "Focus primarily on directory organization, file placement, and naming consistency.",
                "duplication": "Focus primarily on duplicate code, similar implementations, and consolidation opportunities.",
                "unused": "Focus primarily on dead code, unused files, obsolete implementations.",
                "documentation": "Focus primarily on README accuracy, outdated documentation, missing docs.",
                "patterns": "Focus primarily on design pattern consistency, anti-patterns, best practice violations.",
            }
            focus_instructions = focus_map.get(self.focus, "")

        # Include AST-detected issues in prompt context
        ast_context = ""
        if ast_issues:
            ast_context = "\n\n=== PRE-DETECTED ISSUES (AST analysis) ===\n"
            for issue in ast_issues[:10]:  # Limit to top 10
                ast_context += f"- {issue['file']}: {issue['description']}\n"

        prompt = f"""Analyze this codebase for issues that can be automatically fixed or flagged for human review.

CODEBASE: james-in-a-box (Docker sandbox for Claude Code CLI)

{structural_context}
{ast_context}

{codebase_summary}

TASK: Identify the top 15-20 HIGH and MEDIUM priority issues across ALL categories.
{focus_instructions}

NOTE: Some issues were pre-detected by AST analysis. Focus on finding ADDITIONAL issues not already listed above.

ANALYSIS CATEGORIES (check ALL of these):

1. CODE QUALITY (category: "code_quality")
   - Bare except clauses (should use specific exceptions)
   - Missing error handling
   - Code style issues (unused imports, inline imports)
   - Security issues (unquoted shell variables, etc.)

2. STRUCTURAL ISSUES (category: "structural")
   - Files in wrong directories (scripts in wrong locations)
   - Poor directory organization
   - Inconsistent project structure

3. UNUSED/OBSOLETE CODE (category: "unused_code")
   - Dead code, unreferenced functions
   - Obsolete files that should be deleted
   - Old implementations superseded by newer ones

4. DUPLICATION (category: "duplication")
   - Similar code in multiple files
   - Repeated implementations that could be consolidated
   - Copy-pasted code with minor variations

5. DOCUMENTATION DRIFT (category: "documentation")
   - READMEs referencing non-existent files
   - Outdated setup instructions
   - Documentation not matching actual code

6. SYMLINKS (category: "symlinks")
   - Broken symlinks
   - Symlinks pointing to wrong locations

7. NAMING CONSISTENCY (category: "naming")
   - Inconsistent naming conventions (snake_case vs kebab-case)
   - Files that don't match their directory naming pattern
   - Misleading or unclear names

8. PATTERN CONSISTENCY (category: "patterns")
   - Similar modules following different patterns
   - Anti-patterns and bad design choices
   - Inconsistent error handling or logging patterns

For each issue, provide:
- file: relative path to file (or directory for structural issues)
- line_hint: approximate line number, function name, or description
- priority: HIGH or MEDIUM
- category: one of the categories above
- description: clear description of what's wrong
- suggestion: specific, actionable fix
- auto_fixable: true if this can be auto-fixed, false if it needs human review

Return as JSON array:
[
  {{
    "file": "path/to/file.py",
    "line_hint": "in function foo() around line 50",
    "priority": "HIGH",
    "category": "code_quality",
    "description": "Bare except clause catches all exceptions",
    "suggestion": "Replace 'except:' with 'except Exception as e:' and log the error",
    "auto_fixable": true
  }},
  {{
    "file": "host-services/old-service/",
    "line_hint": "entire directory",
    "priority": "MEDIUM",
    "category": "unused_code",
    "description": "Directory contains obsolete service replaced by new implementation",
    "suggestion": "Delete directory after verifying no references exist",
    "auto_fixable": false
  }}
]

Return ONLY the JSON array, no other text."""

        self.logger.info("Calling Claude for analysis (single call)...")

        result = run_claude(prompt, timeout=300)

        if not result.success:
            self.logger.error(f"Claude error: {result.error}")
            # Return pre-detected issues even if Claude fails
            return ast_issues + readme_issues

        response = result.stdout.strip()

        # Extract JSON from response
        try:
            start_idx = response.find("[")
            end_idx = response.rfind("]") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                claude_issues = json.loads(json_str)

                # Merge all issues (deduplicate by file+description)
                all_issues = ast_issues + readme_issues
                existing = {(i.get("file"), i.get("description")[:50]) for i in all_issues}

                for issue in claude_issues:
                    key = (issue.get("file"), issue.get("description", "")[:50])
                    if key not in existing:
                        all_issues.append(issue)
                        existing.add(key)

                # Add broken symlink issues
                for broken_link in structural_info.broken_symlinks:
                    key = (broken_link, "Broken symlink")
                    if key not in existing:
                        all_issues.append(
                            {
                                "file": broken_link,
                                "line_hint": "symlink",
                                "priority": "HIGH",
                                "category": "symlinks",
                                "description": "Broken symlink: target does not exist",
                                "suggestion": "Fix or remove broken symlink",
                                "auto_fixable": False,
                            }
                        )

                self.logger.info(f"Found {len(all_issues)} total issues")

                # Save to cache
                self._save_cache(all_issues)

                return all_issues
            else:
                self.logger.warning("No JSON array found in response")
                return ast_issues + readme_issues

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON: {e}")
            self.logger.debug(f"Response was: {response[:500]}")
            return ast_issues + readme_issues

    def _detect_meta_commentary(self, content: str, file_ext: str) -> tuple[bool, str | None]:
        """Detect if output contains AI meta-commentary mixed into the file content.

        Returns:
            Tuple of (has_meta_commentary, detail_string)
        """
        meta_patterns = [
            r"^(?:Here(?:'s| is) (?:the|my|your)|I(?:'ve| have) (?:made|fixed|updated))",
            r"^(?:The (?:issue|problem|fix|change|solution)|This (?:fixes|resolves|addresses))",
            r"^(?:I (?:will|can|cannot|can't|am|have|don't)|Let me)",
            r"^(?:Note:|Summary:|Explanation:|Changes made:|What I changed:)",
            r"^(?:Unfortunately|Apologies|I apologize|I'm sorry)",
            r"^(?:Sure|Certainly|Of course|Absolutely)[,!.]",
            r"^(?:Great|Perfect|Excellent)[,!.]",
            r"^#{1,3} (?:Changes|Summary|Fix|Solution|Updated)",
        ]

        lines = content.split("\n")[:5]
        for i, line in enumerate(lines):
            line = line.strip()
            for pattern in meta_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    return (True, f"Line {i + 1} contains meta-commentary: '{line[:50]}...'")

        if file_ext in {".py", ".sh"}:
            for i, line in enumerate(lines[:3]):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if (
                    stripped[0].isupper()
                    and stripped.endswith(".")
                    and " " in stripped
                    and not stripped.startswith(("class ", "def ", "import ", "from "))
                ):
                    return (True, f"Line {i + 1} appears to be prose: '{stripped[:50]}...'")
                break

        explanation_markers = ["```", "---", "**Changes:**", "**Summary:**", "**Note:**"]
        marker_count = sum(1 for m in explanation_markers if m in content)
        if marker_count >= 2:
            return (True, f"Found {marker_count} explanation markers in content")

        return (False, None)

    def implement_fix(self, issue: dict) -> tuple[FixResult, str | None]:
        """Implement a single fix using Claude Code.

        Returns:
            Tuple of (FixResult, details_string)
        """
        if not issue.get("auto_fixable", True):
            detail = f"Issue requires human review ({issue.get('category', 'unknown')})"
            self.logger.info(f"Skipping {issue['file']}: {detail}")
            return (FixResult.REQUIRES_RESTRUCTURING, detail)

        if issue.get("category") in ["structural", "unused_code", "symlinks"]:
            detail = "Structural change requires human review"
            self.logger.info(f"Skipping {issue['file']}: {detail}")
            return (FixResult.REQUIRES_RESTRUCTURING, detail)

        file_path = self.codebase_path / issue["file"]

        if not file_path.exists():
            self.logger.warning(f"File not found: {file_path}")
            return (FixResult.FILE_NOT_FOUND, None)

        if file_path.is_dir():
            return (FixResult.REQUIRES_RESTRUCTURING, "Target is a directory")

        try:
            content = file_path.read_text(encoding="utf-8")
            file_size = len(content)

            max_size_for_fix = 20_000
            if file_size > max_size_for_fix:
                detail = f"{file_size // 1000}KB exceeds {max_size_for_fix // 1000}KB limit"
                self.logger.warning(
                    f"Skipping {issue['file']} ({file_size // 1000}KB) - too large for auto-fix"
                )
                return (FixResult.FILE_TOO_LARGE, detail)

            timeout_seconds = max(120, 60 + file_size // 200)

            file_ext = Path(issue["file"]).suffix.lower()
            structure_hint = ""
            if file_ext == ".py":
                first_line = content.split("\n")[0] if content else ""
                if first_line.startswith("#!"):
                    structure_hint = f"The file MUST start with: {first_line}"
                elif first_line.startswith(('"""', "'''")):
                    structure_hint = "The file MUST start with a docstring"
                else:
                    structure_hint = "The file should start with imports or code, not prose"
            elif file_ext == ".sh":
                structure_hint = "The file MUST start with #!/bin/bash or similar shebang"
            elif file_ext == ".md":
                structure_hint = "The file should start with a markdown heading or content"

            prompt = f"""You are a code-only output generator. Your task is to output ONLY the fixed file content.

CRITICAL RULES:
1. Output ONLY the file content - no explanations, no commentary, no markdown fences
2. Do NOT start with "Here is", "I've fixed", "The issue", or any other prose
3. The first character of your output must be the first character of the fixed file
4. Make ONLY the minimal change needed to fix the issue

FILE: {issue["file"]}
ISSUE: {issue["description"]}
LOCATION: {issue.get("line_hint", "unknown")}
SUGGESTED FIX: {issue["suggestion"]}

{structure_hint}

CURRENT FILE CONTENT ({len(content)} chars, {len(content.splitlines())} lines):
{content}

OUTPUT REQUIREMENTS:
- Return the COMPLETE fixed file (all {len(content.splitlines())} lines)
- Output length should be similar to input ({len(content)} chars)
- NO markdown fences (```), NO explanations, NO summaries
- First line of output = first line of the fixed file
- Last line of output = last line of the fixed file

Output the fixed file content now:"""

            result = run_claude(prompt, timeout=timeout_seconds)

            if not result.success:
                self.logger.error(f"Claude error for {issue['file']}: {result.error}")
                return (FixResult.CLAUDE_ERROR, result.error[:200] if result.error else None)

            fixed_content = result.stdout.strip()

            if fixed_content.startswith("```"):
                lines = fixed_content.split("\n")
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                fixed_content = "\n".join(lines)

            if fixed_content.rstrip().endswith("```"):
                lines = fixed_content.split("\n")
                while lines and lines[-1].strip() in ("```", ""):
                    lines = lines[:-1]
                fixed_content = "\n".join(lines)

            has_meta, meta_detail = self._detect_meta_commentary(fixed_content, file_ext)
            if has_meta:
                self.logger.warning(f"Meta-commentary detected in {issue['file']}: {meta_detail}")
                return (FixResult.META_COMMENTARY, meta_detail)

            if len(fixed_content) < len(content) * 0.3:
                detail = (
                    f"output {len(fixed_content)} chars vs original {len(content)} chars (< 30%)"
                )
                self.logger.warning(f"Fixed content too short for {issue['file']}: {detail}")
                return (FixResult.CONTENT_TOO_SHORT, detail)

            if len(fixed_content) > len(content) * 3:
                detail = (
                    f"output {len(fixed_content)} chars vs original {len(content)} chars (> 300%)"
                )
                self.logger.warning(f"Fixed content too long for {issue['file']}: {detail}")
                return (FixResult.CONTENT_TOO_LONG, detail)

            file_path.write_text(fixed_content, encoding="utf-8")
            self.logger.info(f"Fixed: {issue['file']} ({issue['category']})")
            return (FixResult.SUCCESS, None)

        except Exception as e:
            self.logger.error(f"Error fixing {issue['file']}: {e}")
            return (FixResult.OTHER_ERROR, str(e)[:200])

    def create_pr(
        self,
        implemented: list[dict],
        skipped: list[tuple[dict, FixResult, str | None]] | None = None,
    ) -> PRResult:
        """Commit changes and create a PR."""
        if not implemented:
            return PRResult(success=False, error="No issues were successfully fixed")

        skipped = skipped or []
        branch_name = None

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                check=False,
                cwd=self.codebase_path,
                capture_output=True,
                text=True,
            )

            if not result.stdout.strip():
                self.logger.warning("No changes to commit")
                return PRResult(
                    success=False, error="No changes to commit (fixes may not have modified files)"
                )

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"auto-fix/codebase-{timestamp}"

            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.codebase_path,
                check=True,
                capture_output=True,
            )

            subprocess.run(
                ["git", "add", "-A"], cwd=self.codebase_path, check=True, capture_output=True
            )

            categories = {i["category"] for i in implemented}
            commit_msg = f"""Auto-fix: {len(implemented)} codebase improvements

Categories: {", ".join(categories)}

Fixes:
"""
            for issue in implemented:
                commit_msg += f"- {issue['file']}: {issue['description'][:50]}...\n"

            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.codebase_path,
                check=True,
                capture_output=True,
            )

            result = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                check=False,
                cwd=self.codebase_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                error_msg = f"Push failed: {result.stderr.strip()}"
                self.logger.error(error_msg)
                return PRResult(success=False, branch_name=branch_name, error=error_msg)

            pr_body = f"## Auto-fix: {len(implemented)} improvements\n\n"
            for cat in sorted(categories):
                cat_issues = [i for i in implemented if i["category"] == cat]
                pr_body += f"### {cat.title()} ({len(cat_issues)})\n"
                for i in cat_issues:
                    pr_body += f"- `{i['file']}`: {i['description'][:60]}\n"
                pr_body += "\n"

            if skipped:
                pr_body += f"## Skipped Issues ({len(skipped)})\n\n"
                pr_body += "These issues were identified but couldn't be auto-fixed:\n\n"
                for issue, fix_result, detail in skipped:
                    reason = fix_result.value.replace("_", " ")
                    pr_body += f"- `{issue['file']}`: {reason}"
                    if detail:
                        pr_body += f" ({detail})"
                    pr_body += f"\n  - Issue: {issue['description'][:80]}\n"
                pr_body += "\n"

            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--base",
                    "main",
                    "--head",
                    branch_name,
                    "--title",
                    f"Auto-fix: {len(implemented)} codebase improvements",
                    "--body",
                    pr_body,
                ],
                check=False,
                cwd=self.codebase_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                error_msg = f"PR creation failed: {result.stderr.strip()}"
                self.logger.error(error_msg)
                return PRResult(success=False, branch_name=branch_name, error=error_msg)

            pr_url = result.stdout.strip()
            self.logger.info(f"Created PR: {pr_url}")
            return PRResult(success=True, pr_url=pr_url, branch_name=branch_name)

        except subprocess.CalledProcessError as e:
            error_msg = f"Git command failed: {e.cmd} returned {e.returncode}"
            self.logger.error(error_msg)
            return PRResult(success=False, branch_name=branch_name, error=error_msg)
        except Exception as e:
            error_msg = f"Error creating PR: {e}"
            self.logger.error(error_msg)
            return PRResult(success=False, branch_name=branch_name, error=str(e))

    def create_notification(
        self,
        issues: list[dict],
        pr_result: PRResult | None = None,
        implemented: list[dict] | None = None,
        skipped: list[tuple[dict, FixResult, str | None]] | None = None,
    ):
        """Create a notification with findings."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notification_dir / f"{timestamp}-codebase-analysis.md"

        self.notification_dir.mkdir(parents=True, exist_ok=True)

        implemented = implemented or []
        skipped = skipped or []

        content = "# Codebase Analysis\n\n"
        content += f"**Found {len(issues)} issues**\n"
        content += f"**Mode**: {'Full analysis' if self.full_analysis else f'Incremental (last {self.since_days} days)'}\n\n"

        if pr_result:
            if pr_result.success and pr_result.pr_url:
                content += f"**PR Created**: {pr_result.pr_url}\n\n"
            else:
                content += "**PR Creation Failed**\n"
                if pr_result.error:
                    content += f"- Error: {pr_result.error}\n"
                if pr_result.branch_name:
                    content += f"- Branch: `{pr_result.branch_name}` (changes committed locally)\n"
                content += "\n"

        if implemented or skipped:
            content += f"**Fixed**: {len(implemented)} | **Skipped**: {len(skipped)}\n\n"

        categories_order = [
            ("code_quality", "Code Quality"),
            ("structural", "Structural Issues"),
            ("unused_code", "Unused/Obsolete Code"),
            ("duplication", "Duplication"),
            ("documentation", "Documentation Drift"),
            ("symlinks", "Symlinks"),
            ("naming", "Naming Consistency"),
            ("patterns", "Pattern Consistency"),
        ]

        for cat_key, cat_name in categories_order:
            cat_issues = [i for i in issues if i.get("category") == cat_key]
            if not cat_issues:
                continue

            high_cat = [i for i in cat_issues if i.get("priority") == "HIGH"]
            medium_cat = [i for i in cat_issues if i.get("priority") == "MEDIUM"]

            content += f"## {cat_name}\n\n"

            if high_cat:
                content += "**HIGH:**\n"
                for i in high_cat:
                    auto = "[auto]" if i.get("auto_fixable", True) else "[manual]"
                    content += f"- {auto} `{i['file']}`: {i['description']}\n"
                    if i.get("suggestion"):
                        content += f"  - Fix: {i['suggestion'][:80]}\n"

            if medium_cat:
                content += "**MEDIUM:**\n"
                for i in medium_cat:
                    auto = "[auto]" if i.get("auto_fixable", True) else "[manual]"
                    content += f"- {auto} `{i['file']}`: {i['description']}\n"
                    if i.get("suggestion"):
                        content += f"  - Fix: {i['suggestion'][:80]}\n"

            content += "\n"

        other_issues = [i for i in issues if i.get("category") not in dict(categories_order)]
        if other_issues:
            content += "## Other Issues\n\n"
            for i in other_issues:
                priority = "HIGH" if i.get("priority") == "HIGH" else "MEDIUM"
                content += f"- [{priority}] `{i['file']}`: {i['description']}\n"
            content += "\n"

        if skipped:
            content += "## Skipped (couldn't auto-fix)\n\n"
            for issue, fix_result, detail in skipped:
                reason = fix_result.value.replace("_", " ")
                content += f"- `{issue['file']}`: **{reason}**"
                if detail:
                    content += f" - {detail}"
                content += f"\n  - {issue['description'][:100]}\n"
            content += "\n"

        content += "---\n"
        content += "**Legend**: [auto] Auto-fixable | [manual] Needs human review\n\n"
        content += f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

        notif_file.write_text(content)
        self.logger.info(f"Notification: {notif_file}")

    def run(self, implement: bool = False, max_fixes: int = 10):
        """Main analysis workflow."""
        self.logger.info("=" * 60)
        self.logger.info("Codebase Analyzer")
        self.logger.info(
            f"Mode: {'Full' if self.full_analysis else f'Incremental ({self.since_days} days)'}"
        )
        self.logger.info("=" * 60)

        # Single-pass scan
        files, _structural_info = self.scan_codebase_single_pass()

        if not files:
            self.logger.info("No files to analyze")
            return

        # Analyze
        issues = self.analyze_codebase(files)

        if not issues:
            self.logger.info("No issues found")
            return

        # Implement fixes if requested
        pr_result = None
        implemented = []
        skipped = []

        if implement:
            self.logger.info(f"\nImplementing top {max_fixes} fixes...")
            to_fix = issues[:max_fixes]

            for issue in to_fix:
                result, detail = self.implement_fix(issue)
                if result == FixResult.SUCCESS:
                    implemented.append(issue)
                else:
                    skipped.append((issue, result, detail))

            self.logger.info(f"Implemented {len(implemented)}/{len(to_fix)} fixes")
            if skipped:
                self.logger.info(f"Skipped {len(skipped)} issues (see PR/notification for details)")

            if implemented:
                pr_result = self.create_pr(implemented, skipped)
                if pr_result.success:
                    self.logger.info(f"PR created: {pr_result.pr_url}")
                else:
                    self.logger.error(f"PR creation failed: {pr_result.error}")
                    if pr_result.branch_name:
                        self.logger.info(f"Changes are on branch: {pr_result.branch_name}")
            else:
                self.logger.warning("All fixes were skipped - no PR created")
                pr_result = PRResult(
                    success=False, error="All fix attempts were skipped (see skipped issues below)"
                )

        # Create notification
        self.create_notification(issues, pr_result, implemented, skipped)

        self.logger.info("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze codebase for improvements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Analysis Modes:
  Default       - Analyze files changed in last 7 days (incremental)
  --full        - Analyze entire codebase
  --since N     - Analyze files changed in last N days

Analysis Categories:
  code_quality   - Error handling, exceptions, code style
  structural     - Directory organization, file placement
  unused         - Dead code, obsolete files
  duplication    - Similar code, repeated implementations
  documentation  - README accuracy, outdated docs
  patterns       - Design pattern consistency

Examples:
  %(prog)s                           # Incremental analysis (default)
  %(prog)s --full                    # Full codebase analysis
  %(prog)s --since 14                # Files changed in last 14 days
  %(prog)s --focus structural        # Focus on structural issues
  %(prog)s --implement               # Auto-fix top 10 issues, create PR
  %(prog)s --implement --max-fixes 5 # Auto-fix top 5 issues
  %(prog)s --full --implement        # Full analysis with auto-fix
""",
    )
    parser.add_argument("--implement", action="store_true", help="Implement fixes and create PR")
    parser.add_argument("--max-fixes", type=int, default=10, help="Max fixes to implement")
    parser.add_argument(
        "--focus",
        type=str,
        choices=["structural", "duplication", "unused", "documentation", "patterns"],
        help="Focus analysis on a specific category",
    )
    parser.add_argument(
        "--full", action="store_true", help="Analyze entire codebase (default: only recent changes)"
    )
    parser.add_argument(
        "--since",
        type=int,
        default=7,
        help="Analyze files changed in last N days (default: 7, ignored with --full)",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force run (ignored, kept for compatibility)"
    )

    args = parser.parse_args()

    codebase_path = Path.home() / "khan" / "james-in-a-box"
    notification_dir = Path.home() / "sharing" / "notifications"

    if not codebase_path.exists():
        print(f"Error: {codebase_path} not found", file=sys.stderr)
        sys.exit(1)

    try:
        analyzer = CodebaseAnalyzer(
            codebase_path,
            notification_dir,
            focus=args.focus,
            full_analysis=args.full,
            since_days=args.since,
        )
        analyzer.run(implement=args.implement, max_fixes=args.max_fixes)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
