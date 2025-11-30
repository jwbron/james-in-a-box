#!/usr/bin/env python3
"""
Inefficiency Detector - Phase 2 of ADR-LLM-Inefficiency-Reporting

Orchestrates all category-specific detectors to analyze LLM trace sessions
and identify processing inefficiencies.

Usage:
    from inefficiency_detector import InefficiencyDetector

    detector = InefficiencyDetector()
    report = detector.analyze_session(session_id)
    print(f"Inefficiency rate: {report.inefficiency_rate}%")

CLI Usage:
    python inefficiency_detector.py analyze <session_id>
    python inefficiency_detector.py analyze-period --since 2025-11-01 --until 2025-11-30
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add trace-collector to path
trace_collector_path = Path(__file__).parent.parent / "trace-collector"
sys.path.insert(0, str(trace_collector_path))

from trace_reader import TraceReader

from detectors.tool_discovery_detector import ToolDiscoveryDetector
from detectors.tool_execution_detector import ToolExecutionDetector
from detectors.resource_efficiency_detector import ResourceEfficiencyDetector
from inefficiency_schema import (
    AggregateInefficiencyReport,
    SessionInefficiencyReport,
)


class InefficiencyDetector:
    """
    Main inefficiency detection orchestrator.

    Coordinates all category-specific detectors to produce comprehensive
    inefficiency reports.
    """

    def __init__(self, traces_dir: Path | None = None, config: dict | None = None):
        """
        Initialize the inefficiency detector.

        Args:
            traces_dir: Directory containing trace files (default: ~/sharing/traces)
            config: Optional configuration for detectors
        """
        self.trace_reader = TraceReader(traces_dir)
        self.config = config or {}

        # Initialize all category detectors
        # Note: Only implementing 3 high-value categories initially
        # Remaining categories (2, 3, 5, 6) can be added later
        self.detectors = [
            ToolDiscoveryDetector(self.config.get("tool_discovery", {})),
            ToolExecutionDetector(self.config.get("tool_execution", {})),
            ResourceEfficiencyDetector(self.config.get("resource_efficiency", {})),
        ]

    def analyze_session(self, session_id: str) -> SessionInefficiencyReport | None:
        """
        Analyze a single trace session for inefficiencies.

        Args:
            session_id: The session ID to analyze

        Returns:
            SessionInefficiencyReport or None if session not found
        """
        # Get session metadata
        metadata = self.trace_reader.get_session_metadata(session_id)
        if not metadata:
            return None

        # Get session events
        events = self.trace_reader.get_session_events(session_id)
        if not events:
            return None

        # Calculate total tokens for the session
        total_tokens = metadata.total_tokens_generated + metadata.total_input_tokens

        # Create report
        report = SessionInefficiencyReport(
            session_id=session_id,
            task_id=metadata.task_id,
            total_tokens=total_tokens,
            total_wasted_tokens=0,
            inefficiency_rate=0.0,
        )

        # Run all detectors
        for detector in self.detectors:
            detected = detector.detect(events)
            for inefficiency in detected:
                report.add_inefficiency(inefficiency)

        return report

    def analyze_period(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        task_id: str | None = None,
        repository: str | None = None,
    ) -> AggregateInefficiencyReport:
        """
        Analyze multiple sessions over a time period.

        Args:
            since: Start of time range (inclusive)
            until: End of time range (inclusive)
            task_id: Optional filter by Beads task ID
            repository: Optional filter by repository

        Returns:
            AggregateInefficiencyReport with all sessions
        """
        # Get sessions in period
        sessions = self.trace_reader.list_sessions(
            since=since,
            until=until,
            task_id=task_id,
            repository=repository,
        )

        # Format time period
        since_str = since.strftime("%Y-%m-%d") if since else "beginning"
        until_str = until.strftime("%Y-%m-%d") if until else "now"
        time_period = f"{since_str} to {until_str}"

        # Create aggregate report
        aggregate = AggregateInefficiencyReport(
            time_period=time_period,
            total_sessions=0,
            total_tokens=0,
            total_wasted_tokens=0,
            average_inefficiency_rate=0.0,
        )

        # Analyze each session
        for session_summary in sessions:
            session_id = session_summary["session_id"]
            report = self.analyze_session(session_id)

            if report and len(report.inefficiencies) > 0:
                aggregate.add_session_report(report)

        # Compute top issues
        aggregate.compute_top_issues(limit=5)

        return aggregate

    def export_report(
        self, report: SessionInefficiencyReport | AggregateInefficiencyReport, output_path: Path
    ) -> None:
        """
        Export a report to JSON file.

        Args:
            report: The report to export
            output_path: Where to write the JSON file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)

    def generate_markdown_report(
        self, report: AggregateInefficiencyReport, output_path: Path
    ) -> None:
        """
        Generate a human-readable markdown report.

        Args:
            report: The aggregate report to format
            output_path: Where to write the markdown file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            # Header
            f.write(f"# LLM Inefficiency Report - {report.time_period}\n\n")

            # Executive Summary
            f.write("## Executive Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Total Sessions | {report.total_sessions} |\n")
            f.write(f"| Total Tokens | {report.total_tokens:,} |\n")
            f.write(f"| Total Wasted Tokens | {report.total_wasted_tokens:,} |\n")
            f.write(f"| Average Inefficiency Rate | {report.average_inefficiency_rate:.1f}% |\n\n")

            # Top Issues
            if report.top_issues:
                f.write("## Top Issues\n\n")
                for i, issue in enumerate(report.top_issues, 1):
                    f.write(f"### {i}. {issue['sub_category'].replace('_', ' ').title()}\n\n")
                    f.write(f"**Category:** {issue['category']}\n\n")
                    f.write(f"**Occurrences:** {issue['occurrences']}\n\n")
                    f.write(f"**Total Waste:** {issue['total_waste_tokens']:,} tokens\n\n")
                    f.write(f"**Example:** {issue['example_description']}\n\n")
                    f.write(f"**Recommendation:** {issue['recommendation']}\n\n")

            # Category Breakdown
            f.write("## Inefficiency Breakdown by Category\n\n")
            if report.category_counts:
                total_count = sum(report.category_counts.values())
                for category, count in sorted(
                    report.category_counts.items(), key=lambda x: -x[1]
                ):
                    percentage = (count / total_count * 100) if total_count > 0 else 0
                    bar = "█" * int(percentage / 2)  # 2% per block
                    f.write(f"{category.replace('_', ' ').title():<25} {bar} {percentage:.0f}%\n")
                f.write("\n")

            # Severity Breakdown
            f.write("## Inefficiency Breakdown by Severity\n\n")
            if report.severity_counts:
                for severity in ["high", "medium", "low"]:
                    count = report.severity_counts.get(severity, 0)
                    f.write(f"- **{severity.upper()}**: {count}\n")
                f.write("\n")

            # Detailed Sessions (top 5 by inefficiency rate)
            f.write("## Sessions with Highest Inefficiency\n\n")
            top_sessions = sorted(
                report.sessions, key=lambda s: s.inefficiency_rate, reverse=True
            )[:5]

            for session in top_sessions:
                f.write(f"### Session {session.session_id}\n\n")
                f.write(f"**Task:** {session.task_id or 'N/A'}\n\n")
                f.write(f"**Inefficiency Rate:** {session.inefficiency_rate:.1f}%\n\n")
                f.write(
                    f"**Wasted Tokens:** {session.total_wasted_tokens:,} / {session.total_tokens:,}\n\n"
                )
                f.write(f"**Issues Found:** {len(session.inefficiencies)}\n\n")

                # List issues
                if session.inefficiencies:
                    f.write("**Issues:**\n")
                    for ineff in session.inefficiencies:
                        f.write(f"- [{ineff.severity.value.upper()}] {ineff.description}\n")
                    f.write("\n")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="LLM Inefficiency Detector - Analyze trace sessions for processing inefficiencies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Analyze single session
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a single session")
    analyze_parser.add_argument("session_id", help="Session ID to analyze")
    analyze_parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")

    # Analyze period
    period_parser = subparsers.add_parser("analyze-period", help="Analyze sessions over time period")
    period_parser.add_argument("--since", help="Start date (YYYY-MM-DD)")
    period_parser.add_argument("--until", help="End date (YYYY-MM-DD)")
    period_parser.add_argument("--task", help="Filter by task ID")
    period_parser.add_argument("--repo", help="Filter by repository")
    period_parser.add_argument("--output", "-o", help="Output JSON file")
    period_parser.add_argument("--markdown", "-m", help="Output markdown report file")

    args = parser.parse_args()

    detector = InefficiencyDetector()

    if args.command == "analyze":
        report = detector.analyze_session(args.session_id)
        if not report:
            print(f"Session not found: {args.session_id}", file=sys.stderr)
            sys.exit(1)

        if args.output:
            detector.export_report(report, Path(args.output))
            print(f"Report exported to {args.output}")
        else:
            print(json.dumps(report.to_dict(), indent=2))

    elif args.command == "analyze-period":
        since = datetime.fromisoformat(args.since) if args.since else None
        until = datetime.fromisoformat(args.until) if args.until else None

        report = detector.analyze_period(
            since=since, until=until, task_id=args.task, repository=args.repo
        )

        if args.output:
            detector.export_report(report, Path(args.output))
            print(f"JSON report exported to {args.output}")

        if args.markdown:
            detector.generate_markdown_report(report, Path(args.markdown))
            print(f"Markdown report exported to {args.markdown}")

        if not args.output and not args.markdown:
            # Print summary to stdout
            print(f"Analyzed {report.total_sessions} sessions")
            print(f"Total tokens: {report.total_tokens:,}")
            print(f"Wasted tokens: {report.total_wasted_tokens:,}")
            print(f"Average inefficiency rate: {report.average_inefficiency_rate:.1f}%")
            print()
            print("Top Issues:")
            for issue in report.top_issues:
                print(f"  - {issue['sub_category']}: {issue['occurrences']} occurrences")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
