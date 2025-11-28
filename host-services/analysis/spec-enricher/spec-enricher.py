#!/usr/bin/env python3
"""
Spec Enricher CLI for LLM Documentation Strategy

Command-line interface for enriching task specs with relevant documentation
links and code examples. Uses the shared enrichment module.

Per ADR: LLM Documentation Index Strategy (Phase 3)

Usage:
  # Enrich from file
  python3 spec-enricher.py --spec task.md

  # Enrich from stdin
  echo "Add authentication to API" | python3 spec-enricher.py

  # Output as YAML
  python3 spec-enricher.py --spec task.md --format yaml

  # Just get the context (no original content)
  python3 spec-enricher.py --spec task.md --context-only
"""

import argparse
import sys
from pathlib import Path


# Add shared directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from enrichment import (
    CodeExample,
    DocReference,
    EnrichedContext,
    SpecEnricher,
)


# Re-export for backwards compatibility
__all__ = ["CodeExample", "DocReference", "EnrichedContext", "SpecEnricher"]


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich task specs with relevant documentation and code references",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --spec task.md                    # Enrich a spec file
  echo "Add auth" | %(prog)s                 # Enrich from stdin
  %(prog)s --spec task.md --format yaml      # Output as YAML
  %(prog)s --spec task.md --context-only     # Just the context
        """,
    )

    parser.add_argument(
        "--spec",
        "-s",
        type=Path,
        help="Path to spec file to enrich (reads from stdin if not provided)",
    )

    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=Path(__file__).parent.parent.parent.parent,  # james-in-a-box root
        help="Project root (default: james-in-a-box)",
    )

    parser.add_argument(
        "--format",
        "-f",
        choices=["yaml", "markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "--context-only",
        "-c",
        action="store_true",
        help="Output only the context, not the original spec",
    )

    args = parser.parse_args()

    # Read spec content
    if args.spec:
        if not args.spec.exists():
            print(f"Error: Spec file not found: {args.spec}", file=sys.stderr)
            sys.exit(1)
        spec_text = args.spec.read_text()
    elif not sys.stdin.isatty():
        spec_text = sys.stdin.read()
    else:
        print("Error: No spec provided. Use --spec or pipe content via stdin.", file=sys.stderr)
        sys.exit(1)

    if not spec_text.strip():
        print("Error: Empty spec content", file=sys.stderr)
        sys.exit(1)

    # Create enricher and process
    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)

    enricher = SpecEnricher(project_root)
    context = enricher.enrich(spec_text)

    # Format output
    if args.format == "yaml":
        context_str = enricher.format_yaml(context)
    elif args.format == "json":
        context_str = enricher.format_json(context)
    else:
        context_str = enricher.format_markdown(context)

    # Output
    if args.context_only:
        print(context_str)
    # Include original spec with context injected
    elif args.format == "yaml":
        print(context_str)
        print()
        print("# Original spec:")
        print(spec_text)
    else:
        print(context_str)
        print()
        print("---")
        print()
        print(spec_text)


if __name__ == "__main__":
    main()
