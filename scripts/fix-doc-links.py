#!/usr/bin/env python3
"""
Documentation Link Fixer

Automatically fixes broken links in documentation files by:
1. Updating links to files that have moved to new locations
2. Removing or commenting out references to files that no longer exist
3. Fixing relative path issues

Usage:
  python3 fix-doc-links.py                    # Preview changes (dry run)
  python3 fix-doc-links.py --apply            # Apply changes
  python3 fix-doc-links.py --apply --verbose  # Apply with detailed output
"""

import argparse
import re
import sys
from pathlib import Path


class DocLinkFixer:
    """Fixes broken links in documentation files."""

    # Known file relocations: old_path -> new_path
    # These are files that have moved and we know where they went
    KNOWN_RELOCATIONS = {
        # ADRs moved to subdirectories
        "docs/adr/ADR-Autonomous-Software-Engineer.md": "docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md",
        "docs/adr/ADR-Context-Sync-Strategy-Custom-vs-MCP.md": "docs/adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md",
        "docs/adr/ADR-Message-Queue-Slack-Integration.md": "docs/adr/not-implemented/ADR-Message-Queue-Slack-Integration.md",
        "docs/adr/ADR-Slack-Integration-Strategy-MCP-vs-Custom.md": "docs/adr/not-implemented/ADR-Slack-Integration-Strategy-MCP-vs-Custom.md",
        "docs/adr/ADR-GCP-Deployment-Terraform.md": "docs/adr/not-implemented/ADR-GCP-Deployment-Terraform.md",
        "docs/adr/ADR-Slack-Bot-GCP-Integration.md": "docs/adr/not-implemented/ADR-Slack-Bot-GCP-Integration.md",
        "docs/adr/ADR-Internet-Tool-Access-Lockdown.md": "docs/adr/not-implemented/ADR-Internet-Tool-Access-Lockdown.md",
        "docs/adr/ADR-Continuous-System-Reinforcement.md": "docs/adr/not-implemented/ADR-Continuous-System-Reinforcement.md",
        "docs/adr/ADR-LLM-Documentation-Index-Strategy.md": "docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md",
        "docs/adr/in-progress/ADR-LLM-Documentation-Index-Strategy.md": "docs/adr/implemented/ADR-LLM-Documentation-Index-Strategy.md",
        # JSON files in generated directory
        "codebase.json": "docs/generated/codebase.json",
        "patterns.json": "docs/generated/patterns.json",
        "dependencies.json": "docs/generated/dependencies.json",
        # Old host-services paths
        "host-services/slack-notifier/README.md": "docs/architecture/host-slack-notifier.md",
    }

    # Links that are intentionally examples/templates and should be ignored
    TEMPLATE_PATTERNS = [
        r"YYYY-MM-DD.*\.md",  # Date template files
        r"task-\d{8}-\d{6}\.md",  # Task ID examples
        r"RESPONSE-\d{8}-\d{6}\.md",  # Response examples
        r"incoming/task-",  # Example incoming paths
        r"responses/RESPONSE-",  # Example response paths
        r"notifications/\d{8}-",  # Example notification paths
    ]

    # Link patterns that should be removed entirely (no longer valid references)
    REMOVE_PATTERNS = [
        # Old file references that no longer apply
        r"`slack-notifier/manage_notifier\.sh`",
        r"`slack-notifier/SLACK-APP-SETUP\.md`",
        r"`slack-notifier/BIDIRECTIONAL-SETUP\.md`",
        r"`HOST-SLACK-NOTIFIER\.md`",
        r"`manage-scheduler\.sh`",
        r"`SCHEDULING\.md`",
    ]

    # Patterns for markdown links
    MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    CODE_REF_PATTERN = re.compile(r"`([a-zA-Z0-9_\-/.]+\.(py|sh|ts|js|json|yaml|yml|md))`")

    def __init__(self, project_root: Path, verbose: bool = False):
        self.project_root = project_root.resolve()
        self.docs_dir = project_root / "docs"
        self.verbose = verbose

        # Build file cache for existence checks
        self._file_cache: set[str] = set()
        self._build_file_cache()

    def _build_file_cache(self):
        """Build cache of all files in the project."""
        skip_dirs = {
            "__pycache__",
            ".git",
            ".pytest_cache",
            "node_modules",
            ".mypy_cache",
            ".venv",
            "venv",
        }
        for path in self.project_root.rglob("*"):
            if path.is_file() and not any(skip in path.parts for skip in skip_dirs):
                rel_path = str(path.relative_to(self.project_root))
                self._file_cache.add(rel_path)

    def file_exists(self, path: str) -> bool:
        """Check if a file exists in the project."""
        path = path.lstrip("./")
        return path in self._file_cache

    def find_similar_file(self, missing_path: str) -> str | None:
        """Try to find a similar file that might be the new location."""
        filename = Path(missing_path).name
        matches = [e for e in self._file_cache if Path(e).name == filename]
        if len(matches) == 1:
            return matches[0]
        return None

    def is_template_path(self, path: str) -> bool:
        """Check if a path is an example/template that should be ignored."""
        return any(re.search(pattern, path) for pattern in self.TEMPLATE_PATTERNS)

    def get_relocation(self, old_path: str, from_doc: Path) -> str | None:
        """Get the new location for a file that has moved."""
        # Check direct mapping
        if old_path in self.KNOWN_RELOCATIONS:
            return self.KNOWN_RELOCATIONS[old_path]

        # Try to resolve relative path and check mapping
        try:
            resolved = (from_doc.parent / old_path).resolve()
            rel_resolved = str(resolved.relative_to(self.project_root))
            if rel_resolved in self.KNOWN_RELOCATIONS:
                return self.KNOWN_RELOCATIONS[rel_resolved]
        except (ValueError, RuntimeError):
            pass

        # Try to find by filename
        return self.find_similar_file(old_path)

    def fix_markdown_link(self, match: re.Match, doc_path: Path) -> str:
        """Fix a markdown link if needed."""
        link_text = match.group(1)
        link_target = match.group(2)

        # Skip external links and anchors
        if link_target.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)

        # Check if target exists
        try:
            resolved = (doc_path.parent / link_target).resolve()
            rel_target = str(resolved.relative_to(self.project_root))
        except ValueError:
            return match.group(0)  # Outside project

        # Handle anchors in links
        anchor = ""
        if "#" in rel_target:
            rel_target, anchor = rel_target.rsplit("#", 1)
            anchor = "#" + anchor

        # Check if it's a directory (valid)
        if (self.project_root / rel_target).is_dir():
            return match.group(0)

        # Check if file exists
        if self.file_exists(rel_target):
            return match.group(0)

        # Skip template paths
        if self.is_template_path(link_target):
            return match.group(0)

        # Try to find new location
        new_location = self.get_relocation(rel_target, doc_path)
        if new_location and self.file_exists(new_location):
            # Calculate new relative path from doc location
            new_abs = self.project_root / new_location
            try:
                new_rel = new_abs.relative_to(doc_path.parent)
                new_target = str(new_rel) + anchor
                if self.verbose:
                    print(f"  Fixed: [{link_text}]({link_target}) -> [{link_text}]({new_target})")
                return f"[{link_text}]({new_target})"
            except ValueError:
                # Need to go up directories
                # Calculate relative path
                doc_parts = doc_path.parent.relative_to(self.project_root).parts
                new_parts = Path(new_location).parts

                # Find common prefix
                common_len = 0
                for i, (d, n) in enumerate(zip(doc_parts, new_parts, strict=False)):
                    if d != n:
                        break
                    common_len = i + 1

                # Build relative path
                up_count = len(doc_parts) - common_len
                new_target = "../" * up_count + "/".join(new_parts[common_len:]) + anchor
                if self.verbose:
                    print(f"  Fixed: [{link_text}]({link_target}) -> [{link_text}]({new_target})")
                return f"[{link_text}]({new_target})"

        return match.group(0)

    def fix_doc(self, doc_path: Path) -> tuple[str, int]:
        """Fix a single documentation file. Returns (new_content, changes_count)."""
        try:
            content = doc_path.read_text()
        except Exception as e:
            print(f"Warning: Could not read {doc_path}: {e}")
            return "", 0

        changes = 0

        # Fix markdown links
        def fix_link(match):
            nonlocal changes
            result = self.fix_markdown_link(match, doc_path)
            if result != match.group(0):
                changes += 1
            return result

        content = self.MD_LINK_PATTERN.sub(fix_link, content)

        return content, changes

    def fix_all_docs(self, apply: bool = False) -> dict:
        """Fix all documentation files."""
        results = {
            "files_checked": 0,
            "files_modified": 0,
            "total_fixes": 0,
            "details": [],
        }

        # Find all markdown files
        md_files = []
        if self.docs_dir.exists():
            md_files.extend(self.docs_dir.rglob("*.md"))

        # Add root README and CLAUDE.md
        for name in ["README.md", "CLAUDE.md"]:
            root_file = self.project_root / name
            if root_file.exists():
                md_files.append(root_file)

        for md_file in sorted(md_files):
            # Skip generated docs
            if "generated" in md_file.parts:
                continue

            results["files_checked"] += 1
            rel_path = str(md_file.relative_to(self.project_root))

            if self.verbose:
                print(f"\nChecking: {rel_path}")

            new_content, changes = self.fix_doc(md_file)

            if changes > 0:
                results["files_modified"] += 1
                results["total_fixes"] += changes
                results["details"].append(
                    {
                        "file": rel_path,
                        "fixes": changes,
                    }
                )

                if apply:
                    md_file.write_text(new_content)
                    print(f"Fixed {changes} link(s) in {rel_path}")
                else:
                    print(f"Would fix {changes} link(s) in {rel_path}")

        return results


def main():
    parser = argparse.ArgumentParser(
        description="Fix broken links in documentation files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Project root (default: parent of scripts directory)",
    )

    parser.add_argument(
        "--apply",
        "-a",
        action="store_true",
        help="Apply fixes (default: dry run)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )

    args = parser.parse_args()

    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}")
        sys.exit(1)

    print(f"{'Fixing' if args.apply else 'Checking'} documentation links in: {project_root}")
    print()

    fixer = DocLinkFixer(project_root, verbose=args.verbose)
    results = fixer.fix_all_docs(apply=args.apply)

    print()
    print("=" * 60)
    print(f"Files checked: {results['files_checked']}")
    print(f"Files {'modified' if args.apply else 'to modify'}: {results['files_modified']}")
    print(f"Total fixes: {results['total_fixes']}")

    if not args.apply and results["total_fixes"] > 0:
        print()
        print("Run with --apply to apply these fixes")


if __name__ == "__main__":
    main()
