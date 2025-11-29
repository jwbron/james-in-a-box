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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml


# Rate limiting configuration
RATE_LIMIT_DELAY = 0.5  # 500ms between API calls


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

    def research_open_prs(self) -> list[dict]:
        """Research all open ADR PRs and post comments.

        Workflow:
        1. Find open PRs that modify ADR files
        2. For each ADR, invoke jib to research the topic
        3. Post research findings as PR comment
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

            result = self.invoke_jib_research("research_adr", context)
            if result:
                results.append(
                    {
                        "adr": adr.title,
                        "pr_number": adr.pr_number,
                        "status": "comment_posted" if result.get("success") else "failed",
                        "result": result,
                    }
                )

        return results

    def research_merged_adrs(self) -> list[dict]:
        """Research all merged/implemented ADRs and create update PRs.

        Workflow:
        1. Find ADRs in implemented/ directory
        2. For each ADR, invoke jib to research for updates
        3. If updates found, create PR with Research Updates section
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

            result = self.invoke_jib_research("research_adr", context)
            if result:
                results.append(
                    {
                        "adr": adr.title,
                        "path": str(adr.path),
                        "status": "pr_created" if result.get("pr_url") else "no_updates",
                        "result": result,
                    }
                )

        return results

    def generate_adr(self, topic: str) -> dict:
        """Generate a new ADR from research on a topic.

        Workflow:
        1. Research the topic via web search
        2. Generate complete ADR with research-backed content
        3. Create PR with new ADR in docs/adr/proposed/
        """
        print(f"Generating ADR for topic: {topic}")

        context = {
            "task_type": "generate_adr",
            "topic": topic,
            "output_dir": "docs/adr/not-implemented",
            "output_mode": "new_pr",
        }

        result = self.invoke_jib_research("generate_adr", context)
        return {
            "topic": topic,
            "status": "pr_created" if result and result.get("pr_url") else "failed",
            "result": result,
        }

    def review_adr(self, adr_path: Path) -> dict:
        """Review and validate an ADR against current research.

        Workflow:
        1. Read the ADR content
        2. Research each claim/assertion in the ADR
        3. Post review findings as PR comment (if PR exists) or markdown report
        """
        if not adr_path.exists():
            return {"error": f"ADR not found: {adr_path}"}

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

        result = self.invoke_jib_research("review_adr", context)
        return {
            "adr": title,
            "path": str(adr_path),
            "has_pr": pr_info is not None,
            "status": "review_posted" if result and result.get("success") else "failed",
            "result": result,
        }

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

    def research_topic(self, query: str, report_only: bool = False) -> dict:
        """Research a specific topic and output findings.

        Args:
            query: The research query/topic
            report_only: If True, output as markdown report only (no PR/commit)

        Returns:
            Research results dict
        """
        print(f"Researching topic: {query}")

        context = {
            "task_type": "research_topic",
            "query": query,
            "output_mode": "report" if report_only else "pr",
        }

        result = self.invoke_jib_research("research_topic", context)
        return {
            "query": query,
            "status": "completed" if result else "failed",
            "result": result,
        }


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

    results = {}

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
            results = {"prs": researcher.research_open_prs()}
        else:
            adrs = researcher.find_open_adr_prs()
            results = {
                "prs": [{"title": a.title, "pr": a.pr_number} for a in adrs],
                "status": "dry_run",
            }

    elif args.scope == "merged":
        print("\nResearching implemented ADRs...")
        if not args.dry_run:
            results = {"adrs": researcher.research_merged_adrs()}
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

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    # Pretty print summary
    elif "prs" in results:
        pr_results = results["prs"]
        print(f"Processed {len(pr_results)} PR(s)")
        for r in pr_results:
            status = r.get("status", "unknown")
            print(f"  - {r.get('adr', 'Unknown')}: {status}")
    elif "adrs" in results:
        adr_results = results["adrs"]
        print(f"Processed {len(adr_results)} ADR(s)")
        for r in adr_results:
            status = r.get("status", "unknown")
            print(f"  - {r.get('adr', 'Unknown')}: {status}")
    else:
        print(f"Status: {results.get('status', 'unknown')}")
        if results.get("result", {}).get("pr_url"):
            print(f"PR: {results['result']['pr_url']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
