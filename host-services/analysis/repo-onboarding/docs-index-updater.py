#!/usr/bin/env python3
"""
Documentation Index Updater for Jib Repository Onboarding

Updates or creates a docs/index.md navigation file with references to:
- Generated codebase indexes
- Feature documentation
- External (Confluence) documentation

Follows the llms.txt standard for LLM-friendly documentation navigation.

Per ADR: Jib Repository Onboarding Strategy (Phase 4: Index Updates)
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class IndexConfig:
    """Configuration for index generation."""

    repo_root: Path
    generated_dir: Path
    features_md: Path | None
    dry_run: bool


class DocsIndexUpdater:
    """Updates the documentation index with generated content references."""

    # Markers for jib-managed sections
    SECTION_START = "<!-- jib-onboarding-start -->"
    SECTION_END = "<!-- jib-onboarding-end -->"

    def __init__(self, config: IndexConfig):
        self.config = config
        self.repo_name = config.repo_root.name
        self.index_path = config.repo_root / "docs" / "index.md"

    def run(self) -> bool:
        """Main update method. Returns True on success."""
        print(f"Updating documentation index for: {self.repo_name}")

        # Gather information about generated content
        generated_content = self._gather_generated_content()

        # Build the section content
        section_content = self._build_section(generated_content)

        if self.config.dry_run:
            print("\n=== DRY RUN - Section content: ===")
            print(section_content)
            return True

        # Update or create the index file
        if self.index_path.exists():
            return self._update_existing_index(section_content)
        else:
            return self._create_new_index(section_content)

    def _gather_generated_content(self) -> dict:
        """Gather information about all generated content."""
        content = {
            "indexes": [],
            "features": None,
            "feature_docs": [],
            "external_docs": [],
        }

        # Check for generated indexes
        if self.config.generated_dir.exists():
            for json_file in ["codebase.json", "patterns.json", "dependencies.json"]:
                json_path = self.config.generated_dir / json_file
                if json_path.exists():
                    content["indexes"].append(json_file)

            # Check for external docs
            external_docs_path = self.config.generated_dir / "external-docs.json"
            if external_docs_path.exists():
                try:
                    with open(external_docs_path) as f:
                        external_data = json.load(f)
                    content["external_docs"] = external_data.get("discovered_docs", [])[:10]
                except (json.JSONDecodeError, KeyError):
                    pass

        # Check for FEATURES.md
        if self.config.features_md and self.config.features_md.exists():
            content["features"] = str(
                self.config.features_md.relative_to(self.config.repo_root)
            )

        # Check for feature docs directory
        features_dir = self.config.repo_root / "docs" / "features"
        if features_dir.exists():
            for md_file in sorted(features_dir.glob("*.md")):
                if md_file.name != "README.md":
                    content["feature_docs"].append(md_file.name)

        return content

    def _build_section(self, content: dict) -> str:
        """Build the jib-managed section content."""
        lines = [
            self.SECTION_START,
            "",
            "## Generated Documentation",
            "",
            "*This section is automatically managed by jib onboarding.*",
            f"*Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}*",
            "",
        ]

        # Machine-readable indexes section
        if content["indexes"]:
            lines.extend(
                [
                    "### Codebase Indexes",
                    "",
                    "Machine-readable indexes for LLM navigation (local-only, not tracked in git):",
                    "",
                ]
            )
            for index_file in content["indexes"]:
                desc = self._get_index_description(index_file)
                lines.append(f"- [`{index_file}`](generated/{index_file}) - {desc}")
            lines.append("")

        # Features section
        if content["features"]:
            lines.extend(
                [
                    "### Feature Documentation",
                    "",
                    f"- [FEATURES.md]({content['features']}) - Complete feature-to-source mapping",
                ]
            )

            if content["feature_docs"]:
                lines.append("")
                lines.append("Feature category documentation:")
                lines.append("")
                for doc_file in content["feature_docs"][:10]:
                    name = doc_file.replace(".md", "").replace("-", " ").title()
                    lines.append(f"- [{name}](features/{doc_file})")

            lines.append("")

        # External docs section
        if content["external_docs"]:
            lines.extend(
                [
                    "### Org-Specific Documentation",
                    "",
                    "*Auto-discovered from Confluence sync. These documents are managed externally.*",
                    "",
                    "| Document | Description |",
                    "|----------|-------------|",
                ]
            )

            for doc in content["external_docs"]:
                title = doc.get("title", "Unknown")
                relevance = doc.get("relevance", "Related documentation")
                # Create link to confluence sync directory
                doc_path = doc.get("path", "")
                link = f"../../../context-sync/confluence/{doc_path}"
                lines.append(f"| [{title}]({link}) | {relevance} |")

            lines.append("")

        lines.append(self.SECTION_END)

        return "\n".join(lines)

    def _get_index_description(self, filename: str) -> str:
        """Get description for an index file."""
        descriptions = {
            "codebase.json": "Project structure and components",
            "patterns.json": "Detected code patterns and conventions",
            "dependencies.json": "Internal and external dependency graph",
        }
        return descriptions.get(filename, "Index file")

    def _update_existing_index(self, section_content: str) -> bool:
        """Update an existing index.md file."""
        try:
            existing_content = self.index_path.read_text()
        except Exception as e:
            print(f"  Error reading {self.index_path}: {e}")
            return False

        # Check if there's an existing jib section
        start_match = re.search(re.escape(self.SECTION_START), existing_content)
        end_match = re.search(re.escape(self.SECTION_END), existing_content)

        if start_match and end_match:
            # Replace existing section
            new_content = (
                existing_content[: start_match.start()]
                + section_content
                + existing_content[end_match.end() :]
            )
            print("  Updating existing jib section in index.md")
        else:
            # Append section at the end
            new_content = existing_content.rstrip() + "\n\n" + section_content + "\n"
            print("  Appending jib section to index.md")

        try:
            self.index_path.write_text(new_content)
            print(f"  Updated: {self.index_path}")
            return True
        except Exception as e:
            print(f"  Error writing {self.index_path}: {e}")
            return False

    def _create_new_index(self, section_content: str) -> bool:
        """Create a new index.md file."""
        header = f"""# {self.repo_name} Documentation

Welcome to the {self.repo_name} documentation.

"""

        content = header + section_content + "\n"

        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self.index_path.write_text(content)
            print(f"  Created: {self.index_path}")
            return True
        except Exception as e:
            print(f"  Error creating {self.index_path}: {e}")
            return False


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Update documentation index with generated content references",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --repo-root ~/khan/webapp --generated-dir ~/khan/webapp/docs/generated
  %(prog)s --repo-root . --features-md ./docs/FEATURES.md
  %(prog)s --repo-root ~/khan/webapp --dry-run
        """,
    )

    parser.add_argument(
        "--repo-root",
        "-r",
        type=Path,
        required=True,
        help="Root directory of the repository",
    )

    parser.add_argument(
        "--generated-dir",
        "-g",
        type=Path,
        default=None,
        help="Path to generated indexes directory (default: <repo-root>/docs/generated)",
    )

    parser.add_argument(
        "--features-md",
        "-f",
        type=Path,
        default=None,
        help="Path to FEATURES.md file (optional)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    if not repo_root.exists():
        print(f"Error: Repository root does not exist: {repo_root}")
        sys.exit(1)

    generated_dir = args.generated_dir or (repo_root / "docs" / "generated")
    features_md = args.features_md.resolve() if args.features_md else None

    config = IndexConfig(
        repo_root=repo_root,
        generated_dir=generated_dir.resolve(),
        features_md=features_md,
        dry_run=args.dry_run,
    )

    updater = DocsIndexUpdater(config)
    success = updater.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
