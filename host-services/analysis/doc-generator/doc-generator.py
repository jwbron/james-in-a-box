#!/usr/bin/env python3
"""
LLM Documentation Generator - 4-Agent Pipeline

Generates documentation from codebase analysis using a multi-agent pipeline:
1. Context Agent: Analyzes code structure and patterns from indexes
2. Draft Agent: Generates initial documentation
3. Review Agent: Validates accuracy and completeness
4. Output Agent: Formats and saves documentation

Per ADR: LLM Documentation Index Strategy

Usage:
  # Generate status quo docs for a component
  python3 doc-generator.py --type status-quo --topic auth

  # Generate pattern docs
  python3 doc-generator.py --type pattern --topic notification

  # List all detected patterns for documentation
  python3 doc-generator.py --list-topics

  # Generate docs for all detected patterns
  python3 doc-generator.py --all

  # Preview without saving
  python3 doc-generator.py --all --dry-run
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class DocContext:
    """Context gathered by the Context Agent."""

    topic: str
    patterns: list[dict] = field(default_factory=list)
    code_examples: list[str] = field(default_factory=list)
    existing_docs: list[str] = field(default_factory=list)
    components: list[dict] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)


@dataclass
class DraftDoc:
    """Documentation draft from the Draft Agent."""

    title: str
    content: str
    doc_type: str
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReviewResult:
    """Review feedback from the Review Agent."""

    approved: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class DocumentationGenerator:
    """4-agent documentation generation pipeline.

    Generates documentation from codebase indexes (patterns.json, codebase.json).
    For best practice research, use the separate adr-researcher tool.
    """

    # Doc types we can generate
    DOC_TYPES = {
        "status-quo": "Descriptive documentation of current implementation",
        "pattern": "Pattern documentation extracted from code",
        "best-practice": "Best practice documentation (alias for pattern)",
    }

    # Topics mapped to keywords for pattern detection
    TOPIC_KEYWORDS = {
        "auth": ["auth", "jwt", "token", "session", "login", "permission"],
        "notification": ["notify", "notification", "alert", "slack", "message"],
        "sync": ["sync", "synchronize", "fetch", "update", "pull"],
        "config": ["config", "settings", "env", "environment", "option"],
        "connector": ["connector", "client", "adapter", "api", "integration"],
        "testing": ["test", "mock", "fixture", "assert", "expect"],
        "security": ["security", "encrypt", "hash", "sanitize", "validate"],
    }

    def __init__(self, project_root: Path, output_dir: Path | None = None):
        self.project_root = project_root.resolve()
        self.output_dir = output_dir or (project_root / "docs" / "generated" / "authored")
        self.generated_dir = project_root / "docs" / "generated"

        # Load existing indexes if available
        self.codebase_index = self._load_json("codebase.json")
        self.patterns_index = self._load_json("patterns.json")
        self.deps_index = self._load_json("dependencies.json")

    def _load_json(self, filename: str) -> dict:
        """Load a JSON index file if it exists."""
        path = self.generated_dir / filename
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                print(f"Warning: Could not parse {filename}")
        return {}

    def list_available_topics(self) -> list[dict]:
        """List topics available for documentation based on detected patterns."""
        topics = []

        # From patterns.json
        if self.patterns_index.get("patterns"):
            for pattern_name, pattern_data in self.patterns_index["patterns"].items():
                topics.append(
                    {
                        "name": pattern_name,
                        "source": "detected_pattern",
                        "description": pattern_data.get("description", ""),
                        "examples_count": len(pattern_data.get("examples", [])),
                    }
                )

        # From known topic keywords
        for topic_name in self.TOPIC_KEYWORDS:
            if not any(t["name"] == topic_name for t in topics):
                topics.append(
                    {
                        "name": topic_name,
                        "source": "keyword_mapping",
                        "description": f"Documentation for {topic_name} patterns",
                        "examples_count": 0,
                    }
                )

        return sorted(topics, key=lambda t: t["name"])

    # =========================================================================
    # Agent 1: Context Agent - Analyzes code and gathers context
    # =========================================================================
    def gather_context(self, topic: str) -> DocContext:
        """Context Agent: Gather all relevant information about a topic."""
        context = DocContext(topic=topic)

        # Get patterns from index
        if self.patterns_index.get("patterns"):
            for pattern_name, pattern_data in self.patterns_index["patterns"].items():
                if self._topic_matches(topic, pattern_name):
                    context.patterns.append({"name": pattern_name, **pattern_data})
                    context.code_examples.extend(pattern_data.get("examples", []))
                    context.conventions.extend(pattern_data.get("conventions", []))

        # Get components from codebase index
        if self.codebase_index.get("components"):
            keywords = self.TOPIC_KEYWORDS.get(topic.lower(), [topic.lower()])
            for component in self.codebase_index["components"]:
                name = component.get("name", "").lower()
                desc = component.get("description", "").lower()
                if any(kw in name or kw in desc for kw in keywords):
                    context.components.append(component)

        # Find existing documentation
        docs_dir = self.project_root / "docs"
        if docs_dir.exists():
            for md_file in docs_dir.rglob("*.md"):
                try:
                    content = md_file.read_text()
                    if topic.lower() in content.lower():
                        rel_path = str(md_file.relative_to(self.project_root))
                        context.existing_docs.append(rel_path)
                except Exception:
                    pass

        return context

    def _topic_matches(self, topic: str, pattern_name: str) -> bool:
        """Check if a topic matches a pattern name."""
        topic_lower = topic.lower()
        pattern_lower = pattern_name.lower()

        if topic_lower == pattern_lower:
            return True

        keywords = self.TOPIC_KEYWORDS.get(topic_lower, [topic_lower])
        return any(kw in pattern_lower for kw in keywords)

    # =========================================================================
    # Agent 2: Draft Agent - Generates initial documentation
    # =========================================================================
    def generate_draft(self, context: DocContext, doc_type: str) -> DraftDoc:
        """Draft Agent: Generate initial documentation from context."""
        if doc_type == "status-quo":
            return self._draft_status_quo(context)
        elif doc_type in ("pattern", "best-practice"):
            return self._draft_pattern(context)
        else:
            raise ValueError(f"Unknown doc type: {doc_type}")

    def _draft_status_quo(self, context: DocContext) -> DraftDoc:
        """Generate status quo documentation describing current implementation."""
        title = f"{context.topic.title()} Patterns (Status Quo)"
        sections = []
        sections.append(f"# {title}")
        sections.append("")
        sections.append(
            f"> Auto-generated by jib on {datetime.now(UTC).strftime('%Y-%m-%d')}. "
            "Review before relying on."
        )
        sections.append("")

        sections.append("## Current Implementation")
        sections.append("")

        if context.patterns:
            for pattern in context.patterns:
                sections.append(f"### {pattern['name'].replace('_', ' ').title()}")
                sections.append("")
                if pattern.get("description"):
                    sections.append(pattern["description"])
                    sections.append("")

        if context.components:
            sections.append("### Key Components")
            sections.append("")
            sections.append("| Component | Type | Location | Description |")
            sections.append("|-----------|------|----------|-------------|")
            for comp in context.components[:10]:
                name = comp.get("name", "Unknown")
                comp_type = comp.get("type", "unknown")
                location = comp.get("file", "")
                line = comp.get("line", "")
                desc = comp.get("description", "")[:50]
                if line:
                    location = f"`{location}:{line}`"
                else:
                    location = f"`{location}`"
                sections.append(f"| {name} | {comp_type} | {location} | {desc} |")
            sections.append("")

        if context.code_examples:
            sections.append("### Code Examples")
            sections.append("")
            sections.append("Implementation examples found in:")
            sections.append("")
            for example in context.code_examples[:10]:
                sections.append(f"- `{example}`")
            sections.append("")

        if context.conventions:
            sections.append("## Conventions")
            sections.append("")
            for convention in context.conventions:
                sections.append(f"- {convention}")
            sections.append("")

        if context.existing_docs:
            sections.append("## Related Documentation")
            sections.append("")
            for doc in context.existing_docs[:5]:
                sections.append(f"- [{doc}]({doc})")
            sections.append("")

        content = "\n".join(sections)
        return DraftDoc(
            title=title,
            content=content,
            doc_type="status-quo",
            sources=[f"patterns.json:{context.topic}"],
        )

    def _draft_pattern(self, context: DocContext) -> DraftDoc:
        """Generate pattern documentation for detected code patterns."""
        title = f"{context.topic.title()} Pattern"
        sections = []
        sections.append(f"# {title}")
        sections.append("")
        sections.append(f"> Auto-generated by jib on {datetime.now(UTC).strftime('%Y-%m-%d')}.")
        sections.append("")

        sections.append("## Overview")
        sections.append("")
        if context.patterns:
            desc = context.patterns[0].get("description", "")
            sections.append(desc if desc else f"The {context.topic} pattern in this codebase.")
        sections.append("")

        sections.append("## Usage")
        sections.append("")
        if context.conventions:
            for convention in context.conventions:
                sections.append(f"- {convention}")
        else:
            sections.append("*No specific conventions documented yet.*")
        sections.append("")

        sections.append("## Examples")
        sections.append("")
        if context.code_examples:
            for example in context.code_examples[:5]:
                sections.append(f"- `{example}`")
        else:
            sections.append("*No examples found.*")
        sections.append("")

        content = "\n".join(sections)
        return DraftDoc(
            title=title,
            content=content,
            doc_type="pattern",
            sources=[f"patterns.json:{context.topic}"],
        )

    # =========================================================================
    # Agent 3: Review Agent - Validates documentation
    # =========================================================================
    def review_draft(self, draft: DraftDoc, context: DocContext) -> ReviewResult:
        """Review Agent: Validate the draft for accuracy and completeness."""
        issues = []
        suggestions = []

        if len(draft.content) < 200:
            issues.append("Documentation is too short (less than 200 characters)")

        if "TBD" in draft.content or "*Research needed*" in draft.content:
            suggestions.append("Document contains placeholder content that needs completion")

        lines = draft.content.split("\n")
        prev_was_header = False
        for line in lines:
            if line.startswith("#"):
                if prev_was_header:
                    issues.append(f"Empty section before: {line}")
                prev_was_header = True
            elif line.strip():
                prev_was_header = False

        for example in context.code_examples[:3]:
            if ":" in example:
                file_path, _line = example.rsplit(":", 1)
                full_path = self.project_root / file_path
                if not full_path.exists():
                    issues.append(f"Referenced file no longer exists: {file_path}")

        if draft.warnings:
            for warning in draft.warnings:
                suggestions.append(warning)

        approved = len(issues) == 0
        return ReviewResult(approved=approved, issues=issues, suggestions=suggestions)

    # =========================================================================
    # Agent 4: Output Agent - Formats and saves documentation
    # =========================================================================
    def save_documentation(
        self, draft: DraftDoc, review: ReviewResult, output_path: Path | None = None
    ) -> Path:
        """Output Agent: Format and save the final documentation."""
        if output_path is None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{draft.title.lower().replace(' ', '-')}.md"
            filename = "".join(c for c in filename if c.isalnum() or c in "-_.").strip("-")
            output_path = self.output_dir / filename

        final_content = draft.content
        if review.issues or review.suggestions:
            notes = []
            notes.append("")
            notes.append("---")
            notes.append("")
            notes.append("## Review Notes")
            notes.append("")
            if review.issues:
                notes.append("### Issues to Address")
                for issue in review.issues:
                    notes.append(f"- {issue}")
                notes.append("")
            if review.suggestions:
                notes.append("### Suggestions")
                for suggestion in review.suggestions:
                    notes.append(f"- {suggestion}")
                notes.append("")
            final_content += "\n".join(notes)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_content)

        return output_path

    # =========================================================================
    # Pipeline orchestration
    # =========================================================================
    def generate(
        self,
        topic: str,
        doc_type: str = "status-quo",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the 4-agent documentation generation pipeline."""
        result = {
            "topic": topic,
            "doc_type": doc_type,
            "success": False,
            "output_path": None,
            "issues": [],
            "suggestions": [],
        }

        print(f"Generating {doc_type} documentation for: {topic}")

        # Step 1: Context Agent
        print("  [1/4] Gathering context...")
        context = self.gather_context(topic)
        print(
            f"        Found {len(context.patterns)} patterns, {len(context.components)} components"
        )

        if not context.patterns and not context.components:
            print(f"  Warning: No patterns or components found for topic '{topic}'")
            result["issues"].append(f"No patterns or components found for topic '{topic}'")

        # Step 2: Draft Agent
        print("  [2/4] Generating draft...")
        draft = self.generate_draft(context, doc_type)
        print(f"        Generated: {draft.title}")

        # Step 3: Review Agent
        print("  [3/4] Reviewing draft...")
        review = self.review_draft(draft, context)

        result["issues"] = review.issues
        result["suggestions"] = review.suggestions

        if review.approved:
            print("        Review: APPROVED")
        else:
            print(f"        Review: {len(review.issues)} issues found")

        # Step 4: Output Agent
        if dry_run:
            print("  [4/4] Dry run - not saving")
            print("\n--- Generated Content Preview ---")
            print(draft.content[:1500])
            if len(draft.content) > 1500:
                print(f"\n... ({len(draft.content) - 1500} more characters)")
        else:
            print("  [4/4] Saving documentation...")
            output_path = self.save_documentation(draft, review)
            result["output_path"] = str(output_path)
            print(f"        Saved to: {output_path}")
            result["success"] = True

        return result

    def generate_all(
        self,
        doc_type: str = "status-quo",
        dry_run: bool = False,
    ) -> list[dict]:
        """Generate documentation for all detected patterns."""
        results = []
        topics = self.list_available_topics()

        pattern_topics = [t for t in topics if t["source"] == "detected_pattern"]

        print(f"Generating {doc_type} docs for {len(pattern_topics)} detected patterns\n")

        for topic_info in pattern_topics:
            result = self.generate(topic_info["name"], doc_type, dry_run)
            results.append(result)
            print()

        successful = sum(1 for r in results if r["success"])
        print(f"\nSummary: {successful}/{len(results)} documents generated successfully")

        return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate documentation from codebase analysis (4-agent pipeline)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list-topics                    # List available topics
  %(prog)s --topic auth --type status-quo   # Generate auth status quo docs
  %(prog)s --topic auth --type pattern      # Generate pattern docs
  %(prog)s --all                            # Generate all pattern docs
  %(prog)s --all --dry-run                  # Preview without saving

Note: For best practice research, use the adr-researcher tool instead.
        """,
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent.parent,
        help="Project root (default: james-in-a-box)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output directory (default: docs/generated/authored)",
    )

    parser.add_argument(
        "--list-topics",
        "-l",
        action="store_true",
        help="List available topics for documentation",
    )

    parser.add_argument(
        "--topic",
        "-t",
        help="Topic to generate documentation for",
    )

    parser.add_argument(
        "--type",
        choices=["status-quo", "pattern", "best-practice"],
        default="status-quo",
        help="Type of documentation to generate (default: status-quo)",
    )

    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Generate documentation for all detected patterns",
    )

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview without saving files",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)

    generator = DocumentationGenerator(project_root, args.output)

    # List topics
    if args.list_topics:
        topics = generator.list_available_topics()
        if args.json:
            print(json.dumps(topics, indent=2))
        else:
            print("Available documentation topics:")
            print()
            print(f"{'Topic':<20} {'Source':<20} {'Examples':<10} Description")
            print("-" * 80)
            for topic in topics:
                print(
                    f"{topic['name']:<20} {topic['source']:<20} "
                    f"{topic['examples_count']:<10} {topic['description'][:30]}"
                )
        return

    # Generate all
    if args.all:
        results = generator.generate_all(args.type, args.dry_run)
        if args.json:
            print(json.dumps(results, indent=2))
        return

    # Generate single topic
    if args.topic:
        result = generator.generate(args.topic, args.type, args.dry_run)
        if args.json:
            print(json.dumps(result, indent=2))
        return

    # No action specified
    parser.print_help()
    print("\nError: Specify --topic, --all, or --list-topics", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
