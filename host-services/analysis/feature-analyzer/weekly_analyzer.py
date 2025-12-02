#!/usr/bin/env python3
"""
Weekly Code Analyzer - FEATURES.md Auto-Discovery (Phase 5 Enhanced)

This module scans merged code from the past week and identifies new features
to add to FEATURES.md. It uses both commit analysis AND deep code-level
analysis with LLM-powered feature extraction.

The analyzer performs thorough analysis including:
1. Collects commits from the past N days
2. Phase 1: Commit-based feature extraction (original method)
3. Phase 2: Deep code analysis - reads actual file contents for thorough
   feature extraction, useful for poorly named commits
4. Phase 3: Documentation discovery - links features to existing docs
5. Phase 4: Documentation generation - auto-generates docs for undocumented features
6. Updates FEATURES.md with new entries including doc links
7. Creates PR for human review

Key Features:
- Deep code analysis reads source files, not just commit messages
- Extracts meaningful descriptions from docstrings and code comments
- Links each feature entry to its documentation (existing or generated)
- Auto-generates README.md for undocumented features
- FEATURES.md is hooked into docs/index.md for LLM navigation

Usage:
    analyzer = WeeklyAnalyzer(repo_root)
    result = analyzer.analyze_and_update(
        days=7,
        generate_docs=True,
        deep_analysis=True
    )

CLI:
    python weekly_analyzer.py --days 7 --repo-root /path/to/repo
    python weekly_analyzer.py --no-deep-analysis  # Skip code-level analysis
    python weekly_analyzer.py --no-docs           # Skip doc generation
"""

import json
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


# Add host-services shared modules to path (for jib_exec)
# NOTE: Host-side code must use jib_exec which invokes processors via jib --exec
# because Claude CLI is only available inside the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from jib_exec import jib_exec


def _run_llm_prompt_shared(
    repo_root: Path, prompt: str, context_name: str = ""
) -> tuple[bool, str, str | None]:
    """
    Run an LLM prompt via jib container.

    This shared function is used by both WeeklyAnalyzer and RepoAnalyzer.
    Host-side code cannot directly call Claude - it's only available inside
    the container. This method uses jib_exec to invoke the analysis processor.

    Args:
        repo_root: Path to the repository root
        prompt: The prompt to send to the LLM
        context_name: Optional name for logging/debugging

    Returns:
        Tuple of (success, stdout, error_message)
    """
    try:
        result = jib_exec(
            processor="jib-container/jib-tasks/analysis/analysis-processor.py",
            task_type="llm_prompt",
            context={
                "prompt": prompt,
                "cwd": str(repo_root),
                "stream": False,
            },
            # No timeout specified - let the shared claude module determine the default
        )

        if result.success and result.json_output:
            output = result.json_output.get("result", {})
            stdout = output.get("stdout", "")
            return (True, stdout, None)

        # Handle failure - build detailed error message
        error_parts = []

        # Check for jib-level error
        if result.error:
            error_parts.append(result.error)

        # Check for processor-level error in JSON response
        if result.json_output:
            processor_error = result.json_output.get("error")
            if processor_error:
                error_parts.append(f"Processor: {processor_error}")
            # Also check if there's a result with stderr
            processor_result = result.json_output.get("result", {})
            if isinstance(processor_result, dict) and processor_result.get("stderr"):
                error_parts.append(f"stderr: {processor_result['stderr'][:200]}")

        # If success=True but json_output is None, the jib command ran but
        # we couldn't parse the output - include raw stdout for debugging
        if result.success and not result.json_output:
            if result.stdout:
                stdout_preview = result.stdout[:300].replace("\n", "\\n")
                error_parts.append(f"jib succeeded but no JSON parsed. stdout: {stdout_preview}")
            else:
                error_parts.append("jib succeeded but returned empty stdout")

        # If nothing specific, check stderr
        if not error_parts and result.stderr:
            error_parts.append(f"stderr: {result.stderr[:200]}")

        # Build final error message
        error_msg = (
            "; ".join(error_parts) if error_parts else "Unknown error (no details available)"
        )
        return (False, "", error_msg)

    except Exception as e:
        return (False, "", str(e))


def _run_llm_prompt_to_file_shared(
    repo_root: Path, prompt: str, context_name: str = ""
) -> tuple[bool, list | dict | None, str | None]:
    """
    Run an LLM prompt that writes JSON output to a file.

    This avoids JSON parsing issues when the LLM includes explanatory text
    before/after the JSON in its stdout. The LLM writes JSON to a temp file,
    which is then read and parsed.

    Args:
        repo_root: Path to the repository root
        prompt: The prompt to send to the LLM (should request JSON output)
        context_name: Optional name for logging/debugging

    Returns:
        Tuple of (success, parsed_json_content, error_message)
    """
    try:
        result = jib_exec(
            processor="jib-container/jib-tasks/analysis/analysis-processor.py",
            task_type="llm_prompt_to_file",
            context={
                "prompt": prompt,
                "cwd": str(repo_root),
            },
            # No timeout specified - let the shared claude module determine the default
        )

        if result.success and result.json_output:
            output = result.json_output.get("result", {})
            json_content = output.get("json_content")
            if json_content is not None:
                return (True, json_content, None)
            # If json_content is None but success=True, there was an issue
            return (False, None, "LLM did not write JSON to file")

        # Handle failure
        error_parts = []

        if result.error:
            error_parts.append(result.error)

        if result.json_output:
            processor_error = result.json_output.get("error")
            if processor_error:
                error_parts.append(f"Processor: {processor_error}")

        error_msg = (
            "; ".join(error_parts) if error_parts else "Unknown error (no details available)"
        )
        return (False, None, error_msg)

    except Exception as e:
        return (False, None, str(e))


@dataclass
class CommitInfo:
    """Information about a single commit."""

    sha: str
    message: str
    author: str
    date: str
    files: list[str] = field(default_factory=list)
    diff: str = ""


@dataclass
class DetectedFeature:
    """A feature detected from code analysis."""

    name: str
    description: str
    status: str = "implemented"  # Always implemented since it's merged code
    category: str = ""  # e.g., "Analysis & Documentation", "Utilities"
    files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    introduced_in_commit: str = ""
    date_added: str = ""
    confidence: float = 0.0  # 0.0-1.0
    adr_reference: str = ""  # Optional ADR if detected
    needs_review: bool = False  # True if confidence < 0.7
    doc_path: str = ""  # Path to documentation file if exists
    doc_generated: bool = False  # True if doc was auto-generated
    # Hierarchical structure support
    sub_features: list["DetectedFeature"] = field(default_factory=list)
    is_symlink_duplicate: bool = False  # True if this is a symlinked copy


@dataclass
class AnalysisResult:
    """Result of weekly code analysis."""

    commits_analyzed: int = 0
    features_detected: list[DetectedFeature] = field(default_factory=list)
    features_added: list[DetectedFeature] = field(default_factory=list)
    features_skipped: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)
    docs_generated: list[str] = field(default_factory=list)  # Paths to generated docs
    errors: list[str] = field(default_factory=list)
    analysis_date: str = ""


@dataclass
class FullRepoAnalysisResult:
    """Result of full repository analysis."""

    directories_scanned: int = 0
    files_analyzed: int = 0
    features_detected: list[DetectedFeature] = field(default_factory=list)
    features_by_category: dict = field(default_factory=dict)  # category -> list[DetectedFeature]
    errors: list[str] = field(default_factory=list)
    analysis_date: str = ""
    output_file: str = ""


class WeeklyAnalyzer:
    """Analyzes weekly code changes and updates FEATURES.md."""

    # Directories that typically contain feature implementations
    FEATURE_DIRECTORIES = [
        "host-services/",
        "jib-container/scripts/",
        "jib-container/shared/",
    ]

    # Patterns that indicate significant new code (not just refactors)
    SIGNIFICANT_PATTERNS = [
        r"def\s+main\s*\(",  # New CLI tools
        r"class\s+\w+:",  # New classes
        r"argparse\.ArgumentParser",  # CLI argument parsing
        r"@dataclass",  # New data structures
        r"def\s+__init__\s*\(",  # Class initializers
        r"app\.route\(|@router\.",  # API endpoints
    ]

    # Categories for organizing features
    CATEGORY_MAPPINGS = {
        "host-services/analysis/": "Analysis & Documentation",
        "host-services/sync/": "Context Sync",
        "host-services/slack/": "Slack Integration",
        "host-services/utilities/": "Utilities",
        "jib-container/scripts/": "Container Infrastructure",
        "jib-container/shared/": "Container Infrastructure",
    }

    # Maximum number of files to analyze in deep analysis mode
    MAX_DEEP_ANALYSIS_FILES = 15

    def __init__(self, repo_root: Path, use_llm: bool = True):
        """
        Initialize the weekly analyzer.

        Args:
            repo_root: Path to the repository root
            use_llm: If True, use LLM for feature extraction
        """
        self.repo_root = repo_root
        self.use_llm = use_llm
        self.features_md = repo_root / "docs" / "FEATURES.md"

    def _run_llm_prompt(self, prompt: str, context_name: str = "") -> tuple[bool, str, str | None]:
        """
        Run an LLM prompt via jib container.

        Host-side code cannot directly call Claude - it's only available inside
        the container. This method uses jib_exec to invoke the analysis processor.

        Args:
            prompt: The prompt to send to the LLM
            context_name: Optional name for logging/debugging

        Returns:
            Tuple of (success, stdout, error_message)
        """
        return _run_llm_prompt_shared(self.repo_root, prompt, context_name)

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the repo root."""
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=check,
        )

    def get_commits_since(self, days: int = 7) -> list[CommitInfo]:
        """
        Get all commits from the past N days.

        Args:
            days: Number of days to look back

        Returns:
            List of CommitInfo objects
        """
        since_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

        # Get commits with format: sha|message|author|date
        result = self._run_git(
            "log",
            f"--since={since_date}",
            "--pretty=format:%H|%s|%an|%aI",
            "--no-merges",  # Skip merge commits
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append(
                    CommitInfo(
                        sha=parts[0],
                        message=parts[1],
                        author=parts[2],
                        date=parts[3],
                    )
                )

        return commits

    def get_commit_files(self, commit_sha: str) -> list[str]:
        """Get list of files changed in a commit."""
        result = self._run_git(
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit_sha,
            check=False,
        )

        if result.returncode != 0:
            return []

        return [f for f in result.stdout.strip().split("\n") if f]

    def get_commit_diff(self, commit_sha: str) -> str:
        """Get the diff for a commit."""
        result = self._run_git(
            "show",
            "--stat",
            "--patch",
            "--format=",  # Skip commit metadata
            commit_sha,
            check=False,
        )

        if result.returncode != 0:
            return ""

        # Truncate very large diffs
        diff = result.stdout
        if len(diff) > 50000:
            diff = diff[:50000] + "\n... [diff truncated]"

        return diff

    def is_feature_directory(self, file_path: str) -> bool:
        """Check if a file is in a feature-relevant directory."""
        return any(file_path.startswith(d) for d in self.FEATURE_DIRECTORIES)

    def get_category_for_file(self, file_path: str) -> str:
        """Determine the category for a file based on its path."""
        for prefix, category in self.CATEGORY_MAPPINGS.items():
            if file_path.startswith(prefix):
                return category
        return "Utilities"  # Default category

    def is_significant_change(self, diff: str) -> bool:
        """
        Check if a diff represents a significant change (not just refactoring).

        Returns True if the diff likely introduces new functionality.
        """
        return any(re.search(pattern, diff) for pattern in self.SIGNIFICANT_PATTERNS)

    def filter_feature_commits(self, commits: list[CommitInfo]) -> list[CommitInfo]:
        """
        Filter commits to those likely introducing new features.

        Excludes:
        - Refactors (commit message starts with "refactor:")
        - Documentation-only changes
        - Test-only changes (unless introducing new test framework)
        - Dependency updates
        """
        feature_commits = []

        for commit in commits:
            msg_lower = commit.message.lower()

            # Skip refactors, docs, chores
            skip_prefixes = [
                "refactor:",
                "refactor(",
                "docs:",
                "chore:",
                "ci:",
                "build:",
                "style:",
                "bump:",
                "update deps",
                "merge",
            ]
            if any(msg_lower.startswith(prefix) for prefix in skip_prefixes):
                continue

            # Get files for this commit
            commit.files = self.get_commit_files(commit.sha)

            # Skip if no files in feature directories
            feature_files = [f for f in commit.files if self.is_feature_directory(f)]
            if not feature_files:
                continue

            # Skip if only test files
            non_test_files = [f for f in feature_files if "test" not in f.lower()]
            if not non_test_files:
                continue

            feature_commits.append(commit)

        return feature_commits

    # Utility file patterns that should not be listed as features
    UTILITY_PATTERNS = [
        r"^setup\.py$",
        r"^__init__\.py$",
        r"^conftest\.py$",
        r"utils?/",  # Any file in utils/ or util/ directories
        r"helpers?/",  # Any file in helpers/ or helper/ directories
        r"create_symlink\.py$",
        r"get_space_ids\.py$",
        r"list_spaces\.py$",
        r"maintenance\.py$",
        r"link_to_.*\.py$",
    ]

    def _is_utility_file(self, file_path: str) -> bool:
        """Check if a file is a utility script that shouldn't be listed as a feature."""
        return any(re.search(pattern, file_path) for pattern in self.UTILITY_PATTERNS)

    def _generate_feature_extraction_prompt(self, commits: list[CommitInfo]) -> str:
        """Generate a prompt for LLM to extract features from commits."""
        commit_summaries = []
        for commit in commits:
            summary = f"""
## Commit: {commit.sha[:8]}
**Message:** {commit.message}
**Date:** {commit.date}
**Files changed:**
{chr(10).join("- " + f for f in commit.files[:20])}
"""
            if len(commit.files) > 20:
                summary += f"\n... and {len(commit.files) - 20} more files"
            commit_summaries.append(summary)

        commits_text = "\n---\n".join(commit_summaries)

        return f"""You are analyzing code commits to identify NEW FEATURES for documentation.

# Commits to Analyze

{commits_text}

# Your Task

Identify substantive new features from these commits. For each feature, provide:

1. **name**: A clear, human-readable feature name that describes what it does (NOT the filename).
   - Good: "Weekly Code Analyzer", "Slack Message Router", "Confluence Sync Service"
   - Bad: "Hook Handler", "Connector", "Setup" (too generic)

2. **description**: A meaningful one-sentence description explaining:
   - What the feature does
   - Why it's useful
   - NOT just "New tool at <path>" - that tells us nothing

3. **category**: "Analysis & Documentation", "Context Sync", "Slack Integration",
   "Task Tracking", "Git & GitHub Integration", "Container Infrastructure", or "Utilities"

4. **files**: Main implementation files (max 5)

5. **tests**: Test files if any

6. **confidence**: 0.0-1.0 based on how clearly this is a user-facing feature

# What IS a Feature?

- Standalone CLI tools users can run
- Services with systemd units
- Modules providing public APIs for other code
- New capabilities that solve a user problem

# What is NOT a Feature?

- Internal utility functions (setup.py, create_symlink.py, maintenance.py)
- Connector classes that are just internal plumbing
- Hook handlers that are implementation details
- Anything in utils/ or helpers/ directories
- Generic-named modules without clear user benefit

# Quality Requirements

- NEVER use the filename as the feature name (e.g., "Connector" is not a feature name)
- NEVER use "New tool at <path>" as a description
- If two files provide the same logical feature, list them as ONE feature
- If you can't write a meaningful description, don't include it (confidence < 0.3)

# Output Format

Return ONLY a JSON array. No explanation text.

```json
[
  {{
    "name": "Descriptive Feature Name",
    "description": "One sentence explaining what this does and why it matters",
    "category": "Category Name",
    "files": ["path/to/main.py"],
    "tests": [],
    "confidence": 0.85,
    "introduced_in_commit": "abc12345"
  }}
]
```

If no meaningful features are found, return: `[]`
"""

    def _parse_llm_features(self, llm_output: str, context: str = "") -> list[DetectedFeature]:
        """Parse LLM output to extract features.

        Args:
            llm_output: Raw LLM output that may contain JSON
            context: Optional context string for better error messages

        Returns:
            List of detected features, or empty list if parsing fails
        """
        features = []
        context_prefix = f"[{context}] " if context else ""

        # Try multiple patterns to extract JSON array
        # Pattern 1: JSON array anywhere in the output
        json_match = re.search(r"\[[\s\S]*\]", llm_output)

        # Pattern 2: JSON in markdown code block (```json ... ```)
        if not json_match:
            code_block_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", llm_output)
            if code_block_match:
                json_match = code_block_match

        if not json_match:
            # Log the first 500 chars of output to help debug
            preview = llm_output[:500].replace("\n", "\\n") if llm_output else "(empty)"
            print(f"    {context_prefix}Warning: No JSON array found in LLM output")
            print(f"    {context_prefix}Output preview: {preview}...")
            return []

        json_str = json_match.group(1) if json_match.lastindex else json_match.group()

        try:
            data = json.loads(json_str)
            if not isinstance(data, list):
                print(f"    {context_prefix}Warning: JSON is not a list, got {type(data).__name__}")
                return []

            for item in data:
                if not isinstance(item, dict):
                    continue

                confidence = float(item.get("confidence", 0.5))
                feature = DetectedFeature(
                    name=item.get("name", "Unknown"),
                    description=item.get("description", ""),
                    category=item.get("category", "Utilities"),
                    files=item.get("files", []),
                    tests=item.get("tests", []),
                    confidence=confidence,
                    introduced_in_commit=item.get("introduced_in_commit", ""),
                    date_added=datetime.now(UTC).strftime("%Y-%m-%d"),
                    needs_review=confidence < 0.7,
                )
                features.append(feature)

        except (json.JSONDecodeError, ValueError) as e:
            # Log more context about the parsing error
            print(f"    {context_prefix}Warning: Failed to parse LLM JSON: {e}")
            json_preview = json_str[:300].replace("\n", "\\n") if json_str else "(empty)"
            print(f"    {context_prefix}JSON preview: {json_preview}...")

        return features

    def extract_features_with_llm(self, commits: list[CommitInfo]) -> list[DetectedFeature]:
        """Use LLM to extract features from commits."""
        if not commits:
            return []

        prompt = self._generate_feature_extraction_prompt(commits)

        success, stdout, error = self._run_llm_prompt(prompt, "commit-extraction")
        if success and stdout.strip():
            return self._parse_llm_features(stdout, context="commit-extraction")
        else:
            print(f"    Warning: LLM extraction failed: {error or 'Unknown'}")
            return []

    def _extract_docstring(self, content: str) -> str:
        """Extract the module docstring from Python source code."""
        # Match triple-quoted strings at the start of the file
        patterns = [
            r'^"""(.*?)"""',  # Double quotes
            r"^'''(.*?)'''",  # Single quotes
        ]
        for pattern in patterns:
            match = re.search(pattern, content.strip(), re.DOTALL)
            if match:
                docstring = match.group(1).strip()
                # Get first paragraph (up to double newline or end)
                first_para = docstring.split("\n\n")[0]
                # Clean up and truncate
                first_para = " ".join(first_para.split())  # Normalize whitespace
                if len(first_para) > 200:
                    first_para = first_para[:197] + "..."
                return first_para
        return ""

    def _generate_name_from_path(self, file_path: str) -> str:
        """Generate a human-readable name from a file path."""
        # Get the filename without extension
        stem = Path(file_path).stem

        # Get parent directory for context
        parent = Path(file_path).parent.name

        # Convert snake_case/kebab-case to Title Case
        name = stem.replace("_", " ").replace("-", " ").title()

        # If name is generic (like "Connector"), qualify with parent directory
        generic_names = {"connector", "handler", "processor", "manager", "service", "client"}
        if stem.lower() in generic_names:
            parent_name = parent.replace("_", " ").replace("-", " ").title()
            name = f"{parent_name} {name}"

        return name

    def extract_features_heuristically(self, commits: list[CommitInfo]) -> list[DetectedFeature]:
        """
        Extract features using heuristics (fallback when LLM unavailable).

        Looks for:
        - New files in feature directories with main() function
        - New systemd service files
        - New CLI scripts

        Filters out:
        - Utility scripts (setup.py, symlink helpers, etc.)
        - Files in utils/helpers directories
        """
        features = []
        seen_files = set()

        for commit in commits:
            for file_path in commit.files:
                if file_path in seen_files:
                    continue
                seen_files.add(file_path)

                # Skip non-Python files (for now)
                if not file_path.endswith(".py"):
                    continue

                # Skip test files
                if "test" in file_path.lower():
                    continue

                # Skip utility files
                if self._is_utility_file(file_path):
                    continue

                # Check if in feature directory
                if not self.is_feature_directory(file_path):
                    continue

                # Check if file exists and has main function
                full_path = self.repo_root / file_path
                if not full_path.exists():
                    continue

                # Skip very large files (>1MB) to avoid memory issues
                if full_path.stat().st_size > 1_000_000:
                    continue

                # Read with explicit encoding and handle encoding errors
                try:
                    content = full_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue  # Skip files with encoding issues

                has_main = "def main(" in content or 'if __name__ == "__main__"' in content

                if has_main:
                    # Generate a meaningful name
                    name = self._generate_name_from_path(file_path)

                    # Try to extract description from docstring
                    description = self._extract_docstring(content)
                    if not description:
                        # Fallback to generic description
                        description = f"CLI tool providing {name.lower()} functionality"

                    feature = DetectedFeature(
                        name=name,
                        description=description,
                        category=self.get_category_for_file(file_path),
                        files=[file_path],
                        tests=[],
                        confidence=0.5,  # Lower confidence for heuristic detection
                        introduced_in_commit=commit.sha[:8],
                        date_added=datetime.now(UTC).strftime("%Y-%m-%d"),
                        needs_review=True,
                    )
                    features.append(feature)

        return features

    def get_existing_features(self) -> set[str]:
        """Get set of feature names already in FEATURES.md."""
        if not self.features_md.exists():
            return set()

        content = self.features_md.read_text()
        existing = set()

        # Match feature headers: #### Feature Name **[status]**
        pattern = r"####\s+(.+?)\s+\*\*\["
        for match in re.finditer(pattern, content):
            existing.add(match.group(1).lower())

        return existing

    def get_existing_file_paths(self) -> set[str]:
        """Get set of file paths already documented in FEATURES.md."""
        if not self.features_md.exists():
            return set()

        content = self.features_md.read_text()
        paths = set()

        # Match file paths in backticks with common implementation file extensions
        pattern = r"`([^`]+\.(?:py|ts|js|sh|go))`"
        for match in re.finditer(pattern, content):
            paths.add(match.group(1))

        return paths

    def find_existing_documentation(self, feature: DetectedFeature) -> str | None:
        """
        Find existing documentation for a feature by checking common locations.

        Looks for README.md in the feature's directory or a matching doc file
        in docs/reference/ or docs/.

        Returns the relative path to documentation if found, None otherwise.
        """
        if not feature.files:
            return None

        primary_file = Path(feature.files[0])

        # Check for README.md in the same directory
        readme_path = self.repo_root / primary_file.parent / "README.md"
        if readme_path.exists():
            return str(primary_file.parent / "README.md")

        # Check for documentation in docs/reference/
        feature_slug = feature.name.lower().replace(" ", "-")
        for doc_pattern in [
            f"docs/reference/{feature_slug}.md",
            f"docs/{feature_slug}.md",
            f"docs/reference/{primary_file.stem}.md",
        ]:
            doc_path = self.repo_root / doc_pattern
            if doc_path.exists():
                return doc_pattern

        return None

    def _read_file_content(self, file_path: str, max_lines: int = 500) -> str:
        """
        Read file content for code analysis.

        Args:
            file_path: Relative path to the file
            max_lines: Maximum lines to read (default 500)

        Returns:
            File content truncated to max_lines, or empty string if error
        """
        full_path = self.repo_root / file_path
        if not full_path.exists():
            return ""

        try:
            # Skip very large files
            if full_path.stat().st_size > 500_000:  # 500KB limit
                return ""

            content = full_path.read_text(encoding="utf-8")
            lines = content.split("\n")
            if len(lines) > max_lines:
                lines = lines[:max_lines]
                lines.append(f"\n... [truncated at {max_lines} lines]")
            return "\n".join(lines)
        except (UnicodeDecodeError, OSError):
            return ""

    def _analyze_code_with_llm(self, file_contents: dict[str, str]) -> list[DetectedFeature]:
        """
        Use LLM to analyze actual code content and extract features.

        This provides more thorough analysis than commit-based extraction,
        useful for poorly named commits or large refactors.

        Args:
            file_contents: Dict mapping file paths to their content

        Returns:
            List of detected features
        """
        if not file_contents:
            return []

        # Build a comprehensive prompt with actual code
        code_sections = []
        for file_path, content in file_contents.items():
            if content:
                code_sections.append(f"""
## File: {file_path}

```python
{content}
```
""")

        if not code_sections:
            return []

        code_text = "\n---\n".join(code_sections)

        prompt = f"""You are an expert software architect analyzing a codebase to identify user-facing FEATURES for documentation.

# Code to Analyze

{code_text}

# Your Task

Analyze this code thoroughly to identify substantive features. For EACH feature found, provide:

1. **name**: A clear, descriptive feature name
   - Good: "Slack Message Router", "Weekly Code Analyzer", "GitHub Token Refresher"
   - Bad: "Handler", "Service", "Utils" (too generic)

2. **description**: A meaningful description (2-3 sentences) explaining:
   - What the feature does
   - The problem it solves
   - Key capabilities

3. **category**: One of:
   - "Analysis & Documentation" - code analysis, doc generation, PR review tools
   - "Context Sync" - data synchronization services
   - "Slack Integration" - Slack-related features
   - "Task Tracking" - task management features
   - "Git & GitHub Integration" - git/GitHub tooling
   - "Container Infrastructure" - container, Docker, environment tools
   - "Utilities" - general utilities

4. **files**: Main implementation files (the ones you analyzed)

5. **tests**: Any test files mentioned or inferred

6. **confidence**: 0.0-1.0 based on:
   - 0.9+: Clear user-facing feature with main() or public API
   - 0.7-0.9: Likely feature, well-documented
   - 0.5-0.7: Possibly a feature, needs review
   - <0.5: Probably internal utility

# What IS a Feature?

- CLI tools with main() function or argument parser
- Services that run as systemd units or daemons
- Public APIs/libraries used by other code
- Standalone capabilities that solve user problems

# What is NOT a Feature?

- Internal helper functions
- Base classes or abstract interfaces
- Configuration files
- Test utilities
- Generic connectors without clear user benefit

# Quality Requirements

- Extract meaningful descriptions from docstrings and comments
- Identify the PURPOSE, not just the implementation
- If a file is just internal plumbing, skip it (confidence < 0.3)
- Group related functionality into single features

# Output Format

Return ONLY a JSON array:

```json
[
  {{
    "name": "Feature Name",
    "description": "2-3 sentence description of what it does and why",
    "category": "Category Name",
    "files": ["path/to/main.py"],
    "tests": ["tests/test_feature.py"],
    "confidence": 0.85
  }}
]
```

If no features found, return: `[]`
"""

        success, stdout, error = self._run_llm_prompt(prompt, "code-analysis")
        if success and stdout.strip():
            return self._parse_llm_features(stdout, context="code-analysis")
        else:
            print(f"    Warning: Code analysis failed: {error or 'Unknown'}")
            return []

    def generate_feature_documentation(self, feature: DetectedFeature) -> str | None:
        """
        Generate documentation for a feature using LLM.

        Creates a README.md-style documentation file for the feature.

        Args:
            feature: The feature to document

        Returns:
            Path to generated documentation, or None if generation failed
        """
        if not feature.files:
            return None

        # Read the main implementation file
        primary_file = feature.files[0]
        content = self._read_file_content(primary_file, max_lines=800)
        if not content:
            return None

        prompt = f"""Generate comprehensive documentation for this feature.

# Feature: {feature.name}

**Description**: {feature.description}
**Category**: {feature.category}
**Implementation**: `{primary_file}`

# Source Code

```python
{content}
```

# Generate Documentation

Create a README.md for this feature with these sections:

1. **Overview** - What is this feature and why does it exist?
2. **Usage** - How to use it (CLI commands, API calls, etc.)
3. **Configuration** - Any configuration options
4. **Architecture** - Key components and how they work together
5. **Examples** - Practical usage examples

Write clear, concise documentation suitable for developers.
Output ONLY the markdown content, no explanation.
"""

        success, stdout, _error = self._run_llm_prompt(prompt, "doc-generation")
        if success and stdout.strip():
            # Determine output path
            primary_path = Path(primary_file)
            doc_dir = self.repo_root / primary_path.parent

            # Write the documentation
            doc_path = doc_dir / "README.md"
            if not doc_path.exists():
                doc_path.write_text(stdout.strip())
                return str(primary_path.parent / "README.md")
            else:
                print(f"    Skipping doc generation: README.md already exists at {doc_path}")

        return None

    def _deduplicate_by_files(
        self, features: list[DetectedFeature]
    ) -> tuple[list[DetectedFeature], list[tuple[str, str]]]:
        """
        Deduplicate features that have the same implementation files.

        If multiple features point to the same file, keep only the one with
        the highest confidence. This prevents issues like two "Connector"
        features from being listed.

        Returns: (deduplicated_features, skipped_with_reasons)
        """
        # Group features by their primary implementation file
        by_file: dict[str, list[DetectedFeature]] = {}
        for feature in features:
            if feature.files:
                primary_file = feature.files[0]
                if primary_file not in by_file:
                    by_file[primary_file] = []
                by_file[primary_file].append(feature)

        deduplicated = []
        skipped = []

        for file_path, file_features in by_file.items():
            if len(file_features) == 1:
                deduplicated.append(file_features[0])
            else:
                # Keep the one with highest confidence
                best = max(file_features, key=lambda f: f.confidence)
                deduplicated.append(best)
                for other in file_features:
                    if other != best:
                        skipped.append(
                            (other.name, f"Duplicate of {best.name} (same file: {file_path})")
                        )

        # Add features without files to the result.
        # Note: Features without files won't be in by_file (due to `if feature.files:` check above),
        # so they're only added here. This is intentional - file-based deduplication doesn't apply
        # to features without files.
        for feature in features:
            if not feature.files:
                deduplicated.append(feature)

        return deduplicated, skipped

    def filter_new_features(
        self, detected: list[DetectedFeature], existing: set[str]
    ) -> tuple[list[DetectedFeature], list[tuple[str, str]]]:
        """
        Filter detected features to only new ones.

        Performs:
        1. Deduplication by file path (prevents same file -> multiple features)
        2. Name-based duplicate detection against existing FEATURES.md
        3. File path-based duplicate detection against existing FEATURES.md
        4. Low confidence filtering

        Returns: (new_features, skipped_with_reasons)
        """
        all_skipped = []

        # First, deduplicate within the detected set
        detected, dedup_skipped = self._deduplicate_by_files(detected)
        all_skipped.extend(dedup_skipped)

        # Get existing file paths for path-based deduplication
        existing_paths = self.get_existing_file_paths()

        new_features = []

        for feature in detected:
            name_lower = feature.name.lower()
            # Normalize: remove hyphens, extra spaces
            name_normalized = name_lower.replace("-", " ").replace("_", " ")
            name_words = set(name_normalized.split())

            # Check if file path already documented
            if feature.files:
                already_documented = [f for f in feature.files if f in existing_paths]
                if already_documented:
                    all_skipped.append(
                        (feature.name, f"File already documented: {already_documented[0]}")
                    )
                    continue

            # Check if already exists (exact name match)
            if name_lower in existing or name_normalized in existing:
                all_skipped.append((feature.name, "Already in FEATURES.md"))
                continue

            # Check for similar names (fuzzy match using word overlap)
            is_similar = False
            for existing_name in existing:
                existing_words = set(existing_name.split())
                # If any significant word matches
                common = name_words & existing_words
                if common:
                    # Skip single-letter matches
                    significant_common = [w for w in common if len(w) > 3]
                    if significant_common:
                        all_skipped.append((feature.name, f"Similar to existing: {existing_name}"))
                        is_similar = True
                        break

            if is_similar:
                continue

            # Check for substring match
            similar = [e for e in existing if name_lower in e or e in name_lower]
            if similar:
                all_skipped.append((feature.name, f"Similar to existing: {similar[0]}"))
                continue

            # Skip very low confidence
            if feature.confidence < 0.3:
                all_skipped.append((feature.name, f"Low confidence ({feature.confidence:.0%})"))
                continue

            new_features.append(feature)

        return new_features, all_skipped

    def format_feature_entry(self, feature: DetectedFeature) -> str:
        """Format a feature for FEATURES.md with documentation links."""
        review_flag = " **[needs review]**" if feature.needs_review else ""
        lines = [
            f"#### {feature.name} **[{feature.status}]**{review_flag}",
            f"- **Description**: {feature.description}",
        ]

        # Add documentation link if available
        if feature.doc_path:
            doc_label = "(auto-generated)" if feature.doc_generated else ""
            lines.append(
                f"- **Documentation**: [{feature.doc_path}]({feature.doc_path}) {doc_label}"
            )

        # Add ADR reference if available
        if feature.adr_reference:
            lines.append(f"- **ADR**: [{feature.adr_reference}]({feature.adr_reference})")

        if feature.files:
            lines.append("- **Implementation**:")
            for f in feature.files[:5]:
                lines.append(f"  - `{f}`")

        if feature.tests:
            lines.append(f"- **Tests**: `{feature.tests[0]}`")

        if feature.introduced_in_commit:
            lines.append(f"- **Introduced in**: commit {feature.introduced_in_commit}")

        lines.append("")  # Blank line after entry
        return "\n".join(lines)

    def update_features_md(self, features: list[DetectedFeature], dry_run: bool = False) -> str:
        """
        Update FEATURES.md with new features.

        Args:
            features: Features to add
            dry_run: If True, return what would be added without modifying file

        Returns:
            The new content that was/would be added
        """
        if not features:
            return ""

        # Group features by category
        by_category: dict[str, list[DetectedFeature]] = {}
        for feature in features:
            cat = feature.category or "Utilities"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(feature)

        # Read existing content
        content = self.features_md.read_text() if self.features_md.exists() else ""

        # Find where to insert features (before "## Feature Lifecycle" or at end)
        insert_marker = "## Feature Lifecycle"
        insert_pos = content.find(insert_marker)
        if insert_pos == -1:
            insert_pos = len(content)

        # Build new content to insert
        new_entries = []
        for category, cat_features in sorted(by_category.items()):
            new_entries.append(f"\n### {category} (Auto-detected)\n")
            for feature in cat_features:
                new_entries.append(self.format_feature_entry(feature))

        new_content = "\n".join(new_entries)

        if dry_run:
            return new_content

        # Insert new content
        updated = content[:insert_pos] + new_content + "\n" + content[insert_pos:]

        # Update last updated date
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        updated = re.sub(
            r"\*\*Last Updated\*\*: \d{4}-\d{2}-\d{2}",
            f"**Last Updated**: {today}",
            updated,
        )

        # Write updated content
        self.features_md.write_text(updated)

        return new_content

    def analyze_and_update(
        self,
        days: int = 7,
        dry_run: bool = False,
        generate_docs: bool = True,
        deep_analysis: bool = True,
    ) -> AnalysisResult:
        """
        Main entry point: analyze recent commits and update FEATURES.md.

        This method performs thorough feature analysis including:
        1. Commit-based extraction (original method)
        2. Code-level analysis (reads actual file contents for better extraction)
        3. Documentation discovery (links to existing docs)
        4. Documentation generation (creates docs for undocumented features)

        Args:
            days: Number of days to analyze
            dry_run: If True, don't actually modify files
            generate_docs: If True, generate documentation for features without docs
            deep_analysis: If True, also analyze file contents (not just commits)

        Returns:
            AnalysisResult with details of what was found/added
        """
        result = AnalysisResult(
            analysis_date=datetime.now(UTC).isoformat(),
        )

        # Get commits
        print(f"  Fetching commits from past {days} days...")
        commits = self.get_commits_since(days)
        print(f"    Found {len(commits)} commits")

        if not commits:
            return result

        # Filter to feature-relevant commits
        feature_commits = self.filter_feature_commits(commits)
        print(f"    {len(feature_commits)} commits in feature directories")
        result.commits_analyzed = len(feature_commits)

        if not feature_commits:
            return result

        # Phase 1: Extract features from commits (original method)
        print("  Phase 1: Extracting features from commits...")
        if self.use_llm:
            detected = self.extract_features_with_llm(feature_commits)
            if not detected:
                # Fallback to heuristics
                print("    LLM extraction returned empty, using heuristics...")
                detected = self.extract_features_heuristically(feature_commits)
        else:
            detected = self.extract_features_heuristically(feature_commits)

        print(f"    Detected {len(detected)} potential features from commits")

        # Phase 2: Deep code analysis (reads file contents)
        if deep_analysis and self.use_llm:
            print("  Phase 2: Deep code analysis (reading file contents)...")

            # Collect all Python files from commits for deeper analysis
            all_files = set()
            for commit in feature_commits:
                for f in commit.files:
                    if (
                        f.endswith(".py")
                        and self.is_feature_directory(f)
                        and not self._is_utility_file(f)
                        and "test" not in f.lower()
                    ):
                        all_files.add(f)

            if all_files:
                print(f"    Analyzing {len(all_files)} files...")
                # Read file contents (limited to MAX_DEEP_ANALYSIS_FILES to control LLM costs)
                file_contents = {}
                for file_path in list(all_files)[: self.MAX_DEEP_ANALYSIS_FILES]:
                    content = self._read_file_content(file_path)
                    if content:
                        file_contents[file_path] = content

                # Run deep analysis
                if file_contents:
                    deep_features = self._analyze_code_with_llm(file_contents)
                    if deep_features:
                        print(f"    Deep analysis found {len(deep_features)} additional features")
                        # Merge with commit-based features (avoid duplicates)
                        existing_files = {f.files[0] for f in detected if f.files}
                        for df in deep_features:
                            if df.files and df.files[0] not in existing_files:
                                detected.append(df)
                                existing_files.add(df.files[0])

        print(f"    Total: {len(detected)} potential features")
        result.features_detected = detected

        if not detected:
            return result

        # Filter to new features
        existing = self.get_existing_features()
        new_features, skipped = self.filter_new_features(detected, existing)
        result.features_skipped = skipped

        print(f"    {len(new_features)} new features (skipped {len(skipped)})")

        if not new_features:
            return result

        # Phase 3: Documentation discovery and generation
        print("  Phase 3: Documentation discovery and generation...")
        for feature in new_features:
            # Try to find existing documentation
            doc_path = self.find_existing_documentation(feature)
            if doc_path:
                feature.doc_path = doc_path
                print(f"    Found existing docs for {feature.name}: {doc_path}")
            elif generate_docs and self.use_llm and not dry_run:
                # Generate documentation for undocumented features
                print(f"    Generating docs for {feature.name}...")
                generated_path = self.generate_feature_documentation(feature)
                if generated_path:
                    feature.doc_path = generated_path
                    feature.doc_generated = True
                    result.docs_generated.append(generated_path)
                    print(f"      Generated: {generated_path}")

        # Update FEATURES.md
        print("  Updating FEATURES.md...")
        self.update_features_md(new_features, dry_run=dry_run)
        result.features_added = new_features

        if dry_run:
            print("    [DRY RUN] Would add features to FEATURES.md")
        else:
            print(f"    Added {len(new_features)} features")
            if result.docs_generated:
                print(f"    Generated {len(result.docs_generated)} documentation files")

        return result


class RepoAnalyzer:
    """
    Analyzes an entire repository from scratch to generate a comprehensive feature list.

    Uses a multi-agent approach:
    - Pass 1: Preprocessing agent scans directories and builds a structured inventory
    - Pass 2: Feature extraction agent analyzes each directory for user-facing features
    - Pass 3: Consolidation agent deduplicates, categorizes, and organizes final output

    This approach lets the LLM handle complex decisions (deduplication, classification,
    edge cases) rather than trying to encode all possible heuristics in code.
    """

    # Standard categories for feature organization (used as guidance for LLM)
    CATEGORIES = [
        "Core Architecture",
        "Communication",
        "Context Management",
        "GitHub Integration",
        "Self-Improvement System",
        "Documentation System",
        "Custom Commands",
        "Container Infrastructure",
        "Utilities",
        "Security Features",
        "Configuration",
    ]

    # Directories that contain features - scan recursively for actual feature directories
    # These are root directories that MAY contain nested feature directories
    FEATURE_ROOT_DIRECTORIES = [
        "host-services/",
        "jib-container/",
        "scripts/",
        "bin/",
    ]

    # Additional specific feature directories to scan (these contain features directly)
    SPECIFIC_FEATURE_DIRECTORIES = [
        "jib-container/.claude/commands/",
        "jib-container/.claude/hooks/",
        "jib-container/jib-tasks/",
        "jib-container/jib-tools/",
        "jib-container/scripts/",
    ]

    # Basic patterns to skip (obvious non-features)
    # Note: Most patterns are now handled via .gitignore - these are just fallback/hardcoded patterns
    SKIP_PATTERNS = [
        r"__pycache__",
        r"\.pyc$",
        r"\.git/",
        r"node_modules/",
        r"\.egg-info",
    ]

    def __init__(self, repo_root: Path, use_llm: bool = True):
        """
        Initialize the repo analyzer.

        Args:
            repo_root: Path to the repository root
            use_llm: If True, use LLM for feature extraction
        """
        self.repo_root = repo_root
        self.use_llm = use_llm
        self.features_md = repo_root / "docs" / "FEATURES.md"
        # Cache for gitignore check results to avoid repeated subprocess calls
        self._gitignore_cache: dict[str, bool] = {}

    def _run_llm_prompt(self, prompt: str, context_name: str = "") -> tuple[bool, str, str | None]:
        """
        Run an LLM prompt via jib container.

        Host-side code cannot directly call Claude - it's only available inside
        the container. This method uses jib_exec to invoke the analysis processor.

        Args:
            prompt: The prompt to send to the LLM
            context_name: Optional name for logging/debugging

        Returns:
            Tuple of (success, stdout, error_message)
        """
        return _run_llm_prompt_shared(self.repo_root, prompt, context_name)

    def _run_llm_prompt_to_file(
        self, prompt: str, context_name: str = ""
    ) -> tuple[bool, list | dict | None, str | None]:
        """
        Run an LLM prompt that writes JSON output to a file.

        This avoids JSON parsing issues when the LLM includes explanatory text
        before/after the JSON in its stdout. The LLM writes JSON to a temp file,
        which is then read and parsed.

        Args:
            prompt: The prompt to send to the LLM (should request JSON output)
            context_name: Optional name for logging/debugging

        Returns:
            Tuple of (success, parsed_json_content, error_message)
        """
        return _run_llm_prompt_to_file_shared(self.repo_root, prompt, context_name)

    def _is_git_ignored(self, path: Path | str) -> bool:
        """
        Check if a path is ignored by git using 'git check-ignore'.

        This respects all .gitignore files in the repository hierarchy,
        including .venv, node_modules, build directories, etc.

        Args:
            path: Path to check (relative to repo root or absolute)

        Returns:
            True if the path is ignored by git, False otherwise
        """
        # Convert to string for cache lookup
        if isinstance(path, Path):
            try:
                rel_path = str(path.relative_to(self.repo_root))
            except ValueError:
                rel_path = str(path)
        else:
            rel_path = path

        # Check cache first
        if rel_path in self._gitignore_cache:
            return self._gitignore_cache[rel_path]

        try:
            result = subprocess.run(
                ["git", "check-ignore", "-q", rel_path],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            # Exit code 0 means the path IS ignored
            # Exit code 1 means the path is NOT ignored
            # Exit code 128 means git error (not in a repo, etc.)
            is_ignored = result.returncode == 0
            self._gitignore_cache[rel_path] = is_ignored
            return is_ignored
        except Exception:
            # If git command fails, fall back to not ignoring
            self._gitignore_cache[rel_path] = False
            return False

    def _should_skip(self, path: str) -> bool:
        """Check if a path should be skipped (obvious non-features only)."""
        return any(re.search(pattern, path) for pattern in self.SKIP_PATTERNS)

    def scan_directory_structure(self) -> dict[str, list[Path]]:
        """
        Scan the repository DEEPLY to find ALL potential feature directories.

        This method is now UNBOUNDED - it recursively discovers all directories
        that look like they contain features. A directory is considered a
        "feature directory" if it:
        1. Contains Python files (.py) with main() or __main__
        2. Contains shell scripts (.sh)
        3. Contains a README.md (indicates standalone component)
        4. Is a leaf directory with source files (no further subdirectories with source)

        Returns:
            Dict mapping directory paths to lists of relevant files
        """
        feature_dirs: dict[str, list[Path]] = {}

        def is_feature_directory(dir_path: Path) -> bool:
            """
            Determine if a directory is a feature directory (standalone feature unit).

            A feature directory is one that contains implementation files
            and is the logical unit of a feature. We want to find the RIGHT
            level - not too coarse (missing features) but not too fine
            (every utility module as a feature).
            """
            if not dir_path.is_dir():
                return False

            # Check for source files at THIS level (not recursively)
            has_py = any(dir_path.glob("*.py"))
            has_sh = any(dir_path.glob("*.sh"))
            has_readme = (dir_path / "README.md").exists()
            has_md_files = any(dir_path.glob("*.md"))

            # Check directory name for hints
            dir_name = dir_path.name.lower()
            is_internal = dir_name in ["utils", "helpers", "common", "lib", "internal", "docs"]
            is_likely_feature_dir = dir_name not in [
                "__pycache__",
                ".git",
                "node_modules",
                "tests",
                "test",
            ]

            # It's a feature directory if:
            # 1. Has a README (strongest signal of a feature unit), OR
            # 2. Has source files AND is not an internal/utility directory, OR
            # 3. Has markdown files in .claude directories (commands, hooks, rules)
            if has_readme:
                return True
            if (has_py or has_sh) and not is_internal and is_likely_feature_dir:
                return True
            return bool(has_md_files and ".claude" in str(dir_path))

        def collect_files(dir_path: Path) -> list[Path]:
            """Collect all relevant source files from a directory."""
            files = []
            for pattern in ["*.py", "*.sh", "*.md"]:
                for f in dir_path.rglob(pattern):
                    # Skip files that match hardcoded patterns or are git-ignored
                    if self._should_skip(str(f)):
                        continue
                    # Check if file is git-ignored
                    try:
                        rel_path = str(f.relative_to(self.repo_root))
                        if self._is_git_ignored(rel_path):
                            continue
                    except ValueError:
                        pass  # If we can't get relative path, include the file
                    files.append(f)
            return files

        def scan_recursively(base_path: Path, depth: int = 0, max_depth: int = 10):
            """Recursively scan for feature directories."""
            if depth > max_depth:
                return

            if not base_path.exists() or not base_path.is_dir():
                return

            if self._should_skip(str(base_path)):
                return

            # Check if directory is git-ignored (e.g., .venv, node_modules, etc.)
            try:
                rel_path = str(base_path.relative_to(self.repo_root))
                if self._is_git_ignored(rel_path):
                    return
            except ValueError:
                pass  # If we can't get relative path, continue scanning

            # Check if this is a feature directory
            if is_feature_directory(base_path):
                dir_key = str(base_path.relative_to(self.repo_root))
                files = collect_files(base_path)
                if files:
                    feature_dirs[dir_key] = files

            # Always recurse into subdirectories to find nested features
            for item in base_path.iterdir():
                if item.is_dir() and not self._should_skip(str(item)):
                    scan_recursively(item, depth + 1, max_depth)

        # Scan root directories recursively
        for root_dir in self.FEATURE_ROOT_DIRECTORIES:
            base_path = self.repo_root / root_dir
            scan_recursively(base_path)

        # Also scan specific directories that might be missed
        for specific_dir in self.SPECIFIC_FEATURE_DIRECTORIES:
            base_path = self.repo_root / specific_dir
            scan_recursively(base_path)

        # Check for standalone scripts at repo root
        for pattern in ["*.py", "*.sh"]:
            for script in self.repo_root.glob(pattern):
                if not self._should_skip(str(script)):
                    key = str(script.relative_to(self.repo_root))
                    feature_dirs[key] = [script]

        return feature_dirs

    def _read_file_safe(self, path: Path, max_lines: int = 1000) -> str:
        """
        Safely read file content with generous limits using streaming.

        We want Claude to see as much code as possible to make accurate
        feature assessments, so we've increased limits significantly.

        Uses line-by-line reading to avoid loading entire large files into memory.
        """
        try:
            file_size = path.stat().st_size
            lines = []

            # Stream the file line by line to avoid memory spikes on large files
            with path.open(encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"\n... [truncated at {max_lines} lines]")
                        break
                    lines.append(line.rstrip("\n"))

                    # Early exit if we've read enough bytes (500KB limit)
                    if file_size > 500_000 and i >= max_lines:
                        lines.append(f"\n... [truncated, file too large: {file_size} bytes]")
                        break

            return "\n".join(lines)
        except (UnicodeDecodeError, OSError):
            return ""

    def _build_directory_summary(self, dir_path: str, files: list[Path]) -> str:
        """Build a summary of a directory for LLM analysis."""
        summary_parts = [f"Directory: {dir_path}"]
        summary_parts.append(f"Files: {len(files)}")

        # List files
        file_list = [str(f.relative_to(self.repo_root)) for f in files[:20]]
        summary_parts.append("File list: " + ", ".join(file_list))
        if len(files) > 20:
            summary_parts.append(f"... and {len(files) - 20} more")

        # Check for README
        readme_path = self.repo_root / dir_path / "README.md"
        if readme_path.exists():
            readme_content = self._read_file_safe(readme_path, max_lines=50)
            if readme_content:
                summary_parts.append(f"README excerpt:\n{readme_content[:500]}")

        return "\n".join(summary_parts)

    def _analyze_directory_with_llm(
        self, dir_path: str, files: list[Path]
    ) -> list[DetectedFeature]:
        """
        Use LLM to analyze a directory and extract features.

        This is the feature extraction pass - given a directory, identify
        what user-facing features it contains. We now analyze MORE files
        to give Claude the full picture.
        """
        # Prioritize important files: README first, then main files, then others
        # Read up to 15 files (increased from 5) to give Claude more context
        priority_order = []
        readme_files = []
        main_files = []
        other_files = []

        for f in files:
            name = f.name.lower()
            if name == "readme.md":
                readme_files.append(f)
            elif "main" in name or name.endswith("__init__.py") or f.suffix == ".md":
                main_files.append(f)
            else:
                other_files.append(f)

        # Sort other files by size (smaller first, as they're often more focused)
        other_files = sorted(other_files, key=lambda f: f.stat().st_size)

        # Combine in priority order
        priority_order = readme_files + main_files + other_files

        # Read up to 15 files (unbounded approach - let Claude see more)
        max_files = 15
        file_contents = {}
        for f in priority_order[:max_files]:
            content = self._read_file_safe(f)
            if content:
                rel_path = str(f.relative_to(self.repo_root))
                file_contents[rel_path] = content

        if not file_contents:
            return []

        # Check for README
        readme_content = ""
        readme_path = self.repo_root / dir_path / "README.md"
        if readme_path.exists():
            readme_content = self._read_file_safe(readme_path, max_lines=200)

        # Build code sections
        code_sections = []
        for file_path, content in file_contents.items():
            ext = Path(file_path).suffix
            lang = "python" if ext == ".py" else "bash" if ext == ".sh" else ""
            code_sections.append(f"## File: {file_path}\n\n```{lang}\n{content}\n```")

        code_text = "\n---\n".join(code_sections)

        readme_section = ""
        if readme_content:
            readme_section = f"## README.md\n\n```markdown\n{readme_content}\n```\n"

        prompt = f"""Analyze this code directory to identify ALL user-facing FEATURES.

# Directory: {dir_path}

{readme_section}

# Source Files

{code_text}

# Task

Be THOROUGH - identify ALL features in this directory. Don't be conservative.
For each feature provide:

1. **name**: Clear, descriptive name
2. **description**: 2-3 sentence description explaining what it does and why it's useful
3. **category**: One of: Core Architecture, Communication, Context Management, GitHub Integration, Self-Improvement System, Documentation System, Custom Commands, Container Infrastructure, Utilities, Security Features, Configuration
4. **files**: Main implementation files (include ALL relevant files)
5. **confidence**: 0.0-1.0 (use 0.8+ for clear features, lower only if truly ambiguous)

# What IS a Feature? (BE INCLUSIVE)

- Services/daemons that run continuously
- CLI tools users invoke
- Scripts that automate tasks
- Libraries with public APIs
- Configuration systems
- Integration points (Slack, GitHub, etc.)
- Task processors and handlers
- Standalone capabilities solving user problems
- Claude commands (markdown files that define prompts)
- Hooks that extend functionality

# What is NOT a Feature?

- Pure test files (but test utilities ARE features)
- Generic abstract base classes with no functionality
- Empty __init__.py files

# IMPORTANT

- When in doubt, INCLUDE it as a feature
- Multiple related capabilities in one directory should be listed as ONE feature
- If this directory has a README, use it to understand the feature's purpose

# Output

Your output should be a JSON array:

[
  {{
    "name": "Feature Name",
    "description": "Description",
    "category": "Category",
    "files": ["path/to/file.py"],
    "confidence": 0.85
  }}
]

If truly no features (empty directory, only tests), return: `[]`
"""

        # Use file-based approach to avoid JSON parsing issues when LLM includes
        # explanatory text before/after the JSON array
        success, json_content, error = self._run_llm_prompt_to_file(prompt, f"dir:{dir_path}")

        if success and json_content and isinstance(json_content, list):
            return self._json_to_features(json_content)

        if not success:
            # Fallback: try the original stdout parsing approach
            success_fallback, stdout, error_fallback = self._run_llm_prompt(
                prompt, f"dir:{dir_path}-fallback"
            )

            if success_fallback and stdout.strip():
                return self._parse_llm_output(stdout, context=f"dir:{dir_path}")

            if error:
                print(f"    Warning: LLM analysis failed for {dir_path}: {error}")

        return []

    def _parse_llm_output(self, output: str, context: str = "") -> list[DetectedFeature]:
        """Parse LLM JSON output into DetectedFeature objects.

        Args:
            output: Raw LLM output that may contain JSON
            context: Optional context string for better error messages

        Returns:
            List of detected features, or empty list if parsing fails
        """
        features = []
        context_prefix = f"[{context}] " if context else ""

        # Try multiple patterns to extract JSON array
        # Pattern 1: JSON array anywhere in the output
        json_match = re.search(r"\[[\s\S]*\]", output)

        # Pattern 2: JSON in markdown code block (```json ... ```)
        if not json_match:
            code_block_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", output)
            if code_block_match:
                json_match = code_block_match

        if not json_match:
            # Log the first 500 chars of output to help debug
            preview = output[:500].replace("\n", "\\n") if output else "(empty)"
            print(f"    {context_prefix}Warning: No JSON array found in LLM output")
            print(f"    {context_prefix}Output preview: {preview}...")
            return []

        json_str = json_match.group(1) if json_match.lastindex else json_match.group()

        try:
            data = json.loads(json_str)
            if not isinstance(data, list):
                print(f"    {context_prefix}Warning: JSON is not a list, got {type(data).__name__}")
                return []

            for item in data:
                if not isinstance(item, dict):
                    continue

                confidence = float(item.get("confidence", 0.5))
                feature = DetectedFeature(
                    name=item.get("name", "Unknown"),
                    description=item.get("description", ""),
                    category=item.get("category", "Utilities"),
                    files=item.get("files", []),
                    tests=item.get("tests", []),
                    confidence=confidence,
                    date_added=datetime.now(UTC).strftime("%Y-%m-%d"),
                    needs_review=confidence < 0.7,
                )
                features.append(feature)

        except (json.JSONDecodeError, ValueError) as e:
            # Log more context about the parsing error
            print(f"    {context_prefix}Warning: Failed to parse LLM JSON: {e}")
            json_preview = json_str[:300].replace("\n", "\\n") if json_str else "(empty)"
            print(f"    {context_prefix}JSON preview: {json_preview}...")

        return features

    def _json_to_features(self, json_data: list) -> list[DetectedFeature]:
        """
        Convert a list of JSON dicts to DetectedFeature objects.

        This is used when we get JSON directly from a file (via the file-based
        LLM approach) rather than parsing it from stdout.

        Supports hierarchical features with sub_features.

        Args:
            json_data: List of dicts with feature data

        Returns:
            List of DetectedFeature objects
        """
        features = []
        for item in json_data:
            if not isinstance(item, dict):
                continue

            confidence = float(item.get("confidence", 0.5))
            category = item.get("category", "Utilities")

            # Parse sub_features if present
            sub_features = []
            if "sub_features" in item and isinstance(item["sub_features"], list):
                for sub_item in item["sub_features"]:
                    if not isinstance(sub_item, dict):
                        continue
                    sub_confidence = float(sub_item.get("confidence", 0.5))
                    sub_feature = DetectedFeature(
                        name=sub_item.get("name", "Unknown"),
                        description=sub_item.get("description", ""),
                        category=category,  # Inherit parent category
                        files=sub_item.get("files", []),
                        tests=sub_item.get("tests", []),
                        confidence=sub_confidence,
                        date_added=datetime.now(UTC).strftime("%Y-%m-%d"),
                        needs_review=sub_confidence < 0.7,
                    )
                    sub_features.append(sub_feature)

            feature = DetectedFeature(
                name=item.get("name", "Unknown"),
                description=item.get("description", ""),
                category=category,
                files=item.get("files", []),
                tests=item.get("tests", []),
                confidence=confidence,
                introduced_in_commit=item.get("introduced_in_commit", ""),
                date_added=datetime.now(UTC).strftime("%Y-%m-%d"),
                needs_review=confidence < 0.7,
                sub_features=sub_features,
            )
            features.append(feature)
        return features

    def _consolidate_features_with_llm(
        self, all_features: list[DetectedFeature]
    ) -> list[DetectedFeature]:
        """
        Use LLM to consolidate, deduplicate, and organize features.

        This is the consolidation pass - given all raw features from individual
        directory analysis, produce a clean, deduplicated, well-organized list.
        """
        if not all_features:
            return []

        # Build feature summaries for the LLM
        feature_summaries = []
        for i, f in enumerate(all_features):
            files_str = ", ".join(f.files[:3]) if f.files else "none"
            feature_summaries.append(
                f"{i + 1}. {f.name} ({f.category}, {f.confidence:.0%})\n"
                f"   Files: {files_str}\n"
                f"   Description: {f.description}"
            )

        features_text = "\n\n".join(feature_summaries)

        prompt = f"""You are consolidating a list of detected features for a FEATURES.md document.

# Raw Feature List (from directory-by-directory analysis)

{features_text}

# Task

Consolidate this list into a HIERARCHICAL structure with proper deduplication.

## Key Consolidation Rules

1. **REMOVE SYMLINK DUPLICATES**: Files in `.claude/commands/` are symlinked to `claude-commands/`.
   Same for `.claude/rules/` → `claude-rules/`. Keep ONLY the canonical location (`.claude/` paths).
   Do NOT list the same command/rule twice.

2. **CREATE HIERARCHICAL FEATURES**: Group related sub-components under parent features:
   - "LLM Inefficiency Analysis System" with sub_features: [Tool Discovery Detector, Tool Execution Detector, etc.]
   - "Beads Health Analysis" with sub_features: [Beads Metrics Collection, Claude-Powered Task Analysis, etc.]
   - "Claude Agent Rules System" with sub_features: [Mission Rules, Environment Rules, etc.]

3. **MERGE HOST/CONTAINER PAIRS**: When host-side triggers container-side execution, combine into ONE feature:
   - "PR Review Request Handler" (host: github-watcher.py, container: github-processor.py)
   - NOT two separate "PR Review Request Handler (Host)" and "PR Review Request Handler (Container)"

4. **DON'T over-merge distinct features**: "Slack Notifier" and "Slack Receiver" are different features.

5. **Fix categories and descriptions**: Ensure clarity and consistency.

# Categories to use

- Core Architecture
- Communication
- Context Management
- GitHub Integration
- Self-Improvement System
- Documentation System
- Custom Commands
- Container Infrastructure
- Utilities
- Security Features
- Configuration

# Output Format

Your output should be a JSON array with HIERARCHICAL features:

[
  {{
    "name": "Feature Name",
    "description": "Clear 2-3 sentence description",
    "category": "Category",
    "files": ["host-services/path/file.py", "jib-container/path/file.py"],
    "tests": ["path/to/test.py"],
    "confidence": 0.85,
    "sub_features": [
      {{
        "name": "Sub-Component Name",
        "description": "Brief description of this sub-component",
        "files": ["path/to/sub.py"],
        "confidence": 0.85
      }}
    ]
  }}
]

Notes:
- sub_features is OPTIONAL - only use for features with distinct sub-components
- For simple features, omit sub_features entirely (don't include empty array)
- Each sub_feature inherits the parent's category
- Aim for ~100-130 top-level features after proper consolidation (from {len(all_features)} raw)
"""

        # Use file-based approach to avoid JSON parsing issues when LLM includes
        # explanatory text before/after the JSON array
        success, json_content, error = self._run_llm_prompt_to_file(prompt, "consolidation")

        if not success:
            print(f"    Warning: LLM file-based approach failed: {error}")
            print("    Falling back to stdout parsing...")

            # Fallback: try the original stdout parsing approach
            success_fallback, stdout, error_fallback = self._run_llm_prompt(
                prompt, "consolidation-fallback"
            )

            if not success_fallback:
                print(f"    Warning: Fallback also failed: {error_fallback}")
                print("    Using raw features instead")
                return all_features

            if not stdout.strip():
                print("    Warning: Fallback returned empty output")
                print("    Using raw features instead")
                return all_features

            consolidated = self._parse_llm_output(stdout, context="consolidation-fallback")
            if consolidated:
                return consolidated

            print("    Warning: Consolidation parsing returned empty, using raw features")
            return all_features

        # Successfully got JSON from file
        if json_content and isinstance(json_content, list):
            # Convert JSON dicts to DetectedFeature objects
            consolidated = self._json_to_features(json_content)
            if consolidated:
                return consolidated

        print("    Warning: Consolidation parsing returned empty, using raw features")
        return all_features  # Fall back to unprocessed list

    def _analyze_directory_heuristically(
        self, dir_path: str, files: list[Path]
    ) -> list[DetectedFeature]:
        """Analyze a directory using simple heuristics (fallback when LLM unavailable)."""
        features = []

        for f in files:
            if f.suffix == ".py":
                content = self._read_file_safe(f)
                if "def main(" in content or 'if __name__ == "__main__"' in content:
                    # Extract docstring for description
                    docstring = ""
                    match = re.search(r'^"""(.*?)"""', content.strip(), re.DOTALL)
                    if match:
                        docstring = match.group(1).strip().split("\n\n")[0]
                        docstring = " ".join(docstring.split())[:200]

                    dir_name = Path(dir_path).name
                    name = dir_name.replace("_", " ").replace("-", " ").title()
                    description = docstring or f"Tool providing {name.lower()} functionality"

                    feature = DetectedFeature(
                        name=name,
                        description=description,
                        category="Utilities",
                        files=[str(f.relative_to(self.repo_root))],
                        confidence=0.5,
                        date_added=datetime.now(UTC).strftime("%Y-%m-%d"),
                        needs_review=True,
                    )
                    features.append(feature)
                    break  # One feature per directory in heuristic mode

        return features

    def _find_existing_docs(self, feature: DetectedFeature) -> str | None:
        """Find existing documentation for a feature."""
        if not feature.files:
            return None

        primary_file = Path(feature.files[0])
        parent = self.repo_root / primary_file.parent

        readme = parent / "README.md"
        if readme.exists():
            return str(primary_file.parent / "README.md")

        slug = feature.name.lower().replace(" ", "-")
        for pattern in [f"docs/reference/{slug}.md", f"docs/{slug}.md"]:
            if (self.repo_root / pattern).exists():
                return pattern

        return None

    def generate_features_md(
        self, features: list[DetectedFeature], repo_name: str = "Repository"
    ) -> str:
        """Generate complete FEATURES.md content with hierarchical structure."""
        # Group by category
        by_category: dict[str, list[DetectedFeature]] = {}
        for feature in features:
            cat = feature.category or "Utilities"
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(feature)

        # Sort categories
        sorted_categories = [c for c in self.CATEGORIES if c in by_category]
        for cat in by_category:
            if cat not in sorted_categories:
                sorted_categories.append(cat)

        # Count total features including sub-features
        total_features = sum(1 + len(f.sub_features) for f in features)

        lines = [
            f"# {repo_name} Feature List",
            "",
            "> **Purpose:** This list enables automated codebase and document analyzers to systematically assess each feature for quality, security, and improvement opportunities.",
            ">",
            "> **Generated:** This document was auto-generated by the Feature Analyzer.",
            ">",
            f"> **Total Features:** {len(features)} top-level features ({total_features} including sub-features)",
            "",
            "## Table of Contents",
            "",
        ]

        for cat in sorted_categories:
            anchor = cat.lower().replace(" ", "-").replace("&", "and")
            lines.append(f"- [{cat}](#{anchor})")

        lines.extend(["", "---", ""])

        feature_num = 1
        for cat in sorted_categories:
            cat_features = by_category[cat]
            lines.append(f"## {cat}")
            lines.append("")

            for feature in cat_features:
                review_flag = " ⚠️ *needs review*" if feature.needs_review else ""
                lines.append(f"### {feature_num}. {feature.name}{review_flag}")

                if feature.files:
                    # Show multiple files on separate lines if there are many
                    if len(feature.files) <= 2:
                        files_str = ", ".join(f"`{f}`" for f in feature.files)
                        lines.append(f"**Location:** {files_str}")
                    else:
                        lines.append("**Location:**")
                        for f in feature.files[:5]:
                            lines.append(f"- `{f}`")
                        if len(feature.files) > 5:
                            lines.append(f"- *...and {len(feature.files) - 5} more*")

                lines.append("")
                lines.append(f"{feature.description}")

                if feature.doc_path:
                    lines.append("")
                    lines.append(f"**Documentation:** [{feature.doc_path}]({feature.doc_path})")

                # Render sub-features if present
                if feature.sub_features:
                    lines.append("")
                    lines.append("**Components:**")
                    lines.append("")
                    for sub in feature.sub_features:
                        sub_review = " ⚠️" if sub.needs_review else ""
                        sub_files = f" (`{sub.files[0]}`)" if sub.files else ""
                        lines.append(f"- **{sub.name}**{sub_review}{sub_files}")
                        if sub.description:
                            lines.append(f"  - {sub.description}")

                lines.append("")
                feature_num += 1

        lines.extend(
            [
                "---",
                "",
                "## Maintaining This List",
                "",
                "This feature list is maintained by the Feature Analyzer tool.",
                "",
                "### Update Commands",
                "",
                "```bash",
                "# Regenerate entire list from scratch",
                "feature-analyzer full-repo --repo-root /path/to/repo",
                "",
                "# Weekly incremental updates",
                "feature-analyzer weekly-analyze --days 7",
                "```",
                "",
                f"**Last Updated:** {datetime.now(UTC).strftime('%Y-%m-%d')}",
                "",
            ]
        )

        return "\n".join(lines)

    def _analyze_single_directory(
        self, dir_path: str, files: list[Path]
    ) -> tuple[str, int, list[DetectedFeature]]:
        """
        Analyze a single directory for features.

        This method is designed to be called in parallel via ThreadPoolExecutor.

        Args:
            dir_path: Path to the directory relative to repo root
            files: List of files in the directory

        Returns:
            Tuple of (dir_path, file_count, list of detected features)
        """
        if not files:
            return (dir_path, 0, [])

        file_count = len(files)

        if self.use_llm:
            features = self._analyze_directory_with_llm(dir_path, files)
            if not features:
                features = self._analyze_directory_heuristically(dir_path, files)
        else:
            features = self._analyze_directory_heuristically(dir_path, files)

        # Find existing docs for each feature
        for feature in features:
            doc_path = self._find_existing_docs(feature)
            if doc_path:
                feature.doc_path = doc_path

        return (dir_path, file_count, features)

    def analyze_full_repo(
        self,
        dry_run: bool = False,
        output_path: Path | None = None,
        max_workers: int = 5,
    ) -> FullRepoAnalysisResult:
        """
        Analyze entire repository and generate comprehensive FEATURES.md.

        Uses a multi-agent approach with parallel directory analysis:
        1. Scan directories to build inventory
        2. Analyze directories for features IN PARALLEL (LLM pass 1)
        3. Consolidate and deduplicate all features (LLM pass 2)
        4. Generate final FEATURES.md

        Args:
            dry_run: If True, don't write output file
            output_path: Custom output path (defaults to docs/FEATURES.md)
            max_workers: Maximum number of parallel LLM calls (default 5)
        """
        result = FullRepoAnalysisResult(
            analysis_date=datetime.now(UTC).isoformat(),
        )

        output = output_path or self.features_md

        print("Full Repository Feature Analysis (Multi-Agent)")
        print("=" * 50)
        print(f"Repository: {self.repo_root}")
        print(f"Output: {output}")
        print(f"Parallel workers: {max_workers}")
        print()

        # Phase 1: Scan directory structure
        print("Phase 1: Scanning directory structure...")
        feature_dirs = self.scan_directory_structure()
        result.directories_scanned = len(feature_dirs)
        print(f"  Found {len(feature_dirs)} potential feature directories")

        # Phase 2: Analyze directories IN PARALLEL (LLM pass 1 - extraction)
        print(f"\nPhase 2: Analyzing directories for features (parallel, {max_workers} workers)...")
        all_features: list[DetectedFeature] = []

        # Use thread-safe lock for printing
        print_lock = threading.Lock()

        # Filter out empty directories first
        dirs_to_analyze = [(dp, files) for dp, files in feature_dirs.items() if files]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all directory analysis tasks
            future_to_dir = {
                executor.submit(self._analyze_single_directory, dir_path, files): dir_path
                for dir_path, files in dirs_to_analyze
            }

            # Process results as they complete
            for future in as_completed(future_to_dir):
                dir_path = future_to_dir[future]
                try:
                    analyzed_dir, file_count, features = future.result()
                    result.files_analyzed += file_count

                    with print_lock:
                        print(f"  ✓ {analyzed_dir} ({file_count} files)")
                        for feature in features:
                            all_features.append(feature)
                            print(
                                f"    → Found: {feature.name} ({feature.confidence:.0%} confidence)"
                            )

                except Exception as e:
                    with print_lock:
                        print(f"  ✗ {dir_path}: Error - {e}")

        result.features_detected = all_features
        print(f"\n  Total features detected: {len(all_features)}")

        if not all_features:
            print("\n  No features detected. Skipping consolidation and generation.")
            return result

        # Phase 3: Consolidate features (LLM pass 2 - deduplication/organization)
        print("\nPhase 3: Consolidating and organizing (LLM)...")
        if self.use_llm and len(all_features) > 1:
            consolidated_features = self._consolidate_features_with_llm(all_features)
            print(f"  Consolidated to {len(consolidated_features)} features")
        else:
            consolidated_features = all_features
            print(f"  Using {len(consolidated_features)} features (no consolidation)")

        # Update result with consolidated features (not the raw pre-consolidation list)
        result.features_detected = consolidated_features

        # Re-evaluate needs_review based on post-consolidation confidence
        for feature in consolidated_features:
            feature.needs_review = feature.confidence < 0.7

        # Group by category for result
        for feature in consolidated_features:
            cat = feature.category or "Utilities"
            if cat not in result.features_by_category:
                result.features_by_category[cat] = []
            result.features_by_category[cat].append(feature)

        # Phase 4: Generate FEATURES.md
        print("\nPhase 4: Generating FEATURES.md...")
        repo_name = self.repo_root.name
        content = self.generate_features_md(consolidated_features, repo_name=repo_name)

        if dry_run:
            print("\n[DRY RUN] Would write to:", output)
            print("\nPreview (first 50 lines):")
            preview_lines = content.split("\n")[:50]
            for line in preview_lines:
                print(f"  {line}")
            if len(content.split("\n")) > 50:
                print("  ...")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content)
            result.output_file = str(output)
            print(f"  ✓ Written to: {output}")

        return result


def main():
    """CLI entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Weekly code analyzer for FEATURES.md with thorough code analysis"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM extraction, use heuristics only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't modify files, just show what would be done",
    )
    parser.add_argument(
        "--no-docs",
        action="store_true",
        help="Skip documentation generation for undocumented features",
    )
    parser.add_argument(
        "--no-deep-analysis",
        action="store_true",
        help="Skip deep code analysis (only use commit-based extraction)",
    )

    args = parser.parse_args()

    print("Weekly Code Analyzer - Phase 5 (Enhanced)")
    print(f"Repository: {args.repo_root}")
    print(f"Analyzing past {args.days} days")
    print(f"Deep analysis: {'disabled' if args.no_deep_analysis else 'enabled'}")
    print(f"Doc generation: {'disabled' if args.no_docs else 'enabled'}")
    print()

    analyzer = WeeklyAnalyzer(args.repo_root, use_llm=not args.no_llm)
    result = analyzer.analyze_and_update(
        days=args.days,
        dry_run=args.dry_run,
        generate_docs=not args.no_docs,
        deep_analysis=not args.no_deep_analysis,
    )

    print("\n" + "=" * 50)
    print("Analysis Results:")
    print(f"  Commits analyzed: {result.commits_analyzed}")
    print(f"  Features detected: {len(result.features_detected)}")
    print(f"  Features added: {len(result.features_added)}")
    print(f"  Features skipped: {len(result.features_skipped)}")
    print(f"  Docs generated: {len(result.docs_generated)}")

    if result.features_added:
        print("\nNew features added:")
        for feature in result.features_added:
            review = " (needs review)" if feature.needs_review else ""
            doc_info = f" [docs: {feature.doc_path}]" if feature.doc_path else " [no docs]"
            print(f"  - {feature.name}{review}{doc_info}")
            print(f"    {feature.description}")

    if result.docs_generated:
        print("\nDocumentation generated:")
        for doc_path in result.docs_generated:
            print(f"  - {doc_path}")

    if result.features_skipped:
        print("\nSkipped features:")
        for name, reason in result.features_skipped:
            print(f"  - {name}: {reason}")

    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    if args.dry_run:
        print("\n[DRY RUN] No files were modified.")


if __name__ == "__main__":
    main()
