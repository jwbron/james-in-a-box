#!/usr/bin/env python3
"""
Confluence Documentation Discoverer for Jib Repository Onboarding

Scans pre-synced Confluence documentation to find organization-specific
documents relevant to a target repository. Part of the Jib Repository
Onboarding Strategy (ADR-Jib-Repo-Onboarding).

Outputs:
- external-docs.json: Discovered Confluence docs with relevance mapping
- Index additions for docs/index.md integration

Per ADR: Jib Repository Onboarding Strategy (Phase 0: Context Gathering)
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class DiscoveredDoc:
    """A Confluence document discovered during repo scanning."""

    title: str
    path: str  # Relative path from confluence dir
    relevance: str  # Why this doc is relevant
    category: str  # adr, runbook, guide, etc.
    keywords_matched: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0 confidence score


class ConfluenceDocDiscoverer:
    """Discovers relevant Confluence docs for a target repository."""

    # Category detection patterns
    CATEGORY_PATTERNS = {
        "adr": [r"ADR\s*[#]?\d+", r"Architecture\s+Decision", r"Decision\s+Record"],
        "runbook": [r"Runbook", r"Run\s+Book", r"Operations\s+Guide"],
        "guide": [r"Guide", r"Getting\s+Started", r"How\s+To", r"Tutorial"],
        "reference": [r"Reference", r"API\s+Doc", r"Documentation"],
        "policy": [r"Policy", r"Standard", r"Best\s+Practice"],
    }

    # Common abbreviations and alternate names for repos
    REPO_ALIASES = {
        "webapp": ["webapp", "web-app", "web app", "main app", "ka webapp"],
        "perseus": ["perseus", "content editor", "exercise editor"],
        "mobile": ["mobile", "ios", "android", "mobile app"],
    }

    def __init__(
        self,
        confluence_dir: Path,
        repo_name: str,
        output_path: Path,
        public_repo: bool = False,
    ):
        self.confluence_dir = confluence_dir.resolve()
        self.repo_name = repo_name
        self.output_path = output_path.resolve()
        self.public_repo = public_repo

        # Build search terms from repo name
        self.search_terms = self._build_search_terms(repo_name)

        # Results
        self.discovered_docs: list[DiscoveredDoc] = []

    def _build_search_terms(self, repo_name: str) -> list[str]:
        """Build list of search terms from repo name."""
        terms = [repo_name]

        # Add variations
        # Convert kebab-case to spaces and individual words
        if "-" in repo_name:
            terms.append(repo_name.replace("-", " "))
            terms.extend(repo_name.split("-"))

        # Convert snake_case
        if "_" in repo_name:
            terms.append(repo_name.replace("_", " "))
            terms.extend(repo_name.split("_"))

        # Add known aliases if available
        for _alias_key, aliases in self.REPO_ALIASES.items():
            if repo_name.lower() in [a.lower() for a in aliases]:
                terms.extend(aliases)

        # Deduplicate while preserving order
        seen = set()
        unique_terms = []
        for term in terms:
            term_lower = term.lower()
            if term_lower not in seen and len(term) > 2:  # Skip very short terms
                seen.add(term_lower)
                unique_terms.append(term)

        return unique_terms

    def _detect_category(self, filename: str, content: str) -> str:
        """Detect document category from filename and content."""
        text_to_check = f"{filename} {content[:500]}"

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_to_check, re.IGNORECASE):
                    return category

        return "documentation"

    def _calculate_confidence(
        self, filename: str, content: str, keywords_matched: list[str]
    ) -> float:
        """Calculate confidence score for document relevance."""
        score = 0.0

        # Filename matches are high confidence
        filename_lower = filename.lower()
        for term in self.search_terms:
            if term.lower() in filename_lower:
                score += 0.4
                break

        # Title/heading matches
        # Look for the first # heading in markdown
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).lower()
            for term in self.search_terms:
                if term.lower() in title:
                    score += 0.3
                    break

        # Keyword frequency in content
        content_lower = content.lower()
        keyword_count = sum(content_lower.count(term.lower()) for term in self.search_terms)
        if keyword_count > 0:
            # Logarithmic scaling - diminishing returns for many matches
            score += min(0.3, 0.1 * (1 + keyword_count / 5))

        # Bonus for matching multiple keywords
        if len(keywords_matched) > 1:
            score += 0.1

        return min(1.0, score)  # Cap at 1.0

    def _generate_relevance_description(self, category: str, keywords_matched: list[str]) -> str:
        """Generate human-readable relevance description."""
        if not keywords_matched:
            return f"Potentially relevant {category}"

        keywords_str = ", ".join(keywords_matched[:3])
        if len(keywords_matched) > 3:
            keywords_str += f" (+{len(keywords_matched) - 3} more)"

        category_descriptions = {
            "adr": f"Architectural decision referencing {keywords_str}",
            "runbook": f"Operational runbook for {keywords_str}",
            "guide": f"Guide covering {keywords_str}",
            "reference": f"Reference documentation for {keywords_str}",
            "policy": f"Policy or standards for {keywords_str}",
            "documentation": f"Documentation mentioning {keywords_str}",
        }

        return category_descriptions.get(category, f"References {keywords_str}")

    def scan_directory(self, directory: Path, depth: int = 0) -> None:
        """Recursively scan a directory for relevant documents."""
        if depth > 5:  # Limit recursion depth
            return

        try:
            for item in sorted(directory.iterdir()):
                if item.is_dir():
                    # Skip hidden directories
                    if not item.name.startswith("."):
                        self.scan_directory(item, depth + 1)
                elif item.is_file() and item.suffix.lower() == ".md":
                    self._analyze_document(item)
        except PermissionError:
            pass

    def _analyze_document(self, file_path: Path) -> None:
        """Analyze a single document for relevance."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return

        # Check for search term matches
        content_lower = content.lower()
        filename_lower = file_path.name.lower()

        keywords_matched = []
        for term in self.search_terms:
            term_lower = term.lower()
            if term_lower in content_lower or term_lower in filename_lower:
                keywords_matched.append(term)

        if not keywords_matched:
            return  # No relevance detected

        # Calculate confidence
        confidence = self._calculate_confidence(file_path.name, content, keywords_matched)

        # Skip low-confidence matches
        if confidence < 0.2:
            return

        # Detect category
        category = self._detect_category(file_path.name, content)

        # Extract title from first heading or filename
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        else:
            # Clean up filename for title
            title = file_path.stem.replace("-", " ").replace("_", " ").title()

        # Get relative path from confluence dir
        rel_path = str(file_path.relative_to(self.confluence_dir))

        # Generate relevance description
        relevance = self._generate_relevance_description(category, keywords_matched)

        doc = DiscoveredDoc(
            title=title,
            path=rel_path,
            relevance=relevance,
            category=category,
            keywords_matched=keywords_matched,
            confidence=confidence,
        )

        self.discovered_docs.append(doc)

    def discover(self) -> dict:
        """Main discovery method. Returns the generated JSON structure."""
        print(f"Scanning Confluence docs for: {self.repo_name}")
        print(f"  Search terms: {', '.join(self.search_terms)}")
        print(f"  Confluence directory: {self.confluence_dir}")

        if not self.confluence_dir.exists():
            print(f"  Warning: Confluence directory not found: {self.confluence_dir}")
            return self._empty_result()

        # Scan all directories in confluence sync
        self.scan_directory(self.confluence_dir)

        # Sort by confidence (highest first)
        self.discovered_docs.sort(key=lambda d: d.confidence, reverse=True)

        # Apply public repo filtering if needed
        if self.public_repo:
            self._filter_for_public()

        print(f"  Found {len(self.discovered_docs)} relevant documents")

        return self._generate_output()

    def _filter_for_public(self) -> None:
        """Filter documents for public repository safety."""
        # For public repos, we might want to exclude certain categories
        # or documents that reveal internal architecture
        safe_categories = {"guide", "documentation", "reference"}

        filtered = []
        for doc in self.discovered_docs:
            if doc.category in safe_categories:
                filtered.append(doc)
            else:
                print(f"  Filtered (public repo): {doc.title} ({doc.category})")

        self.discovered_docs = filtered

    def _generate_output(self) -> dict:
        """Generate the external-docs.json output structure."""
        generated_at = datetime.now(UTC).isoformat()

        # Build discovered_docs list
        discovered_docs_list = []
        for doc in self.discovered_docs:
            discovered_docs_list.append(
                {
                    "title": doc.title,
                    "path": doc.path,
                    "relevance": doc.relevance,
                    "category": doc.category,
                    "confidence": round(doc.confidence, 2),
                }
            )

        # Build index additions (markdown table rows)
        index_additions = []
        for doc in self.discovered_docs[:10]:  # Top 10 for index
            # Create relative link from target repo docs to confluence
            confluence_link = f"../../../context-sync/confluence/{doc.path}"
            index_additions.append(f"| [{doc.title}]({confluence_link}) | {doc.relevance} |")

        result = {
            "generated": generated_at,
            "repo": self.repo_name,
            "search_terms": self.search_terms,
            "public_repo": self.public_repo,
            "discovered_docs": discovered_docs_list,
            "index_additions": index_additions,
            "summary": {
                "total_found": len(self.discovered_docs),
                "by_category": self._count_by_category(),
            },
        }

        return result

    def _count_by_category(self) -> dict[str, int]:
        """Count documents by category."""
        counts: dict[str, int] = {}
        for doc in self.discovered_docs:
            counts[doc.category] = counts.get(doc.category, 0) + 1
        return dict(sorted(counts.items()))

    def _empty_result(self) -> dict:
        """Return empty result structure when no docs found."""
        return {
            "generated": datetime.now(UTC).isoformat(),
            "repo": self.repo_name,
            "search_terms": self.search_terms,
            "public_repo": self.public_repo,
            "discovered_docs": [],
            "index_additions": [],
            "summary": {"total_found": 0, "by_category": {}},
        }

    def write_output(self, result: dict) -> None:
        """Write the result to output file."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_path, "w") as f:
            json.dump(result, f, indent=2)

        print(f"  Output written to: {self.output_path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Discover relevant Confluence docs for a repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --repo-name webapp
  %(prog)s --repo-name my-service --confluence-dir ~/context-sync/confluence
  %(prog)s --repo-name public-lib --public-repo
        """,
    )

    parser.add_argument(
        "--repo-name",
        "-r",
        required=True,
        help="Name of the repository to find docs for",
    )

    parser.add_argument(
        "--confluence-dir",
        "-c",
        type=Path,
        default=Path.home() / "context-sync" / "confluence",
        help="Path to synced Confluence directory (default: ~/context-sync/confluence)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file path (default: <cwd>/docs/generated/external-docs.json)",
    )

    parser.add_argument(
        "--public-repo",
        action="store_true",
        help="Filter output for public repository safety",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without writing file",
    )

    args = parser.parse_args()

    output_path = args.output or (Path.cwd() / "docs" / "generated" / "external-docs.json")

    discoverer = ConfluenceDocDiscoverer(
        confluence_dir=args.confluence_dir,
        repo_name=args.repo_name,
        output_path=output_path,
        public_repo=args.public_repo,
    )

    result = discoverer.discover()

    if args.dry_run:
        print("\n=== DRY RUN - Output: ===")
        print(json.dumps(result, indent=2))
    else:
        discoverer.write_output(result)

    # Print summary
    summary = result.get("summary", {})
    print("\nSummary:")
    print(f"  Total documents found: {summary.get('total_found', 0)}")
    if summary.get("by_category"):
        print(f"  By category: {summary['by_category']}")


if __name__ == "__main__":
    main()
