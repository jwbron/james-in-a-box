#!/usr/bin/env python3
"""
CLI tool for querying codebase indexes.

Provides quick access to codebase structure, patterns, and dependencies
without loading entire JSON files into LLM context.

Per ADR: LLM Documentation Index Strategy (Phase 2)
"""

import argparse
import json
import sys
from pathlib import Path


def load_index(index_path: Path) -> dict:
    """Load a JSON index file."""
    if not index_path.exists():
        print(f"Error: Index not found: {index_path}")
        print("Run index-generator.py first to create indexes.")
        sys.exit(1)

    with open(index_path) as f:
        return json.load(f)


def cmd_component(args, indexes_dir: Path):
    """Find component by name."""
    codebase = load_index(indexes_dir / "codebase.json")

    name_lower = args.name.lower()
    matches = []

    for component in codebase.get("components", []):
        if name_lower in component.get("name", "").lower():
            matches.append(component)

    if not matches:
        print(f"No components found matching '{args.name}'")
        return

    print(f"Found {len(matches)} component(s) matching '{args.name}':\n")
    for comp in matches[:10]:  # Limit output
        print(f"  {comp.get('type', 'unknown'):8} {comp['name']}")
        print(f"           File: {comp.get('file', 'unknown')}:{comp.get('line', '?')}")
        if "description" in comp:
            print(f"           Desc: {comp['description'][:80]}")
        if "methods" in comp:
            print(f"           Methods: {', '.join(comp['methods'][:5])}")
        print()


def cmd_pattern(args, indexes_dir: Path):
    """Show pattern details."""
    patterns = load_index(indexes_dir / "patterns.json")

    if args.name:
        # Show specific pattern
        pattern_name = args.name.lower()
        pattern_data = patterns.get("patterns", {}).get(pattern_name)

        if not pattern_data:
            available = list(patterns.get("patterns", {}).keys())
            print(f"Pattern '{args.name}' not found.")
            print(f"Available patterns: {', '.join(available)}")
            return

        print(f"Pattern: {args.name}")
        print(f"Description: {pattern_data.get('description', 'N/A')}")
        print(f"\nExamples ({len(pattern_data.get('examples', []))} total):")
        for ex in pattern_data.get("examples", [])[:5]:
            print(f"  - {ex}")
        if len(pattern_data.get("examples", [])) > 5:
            print(f"  ... and {len(pattern_data['examples']) - 5} more")
        print("\nConventions:")
        for conv in pattern_data.get("conventions", []):
            print(f"  • {conv}")
    else:
        # List all patterns
        print("Available patterns:\n")
        for name, data in patterns.get("patterns", {}).items():
            example_count = len(data.get("examples", []))
            print(f"  {name:20} ({example_count} examples)")
            print(f"    {data.get('description', 'N/A')}")
            print()


def cmd_deps(args, indexes_dir: Path):
    """Show dependencies."""
    deps = load_index(indexes_dir / "dependencies.json")

    if args.component:
        # Show deps for specific file/component
        internal = deps.get("internal", {})
        file_deps = internal.get(args.component)

        if file_deps:
            print(f"Dependencies for {args.component}:")
            for dep in file_deps:
                print(f"  - {dep}")
        else:
            print(f"No internal dependencies found for '{args.component}'")
            print("Try using a full path like 'config/host_config.py'")
    else:
        # Show external deps summary
        external = deps.get("external", {})

        # Separate stdlib from third-party
        stdlib = {
            "os",
            "sys",
            "json",
            "pathlib",
            "typing",
            "logging",
            "argparse",
            "subprocess",
            "tempfile",
            "traceback",
            "ast",
            "hashlib",
            "re",
            "dataclasses",
            "datetime",
            "enum",
            "collections",
            "time",
            "signal",
            "threading",
            "pickle",
            "abc",
            "base64",
            "concurrent",
            "urllib",
            "uuid",
            "contextlib",
            "importlib",
            "unittest",
            "html",
        }

        third_party = {k: v for k, v in external.items() if k not in stdlib}

        print(f"External dependencies ({len(third_party)} third-party packages):\n")
        for pkg, version in sorted(third_party.items()):
            print(f"  {pkg:20} {version}")


def cmd_structure(args, indexes_dir: Path):
    """Show project structure."""
    codebase = load_index(indexes_dir / "codebase.json")

    def print_tree(node: dict, prefix: str = "", name: str = ""):
        if name:
            desc = node.get("description", "")
            print(f"{prefix}{name:30} {desc}")

        children = node.get("children", {})
        child_items = list(children.items())

        for i, (child_name, child_node) in enumerate(child_items):
            is_last = i == len(child_items) - 1
            connector = "└── " if is_last else "├── "
            print_tree(child_node, prefix + connector, child_name)

    structure = codebase.get("structure", {})
    print(f"Project: {codebase.get('project', 'unknown')}\n")
    print_tree(structure)


def cmd_summary(args, indexes_dir: Path):
    """Show codebase summary."""
    codebase = load_index(indexes_dir / "codebase.json")
    patterns = load_index(indexes_dir / "patterns.json")
    deps = load_index(indexes_dir / "dependencies.json")

    summary = codebase.get("summary", {})

    print(f"Codebase Summary: {codebase.get('project', 'unknown')}")
    print(f"Generated: {codebase.get('generated', 'unknown')}")
    print()
    print(f"  Python files:  {summary.get('total_python_files', 0)}")
    print(f"  Classes:       {summary.get('total_classes', 0)}")
    print(f"  Functions:     {summary.get('total_functions', 0)}")
    print()
    print(f"  Patterns detected: {len(patterns.get('patterns', {}))}")
    for pattern in patterns.get("patterns", {}):
        print(f"    - {pattern}")
    print()

    # Count third-party deps
    stdlib = {
        "os",
        "sys",
        "json",
        "pathlib",
        "typing",
        "logging",
        "argparse",
        "subprocess",
        "tempfile",
        "traceback",
        "ast",
        "hashlib",
        "re",
        "dataclasses",
        "datetime",
        "enum",
        "collections",
        "time",
        "signal",
        "threading",
        "pickle",
        "abc",
        "base64",
        "concurrent",
        "urllib",
        "uuid",
        "contextlib",
        "importlib",
        "unittest",
        "html",
    }
    external = deps.get("external", {})
    third_party = {k for k in external if k not in stdlib}
    print(f"  External packages: {len(third_party)}")


def cmd_search(args, indexes_dir: Path):
    """Search across all indexes."""
    codebase = load_index(indexes_dir / "codebase.json")
    patterns = load_index(indexes_dir / "patterns.json")

    query = args.query.lower()
    results = []

    # Search components
    for comp in codebase.get("components", []):
        if query in comp.get("name", "").lower():
            results.append(("component", comp["name"], comp.get("file", "")))
        if query in comp.get("description", "").lower():
            results.append(("component", comp["name"], comp.get("description", "")[:60]))

    # Search patterns
    for pattern_name, pattern_data in patterns.get("patterns", {}).items():
        if query in pattern_name.lower():
            results.append(("pattern", pattern_name, pattern_data.get("description", "")))
        if query in pattern_data.get("description", "").lower():
            results.append(("pattern", pattern_name, pattern_data.get("description", "")))

    if not results:
        print(f"No results found for '{args.query}'")
        return

    print(f"Found {len(results)} result(s) for '{args.query}':\n")
    seen = set()
    for result_type, name, context in results[:20]:
        key = (result_type, name)
        if key not in seen:
            seen.add(key)
            print(f"  [{result_type:9}] {name}")
            if context:
                print(f"              {context}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="Query codebase indexes for LLM navigation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary                    # Show codebase overview
  %(prog)s component GitHubWatcher    # Find component by name
  %(prog)s pattern                    # List all patterns
  %(prog)s pattern connector          # Show connector pattern details
  %(prog)s deps                       # Show external dependencies
  %(prog)s structure                  # Show project structure
  %(prog)s search notification        # Search across all indexes
        """,
    )

    parser.add_argument(
        "--indexes",
        "-i",
        type=Path,
        default=Path(__file__).parent.parent.parent.parent / "docs" / "generated",
        help="Path to indexes directory (default: docs/generated)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # summary command
    subparsers.add_parser("summary", help="Show codebase summary")

    # component command
    comp_parser = subparsers.add_parser("component", help="Find component by name")
    comp_parser.add_argument("name", help="Component name (partial match)")

    # pattern command
    pattern_parser = subparsers.add_parser("pattern", help="Show patterns")
    pattern_parser.add_argument("name", nargs="?", help="Pattern name (optional)")

    # deps command
    deps_parser = subparsers.add_parser("deps", help="Show dependencies")
    deps_parser.add_argument("component", nargs="?", help="File path for internal deps")

    # structure command
    subparsers.add_parser("structure", help="Show project structure")

    # search command
    search_parser = subparsers.add_parser("search", help="Search all indexes")
    search_parser.add_argument("query", help="Search query")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    indexes_dir = args.indexes.resolve()

    commands = {
        "summary": cmd_summary,
        "component": cmd_component,
        "pattern": cmd_pattern,
        "deps": cmd_deps,
        "structure": cmd_structure,
        "search": cmd_search,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args, indexes_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
