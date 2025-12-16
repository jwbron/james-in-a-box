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
        "title": "Communication Features",
        "description": "Bidirectional Slack integration for human-agent communication.",
        "overview": [
            "JIB provides seamless two-way communication with humans via Slack:",
            "- **Outbound**: Agent sends notifications, status updates, and questions",
            "- **Inbound**: Humans send tasks, commands, and feedback via DMs",
        ],
        "key_scripts": ["slack-notifier", "slack-receiver"],
        "related_docs": [
            "[Slack Integration Architecture](../architecture/slack-integration.md)",
            "[Host Slack Notifier Details](../architecture/host-slack-notifier.md)",
            "[Slack Quickstart](../setup/slack-quickstart.md)",
            "[Slack App Setup](../setup/slack-app-setup.md)",
        ],
    },
    "Context Management": {
        "file": "context-management.md",
        "title": "Context Management Features",
        "description": "External knowledge synchronization and persistent task tracking.",
        "overview": [
            "JIB maintains context through multiple systems:",
            "- **External Sync**: Confluence docs and JIRA tickets synced locally",
            "- **Task Tracking**: Beads system for persistent memory across restarts",
            "- **PR Context**: Manages PR lifecycle state in Beads",
        ],
        "key_scripts": ["context-sync", "beads"],
        "related_docs": [
            "[Context Sync ADR](../adr/implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md)",
            "[Beads Reference](../reference/beads.md)",
        ],
    },
    "GitHub Integration": {
        "file": "github-integration.md",
        "title": "GitHub Integration Features",
        "description": "Automated PR monitoring, code reviews, and CI/CD failure handling.",
        "overview": [
            "JIB monitors GitHub repositories for events and responds autonomously:",
            "- **PR Monitoring**: Detects check failures, comments, merge conflicts",
            "- **Auto-Review**: Reviews PRs from other developers",
            "- **Comment Response**: Responds to comments on your PRs",
            "- **CI/CD Fixes**: Automatically fixes failing tests and builds",
        ],
        "key_scripts": ["github-watcher", "pr-reviewer"],
        "related_docs": [
            "[GitHub App Setup](../setup/github-app-setup.md)",
            "[PR Context Manager](workflow-context.md)",
        ],
    },
    "Self-Improvement System": {
        "file": "self-improvement.md",
        "title": "Self-Improvement Features",
        "description": "LLM efficiency analysis, inefficiency detection, and automated optimization.",
        "overview": [
            "JIB continuously improves through automated analysis:",
            "- **Trace Collection**: Captures conversation traces for analysis",
            "- **Inefficiency Detection**: Identifies wasteful patterns",
            "- **Optimization**: Suggests and implements improvements",
        ],
        "key_scripts": ["trace-collector", "inefficiency-detector"],
        "related_docs": [
            "[LLM Inefficiency ADR](../adr/implemented/ADR-LLM-Inefficiency-Reporting.md)",
        ],
    },
    "Documentation System": {
        "file": "documentation-system.md",
        "title": "Documentation System Features",
        "description": "Automated documentation generation, sync, and maintenance.",
        "overview": [
            "JIB maintains documentation automatically:",
            "- **Feature Analysis**: Tracks features and their source locations",
            "- **Doc Generation**: Creates and updates documentation",
            "- **Drift Detection**: Identifies stale or inconsistent docs",
        ],
        "key_scripts": ["feature-analyzer", "doc-generator"],
        "related_docs": [
            "[Documentation Index Strategy](../index.md)",
        ],
    },
    "Custom Commands": {
        "file": "container-infrastructure.md",
        "title": "Container Infrastructure Features",
        "description": "Part of container infrastructure - slash commands for common operations.",
        "overview": [],
        "key_scripts": [],
        "merge_into": "Container Infrastructure",
    },
    "Container Infrastructure": {
        "file": "container-infrastructure.md",
        "title": "Container Infrastructure Features",
        "description": "Core jib container management, development environment, and analysis tasks.",
        "overview": [
            "The jib container provides a sandboxed development environment:",
            "- **Container Management**: Build, run, exec operations",
            "- **Custom Commands**: Slash commands for common operations",
            "- **Analysis Tasks**: Automated codebase analysis",
        ],
        "key_scripts": ["jib", "docker-setup.py"],
        "related_docs": [
            "[Environment Reference](../reference/environment.md)",
            "[Mission Guide](../reference/mission.md)",
        ],
    },
    "Utilities": {
        "file": "utilities.md",
        "title": "Utility Features",
        "description": "Helper tools, maintenance scripts, and supporting services.",
        "overview": [
            "Supporting tools and utilities:",
            "- **Worktree Management**: Git worktree watcher for isolation",
            "- **Test Discovery**: Finds test frameworks in codebases",
            "- **Maintenance**: Various helper scripts",
        ],
        "key_scripts": ["worktree-watcher", "test discovery"],
        "related_docs": [],
    },
    "Security Features": {
        "file": "utilities.md",
        "title": "Utility Features",
        "description": "Part of utilities - security-related tools.",
        "overview": [],
        "key_scripts": [],
        "merge_into": "Utilities",
    },
    "Configuration": {
        "file": "utilities.md",
        "title": "Utility Features",
        "description": "Part of utilities - configuration and setup tools.",
        "overview": [],
        "key_scripts": [],
        "merge_into": "Utilities",
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
                if in_location:
                    if line.startswith("- `"):
                        path_match = re.search(r"`([^`]+)`", line)
                        if path_match:
                            current_feature.files.append(path_match.group(1))
                        continue
                    elif line.strip() and not line.startswith("**") and not line.startswith("#"):
                        # Non-empty line that's not a bullet - it's a description
                        in_location = False
                        # Fall through to description collection below
                    elif not line.strip():
                        # Empty line - might be end of location section
                        continue

                # Collect component info
                if in_components:
                    if line.startswith("- **"):
                        comp_match = re.match(
                            r"- \*\*(.+?)\*\*(?:\s+⚠️)?\s*(?:\(`([^`]+)`\))?", line
                        )
                        if comp_match:
                            current_feature.sub_features.append(
                                {
                                    "name": comp_match.group(1),
                                    "file": comp_match.group(2) if comp_match.group(2) else "",
                                }
                            )
                        continue
                    elif line.strip().startswith("- "):
                        # Sub-component description line (indented bullet)
                        continue
                    elif line.strip() and not line.startswith("**") and not line.startswith("#"):
                        # Non-empty line that's not a component - it's a description
                        in_components = False
                        # Fall through to description collection below
                    elif not line.strip():
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

    def generate_category_doc(
        self, doc_file: str, all_categories: dict[str, CategoryInfo], dry_run: bool = False
    ) -> str:
        """Generate a full category documentation file."""
        # Find the primary category for this doc file
        primary_config = None
        for _cat_name, config in CATEGORY_CONFIG.items():
            if config["file"] == doc_file and not config.get("merge_into"):
                primary_config = config
                break

        if not primary_config:
            return ""

        # Collect all features for this doc file
        all_features: list[ParsedFeature] = []
        for _cat_name, cat_info in all_categories.items():
            if cat_info.doc_file == doc_file:
                all_features.extend(cat_info.features)

        if not all_features:
            return ""

        # Build the document
        lines = [
            f"# {primary_config['title']}",
            "",
            primary_config["description"],
            "",
        ]

        # Overview section
        if primary_config.get("overview"):
            lines.append("## Overview")
            lines.append("")
            for line in primary_config["overview"]:
                lines.append(line)
            lines.append("")

        # Features section
        lines.append("## Features")
        lines.append("")

        for feature in all_features:
            lines.append(f"### {feature.name}")
            lines.append("")

            # Purpose (from description)
            if feature.description:
                lines.append(f"**Purpose**: {feature.description}")
                lines.append("")

            # Location
            if feature.files:
                if len(feature.files) == 1:
                    lines.append(f"**Location**: `{feature.files[0]}`")
                else:
                    lines.append("**Location**:")
                    for f in feature.files[:5]:
                        lines.append(f"- `{f}`")
                    if len(feature.files) > 5:
                        lines.append(f"- *...and {len(feature.files) - 5} more*")
                lines.append("")

            # Sub-features / Components
            if feature.sub_features:
                lines.append("**Components**:")
                for sub in feature.sub_features:
                    if sub.get("file"):
                        lines.append(f"- **{sub['name']}** (`{sub['file']}`)")
                    else:
                        lines.append(f"- **{sub['name']}**")
                lines.append("")

        # Related Documentation section
        if primary_config.get("related_docs"):
            lines.append("## Related Documentation")
            lines.append("")
            for doc in primary_config["related_docs"]:
                lines.append(f"- {doc}")
            lines.append("")

        # Source Files table
        lines.append("## Source Files")
        lines.append("")
        lines.append("| Component | Path |")
        lines.append("|-----------|------|")
        for feature in all_features:
            if feature.files:
                # Use the first file as the primary path
                primary_file = feature.files[0]
                lines.append(f"| {feature.name} | `{primary_file}` |")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        lines.append("*Auto-generated by Feature Analyzer*")
        lines.append("")

        content = "\n".join(lines)

        if not dry_run:
            doc_path = self.features_dir / doc_file
            doc_path.write_text(content)
            print(f"  Generated: {doc_path.relative_to(self.repo_root)}")

        return content

    def generate_all_category_docs(
        self, categories: dict[str, CategoryInfo], dry_run: bool = False
    ) -> int:
        """Generate all category documentation files."""
        # Get unique doc files (excluding merge_into categories)
        doc_files = set()
        for config in CATEGORY_CONFIG.values():
            if not config.get("merge_into"):
                doc_files.add(config["file"])

        generated = 0
        for doc_file in sorted(doc_files):
            content = self.generate_category_doc(doc_file, categories, dry_run=dry_run)
            if content:
                generated += 1

        return generated

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

        # Generate all category documentation files
        print("\nGenerating category documentation...")
        generated_docs = self.generate_all_category_docs(categories, dry_run=dry_run)
        print(f"  Generated {generated_docs} category docs")

        # List all feature docs
        existing_docs = list(self.features_dir.glob("*.md")) if self.features_dir.exists() else []
        print(f"\nTotal feature docs: {len(existing_docs)}")
        for doc in sorted(existing_docs, key=lambda x: x.name):
            print(f"  - {doc.name}")

        return {
            "categories": len(categories),
            "features": total_features,
            "generated_docs": generated_docs,
            "total_docs": len(existing_docs),
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
        print(f"  Category docs generated: {result['generated_docs']}")

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
