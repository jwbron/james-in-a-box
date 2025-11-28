#!/usr/bin/env python3
"""
Spec Enricher for LLM Documentation Strategy

Automatically enriches task specs with relevant documentation links and code examples.
Takes a task description and returns an enriched version with context pointers.

Per ADR: LLM Documentation Index Strategy (Phase 3)

Usage:
  # Enrich from file
  python3 spec-enricher.py --spec task.md

  # Enrich from stdin
  echo "Add authentication to API" | python3 spec-enricher.py

  # Output as YAML
  python3 spec-enricher.py --spec task.md --format yaml

  # Just get the context (no original content)
  python3 spec-enricher.py --spec task.md --context-only
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DocReference:
    """A reference to a documentation file."""

    path: str
    description: str
    relevance_score: float = 0.0
    instruction: str = ""


@dataclass
class CodeExample:
    """A reference to example code."""

    path: str
    line: int | None = None
    pattern: str = ""
    description: str = ""
    instruction: str = ""


@dataclass
class EnrichedContext:
    """The enrichment context to add to a spec."""

    documentation: list[DocReference] = field(default_factory=list)
    examples: list[CodeExample] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    keywords_matched: list[str] = field(default_factory=list)


class SpecEnricher:
    """Enriches task specs with relevant documentation and code references."""

    # Keywords that indicate specific documentation needs
    KEYWORD_PATTERNS = {
        # Testing
        r"\btest(?:s|ing)?\b": ["testing", "test"],
        r"\be2e\b": ["testing", "e2e", "end-to-end"],
        r"\bunit\s*test": ["testing", "unit"],
        r"\bpytest\b": ["testing", "pytest"],
        r"\bjest\b": ["testing", "jest"],
        # API
        r"\bapi\b": ["api", "endpoint", "rest"],
        r"\bendpoint(?:s)?\b": ["api", "endpoint"],
        r"\brest\b": ["api", "rest"],
        r"\bgraphql\b": ["api", "graphql"],
        # Authentication/Security
        r"\bauth(?:entication|orization)?\b": ["auth", "security", "authentication"],
        r"\blogin\b": ["auth", "login", "authentication"],
        r"\bsecur(?:e|ity)\b": ["security"],
        r"\btoken\b": ["auth", "token", "jwt"],
        r"\bjwt\b": ["auth", "jwt", "token"],
        r"\boauth\b": ["auth", "oauth"],
        # Database
        r"\bdatabase\b": ["database", "db"],
        r"\bpostgres(?:ql)?\b": ["database", "postgres"],
        r"\bredis\b": ["database", "redis", "cache"],
        r"\bmigration(?:s)?\b": ["database", "migration"],
        r"\bquery\b": ["database", "query"],
        # Slack integration
        r"\bslack\b": ["slack", "notification", "messaging"],
        r"\bnotif(?:ication|y)?\b": ["notification", "slack"],
        # GitHub integration
        r"\bgithub\b": ["github", "pr", "repository"],
        r"\bpr\b": ["github", "pr", "pull-request"],
        r"\bpull[\s-]?request\b": ["github", "pr"],
        # Infrastructure
        r"\bdocker\b": ["docker", "container"],
        r"\bcontainer\b": ["docker", "container"],
        r"\bgcp\b": ["gcp", "cloud", "infrastructure"],
        r"\bdeployment?\b": ["deployment", "infrastructure"],
        # Code patterns
        r"\brefactor\b": ["refactor", "code-quality"],
        r"\bperformance\b": ["performance", "optimization"],
        r"\berror\s*handl(?:e|ing)\b": ["error-handling"],
        r"\blog(?:ging)?\b": ["logging", "observability"],
        # Architecture
        r"\barchitecture\b": ["architecture", "design"],
        r"\badr\b": ["adr", "architecture"],
        r"\bdesign\b": ["architecture", "design"],
        # Beads/Task tracking
        r"\bbeads?\b": ["beads", "task-tracking"],
        r"\btask\s*track(?:ing)?\b": ["beads", "task-tracking"],
        # Context sync
        r"\bconfluence\b": ["confluence", "context-sync"],
        r"\bjira\b": ["jira", "context-sync"],
        r"\bcontext[\s-]?sync\b": ["context-sync"],
    }

    # Documentation index mapping - topic keywords to doc paths
    DOC_INDEX = {
        "testing": [
            ("docs/reference/README.md", "Testing and reference guides"),
        ],
        "api": [
            ("docs/architecture/README.md", "API and architecture patterns"),
        ],
        "auth": [
            ("docs/reference/claude-authentication.md", "Authentication guide"),
            ("docs/setup/github-app-setup.md", "GitHub App authentication"),
        ],
        "security": [
            (
                "docs/adr/not-implemented/ADR-Internet-Tool-Access-Lockdown.md",
                "Security restrictions",
            ),
            (
                "docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md",
                "Security model",
            ),
        ],
        "slack": [
            ("docs/architecture/slack-integration.md", "Slack integration design"),
            ("docs/setup/slack-quickstart.md", "Slack setup guide"),
            ("docs/reference/slack-quick-reference.md", "Slack operations reference"),
        ],
        "notification": [
            ("docs/architecture/slack-integration.md", "Notification system"),
            ("docs/architecture/host-slack-notifier.md", "Notifier implementation"),
        ],
        "github": [
            ("docs/setup/github-app-setup.md", "GitHub App setup"),
        ],
        "docker": [
            (
                "docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md",
                "Container environment",
            ),
        ],
        "architecture": [
            ("docs/architecture/README.md", "Architecture overview"),
            (
                "docs/adr/in-progress/ADR-Autonomous-Software-Engineer.md",
                "System architecture ADR",
            ),
        ],
        "adr": [
            ("docs/adr/README.md", "ADR index"),
        ],
        "beads": [
            ("docs/reference/beads.md", "Beads task tracking system"),
        ],
        "task-tracking": [
            ("docs/reference/beads.md", "Task tracking with Beads"),
        ],
        "context-sync": [
            (
                "docs/adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md",
                "Context sync strategy",
            ),
        ],
        "confluence": [
            (
                "docs/adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md",
                "Confluence sync",
            ),
        ],
        "jira": [
            (
                "docs/adr/in-progress/ADR-Context-Sync-Strategy-Custom-vs-MCP.md",
                "JIRA sync",
            ),
        ],
        "deployment": [
            ("docs/adr/not-implemented/ADR-GCP-Deployment-Terraform.md", "GCP deployment"),
        ],
        "gcp": [
            ("docs/adr/not-implemented/ADR-GCP-Deployment-Terraform.md", "GCP infrastructure"),
            (
                "docs/adr/not-implemented/ADR-Slack-Bot-GCP-Integration.md",
                "GCP Slack integration",
            ),
        ],
        "documentation": [
            (
                "docs/adr/in-progress/ADR-LLM-Documentation-Index-Strategy.md",
                "Documentation strategy",
            ),
            ("docs/index.md", "Documentation index"),
        ],
    }

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.docs_dir = self.project_root / "docs"
        self.generated_dir = self.docs_dir / "generated"

        # Load generated indexes if available
        self.codebase_index = self._load_json("codebase.json")
        self.patterns_index = self._load_json("patterns.json")
        self.dependencies_index = self._load_json("dependencies.json")

    def _load_json(self, filename: str) -> dict[str, Any]:
        """Load a JSON file from the generated directory."""
        filepath = self.generated_dir / filename
        if filepath.exists():
            try:
                return json.loads(filepath.read_text())
            except (json.JSONDecodeError, OSError) as e:
                print(f"Warning: Could not load {filename}: {e}", file=sys.stderr)
        return {}

    def extract_keywords(self, text: str) -> list[str]:
        """Extract relevant keywords from task text."""
        keywords = set()
        text_lower = text.lower()

        for pattern, keyword_list in self.KEYWORD_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                keywords.update(keyword_list)

        return sorted(keywords)

    def find_relevant_docs(self, keywords: list[str]) -> list[DocReference]:
        """Find documentation relevant to the given keywords."""
        doc_scores: dict[str, tuple[float, str]] = defaultdict(lambda: (0.0, ""))

        for keyword in keywords:
            if keyword in self.DOC_INDEX:
                for doc_path, description in self.DOC_INDEX[keyword]:
                    current_score, current_desc = doc_scores[doc_path]
                    # Increment score for each keyword match
                    doc_scores[doc_path] = (current_score + 1.0, description)

        # Convert to DocReferences and sort by score
        docs = []
        for doc_path, (score, description) in doc_scores.items():
            # Verify the doc exists
            full_path = self.project_root / doc_path
            if full_path.exists():
                docs.append(
                    DocReference(
                        path=doc_path,
                        description=description,
                        relevance_score=score,
                        instruction=f"Read for guidance on {description.lower()}",
                    )
                )

        # Sort by relevance score (descending)
        docs.sort(key=lambda d: d.relevance_score, reverse=True)

        # Return top 5 most relevant
        return docs[:5]

    def find_code_examples(self, keywords: list[str]) -> list[CodeExample]:
        """Find code examples relevant to the given keywords."""
        examples = []

        if not self.patterns_index:
            return examples

        patterns_data = self.patterns_index.get("patterns", {})

        # Map keywords to pattern names
        keyword_to_pattern = {
            "notification": "notification",
            "slack": "notification",
            "connector": "connector",
            "sync": "sync",
            "context-sync": "sync",
            "config": "config",
            "event": "event_driven",
            "watcher": "event_driven",
            "handler": "event_driven",
            "processor": "processor",
        }

        matched_patterns = set()
        for keyword in keywords:
            if keyword in keyword_to_pattern:
                matched_patterns.add(keyword_to_pattern[keyword])

        # Get examples from matched patterns
        for pattern_name in matched_patterns:
            if pattern_name in patterns_data:
                pattern_info = patterns_data[pattern_name]
                pattern_examples = pattern_info.get("examples", [])[:3]  # Top 3

                for example_ref in pattern_examples:
                    # Parse "file:line" format
                    if ":" in example_ref:
                        path, line_str = example_ref.rsplit(":", 1)
                        try:
                            line = int(line_str)
                        except ValueError:
                            line = None
                    else:
                        path = example_ref
                        line = None

                    examples.append(
                        CodeExample(
                            path=path,
                            line=line,
                            pattern=pattern_name,
                            description=pattern_info.get("description", ""),
                            instruction=f"Reference for {pattern_name} pattern",
                        )
                    )

        # Also search components for keyword matches
        if self.codebase_index:
            components = self.codebase_index.get("components", [])
            for component in components[:50]:  # Check first 50 components
                comp_name = component.get("name", "").lower()
                comp_desc = component.get("description", "").lower()

                for keyword in keywords:
                    if keyword in comp_name or keyword in comp_desc:
                        examples.append(
                            CodeExample(
                                path=component.get("file", ""),
                                line=component.get("line"),
                                pattern="",
                                description=component.get("description", comp_name),
                                instruction=f"Reference implementation of {comp_name}",
                            )
                        )
                        break

        # Deduplicate by path
        seen_paths = set()
        unique_examples = []
        for ex in examples:
            if ex.path not in seen_paths:
                seen_paths.add(ex.path)
                unique_examples.append(ex)

        return unique_examples[:5]  # Top 5 examples

    def find_relevant_patterns(self, keywords: list[str]) -> list[str]:
        """Find pattern names that match the keywords."""
        if not self.patterns_index:
            return []

        patterns_data = self.patterns_index.get("patterns", {})
        matched = []

        for pattern_name, pattern_info in patterns_data.items():
            description = pattern_info.get("description", "").lower()
            pattern_keywords = pattern_name.replace("_", " ").split()

            for keyword in keywords:
                if keyword in pattern_keywords or keyword in description:
                    if pattern_name not in matched:
                        matched.append(pattern_name)
                    break

        return matched

    def enrich(self, spec_text: str) -> EnrichedContext:
        """Enrich a spec/task with relevant context."""
        # Extract keywords
        keywords = self.extract_keywords(spec_text)

        # Find relevant documentation
        docs = self.find_relevant_docs(keywords)

        # Find code examples
        examples = self.find_code_examples(keywords)

        # Find relevant patterns
        patterns = self.find_relevant_patterns(keywords)

        return EnrichedContext(
            documentation=docs,
            examples=examples,
            patterns=patterns,
            keywords_matched=keywords,
        )

    def format_yaml(self, context: EnrichedContext) -> str:
        """Format enriched context as YAML."""
        lines = ["context:"]

        if context.documentation:
            lines.append("  documentation:")
            for doc in context.documentation:
                lines.append(f'    - path: "{doc.path}"')
                lines.append(f'      instruction: "{doc.instruction}"')

        if context.examples:
            lines.append("  examples:")
            for ex in context.examples:
                path_with_line = f"{ex.path}:{ex.line}" if ex.line else ex.path
                lines.append(f'    - path: "{path_with_line}"')
                lines.append(f'      instruction: "{ex.instruction}"')

        if context.patterns:
            lines.append("  patterns:")
            for pattern in context.patterns:
                lines.append(f"    - {pattern}")

        if context.keywords_matched:
            lines.append(f"  # Keywords matched: {', '.join(context.keywords_matched)}")

        return "\n".join(lines)

    def format_markdown(self, context: EnrichedContext) -> str:
        """Format enriched context as Markdown."""
        lines = ["## Relevant Context", ""]

        if context.documentation:
            lines.append("### Documentation to Read First")
            lines.append("")
            for doc in context.documentation:
                lines.append(f"- **[{doc.path}]({doc.path})**: {doc.instruction}")
            lines.append("")

        if context.examples:
            lines.append("### Code Examples to Reference")
            lines.append("")
            for ex in context.examples:
                path_with_line = f"{ex.path}:{ex.line}" if ex.line else ex.path
                lines.append(f"- `{path_with_line}`: {ex.instruction}")
            lines.append("")

        if context.patterns:
            lines.append("### Patterns Used in This Codebase")
            lines.append("")
            for pattern in context.patterns:
                lines.append(f"- `{pattern}`")
            lines.append("")

        lines.append(f"*Keywords detected: {', '.join(context.keywords_matched)}*")

        return "\n".join(lines)

    def format_json(self, context: EnrichedContext) -> str:
        """Format enriched context as JSON."""
        data = {
            "context": {
                "documentation": [
                    {"path": doc.path, "instruction": doc.instruction}
                    for doc in context.documentation
                ],
                "examples": [
                    {
                        "path": f"{ex.path}:{ex.line}" if ex.line else ex.path,
                        "instruction": ex.instruction,
                    }
                    for ex in context.examples
                ],
                "patterns": context.patterns,
                "keywords_matched": context.keywords_matched,
            }
        }
        return json.dumps(data, indent=2)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich task specs with relevant documentation and code references",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --spec task.md                    # Enrich a spec file
  echo "Add auth" | %(prog)s                 # Enrich from stdin
  %(prog)s --spec task.md --format yaml      # Output as YAML
  %(prog)s --spec task.md --context-only     # Just the context
        """,
    )

    parser.add_argument(
        "--spec",
        "-s",
        type=Path,
        help="Path to spec file to enrich (reads from stdin if not provided)",
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=Path(__file__).parent.parent.parent.parent,  # james-in-a-box root
        help="Project root (default: james-in-a-box)",
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["yaml", "markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "--context-only",
        "-c",
        action="store_true",
        help="Output only the context, not the original spec",
    )

    args = parser.parse_args()

    # Read spec content
    if args.spec:
        if not args.spec.exists():
            print(f"Error: Spec file not found: {args.spec}", file=sys.stderr)
            sys.exit(1)
        spec_text = args.spec.read_text()
    elif not sys.stdin.isatty():
        spec_text = sys.stdin.read()
    else:
        print("Error: No spec provided. Use --spec or pipe content via stdin.", file=sys.stderr)
        sys.exit(1)

    if not spec_text.strip():
        print("Error: Empty spec content", file=sys.stderr)
        sys.exit(1)

    # Create enricher and process
    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)

    enricher = SpecEnricher(project_root)
    context = enricher.enrich(spec_text)

    # Format output
    if args.format == "yaml":
        context_str = enricher.format_yaml(context)
    elif args.format == "json":
        context_str = enricher.format_json(context)
    else:
        context_str = enricher.format_markdown(context)

    # Output
    if args.context_only:
        print(context_str)
    else:
        # Include original spec with context injected
        if args.format == "yaml":
            # For YAML, output context then original
            print(context_str)
            print()
            print("# Original spec:")
            print(spec_text)
        else:
            # For markdown/json, prepend context
            print(context_str)
            print()
            print("---")
            print()
            print(spec_text)


if __name__ == "__main__":
    main()
