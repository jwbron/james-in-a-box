#!/usr/bin/env python3
"""
Log Analyzer - Main entry point for log analysis.

Combines log aggregation, error extraction, and classification
into a unified analysis workflow.

Usage:
    # Full analysis
    python -m log_analyzer.log_analyzer --analyze

    # Just aggregate logs
    python -m log_analyzer.log_analyzer --aggregate

    # Generate summary
    python -m log_analyzer.log_analyzer --summary
"""

import argparse
import json

# Add shared library to path
import sys
from datetime import datetime, timedelta
from pathlib import Path


jib_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(jib_root / "shared"))

from jib_logging import get_logger

from .error_classifier import ClassifiedError, ErrorClassifier
from .error_extractor import ErrorExtractor, ExtractedError
from .log_aggregator import LogAggregator


logger = get_logger("log-analyzer")


class LogAnalyzer:
    """Unified log analysis interface.

    Combines aggregation, extraction, and classification into
    a single workflow for easy use.

    Usage:
        analyzer = LogAnalyzer()

        # Full analysis
        summary = analyzer.analyze()

        # Generate report
        report = analyzer.generate_summary()
    """

    def __init__(
        self,
        logs_dir: Path | None = None,
        model: str = "claude-3-5-haiku-latest",
        timeout: int = 60,
    ):
        """Initialize the analyzer.

        Args:
            logs_dir: Base directory for logs (default: ~/.jib-sharing/logs)
            model: Claude model for classification
            timeout: Timeout in seconds for Claude CLI calls (default: 60)
        """
        self.logs_dir = logs_dir or (Path.home() / ".jib-sharing" / "logs")

        self.aggregator = LogAggregator(output_dir=self.logs_dir)
        self.extractor = ErrorExtractor(logs_dir=self.logs_dir)
        self.classifier = ErrorClassifier(logs_dir=self.logs_dir, model=model, timeout=timeout)

        self.summaries_dir = self.logs_dir / "analysis" / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)

    def aggregate(self, hours: int = 24) -> Path:
        """Aggregate logs from all sources.

        Args:
            hours: Include logs from the last N hours

        Returns:
            Path to aggregated log file
        """
        since = datetime.now() - timedelta(hours=hours)
        return self.aggregator.aggregate(since=since)

    def extract_errors(self, hours: int = 24) -> list[ExtractedError]:
        """Extract errors from aggregated logs.

        Args:
            hours: Include logs from the last N hours

        Returns:
            List of extracted errors
        """
        return self.extractor.extract_recent(hours=hours)

    def classify_errors(
        self,
        errors: list[ExtractedError],
        max_calls: int = 50,
    ) -> list[ClassifiedError]:
        """Classify errors using Claude.

        Args:
            errors: List of errors to classify
            max_calls: Maximum Claude API calls

        Returns:
            List of classified errors
        """
        return self.classifier.classify_errors(errors, max_classifications=max_calls)

    def analyze(
        self,
        hours: int = 24,
        max_calls: int = 50,
    ) -> dict:
        """Run full analysis pipeline.

        1. Aggregate logs
        2. Extract errors
        3. Classify errors
        4. Generate summary

        Args:
            hours: Include logs from the last N hours
            max_calls: Maximum Claude API calls

        Returns:
            Analysis summary dict
        """
        logger.info(f"Starting analysis for last {hours} hours")

        # Step 1: Aggregate
        logger.info("Step 1/4: Aggregating logs...")
        aggregated_file = self.aggregate(hours=hours)

        # Step 2: Extract
        logger.info("Step 2/4: Extracting errors...")
        errors = self.extract_errors(hours=hours)
        errors_file = self.extractor.save_errors(errors)

        # Step 3: Classify
        logger.info("Step 3/4: Classifying errors...")
        classified = self.classify_errors(errors, max_calls=max_calls)
        classifications_file = self.classifier.save_classifications(classified)

        # Step 4: Generate summary
        logger.info("Step 4/4: Generating summary...")
        summary = self.generate_summary(classified)
        summary_file = self.save_summary(summary)

        return {
            "aggregated_file": str(aggregated_file),
            "errors_file": str(errors_file),
            "classifications_file": str(classifications_file),
            "summary_file": str(summary_file),
            "total_errors": len(errors),
            "classified_errors": len(classified),
            "summary": summary,
        }

    def generate_summary(
        self,
        classifications: list[ClassifiedError] | None = None,
        date: datetime | None = None,
    ) -> dict:
        """Generate analysis summary.

        Args:
            classifications: List of classified errors (loads from file if None)
            date: Date to summarize (default: today)

        Returns:
            Summary dictionary
        """
        if date is None:
            date = datetime.now()

        if classifications is None:
            # Load from file
            date_str = date.strftime("%Y-%m-%d")
            classifications_file = (
                self.logs_dir / "analysis" / "classifications" / f"{date_str}.json"
            )
            classifications = self.classifier.load_classifications(classifications_file)

        # Build summary
        summary = {
            "date": date.strftime("%Y-%m-%d"),
            "generated_at": datetime.now().isoformat(),
            "total_errors": len(classifications),
            "by_category": {},
            "by_severity": {},
            "by_source": {},
            "critical_errors": [],
            "high_priority_patterns": [],
            "recommendations": [],
        }

        # Count by category, severity, source
        for c in classifications:
            summary["by_category"][c.category] = summary["by_category"].get(c.category, 0) + 1
            summary["by_severity"][c.severity] = summary["by_severity"].get(c.severity, 0) + 1
            summary["by_source"][c.source] = summary["by_source"].get(c.source, 0) + 1

        # Collect critical errors
        for c in classifications:
            if c.severity == "critical":
                summary["critical_errors"].append(
                    {
                        "error_id": c.error_id,
                        "source": c.source,
                        "message": c.message[:200],
                        "root_cause": c.root_cause,
                        "recommendation": c.recommendation,
                    }
                )

        # Find high-priority patterns (high severity + multiple occurrences)
        patterns_seen = {}
        for c in classifications:
            if c.severity in ("high", "critical"):
                if c.signature not in patterns_seen:
                    patterns_seen[c.signature] = {
                        "signature": c.signature,
                        "category": c.category,
                        "severity": c.severity,
                        "message": c.message[:100],
                        "root_cause": c.root_cause,
                        "recommendation": c.recommendation,
                        "count": 0,
                    }
                patterns_seen[c.signature]["count"] += 1

        summary["high_priority_patterns"] = sorted(
            patterns_seen.values(),
            key=lambda x: -x["count"],
        )[:10]

        # Collect unique recommendations
        recommendations_seen = set()
        for c in classifications:
            if c.severity in ("high", "critical") and c.recommendation:
                if c.recommendation not in recommendations_seen:
                    summary["recommendations"].append(c.recommendation)
                    recommendations_seen.add(c.recommendation)

        return summary

    def save_summary(self, summary: dict, output_file: Path | None = None) -> Path:
        """Save summary to file.

        Args:
            summary: Summary dict
            output_file: Output file path (default: summaries/YYYY-MM-DD.json)

        Returns:
            Path to saved file
        """
        if output_file is None:
            date_str = summary.get("date", datetime.now().strftime("%Y-%m-%d"))
            output_file = self.summaries_dir / f"{date_str}.json"

        with open(output_file, "w") as f:
            json.dump(summary, f, indent=2)

        # Also generate markdown summary
        md_file = output_file.with_suffix(".md")
        self._generate_markdown_summary(summary, md_file)

        logger.info(f"Saved summary to {output_file}")
        return output_file

    def _generate_markdown_summary(self, summary: dict, output_file: Path) -> None:
        """Generate markdown summary report.

        Args:
            summary: Summary dict
            output_file: Output file path
        """
        lines = [
            f"# Error Analysis Summary - {summary['date']}",
            "",
            f"*Generated at: {summary['generated_at']}*",
            "",
            f"**Total Errors:** {summary['total_errors']}",
            "",
            "## Breakdown",
            "",
            "### By Severity",
            "",
        ]

        for severity in ["critical", "high", "medium", "low"]:
            count = summary["by_severity"].get(severity, 0)
            if count > 0:
                emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    severity, "⚪"
                )
                lines.append(f"- {emoji} **{severity}**: {count}")

        lines.extend(
            [
                "",
                "### By Category",
                "",
            ]
        )

        for category, count in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
            lines.append(f"- **{category}**: {count}")

        lines.extend(
            [
                "",
                "### By Source",
                "",
            ]
        )

        for source, count in sorted(summary["by_source"].items(), key=lambda x: -x[1]):
            lines.append(f"- {source}: {count}")

        # Critical errors section
        if summary["critical_errors"]:
            lines.extend(
                [
                    "",
                    "## 🚨 Critical Errors",
                    "",
                ]
            )

            for error in summary["critical_errors"]:
                lines.extend(
                    [
                        f"### {error['source']}",
                        "",
                        f"**Message:** {error['message']}",
                        "",
                        f"**Root Cause:** {error['root_cause']}",
                        "",
                        f"**Recommendation:** {error['recommendation']}",
                        "",
                    ]
                )

        # High priority patterns
        if summary["high_priority_patterns"]:
            lines.extend(
                [
                    "",
                    "## ⚠️ High Priority Patterns",
                    "",
                ]
            )

            for pattern in summary["high_priority_patterns"][:5]:
                lines.extend(
                    [
                        f"### {pattern['category']} ({pattern['count']} occurrences)",
                        "",
                        f"**Message:** {pattern['message']}",
                        "",
                        f"**Root Cause:** {pattern['root_cause']}",
                        "",
                        f"**Recommendation:** {pattern['recommendation']}",
                        "",
                    ]
                )

        # Recommendations
        if summary["recommendations"]:
            lines.extend(
                [
                    "",
                    "## 📋 Recommendations",
                    "",
                ]
            )

            for i, rec in enumerate(summary["recommendations"][:10], 1):
                lines.append(f"{i}. {rec}")

        with open(output_file, "w") as f:
            f.write("\n".join(lines))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Log Analyzer - Claude-powered error analysis")

    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Run full analysis pipeline",
    )
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="Only aggregate logs",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Only extract errors",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Only classify errors",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Only generate summary",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Include logs from the last N hours (default: 24)",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=50,
        help="Maximum Claude API calls (default: 50)",
    )
    parser.add_argument(
        "--model",
        default="claude-3-5-haiku-latest",
        help="Claude model for classification",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout in seconds for Claude CLI calls (default: 60)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    analyzer = LogAnalyzer(model=args.model, timeout=args.timeout)

    if args.analyze or not any([args.aggregate, args.extract, args.classify, args.summary]):
        # Default: full analysis
        result = analyzer.analyze(hours=args.hours, max_calls=args.max_calls)

        print("\n" + "=" * 60)
        print("ANALYSIS COMPLETE")
        print("=" * 60)
        print(f"\nTotal errors: {result['total_errors']}")
        print(f"Classified: {result['classified_errors']}")
        print("\nFiles created:")
        print(f"  Aggregated: {result['aggregated_file']}")
        print(f"  Errors:     {result['errors_file']}")
        print(f"  Classified: {result['classifications_file']}")
        print(f"  Summary:    {result['summary_file']}")

        # Print summary highlights
        summary = result["summary"]
        if summary["critical_errors"]:
            print(f"\n🚨 CRITICAL ERRORS: {len(summary['critical_errors'])}")
            for error in summary["critical_errors"][:3]:
                print(f"  - [{error['source']}] {error['message'][:60]}...")

    elif args.aggregate:
        output = analyzer.aggregate(hours=args.hours)
        print(f"Logs aggregated to: {output}")

    elif args.extract:
        errors = analyzer.extract_errors(hours=args.hours)
        output = analyzer.extractor.save_errors(errors)
        print(f"Extracted {len(errors)} errors to: {output}")

    elif args.classify:
        errors = analyzer.extract_errors(hours=args.hours)
        classified = analyzer.classify_errors(errors, max_calls=args.max_calls)
        output = analyzer.classifier.save_classifications(classified)
        print(f"Classified {len(classified)} errors to: {output}")

    elif args.summary:
        summary = analyzer.generate_summary()
        output = analyzer.save_summary(summary)
        print(f"Summary saved to: {output}")


if __name__ == "__main__":
    main()
