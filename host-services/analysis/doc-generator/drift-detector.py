#!/usr/bin/env python3
"""
Documentation Drift Detector

Compares documentation against current code to find discrepancies.
Identifies docs that reference:
- Files that no longer exist
- Functions/classes that have been renamed or removed
- Outdated configuration values
- Stale path references

Per ADR: LLM Documentation Index Strategy (Phase 4)

Usage:
  # Check all docs for drift
  python3 drift-detector.py

  # Check specific doc file
  python3 drift-detector.py --doc docs/auth.md

  # Output as JSON for automation
  python3 drift-detector.py --json

  # Generate fix suggestions
  python3 drift-detector.py --suggest-fixes
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class DriftIssue:
    """A documentation drift issue."""

    doc_path: str
    line_number: int
    issue_type: str
    description: str
    referenced: str
    suggestion: str = ""


@dataclass
class DriftReport:
    """Full drift detection report."""

    generated: str
    project: str
    docs_checked: int
    issues_found: int
    issues: list[DriftIssue] = field(default_factory=list)


class DriftDetector:
    """Detects documentation that has drifted from current code."""

    # Patterns to find references in documentation
    PATTERNS = {
        # Markdown code spans and blocks
        "code_file": re.compile(r"`([a-zA-Z0-9_\-/.]+\.(py|sh|ts|js|json|yaml|yml|md))`"),
        # File:line references
        "file_line": re.compile(r"`?([a-zA-Z0-9_\-/.]+\.(py|sh|ts|js)):(\d+)`?"),
        # Markdown links
        "md_link": re.compile(r"\[([^\]]+)\]\(([^)]+)\)"),
        # Class/function names (PascalCase or snake_case followed by parens or described)
        "identifier": re.compile(r"`([A-Z][a-zA-Z0-9]+|[a-z_][a-z0-9_]+)`"),
        # Path references
        "path_ref": re.compile(r"(?:in |at |see |from )`([a-zA-Z0-9_\-/.]+/[a-zA-Z0-9_\-/.]+)`"),
    }

    # Directories to skip
    SKIP_DIRS = {
        "__pycache__",
        ".git",
        ".pytest_cache",
        "node_modules",
        ".mypy_cache",
        ".venv",
        "venv",
    }

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.docs_dir = project_root / "docs"
        self.generated_dir = project_root / "docs" / "generated"

        # Cache of existing files for quick lookup
        self._file_cache: set[str] = set()
        self._build_file_cache()

        # Load indexes for component validation
        self._components: dict[str, dict] = {}
        self._load_components()

    def _build_file_cache(self):
        """Build cache of all files in the project."""
        for path in self.project_root.rglob("*"):
            if path.is_file() and not any(skip in path.parts for skip in self.SKIP_DIRS):
                rel_path = str(path.relative_to(self.project_root))
                self._file_cache.add(rel_path)

    def _load_components(self):
        """Load components from codebase.json if available."""
        codebase_path = self.generated_dir / "codebase.json"
        if codebase_path.exists():
            try:
                data = json.loads(codebase_path.read_text())
                for component in data.get("components", []):
                    name = component.get("name")
                    if name:
                        self._components[name] = component
            except json.JSONDecodeError:
                pass

    def file_exists(self, path: str) -> bool:
        """Check if a file exists in the project."""
        # Normalize path
        path = path.lstrip("./")
        return path in self._file_cache

    def find_similar_file(self, missing_path: str) -> str | None:
        """Try to find a similar file that might be the new location."""
        filename = Path(missing_path).name
        matches = []

        for existing in self._file_cache:
            if Path(existing).name == filename:
                matches.append(existing)

        if len(matches) == 1:
            return matches[0]
        return None

    def check_doc(self, doc_path: Path) -> list[DriftIssue]:
        """Check a single documentation file for drift."""
        issues = []

        try:
            content = doc_path.read_text()
        except Exception as e:
            return [
                DriftIssue(
                    doc_path=str(doc_path.relative_to(self.project_root)),
                    line_number=0,
                    issue_type="read_error",
                    description=f"Could not read file: {e}",
                    referenced="",
                )
            ]

        rel_doc_path = str(doc_path.relative_to(self.project_root))
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Check file references
            for match in self.PATTERNS["code_file"].finditer(line):
                file_ref = match.group(1)
                if not self.file_exists(file_ref):
                    similar = self.find_similar_file(file_ref)
                    suggestion = f"File may have moved to: {similar}" if similar else ""
                    issues.append(
                        DriftIssue(
                            doc_path=rel_doc_path,
                            line_number=line_num,
                            issue_type="missing_file",
                            description="Referenced file does not exist",
                            referenced=file_ref,
                            suggestion=suggestion,
                        )
                    )

            # Check file:line references
            for match in self.PATTERNS["file_line"].finditer(line):
                file_ref = match.group(1)
                line_ref = int(match.group(3))
                if not self.file_exists(file_ref):
                    similar = self.find_similar_file(file_ref)
                    suggestion = f"File may have moved to: {similar}" if similar else ""
                    issues.append(
                        DriftIssue(
                            doc_path=rel_doc_path,
                            line_number=line_num,
                            issue_type="missing_file",
                            description="Referenced file:line does not exist",
                            referenced=f"{file_ref}:{line_ref}",
                            suggestion=suggestion,
                        )
                    )
                else:
                    # File exists, check if line is still valid
                    full_path = self.project_root / file_ref
                    try:
                        file_lines = full_path.read_text().split("\n")
                        if line_ref > len(file_lines):
                            issues.append(
                                DriftIssue(
                                    doc_path=rel_doc_path,
                                    line_number=line_num,
                                    issue_type="stale_line_ref",
                                    description=f"Line {line_ref} exceeds file length ({len(file_lines)} lines)",
                                    referenced=f"{file_ref}:{line_ref}",
                                    suggestion=f"Update line reference (file now has {len(file_lines)} lines)",
                                )
                            )
                    except Exception:
                        pass

            # Check markdown links
            for match in self.PATTERNS["md_link"].finditer(line):
                match.group(1)
                link_target = match.group(2)

                # Skip external links
                if link_target.startswith(("http://", "https://", "#", "mailto:")):
                    continue

                # Resolve relative links from doc location
                if link_target.startswith("../"):
                    resolved = (doc_path.parent / link_target).resolve()
                    try:
                        link_target = str(resolved.relative_to(self.project_root))
                    except ValueError:
                        continue  # Link points outside project
                else:
                    link_target = link_target.lstrip("./")

                if not self.file_exists(link_target):
                    similar = self.find_similar_file(link_target)
                    suggestion = f"Link may need updating to: {similar}" if similar else ""
                    issues.append(
                        DriftIssue(
                            doc_path=rel_doc_path,
                            line_number=line_num,
                            issue_type="broken_link",
                            description="Link target does not exist",
                            referenced=link_target,
                            suggestion=suggestion,
                        )
                    )

            # Check path references
            for match in self.PATTERNS["path_ref"].finditer(line):
                path_ref = match.group(1)
                # Only report if it looks like a project path (not URLs)
                if (
                    "/" in path_ref
                    and not self.file_exists(path_ref)
                    and not path_ref.startswith(("http", "www", "//"))
                ):
                    similar = self.find_similar_file(path_ref)
                    suggestion = f"Path may have changed to: {similar}" if similar else ""
                    issues.append(
                        DriftIssue(
                            doc_path=rel_doc_path,
                            line_number=line_num,
                            issue_type="stale_path",
                            description="Path reference may be outdated",
                            referenced=path_ref,
                            suggestion=suggestion,
                        )
                    )

        return issues

    def check_all_docs(self) -> DriftReport:
        """Check all documentation files for drift."""
        issues = []
        docs_checked = 0

        if not self.docs_dir.exists():
            return DriftReport(
                generated=datetime.now(UTC).isoformat(),
                project=self.project_root.name,
                docs_checked=0,
                issues_found=0,
                issues=[],
            )

        # Check all markdown files in docs/
        for md_file in self.docs_dir.rglob("*.md"):
            # Skip generated docs (they're auto-updated)
            if "generated" in md_file.parts:
                continue

            docs_checked += 1
            file_issues = self.check_doc(md_file)
            issues.extend(file_issues)

        # Also check README at root
        root_readme = self.project_root / "README.md"
        if root_readme.exists():
            docs_checked += 1
            issues.extend(self.check_doc(root_readme))

        # Check CLAUDE.md if present
        claude_md = self.project_root / "CLAUDE.md"
        if claude_md.exists():
            docs_checked += 1
            issues.extend(self.check_doc(claude_md))

        return DriftReport(
            generated=datetime.now(UTC).isoformat(),
            project=self.project_root.name,
            docs_checked=docs_checked,
            issues_found=len(issues),
            issues=issues,
        )

    def format_report(self, report: DriftReport, suggest_fixes: bool = False) -> str:
        """Format drift report as human-readable text."""
        lines = []
        lines.append(f"Documentation Drift Report - {report.generated[:10]}")
        lines.append("=" * 60)
        lines.append(f"Project: {report.project}")
        lines.append(f"Documents checked: {report.docs_checked}")
        lines.append(f"Issues found: {report.issues_found}")
        lines.append("")

        if not report.issues:
            lines.append("No drift issues detected.")
            return "\n".join(lines)

        # Group by document
        by_doc: dict[str, list[DriftIssue]] = {}
        for issue in report.issues:
            if issue.doc_path not in by_doc:
                by_doc[issue.doc_path] = []
            by_doc[issue.doc_path].append(issue)

        for doc_path, issues in sorted(by_doc.items()):
            lines.append(f"\n{doc_path}")
            lines.append("-" * len(doc_path))

            for issue in sorted(issues, key=lambda i: i.line_number):
                lines.append(f"  Line {issue.line_number}: [{issue.issue_type}]")
                lines.append(f"    {issue.description}")
                lines.append(f"    Referenced: {issue.referenced}")
                if suggest_fixes and issue.suggestion:
                    lines.append(f"    Suggestion: {issue.suggestion}")

        return "\n".join(lines)

    def format_json(self, report: DriftReport) -> str:
        """Format drift report as JSON."""
        data = {
            "generated": report.generated,
            "project": report.project,
            "docs_checked": report.docs_checked,
            "issues_found": report.issues_found,
            "issues": [
                {
                    "doc_path": i.doc_path,
                    "line_number": i.line_number,
                    "issue_type": i.issue_type,
                    "description": i.description,
                    "referenced": i.referenced,
                    "suggestion": i.suggestion,
                }
                for i in report.issues
            ],
        }
        return json.dumps(data, indent=2)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Detect documentation drift from current code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Check all docs
  %(prog)s --doc docs/auth.md       # Check specific doc
  %(prog)s --json                   # Output as JSON
  %(prog)s --suggest-fixes          # Include fix suggestions
        """,
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent.parent,  # james-in-a-box root
        help="Project root (default: james-in-a-box)",
    )

    parser.add_argument(
        "--doc",
        "-d",
        type=Path,
        help="Check specific documentation file",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    parser.add_argument(
        "--suggest-fixes",
        "-s",
        action="store_true",
        help="Include fix suggestions in output",
    )

    args = parser.parse_args()

    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)

    detector = DriftDetector(project_root)

    # Check specific doc or all docs
    if args.doc:
        doc_path = args.doc.resolve()
        if not doc_path.exists():
            print(f"Error: Document does not exist: {doc_path}", file=sys.stderr)
            sys.exit(1)
        issues = detector.check_doc(doc_path)
        report = DriftReport(
            generated=datetime.now(UTC).isoformat(),
            project=project_root.name,
            docs_checked=1,
            issues_found=len(issues),
            issues=issues,
        )
    else:
        report = detector.check_all_docs()

    # Output
    if args.json:
        print(detector.format_json(report))
    else:
        print(detector.format_report(report, args.suggest_fixes))

    # Exit with error code if issues found
    sys.exit(1 if report.issues_found > 0 else 0)


if __name__ == "__main__":
    main()
