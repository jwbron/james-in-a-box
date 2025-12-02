#!/usr/bin/env python3
"""
LLM Documentation Generator - 4-Agent Pipeline with Claude Integration

Generates documentation from codebase analysis using a multi-agent pipeline,
now enhanced with Claude AI for intelligent analysis at each phase:

1. Context Agent: Analyzes code structure and identifies semantic patterns (Claude-enhanced)
2. Draft Agent: Generates human-quality documentation (Claude-enhanced)
3. Review Agent: Validates accuracy and completeness (Claude-enhanced)
4. Output Agent: Formats and saves documentation (Claude-enhanced)

Per ADR: LLM Documentation Index Strategy

Usage:
  # Generate status quo docs for a component (uses Claude by default)
  python3 doc-generator.py --type status-quo --topic auth

  # Generate pattern docs
  python3 doc-generator.py --type pattern --topic notification

  # List all detected patterns for documentation
  python3 doc-generator.py --list-topics

  # Generate docs for all detected patterns
  python3 doc-generator.py --all

  # Preview without saving
  python3 doc-generator.py --all --dry-run

  # Disable Claude (use heuristic-only mode)
  python3 doc-generator.py --topic auth --no-claude

  # Show verbose Claude output
  python3 doc-generator.py --topic auth --verbose
"""

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Add shared modules to path
sys.path.insert(0, str(Path.home() / "khan" / "james-in-a-box" / "shared"))


@dataclass
class ClaudeResult:
    """Result from a Claude operation."""

    success: bool = False
    stdout: str = ""


try:
    from claude import is_claude_available, run_claude
except ImportError:
    # Fallback if shared module not available
    def is_claude_available() -> bool:
        return False

    def run_claude(*args, **kwargs) -> ClaudeResult:
        return ClaudeResult(success=False, stdout="")


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


@dataclass
class ClaudeContextAnalysis:
    """Enhanced context from Claude analysis."""

    semantic_patterns: list[dict] = field(default_factory=list)
    code_insights: list[str] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    documentation_suggestions: list[str] = field(default_factory=list)
    confidence: str = "medium"


@dataclass
class ContextResult:
    """Result from context gathering, combining static and Claude analysis."""

    context: DocContext
    claude_analysis: ClaudeContextAnalysis | None = None


class ClaudeDocAgent:
    """Claude-based agent for intelligent documentation generation.

    Provides Claude-enhanced analysis for all four phases of the documentation pipeline:
    1. Context Analysis: Semantic understanding of code patterns
    2. Draft Generation: Human-quality documentation writing
    3. Review Validation: Accuracy and completeness checking
    4. Output Formatting: Intelligent formatting suggestions
    """

    # Default timeouts for Claude operations (in seconds)
    DEFAULT_CONTEXT_TIMEOUT = 90
    DEFAULT_DRAFT_TIMEOUT = 120
    DEFAULT_REVIEW_TIMEOUT = 90
    DEFAULT_FORMAT_TIMEOUT = 90

    # Maximum content length to send to Claude to avoid exceeding context window
    MAX_DRAFT_CONTENT_LENGTH = 8000

    CONTEXT_ANALYSIS_PROMPT = """You are a code documentation expert analyzing a codebase.

## Task
Analyze the following code context for the topic "{topic}" and provide semantic insights.

## Available Context

### Detected Patterns (from static analysis)
{patterns_json}

### Code Components
{components_json}

### Existing Documentation
{existing_docs}

## Analysis Request
Provide a JSON response (ONLY valid JSON, no markdown code blocks):

{{
    "semantic_patterns": [
        {{
            "name": "pattern name",
            "description": "what this pattern does and why",
            "use_cases": ["when to use this pattern"],
            "files": ["relevant file paths"]
        }}
    ],
    "code_insights": [
        "insight about code organization",
        "insight about design decisions"
    ],
    "relationships": [
        {{
            "from": "component A",
            "to": "component B",
            "relationship": "description of how they interact"
        }}
    ],
    "documentation_suggestions": [
        "what should be documented",
        "what's currently missing"
    ],
    "confidence": "low|medium|high"
}}

Focus on:
1. **Semantic Understanding**: What the code is trying to accomplish, not just structure
2. **Hidden Patterns**: Patterns that static analysis might miss
3. **Developer Intent**: Why the code is organized this way
4. **Documentation Gaps**: What a developer would need to know

Keep your response concise - limit to 2000 characters max.
"""

    DRAFT_GENERATION_PROMPT = """You are a technical writer creating documentation for a software project.

## Task
Generate {doc_type} documentation for the topic "{topic}".

## Context (analyzed from codebase)

### Patterns
{patterns_summary}

### Components
{components_summary}

### Semantic Insights
{insights}

### Conventions
{conventions}

## Requirements
Generate markdown documentation that:
1. Is clear and actionable for developers
2. Includes code examples where helpful
3. Explains the "why" not just the "what"
4. Is appropriate for the documentation type: {doc_type}

For "status-quo" docs: Describe current implementation objectively
For "pattern" docs: Explain the pattern, when to use it, and how

## Response Format
Provide the complete markdown document. Start with a title (# heading) and structure with clear sections.
Include a note at the top: "> Auto-generated by jib with Claude assistance on {date}. Review before relying on."

Keep the document focused and concise - aim for 1500-3000 words maximum.

Write the documentation now:
"""

    REVIEW_VALIDATION_PROMPT = """You are a documentation reviewer checking for accuracy and completeness.

## Task
Review this documentation for the topic "{topic}" and identify any issues.

## Documentation to Review
{draft_content}

## Source Context
### Patterns Found in Code
{patterns_json}

### Code Examples Referenced
{code_examples}

## Review Criteria
1. **Accuracy**: Does the documentation match the actual code?
2. **Completeness**: Are all important aspects covered?
3. **Clarity**: Is it easy to understand for developers?
4. **Actionability**: Can developers use this to accomplish tasks?
5. **Code References**: Are file paths and code examples correct?

## Response Format
Provide a JSON response (ONLY valid JSON, no markdown code blocks):

{{
    "approved": true|false,
    "issues": [
        "critical issue that must be fixed"
    ],
    "suggestions": [
        "optional improvement"
    ],
    "accuracy_score": 1-10,
    "completeness_score": 1-10,
    "clarity_score": 1-10,
    "summary": "brief review summary"
}}

Keep your response concise - limit to 1500 characters max.
"""

    OUTPUT_FORMATTING_PROMPT = """You are a documentation formatter ensuring consistent, high-quality output.

## Task
Format and polish this documentation for final output.

## Draft Content
{draft_content}

## Review Notes
{review_notes}

## Formatting Requirements
1. Consistent heading hierarchy
2. Proper markdown formatting
3. Code blocks with language specifiers
4. Clear section organization
5. Include any review suggestions that should be addressed

## Response Format
Provide the final formatted markdown document. Include all content, properly formatted.
"""

    def __init__(self, verbose: bool = False, project_root: Path | None = None):
        self.verbose = verbose
        self.project_root = project_root or Path.cwd()
        self._available = None

    def is_available(self) -> bool:
        """Check if Claude is available."""
        if self._available is None:
            self._available = is_claude_available()
        return self._available

    def analyze_context(
        self,
        topic: str,
        patterns: list[dict],
        components: list[dict],
        existing_docs: list[str],
    ) -> ClaudeContextAnalysis | None:
        """Use Claude to provide semantic analysis of the code context."""
        if not self.is_available():
            return None

        prompt = self.CONTEXT_ANALYSIS_PROMPT.format(
            topic=topic,
            patterns_json=json.dumps(patterns[:10], indent=2) if patterns else "[]",
            components_json=json.dumps(components[:15], indent=2) if components else "[]",
            existing_docs="\n".join(f"- {doc}" for doc in existing_docs[:10]) or "None found",
        )

        result = run_claude(
            prompt=prompt,
            timeout=self.DEFAULT_CONTEXT_TIMEOUT,
            stream=self.verbose,
            cwd=self.project_root,
        )

        if not result or not result.success:
            if self.verbose:
                print(f"  Claude context analysis failed for topic '{topic}'")
            return None

        try:
            data = self._extract_json(result.stdout)
            if data:
                return ClaudeContextAnalysis(
                    semantic_patterns=data.get("semantic_patterns", []),
                    code_insights=data.get("code_insights", []),
                    relationships=data.get("relationships", []),
                    documentation_suggestions=data.get("documentation_suggestions", []),
                    confidence=data.get("confidence", "medium"),
                )
        except Exception as e:
            if self.verbose:
                print(f"  Failed to parse Claude context response: {e}")
            logger.debug("Claude context parsing failed: %s", e, exc_info=True)

        return None

    def generate_draft(
        self,
        topic: str,
        doc_type: str,
        context: "DocContext",
        claude_context: ClaudeContextAnalysis | None,
    ) -> str | None:
        """Use Claude to generate documentation draft."""
        if not self.is_available():
            return None

        # Build summaries from context
        patterns_summary = (
            "\n".join(
                f"- **{p.get('name', 'Unknown')}**: {p.get('description', 'No description')}"
                for p in context.patterns[:5]
            )
            or "No patterns detected"
        )

        components_summary = (
            "\n".join(
                f"- **{c.get('name', 'Unknown')}** ({c.get('type', 'unknown')}): {c.get('file', '')}"
                for c in context.components[:10]
            )
            or "No components found"
        )

        insights = ""
        if claude_context:
            insights = (
                "\n".join(f"- {insight}" for insight in claude_context.code_insights)
                or "No additional insights"
            )
        else:
            insights = "No semantic analysis available"

        conventions = (
            "\n".join(f"- {conv}" for conv in context.conventions)
            or "No specific conventions documented"
        )

        prompt = self.DRAFT_GENERATION_PROMPT.format(
            doc_type=doc_type,
            topic=topic,
            patterns_summary=patterns_summary,
            components_summary=components_summary,
            insights=insights,
            conventions=conventions,
            date=datetime.now(UTC).strftime("%Y-%m-%d"),
        )

        result = run_claude(
            prompt=prompt,
            timeout=self.DEFAULT_DRAFT_TIMEOUT,
            stream=self.verbose,
            cwd=self.project_root,
        )

        if not result or not result.success:
            if self.verbose:
                print(f"  Claude draft generation failed for topic '{topic}'")
            return None

        return result.stdout.strip()

    def review_draft(
        self,
        topic: str,
        draft_content: str,
        context: "DocContext",
    ) -> ReviewResult | None:
        """Use Claude to review documentation draft."""
        if not self.is_available():
            return None

        prompt = self.REVIEW_VALIDATION_PROMPT.format(
            topic=topic,
            draft_content=draft_content[: self.MAX_DRAFT_CONTENT_LENGTH],
            patterns_json=json.dumps(
                [
                    {"name": p.get("name"), "description": p.get("description", "")[:200]}
                    for p in context.patterns[:5]
                ],
                indent=2,
            ),
            code_examples="\n".join(context.code_examples[:10]) or "None",
        )

        result = run_claude(
            prompt=prompt,
            timeout=self.DEFAULT_REVIEW_TIMEOUT,
            stream=self.verbose,
            cwd=self.project_root,
        )

        if not result or not result.success:
            if self.verbose:
                print(f"  Claude review failed for topic '{topic}'")
            return None

        try:
            data = self._extract_json(result.stdout)
            if data:
                return ReviewResult(
                    approved=data.get("approved", False),
                    issues=data.get("issues", []),
                    suggestions=data.get("suggestions", []),
                )
        except Exception as e:
            if self.verbose:
                print(f"  Failed to parse Claude review response: {e}")
            logger.debug("Claude review parsing failed: %s", e, exc_info=True)

        return None

    def format_output(
        self,
        draft_content: str,
        review: ReviewResult | None,
    ) -> str | None:
        """Use Claude to format and polish final output."""
        if not self.is_available():
            return None

        review_notes = ""
        if review:
            if review.issues:
                review_notes += "Issues to address:\n" + "\n".join(
                    f"- {issue}" for issue in review.issues
                )
            if review.suggestions:
                review_notes += "\n\nSuggestions:\n" + "\n".join(
                    f"- {sug}" for sug in review.suggestions
                )
        else:
            review_notes = "No review notes available"

        prompt = self.OUTPUT_FORMATTING_PROMPT.format(
            draft_content=draft_content[: self.MAX_DRAFT_CONTENT_LENGTH],
            review_notes=review_notes,
        )

        result = run_claude(
            prompt=prompt,
            timeout=self.DEFAULT_FORMAT_TIMEOUT,
            stream=self.verbose,
            cwd=self.project_root,
        )

        if not result or not result.success:
            return None

        return result.stdout.strip()

    def _extract_json(self, text: str) -> dict | None:
        """Extract JSON from Claude's response.

        Uses multiple strategies to find valid JSON:
        1. Try to find JSON in markdown code blocks first (most reliable)
        2. Try direct JSON parsing
        3. Fall back to finding JSON object boundaries in text
        """
        text = text.strip()

        # Strategy 1: Try to find JSON in markdown code blocks using regex
        code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 2: Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 3: Try to find JSON object boundaries in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return None


class DocumentationGenerator:
    """4-agent documentation generation pipeline.

    Generates documentation from codebase indexes (patterns.json, codebase.json).
    Now enhanced with Claude AI for intelligent analysis at each phase.

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

    def __init__(
        self,
        project_root: Path,
        output_dir: Path | None = None,
        use_claude: bool = True,
        verbose: bool = False,
    ):
        self.project_root = project_root.resolve()
        self.output_dir = output_dir or (project_root / "docs" / "generated" / "authored")
        self.generated_dir = project_root / "docs" / "generated"
        self.use_claude = use_claude
        self.verbose = verbose

        # Initialize Claude agent if enabled
        self.claude_agent = (
            ClaudeDocAgent(verbose=verbose, project_root=self.project_root) if use_claude else None
        )

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
    def gather_context(self, topic: str) -> ContextResult:
        """Context Agent: Gather all relevant information about a topic.

        Returns:
            ContextResult containing DocContext and optional ClaudeContextAnalysis
        """
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

        # Claude-enhanced semantic analysis
        claude_analysis = None
        if self.claude_agent and self.claude_agent.is_available():
            if self.verbose:
                print("        Using Claude for semantic context analysis...")
            claude_analysis = self.claude_agent.analyze_context(
                topic=topic,
                patterns=context.patterns,
                components=context.components,
                existing_docs=context.existing_docs,
            )
            if claude_analysis and self.verbose:
                print(
                    f"        Claude found {len(claude_analysis.semantic_patterns)} semantic patterns"
                )

        return ContextResult(context=context, claude_analysis=claude_analysis)

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
    def generate_draft(
        self,
        context: DocContext,
        doc_type: str,
        claude_context: ClaudeContextAnalysis | None = None,
    ) -> DraftDoc:
        """Draft Agent: Generate initial documentation from context.

        Uses Claude for intelligent draft generation when available,
        falling back to template-based generation.
        """
        # Try Claude-based draft generation first
        if self.claude_agent and self.claude_agent.is_available():
            if self.verbose:
                print("        Using Claude for draft generation...")

            claude_draft = self.claude_agent.generate_draft(
                topic=context.topic,
                doc_type=doc_type,
                context=context,
                claude_context=claude_context,
            )

            if claude_draft:
                title = f"{context.topic.title()} {'Patterns (Status Quo)' if doc_type == 'status-quo' else 'Pattern'}"
                return DraftDoc(
                    title=title,
                    content=claude_draft,
                    doc_type=doc_type,
                    sources=[f"claude-generated:{context.topic}"],
                )

        # Fallback to template-based generation
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
        """Review Agent: Validate the draft for accuracy and completeness.

        Uses Claude for intelligent review when available,
        falling back to heuristic-based validation.
        """
        # Try Claude-based review first
        if self.claude_agent and self.claude_agent.is_available():
            if self.verbose:
                print("        Using Claude for draft review...")

            claude_review = self.claude_agent.review_draft(
                topic=context.topic,
                draft_content=draft.content,
                context=context,
            )

            if claude_review:
                # Merge with heuristic checks for file existence
                heuristic_issues = self._check_file_references(context)
                combined_issues = list(claude_review.issues) + heuristic_issues
                return ReviewResult(
                    approved=claude_review.approved and len(heuristic_issues) == 0,
                    issues=combined_issues,
                    suggestions=claude_review.suggestions,
                )

        # Fallback to heuristic-based validation
        return self._review_draft_heuristic(draft, context)

    def _check_file_references(self, context: DocContext) -> list[str]:
        """Check if referenced files still exist."""
        issues = []
        for example in context.code_examples[:3]:
            if ":" in example:
                file_path, _line = example.rsplit(":", 1)
                full_path = self.project_root / file_path
                if not full_path.exists():
                    issues.append(f"Referenced file no longer exists: {file_path}")
        return issues

    def _review_draft_heuristic(self, draft: DraftDoc, context: DocContext) -> ReviewResult:
        """Heuristic-based review fallback."""
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

        # Check file references
        issues.extend(self._check_file_references(context))

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
        """Output Agent: Format and save the final documentation.

        Uses Claude for intelligent formatting when available,
        falling back to simple concatenation.
        """
        if output_path is None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{draft.title.lower().replace(' ', '-')}.md"
            filename = "".join(c for c in filename if c.isalnum() or c in "-_.").strip("-")
            output_path = self.output_dir / filename

        # Try Claude-based formatting if there are issues/suggestions to address
        final_content = draft.content
        if (
            self.claude_agent
            and self.claude_agent.is_available()
            and (review.issues or review.suggestions)
        ):
            if self.verbose:
                print("        Using Claude for output formatting...")

            formatted = self.claude_agent.format_output(
                draft_content=draft.content,
                review=review,
            )
            if formatted:
                final_content = formatted

        # If Claude formatting wasn't used or failed, use template-based approach
        elif review.issues or review.suggestions:
            final_content = self._format_output_heuristic(draft, review)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(final_content)

        return output_path

    def _format_output_heuristic(self, draft: DraftDoc, review: ReviewResult) -> str:
        """Heuristic-based output formatting fallback."""
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

        return final_content

    # =========================================================================
    # Pipeline orchestration
    # =========================================================================
    def generate(
        self,
        topic: str,
        doc_type: str = "status-quo",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the 4-agent documentation generation pipeline.

        Now enhanced with Claude AI at each phase when available.
        """
        result = {
            "topic": topic,
            "doc_type": doc_type,
            "success": False,
            "output_path": None,
            "issues": [],
            "suggestions": [],
            "analysis_source": "heuristic",
        }

        print(f"Generating {doc_type} documentation for: {topic}")

        # Check Claude availability
        claude_available = self.claude_agent and self.claude_agent.is_available()
        if claude_available:
            print("  Claude analysis: enabled")
            result["analysis_source"] = "claude"
        elif self.use_claude:
            print("  Claude analysis: unavailable (using heuristics)")
        else:
            print("  Claude analysis: disabled (using heuristics)")

        # Step 1: Context Agent
        print("  [1/4] Gathering context...")
        context_result = self.gather_context(topic)
        context = context_result.context
        claude_analysis = context_result.claude_analysis
        print(
            f"        Found {len(context.patterns)} patterns, {len(context.components)} components"
        )
        if claude_analysis:
            print(
                f"        Claude insights: {len(claude_analysis.code_insights)} insights, "
                f"{len(claude_analysis.semantic_patterns)} semantic patterns"
            )

        if not context.patterns and not context.components:
            print(f"  Warning: No patterns or components found for topic '{topic}'")
            result["issues"].append(f"No patterns or components found for topic '{topic}'")

        # Step 2: Draft Agent
        print("  [2/4] Generating draft...")
        draft = self.generate_draft(context, doc_type, claude_analysis)
        print(f"        Generated: {draft.title}")
        if "claude-generated" in str(draft.sources):
            print("        Source: Claude-generated")

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
        description="Generate documentation from codebase analysis (4-agent pipeline with Claude AI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list-topics                    # List available topics
  %(prog)s --topic auth --type status-quo   # Generate auth status quo docs (with Claude)
  %(prog)s --topic auth --type pattern      # Generate pattern docs
  %(prog)s --all                            # Generate all pattern docs
  %(prog)s --all --dry-run                  # Preview without saving
  %(prog)s --topic auth --no-claude         # Use heuristic-only mode (faster)
  %(prog)s --topic auth --verbose           # Show Claude analysis progress

Note: For best practice research, use the adr-researcher tool instead.
        """,
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=Path.cwd(),
        help="Project root (default: current working directory)",
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

    parser.add_argument(
        "--no-claude",
        action="store_true",
        help="Disable Claude analysis, use heuristic mode only (faster, no API calls)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output including Claude analysis progress",
    )

    args = parser.parse_args()

    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)

    generator = DocumentationGenerator(
        project_root,
        args.output,
        use_claude=not args.no_claude,
        verbose=args.verbose,
    )

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
