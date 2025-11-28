#!/usr/bin/env python3
"""
LLM Documentation Generator - Full 6-Agent Pipeline

Generates and maintains documentation using a multi-agent pipeline:
1. Context Agent: Analyzes code structure and patterns
2. Draft Agent: Generates initial documentation
3. Review Agent: Validates accuracy and completeness
4. External Validation Agent: Researches best practices from authoritative sources
5. Revise Agent: Incorporates external feedback into documentation
6. Output Agent: Formats and saves documentation

Per ADR: LLM Documentation Index Strategy (Phases 4 & 5)

Usage:
  # Generate status quo docs for a component
  python3 doc-generator.py --type status-quo --topic auth

  # Generate best practice docs with external validation
  python3 doc-generator.py --type best-practice --topic "JWT security"

  # Skip external validation (faster, offline)
  python3 doc-generator.py --type best-practice --topic auth --skip-external

  # List all detected patterns for documentation
  python3 doc-generator.py --list-topics

  # Generate docs for all detected patterns
  python3 doc-generator.py --all

  # Research best practices for a topic (standalone)
  python3 doc-generator.py --research security
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


@dataclass
class ExternalResearch:
    """External research results from the External Validation Agent."""

    topic: str
    best_practices: list[dict] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    researched_at: str = ""


class ExternalValidator:
    """External Validation Agent - Researches best practices from authoritative sources."""

    # Known authoritative sources by topic
    AUTHORITATIVE_SOURCES = {
        "security": [
            {
                "name": "OWASP Cheat Sheet Series",
                "url": "https://cheatsheetseries.owasp.org/",
                "type": "standards",
            },
            {
                "name": "NIST Cybersecurity",
                "url": "https://www.nist.gov/cybersecurity",
                "type": "standards",
            },
        ],
        "auth": [
            {
                "name": "OWASP Authentication Cheat Sheet",
                "url": "https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html",
                "type": "standards",
            },
            {
                "name": "OWASP Session Management",
                "url": "https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html",
                "type": "standards",
            },
        ],
        "config": [
            {
                "name": "12 Factor App - Config",
                "url": "https://12factor.net/config",
                "type": "best_practice",
            },
        ],
        "testing": [
            {
                "name": "Python Testing Best Practices",
                "url": "https://docs.pytest.org/en/stable/explanation/goodpractices.html",
                "type": "official_docs",
            },
        ],
        "notification": [
            {
                "name": "Slack API Best Practices",
                "url": "https://api.slack.com/best-practices",
                "type": "official_docs",
            },
        ],
    }

    # Well-known best practices by topic (curated knowledge)
    KNOWN_BEST_PRACTICES = {
        "security": [
            {"practice": "Never store secrets in code or version control", "source": "OWASP"},
            {
                "practice": "Use environment variables for sensitive configuration",
                "source": "12 Factor",
            },
            {"practice": "Validate and sanitize all user input", "source": "OWASP"},
            {"practice": "Use parameterized queries to prevent SQL injection", "source": "OWASP"},
            {
                "practice": "Implement proper error handling without exposing internals",
                "source": "OWASP",
            },
            {"practice": "Use HTTPS for all communications", "source": "OWASP"},
            {"practice": "Implement rate limiting on APIs", "source": "OWASP"},
            {
                "practice": "Keep dependencies updated and scan for vulnerabilities",
                "source": "NIST",
            },
        ],
        "auth": [
            {
                "practice": "Use strong, adaptive hashing for passwords (bcrypt, Argon2)",
                "source": "OWASP",
            },
            {
                "practice": "Implement multi-factor authentication for sensitive operations",
                "source": "NIST",
            },
            {
                "practice": "Use short-lived tokens with secure refresh mechanisms",
                "source": "OWASP",
            },
            {"practice": "Validate JWT signatures and all claims", "source": "RFC 7519"},
            {"practice": "Implement proper session invalidation on logout", "source": "OWASP"},
            {
                "practice": "Use secure, HttpOnly, SameSite cookies for session tokens",
                "source": "OWASP",
            },
            {"practice": "Implement account lockout after failed attempts", "source": "NIST"},
        ],
        "config": [
            {
                "practice": "Store config in environment variables, not in code",
                "source": "12 Factor",
            },
            {"practice": "Never commit secrets to version control", "source": "Industry Standard"},
            {
                "practice": "Use different config for dev, staging, production",
                "source": "12 Factor",
            },
            {"practice": "Validate all configuration on startup", "source": "Best Practice"},
            {"practice": "Provide sensible defaults where appropriate", "source": "Best Practice"},
            {"practice": "Document all configuration options", "source": "Best Practice"},
        ],
        "testing": [
            {
                "practice": "Write tests before or alongside code (TDD)",
                "source": "Industry Standard",
            },
            {"practice": "Aim for high coverage on critical paths", "source": "Best Practice"},
            {"practice": "Use fixtures and factories for test data", "source": "pytest"},
            {"practice": "Keep tests fast and independent", "source": "Best Practice"},
            {"practice": "Mock external dependencies", "source": "Best Practice"},
            {"practice": "Test edge cases and error conditions", "source": "Best Practice"},
        ],
        "notification": [
            {"practice": "Implement rate limiting to avoid API throttling", "source": "Slack API"},
            {"practice": "Use threading for related messages", "source": "Slack Best Practices"},
            {"practice": "Handle API errors gracefully with retries", "source": "Best Practice"},
            {
                "practice": "Avoid sending too many notifications (notification fatigue)",
                "source": "UX Best Practice",
            },
        ],
        "connector": [
            {
                "practice": "Implement retry logic with exponential backoff",
                "source": "Best Practice",
            },
            {"practice": "Use connection pooling for efficiency", "source": "Best Practice"},
            {"practice": "Handle timeouts gracefully", "source": "Best Practice"},
            {"practice": "Log requests and responses for debugging", "source": "Best Practice"},
            {
                "practice": "Use circuit breaker pattern for resilience",
                "source": "Resilience Patterns",
            },
        ],
        "sync": [
            {"practice": "Make sync operations idempotent", "source": "Best Practice"},
            {"practice": "Use optimistic locking to prevent conflicts", "source": "Best Practice"},
            {"practice": "Implement incremental sync where possible", "source": "Performance"},
            {"practice": "Track sync state to avoid reprocessing", "source": "Best Practice"},
            {"practice": "Handle partial failures gracefully", "source": "Resilience Patterns"},
        ],
    }

    # Anti-patterns by topic
    KNOWN_ANTI_PATTERNS = {
        "security": [
            "Storing passwords in plain text",
            "Using MD5 or SHA1 for password hashing",
            "Hardcoding secrets in source code",
            "Disabling SSL certificate verification",
            "Using eval() or exec() with user input",
            "Exposing stack traces in error messages",
        ],
        "auth": [
            "Rolling your own cryptography",
            "Using predictable session IDs",
            "Not invalidating sessions on logout",
            "Storing tokens in localStorage (XSS vulnerable)",
            "Using long-lived access tokens without refresh",
        ],
        "config": [
            "Committing .env files with secrets",
            "Hardcoding environment-specific values",
            "Not validating config on startup",
            "Using production credentials in development",
        ],
        "testing": [
            "Testing implementation details instead of behavior",
            "Having tests that depend on each other",
            "Not cleaning up test data",
            "Ignoring flaky tests",
            "Testing third-party code",
        ],
    }

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def research(self, topic: str, force_refresh: bool = False) -> ExternalResearch:
        """Research best practices for a topic."""
        # Check cache first
        if self.cache_dir and not force_refresh:
            cached = self._load_cache(topic)
            if cached:
                return cached

        research = ExternalResearch(
            topic=topic,
            researched_at=datetime.now(timezone.utc).isoformat(),
        )

        # Get known best practices
        topic_key = self._normalize_topic(topic)
        if topic_key in self.KNOWN_BEST_PRACTICES:
            research.best_practices = self.KNOWN_BEST_PRACTICES[topic_key]

        # Get known anti-patterns
        if topic_key in self.KNOWN_ANTI_PATTERNS:
            research.anti_patterns = self.KNOWN_ANTI_PATTERNS[topic_key]

        # Get authoritative sources
        if topic_key in self.AUTHORITATIVE_SOURCES:
            research.sources = self.AUTHORITATIVE_SOURCES[topic_key]

        # Try to fetch live content from sources (best effort)
        research = self._enrich_from_sources(research)

        # Cache the results
        if self.cache_dir:
            self._save_cache(topic, research)

        return research

    def _normalize_topic(self, topic: str) -> str:
        """Normalize topic name to match known keys."""
        topic_lower = topic.lower().strip()

        # Direct mappings
        mappings = {
            "authentication": "auth",
            "authorization": "auth",
            "jwt": "auth",
            "session": "auth",
            "configuration": "config",
            "settings": "config",
            "test": "testing",
            "tests": "testing",
            "slack": "notification",
            "alert": "notification",
            "api": "connector",
            "client": "connector",
            "synchronization": "sync",
        }

        if topic_lower in mappings:
            return mappings[topic_lower]

        # Check if topic contains a known key
        for key in self.KNOWN_BEST_PRACTICES:
            if key in topic_lower or topic_lower in key:
                return key

        return topic_lower

    def _enrich_from_sources(self, research: ExternalResearch) -> ExternalResearch:
        """Try to fetch additional info from authoritative sources."""
        for source in research.sources[:2]:  # Limit to first 2 sources
            try:
                # Simple fetch with timeout
                req = urllib.request.Request(
                    source["url"], headers={"User-Agent": "jib-doc-generator/1.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        source["accessible"] = True
                        source["last_checked"] = datetime.now(timezone.utc).isoformat()
            except (urllib.error.URLError, TimeoutError, Exception):
                source["accessible"] = False

        return research

    def _load_cache(self, topic: str) -> ExternalResearch | None:
        """Load cached research results."""
        if not self.cache_dir:
            return None

        cache_file = self.cache_dir / f"research-{self._normalize_topic(topic)}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                # Check if cache is less than 7 days old
                researched_at = datetime.fromisoformat(data.get("researched_at", "2000-01-01"))
                age = datetime.now(timezone.utc) - researched_at.replace(tzinfo=timezone.utc)
                if age.days < 7:
                    return ExternalResearch(**data)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _save_cache(self, topic: str, research: ExternalResearch):
        """Save research results to cache."""
        if not self.cache_dir:
            return

        cache_file = self.cache_dir / f"research-{self._normalize_topic(topic)}.json"
        data = {
            "topic": research.topic,
            "best_practices": research.best_practices,
            "anti_patterns": research.anti_patterns,
            "sources": research.sources,
            "gaps": research.gaps,
            "recommendations": research.recommendations,
            "researched_at": research.researched_at,
        }
        cache_file.write_text(json.dumps(data, indent=2))

    def generate_research_prompt(self, topic: str) -> str:
        """Generate a research prompt for manual or LLM-assisted research."""
        return f"""# Best Practice Research Task

## Topic: {topic}

## Research Questions:
1. What are the current industry best practices for {topic}?
2. Have these practices changed in the last 6 months?
3. What are common anti-patterns to avoid?
4. What do official documentation sources recommend?

## Sources to Check:
- Official documentation for relevant frameworks/libraries
- OWASP guidelines (if security-related)
- Recent conference talks or blog posts from framework authors
- Popular open-source projects implementing {topic}

## Output Format:
### Current Best Practices
- [List with citations]

### Anti-Patterns to Avoid
- [List with explanations]

### Our Current Approach
- [How does our code compare?]

### Recommendations
- [What should we change, if anything?]
"""


class DocumentationGenerator:
    """Full 6-agent documentation generation pipeline."""

    # Doc types we can generate
    DOC_TYPES = {
        "status-quo": "Descriptive documentation of current implementation",
        "best-practice": "Prescriptive guidelines based on best practices",
        "pattern": "Pattern documentation extracted from code",
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
        self.cache_dir = self.generated_dir / "research-cache"

        # Load existing indexes if available
        self.codebase_index = self._load_json("codebase.json")
        self.patterns_index = self._load_json("patterns.json")
        self.deps_index = self._load_json("dependencies.json")

        # Initialize external validator
        self.external_validator = ExternalValidator(self.cache_dir)

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
        elif doc_type == "best-practice":
            return self._draft_best_practice_skeleton(context)
        elif doc_type == "pattern":
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
            f"> Auto-generated by jib on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. "
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

    def _draft_best_practice_skeleton(self, context: DocContext) -> DraftDoc:
        """Generate skeleton for best practice docs (to be enriched by external validation)."""
        title = f"{context.topic.title()} Best Practices"
        sections = []
        sections.append(f"# {title}")
        sections.append("")
        sections.append(
            f"> Auto-generated by jib on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. "
            "Includes external best practice research."
        )
        sections.append("")

        # Placeholder for industry standards (filled by external validation)
        sections.append("## Industry Standards")
        sections.append("")
        sections.append("{{INDUSTRY_STANDARDS}}")
        sections.append("")

        # Our current approach
        sections.append("## Our Current Approach")
        sections.append("")
        if context.patterns:
            for pattern in context.patterns:
                sections.append(f"### {pattern['name'].replace('_', ' ').title()}")
                sections.append("")
                if pattern.get("description"):
                    sections.append(pattern["description"])
                    sections.append("")
                if pattern.get("conventions"):
                    sections.append("**Conventions:**")
                    for conv in pattern["conventions"]:
                        sections.append(f"- {conv}")
                    sections.append("")
        else:
            sections.append("*No patterns detected in codebase.*")
            sections.append("")

        # Placeholder for compliance (filled by revise agent)
        sections.append("## Compliance Checklist")
        sections.append("")
        sections.append("{{COMPLIANCE_CHECKLIST}}")
        sections.append("")

        # Placeholder for recommendations
        sections.append("## Recommendations")
        sections.append("")
        sections.append("{{RECOMMENDATIONS}}")
        sections.append("")

        # Sources
        sections.append("## Sources")
        sections.append("")
        sections.append("{{SOURCES}}")
        sections.append("")

        content = "\n".join(sections)
        return DraftDoc(
            title=title,
            content=content,
            doc_type="best-practice",
            sources=["patterns.json"],
        )

    def _draft_pattern(self, context: DocContext) -> DraftDoc:
        """Generate pattern documentation for detected code patterns."""
        title = f"{context.topic.title()} Pattern"
        sections = []
        sections.append(f"# {title}")
        sections.append("")
        sections.append(f"> Auto-generated by jib on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.")
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

        # Check for unfilled placeholders
        if "{{" in draft.content:
            suggestions.append("Document contains template placeholders to be filled")

        lines = draft.content.split("\n")
        prev_was_header = False
        for line in lines:
            if line.startswith("#"):
                if prev_was_header:
                    issues.append(f"Empty section before: {line}")
                prev_was_header = True
            elif line.strip() and not line.startswith("{{"):
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
    # Agent 4: External Validation Agent - Researches best practices
    # =========================================================================
    def validate_externally(self, topic: str, context: DocContext) -> ExternalResearch:
        """External Validation Agent: Research best practices from authoritative sources."""
        research = self.external_validator.research(topic)

        # Identify gaps between our practices and best practices
        our_conventions = {c.lower() for c in context.conventions}
        for bp in research.best_practices:
            practice = bp.get("practice", "").lower()
            # Check if any of our conventions align with this practice
            aligned = any(conv in practice or practice in conv for conv in our_conventions)
            if not aligned:
                research.gaps.append(f"Consider: {bp.get('practice')} ({bp.get('source')})")

        # Generate recommendations based on gaps
        if research.gaps:
            research.recommendations.append(
                "Review the identified gaps against current implementation"
            )
        if research.anti_patterns:
            research.recommendations.append("Audit codebase for listed anti-patterns")

        return research

    # =========================================================================
    # Agent 5: Revise Agent - Incorporates external feedback
    # =========================================================================
    def revise_draft(
        self, draft: DraftDoc, research: ExternalResearch, context: DocContext
    ) -> DraftDoc:
        """Revise Agent: Incorporate external validation feedback into documentation."""
        content = draft.content

        # Fill in industry standards section
        if research.best_practices:
            standards_lines = []
            standards_lines.append("Industry best practices for this topic:")
            standards_lines.append("")
            for bp in research.best_practices:
                practice = bp.get("practice", "")
                source = bp.get("source", "")
                standards_lines.append(f"- **{practice}** ({source})")
            standards_lines.append("")

            if research.anti_patterns:
                standards_lines.append("### Anti-Patterns to Avoid")
                standards_lines.append("")
                for ap in research.anti_patterns:
                    standards_lines.append(f"- {ap}")
                standards_lines.append("")

            content = content.replace("{{INDUSTRY_STANDARDS}}", "\n".join(standards_lines))
        else:
            content = content.replace(
                "{{INDUSTRY_STANDARDS}}", "*No specific industry standards found for this topic.*\n"
            )

        # Fill in compliance checklist
        if research.best_practices:
            compliance_lines = []
            compliance_lines.append("| Practice | Status | Notes |")
            compliance_lines.append("|----------|--------|-------|")

            for bp in research.best_practices[:8]:  # Limit to 8 practices
                practice = bp.get("practice", "")[:60]
                # Check if we have a matching convention
                status = "⚠️ Review"
                for conv in context.conventions:
                    if any(word in conv.lower() for word in practice.lower().split()[:3]):
                        status = "✅ Aligned"
                        break
                compliance_lines.append(f"| {practice} | {status} | |")

            content = content.replace("{{COMPLIANCE_CHECKLIST}}", "\n".join(compliance_lines))
        else:
            content = content.replace(
                "{{COMPLIANCE_CHECKLIST}}",
                "*Compliance checklist will be generated after research.*\n",
            )

        # Fill in recommendations
        if research.gaps or research.recommendations:
            rec_lines = []
            if research.gaps:
                rec_lines.append("### Gaps Identified")
                rec_lines.append("")
                for gap in research.gaps[:5]:  # Limit to 5 gaps
                    rec_lines.append(f"- {gap}")
                rec_lines.append("")

            if research.recommendations:
                rec_lines.append("### Action Items")
                rec_lines.append("")
                for rec in research.recommendations:
                    rec_lines.append(f"- {rec}")

            content = content.replace("{{RECOMMENDATIONS}}", "\n".join(rec_lines))
        else:
            content = content.replace(
                "{{RECOMMENDATIONS}}", "No specific recommendations at this time.\n"
            )

        # Fill in sources
        if research.sources:
            source_lines = []
            for source in research.sources:
                name = source.get("name", "Unknown")
                url = source.get("url", "")
                source_type = source.get("type", "reference")
                accessible = source.get("accessible", None)
                status = ""
                if accessible is not None:
                    status = " ✓" if accessible else " (unavailable)"
                source_lines.append(f"- [{name}]({url}) - {source_type}{status}")
            content = content.replace("{{SOURCES}}", "\n".join(source_lines))
        else:
            content = content.replace(
                "{{SOURCES}}", "- Internal codebase analysis\n- Industry best practices\n"
            )

        # Update sources list
        sources = draft.sources.copy()
        for source in research.sources:
            sources.append(f"{source.get('name')}: {source.get('url')}")

        return DraftDoc(
            title=draft.title,
            content=content,
            doc_type=draft.doc_type,
            sources=sources,
            warnings=[],  # Clear warnings after revision
        )

    # =========================================================================
    # Agent 6: Output Agent - Formats and saves documentation
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
        skip_external: bool = False,
    ) -> dict[str, Any]:
        """Run the full 6-agent documentation generation pipeline."""
        result = {
            "topic": topic,
            "doc_type": doc_type,
            "success": False,
            "output_path": None,
            "issues": [],
            "suggestions": [],
            "research": None,
        }

        use_external = doc_type == "best-practice" and not skip_external
        total_steps = 6 if use_external else 4

        print(f"Generating {doc_type} documentation for: {topic}")

        # Step 1: Context Agent
        print(f"  [1/{total_steps}] Gathering context...")
        context = self.gather_context(topic)
        print(
            f"        Found {len(context.patterns)} patterns, {len(context.components)} components"
        )

        if not context.patterns and not context.components:
            print(f"  Warning: No patterns or components found for topic '{topic}'")
            result["issues"].append(f"No patterns or components found for topic '{topic}'")

        # Step 2: Draft Agent
        print(f"  [2/{total_steps}] Generating draft...")
        draft = self.generate_draft(context, doc_type)
        print(f"        Generated: {draft.title}")

        # Step 3: Review Agent
        print(f"  [3/{total_steps}] Reviewing draft...")
        review = self.review_draft(draft, context)

        if use_external:
            # Step 4: External Validation Agent
            print(f"  [4/{total_steps}] Researching external best practices...")
            research = self.validate_externally(topic, context)
            result["research"] = {
                "best_practices": len(research.best_practices),
                "anti_patterns": len(research.anti_patterns),
                "sources": len(research.sources),
                "gaps": len(research.gaps),
            }
            print(
                f"        Found {len(research.best_practices)} best practices, {len(research.gaps)} gaps"
            )

            # Step 5: Revise Agent
            print(f"  [5/{total_steps}] Revising with external feedback...")
            draft = self.revise_draft(draft, research, context)
            print("        Draft revised with external validation")

            # Re-review after revision
            review = self.review_draft(draft, context)

        result["issues"] = review.issues
        result["suggestions"] = review.suggestions

        if review.approved:
            print("        Review: APPROVED")
        else:
            print(f"        Review: {len(review.issues)} issues found")

        # Final step: Output Agent
        step_num = total_steps
        if dry_run:
            print(f"  [{step_num}/{total_steps}] Dry run - not saving")
            print("\n--- Generated Content Preview ---")
            print(draft.content[:1500])
            if len(draft.content) > 1500:
                print(f"\n... ({len(draft.content) - 1500} more characters)")
        else:
            print(f"  [{step_num}/{total_steps}] Saving documentation...")
            output_path = self.save_documentation(draft, review)
            result["output_path"] = str(output_path)
            print(f"        Saved to: {output_path}")
            result["success"] = True

        return result

    def generate_all(
        self,
        doc_type: str = "status-quo",
        dry_run: bool = False,
        skip_external: bool = False,
    ) -> list[dict]:
        """Generate documentation for all detected patterns."""
        results = []
        topics = self.list_available_topics()

        pattern_topics = [t for t in topics if t["source"] == "detected_pattern"]

        print(f"Generating {doc_type} docs for {len(pattern_topics)} detected patterns\n")

        for topic_info in pattern_topics:
            result = self.generate(topic_info["name"], doc_type, dry_run, skip_external)
            results.append(result)
            print()

        successful = sum(1 for r in results if r["success"])
        print(f"\nSummary: {successful}/{len(results)} documents generated successfully")

        return results

    def research_topic(self, topic: str) -> ExternalResearch:
        """Standalone research for a topic."""
        return self.external_validator.research(topic, force_refresh=True)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate documentation using 6-agent pipeline with external validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list-topics                         # List available topics
  %(prog)s --topic auth --type status-quo        # Generate auth status quo docs
  %(prog)s --topic security --type best-practice # Best practice docs with research
  %(prog)s --topic auth --type best-practice --skip-external  # Skip web research
  %(prog)s --all                                 # Generate all pattern docs
  %(prog)s --all --dry-run                       # Preview without saving
  %(prog)s --research security                   # Research best practices only
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
        choices=["status-quo", "best-practice", "pattern"],
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
        "--skip-external",
        action="store_true",
        help="Skip external validation (faster, works offline)",
    )

    parser.add_argument(
        "--research",
        "-r",
        metavar="TOPIC",
        help="Research best practices for a topic (standalone)",
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

    # Research mode
    if args.research:
        print(f"Researching best practices for: {args.research}\n")
        research = generator.research_topic(args.research)

        if args.json:
            print(
                json.dumps(
                    {
                        "topic": research.topic,
                        "best_practices": research.best_practices,
                        "anti_patterns": research.anti_patterns,
                        "sources": research.sources,
                        "gaps": research.gaps,
                        "recommendations": research.recommendations,
                        "researched_at": research.researched_at,
                    },
                    indent=2,
                )
            )
        else:
            print("## Best Practices")
            for bp in research.best_practices:
                print(f"  - {bp.get('practice')} ({bp.get('source')})")
            print("\n## Anti-Patterns")
            for ap in research.anti_patterns:
                print(f"  - {ap}")
            print("\n## Sources")
            for src in research.sources:
                print(f"  - {src.get('name')}: {src.get('url')}")

            # Also print research prompt
            print("\n## Research Prompt (for manual/LLM research)")
            print("-" * 40)
            print(generator.external_validator.generate_research_prompt(args.research))
        return

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
        results = generator.generate_all(args.type, args.dry_run, args.skip_external)
        if args.json:
            print(json.dumps(results, indent=2))
        return

    # Generate single topic
    if args.topic:
        result = generator.generate(args.topic, args.type, args.dry_run, args.skip_external)
        if args.json:
            print(json.dumps(result, indent=2))
        return

    # No action specified
    parser.print_help()
    print("\nError: Specify --topic, --all, --research, or --list-topics", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
