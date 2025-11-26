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

Efficiency Features:
- Uses ONE Claude call to analyze all files at once (not one per file)
- Git-based change detection: Only analyzes files changed since last run
- Single directory walk: Consolidated file iteration (not multiple rglobs)
- Linter config discovery: Detects and includes pyproject.toml, ruff.toml, etc.

Usage:
  codebase-analyzer.py                    # Incremental analysis (changed files only)
  codebase-analyzer.py --full-analysis    # Full analysis of all files
  codebase-analyzer.py --implement        # Analyze, fix top 10 issues, open PR
  codebase-analyzer.py --implement --max-fixes 5  # Fix top 5 issues
  codebase-analyzer.py --focus structural  # Focus on structural analysis
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


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
class LinterConfig:
    """Information about linter/formatter configuration."""

    config_file: str  # e.g., "pyproject.toml", "ruff.toml"
    tool: str  # e.g., "ruff", "flake8", "eslint"
    content: str  # Full content of the config file
    rules_enabled: list[str] = field(default_factory=list)  # e.g., ["E", "W", "F"]
    rules_ignored: list[str] = field(default_factory=list)  # e.g., ["E501", "PLR0913"]


@dataclass
class StructuralInfo:
    """Information about codebase structure."""

    directory_tree: dict[str, list[str]] = field(default_factory=dict)
    file_types: dict[str, int] = field(default_factory=dict)
    symlinks: dict[str, str] = field(default_factory=dict)  # symlink -> target
    broken_symlinks: list[str] = field(default_factory=list)
    readme_files: list[str] = field(default_factory=list)
    naming_patterns: dict[str, list[str]] = field(default_factory=dict)  # pattern -> files
    linter_configs: list[LinterConfig] = field(default_factory=list)  # Linter configurations


@dataclass
class PRResult:
    """Result of PR creation attempt."""

    success: bool
    pr_url: str | None = None
    branch_name: str | None = None
    error: str | None = None


class CodebaseAnalyzer:
    """Analyzes codebase for improvements using a single Claude Code call."""

    # State file to track last run timestamp
    STATE_FILE_NAME = ".codebase-analyzer-state.json"

    def __init__(
        self,
        codebase_path: Path,
        notification_dir: Path,
        focus: str | None = None,
        full_analysis: bool = False,
    ):
        self.codebase_path = codebase_path
        self.notification_dir = notification_dir
        self.focus = focus  # Optional focus category
        self.full_analysis = full_analysis  # If True, skip change detection
        self.logger = self._setup_logging()

        # Check for claude CLI
        if not self._check_claude_cli():
            self.logger.error("claude CLI not found in PATH")
            raise ValueError("claude command not available")

        # Load gitignore patterns
        self.gitignore_patterns = self._load_gitignore_patterns()
        self.always_ignore = {".git", "__pycache__", "node_modules", ".venv"}

        # Structural information (populated during analysis)
        self.structural_info: StructuralInfo | None = None

        # State tracking
        self.state_file = notification_dir / self.STATE_FILE_NAME
        self.last_run_commit: str | None = None
        self._load_state()

    def _check_claude_cli(self) -> bool:
        """Check if claude CLI is available."""
        try:
            result = subprocess.run(
                ["claude", "--version"], check=False, capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

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

    def _load_gitignore_patterns(self) -> set[str]:
        """Load and parse .gitignore file."""
        patterns = set()
        gitignore_path = self.codebase_path / ".gitignore"

        if gitignore_path.exists():
            try:
                with open(gitignore_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.split("#")[0].strip()
                        if line:
                            patterns.add(line)
            except Exception as e:
                self.logger.warning(f"Error reading .gitignore: {e}")

        return patterns

    def _load_state(self):
        """Load state from previous run."""
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    state = json.load(f)
                    self.last_run_commit = state.get("last_commit")
                    self.logger.info(f"Loaded state: last commit {self.last_run_commit[:8] if self.last_run_commit else 'None'}")
            except Exception as e:
                self.logger.warning(f"Error loading state: {e}")

    def _save_state(self, current_commit: str):
        """Save state for next run."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({"last_commit": current_commit, "timestamp": datetime.now().isoformat()}, f)
            self.logger.info(f"Saved state: commit {current_commit[:8]}")
        except Exception as e:
            self.logger.warning(f"Error saving state: {e}")

    def _get_current_commit(self) -> str | None:
        """Get the current HEAD commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.codebase_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            self.logger.warning(f"Error getting current commit: {e}")
        return None

    def _get_changed_files_since(self, since_commit: str) -> set[str]:
        """Get list of files changed since the given commit.

        Returns relative paths of changed files.
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", since_commit, "HEAD"],
                cwd=self.codebase_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if result.returncode == 0:
                files = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
                # Also include untracked files
                result2 = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    cwd=self.codebase_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
                if result2.returncode == 0 and result2.stdout.strip():
                    files.update(result2.stdout.strip().split("\n"))
                return files
        except Exception as e:
            self.logger.warning(f"Error getting changed files: {e}")
        return set()

    def _should_analyze(self, file_path: Path) -> bool:
        """Determine if file should be analyzed."""
        # Check always-ignore patterns
        for pattern in self.always_ignore:
            if pattern in str(file_path):
                return False

        # Only analyze specific file types
        valid_extensions = {".py", ".sh", ".md", ".yml", ".yaml", ".json"}
        if file_path.suffix.lower() not in valid_extensions and file_path.name != "Dockerfile":
            return False

        # Skip very large files (>50KB)
        try:
            if file_path.stat().st_size > 50_000:
                return False
        except OSError:
            return False

        return True

    def get_files_to_analyze(self) -> list[Path]:
        """Get list of files to analyze from codebase.

        Uses git-based change detection when possible:
        - If --full-analysis: analyze all files
        - If last_run_commit exists: only analyze changed files
        - Otherwise: analyze all files (first run)

        Uses a single directory walk instead of multiple rglob calls.
        """
        # Determine if we should use incremental analysis
        current_commit = self._get_current_commit()
        changed_files: set[str] | None = None

        if not self.full_analysis and self.last_run_commit and current_commit:
            # Check if last_run_commit still exists
            try:
                result = subprocess.run(
                    ["git", "cat-file", "-t", self.last_run_commit],
                    cwd=self.codebase_path,
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
                if result.returncode == 0:
                    changed_files = self._get_changed_files_since(self.last_run_commit)
                    if changed_files:
                        self.logger.info(f"Incremental analysis: {len(changed_files)} files changed since {self.last_run_commit[:8]}")
                    else:
                        self.logger.info(f"No files changed since {self.last_run_commit[:8]} - nothing to analyze")
                        return []
                else:
                    self.logger.warning(f"Last commit {self.last_run_commit[:8]} no longer exists, running full analysis")
            except Exception as e:
                self.logger.warning(f"Error checking commit: {e}, running full analysis")

        if self.full_analysis:
            self.logger.info("Running full analysis (--full-analysis flag)")

        # Single directory walk - collect all data in one pass
        files = []
        for file_path in self.codebase_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Apply change detection filter if available
            if changed_files is not None:
                rel_path = str(file_path.relative_to(self.codebase_path))
                if rel_path not in changed_files:
                    continue

            if self._should_analyze(file_path):
                files.append(file_path)

        self.logger.info(f"Found {len(files)} files to analyze")
        return files

    def gather_structural_info(self) -> StructuralInfo:
        """Gather structural information about the codebase for analysis.

        OPTIMIZED: Uses a single directory walk instead of multiple rglob calls.
        Also detects linter/formatter configurations for Claude to use.
        """
        info = StructuralInfo()

        # Linter config file patterns
        linter_config_files = {
            "pyproject.toml": "ruff",
            "ruff.toml": "ruff",
            ".ruff.toml": "ruff",
            ".flake8": "flake8",
            "setup.cfg": "flake8",
            ".pylintrc": "pylint",
            "pylintrc": "pylint",
            ".eslintrc": "eslint",
            ".eslintrc.js": "eslint",
            ".eslintrc.json": "eslint",
            ".prettierrc": "prettier",
            ".prettierrc.json": "prettier",
            "biome.json": "biome",
        }

        # SINGLE directory walk - collect all data in one pass
        for path in self.codebase_path.rglob("*"):
            # Skip ignored patterns
            if any(ig in str(path) for ig in self.always_ignore):
                continue

            rel_path = path.relative_to(self.codebase_path)
            rel_path_str = str(rel_path)
            parent = str(rel_path.parent) if rel_path.parent != Path(".") else "."

            # Handle symlinks (check before is_file/is_dir as symlinks can be both)
            if path.is_symlink():
                target = os.readlink(path)
                info.symlinks[rel_path_str] = target
                # Check if target exists
                resolved = path.parent / target
                if not resolved.exists():
                    info.broken_symlinks.append(rel_path_str)
                continue  # Don't process symlinks further

            # Handle directories
            if path.is_dir():
                if parent not in info.directory_tree:
                    info.directory_tree[parent] = []
                info.directory_tree[parent].append(str(rel_path.name))
                continue

            # Handle files
            if path.is_file():
                # Track file types
                ext = path.suffix.lower() or "no_extension"
                info.file_types[ext] = info.file_types.get(ext, 0) + 1

                # Track README files
                if path.name.lower().startswith("readme"):
                    info.readme_files.append(rel_path_str)

                # Track naming patterns for Python/shell scripts
                if path.suffix in {".py", ".sh"}:
                    name = path.stem
                    # Categorize naming patterns
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
                    info.naming_patterns[pattern].append(rel_path_str)

                # Detect linter configuration files
                if path.name in linter_config_files:
                    linter_tool = linter_config_files[path.name]
                    try:
                        content = path.read_text(encoding="utf-8", errors="ignore")
                        linter_config = self._parse_linter_config(rel_path_str, linter_tool, content)
                        if linter_config:
                            info.linter_configs.append(linter_config)
                            self.logger.info(f"Found {linter_tool} config: {rel_path_str}")
                    except Exception as e:
                        self.logger.warning(f"Error reading linter config {path}: {e}")

        self.structural_info = info
        return info

    def _parse_linter_config(self, config_file: str, tool: str, content: str) -> LinterConfig | None:
        """Parse a linter configuration file to extract rules.

        This helps Claude understand what lint rules are enabled/disabled.
        """
        rules_enabled = []
        rules_ignored = []

        try:
            if tool == "ruff" and config_file.endswith(".toml"):
                # Parse TOML for ruff configuration
                # Look for [tool.ruff.lint] section
                import re

                # Find select = [...] pattern
                select_match = re.search(r'select\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if select_match:
                    # Extract rule codes
                    rules_text = select_match.group(1)
                    rules_enabled = re.findall(r'"([A-Z0-9]+)"', rules_text)

                # Find ignore = [...] pattern
                ignore_match = re.search(r'ignore\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if ignore_match:
                    rules_text = ignore_match.group(1)
                    rules_ignored = re.findall(r'"([A-Z0-9]+)"', rules_text)

            elif tool == "flake8":
                # Parse flake8 config (ini-style)
                # Look for select = and ignore = lines
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("select"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            rules_enabled = [r.strip() for r in parts[1].split(",") if r.strip()]
                    elif line.startswith("ignore"):
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            rules_ignored = [r.strip() for r in parts[1].split(",") if r.strip()]

            elif tool == "eslint":
                # For ESLint, just include the full content (JSON or JS)
                # Parsing is complex, let Claude interpret it
                pass

        except Exception as e:
            self.logger.debug(f"Error parsing {config_file}: {e}")

        return LinterConfig(
            config_file=config_file,
            tool=tool,
            content=content,
            rules_enabled=rules_enabled,
            rules_ignored=rules_ignored,
        )

    def detect_potential_duplicates(self, files: list[Path]) -> list[tuple[str, str, float]]:
        """Detect potentially duplicated code by comparing file content hashes and structure.

        Returns list of (file1, file2, similarity_score) tuples.
        """
        duplicates = []

        # Group files by size (similar size = potential duplicate)
        size_groups: dict[int, list[Path]] = defaultdict(list)
        for f in files:
            try:
                size = f.stat().st_size
                # Group by size bucket (within 20% of each other)
                bucket = size // 100 * 100
                size_groups[bucket].append(f)
            except OSError:
                continue

        # For groups with multiple files, compare content
        for _bucket, group in size_groups.items():
            if len(group) < 2:
                continue

            # Compare files in group
            for i, f1 in enumerate(group):
                for f2 in group[i + 1 :]:
                    try:
                        c1 = f1.read_text(encoding="utf-8", errors="ignore")
                        c2 = f2.read_text(encoding="utf-8", errors="ignore")

                        # Simple similarity: line-based comparison
                        lines1 = set(c1.strip().split("\n"))
                        lines2 = set(c2.strip().split("\n"))

                        if not lines1 or not lines2:
                            continue

                        intersection = len(lines1 & lines2)
                        union = len(lines1 | lines2)
                        similarity = intersection / union if union > 0 else 0

                        if similarity > 0.5:  # More than 50% similar
                            rel1 = str(f1.relative_to(self.codebase_path))
                            rel2 = str(f2.relative_to(self.codebase_path))
                            duplicates.append((rel1, rel2, similarity))
                    except Exception:
                        continue

        return duplicates

    def check_readme_consistency(self, files: list[Path]) -> list[dict]:
        """Check if README files reference files that exist or are missing."""
        issues = []

        for readme_path in files:
            if not readme_path.name.lower().startswith("readme"):
                continue

            try:
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                rel_readme = str(readme_path.relative_to(self.codebase_path))
                readme_dir = readme_path.parent

                # Find file/path references in README
                # Look for: `filename`, ./filename, ../filename, path/to/file
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
                    # Skip URLs and anchors
                    if ref.startswith(("http", "#")):
                        continue

                    # Check if file exists relative to README location
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
                            }
                        )

            except Exception as e:
                self.logger.warning(f"Error checking README {readme_path}: {e}")

        return issues

    def build_codebase_summary(self, files: list[Path]) -> str:
        """Build a summary of the codebase for Claude to analyze."""
        summary_parts = []

        for file_path in files:
            try:
                rel_path = file_path.relative_to(self.codebase_path)
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                # Truncate large files
                if len(content) > 3000:
                    content = content[:3000] + "\n... [truncated]"

                summary_parts.append(f"=== FILE: {rel_path} ===\n{content}\n")

            except Exception as e:
                self.logger.warning(f"Error reading {file_path}: {e}")

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

        # Linter/formatter configurations - IMPORTANT for Claude to understand lint rules
        if structural_info.linter_configs:
            context_parts.append("\n=== LINTER/FORMATTER CONFIGURATION ===")
            context_parts.append("Use these rules when analyzing code for style/lint issues:")
            for config in structural_info.linter_configs:
                context_parts.append(f"\n--- {config.tool.upper()} ({config.config_file}) ---")
                if config.rules_enabled:
                    context_parts.append(f"Enabled rules: {', '.join(config.rules_enabled)}")
                if config.rules_ignored:
                    context_parts.append(f"Ignored rules: {', '.join(config.rules_ignored)}")
                # Include full config content (truncated if too long)
                config_content = config.content
                if len(config_content) > 2000:
                    config_content = config_content[:2000] + "\n... [truncated]"
                context_parts.append(f"\nFull config:\n{config_content}")

        return "\n".join(context_parts)

    def analyze_codebase(self, files: list[Path]) -> list[dict]:
        """Analyze entire codebase in a single Claude call."""
        self.logger.info("Gathering structural information...")
        structural_info = self.gather_structural_info()

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

        prompt = f"""Analyze this codebase for issues that can be automatically fixed or flagged for human review.

CODEBASE: james-in-a-box (Docker sandbox for Claude Code CLI)

{structural_context}

{codebase_summary}

TASK: Identify the top 15-20 HIGH and MEDIUM priority issues across ALL categories.
{focus_instructions}

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

        try:
            result = subprocess.run(
                ["claude", "--dangerously-skip-permissions"],
                check=False,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for large analysis
            )

            if result.returncode != 0:
                self.logger.error(f"Claude returned error: {result.stderr}")
                return []

            response = result.stdout.strip()

            # Extract JSON from response
            try:
                # Find JSON array in response
                start_idx = response.find("[")
                end_idx = response.rfind("]") + 1
                if start_idx != -1 and end_idx > start_idx:
                    json_str = response[start_idx:end_idx]
                    issues = json.loads(json_str)

                    # Merge pre-detected README issues (avoid duplicates)
                    existing_files = {i.get("file") for i in issues}
                    for readme_issue in readme_issues:
                        if readme_issue["file"] not in existing_files:
                            issues.append(readme_issue)

                    # Add broken symlink issues
                    for broken_link in structural_info.broken_symlinks:
                        if broken_link not in existing_files:
                            issues.append(
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

                    self.logger.info(f"Found {len(issues)} total issues")
                    return issues
                else:
                    self.logger.warning("No JSON array found in response")
                    # Return pre-detected issues even if Claude fails
                    return readme_issues + [
                        {
                            "file": link,
                            "line_hint": "symlink",
                            "priority": "HIGH",
                            "category": "symlinks",
                            "description": "Broken symlink",
                            "suggestion": "Fix or remove",
                            "auto_fixable": False,
                        }
                        for link in structural_info.broken_symlinks
                    ]
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON: {e}")
                self.logger.debug(f"Response was: {response[:500]}")
                return readme_issues  # Return pre-detected issues on parse failure

        except subprocess.TimeoutExpired:
            self.logger.error("Claude call timed out")
            return readme_issues  # Return pre-detected issues on timeout
        except Exception as e:
            self.logger.error(f"Error calling Claude: {e}")
            return readme_issues  # Return pre-detected issues on error

    def _detect_meta_commentary(self, content: str, file_ext: str) -> tuple[bool, str | None]:
        """Detect if output contains AI meta-commentary mixed into the file content.

        Returns:
            Tuple of (has_meta_commentary, detail_string)
        """
        # Patterns that indicate AI explanation/reasoning mixed into output
        meta_patterns = [
            # Reasoning/explanation phrases
            r"^(?:Here(?:'s| is) (?:the|my|your)|I(?:'ve| have) (?:made|fixed|updated))",
            r"^(?:The (?:issue|problem|fix|change|solution)|This (?:fixes|resolves|addresses))",
            r"^(?:I (?:will|can|cannot|can't|am|have|don't)|Let me)",
            r"^(?:Note:|Summary:|Explanation:|Changes made:|What I changed:)",
            r"^(?:Unfortunately|Apologies|I apologize|I'm sorry)",
            # Common AI response starters that shouldn't be in code
            r"^(?:Sure|Certainly|Of course|Absolutely)[,!.]",
            r"^(?:Great|Perfect|Excellent)[,!.]",
            # Markdown-style headers that shouldn't be in code files
            r"^#{1,3} (?:Changes|Summary|Fix|Solution|Updated)",
        ]

        # Check first 5 lines for meta-commentary patterns
        lines = content.split("\n")[:5]
        for i, line in enumerate(lines):
            line = line.strip()
            for pattern in meta_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    return (True, f"Line {i + 1} contains meta-commentary: '{line[:50]}...'")

        # For Python/shell files, check if first non-comment line looks like prose
        if file_ext in {".py", ".sh"}:
            for i, line in enumerate(lines[:3]):
                stripped = line.strip()
                # Skip empty lines, shebangs, and comments
                if not stripped or stripped.startswith("#"):
                    continue
                # Check if line looks like prose (starts with capital, ends with period)
                if (
                    stripped[0].isupper()
                    and stripped.endswith(".")
                    and " " in stripped
                    and not stripped.startswith(("class ", "def ", "import ", "from "))
                ):
                    # Looks like prose, not code
                    return (True, f"Line {i + 1} appears to be prose: '{stripped[:50]}...'")
                break  # Stop at first actual code line

        # Check for explanation blocks that might be mixed in
        explanation_markers = [
            "```",  # Nested markdown fences
            "---",  # Markdown horizontal rules (multiple occurrences)
            "**Changes:**",
            "**Summary:**",
            "**Note:**",
        ]
        marker_count = sum(1 for m in explanation_markers if m in content)
        if marker_count >= 2:
            return (True, f"Found {marker_count} explanation markers in content")

        return (False, None)

    def implement_fix(self, issue: dict) -> tuple[FixResult, str | None]:
        """Implement a single fix using Claude Code.

        Returns:
            Tuple of (FixResult, details_string)
        """
        # Skip issues marked as not auto-fixable
        if not issue.get("auto_fixable", True):
            detail = f"Issue requires human review ({issue.get('category', 'unknown')})"
            self.logger.info(f"Skipping {issue['file']}: {detail}")
            return (FixResult.REQUIRES_RESTRUCTURING, detail)

        # Skip structural issues (directory moves, deletions, etc.)
        if issue.get("category") in ["structural", "unused_code", "symlinks"]:
            detail = "Structural change requires human review"
            self.logger.info(f"Skipping {issue['file']}: {detail}")
            return (FixResult.REQUIRES_RESTRUCTURING, detail)

        file_path = self.codebase_path / issue["file"]

        if not file_path.exists():
            self.logger.warning(f"File not found: {file_path}")
            return (FixResult.FILE_NOT_FOUND, None)

        # Skip if path is a directory
        if file_path.is_dir():
            return (FixResult.REQUIRES_RESTRUCTURING, "Target is a directory")

        try:
            content = file_path.read_text(encoding="utf-8")
            file_size = len(content)

            # Skip files that are too large for the full-rewrite approach
            # Large files take too long and often timeout
            max_size_for_fix = 20_000  # 20KB
            if file_size > max_size_for_fix:
                detail = f"{file_size // 1000}KB exceeds {max_size_for_fix // 1000}KB limit"
                self.logger.warning(
                    f"Skipping {issue['file']} ({file_size // 1000}KB) - too large for auto-fix"
                )
                return (FixResult.FILE_TOO_LARGE, detail)

            # Scale timeout based on file size (60s base + 1s per 200 chars)
            timeout_seconds = max(120, 60 + file_size // 200)

            # Determine expected file structure for validation hint
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

            result = subprocess.run(
                ["claude", "--dangerously-skip-permissions"],
                check=False,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            if result.returncode != 0:
                self.logger.error(f"Claude error for {issue['file']}: {result.stderr}")
                return (FixResult.CLAUDE_ERROR, result.stderr[:200] if result.stderr else None)

            fixed_content = result.stdout.strip()

            # Remove markdown fences if present
            if fixed_content.startswith("```"):
                lines = fixed_content.split("\n")
                # Remove language identifier line (e.g., ```python)
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                fixed_content = "\n".join(lines)

            # Also remove trailing fence if content doesn't start with fence
            if fixed_content.rstrip().endswith("```"):
                lines = fixed_content.split("\n")
                while lines and lines[-1].strip() in ("```", ""):
                    lines = lines[:-1]
                fixed_content = "\n".join(lines)

            # Comprehensive meta-commentary detection
            has_meta, meta_detail = self._detect_meta_commentary(fixed_content, file_ext)
            if has_meta:
                self.logger.warning(f"Meta-commentary detected in {issue['file']}: {meta_detail}")
                return (FixResult.META_COMMENTARY, meta_detail)

            # Validate the fix by size
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

            # Write the fix
            file_path.write_text(fixed_content, encoding="utf-8")
            self.logger.info(f"✓ Fixed: {issue['file']} ({issue['category']})")
            return (FixResult.SUCCESS, None)

        except subprocess.TimeoutExpired:
            detail = f"exceeded {timeout_seconds}s timeout"
            self.logger.error(f"Timeout fixing {issue['file']}: {detail}")
            return (FixResult.TIMEOUT, detail)
        except Exception as e:
            self.logger.error(f"Error fixing {issue['file']}: {e}")
            return (FixResult.OTHER_ERROR, str(e)[:200])

    def create_pr(
        self,
        implemented: list[dict],
        skipped: list[tuple[dict, FixResult, str | None]] | None = None,
    ) -> PRResult:
        """Commit changes and create a PR.

        Args:
            implemented: List of issues that were successfully fixed
            skipped: List of (issue, result, detail) tuples for issues that couldn't be fixed

        Returns:
            PRResult with success status, PR URL (if created), branch name, and any error
        """
        if not implemented:
            return PRResult(success=False, error="No issues were successfully fixed")

        skipped = skipped or []
        branch_name = None

        try:
            # Check for changes
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

            # Create branch
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"auto-fix/codebase-{timestamp}"

            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self.codebase_path,
                check=True,
                capture_output=True,
            )

            # Stage and commit
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

            # Push
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

            # Create PR body
            pr_body = f"## Auto-fix: {len(implemented)} improvements\n\n"
            for cat in sorted(categories):
                cat_issues = [i for i in implemented if i["category"] == cat]
                pr_body += f"### {cat.title()} ({len(cat_issues)})\n"
                for i in cat_issues:
                    pr_body += f"- `{i['file']}`: {i['description'][:60]}\n"
                pr_body += "\n"

            # Add skipped section if any
            if skipped:
                pr_body += f"## ⚠️ Skipped Issues ({len(skipped)})\n\n"
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
            self.logger.info(f"✓ Created PR: {pr_url}")
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
        """Create a notification with findings.

        Args:
            issues: All issues found during analysis
            pr_result: Result of PR creation attempt (if any)
            implemented: Issues that were successfully fixed
            skipped: Issues that couldn't be auto-fixed (issue, result, detail)
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        notif_file = self.notification_dir / f"{timestamp}-codebase-analysis.md"

        self.notification_dir.mkdir(parents=True, exist_ok=True)

        implemented = implemented or []
        skipped = skipped or []

        content = "# 🔍 Codebase Analysis\n\n"
        content += f"**Found {len(issues)} issues**\n\n"

        # Show PR result with details
        if pr_result:
            if pr_result.success and pr_result.pr_url:
                content += f"**PR Created**: {pr_result.pr_url}\n\n"
            else:
                content += "**⚠️ PR Creation Failed**\n"
                if pr_result.error:
                    content += f"- Error: {pr_result.error}\n"
                if pr_result.branch_name:
                    content += f"- Branch: `{pr_result.branch_name}` (changes committed locally)\n"
                content += "\n"

        if implemented or skipped:
            content += f"**Fixed**: {len(implemented)} | **Skipped**: {len(skipped)}\n\n"

        # Group by category first, then by priority
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

        # Build category-priority groups
        for cat_key, cat_name in categories_order:
            cat_issues = [i for i in issues if i.get("category") == cat_key]
            if not cat_issues:
                continue

            high_cat = [i for i in cat_issues if i.get("priority") == "HIGH"]
            medium_cat = [i for i in cat_issues if i.get("priority") == "MEDIUM"]

            content += f"## {cat_name}\n\n"

            if high_cat:
                content += "**🔴 HIGH:**\n"
                for i in high_cat:
                    auto = "✅" if i.get("auto_fixable", True) else "👤"
                    content += f"- {auto} `{i['file']}`: {i['description']}\n"
                    if i.get("suggestion"):
                        content += f"  - Fix: {i['suggestion'][:80]}\n"

            if medium_cat:
                content += "**🟡 MEDIUM:**\n"
                for i in medium_cat:
                    auto = "✅" if i.get("auto_fixable", True) else "👤"
                    content += f"- {auto} `{i['file']}`: {i['description']}\n"
                    if i.get("suggestion"):
                        content += f"  - Fix: {i['suggestion'][:80]}\n"

            content += "\n"

        # Issues without a recognized category
        other_issues = [i for i in issues if i.get("category") not in dict(categories_order)]
        if other_issues:
            content += "## Other Issues\n\n"
            for i in other_issues:
                priority_icon = "🔴" if i.get("priority") == "HIGH" else "🟡"
                content += f"- {priority_icon} `{i['file']}`: {i['description']}\n"
            content += "\n"

        # Skipped issues section (for --implement mode)
        if skipped:
            content += "## ⚠️ Skipped (couldn't auto-fix)\n\n"
            for issue, fix_result, detail in skipped:
                reason = fix_result.value.replace("_", " ")
                content += f"- `{issue['file']}`: **{reason}**"
                if detail:
                    content += f" - {detail}"
                content += f"\n  - {issue['description'][:100]}\n"
            content += "\n"

        # Legend
        content += "---\n"
        content += "**Legend**: ✅ Auto-fixable | 👤 Needs human review\n\n"
        content += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"

        notif_file.write_text(content)
        self.logger.info(f"Notification: {notif_file}")

    def run(self, implement: bool = False, max_fixes: int = 10):
        """Main analysis workflow."""
        self.logger.info("=" * 60)
        self.logger.info("Codebase Analyzer")
        if self.full_analysis:
            self.logger.info("Mode: Full Analysis")
        else:
            self.logger.info("Mode: Incremental (git-based change detection)")
        self.logger.info("=" * 60)

        # Get current commit for state tracking
        current_commit = self._get_current_commit()

        # Get files
        files = self.get_files_to_analyze()

        # If no files to analyze (no changes), still save state and exit early
        if not files:
            if current_commit:
                self._save_state(current_commit)
            self.logger.info("No files to analyze - exiting")
            return

        # Analyze (single Claude call)
        issues = self.analyze_codebase(files)

        if not issues:
            self.logger.info("No issues found")
            # Save state even if no issues found
            if current_commit:
                self._save_state(current_commit)
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
                # Create a PRResult to explain what happened
                pr_result = PRResult(
                    success=False, error="All fix attempts were skipped (see skipped issues below)"
                )

        # Create notification
        self.create_notification(issues, pr_result, implemented, skipped)

        # Save state after successful run
        if current_commit:
            self._save_state(current_commit)

        self.logger.info("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze codebase for improvements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Analysis Categories:
  code_quality   - Error handling, exceptions, code style
  structural     - Directory organization, file placement
  unused         - Dead code, obsolete files
  duplication    - Similar code, repeated implementations
  documentation  - README accuracy, outdated docs
  patterns       - Design pattern consistency

Efficiency Features:
  - Git-based change detection: Only analyzes files changed since last run
  - Single directory walk: Consolidated file iteration
  - Linter config discovery: Detects pyproject.toml, ruff.toml, etc.

Examples:
  %(prog)s                           # Incremental analysis (changed files only)
  %(prog)s --full-analysis           # Analyze ALL files (ignore change detection)
  %(prog)s --focus structural        # Focus on structural issues
  %(prog)s --implement               # Auto-fix top 10 issues, create PR
  %(prog)s --implement --max-fixes 5 # Auto-fix top 5 issues
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
        "--full-analysis",
        action="store_true",
        help="Analyze ALL files, bypassing git-based change detection",
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
            codebase_path, notification_dir, focus=args.focus, full_analysis=args.full_analysis
        )
        analyzer.run(implement=args.implement, max_fixes=args.max_fixes)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
