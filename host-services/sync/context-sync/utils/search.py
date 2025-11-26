#!/usr/bin/env python3
"""
Search functionality for synced Confluence documentation.
"""

import sys
from pathlib import Path

from connectors.confluence.config import ConfluenceConfig
from dotenv import load_dotenv


def search_documentation(query: str, space: str | None = None, max_results: int = 50) -> list[dict]:
    """Search through synced documentation."""
    load_dotenv()
    config = ConfluenceConfig()

    output_dir = Path(config.OUTPUT_DIR)
    if not output_dir.exists():
        print("No synced documentation found. Run 'make docs-sync' first.")
        return []

    results = []
    query_lower = query.lower()

    # Search through all spaces or specific space
    spaces_to_search = [space] if space else [d.name for d in output_dir.iterdir() if d.is_dir()]

    for space_dir in spaces_to_search:
        space_path = output_dir / space_dir
        if not space_path.exists():
            continue

        # Search through markdown files in this space
        for md_file in space_path.glob("*.md"):
            if md_file.name == "README.md":
                continue  # Skip index files

            try:
                with open(md_file, encoding="utf-8") as f:
                    content = f.read()

                # Simple text search
                if query_lower in content.lower():
                    # Extract title from first line
                    lines = content.split("\n")
                    title = lines[0].replace("# ", "").strip() if lines else md_file.stem

                    # Find context around match
                    content_lower = content.lower()
                    match_pos = content_lower.find(query_lower)
                    start = max(0, match_pos - 200)
                    end = min(len(content), match_pos + len(query_lower) + 200)
                    context = content[start:end].strip()

                    results.append(
                        {
                            "title": title,
                            "space": space_dir,
                            "file": str(md_file),
                            "context": context,
                            "match_position": match_pos,
                        }
                    )

                    if len(results) >= max_results:
                        break

            except Exception as e:
                print(f"Error reading {md_file}: {e}")

    # Sort by relevance (simple: earlier matches are more relevant)
    results.sort(key=lambda x: x["match_position"])

    return results[:max_results]


def list_spaces():
    """List all available spaces."""
    load_dotenv()
    config = ConfluenceConfig()

    output_dir = Path(config.OUTPUT_DIR)
    if not output_dir.exists():
        print("No synced documentation found. Run 'make docs-sync' first.")
        return

    spaces = [d.name for d in output_dir.iterdir() if d.is_dir()]

    print("Available spaces:")
    for space in sorted(spaces):
        space_path = output_dir / space
        md_files = list(space_path.glob("*.md"))
        print(f"  {space}: {len(md_files)} pages")


def main():
    """Main search function."""
    if len(sys.argv) < 2:
        print("Usage: python search.py <query> [--space SPACE] [--max-results N]")
        return

    query = sys.argv[1]

    # Parse options
    space = None
    max_results = 50

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--space" and i + 1 < len(sys.argv):
            space = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--max-results" and i + 1 < len(sys.argv):
            max_results = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--list-spaces":
            list_spaces()
            return
        else:
            i += 1

    results = search_documentation(query, space, max_results)

    if not results:
        print(f"No results found for '{query}'")
        return

    print(f"Found {len(results)} results for '{query}':")
    print()

    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']} (in {result['space']})")
        print(f"   File: {result['file']}")
        print(f"   Context: {result['context'][:100]}...")
        print()


if __name__ == "__main__":
    main()
