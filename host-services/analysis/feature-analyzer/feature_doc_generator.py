#!/usr/bin/env python3
"""
Feature Documentation Generator

Generates detailed feature documentation files from FEATURES.md.

This script:
1. Parses FEATURES.md to extract features by category
2. Generates or updates individual feature docs in docs/features/
3. Updates docs/features/README.md with navigation
4. Can be run manually or by the feature-analyzer CLI

Usage:
    python feature_doc_generator.py [--repo-root PATH] [--dry-run]
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ParsedFeature:
    """A feature parsed from FEATURES.md."""

    number: int
    name: str
    category: str
    description: str
    files: list[str] = field(default_factory=list)
    doc_path: str = ""
    sub_features: list[dict] = field(default_factory=list)


@dataclass
class CategoryInfo:
    """Information about a feature category."""

    name: str
    doc_file: str
    features: list[ParsedFeature] = field(default_factory=list)
    description: str = ""
    key_scripts: list[str] = field(default_factory=list)


# Mapping from FEATURES.md categories to doc files and descriptions
CATEGORY_CONFIG = {
    "Communication": {
        "file": "communication.md",
        "description": "Bidirectional Slack integration for human-agent communication.",
        "key_scripts": ["slack-notifier", "slack-receiver"],
    },
    "Context Management": {
        "file": "context-management.md",
        "description": "External knowledge synchronization and persistent task tracking.",
        "key_scripts": ["context-sync", "beads"],
    },
    "GitHub Integration": {
        "file": "github-integration.md",
        "description": "Automated PR monitoring, code reviews, and CI/CD failure handling.",
        "key_scripts": ["github-watcher", "pr-reviewer"],
    },
    "Self-Improvement System": {
        "file": "self-improvement.md",
        "description": "LLM efficiency analysis, inefficiency detection, and automated optimization.",
        "key_scripts": ["trace-collector", "inefficiency-detector"],
    },
    "Documentation System": {
        "file": "documentation-system.md",
        "description": "Automated documentation generation, sync, and maintenance.",
        "key_scripts": ["feature-analyzer", "doc-generator"],
    },
    "Custom Commands": {
        "file": "container-infrastructure.md",
        "description": "Part of container infrastructure - slash commands for common operations.",
        "key_scripts": [],
    },
    "Container Infrastructure": {
        "file": "container-infrastructure.md",
        "description": "Core jib container management, development environment, and analysis tasks.",
        "key_scripts": ["jib", "docker-setup.py"],
    },
    "Utilities": {
        "file": "utilities.md",
        "description": "Helper tools, maintenance scripts, and supporting services.",
        "key_scripts": ["worktree-watcher", "test discovery"],
    },
    "Security Features": {
        "file": "utilities.md",
        "description": "Part of utilities - security-related tools.",
        "key_scripts": [],
    },
    "Configuration": {
        "file": "utilities.md",
        "description": "Part of utilities - configuration and setup tools.",
        "key_scripts": [],
    },
}


class FeatureDocGenerator:
    """Generates feature documentation from FEATURES.md."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.features_md = repo_root / "docs" / "FEATURES.md"
        self.features_dir = repo_root / "docs" / "features"

    def parse_features_md(self) -> dict[str, CategoryInfo]:
        """Parse FEATURES.md and extract features by category."""
        if not self.features_md.exists():
            raise FileNotFoundError(f"FEATURES.md not found at {self.features_md}")

        content = self.features_md.read_text()
        lines = content.split("\n")

        categories: dict[str, CategoryInfo] = {}
        current_category = None
        current_feature = None
        in_location = False
        in_components = False

        for line in lines:
            # Match category headers (## Category Name)
            category_match = re.match(r"^## (.+)$", line)
            if category_match:
                cat_name = category_match.group(1).strip()
                if cat_name not in ["Table of Contents", "Maintaining This List"]:
                    config = CATEGORY_CONFIG.get(
                        cat_name,
                        {"file": "utilities.md", "description": "", "key_scripts": []},
                    )
                    current_category = CategoryInfo(
                        name=cat_name,
                        doc_file=config["file"],
                        description=config.get("description", ""),
                        key_scripts=config.get("key_scripts", []),
                    )
                    categories[cat_name] = current_category
                    current_feature = None
                    in_location = False
                    in_components = False
                continue

            # Match feature headers (### N. Feature Name)
            feature_match = re.match(r"^### (\d+)\. (.+?)(?:\s+⚠️.*)?$", line)
            if feature_match and current_category:
                num = int(feature_match.group(1))
                name = feature_match.group(2).strip()
                current_feature = ParsedFeature(
                    number=num,
                    name=name,
                    category=current_category.name,
                    description="",
                )
                current_category.features.append(current_feature)
                in_location = False
                in_components = False
                continue

            # Match location lines
            if current_feature:
                if line.startswith("**Location:**"):
                    in_location = True
                    in_components = False
                    # Check for inline location
                    loc_match = re.search(r"\*\*Location:\*\*\s*(.+)$", line)
                    if loc_match:
                        loc = loc_match.group(1).strip()
                        # Extract paths from backticks
                        paths = re.findall(r"`([^`]+)`", loc)
                        current_feature.files.extend(paths)
                        in_location = False
                    continue

                if line.startswith("**Components:**"):
                    in_location = False
                    in_components = True
                    continue

                if line.startswith("**Documentation:**"):
                    in_location = False
                    in_components = False
                    doc_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", line)
                    if doc_match:
                        current_feature.doc_path = doc_match.group(2)
                    continue

                if line.startswith(("**", "---")):
                    in_location = False
                    in_components = False

                # Collect location lines (bullet points with paths)
                if in_location and line.startswith("- `"):
                    path_match = re.search(r"`([^`]+)`", line)
                    if path_match:
                        current_feature.files.append(path_match.group(1))
                    continue

                # Collect component info
                if in_components and line.startswith("- **"):
                    comp_match = re.match(r"- \*\*(.+?)\*\*(?:\s+⚠️)?\s*(?:\(`([^`]+)`\))?", line)
                    if comp_match:
                        current_feature.sub_features.append(
                            {
                                "name": comp_match.group(1),
                                "file": comp_match.group(2) if comp_match.group(2) else "",
                            }
                        )
                    continue

                # Collect description (non-empty lines that aren't special)
                if (
                    line.strip()
                    and not line.startswith("**")
                    and not line.startswith("- ")
                    and not line.startswith("#")
                    and not in_location
                    and not in_components
                ):
                    if current_feature.description:
                        current_feature.description += " " + line.strip()
                    else:
                        current_feature.description = line.strip()

        return categories

    def generate_readme(self, categories: dict[str, CategoryInfo], dry_run: bool = False) -> str:
        """Generate docs/features/README.md."""
        lines = [
            "# Feature Documentation",
            "",
            "This directory contains detailed documentation for each major feature category in james-in-a-box.",
            "",
            "## Quick Reference",
            "",
            "| Category | Description | Key Scripts |",
            "|----------|-------------|-------------|",
        ]

        # Deduplicate categories by doc file
        seen_files = set()
        for cat_name, cat_info in categories.items():
            if cat_info.doc_file in seen_files:
                continue
            seen_files.add(cat_info.doc_file)

            scripts = (
                ", ".join(f"`{s}`" for s in cat_info.key_scripts) if cat_info.key_scripts else "-"
            )
            lines.append(
                f"| [{cat_name}]({cat_info.doc_file}) | {cat_info.description[:50]}{'...' if len(cat_info.description) > 50 else ''} | {scripts} |"
            )

        lines.extend(
            [
                "",
                "## How to Use These Docs",
                "",
                "1. **Finding a feature**: Use the category docs above or search [FEATURES.md](../FEATURES.md) for the comprehensive list",
                "2. **Understanding a feature**: Each category doc includes:",
                "   - Overview and purpose",
                "   - Helper scripts and commands",
                "   - Configuration options",
                "   - Links to detailed documentation",
                "3. **Extending a feature**: Check the linked source files and ADRs for implementation details",
                "",
                "## Auto-Generation",
                "",
                "These documents are maintained by the Feature Analyzer:",
                "",
                "```bash",
                "# Regenerate all feature docs",
                "feature-analyzer generate-feature-docs",
                "",
                "# Update after changes",
                "feature-analyzer full-repo --repo-root ~/khan/james-in-a-box",
                "```",
                "",
                "## Related Documentation",
                "",
                "- [FEATURES.md](../FEATURES.md) - Complete feature-to-source mapping",
                "- [Architecture Overview](../architecture/README.md) - System design",
                "- [ADR Index](../adr/README.md) - Design decisions",
                "",
                "---",
                "",
                f"*Last updated: {datetime.now(UTC).strftime('%Y-%m-%d')}*",
                "",
            ]
        )

        content = "\n".join(lines)

        if not dry_run:
            readme_path = self.features_dir / "README.md"
            readme_path.write_text(content)
            print(f"  Updated: {readme_path.relative_to(self.repo_root)}")

        return content

    def generate_feature_summary(self, categories: dict[str, CategoryInfo]) -> dict[str, str]:
        """Generate a summary of features by category for updating existing docs."""
        summaries = {}

        for _cat_name, cat_info in categories.items():
            if not cat_info.features:
                continue

            lines = ["\n## Features from FEATURES.md\n"]
            for feature in cat_info.features:
                lines.append(f"### {feature.name}")
                lines.append("")
                if feature.description:
                    lines.append(feature.description)
                    lines.append("")
                if feature.files:
                    lines.append("**Location:**")
                    for f in feature.files[:5]:
                        lines.append(f"- `{f}`")
                    if len(feature.files) > 5:
                        lines.append(f"- *...and {len(feature.files) - 5} more*")
                    lines.append("")
                if feature.sub_features:
                    lines.append("**Components:**")
                    for sub in feature.sub_features:
                        if sub.get("file"):
                            lines.append(f"- **{sub['name']}** (`{sub['file']}`)")
                        else:
                            lines.append(f"- **{sub['name']}**")
                    lines.append("")

            summaries[cat_info.doc_file] = "\n".join(lines)

        return summaries

    def run(self, dry_run: bool = False) -> dict:
        """Run the feature doc generation."""
        print("Feature Documentation Generator")
        print("=" * 50)
        print(f"Repository: {self.repo_root}")
        print(f"Dry run: {dry_run}")
        print()

        # Ensure features directory exists
        if not dry_run:
            self.features_dir.mkdir(parents=True, exist_ok=True)

        # Parse FEATURES.md
        print("Parsing FEATURES.md...")
        categories = self.parse_features_md()
        print(f"  Found {len(categories)} categories")

        total_features = sum(len(c.features) for c in categories.values())
        print(f"  Found {total_features} features")
        print()

        # Generate README
        print("Generating feature docs...")
        self.generate_readme(categories, dry_run=dry_run)

        # Generate feature summaries (for reference)
        summaries = self.generate_feature_summary(categories)
        print(f"  Generated summaries for {len(summaries)} doc files")

        # List existing feature docs
        existing_docs = list(self.features_dir.glob("*.md")) if self.features_dir.exists() else []
        print(f"\nExisting feature docs: {len(existing_docs)}")
        for doc in existing_docs:
            print(f"  - {doc.name}")

        return {
            "categories": len(categories),
            "features": total_features,
            "summaries": len(summaries),
            "existing_docs": len(existing_docs),
        }


def main():
    parser = argparse.ArgumentParser(description="Generate feature documentation from FEATURES.md")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root directory (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying files",
    )

    args = parser.parse_args()

    try:
        generator = FeatureDocGenerator(args.repo_root)
        result = generator.run(dry_run=args.dry_run)

        print()
        print("=" * 50)
        print("Summary:")
        print(f"  Categories parsed: {result['categories']}")
        print(f"  Features found: {result['features']}")
        print(f"  Doc files updated: {result['summaries']}")

        if args.dry_run:
            print("\n[DRY RUN] No files were modified.")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
