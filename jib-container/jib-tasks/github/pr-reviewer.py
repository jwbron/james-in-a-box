#!/usr/bin/env python3
"""
PR Reviewer - Generates code reviews for GitHub pull requests

Analyzes PR diffs and metadata to provide comprehensive code reviews
covering code quality, security, performance, and best practices.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# Add shared directory to path for imports
# Path: jib-container/jib-tasks/github/pr-reviewer.py -> repo-root/shared
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
try:
    from beads import PRContextManager
    from jib_logging import get_logger
    from notifications import NotificationContext, get_slack_service
except ImportError as e:
    print("=" * 60, file=sys.stderr)
    print("ERROR: Cannot import shared libraries", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"  Import error: {e}", file=sys.stderr)
    print(
        f"  Expected path: {Path(__file__).parent.parent.parent.parent / 'shared'}", file=sys.stderr
    )
    print("", file=sys.stderr)
    print("This usually means a shared module is missing.", file=sys.stderr)
    print(
        "Check that shared/ directory exists in the repo root.",
        file=sys.stderr,
    )
    sys.exit(1)

logger = get_logger("pr-reviewer")


# PRContextManager is now imported from shared/beads
# It manages persistent PR context in Beads for tracking PR work across sessions


class PRReviewer:
    def __init__(self):
        self.github_dir = Path.home() / "context-sync" / "github"
        self.prs_dir = self.github_dir / "prs"
        self.beads_dir = Path.home() / "beads"

        # Initialize notification service
        self.slack = get_slack_service()

        # Initialize PR context manager for beads integration
        self.pr_context = PRContextManager()

        # Track which PRs have been reviewed
        self.state_file = Path.home() / "sharing" / "tracking" / "pr-reviewer-state.json"
        self.reviewed_prs = self.load_state()

    def load_state(self) -> dict:
        """Load previously reviewed PR IDs"""
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except:
                pass
        return {"reviewed": {}}

    def save_state(self):
        """Save reviewed PR IDs"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open("w") as f:
            json.dump(self.reviewed_prs, f, indent=2)

    def watch(self):
        """Scan for new PRs and review them"""
        if not self.prs_dir.exists():
            print("PRs directory not found - skipping review")
            return

        print("Scanning for new PRs to review...")

        # Get current user to skip self-reviews
        current_user = self.get_current_user()

        # Scan all PR files
        for pr_file in self.prs_dir.glob("*-PR-*.md"):
            try:
                # Extract PR number and repo from filename: repo-PR-123.md
                filename = pr_file.stem
                parts = filename.split("-PR-")
                if len(parts) != 2:
                    continue

                repo_name = parts[0]
                pr_num = int(parts[1])

                # Check if already reviewed
                review_key = f"{repo_name}-{pr_num}"
                if review_key in self.reviewed_prs.get("reviewed", {}):
                    continue

                # Load PR to check author
                pr_context = self.load_pr_metadata(pr_file)

                # Skip PRs authored by current user (don't self-review)
                if current_user and pr_context.get("author", "").lower() == current_user.lower():
                    print(f"  Skipping PR #{pr_num} (your own PR)")
                    continue

                print(f"  Reviewing new PR #{pr_num} in {repo_name}")

                # Generate review
                if self.review_pr(pr_num, repo_name):
                    # Mark as reviewed
                    self.reviewed_prs.setdefault("reviewed", {})[review_key] = {
                        "reviewed_at": datetime.now().isoformat(),
                        "pr_num": pr_num,
                        "repo": repo_name,
                    }
                    self.save_state()

            except Exception as e:
                print(f"  Error processing {pr_file}: {e}")

    def get_current_user(self) -> str:
        """Get current GitHub user from gh CLI"""
        try:
            result = subprocess.run(
                ["gh", "api", "user", "--jq", ".login"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return None

    def review_pr(self, pr_num: int, repo_name: str | None = None) -> bool:
        """Generate a comprehensive review for the specified PR"""
        print(f"Generating review for PR #{pr_num}")

        # Find PR file
        pr_file = None
        diff_file = None

        if repo_name:
            pr_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.md"
            diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"
        else:
            # Search for PR file
            matches = list(self.prs_dir.glob(f"*-PR-{pr_num}.md"))
            if matches:
                pr_file = matches[0]
                repo_name = pr_file.name.split("-PR-")[0]
                diff_file = self.prs_dir / f"{repo_name}-PR-{pr_num}.diff"

        if not pr_file or not pr_file.exists():
            print(f"  ⚠️ PR #{pr_num} not found in synced data")
            return False

        # Load PR metadata
        pr_context = self.load_pr_metadata(pr_file)

        # Load diff
        if not diff_file or not diff_file.exists():
            print(f"  ⚠️ Diff file not found for PR #{pr_num}")
            return False

        with diff_file.open() as f:
            diff_content = f.read()

        # Parse diff into file changes
        file_changes = self.parse_diff(diff_content)

        # Generate review
        review = self.analyze_changes(pr_context, file_changes, diff_content)

        # Create Beads task for review
        beads_id = self.create_beads_task(pr_num, repo_name, pr_context)

        # Create notification
        self.create_review_notification(pr_num, repo_name, pr_context, review, beads_id)

        print(f"  ✅ Review generated for PR #{pr_num}")
        return True

    def load_pr_metadata(self, pr_file: Path) -> dict:
        """Load PR metadata from markdown file"""
        with pr_file.open() as f:
            content = f.read()

        metadata = {
            "title": "",
            "description": "",
            "url": "",
            "branch": "",
            "author": "",
            "files_changed": [],
            "additions": 0,
            "deletions": 0,
        }

        lines = content.split("\n")
        in_description = False

        for _i, line in enumerate(lines):
            if line.startswith("# PR #"):
                metadata["title"] = line.split(": ", 1)[1] if ": " in line else ""
            elif line.startswith("**URL**:"):
                # URL has colons in it, so split after the label
                metadata["url"] = line.replace("**URL**: ", "").strip()
            elif line.startswith("**Branch**:"):
                metadata["branch"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Author**:"):
                metadata["author"] = line.split(":", 1)[1].strip()
            elif line.startswith("**Files Changed**:"):
                # Parse file changes count
                match = re.search(r"(\d+)", line)
                if match:
                    metadata["files_count"] = int(match.group(1))
            elif line.startswith("**Additions**:"):
                match = re.search(r"(\d+)", line)
                if match:
                    metadata["additions"] = int(match.group(1))
            elif line.startswith("**Deletions**:"):
                match = re.search(r"(\d+)", line)
                if match:
                    metadata["deletions"] = int(match.group(1))
            elif line.startswith("## Description"):
                in_description = True
            elif in_description and line.startswith("## "):
                in_description = False
            elif in_description and line.strip():
                metadata["description"] += line + "\n"

        return metadata

    def parse_diff(self, diff_content: str) -> list[dict]:
        """Parse diff content into structured file changes"""
        file_changes = []
        current_file = None

        for line in diff_content.split("\n"):
            if line.startswith("diff --git"):
                # New file
                if current_file:
                    file_changes.append(current_file)

                # Extract file path
                match = re.search(r"b/(.+)$", line)
                file_path = match.group(1) if match else "unknown"

                current_file = {
                    "path": file_path,
                    "additions": 0,
                    "deletions": 0,
                    "chunks": [],
                    "language": self.detect_language(file_path),
                }

            elif current_file:
                if line.startswith("@@"):
                    # New chunk
                    current_file["chunks"].append({"header": line, "lines": []})
                elif line.startswith("+") and not line.startswith("+++"):
                    current_file["additions"] += 1
                    if current_file["chunks"]:
                        current_file["chunks"][-1]["lines"].append(line)
                elif line.startswith("-") and not line.startswith("---"):
                    current_file["deletions"] += 1
                    if current_file["chunks"]:
                        current_file["chunks"][-1]["lines"].append(line)
                elif current_file["chunks"]:
                    current_file["chunks"][-1]["lines"].append(line)

        if current_file:
            file_changes.append(current_file)

        return file_changes

    def detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension"""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rb": "ruby",
            ".php": "php",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".rs": "rust",
            ".sh": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".md": "markdown",
        }

        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "unknown")

    def analyze_changes(
        self, pr_context: dict, file_changes: list[dict], diff_content: str
    ) -> dict:
        """Analyze code changes and generate review"""
        review = {
            "overall_assessment": "",
            "concerns": [],
            "suggestions": [],
            "security_issues": [],
            "performance_issues": [],
            "quality_issues": [],
            "file_reviews": [],
            "files_summary": [],  # Summary of changed files
            "testing_gaps": [],
            "positive_notes": [],
        }

        # Build file summary
        for fc in file_changes:
            review["files_summary"].append(
                {
                    "path": fc["path"],
                    "additions": fc.get("additions", 0),
                    "deletions": fc.get("deletions", 0),
                    "language": fc.get("language", "unknown"),
                }
            )

        # Overall assessment
        total_additions = pr_context.get("additions", 0)
        total_deletions = pr_context.get("deletions", 0)
        net_change = total_additions - total_deletions

        if net_change > 500:
            review["overall_assessment"] = (
                "Large PR with significant code changes. Consider breaking into smaller PRs for easier review."
            )
            review["concerns"].append("PR size is large - may be difficult to review thoroughly")
        elif net_change > 200:
            review["overall_assessment"] = "Medium-sized PR with moderate changes."
        else:
            review["overall_assessment"] = "Small, focused PR - good size for review."
            review["positive_notes"].append("PR is well-scoped and focused")

        # Analyze each file
        for file_change in file_changes:
            file_review = self.analyze_file(file_change, diff_content)
            if file_review["comments"]:
                review["file_reviews"].append(file_review)

            # Collect specific issue types
            for comment in file_review["comments"]:
                if comment["type"] == "security":
                    review["security_issues"].append(
                        {"file": file_change["path"], "concern": comment["text"]}
                    )
                elif comment["type"] == "performance":
                    review["performance_issues"].append(
                        {"file": file_change["path"], "concern": comment["text"]}
                    )
                elif comment["type"] == "quality":
                    review["quality_issues"].append(
                        {
                            "file": file_change["path"],
                            "concern": comment["text"],
                            "severity": comment.get("severity", "low"),
                        }
                    )

        # Check for testing
        has_test_files = any("test" in f["path"].lower() for f in file_changes)
        has_code_changes = any(
            f["language"] in ["python", "javascript", "typescript", "java", "go"]
            for f in file_changes
            if "test" not in f["path"].lower()
        )

        if has_code_changes and not has_test_files:
            review["testing_gaps"].append(
                "No test files found - consider adding tests for new functionality"
            )

        # Overall suggestions
        if not review["security_issues"] and not review["performance_issues"]:
            review["positive_notes"].append("No obvious security or performance concerns detected")

        return review

    def analyze_file(self, file_change: dict, full_diff: str) -> dict:
        """Analyze a single file change"""
        file_review = {
            "path": file_change["path"],
            "language": file_change["language"],
            "comments": [],
        }

        # Get added lines for analysis
        added_lines = []
        for chunk in file_change["chunks"]:
            for line in chunk["lines"]:
                if line.startswith("+") and not line.startswith("+++"):
                    added_lines.append(line[1:])  # Remove + prefix

        added_code = "\n".join(added_lines)

        # Pattern-based analysis
        patterns = self.get_analysis_patterns(file_change["language"])

        for _pattern_name, pattern_config in patterns.items():
            regex = pattern_config["regex"]
            matches = re.finditer(regex, added_code, re.MULTILINE | re.IGNORECASE)

            for match in matches:
                file_review["comments"].append(
                    {
                        "type": pattern_config["type"],
                        "severity": pattern_config["severity"],
                        "text": pattern_config["message"],
                        "context": match.group(0)[:100],
                    }
                )

        return file_review

    def get_analysis_patterns(self, language: str) -> dict:
        """Get code analysis patterns for specific language"""
        # Common patterns across languages
        common_patterns = {
            "console_log": {
                "regex": r"console\.(log|debug|info|warn|error)",
                "type": "quality",
                "severity": "low",
                "message": "Console log statement found - consider removing debug logs before merge",
            },
            "todo_comment": {
                "regex": r"(TODO|FIXME|HACK|XXX):",
                "type": "quality",
                "severity": "low",
                "message": "TODO/FIXME comment found - consider addressing or creating a ticket",
            },
            "hardcoded_url": {
                "regex": r'https?://(?!localhost|127\.0\.0\.1|example\.com)[^\s\'"]+',
                "type": "quality",
                "severity": "medium",
                "message": "Hardcoded URL found - consider using configuration",
            },
        }

        # Python-specific patterns
        python_patterns = {
            "eval_exec": {
                "regex": r"\b(eval|exec)\s*\(",
                "type": "security",
                "severity": "high",
                "message": "Use of eval/exec detected - potential security risk",
            },
            "sql_string_concat": {
                "regex": r"(SELECT|INSERT|UPDATE|DELETE).*\+.*\+",
                "type": "security",
                "severity": "high",
                "message": "Possible SQL injection risk - use parameterized queries",
            },
            "bare_except": {
                "regex": r"except\s*:",
                "type": "quality",
                "severity": "medium",
                "message": "Bare except clause - specify exception types",
            },
            "print_statement": {
                "regex": r"\bprint\s*\(",
                "type": "quality",
                "severity": "low",
                "message": "Print statement found - use logging instead",
            },
        }

        # JavaScript/TypeScript patterns
        js_patterns = {
            "var_keyword": {
                "regex": r"\bvar\s+\w+",
                "type": "quality",
                "severity": "low",
                "message": "Use of var keyword - prefer const or let",
            },
            "double_equals": {
                "regex": r"[^=!]={2}[^=]",
                "type": "quality",
                "severity": "medium",
                "message": "Use of == operator - prefer === for strict equality",
            },
            "dangerouslySetInnerHTML": {
                "regex": r"dangerouslySetInnerHTML",
                "type": "security",
                "severity": "high",
                "message": "dangerouslySetInnerHTML used - ensure HTML is sanitized to prevent XSS",
            },
        }

        if language == "python":
            return {**common_patterns, **python_patterns}
        elif language in ["javascript", "typescript"]:
            return {**common_patterns, **js_patterns}
        else:
            return common_patterns

    def create_beads_task(self, pr_num: int, repo_name: str, pr_context: dict) -> str | None:
        """Create or update Beads task for PR review.

        Uses PRContextManager to maintain persistent PR context across sessions.
        Each PR gets ONE task that tracks its entire lifecycle.
        """
        pr_title = pr_context.get("title", f"PR #{pr_num}")

        # Get or create PR context (reuses existing if found)
        beads_id = self.pr_context.get_or_create_context(repo_name, pr_num, pr_title)

        if beads_id:
            # Update with review information
            notes = f"Review generated\nURL: {pr_context.get('url', 'N/A')}\nAuthor: {pr_context.get('author', 'N/A')}"
            self.pr_context.update_context(beads_id, notes, status="in_progress")
            print(f"  ✓ Beads task: {beads_id}")
            return beads_id
        else:
            print("  ⚠ Could not create/find Beads task")
            return None

    def create_review_notification(
        self, pr_num: int, repo_name: str, pr_context: dict, review: dict, beads_id: str | None
    ):
        """Send notification with review results via notifications service."""
        # Build the review body
        body_parts = []

        # Header info
        body_parts.append(f"**PR**: {pr_context['title']}")
        body_parts.append(f"**Repository**: {repo_name}")
        body_parts.append(f"**URL**: {pr_context.get('url', 'N/A')}")
        body_parts.append(f"**Branch**: {pr_context.get('branch', 'N/A')}")
        body_parts.append(
            f"**Changes**: +{pr_context.get('additions', 0)} -{pr_context.get('deletions', 0)}"
        )
        if beads_id:
            body_parts.append(f"**Beads Task**: {beads_id}")
        body_parts.append("")

        # Overall assessment
        body_parts.append("## Overall Assessment")
        body_parts.append(f"{review['overall_assessment']}")
        body_parts.append("")

        # Files changed summary
        if review.get("files_summary"):
            body_parts.append("## Files Changed")
            for f in review["files_summary"][:10]:  # Limit to first 10 files
                body_parts.append(
                    f"- `{f['path']}` (+{f['additions']} -{f['deletions']}) [{f['language']}]"
                )
            if len(review["files_summary"]) > 10:
                body_parts.append(f"- ... and {len(review['files_summary']) - 10} more files")
            body_parts.append("")

        # Positive notes
        if review["positive_notes"]:
            body_parts.append("### Positive Notes")
            for note in review["positive_notes"]:
                body_parts.append(f"- {note}")
            body_parts.append("")

        # Security issues
        if review["security_issues"]:
            body_parts.append("## Security Concerns")
            for issue in review["security_issues"]:
                body_parts.append(f"**{issue['file']}**: {issue['concern']}")
            body_parts.append("")

        # Performance issues
        if review["performance_issues"]:
            body_parts.append("## Performance Concerns")
            for issue in review["performance_issues"]:
                body_parts.append(f"**{issue['file']}**: {issue['concern']}")
            body_parts.append("")

        # Quality issues (only show medium+ severity)
        quality_issues = [
            q for q in review.get("quality_issues", []) if q.get("severity") in ["medium", "high"]
        ]
        if quality_issues:
            body_parts.append("## Code Quality Notes")
            for issue in quality_issues[:5]:  # Limit to 5 issues
                body_parts.append(f"- **{issue['file']}**: {issue['concern']}")
            if len(quality_issues) > 5:
                body_parts.append(f"- ... and {len(quality_issues) - 5} more quality notes")
            body_parts.append("")

        # Testing gaps
        if review["testing_gaps"]:
            body_parts.append("## Testing Gaps")
            for gap in review["testing_gaps"]:
                body_parts.append(f"- {gap}")
            body_parts.append("")

        # Summary
        total_issues = (
            len(review["security_issues"])
            + len(review["performance_issues"])
            + len(review["testing_gaps"])
            + len(quality_issues)
        )

        body_parts.append("## Summary")
        if total_issues == 0:
            body_parts.append("No major issues found. Code looks good!")
        else:
            body_parts.append(f"Found {total_issues} area(s) that may need attention:")
            if review["security_issues"]:
                body_parts.append(f"- {len(review['security_issues'])} security concern(s)")
            if review["performance_issues"]:
                body_parts.append(f"- {len(review['performance_issues'])} performance concern(s)")
            if quality_issues:
                body_parts.append(f"- {len(quality_issues)} code quality note(s)")
            if review["testing_gaps"]:
                body_parts.append(f"- {len(review['testing_gaps'])} testing gap(s)")

        body = "\n".join(body_parts)

        # Create notification context for threading
        context = NotificationContext(
            task_id=f"pr-review-{repo_name}-{pr_num}",
            source="pr-reviewer",
            repository=repo_name,
            pr_number=pr_num,
        )

        # Send notification via the service
        if review["security_issues"]:
            # Use warning for security issues
            self.slack.notify_warning(
                title=f"PR Review: #{pr_num} (Security Concerns Found)",
                body=body,
                context=context,
            )
        else:
            # Use default notify (INFO type) for clean reviews
            self.slack.notify(
                title=f"PR Review: #{pr_num}",
                body=body,
                context=context,
            )

        print(f"  ✓ Sent PR review notification for #{pr_num}")


def main():
    """Main entry point for PR review"""
    import argparse

    parser = argparse.ArgumentParser(description="Generate code reviews for GitHub PRs")
    parser.add_argument("pr_number", nargs="?", type=int, help="PR number to review")
    parser.add_argument("repo_name", nargs="?", help="Repository name (optional)")
    parser.add_argument(
        "--watch",
        "-w",
        action="store_true",
        help="Scan for new PRs and review them (excludes own PRs)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("PR Reviewer - Starting")
    print("=" * 60)

    try:
        reviewer = PRReviewer()

        if args.watch:
            # Watch mode: scan for new PRs to review
            reviewer.watch()
        elif args.pr_number:
            # Direct PR review
            success = reviewer.review_pr(args.pr_number, args.repo_name)
            if not success:
                print("=" * 60, file=sys.stderr)
                print(f"ERROR: Failed to review PR #{args.pr_number}", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                sys.exit(1)
        else:
            # Default: run in watch mode
            reviewer.watch()

        print("=" * 60)
        print("PR Reviewer - Completed successfully")
        print("=" * 60)
        sys.exit(0)

    except Exception as e:
        print("=" * 60, file=sys.stderr)
        print(f"ERROR: {e}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        import traceback

        traceback.print_exc()
        print("=" * 60, file=sys.stderr)
        print("If this persists, check:", file=sys.stderr)
        print("  1. GitHub authentication: gh auth status", file=sys.stderr)
        print("  2. Context sync directory: ~/context-sync/github/prs/", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
