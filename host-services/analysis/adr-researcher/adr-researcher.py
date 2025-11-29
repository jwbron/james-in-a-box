#!/usr/bin/env python3
"""
ADR Researcher - Research-Based ADR Workflow Tool

Implements Phase 6 of ADR-LLM-Documentation-Index-Strategy: PR-Based Research Workflow.

This tool researches ADRs via web search and outputs findings as PRs or comments.
It runs on the host (NOT in the container) and uses the jib command to spawn
Claude-powered research agents inside containers.

Workflows:
1. --scope open-prs: Research open ADR PRs and post comments
2. --scope merged: Research merged/implemented ADRs and create update PRs
3. --generate "topic": Generate new ADRs from research
4. --review path: Review draft ADRs against current research

Usage:
  # Research all open ADR PRs and post comments
  adr-researcher --scope open-prs

  # Research all merged/implemented ADRs and create update PRs
  adr-researcher --scope merged

  # Generate a new ADR from research on a topic
  adr-researcher --generate "MCP Server Security Model"

  # Review and validate an existing ADR with current research
  adr-researcher --review docs/adr/proposed/ADR-New-Feature.md

  # Research specific ADR topic (output as markdown report)
  adr-researcher --scope topic --query "Docker sandbox isolation" --report-only
"""

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml


# Rate limiting configuration
RATE_LIMIT_DELAY = 0.5  # 500ms between API calls


@dataclass
class ResearchSource:
    """A source reference from research."""

    url: str
    title: str
    summary: str = ""
    date: str | None = None  # When the source was published


@dataclass
class KeyFinding:
    """A key finding from research."""

    topic: str
    finding: str
    confidence: Literal["high", "medium", "low"] = "medium"
    sources: list[str] = field(default_factory=list)  # URLs supporting this finding


@dataclass
class IndustryAdoption:
    """Industry adoption information for a technology/approach."""

    organization: str
    approach: str
    notes: str = ""
    source_url: str | None = None


@dataclass
class Recommendation:
    """An actionable recommendation from research."""

    recommendation: str
    rationale: str
    priority: Literal["high", "medium", "low"] = "medium"
    effort: Literal["low", "medium", "high"] | None = None


@dataclass
class ResearchResult:
    """Structured result from ADR research.

    This dataclass provides typed, validated output from Claude's research
    operations. It enables:
    - IDE autocomplete for downstream consumers
    - Runtime validation of research quality
    - Consistent output format guarantees across all research task types
    """

    success: bool
    query: str  # The research query or ADR title
    summary: str = ""  # 2-3 sentence overview
    sources: list[ResearchSource] = field(default_factory=list)
    key_findings: list[KeyFinding] = field(default_factory=list)
    industry_adoption: list[IndustryAdoption] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)
    raw_output: str = ""  # Full Claude output for debugging
    error: str | None = None
    pr_url: str | None = None  # If a PR was created
    pr_number: int | None = None  # If commenting on a PR


@dataclass
class ADRInfo:
    """Information about an ADR."""

    path: Path
    title: str
    status: str  # proposed, in-progress, implemented, not-implemented
    topics: list[str] = field(default_factory=list)
    pr_number: int | None = None
    pr_url: str | None = None
    content: str = ""


def load_config() -> dict:
    """Load repository configuration.

    Returns dict with:
        - writable_repos: List of repos jib can modify
        - github_username: Configured GitHub username
    """
    config_paths = [
        Path.home() / "khan" / "james-in-a-box" / "config" / "repositories.yaml",
        Path(__file__).parent.parent.parent.parent / "config" / "repositories.yaml",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    return yaml.safe_load(f)
            except yaml.YAMLError as e:
                print(f"Warning: Failed to parse {config_path}: {e}")
                continue

    return {"writable_repos": [], "github_username": "jib"}


def gh_json(args: list[str]) -> dict | list | None:
    """Run gh CLI command and return JSON output."""
    time.sleep(RATE_LIMIT_DELAY)
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        print(f"  gh command failed: {' '.join(args)}")
        if hasattr(e, "stderr"):
            print(f"  stderr: {e.stderr}")
        return None


def utc_now_iso() -> str:
    """Get current UTC time in ISO format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ADRResearcher:
    """Main ADR research orchestrator.

    This class handles finding ADRs, invoking jib for research, and
    outputting results as PRs or comments.
    """

    def __init__(self, project_root: Path | None = None):
        self.config = load_config()
        self.project_root = project_root or Path(__file__).parent.parent.parent.parent.resolve()
        self.adr_dir = self.project_root / "docs" / "adr"

    def find_adrs_by_status(
        self, status: Literal["implemented", "in-progress", "not-implemented", "proposed"]
    ) -> list[ADRInfo]:
        """Find ADRs by their status directory."""
        status_dir = self.adr_dir / status
        if not status_dir.exists():
            return []

        adrs = []
        for md_file in status_dir.glob("ADR-*.md"):
            content = md_file.read_text()
            title = self._extract_title(content)
            topics = self._extract_topics(content)
            adrs.append(
                ADRInfo(
                    path=md_file,
                    title=title,
                    status=status,
                    topics=topics,
                    content=content,
                )
            )
        return adrs

    def find_open_adr_prs(self) -> list[ADRInfo]:
        """Find open PRs that modify ADR files."""
        adrs = []
        for repo in self.config.get("writable_repos", []):
            prs = gh_json(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--json",
                    "number,title,url,headRefName,files",
                ]
            )
            if not prs:
                continue

            for pr in prs:
                files = pr.get("files", [])
                adr_files = [
                    f
                    for f in files
                    if f.get("path", "").startswith("docs/adr/")
                    and f.get("path", "").endswith(".md")
                ]
                if adr_files:
                    for adr_file in adr_files:
                        adr_path = self.project_root / adr_file["path"]
                        content = adr_path.read_text() if adr_path.exists() else ""
                        title = self._extract_title(content) if content else pr["title"]
                        adrs.append(
                            ADRInfo(
                                path=adr_path,
                                title=title,
                                status="proposed",
                                topics=self._extract_topics(content) if content else [],
                                pr_number=pr["number"],
                                pr_url=pr["url"],
                                content=content,
                            )
                        )
        return adrs

    def _extract_title(self, content: str) -> str:
        """Extract title from ADR content."""
        for line in content.split("\n"):
            if line.startswith("# "):
                return line[2:].strip()
        return "Untitled ADR"

    def _extract_topics(self, content: str) -> list[str]:
        """Extract key topics/keywords from ADR content."""
        topics = []
        content_lower = content.lower()

        # Common technology/pattern keywords to look for
        keywords = [
            "mcp",
            "docker",
            "slack",
            "github",
            "llm",
            "agent",
            "security",
            "authentication",
            "deployment",
            "terraform",
            "gcp",
            "aws",
            "kubernetes",
            "api",
            "rest",
            "graphql",
            "database",
            "redis",
            "postgres",
            "testing",
            "ci/cd",
            "monitoring",
            "logging",
        ]

        for keyword in keywords:
            if keyword in content_lower:
                topics.append(keyword)

        return topics[:10]  # Limit to 10 topics

    def _parse_research_result(self, raw_result: dict, query: str) -> ResearchResult:
        """Parse raw jib output into structured ResearchResult.

        This method extracts structured data from Claude's markdown output,
        parsing sections like Sources, Key Findings, Recommendations, etc.

        Args:
            raw_result: Raw dict from jib subprocess (contains 'success', 'output', etc.)
            query: The research query or ADR title for context

        Returns:
            ResearchResult with parsed structured fields
        """
        if not raw_result or not raw_result.get("success"):
            return ResearchResult(
                success=False,
                query=query,
                error=raw_result.get("error", "Research failed") if raw_result else "No result",
                raw_output=raw_result.get("output", "") if raw_result else "",
            )

        output = raw_result.get("output", "")

        # Extract PR info if present
        pr_url = raw_result.get("pr_url")
        pr_number = raw_result.get("pr_number")

        # Parse structured content from markdown output
        sources = self._parse_sources(output)
        key_findings = self._parse_key_findings(output)
        industry_adoption = self._parse_industry_adoption(output)
        recommendations = self._parse_recommendations(output)
        anti_patterns = self._parse_anti_patterns(output)
        summary = self._parse_summary(output)

        return ResearchResult(
            success=True,
            query=query,
            summary=summary,
            sources=sources,
            key_findings=key_findings,
            industry_adoption=industry_adoption,
            recommendations=recommendations,
            anti_patterns=anti_patterns,
            raw_output=output,
            pr_url=pr_url,
            pr_number=pr_number,
        )

    def _parse_sources(self, content: str) -> list[ResearchSource]:
        """Parse source references from markdown content.

        Looks for patterns like:
        - [Title](URL) - Description
        - **Source:** [URL]
        """
        import re

        sources = []
        # Match markdown links: [Title](URL)
        # Optional: followed by " - description"
        link_pattern = re.compile(
            r'\[([^\]]+)\]\((https?://[^\)]+)\)(?:\s*[-–—]\s*(.+?))?(?:\n|$)',
            re.IGNORECASE
        )

        for match in link_pattern.finditer(content):
            title = match.group(1).strip()
            url = match.group(2).strip()
            summary = match.group(3).strip() if match.group(3) else ""

            # Skip internal/anchor links
            if url.startswith("#"):
                continue

            sources.append(ResearchSource(
                title=title,
                url=url,
                summary=summary,
            ))

        # Deduplicate by URL
        seen_urls = set()
        unique_sources = []
        for source in sources:
            if source.url not in seen_urls:
                seen_urls.add(source.url)
                unique_sources.append(source)

        return unique_sources[:20]  # Limit to 20 sources

    def _parse_key_findings(self, content: str) -> list[KeyFinding]:
        """Parse key findings from markdown content.

        Looks for patterns in "Key Findings" or similar sections.
        """
        import re

        findings = []

        # Find the Key Findings section
        findings_section = self._extract_section(content, [
            "Key Findings",
            "Findings",
            "Main Findings",
            "Research Findings",
        ])

        if not findings_section:
            return findings

        # Parse bullet points or numbered items
        # Match: ### [Topic]\n[Finding text]
        # Or: - **Topic:** Finding text
        # Or: 1. **Topic:** Finding text
        topic_pattern = re.compile(
            r'(?:^|\n)(?:#{1,4}\s+|\d+\.\s+|\*\s+|-\s+)(?:\*\*)?([^*\n:]+)(?:\*\*)?:?\s*([^\n]+)',
            re.MULTILINE
        )

        for match in topic_pattern.finditer(findings_section):
            topic = match.group(1).strip()
            finding = match.group(2).strip()

            if topic and finding and len(finding) > 10:  # Skip very short findings
                findings.append(KeyFinding(
                    topic=topic,
                    finding=finding,
                    confidence="medium",  # Default; could be parsed if in content
                ))

        return findings[:15]  # Limit to 15 findings

    def _parse_industry_adoption(self, content: str) -> list[IndustryAdoption]:
        """Parse industry adoption table from markdown content.

        Looks for tables with Organization/Project, Approach, Notes columns.
        """
        import re

        adoptions = []

        # Find the Industry Adoption section
        adoption_section = self._extract_section(content, [
            "Industry Adoption",
            "Adoption",
            "Industry Examples",
            "Real-World Examples",
        ])

        if not adoption_section:
            return adoptions

        # Parse markdown tables
        # Format: | Organization | Approach | Notes |
        table_row_pattern = re.compile(
            r'\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|',
            re.MULTILINE
        )

        for match in table_row_pattern.finditer(adoption_section):
            org = match.group(1).strip()
            approach = match.group(2).strip()
            notes = match.group(3).strip()

            # Skip header rows and separator rows
            if org.startswith("-") or org.lower() in ("organization", "project", "company"):
                continue

            if org and approach:
                adoptions.append(IndustryAdoption(
                    organization=org,
                    approach=approach,
                    notes=notes if notes != "..." else "",
                ))

        return adoptions[:10]  # Limit to 10 examples

    def _parse_recommendations(self, content: str) -> list[Recommendation]:
        """Parse recommendations from markdown content."""
        import re

        recommendations = []

        # Find the Recommendations section
        rec_section = self._extract_section(content, [
            "Recommendations",
            "Suggested Actions",
            "Action Items",
            "Next Steps",
        ])

        if not rec_section:
            return recommendations

        # Parse bullet points
        # Format: - Recommendation text
        # Or: 1. Recommendation text
        bullet_pattern = re.compile(
            r'(?:^|\n)(?:\d+\.\s+|\*\s+|-\s+)(.+?)(?=\n(?:\d+\.|\*|-)|$)',
            re.MULTILINE | re.DOTALL
        )

        for match in bullet_pattern.finditer(rec_section):
            rec_text = match.group(1).strip()

            # Clean up the recommendation
            rec_text = re.sub(r'\n\s+', ' ', rec_text)

            if rec_text and len(rec_text) > 10:
                recommendations.append(Recommendation(
                    recommendation=rec_text[:500],  # Limit length
                    rationale="",  # Could be parsed from sub-bullets
                    priority="medium",
                ))

        return recommendations[:10]  # Limit to 10 recommendations

    def _parse_anti_patterns(self, content: str) -> list[str]:
        """Parse anti-patterns from markdown content."""
        import re

        anti_patterns = []

        # Find the Anti-Patterns section
        ap_section = self._extract_section(content, [
            "Anti-Patterns",
            "Anti-Patterns to Avoid",
            "Pitfalls",
            "Common Mistakes",
            "What to Avoid",
        ])

        if not ap_section:
            return anti_patterns

        # Parse bullet points
        bullet_pattern = re.compile(
            r'(?:^|\n)(?:\d+\.\s+|\*\s+|-\s+)(.+?)(?=\n(?:\d+\.|\*|-)|$)',
            re.MULTILINE
        )

        for match in bullet_pattern.finditer(ap_section):
            ap_text = match.group(1).strip()
            if ap_text and len(ap_text) > 5:
                anti_patterns.append(ap_text[:300])

        return anti_patterns[:10]  # Limit to 10 anti-patterns

    def _parse_summary(self, content: str) -> str:
        """Parse summary from markdown content."""
        import re

        # Find the Summary section
        summary_section = self._extract_section(content, [
            "Summary",
            "Overview",
            "Executive Summary",
            "TL;DR",
        ])

        if summary_section:
            # Get first paragraph
            paragraphs = summary_section.strip().split("\n\n")
            if paragraphs:
                return paragraphs[0].strip()[:1000]

        # Fallback: try to get first substantial paragraph from content
        paragraphs = content.strip().split("\n\n")
        for para in paragraphs:
            para = para.strip()
            # Skip headers, code blocks, tables
            if para.startswith("#") or para.startswith("`") or para.startswith("|"):
                continue
            if len(para) > 50:
                return para[:1000]

        return ""

    def _extract_section(self, content: str, section_names: list[str]) -> str | None:
        """Extract a section from markdown content by header name.

        Args:
            content: Full markdown content
            section_names: List of possible section header names (case-insensitive)

        Returns:
            Section content (between this header and next header), or None
        """
        import re

        for section_name in section_names:
            # Match headers like ## Section Name or ### Section Name
            pattern = re.compile(
                rf'^(#{1,4})\s*{re.escape(section_name)}\s*$',
                re.MULTILINE | re.IGNORECASE
            )

            match = pattern.search(content)
            if match:
                start = match.end()
                header_level = len(match.group(1))

                # Find the next header of same or higher level
                next_header = re.compile(
                    rf'^#{{{1},{header_level}}}\s+',
                    re.MULTILINE
                )
                next_match = next_header.search(content, start)

                if next_match:
                    return content[start:next_match.start()]
                else:
                    return content[start:]

        return None

    def invoke_jib_research(
        self,
        task_type: str,
        context: dict,
    ) -> dict | None:
        """Invoke jib container for research task.

        Args:
            task_type: One of 'research_adr', 'generate_adr', 'review_adr'
            context: Dict containing task-specific context

        Returns:
            Research result dict if successful, None otherwise
        """
        context_json = json.dumps(context)

        # Container path is fixed - jib always mounts to /home/jwies/khan/
        processor_path = (
            "/home/jwies/khan/james-in-a-box/jib-container/jib-tasks/adr/adr-processor.py"
        )

        cmd = [
            "jib",
            "--exec",
            "python3",
            processor_path,
            "--task",
            task_type,
            "--context",
            context_json,
        ]

        print(f"  Invoking jib: {task_type}")

        try:
            # No explicit timeout - rely on jib/Claude's internal timeout handling
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                print("  jib completed successfully")
                # Try to parse JSON output from jib
                try:
                    # Look for JSON in stdout (after any logging output)
                    lines = result.stdout.strip().split("\n")
                    for line in reversed(lines):
                        if line.startswith("{"):
                            return json.loads(line)
                    return {"success": True, "output": result.stdout}
                except json.JSONDecodeError:
                    return {"success": True, "output": result.stdout}
            else:
                print(f"  jib failed with code {result.returncode}")
                stderr_tail = result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr
                if stderr_tail:
                    print(f"  stderr: {stderr_tail}")
                return None
        except FileNotFoundError:
            print("  jib command not found - is it in PATH?")
            return None

    def research_open_prs(self) -> list[ResearchResult]:
        """Research all open ADR PRs and post comments.

        Workflow:
        1. Find open PRs that modify ADR files
        2. For each ADR, invoke jib to research the topic
        3. Post research findings as PR comment

        Returns:
            List of ResearchResult objects with typed, structured research findings.
        """
        results = []
        adrs = self.find_open_adr_prs()

        print(f"Found {len(adrs)} open PR(s) with ADR changes")

        for adr in adrs:
            print(f"\nResearching: {adr.title}")
            print(f"  PR #{adr.pr_number}: {adr.pr_url}")

            context = {
                "task_type": "research_adr",
                "adr_title": adr.title,
                "adr_content": adr.content[:20000],  # Limit content size
                "topics": adr.topics,
                "pr_number": adr.pr_number,
                "pr_url": adr.pr_url,
                "output_mode": "pr_comment",
            }

            raw_result = self.invoke_jib_research("research_adr", context)
            research_result = self._parse_research_result(raw_result, adr.title)
            research_result.pr_number = adr.pr_number
            results.append(research_result)

        return results

    def research_merged_adrs(self) -> list[ResearchResult]:
        """Research all merged/implemented ADRs and create update PRs.

        Workflow:
        1. Find ADRs in implemented/ directory
        2. For each ADR, invoke jib to research for updates
        3. If updates found, create PR with Research Updates section

        Returns:
            List of ResearchResult objects with typed, structured research findings.
        """
        results = []
        adrs = self.find_adrs_by_status("implemented")

        print(f"Found {len(adrs)} implemented ADR(s) to research")

        for adr in adrs:
            print(f"\nResearching: {adr.title}")
            print(f"  Path: {adr.path}")

            context = {
                "task_type": "research_adr",
                "adr_title": adr.title,
                "adr_path": str(adr.path.relative_to(self.project_root)),
                "adr_content": adr.content[:20000],
                "topics": adr.topics,
                "output_mode": "update_pr",
            }

            raw_result = self.invoke_jib_research("research_adr", context)
            research_result = self._parse_research_result(raw_result, adr.title)
            results.append(research_result)

        return results

    def generate_adr(self, topic: str) -> ResearchResult:
        """Generate a new ADR from research on a topic.

        Workflow:
        1. Research the topic via web search
        2. Generate complete ADR with research-backed content
        3. Create PR with new ADR in docs/adr/proposed/

        Returns:
            ResearchResult with typed, structured research findings.
        """
        print(f"Generating ADR for topic: {topic}")

        context = {
            "task_type": "generate_adr",
            "topic": topic,
            "output_dir": "docs/adr/not-implemented",
            "output_mode": "new_pr",
        }

        raw_result = self.invoke_jib_research("generate_adr", context)
        return self._parse_research_result(raw_result, topic)

    def review_adr(self, adr_path: Path) -> ResearchResult:
        """Review and validate an ADR against current research.

        Workflow:
        1. Read the ADR content
        2. Research each claim/assertion in the ADR
        3. Post review findings as PR comment (if PR exists) or markdown report

        Returns:
            ResearchResult with typed, structured research findings.
        """
        if not adr_path.exists():
            return ResearchResult(
                success=False,
                query=str(adr_path),
                error=f"ADR not found: {adr_path}",
            )

        content = adr_path.read_text()
        title = self._extract_title(content)
        topics = self._extract_topics(content)

        print(f"Reviewing ADR: {title}")
        print(f"  Path: {adr_path}")
        print(f"  Topics: {', '.join(topics)}")

        # Check if there's an open PR for this ADR
        pr_info = self._find_pr_for_file(str(adr_path.relative_to(self.project_root)))

        context = {
            "task_type": "review_adr",
            "adr_title": title,
            "adr_path": str(adr_path.relative_to(self.project_root)),
            "adr_content": content[:20000],
            "topics": topics,
            "pr_number": pr_info.get("number") if pr_info else None,
            "pr_url": pr_info.get("url") if pr_info else None,
            "output_mode": "pr_comment" if pr_info else "report",
        }

        raw_result = self.invoke_jib_research("review_adr", context)
        research_result = self._parse_research_result(raw_result, title)
        research_result.pr_number = pr_info.get("number") if pr_info else None
        return research_result

    def _find_pr_for_file(self, file_path: str) -> dict | None:
        """Find an open PR that modifies a specific file."""
        for repo in self.config.get("writable_repos", []):
            prs = gh_json(
                [
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "open",
                    "--json",
                    "number,url,files",
                ]
            )
            if not prs:
                continue

            for pr in prs:
                files = pr.get("files", [])
                if any(f.get("path") == file_path for f in files):
                    return {"number": pr["number"], "url": pr["url"]}

        return None

    def research_topic(self, query: str, report_only: bool = False) -> ResearchResult:
        """Research a specific topic and output findings.

        Args:
            query: The research query/topic
            report_only: If True, output as markdown report only (no PR/commit)

        Returns:
            ResearchResult with typed, structured research findings.
        """
        print(f"Researching topic: {query}")

        context = {
            "task_type": "research_topic",
            "query": query,
            "output_mode": "report" if report_only else "pr",
        }

        raw_result = self.invoke_jib_research("research_topic", context)
        return self._parse_research_result(raw_result, query)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Research-based ADR workflow tool (Phase 6 of ADR-LLM-Documentation-Index-Strategy)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --scope open-prs              # Research open ADR PRs, post comments
  %(prog)s --scope merged                # Research implemented ADRs, create update PRs
  %(prog)s --generate "Topic"            # Generate new ADR from research
  %(prog)s --review path/to/ADR.md       # Review ADR against current research
  %(prog)s --scope topic --query "X"     # Research specific topic
  %(prog)s --scope topic --query "X" --report-only  # Output as report only

Note: This tool invokes jib containers for research. Ensure jib is in PATH.
        """,
    )

    parser.add_argument(
        "--scope",
        choices=["open-prs", "merged", "topic"],
        help="Research scope: open-prs (comment on PRs), merged (update ADRs), topic (specific query)",
    )

    parser.add_argument(
        "--generate",
        metavar="TOPIC",
        help="Generate a new ADR from research on a topic",
    )

    parser.add_argument(
        "--review",
        metavar="PATH",
        type=Path,
        help="Review and validate an existing ADR with current research",
    )

    parser.add_argument(
        "--query",
        "-q",
        help="Research query (used with --scope topic)",
    )

    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Output findings as markdown report without creating PR/commit",
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=None,
        help="Project root (default: auto-detect)",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.scope and not args.generate and not args.review:
        parser.print_help()
        print("\nError: Specify --scope, --generate, or --review", file=sys.stderr)
        sys.exit(1)

    if args.scope == "topic" and not args.query:
        print("Error: --scope topic requires --query", file=sys.stderr)
        sys.exit(1)

    # Initialize researcher
    project_root = args.project.resolve() if args.project else None
    researcher = ADRResearcher(project_root)

    print("=" * 60)
    print("ADR Researcher - Research-Based ADR Workflow")
    print(f"Time: {utc_now_iso()}")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN MODE - No changes will be made]\n")

    results: dict | ResearchResult | list[ResearchResult] = {}

    # Execute requested action
    if args.generate:
        print(f"\nGenerating ADR for topic: {args.generate}")
        if not args.dry_run:
            results = researcher.generate_adr(args.generate)
        else:
            results = {"topic": args.generate, "status": "dry_run"}

    elif args.review:
        print(f"\nReviewing ADR: {args.review}")
        if not args.dry_run:
            results = researcher.review_adr(args.review)
        else:
            results = {"path": str(args.review), "status": "dry_run"}

    elif args.scope == "open-prs":
        print("\nResearching open ADR PRs...")
        if not args.dry_run:
            results = researcher.research_open_prs()
        else:
            adrs = researcher.find_open_adr_prs()
            results = {
                "prs": [{"title": a.title, "pr": a.pr_number} for a in adrs],
                "status": "dry_run",
            }

    elif args.scope == "merged":
        print("\nResearching implemented ADRs...")
        if not args.dry_run:
            results = researcher.research_merged_adrs()
        else:
            adrs = researcher.find_adrs_by_status("implemented")
            results = {
                "adrs": [{"title": a.title, "path": str(a.path)} for a in adrs],
                "status": "dry_run",
            }

    elif args.scope == "topic":
        print(f"\nResearching topic: {args.query}")
        if not args.dry_run:
            results = researcher.research_topic(args.query, args.report_only)
        else:
            results = {"query": args.query, "status": "dry_run"}

    # Output results
    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)

    # Convert ResearchResult objects to dicts for output
    def to_output(obj):
        """Convert ResearchResult or list of ResearchResult to JSON-serializable dict."""
        if isinstance(obj, ResearchResult):
            return asdict(obj)
        elif isinstance(obj, list):
            return [asdict(item) if isinstance(item, ResearchResult) else item for item in obj]
        return obj

    if args.json:
        output = to_output(results)
        print(json.dumps(output, indent=2, default=str))
    # Pretty print summary
    elif isinstance(results, list):
        # List of ResearchResult objects
        print(f"Processed {len(results)} item(s)")
        for r in results:
            status = "success" if r.success else "failed"
            print(f"  - {r.query}: {status}")
            if r.sources:
                print(f"      Sources: {len(r.sources)}")
            if r.key_findings:
                print(f"      Key findings: {len(r.key_findings)}")
            if r.recommendations:
                print(f"      Recommendations: {len(r.recommendations)}")
            if r.pr_url:
                print(f"      PR: {r.pr_url}")
    elif isinstance(results, ResearchResult):
        # Single ResearchResult
        print(f"Query: {results.query}")
        print(f"Status: {'success' if results.success else 'failed'}")
        if results.error:
            print(f"Error: {results.error}")
        if results.summary:
            print(f"\nSummary: {results.summary[:200]}...")
        if results.sources:
            print(f"\nSources ({len(results.sources)}):")
            for source in results.sources[:5]:
                print(f"  - {source.title}: {source.url}")
            if len(results.sources) > 5:
                print(f"  ... and {len(results.sources) - 5} more")
        if results.key_findings:
            print(f"\nKey Findings ({len(results.key_findings)}):")
            for finding in results.key_findings[:3]:
                print(f"  - {finding.topic}: {finding.finding[:100]}...")
            if len(results.key_findings) > 3:
                print(f"  ... and {len(results.key_findings) - 3} more")
        if results.recommendations:
            print(f"\nRecommendations ({len(results.recommendations)}):")
            for rec in results.recommendations[:3]:
                print(f"  - {rec.recommendation[:100]}...")
            if len(results.recommendations) > 3:
                print(f"  ... and {len(results.recommendations) - 3} more")
        if results.pr_url:
            print(f"\nPR: {results.pr_url}")
    elif isinstance(results, dict):
        # Dry run or fallback dict
        print(f"Status: {results.get('status', 'unknown')}")
        if "prs" in results:
            print(f"PRs to process: {len(results['prs'])}")
        if "adrs" in results:
            print(f"ADRs to process: {len(results['adrs'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
