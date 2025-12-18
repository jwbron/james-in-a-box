#!/usr/bin/env python3
"""
Context Gatherer - Collects relevant context for JIRA ticket analysis.

Gathers:
- Related codebase files (via keyword/path matching)
- Relevant documentation
- Similar past tickets/PRs
- Error logs from ticket descriptions
- Repository-specific guidelines (CLAUDE.md)

Part of the JIRA Ticket Triage Workflow (ADR).
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GatheredContext:
    """Container for gathered context from various sources."""

    # Ticket information
    ticket_key: str
    ticket_title: str
    ticket_description: str
    ticket_labels: list[str] = field(default_factory=list)
    ticket_comments: list[str] = field(default_factory=list)

    # Related code
    related_files: list[dict] = field(default_factory=list)  # [{path, relevance, snippet}]

    # Documentation
    related_docs: list[dict] = field(default_factory=list)  # [{path, title, relevance}]

    # Similar tickets
    similar_tickets: list[dict] = field(default_factory=list)  # [{key, title, similarity}]

    # Error information extracted from ticket
    error_messages: list[str] = field(default_factory=list)
    stack_traces: list[str] = field(default_factory=list)

    # Repository context
    repo_guidelines: str = ""  # CLAUDE.md contents

    # Metadata
    total_tokens_estimate: int = 0
    gathering_time_seconds: float = 0.0

    def to_prompt_context(self) -> str:
        """Format gathered context for LLM consumption."""
        sections = []

        # Ticket information
        sections.append(f"## Ticket: {self.ticket_key}")
        sections.append(f"**Title:** {self.ticket_title}")
        sections.append(f"**Labels:** {', '.join(self.ticket_labels) if self.ticket_labels else 'None'}")
        sections.append("")
        sections.append("### Description")
        sections.append(self.ticket_description or "*No description*")
        sections.append("")

        # Comments
        if self.ticket_comments:
            sections.append("### Comments")
            for i, comment in enumerate(self.ticket_comments[:5], 1):  # Limit to 5 comments
                sections.append(f"**Comment {i}:**")
                sections.append(comment[:500])  # Truncate long comments
                sections.append("")

        # Error information
        if self.error_messages or self.stack_traces:
            sections.append("### Error Information")
            if self.error_messages:
                sections.append("**Error Messages:**")
                for msg in self.error_messages[:3]:
                    sections.append(f"- {msg}")
            if self.stack_traces:
                sections.append("\n**Stack Traces:**")
                for trace in self.stack_traces[:2]:
                    sections.append(f"```\n{trace[:1000]}\n```")
            sections.append("")

        # Related code files
        if self.related_files:
            sections.append("### Related Code Files")
            for f in self.related_files[:10]:  # Limit to top 10
                sections.append(f"- **{f['path']}** (relevance: {f.get('relevance', 'unknown')})")
                if f.get("snippet"):
                    sections.append(f"  ```\n  {f['snippet'][:300]}\n  ```")
            sections.append("")

        # Related documentation
        if self.related_docs:
            sections.append("### Related Documentation")
            for doc in self.related_docs[:5]:
                sections.append(f"- **{doc.get('title', doc['path'])}** - {doc['path']}")
            sections.append("")

        # Similar tickets
        if self.similar_tickets:
            sections.append("### Similar Past Tickets")
            for ticket in self.similar_tickets[:5]:
                sections.append(f"- **{ticket['key']}**: {ticket['title']}")
            sections.append("")

        # Repository guidelines
        if self.repo_guidelines:
            sections.append("### Repository Guidelines (CLAUDE.md)")
            sections.append(self.repo_guidelines[:2000])  # Truncate if needed
            sections.append("")

        return "\n".join(sections)


class ContextGatherer:
    """Gathers relevant context for JIRA ticket analysis."""

    def __init__(
        self,
        repos_dir: Path | str | None = None,
        jira_dir: Path | str | None = None,
        max_tokens: int = 50000,
        timeout_seconds: int = 60,
    ):
        """Initialize context gatherer.

        Args:
            repos_dir: Base directory containing repositories (default: ~/khan/)
            jira_dir: Directory containing synced JIRA tickets (default: ~/context-sync/jira/)
            max_tokens: Maximum tokens for gathered context (cost control)
            timeout_seconds: Timeout for context gathering operations
        """
        self.repos_dir = Path(repos_dir or os.path.expanduser("~/khan"))
        self.jira_dir = Path(jira_dir or os.path.expanduser("~/context-sync/jira"))
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

        # Enabled repos (configured via environment)
        enabled_repos_env = os.environ.get("JIB_TRIAGE_ENABLED_REPOS", "jwbron/james-in-a-box")
        self.enabled_repos = [r.strip().split("/")[-1] for r in enabled_repos_env.split(",")]

    def gather_context(self, ticket: dict) -> GatheredContext:
        """Gather all relevant context for a ticket.

        Args:
            ticket: Parsed ticket data with keys: key, title, description, labels, comments

        Returns:
            GatheredContext with all gathered information
        """
        import time

        start_time = time.time()

        context = GatheredContext(
            ticket_key=ticket.get("key", ""),
            ticket_title=ticket.get("title", ""),
            ticket_description=ticket.get("description", ""),
            ticket_labels=ticket.get("labels", []),
            ticket_comments=ticket.get("comments", []),
        )

        # Extract error information from ticket
        self._extract_error_info(context)

        # Extract keywords for searching
        keywords = self._extract_keywords(context)

        # Gather related code files
        context.related_files = self._find_related_code(keywords)

        # Gather related documentation
        context.related_docs = self._find_related_docs(keywords)

        # Find similar past tickets
        context.similar_tickets = self._find_similar_tickets(context.ticket_key, keywords)

        # Load repository guidelines
        context.repo_guidelines = self._load_repo_guidelines()

        # Calculate token estimate (rough approximation: 1 token ~= 4 chars)
        full_context = context.to_prompt_context()
        context.total_tokens_estimate = len(full_context) // 4

        context.gathering_time_seconds = time.time() - start_time

        return context

    def _extract_keywords(self, context: GatheredContext) -> list[str]:
        """Extract searchable keywords from ticket content."""
        keywords = set()

        # Extract from title
        title_words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", context.ticket_title)
        keywords.update(w.lower() for w in title_words if len(w) > 3)

        # Extract from description
        desc_words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", context.ticket_description)
        keywords.update(w.lower() for w in desc_words if len(w) > 3)

        # Extract file paths mentioned
        file_paths = re.findall(r"[\w/.-]+\.(py|ts|js|go|md|yaml|json)", context.ticket_description)
        keywords.update(file_paths)

        # Extract class/function names (CamelCase or snake_case)
        identifiers = re.findall(r"\b[A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)*\b", context.ticket_description)
        keywords.update(identifiers)

        snake_case = re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", context.ticket_description)
        keywords.update(snake_case)

        # Filter out common words
        common_words = {
            "the",
            "and",
            "for",
            "with",
            "that",
            "this",
            "from",
            "have",
            "been",
            "should",
            "would",
            "could",
            "when",
            "where",
            "which",
            "there",
            "their",
            "about",
            "into",
            "more",
            "some",
            "than",
            "them",
            "then",
            "these",
            "they",
            "what",
            "will",
            "your",
            "need",
            "added",
            "update",
            "updated",
            "change",
            "changed",
            "please",
            "thanks",
        }
        keywords -= common_words

        return list(keywords)[:20]  # Limit to top 20 keywords

    def _extract_error_info(self, context: GatheredContext) -> None:
        """Extract error messages and stack traces from ticket content."""
        full_text = f"{context.ticket_description}\n" + "\n".join(context.ticket_comments)

        # Extract error messages (common patterns)
        error_patterns = [
            r"(?:Error|Exception|Failed|Failure):\s*(.+?)(?:\n|$)",
            r"(?:error|exception|failed|failure):\s*(.+?)(?:\n|$)",
            r"Traceback.*?(?=\n\n|\Z)",
        ]

        for pattern in error_patterns[:2]:  # Error messages
            matches = re.findall(pattern, full_text, re.IGNORECASE)
            context.error_messages.extend(matches[:5])

        # Extract stack traces
        stack_pattern = r"(?:Traceback \(most recent call last\):.*?(?:\n\n|\Z)|at [\w.$]+\([^)]*\)(?:\n\s*at.*)*)"
        stack_matches = re.findall(stack_pattern, full_text, re.DOTALL)
        context.stack_traces.extend(stack_matches[:3])

    def _find_related_code(self, keywords: list[str]) -> list[dict]:
        """Find code files related to the ticket keywords."""
        related_files = []

        if not keywords:
            return related_files

        for repo_name in self.enabled_repos:
            repo_path = self.repos_dir / repo_name
            if not repo_path.exists():
                continue

            # Search for keywords in code files
            for keyword in keywords[:10]:  # Limit keyword searches
                try:
                    result = subprocess.run(
                        [
                            "grep",
                            "-rl",
                            "--include=*.py",
                            "--include=*.ts",
                            "--include=*.js",
                            "--include=*.go",
                            keyword,
                            str(repo_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        for file_path in result.stdout.strip().split("\n")[:5]:
                            if file_path and file_path not in [f["path"] for f in related_files]:
                                # Get a snippet of the match
                                snippet = self._get_file_snippet(file_path, keyword)
                                related_files.append(
                                    {"path": file_path, "relevance": f"contains '{keyword}'", "snippet": snippet}
                                )
                except (subprocess.TimeoutExpired, Exception):
                    continue

            if len(related_files) >= 20:
                break

        return related_files[:20]

    def _get_file_snippet(self, file_path: str, keyword: str, context_lines: int = 2) -> str:
        """Get a snippet of the file around the keyword match."""
        try:
            result = subprocess.run(
                ["grep", "-n", "-B", str(context_lines), "-A", str(context_lines), keyword, file_path],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return result.stdout[:500]  # Truncate long snippets
        except (subprocess.TimeoutExpired, Exception):
            pass
        return ""

    def _find_related_docs(self, keywords: list[str]) -> list[dict]:
        """Find documentation files related to the keywords."""
        related_docs = []

        for repo_name in self.enabled_repos:
            repo_path = self.repos_dir / repo_name
            docs_dirs = [repo_path / "docs", repo_path / "README.md"]

            for docs_dir in docs_dirs:
                if not docs_dir.exists():
                    continue

                if docs_dir.is_file():
                    # README.md
                    related_docs.append({"path": str(docs_dir), "title": "README", "relevance": "repository readme"})
                else:
                    # Search in docs directory
                    for keyword in keywords[:5]:
                        try:
                            result = subprocess.run(
                                ["grep", "-rl", "--include=*.md", keyword, str(docs_dir)],
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if result.returncode == 0:
                                for doc_path in result.stdout.strip().split("\n")[:3]:
                                    if doc_path and doc_path not in [d["path"] for d in related_docs]:
                                        title = Path(doc_path).stem.replace("-", " ").replace("_", " ").title()
                                        related_docs.append(
                                            {"path": doc_path, "title": title, "relevance": f"contains '{keyword}'"}
                                        )
                        except (subprocess.TimeoutExpired, Exception):
                            continue

        return related_docs[:10]

    def _find_similar_tickets(self, current_key: str, keywords: list[str]) -> list[dict]:
        """Find similar past tickets based on keywords."""
        similar_tickets = []

        if not self.jira_dir.exists():
            return similar_tickets

        for ticket_file in self.jira_dir.glob("*.md"):
            ticket_key = ticket_file.stem.split("_")[0]
            if ticket_key == current_key:
                continue

            try:
                content = ticket_file.read_text()
                title_match = re.search(r"^#\s*(.+)$", content, re.MULTILINE)
                title = title_match.group(1) if title_match else ticket_file.stem

                # Calculate simple keyword overlap
                content_lower = content.lower()
                matches = sum(1 for kw in keywords if kw.lower() in content_lower)

                if matches >= 2:  # At least 2 keyword matches
                    similar_tickets.append({"key": ticket_key, "title": title, "similarity": matches})
            except Exception:
                continue

        # Sort by similarity score
        similar_tickets.sort(key=lambda x: x["similarity"], reverse=True)
        return similar_tickets[:5]

    def _load_repo_guidelines(self) -> str:
        """Load repository-specific guidelines from CLAUDE.md files."""
        guidelines = []

        for repo_name in self.enabled_repos:
            repo_path = self.repos_dir / repo_name
            claude_md = repo_path / "CLAUDE.md"

            if claude_md.exists():
                try:
                    content = claude_md.read_text()
                    guidelines.append(f"## {repo_name} Guidelines\n\n{content}")
                except Exception:
                    pass

        return "\n\n---\n\n".join(guidelines) if guidelines else ""


# For direct testing
if __name__ == "__main__":
    gatherer = ContextGatherer()
    test_ticket = {
        "key": "INFRA-1234",
        "title": "Fix typo in slack-receiver.py",
        "description": "The error message says 'recieved' instead of 'received'",
        "labels": ["jib", "bug"],
        "comments": [],
    }
    context = gatherer.gather_context(test_ticket)
    print(context.to_prompt_context())
