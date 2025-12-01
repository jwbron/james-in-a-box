#!/usr/bin/env python3
"""
Beads Integration Analyzer for jib (James-in-a-Box) - Host-side wrapper.

This script runs on the HOST and delegates all analysis work to the jib container
via `jib --exec`. This ensures all file operations happen in an isolated git worktree,
preventing uncommitted changes from appearing in the host's main worktree.

The actual analysis logic lives in:
    jib-container/jib-tasks/analysis/beads-analyzer-processor.py

Metrics tracked:
1. Task Lifecycle - Are tasks properly created, progressed, and closed?
2. Context Continuity - Are related tasks properly linked?
3. Task Quality - Are titles searchable? Are notes meaningful?
4. Integration Coverage - What percentage of work is tracked?
5. Abandonment Patterns - How many tasks are left hanging?

Reports: Creates PRs with reports committed to docs/analysis/beads/ in the repo.
         Keeps only the last 5 reports (deletes older ones when creating PR #6).

Runs on host via systemd timer:
- Weekly (checks if last run was within 7 days)
- Can force run with --force flag

Usage:
    beads-analyzer.py [--days N] [--force] [--skip-claude]

Example:
    beads-analyzer.py --days 7
    beads-analyzer.py --force
    beads-analyzer.py --days 30 --skip-claude
"""

import argparse
import sys
from pathlib import Path


# Add host-services/shared to path for jib_exec
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared"))
from jib_exec import is_jib_available, jib_exec


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Beads task tracking integration health",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script delegates to the jib container for analysis, ensuring all
file operations happen in an isolated git worktree.

Examples:
  %(prog)s                    # Run if last analysis was >7 days ago
  %(prog)s --force            # Force run regardless of schedule
  %(prog)s --days 30          # Analyze last 30 days
  %(prog)s --skip-claude      # Skip AI analysis for faster results
        """,
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to analyze (default: 7)"
    )
    parser.add_argument("--force", action="store_true", help="Force analysis even if run recently")
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip Claude-powered AI analysis (faster but less insightful)",
    )

    args = parser.parse_args()

    # Check if jib is available
    if not is_jib_available():
        print("ERROR: jib command not available", file=sys.stderr)
        print("Make sure jib is installed and in PATH", file=sys.stderr)
        sys.exit(1)

    print(f"Starting Beads integration analysis (days={args.days}, force={args.force})...")
    print("Delegating to jib container for isolated worktree operations...")

    # Invoke the container-side processor
    result = jib_exec(
        processor="jib-container/jib-tasks/analysis/beads-analyzer-processor.py",
        task_type="run_analysis",
        context={
            "days": args.days,
            "force": args.force,
            "skip_claude": args.skip_claude,
        },
        timeout=600,  # 10 minutes for full analysis with Claude
    )

    if not result.success:
        print(f"ERROR: Analysis failed: {result.error}", file=sys.stderr)
        if result.stderr:
            print(f"stderr: {result.stderr[:500]}", file=sys.stderr)
        sys.exit(1)

    # Process result
    if result.json_output:
        output = result.json_output
        if output.get("success"):
            result_data = output.get("result", {})

            if result_data.get("skipped"):
                print(f"Analysis skipped: {result_data.get('reason')}")
                print("Use --force to run anyway")
                sys.exit(0)

            # Print summary
            print("\n" + "=" * 60)
            print("BEADS INTEGRATION HEALTH REPORT")
            print("=" * 60)
            print(f"Health Score: {result_data.get('health_score', '?')}/100")
            print(f"Total Tasks: {result_data.get('total_tasks', '?')}")
            print(f"  Created: {result_data.get('tasks_created', '?')}")
            print(f"  Closed: {result_data.get('tasks_closed', '?')}")
            print(f"  Abandoned: {result_data.get('tasks_abandoned', '?')}")
            print()
            print("Issues:")
            print(f"  High: {result_data.get('issues_high', '?')}")
            print(f"  Medium: {result_data.get('issues_medium', '?')}")
            print(f"  Low: {result_data.get('issues_low', '?')}")
            print()
            print(f"Report: {result_data.get('report_path', 'N/A')}")

            pr_url = result_data.get("pr_url")
            pr_error = result_data.get("pr_error")

            if pr_url:
                print(f"PR Created: {pr_url}")
            elif pr_error:
                print(f"PR Creation Error: {pr_error}")

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
