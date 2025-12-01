#!/usr/bin/env python3
"""
Weekly Inefficiency Report Generator - Phase 3 of ADR-LLM-Inefficiency-Reporting

Generates weekly reports on LLM processing inefficiencies and delivers them via Slack.

This is the automated component that:
1. Analyzes trace sessions from the past week
2. Generates comprehensive inefficiency reports
3. Creates PRs with reports committed to docs/analysis/inefficiency/
4. Sends Slack notifications with summary and actionable insights

Reports: Creates PRs with reports committed to docs/analysis/inefficiency/ in the repo.
         Keeps only the last 5 reports (deletes older ones when creating PR #6).

Runs on host (not in container) via systemd timer:
- Weekly (Monday at 11:00 AM, after beads-analyzer)
- Can force run with --force flag

Usage:
    weekly_report_generator.py [--days N] [--force] [--no-slack] [--stdout]

Example:
    weekly_report_generator.py                    # Run weekly analysis with Slack
    weekly_report_generator.py --force            # Force run regardless of schedule
    weekly_report_generator.py --days 14          # Analyze last 14 days
    weekly_report_generator.py --no-slack         # Skip Slack notification
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the inefficiency-detector to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from inefficiency_detector import InefficiencyDetector
from inefficiency_schema import AggregateInefficiencyReport, Severity

# Constants
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ANALYSIS_DIR = REPO_ROOT / "docs" / "analysis" / "inefficiency"
SHARING_DIR = Path.home() / "sharing"


class WeeklyReportGenerator:
    """
    Generates weekly inefficiency reports with Slack delivery and GitHub PR creation.
    """

    def __init__(self, days: int = 7):
        self.days = days
        self.analysis_dir = ANALYSIS_DIR
        self.detector = InefficiencyDetector()

    def generate_weekly_report(self) -> tuple[AggregateInefficiencyReport | None, Path | None]:
        """
        Generate the weekly inefficiency report.

        Returns:
            Tuple of (report, report_file_path) or (None, None) if no data
        """
        print(f"Analyzing LLM inefficiencies from last {self.days} days...")

        # Calculate time range
        end = datetime.now()
        start = end - timedelta(days=self.days)

        # Run analysis
        report = self.detector.analyze_period(since=start, until=end)

        if report.total_sessions == 0:
            print("No sessions found in the specified period")
            return None, None

        # Ensure output directory exists
        self.analysis_dir.mkdir(parents=True, exist_ok=True)

        # Save report
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        report_file = self.analysis_dir / f"inefficiency-report-{timestamp}.md"
        metrics_file = self.analysis_dir / f"inefficiency-metrics-{timestamp}.json"

        # Generate markdown report
        self._generate_enhanced_markdown_report(report, report_file, timestamp)

        # Save JSON metrics
        self.detector.export_report(report, metrics_file)

        # Create latest symlinks
        latest_report = self.analysis_dir / "latest-report.md"
        latest_metrics = self.analysis_dir / "latest-metrics.json"

        if latest_report.exists() or latest_report.is_symlink():
            latest_report.unlink()
        if latest_metrics.exists() or latest_metrics.is_symlink():
            latest_metrics.unlink()

        latest_report.symlink_to(report_file.name)
        latest_metrics.symlink_to(metrics_file.name)

        print(f"\n✓ Report generated!")
        print(f"  Markdown: {report_file}")
        print(f"  JSON: {metrics_file}")

        return report, report_file

    def _generate_enhanced_markdown_report(
        self, report: AggregateInefficiencyReport, output_path: Path, timestamp: str
    ) -> None:
        """Generate an enhanced markdown report with additional formatting."""
        with open(output_path, "w") as f:
            # Header
            f.write(f"# LLM Inefficiency Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Period:** {report.time_period}\n\n")

            # Health Score
            health_score = self._calculate_health_score(report)
            f.write(f"## Health Score: {health_score}/100 {self._get_health_emoji(health_score)}\n\n")

            # Executive Summary
            f.write("## Executive Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Total Sessions Analyzed | {report.total_sessions} |\n")
            f.write(f"| Total Tokens Consumed | {report.total_tokens:,} |\n")
            f.write(f"| Total Wasted Tokens | {report.total_wasted_tokens:,} |\n")
            f.write(f"| Average Inefficiency Rate | {report.average_inefficiency_rate:.1f}% |\n")

            # Calculate potential savings
            if report.total_wasted_tokens > 0:
                # Rough cost estimate: ~$0.003 per 1K tokens for output
                potential_savings = (report.total_wasted_tokens / 1000) * 0.003
                f.write(f"| Estimated Weekly Savings | ~${potential_savings:.2f} |\n")

            f.write("\n")

            # Key Finding
            if report.top_issues:
                top_issue = report.top_issues[0]
                f.write(f"**Top Issue:** {top_issue['sub_category'].replace('_', ' ').title()} ")
                f.write(f"accounts for {top_issue['total_waste_tokens']:,} wasted tokens ")
                f.write(f"across {top_issue['occurrences']} occurrences.\n\n")

            # Inefficiency Breakdown by Category
            f.write("## Inefficiency Breakdown by Category\n\n")
            if report.category_counts:
                total_count = sum(report.category_counts.values())
                f.write("```\n")
                for category, count in sorted(report.category_counts.items(), key=lambda x: -x[1]):
                    percentage = (count / total_count * 100) if total_count > 0 else 0
                    bar_len = int(percentage / 2.5)  # 40 chars max
                    bar = "█" * bar_len
                    f.write(f"{category.replace('_', ' ').title():<25} {bar:<40} {percentage:.0f}%\n")
                f.write("```\n\n")
            else:
                f.write("*No inefficiencies detected this period!*\n\n")

            # Severity Breakdown
            f.write("## Inefficiency Breakdown by Severity\n\n")
            if report.severity_counts:
                for severity in ["high", "medium", "low"]:
                    count = report.severity_counts.get(severity, 0)
                    emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}[severity]
                    f.write(f"- {emoji} **{severity.upper()}**: {count}\n")
                f.write("\n")
            else:
                f.write("*No issues detected.*\n\n")

            # Top Issues (detailed)
            if report.top_issues:
                f.write("## Top 5 Issues\n\n")
                for i, issue in enumerate(report.top_issues, 1):
                    f.write(f"### {i}. {issue['sub_category'].replace('_', ' ').title()}\n\n")
                    f.write(f"**Category:** {issue['category'].replace('_', ' ').title()}\n\n")
                    f.write(f"**Occurrences:** {issue['occurrences']}\n\n")
                    f.write(f"**Total Waste:** {issue['total_waste_tokens']:,} tokens\n\n")
                    f.write(f"**Example:** {issue['example_description']}\n\n")
                    f.write(f"**Recommendation:** {issue['recommendation']}\n\n")
                    f.write("---\n\n")

            # Sessions with Highest Inefficiency
            f.write("## Sessions with Highest Inefficiency\n\n")
            top_sessions = sorted(
                report.sessions, key=lambda s: s.inefficiency_rate, reverse=True
            )[:5]

            if top_sessions:
                for session in top_sessions:
                    f.write(f"### Session: `{session.session_id}`\n\n")
                    f.write(f"- **Task:** {session.task_id or 'N/A'}\n")
                    f.write(f"- **Inefficiency Rate:** {session.inefficiency_rate:.1f}%\n")
                    f.write(f"- **Wasted Tokens:** {session.total_wasted_tokens:,} / {session.total_tokens:,}\n")
                    f.write(f"- **Issues Found:** {len(session.inefficiencies)}\n\n")

                    if session.inefficiencies:
                        f.write("**Issues:**\n")
                        for ineff in session.inefficiencies[:5]:  # Limit to 5
                            severity_emoji = {
                                Severity.HIGH: "🔴",
                                Severity.MEDIUM: "🟡",
                                Severity.LOW: "🟢"
                            }.get(ineff.severity, "⚪")
                            f.write(f"- {severity_emoji} {ineff.description}\n")
                        if len(session.inefficiencies) > 5:
                            f.write(f"- *(+{len(session.inefficiencies) - 5} more)*\n")
                        f.write("\n")
            else:
                f.write("*No sessions analyzed in this period.*\n\n")

            # Actionable Improvements Section
            f.write("## Actionable Improvements\n\n")
            recommendations = self._generate_recommendations(report)
            if recommendations:
                f.write("### High Priority (This Week)\n\n")
                for i, rec in enumerate(recommendations[:3], 1):
                    f.write(f"{i}. {rec}\n")
                f.write("\n")

                if len(recommendations) > 3:
                    f.write("### Medium Priority (Next Sprint)\n\n")
                    for i, rec in enumerate(recommendations[3:], 4):
                        f.write(f"{i}. {rec}\n")
                    f.write("\n")
            else:
                f.write("*No specific recommendations - keep up the good work!*\n\n")

            # Footer
            f.write("---\n\n")
            f.write(f"*Report generated from {report.total_sessions} sessions over {self.days} days*\n")
            f.write(f"*Analysis performed by [LLM Inefficiency Detector](../../../docs/adr/in-progress/ADR-LLM-Inefficiency-Reporting.md)*\n")

    def _calculate_health_score(self, report: AggregateInefficiencyReport) -> int:
        """Calculate an overall health score (0-100)."""
        if report.total_sessions == 0:
            return 100

        score = 100

        # Deduct based on inefficiency rate
        avg_rate = report.average_inefficiency_rate
        if avg_rate > 20:
            score -= 30
        elif avg_rate > 15:
            score -= 20
        elif avg_rate > 10:
            score -= 10
        elif avg_rate > 5:
            score -= 5

        # Deduct for severity
        high_count = report.severity_counts.get("high", 0)
        medium_count = report.severity_counts.get("medium", 0)

        score -= high_count * 5
        score -= medium_count * 2

        # Bonus for low waste percentage
        if report.total_tokens > 0:
            waste_pct = (report.total_wasted_tokens / report.total_tokens) * 100
            if waste_pct < 5:
                score += 10
            elif waste_pct < 10:
                score += 5

        return max(0, min(100, score))

    def _get_health_emoji(self, score: int) -> str:
        """Get emoji for health score."""
        if score >= 90:
            return "🌟"
        elif score >= 70:
            return "✅"
        elif score >= 50:
            return "⚠️"
        else:
            return "🔴"

    def _generate_recommendations(self, report: AggregateInefficiencyReport) -> list[str]:
        """Generate actionable recommendations based on the report."""
        recommendations = []

        for issue in report.top_issues[:5]:
            sub_cat = issue["sub_category"]
            rec = issue["recommendation"]

            if sub_cat == "documentation_miss":
                recommendations.append(
                    f"**Update CLAUDE.md**: Add guidance to prefer glob patterns for file discovery. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "retry_storm":
                recommendations.append(
                    f"**Add error handling guidance**: Investigate errors before retrying, check prerequisites. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "redundant_read":
                recommendations.append(
                    f"**Improve context management**: Add guidance to avoid re-reading files already in context. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "excessive_context":
                recommendations.append(
                    f"**Add file reading guidance**: Use limit/offset for large files. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "api_confusion":
                recommendations.append(
                    f"**Improve tool documentation**: Add clearer parameter examples. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "search_failure":
                recommendations.append(
                    f"**Add search strategy guidance**: Verify targets exist before extensive searching. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            elif sub_cat == "parameter_error":
                recommendations.append(
                    f"**Add parameter validation guidance**: Verify tool parameters before calling. "
                    f"({issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens wasted)"
                )
            else:
                recommendations.append(f"**{sub_cat.replace('_', ' ').title()}**: {rec}")

        return recommendations

    def send_slack_notification(self, report: AggregateInefficiencyReport, report_file: Path) -> bool:
        """
        Send Slack notification with report summary.

        Returns:
            True if notification sent successfully
        """
        if report.total_sessions == 0:
            print("Skipping Slack notification - no sessions to report")
            return False

        try:
            # Try to use the notifications library
            notifications_path = Path.home() / "khan" / "james-in-a-box" / "jib-container" / "shared"
            sys.path.insert(0, str(notifications_path))

            from notifications import slack_notify

            health_score = self._calculate_health_score(report)

            # Build notification body
            body_lines = [
                f"**Health Score:** {health_score}/100 {self._get_health_emoji(health_score)}",
                "",
                "**Quick Stats:**",
                f"- Sessions Analyzed: {report.total_sessions}",
                f"- Total Tokens: {report.total_tokens:,}",
                f"- Wasted Tokens: {report.total_wasted_tokens:,}",
                f"- Inefficiency Rate: {report.average_inefficiency_rate:.1f}%",
                "",
            ]

            # Add top issue
            if report.top_issues:
                top = report.top_issues[0]
                body_lines.extend([
                    "**Top Issue:**",
                    f"- {top['sub_category'].replace('_', ' ').title()}: {top['occurrences']} occurrences, {top['total_waste_tokens']:,} tokens wasted",
                    f"- Recommendation: {top['recommendation'][:100]}...",
                    "",
                ])

            # Add severity summary
            body_lines.extend([
                "**Severity Summary:**",
                f"- 🔴 High: {report.severity_counts.get('high', 0)}",
                f"- 🟡 Medium: {report.severity_counts.get('medium', 0)}",
                f"- 🟢 Low: {report.severity_counts.get('low', 0)}",
            ])

            body = "\n".join(body_lines)

            slack_notify(
                f"Weekly LLM Inefficiency Report - Score: {health_score}/100",
                body
            )

            print("✓ Slack notification sent")
            return True

        except ImportError as e:
            print(f"WARNING: Could not import notifications library: {e}")
            return self._fallback_slack_notification(report)
        except Exception as e:
            print(f"WARNING: Failed to send Slack notification: {e}")
            return False

    def _fallback_slack_notification(self, report: AggregateInefficiencyReport) -> bool:
        """Fallback to file-based notification if library not available."""
        try:
            notifications_dir = SHARING_DIR / "notifications"
            notifications_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            notification_file = notifications_dir / f"{timestamp}-inefficiency-report.md"

            health_score = self._calculate_health_score(report)

            content = f"""# 📊 Weekly LLM Inefficiency Report

**Health Score**: {health_score}/100 {self._get_health_emoji(health_score)}

## Quick Stats
- Sessions: {report.total_sessions}
- Total Tokens: {report.total_tokens:,}
- Wasted: {report.total_wasted_tokens:,} ({report.average_inefficiency_rate:.1f}%)

## Severity Summary
- 🔴 High: {report.severity_counts.get('high', 0)}
- 🟡 Medium: {report.severity_counts.get('medium', 0)}
- 🟢 Low: {report.severity_counts.get('low', 0)}

Full report available in docs/analysis/inefficiency/
"""

            with open(notification_file, "w") as f:
                f.write(content)

            print(f"✓ Notification file created: {notification_file}")
            return True

        except Exception as e:
            print(f"ERROR: Failed to create notification file: {e}")
            return False

    def _cleanup_old_reports(self, max_reports: int = 5) -> list[Path]:
        """Keep only the last N reports, return files to be deleted."""
        report_files = sorted(
            self.analysis_dir.glob("inefficiency-report-*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        metrics_files = sorted(
            self.analysis_dir.glob("inefficiency-metrics-*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        to_delete = []

        if len(report_files) > max_reports:
            to_delete.extend(report_files[max_reports:])
        if len(metrics_files) > max_reports:
            to_delete.extend(metrics_files[max_reports:])

        return to_delete

    def create_pr_with_report(
        self, report: AggregateInefficiencyReport, report_file: Path, timestamp: str
    ) -> str | None:
        """
        Create a PR with the inefficiency report.

        Returns:
            PR URL if successful, None otherwise
        """
        print("\nPreparing to create PR with inefficiency report...")

        # Cleanup old reports
        to_delete = self._cleanup_old_reports(max_reports=5)

        branch_name = f"inefficiency-report-{timestamp}"

        try:
            # Create new branch from origin/main
            subprocess.run(
                ["git", "checkout", "-b", branch_name, "origin/main"],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            print(f"✓ Created branch: {branch_name}")

            # Delete old reports if any
            if to_delete:
                for file_path in to_delete:
                    subprocess.run(
                        ["git", "rm", str(file_path)],
                        check=True,
                        cwd=REPO_ROOT,
                        capture_output=True,
                        text=True,
                    )
                print(f"✓ Removed {len(to_delete)} old report(s)")

            # Stage new report files
            subprocess.run(
                ["git", "add", str(self.analysis_dir)],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )

            # Commit
            health_score = self._calculate_health_score(report)
            commit_message = f"""chore: Add LLM inefficiency report {timestamp}

Health Score: {health_score}/100
- Sessions Analyzed: {report.total_sessions}
- Total Tokens: {report.total_tokens:,}
- Wasted Tokens: {report.total_wasted_tokens:,}
- Inefficiency Rate: {report.average_inefficiency_rate:.1f}%

High-severity issues: {report.severity_counts.get('high', 0)}
"""
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            print("✓ Committed changes")

            # Push branch
            subprocess.run(
                ["git", "push", "origin", branch_name],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            print(f"✓ Pushed to origin/{branch_name}")

            # Create PR
            pr_title = f"LLM Inefficiency Report - {timestamp}"
            pr_body = f"""## LLM Inefficiency Report

**Health Score**: {health_score}/100 {self._get_health_emoji(health_score)}

### Quick Stats
- 📊 Sessions Analyzed: {report.total_sessions}
- 🔢 Total Tokens: {report.total_tokens:,}
- ⚠️ Wasted Tokens: {report.total_wasted_tokens:,}
- 📈 Inefficiency Rate: {report.average_inefficiency_rate:.1f}%

### Severity Summary
- 🔴 High: {report.severity_counts.get('high', 0)}
- 🟡 Medium: {report.severity_counts.get('medium', 0)}
- 🟢 Low: {report.severity_counts.get('low', 0)}

### Top Issues
"""
            for issue in report.top_issues[:3]:
                pr_body += f"- **{issue['sub_category'].replace('_', ' ').title()}**: {issue['occurrences']} occurrences, {issue['total_waste_tokens']:,} tokens\n"

            pr_body += f"""
### Files in this PR
- `docs/analysis/inefficiency/inefficiency-report-{timestamp}.md` - Full report
- `docs/analysis/inefficiency/inefficiency-metrics-{timestamp}.json` - Machine-readable metrics
- Symlinks updated to point to latest reports

See the full report for detailed analysis and actionable recommendations.
"""
            # Add cleanup note if files were deleted
            if to_delete:
                pr_body += f"\n### Cleanup\n- Removed {len(to_delete)} old report(s) to maintain max 5 reports\n"

            result = subprocess.run(
                ["gh", "pr", "create", "--title", pr_title, "--body", pr_body, "--base", "main", "--head", branch_name],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            pr_url = result.stdout.strip()
            print(f"✓ Created PR: {pr_url}")
            return pr_url

        except subprocess.CalledProcessError as e:
            print(f"ERROR creating PR: {e}", file=sys.stderr)
            print(f"  stdout: {e.stdout}", file=sys.stderr)
            print(f"  stderr: {e.stderr}", file=sys.stderr)
            # Try to return to original branch
            try:
                subprocess.run(
                    ["git", "checkout", "-"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                )
            except Exception:
                pass
            return None

    def run(self, send_slack: bool = True) -> bool:
        """
        Run the full weekly report generation workflow.

        Returns:
            True if report generated successfully
        """
        # Generate report
        report, report_file = self.generate_weekly_report()

        if report is None:
            print("No data to report")
            return False

        # Create timestamp for PR
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Send Slack notification
        if send_slack:
            self.send_slack_notification(report, report_file)

        # Create PR with report
        pr_url = self.create_pr_with_report(report, report_file, timestamp)

        print("\n" + "=" * 60)
        print("Weekly Inefficiency Report Complete")
        print("=" * 60)
        print(f"Sessions Analyzed: {report.total_sessions}")
        print(f"Inefficiency Rate: {report.average_inefficiency_rate:.1f}%")
        print(f"Health Score: {self._calculate_health_score(report)}/100")
        if pr_url:
            print(f"PR Created: {pr_url}")
        print("=" * 60)

        return True


def check_last_run(analysis_dir: Path) -> datetime | None:
    """Check when the analyzer was last run."""
    try:
        reports = list(analysis_dir.glob("inefficiency-report-*.md"))
        if not reports:
            return None

        reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        most_recent = reports[0]
        return datetime.fromtimestamp(most_recent.stat().st_mtime)
    except Exception:
        return None


def should_run_analysis(analysis_dir: Path, force: bool = False) -> bool:
    """Determine if analysis should run based on weekly schedule."""
    if force:
        print("Force flag set - running analysis")
        return True

    last_run = check_last_run(analysis_dir)

    if last_run is None:
        print("No previous analysis found - running analysis")
        return True

    days_since_last_run = (datetime.now() - last_run).days

    if days_since_last_run >= 7:
        print(f"Last analysis was {days_since_last_run} days ago - running analysis")
        return True
    else:
        print(f"Last analysis was {days_since_last_run} days ago (< 7 days) - skipping")
        print("Use --force to run anyway")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate weekly LLM inefficiency reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Run if last analysis was >7 days ago
  %(prog)s --force            # Force run regardless of schedule
  %(prog)s --days 14          # Analyze last 14 days
  %(prog)s --no-slack         # Skip Slack notification
        """,
    )
    parser.add_argument(
        "--days", type=int, default=7, help="Number of days to analyze (default: 7)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force analysis even if run recently"
    )
    parser.add_argument(
        "--no-slack", action="store_true", help="Skip Slack notification"
    )
    parser.add_argument(
        "--stdout", action="store_true", help="Print report to stdout"
    )

    args = parser.parse_args()

    # Check if we should run
    if not should_run_analysis(ANALYSIS_DIR, force=args.force):
        sys.exit(0)

    # Run report generation
    generator = WeeklyReportGenerator(days=args.days)
    success = generator.run(send_slack=not args.no_slack)

    # Optionally print to stdout
    if args.stdout:
        latest = ANALYSIS_DIR / "latest-report.md"
        if latest.exists():
            print("\n" + "=" * 80)
            print(latest.read_text())
            print("=" * 80)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
