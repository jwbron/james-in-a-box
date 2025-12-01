#!/usr/bin/env python3
"""
Weekly Code Analyzer - FEATURES.md Auto-Discovery (Phase 5)

This module scans merged code from the past week and identifies new features
to add to FEATURES.md. It uses git log analysis and LLM-based feature extraction.

The analyzer:
1. Collects commits from the past 7 days
2. Analyzes commit diffs to identify new capabilities
3. Extracts feature metadata (name, description, files, tests)
4. Updates FEATURES.md with new entries
5. Creates PR for human review

Usage:
    analyzer = WeeklyAnalyzer(repo_root)
    result = analyzer.analyze_and_update()
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path


# Add shared modules to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
from claude import run_claude


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


@dataclass
class AnalysisResult:
    """Result of weekly code analysis."""

    commits_analyzed: int = 0
    features_detected: list[DetectedFeature] = field(default_factory=list)
    features_added: list[DetectedFeature] = field(default_factory=list)
    features_skipped: list[tuple[str, str]] = field(default_factory=list)  # (name, reason)
    errors: list[str] = field(default_factory=list)
    analysis_date: str = ""


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

        return f"""Analyze these commits to identify new features that should be documented in FEATURES.md.

# Commits to Analyze

{commits_text}

# Instructions

For each new feature identified, extract:
1. **name**: A clear, concise feature name (e.g., "Weekly Code Analyzer")
2. **description**: One sentence describing what it does
3. **category**: One of: "Analysis & Documentation", "Context Sync", "Slack Integration", "Task Tracking", "Git & GitHub Integration", "Container Infrastructure", "Utilities"
4. **files**: List of main implementation files (max 5)
5. **tests**: List of test files if any
6. **confidence**: 0.0-1.0 how confident you are this is a real user-facing feature

# What counts as a feature?
- New CLI tools or commands
- New services (systemd services, daemons)
- New Python modules with public APIs
- New capabilities users can interact with

# What does NOT count as a feature?
- Internal refactoring
- Bug fixes
- Documentation changes
- Test improvements
- Config file changes
- Minor utility functions

# Output Format

Return a JSON array of features. Example:
```json
[
  {{
    "name": "Feature Name",
    "description": "One sentence description",
    "category": "Category Name",
    "files": ["path/to/main.py", "path/to/helper.py"],
    "tests": ["tests/test_feature.py"],
    "confidence": 0.85,
    "introduced_in_commit": "abc12345"
  }}
]
```

If no new features are found, return an empty array: `[]`

Only output the JSON, no other text.
"""

    def _parse_llm_features(self, llm_output: str) -> list[DetectedFeature]:
        """Parse LLM output to extract features."""
        features = []

        # Try to extract JSON from the output
        # Look for JSON array pattern
        json_match = re.search(r"\[[\s\S]*\]", llm_output)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())
            if not isinstance(data, list):
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
            print(f"    Warning: Failed to parse LLM output: {e}")

        return features

    def extract_features_with_llm(self, commits: list[CommitInfo]) -> list[DetectedFeature]:
        """Use LLM to extract features from commits."""
        if not commits:
            return []

        prompt = self._generate_feature_extraction_prompt(commits)

        try:
            result = run_claude(
                prompt=prompt,
                timeout=300,
                cwd=self.repo_root,
                stream=False,
            )

            if result.success and result.stdout.strip():
                return self._parse_llm_features(result.stdout)
            else:
                error_msg = result.error or result.stderr[:200] if result.stderr else "Unknown"
                print(f"    Warning: LLM extraction failed: {error_msg}")
                return []

        except Exception as e:
            print(f"    Warning: LLM extraction error: {e}")
            return []

    def extract_features_heuristically(self, commits: list[CommitInfo]) -> list[DetectedFeature]:
        """
        Extract features using heuristics (fallback when LLM unavailable).

        Looks for:
        - New files in feature directories with main() function
        - New systemd service files
        - New CLI scripts
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
                    # Extract name from file path
                    name = Path(file_path).stem.replace("_", " ").title()
                    if name.endswith(" Py"):
                        name = name[:-3]

                    feature = DetectedFeature(
                        name=name,
                        description=f"New tool at {file_path}",
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

    def filter_new_features(
        self, detected: list[DetectedFeature], existing: set[str]
    ) -> tuple[list[DetectedFeature], list[tuple[str, str]]]:
        """
        Filter detected features to only new ones.

        Returns: (new_features, skipped_with_reasons)
        """
        new_features = []
        skipped = []

        for feature in detected:
            name_lower = feature.name.lower()
            # Normalize: remove hyphens, extra spaces
            name_normalized = name_lower.replace("-", " ").replace("_", " ")
            name_words = set(name_normalized.split())

            # Check if already exists (exact match)
            if name_lower in existing or name_normalized in existing:
                skipped.append((feature.name, "Already in FEATURES.md"))
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
                        skipped.append((feature.name, f"Similar to existing: {existing_name}"))
                        is_similar = True
                        break

            if is_similar:
                continue

            # Check for substring match
            similar = [e for e in existing if name_lower in e or e in name_lower]
            if similar:
                skipped.append((feature.name, f"Similar to existing: {similar[0]}"))
                continue

            # Skip very low confidence
            if feature.confidence < 0.3:
                skipped.append((feature.name, f"Low confidence ({feature.confidence:.0%})"))
                continue

            new_features.append(feature)

        return new_features, skipped

    def format_feature_entry(self, feature: DetectedFeature) -> str:
        """Format a feature for FEATURES.md."""
        review_flag = " **[needs review]**" if feature.needs_review else ""
        lines = [
            f"#### {feature.name} **[{feature.status}]**{review_flag}",
            f"- **Description**: {feature.description}",
        ]

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

    def analyze_and_update(self, days: int = 7, dry_run: bool = False) -> AnalysisResult:
        """
        Main entry point: analyze recent commits and update FEATURES.md.

        Args:
            days: Number of days to analyze
            dry_run: If True, don't actually modify files

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

        # Extract features
        print("  Extracting features...")
        if self.use_llm:
            detected = self.extract_features_with_llm(feature_commits)
            if not detected:
                # Fallback to heuristics
                print("    LLM extraction returned empty, using heuristics...")
                detected = self.extract_features_heuristically(feature_commits)
        else:
            detected = self.extract_features_heuristically(feature_commits)

        print(f"    Detected {len(detected)} potential features")
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

        # Update FEATURES.md
        print("  Updating FEATURES.md...")
        self.update_features_md(new_features, dry_run=dry_run)
        result.features_added = new_features

        if dry_run:
            print("    [DRY RUN] Would add features to FEATURES.md")
        else:
            print(f"    Added {len(new_features)} features")

        return result


def main():
    """CLI entry point for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Weekly code analyzer for FEATURES.md")
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

    args = parser.parse_args()

    print("Weekly Code Analyzer - Phase 5")
    print(f"Repository: {args.repo_root}")
    print(f"Analyzing past {args.days} days")
    print()

    analyzer = WeeklyAnalyzer(args.repo_root, use_llm=not args.no_llm)
    result = analyzer.analyze_and_update(days=args.days, dry_run=args.dry_run)

    print("\n" + "=" * 50)
    print("Analysis Results:")
    print(f"  Commits analyzed: {result.commits_analyzed}")
    print(f"  Features detected: {len(result.features_detected)}")
    print(f"  Features added: {len(result.features_added)}")
    print(f"  Features skipped: {len(result.features_skipped)}")

    if result.features_added:
        print("\nNew features added:")
        for feature in result.features_added:
            review = " (needs review)" if feature.needs_review else ""
            print(f"  - {feature.name}{review}")
            print(f"    {feature.description}")

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
