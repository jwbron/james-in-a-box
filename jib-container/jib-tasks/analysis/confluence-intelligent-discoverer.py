#!/usr/bin/env python3
"""
Intelligent Confluence Documentation Discoverer for Jib Repository Onboarding.

Uses Claude to semantically analyze Confluence documents and intelligently select
the most relevant ones for a target repository. This provides much higher quality
results than keyword-based matching.

The intelligent discovery process:
1. Quick heuristic scan to get candidate documents (fast filter)
2. Group candidates into batches for efficiency
3. Use Claude to analyze each batch and score relevance
4. Consolidate and rank results by semantic relevance

This script runs inside the jib container where it has access to Claude.

Usage:
    # From inside container (or via jib --exec):
    confluence-intelligent-discoverer --repo-name webapp --output /tmp/external-docs.json

    # With custom confluence dir:
    confluence-intelligent-discoverer --repo-name my-service --confluence-dir ~/context-sync/confluence

    # With max documents limit:
    confluence-intelligent-discoverer --repo-name webapp --max-docs 30
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


# Import shared modules - find shared directory dynamically
def _find_shared_path() -> Path:
    """Find the shared directory by walking up from the script location."""
    script_path = Path(__file__).resolve()
    for i in range(1, 6):
        if i < len(script_path.parents):
            candidate = script_path.parents[i] / "shared"
            if (candidate / "claude").is_dir():
                return candidate
    # Fallback: check /opt/jib-runtime/shared (container path)
    container_shared = Path("/opt/jib-runtime/shared")
    if (container_shared / "claude").is_dir():
        return container_shared
    raise ImportError(f"Cannot find shared/claude module from {script_path}")


sys.path.insert(0, str(_find_shared_path()))
from claude import is_claude_available, run_claude


@dataclass
class DiscoveredDoc:
    """A Confluence document discovered during repo scanning."""

    title: str
    path: str  # Relative path from confluence dir
    relevance: str  # Why this doc is relevant
    category: str  # adr, runbook, guide, etc.
    keywords_matched: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0 confidence score
    llm_reasoning: str = ""  # LLM's explanation for relevance


# Category detection patterns (same as heuristic discoverer)
CATEGORY_PATTERNS = {
    "adr": [r"ADR\s*[#]?\d+", r"Architecture\s+Decision", r"Decision\s+Record"],
    "runbook": [r"Runbook", r"Run\s+Book", r"Operations\s+Guide"],
    "guide": [r"Guide", r"Getting\s+Started", r"How\s+To", r"Tutorial"],
    "reference": [r"Reference", r"API\s+Doc", r"Documentation"],
    "policy": [r"Policy", r"Standard", r"Best\s+Practice"],
}

# Common abbreviations and alternate names for repos
REPO_ALIASES = {
    "webapp": ["webapp", "web-app", "web app", "main app", "ka webapp", "khan academy webapp"],
    "perseus": ["perseus", "content editor", "exercise editor", "math editor"],
    "mobile": ["mobile", "ios", "android", "mobile app", "native app"],
    "services": ["services", "backend services", "microservices", "api services"],
}


def detect_category(filename: str, content: str) -> str:
    """Detect document category from filename and content."""
    text_to_check = f"{filename} {content[:500]}"
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return category
    return "documentation"


def build_search_terms(repo_name: str) -> list[str]:
    """Build list of search terms from repo name."""
    terms = [repo_name]

    # Add variations
    if "-" in repo_name:
        terms.append(repo_name.replace("-", " "))
        terms.extend(repo_name.split("-"))

    if "_" in repo_name:
        terms.append(repo_name.replace("_", " "))
        terms.extend(repo_name.split("_"))

    # Add known aliases if available
    for _alias_key, aliases in REPO_ALIASES.items():
        if repo_name.lower() in [a.lower() for a in aliases]:
            terms.extend(aliases)

    # Deduplicate while preserving order
    seen = set()
    unique_terms = []
    for term in terms:
        term_lower = term.lower()
        if term_lower not in seen and len(term) > 2:
            seen.add(term_lower)
            unique_terms.append(term)

    return unique_terms


def quick_heuristic_scan(
    confluence_dir: Path, search_terms: list[str], max_candidates: int = 100
) -> list[dict]:
    """Quick keyword-based scan to get candidate documents.

    This is a fast filter to reduce the number of documents we need to
    analyze with Claude. Returns documents that have at least some
    keyword matches.
    """
    candidates = []

    def scan_dir(directory: Path, depth: int = 0):
        if depth > 5:
            return
        try:
            for item in sorted(directory.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    scan_dir(item, depth + 1)
                elif item.is_file() and item.suffix.lower() == ".md":
                    analyze_doc(item)
        except PermissionError:
            pass

    def analyze_doc(file_path: Path):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return

        content_lower = content.lower()
        filename_lower = file_path.name.lower()

        keywords_matched = []
        for term in search_terms:
            term_lower = term.lower()
            if term_lower in content_lower or term_lower in filename_lower:
                keywords_matched.append(term)

        if not keywords_matched:
            return

        # Extract title
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else file_path.stem.replace("-", " ").title()

        # Quick confidence score for sorting
        score = 0.0
        if any(term.lower() in filename_lower for term in search_terms):
            score += 0.4
        if title_match and any(term.lower() in title_match.group(1).lower() for term in search_terms):
            score += 0.3
        keyword_count = sum(content_lower.count(term.lower()) for term in search_terms)
        score += min(0.3, 0.1 * (1 + keyword_count / 5))

        rel_path = str(file_path.relative_to(confluence_dir))
        category = detect_category(file_path.name, content)

        # Extract summary (first paragraph after title)
        summary = ""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("#"):
                continue
            line = line.strip()
            if line and not line.startswith(("!", "[", "|", "-", "*", ">")):
                summary = line[:300]
                break

        candidates.append({
            "title": title,
            "path": rel_path,
            "category": category,
            "keywords_matched": keywords_matched,
            "heuristic_score": score,
            "summary": summary,
            "content_preview": content[:2000],
        })

    scan_dir(confluence_dir)

    # Sort by heuristic score and take top candidates
    candidates.sort(key=lambda d: d["heuristic_score"], reverse=True)
    return candidates[:max_candidates]


def analyze_batch_with_claude(
    candidates: list[dict],
    repo_name: str,
    repo_description: str,
    batch_num: int,
    total_batches: int,
) -> list[dict]:
    """Use Claude to analyze a batch of candidate documents.

    Returns documents with LLM-assigned relevance scores and reasoning.
    """
    if not candidates:
        return []

    # Build prompt
    docs_text = ""
    for i, doc in enumerate(candidates):
        docs_text += f"""
---
Document {i + 1}:
- Title: {doc['title']}
- Path: {doc['path']}
- Category: {doc['category']}
- Keywords matched: {', '.join(doc['keywords_matched'])}
- Summary: {doc['summary'][:200]}...
- Content preview: {doc['content_preview'][:800]}...
---
"""

    prompt = f"""You are helping identify the most relevant Confluence documentation for developers working on the "{repo_name}" repository.

Repository context:
- Name: {repo_name}
{f'- Description: {repo_description}' if repo_description else ''}

I have {len(candidates)} candidate documents (batch {batch_num}/{total_batches}) that might be relevant. Please analyze each and rate its relevance.

CANDIDATES:
{docs_text}

For each document, provide:
1. A relevance score from 0.0 to 1.0 where:
   - 0.0-0.3: Not relevant or tangentially related
   - 0.3-0.5: Somewhat relevant, nice to know
   - 0.5-0.7: Relevant, useful for developers
   - 0.7-0.9: Highly relevant, important reference
   - 0.9-1.0: Essential, must-read for this repo

2. A brief explanation of WHY it's relevant (or not) to {repo_name} developers

3. A concise relevance description for the final output

Respond with a JSON array like this:
[
  {{
    "doc_index": 1,
    "relevance_score": 0.85,
    "reasoning": "This ADR directly covers the authentication system used in {repo_name}...",
    "relevance_description": "Architecture decision for user authentication flow"
  }},
  ...
]

Focus on practical relevance - what would actually help a developer understand, maintain, or extend {repo_name}?

Output ONLY the JSON array, no other text."""

    print(f"  Analyzing batch {batch_num}/{total_batches} ({len(candidates)} docs)...")

    result = run_claude(
        prompt=prompt,
        timeout=120,
        stream=False,
    )

    if not result.success:
        print(f"    Warning: Claude analysis failed: {result.error}")
        # Return candidates with original heuristic scores as fallback
        return [
            {
                **doc,
                "llm_score": doc["heuristic_score"],
                "llm_reasoning": "Heuristic fallback (LLM analysis failed)",
                "relevance_description": f"Documentation related to {', '.join(doc['keywords_matched'][:3])}",
            }
            for doc in candidates
        ]

    # Parse Claude's response
    try:
        # Try to extract JSON from response
        output = result.stdout.strip()

        # Try direct parse first
        try:
            analyses = json.loads(output)
        except json.JSONDecodeError:
            # Try to find JSON array in markdown code block
            json_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", output)
            if json_match:
                analyses = json.loads(json_match.group(1))
            else:
                # Try to find any JSON array
                array_match = re.search(r"\[[\s\S]*\]", output)
                if array_match:
                    analyses = json.loads(array_match.group())
                else:
                    raise ValueError("No JSON array found in output")

        # Match analyses to candidates
        analysis_by_index = {a.get("doc_index", 0): a for a in analyses}

        results = []
        for i, doc in enumerate(candidates):
            analysis = analysis_by_index.get(i + 1, {})
            results.append({
                **doc,
                "llm_score": analysis.get("relevance_score", doc["heuristic_score"]),
                "llm_reasoning": analysis.get("reasoning", ""),
                "relevance_description": analysis.get(
                    "relevance_description",
                    f"Documentation related to {', '.join(doc['keywords_matched'][:3])}",
                ),
            })

        return results

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print(f"    Warning: Failed to parse Claude response: {e}")
        # Return candidates with original heuristic scores as fallback
        return [
            {
                **doc,
                "llm_score": doc["heuristic_score"],
                "llm_reasoning": "Heuristic fallback (parse error)",
                "relevance_description": f"Documentation related to {', '.join(doc['keywords_matched'][:3])}",
            }
            for doc in candidates
        ]


def intelligent_discover(
    confluence_dir: Path,
    repo_name: str,
    output_path: Path,
    repo_description: str = "",
    max_docs: int = 50,
    min_relevance: float = 0.3,
    batch_size: int = 10,
) -> dict:
    """Main intelligent discovery function.

    1. Quick heuristic scan to get candidates
    2. Batch analyze with Claude
    3. Filter and rank results
    4. Generate output JSON
    """
    print(f"Intelligent Confluence Discovery for: {repo_name}")
    print(f"  Confluence directory: {confluence_dir}")

    if not confluence_dir.exists():
        print(f"  Warning: Confluence directory not found: {confluence_dir}")
        return _empty_result(repo_name)

    # Check Claude availability
    if not is_claude_available():
        print("  Warning: Claude not available, falling back to heuristic-only mode")
        return _heuristic_only_discover(confluence_dir, repo_name, output_path, max_docs)

    # Build search terms
    search_terms = build_search_terms(repo_name)
    print(f"  Search terms: {', '.join(search_terms)}")

    # Phase 1: Quick heuristic scan
    print("\nPhase 1: Quick heuristic scan...")
    candidates = quick_heuristic_scan(confluence_dir, search_terms, max_candidates=max_docs * 3)
    print(f"  Found {len(candidates)} candidate documents")

    if not candidates:
        print("  No candidates found matching search terms")
        return _empty_result(repo_name)

    # Phase 2: Intelligent analysis with Claude
    print("\nPhase 2: Intelligent analysis with Claude...")
    analyzed_docs = []

    # Process in batches
    total_batches = (len(candidates) + batch_size - 1) // batch_size
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        batch_num = i // batch_size + 1
        batch_results = analyze_batch_with_claude(
            batch, repo_name, repo_description, batch_num, total_batches
        )
        analyzed_docs.extend(batch_results)

    # Phase 3: Filter and rank
    print("\nPhase 3: Filtering and ranking...")

    # Filter by minimum relevance
    relevant_docs = [d for d in analyzed_docs if d.get("llm_score", 0) >= min_relevance]
    print(f"  {len(relevant_docs)} docs above {min_relevance} relevance threshold")

    # Sort by LLM score
    relevant_docs.sort(key=lambda d: d.get("llm_score", 0), reverse=True)

    # Take top max_docs
    final_docs = relevant_docs[:max_docs]
    print(f"  Selected top {len(final_docs)} documents")

    # Generate output
    return _generate_output(final_docs, repo_name, search_terms)


def _heuristic_only_discover(
    confluence_dir: Path, repo_name: str, output_path: Path, max_docs: int
) -> dict:
    """Fallback to heuristic-only discovery when Claude is unavailable."""
    search_terms = build_search_terms(repo_name)
    candidates = quick_heuristic_scan(confluence_dir, search_terms, max_candidates=max_docs)

    # Convert to output format
    docs = []
    for doc in candidates:
        docs.append({
            **doc,
            "llm_score": doc["heuristic_score"],
            "llm_reasoning": "Heuristic-only (Claude unavailable)",
            "relevance_description": f"Documentation related to {', '.join(doc['keywords_matched'][:3])}",
        })

    return _generate_output(docs, repo_name, search_terms)


def _generate_output(docs: list[dict], repo_name: str, search_terms: list[str]) -> dict:
    """Generate the external-docs.json output structure."""
    generated_at = datetime.now(UTC).isoformat()

    # Build discovered_docs list
    discovered_docs_list = []
    for doc in docs:
        discovered_docs_list.append({
            "title": doc["title"],
            "path": doc["path"],
            "relevance": doc.get("relevance_description", ""),
            "category": doc["category"],
            "confidence": round(doc.get("llm_score", doc.get("heuristic_score", 0)), 2),
            "reasoning": doc.get("llm_reasoning", ""),
        })

    # Build index additions (markdown table rows)
    index_additions = []
    for doc in discovered_docs_list[:10]:
        confluence_link = f"../../../context-sync/confluence/{doc['path']}"
        index_additions.append(f"| [{doc['title']}]({confluence_link}) | {doc['relevance']} |")

    # Count by category
    counts: dict[str, int] = {}
    for doc in discovered_docs_list:
        cat = doc["category"]
        counts[cat] = counts.get(cat, 0) + 1

    result = {
        "generated": generated_at,
        "repo": repo_name,
        "search_terms": search_terms,
        "analysis_method": "intelligent",
        "discovered_docs": discovered_docs_list,
        "index_additions": index_additions,
        "summary": {
            "total_found": len(discovered_docs_list),
            "by_category": dict(sorted(counts.items())),
        },
    }

    return result


def _empty_result(repo_name: str) -> dict:
    """Return empty result structure when no docs found."""
    return {
        "generated": datetime.now(UTC).isoformat(),
        "repo": repo_name,
        "search_terms": [],
        "analysis_method": "intelligent",
        "discovered_docs": [],
        "index_additions": [],
        "summary": {"total_found": 0, "by_category": {}},
    }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Intelligent Confluence documentation discoverer using Claude",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --repo-name webapp
  %(prog)s --repo-name my-service --max-docs 30
  %(prog)s --repo-name webapp --min-relevance 0.5
        """,
    )

    parser.add_argument(
        "--repo-name",
        "-r",
        required=True,
        help="Name of the repository to find docs for",
    )

    parser.add_argument(
        "--repo-description",
        "-d",
        default="",
        help="Optional description of the repository to help Claude understand context",
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
        "--max-docs",
        type=int,
        default=50,
        help="Maximum number of documents to include (default: 50)",
    )

    parser.add_argument(
        "--min-relevance",
        type=float,
        default=0.3,
        help="Minimum relevance score to include (default: 0.3)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of documents to analyze per Claude batch (default: 10)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without writing file",
    )

    args = parser.parse_args()

    output_path = args.output or (Path.cwd() / "docs" / "generated" / "external-docs.json")

    result = intelligent_discover(
        confluence_dir=args.confluence_dir,
        repo_name=args.repo_name,
        output_path=output_path,
        repo_description=args.repo_description,
        max_docs=args.max_docs,
        min_relevance=args.min_relevance,
        batch_size=args.batch_size,
    )

    if args.dry_run:
        print("\n=== DRY RUN - Output: ===")
        print(json.dumps(result, indent=2))
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nOutput written to: {output_path}")

    # Print summary
    summary = result.get("summary", {})
    print("\nSummary:")
    print(f"  Total documents found: {summary.get('total_found', 0)}")
    if summary.get("by_category"):
        print(f"  By category: {summary['by_category']}")

    # Print top 5 docs
    if result.get("discovered_docs"):
        print("\nTop 5 most relevant documents:")
        for doc in result["discovered_docs"][:5]:
            print(f"  - [{doc['confidence']:.0%}] {doc['title']}")
            print(f"    {doc['relevance']}")


if __name__ == "__main__":
    main()
