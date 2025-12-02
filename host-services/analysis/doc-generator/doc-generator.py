#!/usr/bin/env python3
"""
LLM Documentation Generator - Host-side wrapper.

This script runs on the HOST and delegates all documentation generation work to
the jib container via `jib --exec`. This ensures Claude can be called properly
(Claude requires the container environment).

The actual 4-agent pipeline logic lives in:
    jib-container/jib-tasks/analysis/doc-generator-processor.py

Pipeline phases (all run in container):
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

IMPORTANT: This host-side wrapper does NOT import Claude directly.
All Claude operations happen inside the container via jib_exec.
"""

import argparse
import json
import sys
from pathlib import Path

# Add host-services/shared to path for jib_exec
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared"))
from jib_exec import is_jib_available, jib_exec


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

This script delegates to the jib container for documentation generation,
ensuring Claude can be called properly from the container environment.

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

    # Check if jib is available
    if not is_jib_available():
        print("ERROR: jib command not available", file=sys.stderr)
        print("Make sure jib is installed and in PATH", file=sys.stderr)
        sys.exit(1)

    project_root = args.project.resolve()
    if not project_root.exists():
        print(f"Error: Project root does not exist: {project_root}", file=sys.stderr)
        sys.exit(1)

    # Build context for processor
    context = {
        "project_root": str(project_root),
        "use_claude": not args.no_claude,
        "verbose": args.verbose,
        "doc_type": args.type,
        "dry_run": args.dry_run,
    }

    if args.output:
        context["output_dir"] = str(args.output.resolve())

    # Determine task type
    if args.list_topics:
        task_type = "list_topics"
    elif args.all:
        task_type = "generate_all"
    elif args.topic:
        task_type = "generate"
        context["topic"] = args.topic
    else:
        parser.print_help()
        print("\nError: Specify --topic, --all, or --list-topics", file=sys.stderr)
        sys.exit(1)

    print(f"Starting documentation generation (task={task_type})...")
    print("Delegating to jib container for Claude-enabled processing...")

    # Invoke the container-side processor
    result = jib_exec(
        processor="jib-container/jib-tasks/analysis/doc-generator-processor.py",
        task_type=task_type,
        context=context,
        timeout=600,  # 10 minutes for full generation with Claude
    )

    if not result.success:
        print(f"ERROR: Documentation generation failed: {result.error}", file=sys.stderr)
        if result.stderr:
            print(f"stderr: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)

    # Process result
    if result.json_output:
        output = result.json_output

        if args.json:
            print(json.dumps(output, indent=2))
            return

        if output.get("success"):
            if task_type == "list_topics":
                topics = output.get("topics", [])
                print("\nAvailable documentation topics:")
                print()
                print(f"{'Topic':<20} {'Source':<20} {'Examples':<10} Description")
                print("-" * 80)
                for topic in topics:
                    print(
                        f"{topic['name']:<20} {topic['source']:<20} "
                        f"{topic['examples_count']:<10} {topic.get('description', '')[:30]}"
                    )

            elif task_type == "generate":
                print("\n" + "=" * 60)
                print("DOCUMENTATION GENERATED")
                print("=" * 60)
                print(f"Topic: {output.get('topic')}")
                print(f"Type: {output.get('doc_type')}")
                print(f"Analysis: {output.get('analysis_source', 'unknown')}")

                if output.get("output_path"):
                    print(f"Output: {output.get('output_path')}")
                elif output.get("preview"):
                    print("\n--- Preview ---")
                    print(output.get("preview")[:1500])
                    if len(output.get("preview", "")) > 1500:
                        print(f"\n... (truncated)")

                if output.get("issues"):
                    print("\nIssues:")
                    for issue in output.get("issues"):
                        print(f"  - {issue}")

                if output.get("suggestions"):
                    print("\nSuggestions:")
                    for suggestion in output.get("suggestions"):
                        print(f"  - {suggestion}")

                print("=" * 60)

            elif task_type == "generate_all":
                print("\n" + "=" * 60)
                print("DOCUMENTATION GENERATION SUMMARY")
                print("=" * 60)
                print(f"Total: {output.get('total', 0)}")
                print(f"Successful: {output.get('successful', 0)}")

                results = output.get("results", [])
                for r in results:
                    status = "OK" if r.get("success") else "FAILED"
                    print(f"  [{status}] {r.get('topic')}")

                print("=" * 60)

        else:
            print(f"ERROR: {output.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    else:
        # No JSON output - print raw output
        print("Output from container:")
        print(result.stdout)


if __name__ == "__main__":
    main()
