"""
Spec/Task Enricher with Dynamic Documentation Discovery.

Per ADR: LLM Documentation Index Strategy (Phase 3)

Dynamically parses docs/index.md to discover available documentation,
then enriches task descriptions with relevant doc links and code examples.
"""

import json
import re
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
    """Enriches task specs with relevant documentation and code references.

    Dynamically discovers documentation by parsing docs/index.md.
    """

    # Keyword patterns to extract from task text
    # Maps regex pattern -> list of keywords to associate
    KEYWORD_PATTERNS = {
        # Testing
        r"\btest(?:s|ing)?\b": ["test", "testing"],
        r"\be2e\b": ["e2e", "testing", "end-to-end"],
        r"\bunit\s*test": ["testing", "unit"],
        r"\bpytest\b": ["testing", "pytest"],
        r"\bjest\b": ["testing", "jest"],
        # API
        r"\bapi\b": ["api", "endpoint"],
        r"\bendpoint(?:s)?\b": ["api", "endpoint"],
        r"\brest\b": ["api", "rest"],
        # Authentication/Security
        r"\bauth(?:entication|orization)?\b": ["auth", "authentication", "security"],
        r"\blogin\b": ["auth", "login"],
        r"\bsecur(?:e|ity)\b": ["security"],
        r"\btoken\b": ["auth", "token"],
        r"\bjwt\b": ["auth", "jwt", "token"],
        # Database
        r"\bdatabase\b": ["database", "db"],
        r"\bpostgres(?:ql)?\b": ["database", "postgres"],
        r"\bredis\b": ["redis", "cache"],
        r"\bmigration(?:s)?\b": ["database", "migration"],
        # Slack integration
        r"\bslack\b": ["slack", "notification"],
        r"\bnotif(?:ication|y)?\b": ["notification"],
        # GitHub integration
        r"\bgithub\b": ["github"],
        r"\bpr\b": ["pr", "pull-request", "github"],
        r"\bpull[\s-]?request\b": ["pr", "pull-request", "github"],
        # Infrastructure
        r"\bdocker\b": ["docker", "container"],
        r"\bcontainer\b": ["docker", "container"],
        r"\bgcp\b": ["gcp", "cloud", "deployment"],
        r"\bterraform\b": ["terraform", "deployment", "infrastructure"],
        r"\bdeployment?\b": ["deployment"],
        # Architecture
        r"\barchitecture\b": ["architecture"],
        r"\badr\b": ["adr", "architecture"],
        r"\bdesign\b": ["design", "architecture"],
        # Beads/Task tracking
        r"\bbeads?\b": ["beads", "task"],
        r"\btask\s*track(?:ing)?\b": ["beads", "task"],
        # Context sync
        r"\bconfluence\b": ["confluence", "sync"],
        r"\bjira\b": ["jira", "sync"],
        r"\bcontext[\s-]?sync\b": ["sync", "context"],
        # Setup
        r"\bsetup\b": ["setup", "install", "configuration"],
        r"\binstall(?:ation)?\b": ["setup", "install"],
        r"\bconfig(?:uration)?\b": ["configuration", "setup"],
    }

    def __init__(self, project_root: Path | None = None):
        """Initialize the enricher.

        Args:
            project_root: Project root directory. Defaults to james-in-a-box.
        """
        if project_root is None:
            # Default to james-in-a-box
            project_root = Path(__file__).parent.parent.parent

        self.project_root = project_root.resolve()
        self.docs_dir = self.project_root / "docs"
        self.generated_dir = self.docs_dir / "generated"
        self.index_file = self.docs_dir / "index.md"

        # Dynamically discovered docs from index.md
        self._doc_index: dict[str, list[tuple[str, str]]] | None = None

        # Load generated indexes
        self.codebase_index = self._load_json("codebase.json")
        self.patterns_index = self._load_json("patterns.json")

    def _load_json(self, filename: str) -> dict[str, Any]:
        """Load a JSON file from the generated directory."""
        filepath = self.generated_dir / filename
        if filepath.exists():
            try:
                return json.loads(filepath.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    @property
    def doc_index(self) -> dict[str, list[tuple[str, str]]]:
        """Lazily load and parse the documentation index."""
        if self._doc_index is None:
            self._doc_index = self._parse_docs_index()
        return self._doc_index

    def _parse_docs_index(self) -> dict[str, list[tuple[str, str]]]:
        """Parse docs/index.md to build keyword -> doc mappings.

        Returns:
            Dict mapping keywords to list of (doc_path, description) tuples.
        """
        doc_index: dict[str, list[tuple[str, str]]] = {}

        if not self.index_file.exists():
            return doc_index

        try:
            content = self.index_file.read_text()
        except OSError:
            return doc_index

        # Parse markdown tables to extract doc links and descriptions
        # Format: | [Title](path) | Description |
        table_row_pattern = r"\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+)\|"

        for match in re.finditer(table_row_pattern, content):
            title = match.group(1).strip()
            path = match.group(2).strip()
            description = match.group(3).strip()

            # Normalize path (add docs/ prefix if needed)
            if not path.startswith("docs/") and not path.startswith("../"):
                path = f"docs/{path}"

            # Extract keywords from title and description
            keywords = self._extract_keywords_from_text(f"{title} {description}")

            # Also add keywords from the path
            path_parts = path.lower().replace("-", " ").replace("_", " ").split("/")
            for part in path_parts:
                # Remove file extension
                part = re.sub(r"\.md$", "", part)
                if part and part not in ["docs", "adr", "in", "progress", "not", "implemented"]:
                    keywords.add(part)

            # Add to index
            for keyword in keywords:
                if keyword not in doc_index:
                    doc_index[keyword] = []
                if (path, description) not in doc_index[keyword]:
                    doc_index[keyword].append((path, description))

        return doc_index

    def _extract_keywords_from_text(self, text: str) -> set[str]:
        """Extract keywords from text using pattern matching."""
        keywords = set()
        text_lower = text.lower()

        for pattern, kw_list in self.KEYWORD_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                keywords.update(kw_list)

        # Also extract simple words that might be keywords
        words = re.findall(r"\b[a-z]{3,}\b", text_lower)
        important_words = {
            "slack", "github", "beads", "authentication", "security",
            "deployment", "architecture", "testing", "notification",
            "sync", "jira", "confluence", "setup", "reference",
        }
        for word in words:
            if word in important_words:
                keywords.add(word)

        return keywords

    def extract_keywords(self, text: str) -> list[str]:
        """Extract relevant keywords from task text.

        Args:
            text: Task description text.

        Returns:
            Sorted list of extracted keywords.
        """
        keywords = set()
        text_lower = text.lower()

        for pattern, kw_list in self.KEYWORD_PATTERNS.items():
            if re.search(pattern, text_lower, re.IGNORECASE):
                keywords.update(kw_list)

        return sorted(keywords)

    def find_relevant_docs(self, keywords: list[str]) -> list[DocReference]:
        """Find documentation relevant to the given keywords.

        Args:
            keywords: List of keywords to search for.

        Returns:
            List of DocReference objects, sorted by relevance.
        """
        doc_scores: dict[str, tuple[float, str]] = {}

        for keyword in keywords:
            if keyword in self.doc_index:
                for doc_path, description in self.doc_index[keyword]:
                    if doc_path not in doc_scores:
                        doc_scores[doc_path] = (0.0, description)
                    current_score, desc = doc_scores[doc_path]
                    doc_scores[doc_path] = (current_score + 1.0, desc)

        # Convert to DocReferences and verify existence
        docs = []
        for doc_path, (score, description) in doc_scores.items():
            full_path = self.project_root / doc_path
            if full_path.exists():
                docs.append(
                    DocReference(
                        path=doc_path,
                        description=description,
                        relevance_score=score,
                        instruction=f"Read for guidance on {description.lower()}"
                        if description
                        else f"Read {doc_path}",
                    )
                )

        # Sort by relevance score (descending)
        docs.sort(key=lambda d: d.relevance_score, reverse=True)

        return docs[:5]  # Top 5

    def find_code_examples(self, keywords: list[str]) -> list[CodeExample]:
        """Find code examples relevant to the given keywords.

        Args:
            keywords: List of keywords to search for.

        Returns:
            List of CodeExample objects.
        """
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
            "context": "sync",
            "config": "config",
            "configuration": "config",
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
                pattern_examples = pattern_info.get("examples", [])[:3]

                for example_ref in pattern_examples:
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

        # Deduplicate by path
        seen_paths = set()
        unique_examples = []
        for ex in examples:
            if ex.path not in seen_paths:
                seen_paths.add(ex.path)
                unique_examples.append(ex)

        return unique_examples[:5]

    def find_relevant_patterns(self, keywords: list[str]) -> list[str]:
        """Find pattern names that match the keywords.

        Args:
            keywords: List of keywords to search for.

        Returns:
            List of matching pattern names.
        """
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
        """Enrich a spec/task with relevant context.

        Args:
            spec_text: The task/spec description to enrich.

        Returns:
            EnrichedContext with relevant docs, examples, and patterns.
        """
        keywords = self.extract_keywords(spec_text)
        docs = self.find_relevant_docs(keywords)
        examples = self.find_code_examples(keywords)
        patterns = self.find_relevant_patterns(keywords)

        return EnrichedContext(
            documentation=docs,
            examples=examples,
            patterns=patterns,
            keywords_matched=keywords,
        )

    def format_markdown(self, context: EnrichedContext) -> str:
        """Format enriched context as Markdown.

        Args:
            context: The enriched context to format.

        Returns:
            Markdown string.
        """
        if not context.keywords_matched:
            return ""

        lines = ["## Relevant Documentation Context", ""]

        if context.documentation:
            lines.append("### Read These First")
            for doc in context.documentation:
                lines.append(f"- `{doc.path}`: {doc.description}")
            lines.append("")

        if context.examples:
            lines.append("### Code Examples to Reference")
            for ex in context.examples:
                path_with_line = f"{ex.path}:{ex.line}" if ex.line else ex.path
                lines.append(f"- `{path_with_line}`: {ex.instruction}")
            lines.append("")

        if context.patterns:
            lines.append("### Patterns in This Codebase")
            for pattern in context.patterns:
                lines.append(f"- `{pattern}`")
            lines.append("")

        lines.append(f"*Auto-detected keywords: {', '.join(context.keywords_matched)}*")
        lines.append("")

        return "\n".join(lines)

    def format_yaml(self, context: EnrichedContext) -> str:
        """Format enriched context as YAML.

        Args:
            context: The enriched context to format.

        Returns:
            YAML string.
        """
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

    def format_json(self, context: EnrichedContext) -> str:
        """Format enriched context as JSON.

        Args:
            context: The enriched context to format.

        Returns:
            JSON string.
        """
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


def enrich_task(task_text: str, project_root: Path | None = None) -> str:
    """Convenience function to enrich a task and return markdown context.

    Args:
        task_text: The task description to enrich.
        project_root: Optional project root path.

    Returns:
        Markdown string with relevant context, or empty string if no matches.
    """
    enricher = SpecEnricher(project_root)
    context = enricher.enrich(task_text)
    return enricher.format_markdown(context)
